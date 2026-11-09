import asyncio
import sys
from pathlib import Path

# Ensure backend is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text
from app.core.database import Base, engine
import app.models.models  # noqa: F401 - Register models with Base metadata


async def init_db() -> None:
    print("Connecting to database and creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("ALTER TABLE monitors ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ;")
        )
        await conn.execute(
            text("ALTER TABLE monitors ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0;")
        )
    print("Database tables created and updated successfully!")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())

