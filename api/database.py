"""Async SQLite database engine and session management using aiosqlite.

Provides the core database infrastructure for the Sunrise Health Clinic API:
- Async SQLAlchemy engine backed by aiosqlite
- Session factory for dependency injection
- Table initialization utility
"""

import os
from typing import AsyncGenerator

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./clinic.db")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base class for all SQLAlchemy ORM models."""

    pass


async def init_db() -> None:
    """Create all database tables defined by ORM models.

    This imports all models to ensure they are registered with the Base
    metadata before issuing CREATE TABLE statements. Safe to call multiple
    times -- SQLAlchemy's create_all uses IF NOT EXISTS semantics.
    """
    # Import models so they register with Base.metadata before create_all
    import api.models  # noqa: F401

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully (url={})", DATABASE_URL)
    except Exception as exc:
        logger.error("Failed to initialize database: {}", exc)
        raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for FastAPI dependency injection.

    The session is automatically closed when the request completes, even
    if an exception occurs during request processing.
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception as exc:
            await session.rollback()
            logger.error("Database session error, rolled back: {}", exc)
            raise
        finally:
            await session.close()
