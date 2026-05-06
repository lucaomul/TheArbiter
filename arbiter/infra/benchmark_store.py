import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = PROJECT_ROOT / ".arbiter_memory"
BENCHMARK_PATH = BENCHMARK_DIR / "benchmark_runs.jsonl"


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

    def __init__(self):
        self._runs: List[Dict] = []
        self._ensure_paths()
        self._load()

    @staticmethod
    def _ensure_paths():
        BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
        if not BENCHMARK_PATH.exists():
            BENCHMARK_PATH.touch()

    def _load(self):
        loaded = []
        with BENCHMARK_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    loaded.append(json.loads(raw))
                except Exception:
                    continue
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
        }
        self._runs.append(entry)
        self._runs = self._runs[-500:]
        with BENCHMARK_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
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

    def recent_runs(self, limit: int = 10) -> List[Dict]:
        return list(self._runs[-limit:])


_store = BenchmarkStore()


def get_benchmark_store() -> BenchmarkStore:
    return _store
