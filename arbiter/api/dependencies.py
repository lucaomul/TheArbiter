import os
from typing import AsyncIterator, Optional

from fastapi import Header, HTTPException, status

from arbiter.infra.db.session import get_session


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    configured = str(os.getenv("API_KEY", "") or "").strip()
    if not configured:
        return
    if str(x_api_key or "").strip() != configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )


async def get_db_session() -> AsyncIterator:
    async for session in get_session():
        yield session
