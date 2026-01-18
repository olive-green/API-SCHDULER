import httpx
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Schedule, Target, Run, Attempt, RunStatus, HTTPMethod
from app.config import settings

logger = logging.getLogger(__name__)


class RequestExecutor:
    """Executes HTTP requests and records results"""
    
    def __init__(self):
        self.timeout = httpx.Timeout(settings.default_timeout, connect=10.0)
        self.limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
    
    async def execute_schedule(self, schedule_id: int, db: AsyncSession) -> Optional[Run]:
        """
        Execute a scheduled HTTP request
        
        Args:
            schedule_id: Schedule ID to execute
            db: Database session
            
        Returns:
            Run object if successful, None otherwise
        """
        try:
            # Load schedule and target
            result = await db.execute(
                select(Schedule).filter(Schedule.id == schedule_id)
            )
            schedule = result.scalar_one_or_none()
            
            if not schedule:
                logger.error(f"Schedule {schedule_id} not found")
                return None
            
            result = await db.execute(
                select(Target).filter(Target.id == schedule.target_id)
            )
            target = result.scalar_one_or_none()
            
            if not target:
                logger.error(f"Target {schedule.target_id} not found for schedule {schedule_id}")
                return None
            
            # Create run record
            run = Run(
                schedule_id=schedule_id,
                status=RunStatus.FAILED,  # Default to failed, update on success
                request_url=str(target.url),
                request_method=target.method.value,
                request_headers=target.headers,
                request_body=target.body_template,
                started_at=datetime.utcnow(),
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)
            
            # Execute the request
            status, latency, status_code, error_msg, error_type, response_data = await self._execute_request(
                url=str(target.url),
                method=target.method,
                headers=self._parse_headers(target.headers),
                body=target.body_template,
            )
            
            # Update run with results
            run.status = status
            run.latency_ms = latency
            run.status_code = status_code
            run.error_message = error_msg
            run.error_type = error_type
            run.completed_at = datetime.utcnow()
            
            if response_data:
                run.response_headers = json.dumps(dict(response_data.get('headers', {})))
                run.response_body = response_data.get('body', '')[:10000]  # Truncate to 10KB
                run.response_size_bytes = response_data.get('size', 0)
            
            # Create attempt record
            attempt = Attempt(
                run_id=run.id,
                attempt_number=1,
                status=status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                status_code=status_code,
                latency_ms=latency,
                error_message=error_msg,
                error_type=error_type,
            )
            db.add(attempt)
            
            await db.commit()
            await db.refresh(run)
            
            logger.info(
                f"Schedule {schedule_id} executed: status={status.value}, "
                f"latency={latency}ms, code={status_code}"
            )
            
            return run
            
        except Exception as e:
            logger.error(f"Error executing schedule {schedule_id}: {e}", exc_info=True)
            await db.rollback()
            return None
    
    async def _execute_request(
        self,
        url: str,
        method: HTTPMethod,
        headers: Optional[Dict[str, str]],
        body: Optional[str],
    ) -> Tuple[RunStatus, Optional[float], Optional[int], Optional[str], Optional[str], Optional[Dict]]:
        """
        Execute HTTP request and classify the result
        
        Returns:
            (status, latency_ms, status_code, error_message, error_type, response_data)
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout, limits=self.limits) as client:
                # Prepare request
                request_kwargs = {
                    'method': method.value,
                    'url': url,
                    'headers': headers or {},
                }
                
                if body and method in [HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH]:
                    # Try to parse as JSON, otherwise send as text
                    try:
                        request_kwargs['json'] = json.loads(body)
                    except json.JSONDecodeError:
                        request_kwargs['content'] = body
                
                # Execute request
                response = await client.request(**request_kwargs)
                
                # Calculate latency
                latency = (asyncio.get_event_loop().time() - start_time) * 1000
                
                # Prepare response data
                response_data = {
                    'headers': dict(response.headers),
                    'body': response.text,
                    'size': len(response.content),
                }
                
                # Classify response
                if 200 <= response.status_code < 300:
                    return RunStatus.SUCCESS, latency, response.status_code, None, None, response_data
                elif response.status_code >= 500:
                    return (
                        RunStatus.FAILED,
                        latency,
                        response.status_code,
                        f"Server error: {response.status_code}",
                        "http_5xx",
                        response_data,
                    )
                elif response.status_code >= 400:
                    return (
                        RunStatus.FAILED,
                        latency,
                        response.status_code,
                        f"Client error: {response.status_code}",
                        "http_4xx",
                        response_data,
                    )
                else:
                    return (
                        RunStatus.FAILED,
                        latency,
                        response.status_code,
                        f"Unexpected status: {response.status_code}",
                        "http_unexpected",
                        response_data,
                    )
                    
        except httpx.TimeoutException as e:
            latency = (asyncio.get_event_loop().time() - start_time) * 1000
            return RunStatus.TIMEOUT, latency, None, str(e), "timeout", None
            
        except httpx.ConnectError as e:
            latency = (asyncio.get_event_loop().time() - start_time) * 1000
            return RunStatus.CONNECTION_ERROR, latency, None, str(e), "connection", None
            
        except httpx.ConnectTimeout as e:
            latency = (asyncio.get_event_loop().time() - start_time) * 1000
            return RunStatus.TIMEOUT, latency, None, str(e), "timeout", None
            
        except Exception as e:
            latency = (asyncio.get_event_loop().time() - start_time) * 1000
            # Check if it's a DNS error
            error_str = str(e).lower()
            if 'name or service not known' in error_str or 'nodename nor servname provided' in error_str:
                return RunStatus.DNS_ERROR, latency, None, str(e), "dns", None
            return RunStatus.FAILED, latency, None, str(e), "unknown", None
    
    def _parse_headers(self, headers_json: Optional[str]) -> Optional[Dict[str, str]]:
        """Parse headers from JSON string"""
        if not headers_json:
            return None
        try:
            return json.loads(headers_json)
        except json.JSONDecodeError:
            return None

