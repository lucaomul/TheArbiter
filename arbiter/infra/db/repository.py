import asyncio
import hashlib
from datetime import datetime
from statistics import mean
from typing import Optional
from uuid import uuid4

try:  # pragma: no cover - optional production dependency
    from sqlalchemy import select
except Exception:  # pragma: no cover - graceful fallback when DB deps are absent
    select = None  # type: ignore[assignment]

from arbiter.infra.db.models import Iteration, MemoryEntry, Run, SQLALCHEMY_MODELS_AVAILABLE
from arbiter.infra.db.session import database_enabled, session_scope, sqlalchemy_available
from arbiter.infra.structured_logging import get_logger

logger = get_logger(__name__)
_WARNED_STATES: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key in _WARNED_STATES:
        return
    _WARNED_STATES.add(key)
    logger.warning(message)


def _persistence_available() -> bool:
    available = sqlalchemy_available() and SQLALCHEMY_MODELS_AVAILABLE and select is not None and database_enabled()
    if not available:
        _warn_once(
            "db_unavailable",
            "database_persistence_unavailable",
        )
    return available


def persistence_available() -> bool:
    return _persistence_available()


def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def _json_value(value, default):
    if value is None:
        return default
    return value


def _run_to_dict(run: Run) -> dict:
    return {
        "id": getattr(run, "id", ""),
        "created_at": _iso(getattr(run, "created_at", "")),
        "task_mode": getattr(run, "task_mode", ""),
        "user_input": getattr(run, "user_input", ""),
        "best_score": float(getattr(run, "best_score", 0.0) or 0.0),
        "best_solution": getattr(run, "best_solution", ""),
        "iteration_count": int(getattr(run, "iteration_count", 0) or 0),
        "total_cost_usd": float(getattr(run, "total_cost_usd", 0.0) or 0.0),
        "stop_reason": getattr(run, "stop_reason", ""),
        "ship_readiness": getattr(run, "ship_readiness", ""),
        "verification_status": getattr(run, "verification_status", ""),
        "validity_status": getattr(run, "validity_status", ""),
        "run_metadata": _json_value(getattr(run, "run_metadata", {}), {}),
    }


def _iteration_to_dict(iteration: Iteration) -> dict:
    return {
        "id": getattr(iteration, "id", ""),
        "run_id": getattr(iteration, "run_id", ""),
        "iteration_number": int(getattr(iteration, "iteration_number", 0) or 0),
        "tech_score": int(getattr(iteration, "tech_score", 0) or 0),
        "logic_score": int(getattr(iteration, "logic_score", 0) or 0),
        "avg_score": float(getattr(iteration, "avg_score", 0.0) or 0.0),
        "ship_readiness": getattr(iteration, "ship_readiness", ""),
        "verification_status": getattr(iteration, "verification_status", ""),
        "verification_score": float(getattr(iteration, "verification_score", 0.0) or 0.0),
        "architect_model": getattr(iteration, "architect_model", ""),
        "tech_model": getattr(iteration, "tech_model", ""),
        "logic_model": getattr(iteration, "logic_model", ""),
        "preflight_issues": _json_value(getattr(iteration, "preflight_issues", []), []),
        "tech_issues": _json_value(getattr(iteration, "tech_issues", []), []),
        "logic_issues": _json_value(getattr(iteration, "logic_issues", []), []),
        "janitor_summary": getattr(iteration, "janitor_summary", ""),
        "solution": getattr(iteration, "solution", ""),
        "created_at": _iso(getattr(iteration, "created_at", "")),
    }


async def save_run(run_data: dict) -> str:
    run_id = str(run_data.get("id") or run_data.get("run_id") or uuid4())
    if not _persistence_available():
        return run_id

    record = Run(
        id=run_id,
        task_mode=str(run_data.get("task_mode", "") or ""),
        user_input=str(run_data.get("user_input", "") or ""),
        best_score=float(run_data.get("best_score", 0.0) or 0.0),
        best_solution=str(run_data.get("best_solution", "") or ""),
        iteration_count=int(run_data.get("iteration_count", 0) or 0),
        total_cost_usd=float(run_data.get("total_cost_usd", 0.0) or 0.0),
        stop_reason=str(run_data.get("stop_reason", "") or ""),
        ship_readiness=str(run_data.get("ship_readiness", "UNASSESSED") or "UNASSESSED"),
        verification_status=str(run_data.get("verification_status", "UNVERIFIED") or "UNVERIFIED"),
        validity_status=str(run_data.get("validity_status", "UNKNOWN") or "UNKNOWN"),
        run_metadata=dict(run_data.get("run_metadata", {}) or {}),
    )
    async with session_scope() as session:
        if session is None:
            return run_id
        session.add(record)
    return run_id


async def save_iteration(run_id: str, iter_data: dict) -> None:
    if not _persistence_available():
        return

    record = Iteration(
        id=str(iter_data.get("id") or uuid4()),
        run_id=str(run_id or ""),
        iteration_number=int(iter_data.get("iteration_number", iter_data.get("iter", 0)) or 0),
        tech_score=int(iter_data.get("tech_score", iter_data.get("tech", 0)) or 0),
        logic_score=int(iter_data.get("logic_score", iter_data.get("logic", 0)) or 0),
        avg_score=float(iter_data.get("avg_score", iter_data.get("avg", 0.0)) or 0.0),
        ship_readiness=str(iter_data.get("ship_readiness", "UNASSESSED") or "UNASSESSED"),
        verification_status=str(iter_data.get("verification_status", "UNVERIFIED") or "UNVERIFIED"),
        verification_score=float(iter_data.get("verification_score", 0.0) or 0.0),
        architect_model=str(iter_data.get("architect_model", "") or ""),
        tech_model=str(iter_data.get("tech_model", "") or ""),
        logic_model=str(iter_data.get("logic_model", "") or ""),
        preflight_issues=list(iter_data.get("preflight_issues", []) or []),
        tech_issues=list(iter_data.get("tech_issues", []) or []),
        logic_issues=list(iter_data.get("logic_issues", []) or []),
        janitor_summary=str(iter_data.get("janitor_summary", "") or ""),
        solution=str(iter_data.get("solution", "") or ""),
    )
    async with session_scope() as session:
        if session is None:
            return
        session.add(record)


async def get_run(run_id: str) -> Optional[dict]:
    if not _persistence_available():
        return None
    async with session_scope() as session:
        if session is None:
            return None
        result = await session.execute(select(Run).where(Run.id == str(run_id or "")))
        row = result.scalars().first()
        return _run_to_dict(row) if row else None


async def list_runs(limit: int = 50, task_mode: Optional[str] = None) -> list[dict]:
    if not _persistence_available():
        return []
    async with session_scope() as session:
        if session is None:
            return []
        stmt = select(Run).order_by(Run.created_at.desc()).limit(max(1, int(limit or 50)))
        if task_mode:
            stmt = stmt.where(Run.task_mode == str(task_mode))
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [_run_to_dict(row) for row in rows]


async def get_run_iterations(run_id: str) -> list[dict]:
    if not _persistence_available():
        return []
    async with session_scope() as session:
        if session is None:
            return []
        stmt = (
            select(Iteration)
            .where(Iteration.run_id == str(run_id or ""))
            .order_by(Iteration.iteration_number.asc(), Iteration.created_at.asc())
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [_iteration_to_dict(row) for row in rows]


async def get_benchmark_stats() -> dict:
    runs = await list_runs(limit=500)
    if not runs:
        return {
            "count": 0,
            "avg_score": 0.0,
            "avg_cost": 0.0,
            "ready_rate": 0.0,
            "verified_rate": 0.0,
            "task_modes": {},
        }

    task_modes = {}
    for run in runs:
        mode = run.get("task_mode") or "Unknown"
        task_modes.setdefault(mode, []).append(run)

    ready_count = sum(1 for run in runs if run.get("ship_readiness") == "READY")
    verified_count = sum(1 for run in runs if run.get("verification_status") == "VERIFIED")
    return {
        "count": len(runs),
        "avg_score": round(mean(float(run.get("best_score", 0.0) or 0.0) for run in runs), 2),
        "avg_cost": round(mean(float(run.get("total_cost_usd", 0.0) or 0.0) for run in runs), 6),
        "ready_rate": round((ready_count / len(runs)) * 100, 1),
        "verified_rate": round((verified_count / len(runs)) * 100, 1),
        "task_modes": {
            mode: {
                "count": len(items),
                "avg_score": round(mean(float(item.get("best_score", 0.0) or 0.0) for item in items), 2),
            }
            for mode, items in task_modes.items()
        },
    }


async def save_memory_entry(entry: dict) -> None:
    if not _persistence_available():
        return

    task_text = str(entry.get("task_text", "") or "")
    task_hash = hashlib.sha256(task_text.encode("utf-8")).hexdigest()[:24] if task_text else ""
    record = MemoryEntry(
        id=str(entry.get("id") or entry.get("memory_id") or uuid4()),
        run_id=str(entry.get("run_id", "") or ""),
        task_mode=str(entry.get("task_mode", "") or ""),
        task_hash=task_hash,
        avg_score=float(entry.get("avg_score", 0.0) or 0.0),
        memory_status=str(entry.get("memory_status", "ACCEPT") or "ACCEPT"),
        consensus_score=float(entry.get("consensus_score", 0.0) or 0.0),
        repair_patterns={
            "tech_repair_contract": list(entry.get("tech_repair_contract", []) or []),
            "logic_repair_contract": list(entry.get("logic_repair_contract", []) or []),
            "preflight_issues": list(entry.get("preflight_issues", []) or []),
            "memory_reasons": list(entry.get("memory_reasons", []) or []),
        },
        updated_at=datetime.utcnow(),
    )
    async with session_scope() as session:
        if session is None:
            return
        session.add(record)


def _run_sync(coro, default=None):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    _warn_once(
        "db_sync_bridge_skipped",
        "database_sync_bridge_skipped_inside_active_event_loop",
    )
    return default


def save_run_sync(run_data: dict) -> str:
    run_id = str(run_data.get("id") or run_data.get("run_id") or uuid4())
    return _run_sync(save_run(run_data), default=run_id) or run_id


def save_iteration_sync(run_id: str, iter_data: dict) -> None:
    _run_sync(save_iteration(run_id, iter_data), default=None)


def save_memory_entry_sync(entry: dict) -> None:
    _run_sync(save_memory_entry(entry), default=None)
