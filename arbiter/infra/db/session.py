import asyncio
import importlib.util
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

try:  # pragma: no cover - optional production dependency
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
except Exception:  # pragma: no cover - graceful fallback when DB deps are absent
    AsyncEngine = Any  # type: ignore[assignment]
    AsyncSession = Any  # type: ignore[assignment]
    async_sessionmaker = None  # type: ignore[assignment]
    create_async_engine = None  # type: ignore[assignment]

from arbiter.infra.structured_logging import get_logger
from arbiter.infra.db.models import Base, SQLALCHEMY_MODELS_AVAILABLE


DATABASE_URL_DEFAULT = "sqlite+aiosqlite:///arbiter.db"

_ENGINE: Optional[AsyncEngine] = None
_SESSION_FACTORY = None
_ENGINE_INIT_FAILED = False
_SCHEMA_INIT_FAILED = False
_SCHEMA_READY = False
_SCHEMA_LOCK: Optional[asyncio.Lock] = None
logger = get_logger(__name__)


def sqlalchemy_available() -> bool:
    return create_async_engine is not None and async_sessionmaker is not None


def get_database_url() -> str:
    return str(os.getenv("DATABASE_URL", DATABASE_URL_DEFAULT) or DATABASE_URL_DEFAULT).strip()


def _required_driver_module(database_url: str) -> str:
    url = str(database_url or "").lower()
    if "+aiosqlite" in url:
        return "aiosqlite"
    if "+asyncpg" in url:
        return "asyncpg"
    if "+aiomysql" in url:
        return "aiomysql"
    if "+asyncmy" in url:
        return "asyncmy"
    return ""


def _runtime_support_modules(database_url: str) -> list[str]:
    modules = []
    driver_module = _required_driver_module(database_url)
    if driver_module:
        modules.append(driver_module)
    if sqlalchemy_available():
        modules.append("greenlet")
    return modules


def driver_available(database_url: str = "") -> bool:
    modules = _runtime_support_modules(database_url or get_database_url())
    return all(importlib.util.find_spec(module_name) is not None for module_name in modules)


def database_enabled() -> bool:
    return (
        sqlalchemy_available()
        and not _ENGINE_INIT_FAILED
        and not _SCHEMA_INIT_FAILED
        and bool(get_database_url())
        and driver_available(get_database_url())
    )


def get_engine() -> Optional[AsyncEngine]:
    global _ENGINE, _ENGINE_INIT_FAILED
    if not database_enabled():
        return None
    if _ENGINE is None:
        try:
            _ENGINE = create_async_engine(
                get_database_url(),
                future=True,
                echo=False,
                pool_pre_ping=True,
            )
        except Exception as exc:
            _ENGINE_INIT_FAILED = True
            logger.warning(
                "database_engine_unavailable",
                extra={
                    "agent_name": "DB",
                    "reason": str(exc),
                },
            )
            return None
    return _ENGINE


def get_session_factory():
    global _SESSION_FACTORY
    if not database_enabled():
        return None
    if _SESSION_FACTORY is None:
        engine = get_engine()
        if engine is None:
            return None
        _SESSION_FACTORY = async_sessionmaker(engine, expire_on_commit=False)
    return _SESSION_FACTORY


async def ensure_schema_ready() -> bool:
    global _SCHEMA_READY, _SCHEMA_INIT_FAILED, _SCHEMA_LOCK
    if _SCHEMA_READY:
        return True
    if not database_enabled() or not SQLALCHEMY_MODELS_AVAILABLE:
        return False

    engine = get_engine()
    if engine is None:
        return False

    if _SCHEMA_LOCK is None:
        _SCHEMA_LOCK = asyncio.Lock()

    async with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return True
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _SCHEMA_READY = True
            return True
        except Exception as exc:
            _SCHEMA_INIT_FAILED = True
            logger.warning(
                "database_schema_unavailable",
                extra={
                    "agent_name": "DB",
                    "reason": str(exc),
                },
            )
            return False


@asynccontextmanager
async def session_scope() -> AsyncIterator[Optional[AsyncSession]]:
    if not await ensure_schema_ready():
        yield None
        return

    factory = get_session_factory()
    if factory is None:
        yield None
        return

    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session() -> AsyncIterator[Optional[AsyncSession]]:
    async with session_scope() as session:
        yield session
