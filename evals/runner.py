import argparse
import csv
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Iterable, Optional


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_STRATEGY = "arbiter_full_loop"
COMPARE_STRATEGIES = ("baseline_single_model", "arbiter_full_loop")
RESULT_FIELDS = [
    "fixture_id",
    "task_mode",
    "source_file",
    "source_line",
    "strategy",
    "score",
    "verification_status",
    "ship_readiness",
    "iteration_count",
    "total_cost",
    "pass",
    "dry_run",
    "min_score",
    "notes",
    "tags",
    "expected_team_mode",
    "team_mode_recommended",
    "team_mode_used",
    "team_approval_missing",
    "complexity_score",
    "complexity_level",
    "detected_domains",
    "detected_technologies",
    "team_roles",
    "signal_reasons",
    "output_excerpt",
]


def load_fixtures(
    fixtures_root: Optional[Path] = None,
    *,
    task_mode: str = "",
    limit: Optional[int] = None,
) -> list[dict]:
    root = Path(fixtures_root or FIXTURES_DIR)
    fixtures = []
    for path in sorted(root.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                fixture = {
                    "id": str(payload["id"]).strip(),
                    "task_mode": str(payload["task_mode"]).strip(),
                    "task": str(payload["task"]).strip(),
                    "expected_keywords": [str(item).strip() for item in payload.get("expected_keywords", []) if str(item).strip()],
                    "min_score": float(payload.get("min_score", 7.0)),
                    "notes": str(payload.get("notes", "")).strip(),
                    "tags": [str(item).strip() for item in payload.get("tags", []) if str(item).strip()],
                    "expected_team_mode": (
                        None if payload.get("expected_team_mode") is None else bool(payload.get("expected_team_mode"))
                    ),
                    "source_file": path.name,
                    "source_line": line_number,
                }
                fixtures.append(fixture)
    if task_mode:
        fixtures = [item for item in fixtures if item["task_mode"] == task_mode]
    if limit is not None:
        fixtures = fixtures[: max(0, int(limit))]
    return fixtures


def inspect_team_routing(fixture: dict) -> dict:
    if str(fixture.get("task_mode", "")).strip() != "Software & IT":
        return {
            "team_mode_recommended": False,
            "team_mode_used": False,
            "team_approval_missing": False,
            "complexity_score": 0,
            "complexity_level": "standard",
            "detected_domains": [],
            "detected_technologies": [],
            "team_roles": [],
            "signal_reasons": [],
        }

    from arbiter.core.team_router import TeamRouter

    decision = TeamRouter().route(str(fixture.get("task_mode", "")), str(fixture.get("task", "")))
    expected_team_mode = fixture.get("expected_team_mode")
    team_used = bool(decision.use_team)
    if expected_team_mode is False:
        team_used = False
    return {
        "team_mode_recommended": bool(decision.use_team),
        "team_mode_used": team_used,
        "team_approval_missing": bool(decision.use_team and not team_used),
        "complexity_score": int(decision.complexity_score or 0),
        "complexity_level": str(decision.complexity_level or "standard"),
        "detected_domains": list(decision.detected_domains or []),
        "detected_technologies": list(decision.detected_technologies or []),
        "team_roles": list(decision.suggested_roles or []),
        "signal_reasons": list(decision.signal_reasons or []),
    }


def dry_run_record(fixture: dict, strategy: str) -> dict:
    seed = int(hashlib.sha256(f"{fixture['id']}::{strategy}".encode("utf-8")).hexdigest()[:8], 16)
    min_score = float(fixture.get("min_score", 7.0) or 7.0)
    team_meta = inspect_team_routing(fixture)
    variance = ((seed % 5) - 2) * 0.12
    if strategy == "arbiter_full_loop":
        score = min(9.8, max(1.0, round(min_score + 0.45 + variance, 2)))
        iteration_count = 2 + (seed % 2)
        total_cost = round(0.001 + ((seed % 7) * 0.00013), 6)
    else:
        score = min(9.2, max(1.0, round(min_score - 0.55 + variance, 2)))
        iteration_count = 1
        total_cost = round(0.0003 + ((seed % 5) * 0.00007), 6)

    if score >= 8.2:
        verification_status = "VERIFIED"
        ship_readiness = "READY"
    elif score >= 6.6:
        verification_status = "CAUTION"
        ship_readiness = "CLOSE"
    else:
        verification_status = "FAILED"
        ship_readiness = "BLOCKED"

    keywords = fixture.get("expected_keywords", [])[:4]
    excerpt = (
        f"{'Arbiter' if strategy == 'arbiter_full_loop' else 'Baseline'} dry-run output for "
        f"{fixture['id']}: " + ", ".join(keywords)
    ).strip()
    return {
        "fixture_id": fixture["id"],
        "task_mode": fixture["task_mode"],
        "source_file": fixture.get("source_file", ""),
        "source_line": int(fixture.get("source_line", 0) or 0),
        "strategy": strategy,
        "score": score,
        "verification_status": verification_status,
        "ship_readiness": ship_readiness,
        "iteration_count": iteration_count,
        "total_cost": total_cost,
        "pass": score >= min_score,
        "dry_run": True,
        "min_score": min_score,
        "notes": fixture.get("notes", ""),
        "tags": list(fixture.get("tags", []) or []),
        "expected_team_mode": fixture.get("expected_team_mode"),
        "team_mode_recommended": bool(team_meta.get("team_mode_recommended", False)),
        "team_mode_used": bool(team_meta.get("team_mode_used", False)) if strategy == "arbiter_full_loop" else False,
        "team_approval_missing": bool(team_meta.get("team_approval_missing", False)) if strategy == "arbiter_full_loop" else False,
        "complexity_score": int(team_meta.get("complexity_score", 0) or 0),
        "complexity_level": str(team_meta.get("complexity_level", "standard") or "standard"),
        "detected_domains": list(team_meta.get("detected_domains", []) or []),
        "detected_technologies": list(team_meta.get("detected_technologies", []) or []),
        "team_roles": list(team_meta.get("team_roles", []) or []),
        "signal_reasons": list(team_meta.get("signal_reasons", []) or []),
        "output_excerpt": excerpt[:240],
    }


def _ship_readiness_from_verification(status: str) -> str:
    normalized = str(status or "UNVERIFIED").upper()
    if normalized in {"FAILED", "BLOCKED"}:
        return "BLOCKED"
    if normalized == "CAUTION":
        return "CLOSE"
    if normalized == "VERIFIED":
        return "READY"
    return "UNASSESSED"


def run_baseline_fixture(fixture: dict) -> dict:
    from arbiter.agents.base_agent import BaseAgent
    from arbiter.core.agent_runner import AgentRunner
    from arbiter.core.final_verifier import FinalVerifier
    from arbiter.prompts.registry import PromptRegistry

    registry = PromptRegistry(task_mode=fixture["task_mode"])
    runner = AgentRunner(registry)
    payload = registry.build_task_payload(fixture["task"])
    solution, model = runner.run_architect(
        payload,
        history="",
        context={"stable_mode": True, "iteration": 1},
    )
    provider_error = bool(BaseAgent.error_payload(solution))
    verification = FinalVerifier().verify(
        task_mode=fixture["task_mode"],
        task_text=payload,
        solution=solution,
        provider_error=provider_error,
    )
    team_meta = inspect_team_routing(fixture)
    score = round(float(verification.score or 0.0) * 10.0, 2)
    return {
        "fixture_id": fixture["id"],
        "task_mode": fixture["task_mode"],
        "source_file": fixture.get("source_file", ""),
        "source_line": int(fixture.get("source_line", 0) or 0),
        "strategy": "baseline_single_model",
        "score": score,
        "verification_status": verification.status,
        "ship_readiness": _ship_readiness_from_verification(verification.status),
        "iteration_count": 1,
        "total_cost": round(float(runner.latest_call_cost("Architect", model) or 0.0), 8),
        "pass": score >= float(fixture.get("min_score", 7.0) or 7.0),
        "dry_run": False,
        "min_score": float(fixture.get("min_score", 7.0) or 7.0),
        "notes": fixture.get("notes", ""),
        "tags": list(fixture.get("tags", []) or []),
        "expected_team_mode": fixture.get("expected_team_mode"),
        "team_mode_recommended": bool(team_meta.get("team_mode_recommended", False)),
        "team_mode_used": False,
        "team_approval_missing": False,
        "complexity_score": int(team_meta.get("complexity_score", 0) or 0),
        "complexity_level": str(team_meta.get("complexity_level", "standard") or "standard"),
        "detected_domains": list(team_meta.get("detected_domains", []) or []),
        "detected_technologies": list(team_meta.get("detected_technologies", []) or []),
        "team_roles": list(team_meta.get("team_roles", []) or []),
        "signal_reasons": list(team_meta.get("signal_reasons", []) or []),
        "output_excerpt": str(solution or "").strip().replace("\n", " ")[:240],
    }


def run_arbiter_fixture(fixture: dict) -> dict:
    from arbiter.core.orchestrator import ArbiterOrchestrator

    expected_team_mode = fixture.get("expected_team_mode")
    allow_complex_software_team = bool(expected_team_mode) if expected_team_mode is not None else None
    orchestrator = ArbiterOrchestrator(
        task_mode=fixture["task_mode"],
        auto_mode=True,
        target_score=max(8.0, float(fixture.get("min_score", 7.0) or 7.0)),
        max_iterations=5,
        stable_mode=True,
        benchmark_mode=True,
        benchmark_strategy="arbiter_full_loop",
        benchmark_pack="evals",
        benchmark_case_id=fixture["id"],
        benchmark_case_title=fixture["id"],
    )
    result = orchestrator.run(
        user_input=fixture["task"],
        allow_complex_software_team=allow_complex_software_team,
    )
    debug = dict(result.debug_info or {})
    team_meta = dict(debug.get("software_team", {}) or {})
    if not team_meta:
        team_meta = inspect_team_routing(fixture)
    if debug.get("needs_clarification"):
        return {
            "fixture_id": fixture["id"],
            "task_mode": fixture["task_mode"],
            "source_file": fixture.get("source_file", ""),
            "source_line": int(fixture.get("source_line", 0) or 0),
            "strategy": "arbiter_full_loop",
            "score": 0.0,
            "verification_status": "BLOCKED",
            "ship_readiness": "BLOCKED",
            "iteration_count": 0,
            "total_cost": round(float(result.costs.get("Total", 0.0) or 0.0), 8),
            "pass": False,
            "dry_run": False,
            "min_score": float(fixture.get("min_score", 7.0) or 7.0),
            "notes": fixture.get("notes", ""),
            "tags": list(fixture.get("tags", []) or []),
            "expected_team_mode": fixture.get("expected_team_mode"),
            "team_mode_recommended": bool(team_meta.get("team_mode_recommended", team_meta.get("recommended", False))),
            "team_mode_used": bool(team_meta.get("team_mode_used", team_meta.get("use_team", False))),
            "team_approval_missing": bool(team_meta.get("team_approval_missing", team_meta.get("approval_missing", False))),
            "complexity_score": int(team_meta.get("complexity_score", 0) or 0),
            "complexity_level": str(team_meta.get("complexity_level", "standard") or "standard"),
            "detected_domains": list(team_meta.get("detected_domains", []) or []),
            "detected_technologies": list(team_meta.get("detected_technologies", []) or []),
            "team_roles": list(team_meta.get("team_roles", team_meta.get("roles", [])) or []),
            "signal_reasons": list(team_meta.get("signal_reasons", []) or []),
            "output_excerpt": "Clarification required before execution.",
        }

    latest = result.iteration_history[-1] if result.iteration_history else {}
    score = round(float(result.best_score or 0.0), 2)
    return {
        "fixture_id": fixture["id"],
        "task_mode": fixture["task_mode"],
        "source_file": fixture.get("source_file", ""),
        "source_line": int(fixture.get("source_line", 0) or 0),
        "strategy": "arbiter_full_loop",
        "score": score,
        "verification_status": str(latest.get("verification_status", "UNVERIFIED")).upper(),
        "ship_readiness": str(latest.get("ship_readiness", "UNASSESSED")).upper(),
        "iteration_count": int(result.iteration_count or 0),
        "total_cost": round(float(result.costs.get("Total", 0.0) or 0.0), 8),
        "pass": score >= float(fixture.get("min_score", 7.0) or 7.0),
        "dry_run": False,
        "min_score": float(fixture.get("min_score", 7.0) or 7.0),
        "notes": fixture.get("notes", ""),
        "tags": list(fixture.get("tags", []) or []),
        "expected_team_mode": fixture.get("expected_team_mode"),
        "team_mode_recommended": bool(team_meta.get("team_mode_recommended", team_meta.get("recommended", False))),
        "team_mode_used": bool(team_meta.get("team_mode_used", team_meta.get("use_team", False))),
        "team_approval_missing": bool(team_meta.get("team_approval_missing", team_meta.get("approval_missing", False))),
        "complexity_score": int(team_meta.get("complexity_score", 0) or 0),
        "complexity_level": str(team_meta.get("complexity_level", "standard") or "standard"),
        "detected_domains": list(team_meta.get("detected_domains", []) or []),
        "detected_technologies": list(team_meta.get("detected_technologies", []) or []),
        "team_roles": list(team_meta.get("team_roles", team_meta.get("roles", [])) or []),
        "signal_reasons": list(team_meta.get("signal_reasons", []) or []),
        "output_excerpt": str(result.best_solution or "").strip().replace("\n", " ")[:240],
    }


def _run_one_record(fixture: dict, *, dry_run: bool, strategy: str) -> dict:
    if dry_run:
        return dry_run_record(fixture, strategy)
    if strategy == "baseline_single_model":
        return run_baseline_fixture(fixture)
    return run_arbiter_fixture(fixture)


def run_records(
    fixtures: Iterable[dict],
    *,
    dry_run: bool,
    strategy: str,
    compare: bool,
    max_total_cost: float = 0.0,
) -> list[dict]:
    strategies = list(COMPARE_STRATEGIES if compare else (strategy,))
    records = []
    running_cost = 0.0
    for fixture in fixtures:
        for selected_strategy in strategies:
            record = _run_one_record(fixture, dry_run=dry_run, strategy=selected_strategy)
            records.append(record)
            running_cost += float(record.get("total_cost", 0.0) or 0.0)
            if max_total_cost > 0 and running_cost >= max_total_cost:
                return records
    return records


def write_results(records: list[dict], output_format: str, results_path: Path) -> Path:
    try:
        results_path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        results_path = Path(tempfile.gettempdir()) / results_path.name
        results_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if output_format == "csv":
            with results_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
                writer.writeheader()
                for record in records:
                    writer.writerow({field: record.get(field, "") for field in RESULT_FIELDS})
        else:
            with results_path.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    except PermissionError:
        fallback_path = Path(tempfile.gettempdir()) / results_path.name
        if output_format == "csv":
            with fallback_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
                writer.writeheader()
                for record in records:
                    writer.writerow({field: record.get(field, "") for field in RESULT_FIELDS})
        else:
            with fallback_path.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        results_path = fallback_path
    return results_path


def summarize(records: list[dict]) -> dict:
    strategies = {}
    for record in records:
        bucket = strategies.setdefault(
            record["strategy"],
            {"count": 0, "pass_count": 0, "avg_score": 0.0, "avg_cost": 0.0},
        )
        bucket["count"] += 1
        bucket["pass_count"] += 1 if record.get("pass") else 0
        bucket["avg_score"] += float(record.get("score", 0.0) or 0.0)
        bucket["avg_cost"] += float(record.get("total_cost", 0.0) or 0.0)
    for bucket in strategies.values():
        count = max(bucket["count"], 1)
        bucket["avg_score"] = round(bucket["avg_score"] / count, 2)
        bucket["avg_cost"] = round(bucket["avg_cost"] / count, 6)
    return {
        "records": len(records),
        "total_cost": round(sum(float(record.get("total_cost", 0.0) or 0.0) for record in records), 6),
        "strategies": strategies,
    }


def record_records_to_benchmark_store(records: list[dict], *, benchmark_pack: str = "evals") -> int:
    from arbiter.infra.benchmark_store import get_benchmark_store

    store = get_benchmark_store()
    recorded = 0
    for record in records:
        verification_status = str(record.get("verification_status", "UNVERIFIED") or "UNVERIFIED").upper()
        if verification_status in {"VERIFIED", "CAUTION"}:
            validity_status = "VALID"
            score_status = "final"
        elif verification_status == "BLOCKED":
            validity_status = "PROVIDER LIMITED"
            score_status = "diagnostic"
        else:
            validity_status = "REVIEW DEGRADED"
            score_status = "diagnostic"
        fixture_id = str(record.get("fixture_id", "unknown") or "unknown")
        try:
            store.record_run(
                task_mode=str(record.get("task_mode", "General Problem Solving") or "General Problem Solving"),
                run_id=f"eval::{record.get('strategy', 'unknown')}::{fixture_id}",
                best_score=float(record.get("score", 0.0) or 0.0),
                iteration_count=int(record.get("iteration_count", 0) or 0),
                total_cost=float(record.get("total_cost", 0.0) or 0.0),
                validity_status=validity_status,
                score_status=score_status,
                verification_status=verification_status,
                ship_readiness=str(record.get("ship_readiness", "UNASSESSED") or "UNASSESSED"),
                stop_reason="dry-run-eval" if record.get("dry_run") else "eval-run",
                preflight_events=0,
                repair_events=max(0, int(record.get("iteration_count", 0) or 0) - 1),
                benchmark_mode=True,
                benchmark_strategy=str(record.get("strategy", "") or ""),
                benchmark_pack=benchmark_pack,
                benchmark_case_id=fixture_id,
                benchmark_case_title=fixture_id,
                team_mode_expected=record.get("expected_team_mode"),
                team_mode_recommended=record.get("team_mode_recommended"),
                team_mode_used=record.get("team_mode_used"),
                team_approval_missing=record.get("team_approval_missing"),
                team_complexity_score=int(record.get("complexity_score", 0) or 0),
                team_complexity_level=str(record.get("complexity_level", "") or ""),
                team_detected_domains=list(record.get("detected_domains", []) or []),
                team_roles=list(record.get("team_roles", []) or []),
            )
        except (PermissionError, OSError):
            break
        recorded += 1
    return recorded


def default_results_path(output_format: str) -> Path:
    suffix = "csv" if output_format == "csv" else "jsonl"
    return RESULTS_DIR / f"eval_results.{suffix}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run The Arbiter evaluation fixtures.")
    parser.add_argument("--dry-run", action="store_true", help="Run with synthetic offline results only.")
    parser.add_argument(
        "--output",
        choices=("jsonl", "csv"),
        default="jsonl",
        help="Results file format.",
    )
    parser.add_argument(
        "--results-path",
        default="",
        help="Optional explicit path for the output file.",
    )
    parser.add_argument(
        "--strategy",
        choices=("arbiter_full_loop", "baseline_single_model"),
        default=DEFAULT_STRATEGY,
        help="Strategy to run when not using --compare.",
    )
    parser.add_argument("--compare", action="store_true", help="Run both baseline and Arbiter strategies.")
    parser.add_argument("--task-mode", default="", help="Optional task mode filter.")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on fixture count.")
    parser.add_argument(
        "--max-total-cost",
        type=float,
        default=0.0,
        help="Optional ceiling for cumulative estimated spend. When reached, the run stops early.",
    )
    parser.add_argument(
        "--record-benchmark-store",
        action="store_true",
        help="Append evaluation records to the local benchmark store for analytics, including dry-run results.",
    )
    parser.add_argument(
        "--fixtures-root",
        default="",
        help="Optional alternate fixtures directory.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    fixtures_root = Path(args.fixtures_root).expanduser() if args.fixtures_root else FIXTURES_DIR
    fixtures = load_fixtures(
        fixtures_root,
        task_mode=args.task_mode,
        limit=args.limit or None,
    )
    if not fixtures:
        raise SystemExit("No evaluation fixtures were found.")

    records = run_records(
        fixtures,
        dry_run=bool(args.dry_run),
        strategy=args.strategy,
        compare=bool(args.compare),
        max_total_cost=float(args.max_total_cost or 0.0),
    )
    results_path = Path(args.results_path).expanduser() if args.results_path else default_results_path(args.output)
    results_path = write_results(records, args.output, results_path)
    summary = summarize(records)
    recorded_benchmarks = 0
    benchmark_store_blocked = False
    if args.record_benchmark_store:
        recorded_benchmarks = record_records_to_benchmark_store(records)
        benchmark_store_blocked = recorded_benchmarks < len(records)
    print(
        json.dumps(
            {
                "dry_run": bool(args.dry_run),
                "fixtures": len(fixtures),
                "records_executed": len(records),
                "results_path": str(results_path),
                "recorded_benchmarks": recorded_benchmarks,
                "benchmark_store_blocked": benchmark_store_blocked,
                "summary": summary,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
