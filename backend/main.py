import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.monitors import router as monitors_router
from app.core.config import settings
from app.core.redis_client import close_redis
from app.workers.scheduler import run_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("apipulse.main")

stop_event = asyncio.Event()
scheduler_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler_task, stop_event
    logger.info("Starting up API Pulse AI Backend...")
    stop_event.clear()
    scheduler_task = asyncio.create_task(run_scheduler(stop_event))
    yield
    logger.info("Shutting down API Pulse AI Backend...")
    stop_event.set()
    if scheduler_task:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
    await close_redis()
    logger.info("Shutdown completed.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Distributed API health monitoring, time-series observability, and anomaly detection platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(monitors_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "API Pulse AI Backend"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

