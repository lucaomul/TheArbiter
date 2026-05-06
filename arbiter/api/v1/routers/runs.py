import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from arbiter.api.dependencies import require_api_key
from arbiter.api.v1.schemas.run import IterationSchema, RunRequest, RunResponse
from arbiter.core.orchestrator import ArbiterOrchestrator
from arbiter.infra.db import (
    get_run as db_get_run,
    get_run_iterations as db_get_run_iterations,
    persistence_available,
    save_run,
)
from arbiter.infra.structured_logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["runs"])


def _status_from_result(result) -> str:
    if result.debug_info.get("needs_clarification"):
        return "needs_clarification"
    if result.iteration_history:
        latest = result.iteration_history[-1]
        if latest.get("ship_readiness") == "BLOCKED":
            return "blocked"
    return "completed"


def _iterations_from_result(result) -> list[IterationSchema]:
    items = []
    for record in result.iteration_history:
        items.append(
            IterationSchema(
                iteration=int(record.get("iter", 0) or 0),
                tech_score=int(record.get("tech", 0) or 0),
                logic_score=int(record.get("logic", 0) or 0),
                avg_score=float(record.get("avg", 0.0) or 0.0),
                ship_readiness=str(record.get("ship_readiness", "UNASSESSED") or "UNASSESSED"),
                verification_status=str(record.get("verification_status", "UNVERIFIED") or "UNVERIFIED"),
            )
        )
    return items


def _build_response(result, fallback_run_id: str) -> RunResponse:
    run_id = str(result.debug_info.get("run_id", "") or fallback_run_id)
    return RunResponse(
        run_id=run_id,
        status=_status_from_result(result),
        best_score=float(result.best_score or 0.0),
        best_solution=str(result.best_solution or ""),
        iteration_count=int(result.iteration_count or 0),
        iterations=_iterations_from_result(result),
        total_cost_usd=float((result.costs or {}).get("Total", 0.0) or 0.0),
        needs_clarification=bool(result.debug_info.get("needs_clarification", False)),
        clarification_questions=list(result.debug_info.get("questions", []) or []),
    )


async def _persist_clarification_run(response: RunResponse, payload: RunRequest) -> None:
    if not persistence_available():
        return
    await save_run(
        {
            "id": response.run_id,
            "task_mode": payload.task_mode,
            "user_input": payload.user_input,
            "best_score": response.best_score,
            "best_solution": response.best_solution,
            "iteration_count": response.iteration_count,
            "total_cost_usd": response.total_cost_usd,
            "stop_reason": "needs_clarification",
            "ship_readiness": "UNASSESSED",
            "verification_status": "UNVERIFIED",
            "validity_status": "CLARIFICATION REQUIRED",
            "run_metadata": {
                "clarification_questions": list(response.clarification_questions or []),
                "clarification": payload.clarification,
                "manual_override": payload.manual_override,
                "stable_mode": payload.stable_mode,
            },
        }
    )


@router.post("/runs", response_model=RunResponse, dependencies=[Depends(require_api_key)])
async def create_run(payload: RunRequest) -> RunResponse:
    run_id = f"api-{uuid4().hex[:12]}"
    logger.info(
        "api_run_started",
        extra={
            "run_id": run_id,
            "agent_name": "API",
            "task_mode": payload.task_mode,
        },
    )
    try:
        orchestrator = ArbiterOrchestrator(
            task_mode=payload.task_mode,
            auto_mode=True,
            target_score=payload.target_score,
            max_iterations=payload.max_iterations,
            stable_mode=payload.stable_mode,
        )
        result = await asyncio.to_thread(
            orchestrator.run,
            payload.user_input,
            clarification=payload.clarification,
            manual_override=payload.manual_override,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "api_run_failed",
            extra={"run_id": run_id, "agent_name": "API"},
            exc_info=exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The Arbiter run failed before completion.",
        ) from exc

    response = _build_response(result, run_id)
    if response.needs_clarification:
        try:
            await _persist_clarification_run(response, payload)
        except Exception as exc:
            logger.warning(
                "api_clarification_persist_failed",
                extra={"run_id": response.run_id, "agent_name": "API"},
                exc_info=exc,
            )
    logger.info(
        "api_run_completed",
        extra={
            "run_id": response.run_id,
            "agent_name": "API",
            "score": response.best_score,
            "status": response.status,
        },
    )
    return response


@router.get("/runs/{run_id}", response_model=RunResponse, dependencies=[Depends(require_api_key)])
async def get_run(run_id: str) -> RunResponse:
    if not persistence_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Run retrieval requires database persistence to be enabled and installed.",
        )

    run = await db_get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run `{run_id}` was not found.",
        )

    iterations_raw = await db_get_run_iterations(run_id)
    iterations = [
        IterationSchema(
            iteration=int(item.get("iteration_number", 0) or 0),
            tech_score=int(item.get("tech_score", 0) or 0),
            logic_score=int(item.get("logic_score", 0) or 0),
            avg_score=float(item.get("avg_score", 0.0) or 0.0),
            ship_readiness=str(item.get("ship_readiness", "UNASSESSED") or "UNASSESSED"),
            verification_status=str(item.get("verification_status", "UNVERIFIED") or "UNVERIFIED"),
        )
        for item in iterations_raw
    ]

    metadata = dict(run.get("run_metadata", {}) or {})
    questions = list(metadata.get("clarification_questions", []) or [])
    status_value = "needs_clarification" if questions else "completed"
    if run.get("ship_readiness") == "BLOCKED":
        status_value = "blocked"

    return RunResponse(
        run_id=str(run.get("id", "") or run_id),
        status=status_value,
        best_score=float(run.get("best_score", 0.0) or 0.0),
        best_solution=str(run.get("best_solution", "") or ""),
        iteration_count=int(run.get("iteration_count", 0) or 0),
        iterations=iterations,
        total_cost_usd=float(run.get("total_cost_usd", 0.0) or 0.0),
        needs_clarification=bool(questions),
        clarification_questions=questions,
    )
