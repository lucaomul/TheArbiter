from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from arbiter.api.middleware import install_middleware
from arbiter.api.v1 import router as v1_router
from arbiter.infra.structured_logging import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="The Arbiter API",
        version="0.1.0",
        description="Service layer for The Arbiter multi-agent orchestration engine.",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    install_middleware(app)
    app.include_router(v1_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(
            "api_unhandled_exception",
            extra={
                "agent_name": "API",
                "path": request.url.path,
                "method": request.method,
            },
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Unhandled server error.",
                "path": request.url.path,
            },
        )

    @app.on_event("startup")
    async def announce_startup() -> None:
        logger.info("api_ready", extra={"agent_name": "API"})

    return app


app = create_app()
