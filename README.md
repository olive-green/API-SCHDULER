# API Scheduler - Cron for API Calls

A robust, production-ready backend service that schedules and executes HTTP requests to external targets. Think of it as "cron for API calls" with comprehensive observability and error handling.

## 🎯 Features

- **Target Management**: Define HTTP endpoints with custom methods, headers, and body templates
- **Flexible Scheduling**: 
  - **INTERVAL**: Run indefinitely every N seconds
  - **WINDOW**: Run for M seconds, then automatically stop
- **Comprehensive Observability**: 
  - Track all runs with detailed metrics (latency, status, response size)
  - Error classification (timeout, DNS, connection, 4xx, 5xx)
  - System-wide and per-schedule metrics
- **Pause/Resume**: Full control over schedule execution
- **Graceful Restarts**: Schedules persist and resume after server restarts
- **Concurrency Safe**: Handles high concurrency with duplicate prevention

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- pip

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd url

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Run the Server

```bash
# Option 1: Using uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Option 2: Using Python
python -m app.main

# Option 3: Using the run script
chmod +x run.sh
./run.sh
```

The API will be available at:
- **API**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 📖 API Usage

### 1. Create a Target

```bash
curl -X POST "http://localhost:8000/targets" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "httpbin-test",
    "url": "https://httpbin.org/get",
    "method": "GET",
    "headers": {"User-Agent": "API-Scheduler/1.0"}
  }'
```

### 2. Create a Schedule

**Interval Schedule** (runs indefinitely):
```bash
curl -X POST "http://localhost:8000/schedules" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "every-30-seconds",
    "target_id": 1,
    "schedule_type": "INTERVAL",
    "interval_seconds": 30
  }'
```

**Window Schedule** (runs for 5 minutes):
```bash
curl -X POST "http://localhost:8000/schedules" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "5-minute-test",
    "target_id": 1,
    "schedule_type": "WINDOW",
    "interval_seconds": 10,
    "duration_seconds": 300
  }'
```

### 3. Pause/Resume Schedule

```bash
# Pause
curl -X POST "http://localhost:8000/schedules/1/pause"

# Resume
curl -X POST "http://localhost:8000/schedules/1/resume"
```

### 4. View Runs

```bash
# List all runs
curl "http://localhost:8000/runs"

# Filter by schedule
curl "http://localhost:8000/runs?schedule_id=1"

# Filter by status
curl "http://localhost:8000/runs?status_filter=SUCCESS"

# Get detailed run info
curl "http://localhost:8000/runs/1"
```

### 5. View Metrics

```bash
# System metrics
curl "http://localhost:8000/metrics"

# Per-schedule metrics
curl "http://localhost:8000/metrics/schedules"
```

## 🏗️ Architecture

### Technology Stack

- **FastAPI**: Modern, async web framework with auto-generated docs
- **SQLAlchemy**: ORM for database operations with async support
- **APScheduler**: Reliable job scheduling with persistence
- **HTTPX**: Async HTTP client for making requests
- **SQLite**: Default database (easily switchable to PostgreSQL)

### Key Components

```
app/
├── main.py              # FastAPI app with lifespan management
├── models.py            # SQLAlchemy models (Target, Schedule, Run, Attempt)
├── schemas.py           # Pydantic schemas for validation
├── database.py          # Database configuration and session management
├── config.py            # Application settings
├── scheduler.py         # APScheduler integration
├── api/                 # API endpoints
│   ├── targets.py       # Target CRUD operations
│   ├── schedules.py     # Schedule management
│   ├── runs.py          # Run observability
│   └── metrics.py       # Metrics endpoints
└── services/
    └── executor.py      # HTTP request execution
```

### Database Schema

**Target**: HTTP endpoint configuration
- id, name, url, method, headers, body_template
- Relationships: One-to-many with Schedule

**Schedule**: Scheduling configuration
- id, name, target_id, schedule_type, interval_seconds, duration_seconds
- status (ACTIVE, PAUSED, STOPPED), job_id
- Relationships: Many-to-one with Target, One-to-many with Run

**Run**: Individual execution record
- id, schedule_id, status, timestamps, HTTP details
- Captures: latency, status_code, response_size, error details
- Relationships: Many-to-one with Schedule, One-to-many with Attempt

**Attempt**: Individual attempt within a run (for future retry support)
- id, run_id, attempt_number, status, timing, error details

## 🔑 Key Design Decisions

### 1. **APScheduler for Reliability**

**Decision**: Use APScheduler instead of building from scratch or using Celery

**Rationale**:
- APScheduler provides robust job scheduling with misfire handling
- Built-in support for interval and cron-like scheduling
- Simpler than Celery (no message broker required)
- `coalesce=True`: Prevents duplicate executions during downtime
- `max_instances=1`: Ensures only one instance of a job runs at a time

**Trade-offs**:
- Memory-based jobstore (can switch to SQLAlchemy jobstore for persistence)
- Single-process (for distributed, would need Celery/RQ)

### 2. **Graceful Restart Handling**

**Implementation**:
- Schedules persisted in SQLite database
- On startup: `load_schedules()` reloads all ACTIVE schedules
- APScheduler `job_id` stored in database for tracking
- Window schedules recalculate remaining time on restart

**Guarantees**:
- No schedule loss on restart
- No duplicate schedules
- Automatic resume of active schedules

### 3. **Error Classification**

**Categories**:
- `SUCCESS`: 2xx responses
- `TIMEOUT`: Request timeout or connection timeout
- `DNS_ERROR`: DNS resolution failure
- `CONNECTION_ERROR`: Cannot connect to host
- `FAILED`: 4xx, 5xx, or other errors

**Rationale**: Clear error classification helps with debugging and monitoring

### 4. **Concurrency Safety**

**Mechanisms**:
- APScheduler `max_instances=1`: Prevents concurrent execution of same job
- APScheduler `coalesce=True`: Combines missed executions into one
- Database transactions with async SQLAlchemy
- Job execution creates Run record immediately

**Trade-offs**:
- If a job takes longer than the interval, next execution is skipped
- For true parallel execution, would need job queuing (Celery)

### 5. **Two Schedule Types**

**INTERVAL**: Simple repeating execution
- Use case: Health checks, periodic data sync
- Runs until explicitly paused/deleted

**WINDOW**: Time-bounded execution
- Use case: Load testing, temporary monitoring
- Automatically stops after duration
- Status changes to STOPPED

**Rationale**: Covers most common scheduling patterns while keeping API simple

### 6. **SQLite for Development, PostgreSQL for Production**

**Current**: SQLite with async support (aiosqlite)

**Production Path**:
```python
# In .env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/scheduler
```

**Trade-offs**:
- SQLite: Simple, no setup, file-based
- PostgreSQL: Better concurrency, production-ready, supports advanced features

## 🐛 Error Handling

### Request Timeouts
- Default: 30 seconds (configurable)
- Classified as `TIMEOUT`
- Latency tracked up to timeout

### Network Errors
- DNS failures → `DNS_ERROR`
- Connection refused → `CONNECTION_ERROR`
- SSL errors → `CONNECTION_ERROR`

### HTTP Errors
- 4xx → `FAILED` with `http_4xx` error type
- 5xx → `FAILED` with `http_5xx` error type
- Response body captured (truncated to 10KB)

### Scheduler Failures
- Job execution errors logged
- Run record created even on failure
- Schedule remains active (no automatic disable)

## 📊 Observability

### Metrics Available

**System Metrics** (`/metrics`):
- Total targets, schedules (by status)
- Total runs, runs in last hour
- Overall success rate
- Average latency

**Schedule Metrics** (`/metrics/schedules`):
- Per-schedule run counts
- Success/failure breakdown
- Average latency
- Last run timestamp


## 🔧 Configuration

### Environment Variables

Create a `.env` file:

```bash
# Database
DATABASE_URL=sqlite+aiosqlite:///./scheduler.db

# Scheduler
SCHEDULER_TIMEZONE=UTC
MAX_CONCURRENT_JOBS=100

# HTTP Client
DEFAULT_TIMEOUT=30
MAX_RETRIES=0

# Application
APP_TITLE=API Scheduler
APP_VERSION=1.0.0
LOG_LEVEL=INFO
```

### Configuration Options

All settings in `app/config.py`:
- `database_url`: Database connection string
- `scheduler_timezone`: Timezone for scheduler (default: UTC)
- `max_concurrent_jobs`: Max simultaneous jobs
- `default_timeout`: HTTP request timeout (seconds)
- `log_level`: Logging level (DEBUG, INFO, WARNING, ERROR)



## 📝 API Reference

See the auto-generated documentation at `/docs` when the server is running.

### Endpoints Summary

**Targets**
- `POST /targets` - Create target
- `GET /targets` - List targets
- `GET /targets/{id}` - Get target
- `PUT /targets/{id}` - Update target
- `DELETE /targets/{id}` - Delete target

**Schedules**
- `POST /schedules` - Create schedule
- `GET /schedules` - List schedules
- `GET /schedules/{id}` - Get schedule
- `PUT /schedules/{id}` - Update schedule
- `POST /schedules/{id}/pause` - Pause schedule
- `POST /schedules/{id}/resume` - Resume schedule
- `DELETE /schedules/{id}` - Delete schedule

**Runs**
- `GET /runs` - List runs (with filters)
- `GET /runs/{id}` - Get run details

**Metrics**
- `GET /metrics` - System metrics
- `GET /metrics/schedules` - Per-schedule metrics

**Health**
- `GET /health` - Health check

## 🤝 Contributing

This is a demo project. For production use:
1. Fork the repository
2. Add tests
3. Implement production features from checklist
4. Submit PR



## 🎥 Demo Video

[Link to Loom video will be here]

## 💡 AI Tools Used

This project was built with assistance from:
- **Cursor AI and Claude Sonnet**: Code completion and generation


## 📧 Contact

For questions or feedback, please open an issue on GitHub.



