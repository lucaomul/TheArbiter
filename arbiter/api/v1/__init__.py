from fastapi import APIRouter

from arbiter.api.v1.routers.health import router as health_router
from arbiter.api.v1.routers.models import router as models_router
from arbiter.api.v1.routers.runs import router as runs_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(models_router)
router.include_router(runs_router)

__all__ = ["router"]
