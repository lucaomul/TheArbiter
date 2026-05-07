from pathlib import Path

from arbiter.infra import benchmark_store


def test_benchmark_store_records_team_metadata(tmp_path):
    store = benchmark_store.BenchmarkStore(benchmark_path=tmp_path / "benchmarks.jsonl")

    store.record_run(
        task_mode="Software & IT",
        run_id="run-1",
        best_score=8.2,
        iteration_count=3,
        total_cost=0.012,
        validity_status="VALID",
        score_status="final",
        verification_status="VERIFIED",
        ship_readiness="READY",
        stop_reason="target_reached",
        preflight_events=0,
        repair_events=1,
        benchmark_mode=True,
        benchmark_strategy="arbiter_full_loop",
        benchmark_pack="evals",
        benchmark_case_id="software_team_support_platform",
        benchmark_case_title="software_team_support_platform",
        team_mode_expected=True,
        team_mode_recommended=True,
        team_mode_used=True,
        team_approval_missing=False,
        team_complexity_score=4,
        team_complexity_level="complex",
        team_detected_domains=["backend", "frontend", "database"],
        team_roles=["Lead Software Architect", "Backend Architect"],
    )

    recent = store.recent_runs(1)[0]
    assert recent["team_mode_expected"] is True
    assert recent["team_mode_recommended"] is True
    assert recent["team_mode_used"] is True
    assert recent["team_detected_domains"] == ["backend", "frontend", "database"]
    assert recent["team_roles"] == ["Lead Software Architect", "Backend Architect"]

    routing = store.team_routing_stats()
    assert routing["summary"]["cases"] == 1
    assert routing["summary"]["matched"] == 1
    assert routing["summary"]["used"] == 1


def test_benchmark_store_falls_back_when_primary_path_is_blocked(monkeypatch, tmp_path):
    primary_path = tmp_path / "blocked" / "benchmark_runs.jsonl"
    fallback_path = tmp_path / "fallback" / "benchmark_runs.jsonl"
    original_ensure = benchmark_store.BenchmarkStore._ensure_path

    def fake_ensure(path: Path):
        if Path(path) == primary_path:
            raise PermissionError("blocked")
        return original_ensure(path)

    monkeypatch.setattr(benchmark_store, "FALLBACK_BENCHMARK_PATH", fallback_path)
    monkeypatch.setattr(benchmark_store.BenchmarkStore, "_ensure_path", staticmethod(fake_ensure))

    store = benchmark_store.BenchmarkStore(benchmark_path=primary_path)

    assert store.fallback_in_use is True
    assert store.benchmark_path == fallback_path
    assert fallback_path.exists()
    assert "blocked" in store.last_error


def test_benchmark_store_stats_report_store_status(tmp_path):
    store = benchmark_store.BenchmarkStore(benchmark_path=tmp_path / "benchmarks.jsonl")

    stats = store.stats()

    assert stats["store_path"] == str(tmp_path / "benchmarks.jsonl")
    assert stats["fallback_in_use"] is False
