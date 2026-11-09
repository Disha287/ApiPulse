import asyncio
from datetime import datetime, timezone
import logging
from typing import List
import uuid
import httpx
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.models import Monitor
from app.services.prober import execute_probe

logger = logging.getLogger("apipulse.scheduler")


async def run_scheduler(stop_event: asyncio.Event) -> None:
    """
    Non-blocking background scheduler that queries active monitors and concurrently
    triggers health probes using an asyncio semaphore when their interval has elapsed.
    """
    semaphore = asyncio.Semaphore(50)
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)

    logger.info("Starting background monitor scheduler...")

    async with httpx.AsyncClient(limits=limits) as client:
        while not stop_event.is_set():
            try:
                due_monitor_ids: List[uuid.UUID] = []
                now = datetime.now(timezone.utc)

                async with AsyncSessionLocal() as session:
                    stmt = select(Monitor).where(Monitor.is_active == True)
                    result = await session.execute(stmt)
                    monitors = result.scalars().all()

                    for m in monitors:
                        if m.last_checked_at is None:
                            due_monitor_ids.append(m.id)
                        else:
                            elapsed = (now - m.last_checked_at).total_seconds()
                            if elapsed >= m.interval_seconds:
                                due_monitor_ids.append(m.id)

                if due_monitor_ids:
                    logger.info(
                        f"Dispatching probes for {len(due_monitor_ids)} due monitor(s)..."
                    )

                    async def sem_probe(mid: uuid.UUID):
                        async with semaphore:
                            try:
                                return await execute_probe(mid, client)
                            except Exception as e:
                                logger.error(f"Error probing monitor {mid}: {e}")
                                return None

                    await asyncio.gather(
                        *(sem_probe(mid) for mid in due_monitor_ids),
                        return_exceptions=True,
                    )

            except Exception as e:
                logger.error(f"Scheduler tick error: {e}")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

    logger.info("Background monitor scheduler stopped cleanly.")

