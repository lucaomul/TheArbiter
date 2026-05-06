from fastapi import APIRouter, Depends

from arbiter.api.dependencies import require_api_key
from arbiter.api.v1.schemas.health import HealthResponse
from arbiter.infra.db.session import database_enabled, sqlalchemy_available

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, dependencies=[Depends(require_api_key)])
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="The Arbiter API",
        database_enabled=database_enabled(),
        detail="SQLAlchemy available" if sqlalchemy_available() else "DB dependencies not installed.",
    )


@router.get("/ready", response_model=HealthResponse, dependencies=[Depends(require_api_key)])
async def ready() -> HealthResponse:
    return HealthResponse(
        status="ready",
        service="The Arbiter API",
        database_enabled=database_enabled(),
        detail="Service is ready to accept runs.",
    )
