"""FastAPI dependency injection providers.

Centralizes reusable dependencies so route modules can declare them via
``Depends()`` without importing database internals directly.
"""

from typing import AsyncGenerator

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session scoped to a single request.

    Usage in route handlers::

        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...

    The session is committed automatically if no exception occurs.
    On error it is rolled back. In all cases the session is closed.
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception as exc:
            await session.rollback()
            logger.error("Database session rolled back due to error: {}", exc)
            raise
        finally:
            await session.close()
