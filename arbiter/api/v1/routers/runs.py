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
    team_meta = dict(result.debug_info.get("software_team", {}) or {})
    evidence_meta = dict(result.debug_info.get("evidence", {}) or {})
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
        team_mode_used=bool(team_meta.get("use_team")) if team_meta else None,
        team_recommended=bool(team_meta.get("recommended")) if team_meta else None,
        team_approval_missing=bool(team_meta.get("approval_missing")) if team_meta else None,
        team_profile=str(team_meta.get("selected_profile", "") or "") or None,
        team_profile_label=str(team_meta.get("selected_profile_label", "") or "") or None,
        team_roles=list(team_meta.get("roles", []) or []),
        detected_domains=list(team_meta.get("detected_domains", []) or []),
        detected_technologies=list(team_meta.get("detected_technologies", []) or []),
        team_signal_reasons=list(team_meta.get("signal_reasons", []) or []),
        team_complexity_level=str(team_meta.get("complexity_level", "") or "") or None,
        team_estimated_cost_multiplier=float(team_meta.get("estimated_cost_multiplier", 0.0) or 0.0) or None,
        team_estimated_latency_multiplier=float(team_meta.get("estimated_latency_multiplier", 0.0) or 0.0) or None,
        architecture_summary=str(team_meta.get("architecture_summary", "") or "") or None,
        evidence_source_count=int(evidence_meta.get("source_count", 0) or 0) if evidence_meta else None,
        evidence_source_names=list(evidence_meta.get("source_names", []) or []),
        evidence_warning_count=int(evidence_meta.get("warning_count", 0) or 0) if evidence_meta else None,
        evidence_rag_used=bool(evidence_meta.get("rag_used")) if evidence_meta else None,
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
                "team_mode_used": response.team_mode_used,
                "team_recommended": response.team_recommended,
                "team_approval_missing": response.team_approval_missing,
                "team_profile": response.team_profile,
                "team_profile_label": response.team_profile_label,
                "team_roles": list(response.team_roles or []),
                "detected_domains": list(response.detected_domains or []),
                "detected_technologies": list(response.detected_technologies or []),
                "team_signal_reasons": list(response.team_signal_reasons or []),
                "team_complexity_level": response.team_complexity_level,
                "team_estimated_cost_multiplier": response.team_estimated_cost_multiplier,
                "team_estimated_latency_multiplier": response.team_estimated_latency_multiplier,
                "architecture_summary": response.architecture_summary or "",
                "evidence_source_count": response.evidence_source_count,
                "evidence_source_names": list(response.evidence_source_names or []),
                "evidence_warning_count": response.evidence_warning_count,
                "evidence_rag_used": response.evidence_rag_used,
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
            allow_complex_software_team=payload.allow_complex_software_team,
            software_team_profile=payload.software_team_profile,
            supporting_materials=[item.model_dump() for item in payload.supporting_materials],
            supporting_urls=list(payload.supporting_urls or []),
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
        team_mode_used=metadata.get("team_mode_used"),
        team_recommended=metadata.get("team_recommended"),
        team_approval_missing=metadata.get("team_approval_missing"),
        team_profile=metadata.get("team_profile"),
        team_profile_label=metadata.get("team_profile_label"),
        team_roles=list(metadata.get("team_roles", []) or []),
        detected_domains=list(metadata.get("detected_domains", []) or []),
        detected_technologies=list(metadata.get("detected_technologies", []) or []),
        team_signal_reasons=list(metadata.get("team_signal_reasons", []) or []),
        team_complexity_level=str(metadata.get("team_complexity_level", "") or "") or None,
        team_estimated_cost_multiplier=metadata.get("team_estimated_cost_multiplier"),
        team_estimated_latency_multiplier=metadata.get("team_estimated_latency_multiplier"),
        architecture_summary=str(metadata.get("architecture_summary", "") or "") or None,
        evidence_source_count=metadata.get("evidence_source_count"),
        evidence_source_names=list(metadata.get("evidence_source_names", []) or []),
        evidence_warning_count=metadata.get("evidence_warning_count"),
        evidence_rag_used=metadata.get("evidence_rag_used"),
    )
