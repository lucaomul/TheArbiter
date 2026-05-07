import json
import os
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MEMORY_DIR = PROJECT_ROOT / ".arbiter_memory"
DEFAULT_BENCHMARK_PATH = DEFAULT_MEMORY_DIR / "benchmark_runs.jsonl"
FALLBACK_BENCHMARK_DIR = Path(tempfile.gettempdir()) / "the_arbiter_benchmark_store"
FALLBACK_BENCHMARK_PATH = FALLBACK_BENCHMARK_DIR / "benchmark_runs.jsonl"


def _configured_benchmark_path() -> Path:
    explicit_path = str(os.getenv("ARBITER_BENCHMARK_PATH", "") or "").strip()
    if explicit_path:
        return Path(explicit_path).expanduser()

    explicit_dir = str(os.getenv("ARBITER_BENCHMARK_DIR", "") or "").strip()
    if explicit_dir:
        return Path(explicit_dir).expanduser() / "benchmark_runs.jsonl"

    explicit_memory_dir = str(os.getenv("ARBITER_MEMORY_DIR", "") or "").strip()
    if explicit_memory_dir:
        return Path(explicit_memory_dir).expanduser() / "benchmark_runs.jsonl"

    return DEFAULT_BENCHMARK_PATH


class BenchmarkStore:
    """
    Lightweight benchmark and run-metrics store.

    This is not a full evaluation harness yet, but it gives Arbiter
    measurable history for:
    - score quality
    - cost
    - iteration count
    - validity rate
    - diagnostic rate
    - benchmark-mode performance
    """

    def __init__(self, benchmark_path: Optional[Path] = None):
        self._runs: List[Dict] = []
        self.primary_path = Path(benchmark_path or _configured_benchmark_path()).expanduser()
        self.benchmark_path = self.primary_path
        self.fallback_in_use = False
        self.last_error = ""
        self._activate_path()
        self._load()

    def _activate_path(self):
        try:
            self._ensure_path(self.primary_path)
            self.benchmark_path = self.primary_path
            return
        except OSError as exc:
            self.last_error = str(exc)
            self._switch_to_fallback(exc)

    @staticmethod
    def _ensure_path(path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()

    def _switch_to_fallback(self, exc: Optional[Exception] = None):
        self.fallback_in_use = True
        self.last_error = str(exc or self.last_error or "primary benchmark path unavailable")
        self._ensure_path(FALLBACK_BENCHMARK_PATH)
        self.benchmark_path = FALLBACK_BENCHMARK_PATH

    def _load(self):
        loaded = []
        try:
            with self.benchmark_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        loaded.append(json.loads(raw))
                    except Exception:
                        continue
        except OSError as exc:
            if not self.fallback_in_use:
                self._switch_to_fallback(exc)
                return self._load()
            self.last_error = str(exc)
        self._runs = loaded[-500:]

    def record_run(
        self,
        task_mode: str,
        run_id: str,
        best_score: float,
        iteration_count: int,
        total_cost: float,
        validity_status: str,
        score_status: str,
        verification_status: str,
        ship_readiness: str,
        stop_reason: str,
        preflight_events: int,
        repair_events: int,
        benchmark_mode: bool = False,
        benchmark_strategy: str = "",
        benchmark_pack: str = "",
        benchmark_case_id: str = "",
        benchmark_case_title: str = "",
        team_mode_expected: Optional[bool] = None,
        team_mode_recommended: Optional[bool] = None,
        team_mode_used: Optional[bool] = None,
        team_approval_missing: Optional[bool] = None,
        team_complexity_score: int = 0,
        team_complexity_level: str = "",
        team_detected_domains: Optional[list[str]] = None,
        team_roles: Optional[list[str]] = None,
    ) -> Dict:
        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "task_mode": task_mode,
            "best_score": float(best_score or 0.0),
            "iteration_count": int(iteration_count or 0),
            "total_cost": float(total_cost or 0.0),
            "validity_status": validity_status,
            "score_status": score_status,
            "verification_status": str(verification_status or "UNVERIFIED"),
            "ship_readiness": str(ship_readiness or "UNASSESSED"),
            "stop_reason": str(stop_reason or "").strip(),
            "preflight_events": int(preflight_events or 0),
            "repair_events": int(repair_events or 0),
            "benchmark_mode": bool(benchmark_mode),
            "benchmark_strategy": str(benchmark_strategy or "").strip(),
            "benchmark_pack": str(benchmark_pack or "").strip(),
            "benchmark_case_id": str(benchmark_case_id or "").strip(),
            "benchmark_case_title": str(benchmark_case_title or "").strip(),
            "team_mode_expected": team_mode_expected,
            "team_mode_recommended": team_mode_recommended,
            "team_mode_used": team_mode_used,
            "team_approval_missing": team_approval_missing,
            "team_complexity_score": int(team_complexity_score or 0),
            "team_complexity_level": str(team_complexity_level or "").strip(),
            "team_detected_domains": list(team_detected_domains or []),
            "team_roles": list(team_roles or []),
        }
        self._runs.append(entry)
        self._runs = self._runs[-500:]
        try:
            with self.benchmark_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        except OSError as exc:
            if not self.fallback_in_use:
                self._switch_to_fallback(exc)
                with self.benchmark_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
            else:
                self.last_error = str(exc)
                raise
        return entry

    def stats(self) -> Dict:
        if not self._runs:
            return {
                "count": 0,
                "avg_score": 0.0,
                "avg_cost": 0.0,
                "avg_iterations": 0.0,
                "avg_valid_score": 0.0,
                "avg_benchmark_score": 0.0,
                "valid_runs": 0,
                "diagnostic_runs": 0,
                "valid_rate": 0.0,
                "diagnostic_rate": 0.0,
                "validity": {},
                "task_modes": {},
                "benchmark_runs": 0,
                "verified_runs": 0,
                "verified_rate": 0.0,
                "ready_runs": 0,
                "ready_rate": 0.0,
                "store_path": str(self.benchmark_path),
                "fallback_in_use": self.fallback_in_use,
                "last_error": self.last_error,
            }

        count = len(self._runs)
        avg_score = sum(item.get("best_score", 0.0) for item in self._runs) / count
        avg_cost = sum(item.get("total_cost", 0.0) for item in self._runs) / count
        avg_iterations = sum(item.get("iteration_count", 0) for item in self._runs) / count
        validity = Counter(item.get("validity_status", "UNKNOWN") for item in self._runs)
        task_modes = Counter(item.get("task_mode", "Unknown") for item in self._runs)
        benchmark_runs = sum(1 for item in self._runs if item.get("benchmark_mode"))
        valid_entries = [item for item in self._runs if item.get("validity_status") == "VALID"]
        diagnostic_entries = [item for item in self._runs if item.get("score_status") == "diagnostic"]
        benchmark_entries = [item for item in self._runs if item.get("benchmark_mode")]
        verified_entries = [item for item in self._runs if item.get("verification_status") == "VERIFIED"]
        ready_entries = [item for item in self._runs if item.get("ship_readiness") == "READY"]
        return {
            "count": count,
            "avg_score": round(avg_score, 2),
            "avg_cost": round(avg_cost, 4),
            "avg_iterations": round(avg_iterations, 2),
            "avg_valid_score": round(
                sum(item.get("best_score", 0.0) for item in valid_entries) / len(valid_entries), 2
            ) if valid_entries else 0.0,
            "avg_benchmark_score": round(
                sum(item.get("best_score", 0.0) for item in benchmark_entries) / len(benchmark_entries), 2
            ) if benchmark_entries else 0.0,
            "valid_runs": len(valid_entries),
            "verified_runs": len(verified_entries),
            "ready_runs": len(ready_entries),
            "diagnostic_runs": len(diagnostic_entries),
            "valid_rate": round((len(valid_entries) / count) * 100, 1),
            "verified_rate": round((len(verified_entries) / count) * 100, 1),
            "ready_rate": round((len(ready_entries) / count) * 100, 1),
            "diagnostic_rate": round((len(diagnostic_entries) / count) * 100, 1),
            "validity": dict(validity),
            "task_modes": dict(task_modes),
            "benchmark_runs": benchmark_runs,
            "store_path": str(self.benchmark_path),
            "fallback_in_use": self.fallback_in_use,
            "last_error": self.last_error,
        }

    def by_task_mode(self) -> Dict[str, Dict]:
        grouped = defaultdict(list)
        for run in self._runs:
            grouped[run.get("task_mode", "Unknown")].append(run)
        output = {}
        for mode, runs in grouped.items():
            count = len(runs)
            verified_runs = [item for item in runs if item.get("verification_status") == "VERIFIED"]
            ready_runs = [item for item in runs if item.get("ship_readiness") == "READY"]
            output[mode] = {
                "count": count,
                "avg_score": round(sum(item.get("best_score", 0.0) for item in runs) / count, 2),
                "avg_cost": round(sum(item.get("total_cost", 0.0) for item in runs) / count, 4),
                "avg_iterations": round(sum(item.get("iteration_count", 0) for item in runs) / count, 2),
                "verified_rate": round((len(verified_runs) / count) * 100, 1) if count else 0.0,
                "ready_rate": round((len(ready_runs) / count) * 100, 1) if count else 0.0,
            }
        return output

    def by_strategy(self) -> Dict[str, Dict]:
        grouped = defaultdict(list)
        for run in self._runs:
            strategy = run.get("benchmark_strategy") or "unlabeled"
            grouped[strategy].append(run)
        output = {}
        for strategy, runs in grouped.items():
            count = len(runs)
            valid_runs = [item for item in runs if item.get("validity_status") == "VALID"]
            verified_runs = [item for item in runs if item.get("verification_status") == "VERIFIED"]
            ready_runs = [item for item in runs if item.get("ship_readiness") == "READY"]
            output[strategy] = {
                "count": count,
                "avg_score": round(sum(item.get("best_score", 0.0) for item in runs) / count, 2),
                "avg_cost": round(sum(item.get("total_cost", 0.0) for item in runs) / count, 4),
                "avg_iterations": round(sum(item.get("iteration_count", 0) for item in runs) / count, 2),
                "valid_rate": round((len(valid_runs) / count) * 100, 1) if count else 0.0,
                "verified_rate": round((len(verified_runs) / count) * 100, 1) if count else 0.0,
                "ready_rate": round((len(ready_runs) / count) * 100, 1) if count else 0.0,
            }
        return output

    def by_case(self) -> Dict[str, Dict]:
        grouped = defaultdict(list)
        for run in self._runs:
            case_id = run.get("benchmark_case_id") or "ad_hoc"
            grouped[case_id].append(run)
        output = {}
        for case_id, runs in grouped.items():
            count = len(runs)
            output[case_id] = {
                "count": count,
                "title": runs[-1].get("benchmark_case_title") or case_id,
                "pack": runs[-1].get("benchmark_pack") or "",
                "avg_score": round(sum(item.get("best_score", 0.0) for item in runs) / count, 2),
                "avg_cost": round(sum(item.get("total_cost", 0.0) for item in runs) / count, 4),
                "avg_iterations": round(sum(item.get("iteration_count", 0) for item in runs) / count, 2),
            }
        return output

    def team_routing_stats(self) -> Dict[str, Dict]:
        benchmark_runs = [item for item in self._runs if item.get("benchmark_mode")]
        cases = [
            item
            for item in benchmark_runs
            if item.get("team_mode_expected") is not None
            or item.get("team_mode_recommended") is not None
            or item.get("team_mode_used") is not None
        ]
        total = len(cases)
        if not total:
            return {
                "summary": {
                    "cases": 0,
                    "matched": 0,
                    "mismatched": 0,
                    "recommended": 0,
                    "used": 0,
                },
                "rows": [],
            }

        rows = []
        matched = 0
        recommended = 0
        used = 0
        for item in cases:
            expected = item.get("team_mode_expected")
            recommended_flag = item.get("team_mode_recommended")
            used_flag = item.get("team_mode_used")
            match = expected is None or bool(expected) == bool(recommended_flag)
            matched += 1 if match else 0
            recommended += 1 if bool(recommended_flag) else 0
            used += 1 if bool(used_flag) else 0
            rows.append(
                {
                    "case_id": item.get("benchmark_case_id") or item.get("run_id", ""),
                    "title": item.get("benchmark_case_title") or item.get("benchmark_case_id") or item.get("run_id", ""),
                    "expected_team_mode": expected,
                    "team_mode_recommended": recommended_flag,
                    "team_mode_used": used_flag,
                    "team_approval_missing": item.get("team_approval_missing"),
                    "complexity_score": item.get("team_complexity_score", 0),
                    "complexity_level": item.get("team_complexity_level", ""),
                    "detected_domains": ", ".join(item.get("team_detected_domains", []) or []),
                    "team_roles": ", ".join(item.get("team_roles", []) or []),
                    "match": match,
                }
            )
        return {
            "summary": {
                "cases": total,
                "matched": matched,
                "mismatched": total - matched,
                "recommended": recommended,
                "used": used,
            },
            "rows": rows,
        }

    def recent_runs(self, limit: int = 10) -> List[Dict]:
        return list(self._runs[-limit:])


_store = BenchmarkStore()


def get_benchmark_store() -> BenchmarkStore:
    return _store
