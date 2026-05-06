import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from arbiter.infra.structured_logging import get_logger

logger = get_logger(__name__)


def _cors_origins() -> list[str]:
    raw = str(os.getenv("CORS_ORIGINS", "http://localhost:8501") or "").strip()
    if not raw:
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _rate_limit_headers() -> dict[str, str]:
    limit = str(os.getenv("ARBITER_RATE_LIMIT_LIMIT", "0") or "0").strip() or "0"
    reset = str(os.getenv("ARBITER_RATE_LIMIT_RESET", "60") or "60").strip() or "60"
    return {
        "X-RateLimit-Limit": limit,
        "X-RateLimit-Remaining": limit,
        "X-RateLimit-Reset": reset,
    }


def install_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        logger.info(
            "api_request",
            extra={
                "agent_name": "API",
                "latency_ms": latency_ms,
                "method": request.method,
                "path": request.url.path,
            },
        )
        response.headers["X-Process-Time"] = str(round((time.perf_counter() - started), 4))
        for header_name, header_value in _rate_limit_headers().items():
            response.headers[header_name] = header_value
        return response
