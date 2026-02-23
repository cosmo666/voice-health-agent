"""Alembic async migration environment for SQLite + aiosqlite.

Configures Alembic to work with the project's async SQLAlchemy engine.
Supports both offline (SQL script generation) and online (live migration)
modes.  Online mode runs migrations inside an asyncio event loop using
``async_engine_from_config``.

The ``target_metadata`` is pulled from ``api.database.Base.metadata`` so
Alembic's ``--autogenerate`` can diff the current DB state against the
ORM model definitions.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import the project's declarative base and all models so that
# Base.metadata contains every table for autogenerate support.
from api.database import Base, DATABASE_URL
from api.models import Doctor, Patient, TimeSlot, Appointment, CallLog  # noqa: F401

# Alembic Config object -- provides access to alembic.ini values.
config = context.config

# Override the sqlalchemy.url from alembic.ini with the application's
# canonical DATABASE_URL so there is a single source of truth.
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Set up Python logging from the alembic.ini [loggers] section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL statements without connecting to the database.  Useful for
    reviewing migration scripts before applying them, or for environments
    where a live DB connection is not available.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Execute migrations against an active database connection.

    This is the synchronous callback invoked inside ``connection.run_sync()``
    by the async migration runner.

    Args:
        connection: A synchronous SQLAlchemy connection object.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations inside the event loop.

    Uses ``NullPool`` to avoid connection-pool issues during one-shot
    migration execution.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live database connection.

    Delegates to the async migration runner which handles the event loop.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
