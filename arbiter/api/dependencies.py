import os
import time
from typing import AsyncIterator, Optional

from fastapi import Header, HTTPException, status

from arbiter.infra.db.session import get_session


PRODUCTION_ENVS = {"prod", "production"}


def arbiter_env() -> str:
    return str(os.getenv("ARBITER_ENV", "development") or "development").strip().lower()


def is_production_env() -> bool:
    return arbiter_env() in PRODUCTION_ENVS


def configured_api_key() -> str:
    return str(os.getenv("API_KEY", "") or "").strip()


def configured_api_key_expired() -> bool:
    raw = str(os.getenv("API_KEY_EXPIRES_AT", "") or "").strip()
    if not raw:
        return False
    try:
        return float(raw) <= time.time()
    except ValueError:
        return True


def _resolve_request_api_key(x_api_key: Optional[str], authorization: Optional[str]) -> str:
    header_key = str(x_api_key or "").strip()
    if header_key:
        return header_key

    auth_value = str(authorization or "").strip()
    if not auth_value:
        return ""
    parts = auth_value.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed Authorization header.",
        )
    return parts[1].strip()


async def require_api_key(
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> None:
    configured = configured_api_key()
    if not configured:
        if is_production_env():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key authentication is required in production.",
            )
        return

    if configured_api_key_expired():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Configured API key is expired or invalid.",
        )

    supplied = _resolve_request_api_key(x_api_key, authorization)
    if supplied != configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )


async def get_db_session() -> AsyncIterator:
    async for session in get_session():
        yield session
