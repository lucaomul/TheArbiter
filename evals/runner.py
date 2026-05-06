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
                    "source_file": path.name,
                    "source_line": line_number,
                }
                fixtures.append(fixture)
    if task_mode:
        fixtures = [item for item in fixtures if item["task_mode"] == task_mode]
    if limit is not None:
        fixtures = fixtures[: max(0, int(limit))]
    return fixtures


def dry_run_record(fixture: dict, strategy: str) -> dict:
    seed = int(hashlib.sha256(f"{fixture['id']}::{strategy}".encode("utf-8")).hexdigest()[:8], 16)
    min_score = float(fixture.get("min_score", 7.0) or 7.0)
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
    score = round(float(verification.score or 0.0) * 10.0, 2)
    return {
        "fixture_id": fixture["id"],
        "task_mode": fixture["task_mode"],
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
        "output_excerpt": str(solution or "").strip().replace("\n", " ")[:240],
    }


def run_arbiter_fixture(fixture: dict) -> dict:
    from arbiter.core.orchestrator import ArbiterOrchestrator

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
    result = orchestrator.run(user_input=fixture["task"])
    debug = dict(result.debug_info or {})
    if debug.get("needs_clarification"):
        return {
            "fixture_id": fixture["id"],
            "task_mode": fixture["task_mode"],
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
            "output_excerpt": "Clarification required before execution.",
        }

    latest = result.iteration_history[-1] if result.iteration_history else {}
    score = round(float(result.best_score or 0.0), 2)
    return {
        "fixture_id": fixture["id"],
        "task_mode": fixture["task_mode"],
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
        "output_excerpt": str(result.best_solution or "").strip().replace("\n", " ")[:240],
    }


def run_records(fixtures: Iterable[dict], *, dry_run: bool, strategy: str, compare: bool) -> list[dict]:
    strategies = list(COMPARE_STRATEGIES if compare else (strategy,))
    records = []
    for fixture in fixtures:
        for selected_strategy in strategies:
            if dry_run:
                records.append(dry_run_record(fixture, selected_strategy))
            elif selected_strategy == "baseline_single_model":
                records.append(run_baseline_fixture(fixture))
            else:
                records.append(run_arbiter_fixture(fixture))
    return records


def write_results(records: list[dict], output_format: str, results_path: Path) -> Path:
    try:
        results_path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        results_path = Path(tempfile.gettempdir()) / results_path.name
        results_path.parent.mkdir(parents=True, exist_ok=True)
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
        "strategies": strategies,
    }


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
    )
    results_path = Path(args.results_path).expanduser() if args.results_path else default_results_path(args.output)
    write_results(records, args.output, results_path)
    summary = summarize(records)
    print(
        json.dumps(
            {
                "dry_run": bool(args.dry_run),
                "fixtures": len(fixtures),
                "results_path": str(results_path),
                "summary": summary,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
