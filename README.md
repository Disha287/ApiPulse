# API Pulse AI

Distributed API Health Monitoring, Time-Series Observability, and Incident Lifecycle Platform.

## Architecture Overview

API Pulse AI monitors critical HTTP endpoints with high-precision probes, tracks incident lifecycles with state machines, prevents alert storms via distributed Redis cooldown locks, and delivers real-time time-series latency percentiles (P50, P95, P99) and SLA uptime metrics.

### System Components

- **FastAPI Core Backend** (`http://localhost:8000`): Asynchronous REST API providing monitor registration, incident history, on-demand probing, and analytical rollups.
- **Background Async Scheduler**: High-concurrency worker loop utilizing `asyncio.Semaphore(50)` and connection pooling (`httpx.AsyncClient`) to probe active targets on configured intervals.
- **3-Strike State Machine**:
  - Consecutive Failures 1–2: Transitions monitor to `DEGRADED`.
  - Consecutive Failures 3+: Transitions monitor to `DOWN`, creates an `OPEN` `Incident`, and requests a distributed Redis cooldown lock.
  - Recovery: On subsequent success, resets failure counts to 0, transitions monitor to `HEALTHY`, marks the incident `RESOLVED`, clears the Redis lock, and dispatches a recovery notification.
- **Redis Alert Deduplication**: Atomic `SET alert:cooldown:<monitor_id> <incident_id> EX 300 NX` prevents notification spam during extended outages.
- **Time-Series Analytics Engine**: In-database percentile rollups using PostgreSQL `PERCENTILE_CONT(0.50|0.95|0.99)` and chronological time-bucketed rollups.
- **Chaos Target Simulator** (`http://localhost:9000`): Mock server simulating real-world anomalies (`/health`, `/flaky`, `/latent-spike`, `/rate-limited`, `/down`).
- **PostgreSQL 16 & Redis 7**: Containerized services configured with persistent volumes via Docker Compose.

---

## Directory Structure

```text
ApiPulse/
├── docker-compose.yml          # PostgreSQL & Redis infrastructure
├── pyproject.toml              # Pyright / IDE tooling config
├── pyrightconfig.json          # Language server configuration
├── .vscode/settings.json       # Workspace editor settings
├── backend/
│   ├── requirements.txt        # Backend Python dependencies
│   ├── init_db.py              # Database table creator & schema migration runner
│   ├── main.py                 # FastAPI application entrypoint with lifespan
│   └── app/
│       ├── api/
│       │   └── monitors.py     # CRUD, manual probe & analytics REST endpoints
│       ├── core/
│       │   ├── config.py       # Pydantic BaseSettings (DB & Redis connection URLs)
│       │   ├── database.py     # Async SQLAlchemy 2.0 engine & session maker
│       │   └── redis_client.py # Async Redis connection singleton & lifecycle
│       ├── models/
│       │   └── models.py       # SQLAlchemy models: Monitor, ProbeLog, Incident
│       ├── schemas/
│       │   ├── monitor.py      # Monitor & Incident Pydantic v2 schemas
│       │   └── analytics.py    # Time-series & SLA summary schemas
│       ├── services/
│       │   ├── prober.py       # High-precision async HTTP prober & 3-strike state machine
│       │   ├── alert_service.py# Redis cooldown locks & structured alert dispatching
│       │   └── analytics_service.py # PostgreSQL percentile calculation engine
│       └── workers/
│           └── scheduler.py    # Concurrency-bounded background probe scheduler
└── mock_server/
    └── main.py                 # Chaos Target Simulator FastAPI app
```

---

## Quickstart

### 1. Start Infrastructure
```bash
docker compose up -d
```

### 2. Install Dependencies & Initialize Database
```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\pip install -r backend/requirements.txt
$env:PYTHONPATH="backend"; .\.venv\Scripts\python backend/init_db.py
```

### 3. Start Mock Chaos Server
```bash
.\.venv\Scripts\python -m uvicorn mock_server.main:app --port 9000
```

### 4. Start API Pulse AI Backend
```bash
$env:PYTHONPATH="backend"; .\.venv\Scripts\python -m uvicorn main:app --app-dir backend --port 8000 --reload
```

---

## Key Endpoints

- `GET /health` — Service health check
- `POST /api/v1/monitors` — Register target monitor
- `GET /api/v1/monitors` — List registered monitors
- `GET /api/v1/monitors/overview` — Platform-wide status counts & 24h global SLA uptime
- `GET /api/v1/monitors/{id}/metrics?window_hours=24` — P50, P95, P99 latencies and SLA uptime %
- `GET /api/v1/monitors/{id}/timeseries?window_hours=1&bucket_minutes=1` — Time-bucketed series
- `POST /api/v1/monitors/{id}/probe` — Trigger on-demand manual probe
- `GET /api/v1/monitors/{id}/incidents` — List all incidents for monitor
- `GET /api/v1/monitors/incidents/active` — List open incidents across the platform

