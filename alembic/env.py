from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context

try:  # pragma: no cover - optional production dependency
    from sqlalchemy import pool
    from sqlalchemy.engine import Connection
    from sqlalchemy.ext.asyncio import async_engine_from_config
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "SQLAlchemy async dependencies are required to run Alembic migrations for The Arbiter."
    ) from exc

from arbiter.infra.db.models import Base, SQLALCHEMY_MODELS_AVAILABLE
from arbiter.infra.db.session import DATABASE_URL_DEFAULT

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata if SQLALCHEMY_MODELS_AVAILABLE and hasattr(Base, "metadata") else None
database_url = str(os.getenv("DATABASE_URL", DATABASE_URL_DEFAULT) or DATABASE_URL_DEFAULT).strip()
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async def _run() -> None:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()

    import asyncio

    asyncio.run(_run())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
