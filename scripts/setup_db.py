"""Create database tables from SQLAlchemy models.

Runs the async SQLAlchemy ``create_all`` method against the configured SQLite
database (``clinic.db`` by default).  Safe to run repeatedly -- existing tables
are silently skipped thanks to ``IF NOT EXISTS`` semantics.

Usage::

    python scripts/setup_db.py
"""

import asyncio
import sys
import os

# Add project root to path so ``api.*`` imports resolve correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from api.database import engine, Base
from api.models import Doctor, Patient, TimeSlot, Appointment, CallLog  # noqa: F401


async def setup_database() -> None:
    """Create all database tables defined by the ORM models.

    Opens a transactional connection, synchronously runs ``Base.metadata.create_all``,
    then disposes the engine to release the connection pool.
    """
    logger.info("Creating database tables...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as exc:
        logger.error("Failed to create database tables: {}", exc)
        raise
    finally:
        await engine.dispose()
        logger.debug("Database engine disposed")


if __name__ == "__main__":
    asyncio.run(setup_database())
