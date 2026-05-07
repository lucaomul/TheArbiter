import csv
import json
from pathlib import Path

from evals import runner


def _write_fixture(path, fixture):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(fixture) + "\n")


def test_load_fixtures_reads_jsonl_files(tmp_path):
    fixture_file = tmp_path / "sample.jsonl"
    _write_fixture(
        fixture_file,
        {
            "id": "fixture-1",
            "task_mode": "General Problem Solving",
            "task": "Recommend a path.",
            "expected_keywords": ["recommendation", "tradeoff"],
            "min_score": 7.2,
            "notes": "sample",
            "tags": ["trust", "decision"],
            "expected_team_mode": False,
        },
    )

    fixtures = runner.load_fixtures(tmp_path)

    assert len(fixtures) == 1
    assert fixtures[0]["id"] == "fixture-1"
    assert fixtures[0]["task_mode"] == "General Problem Solving"
    assert fixtures[0]["tags"] == ["trust", "decision"]
    assert fixtures[0]["expected_team_mode"] is False


def test_run_records_compare_dry_run_returns_both_strategies(tmp_path):
    fixture_file = tmp_path / "sample.jsonl"
    _write_fixture(
        fixture_file,
        {
            "id": "fixture-1",
            "task_mode": "Marketing & Growth",
            "task": "Create a campaign plan.",
            "expected_keywords": ["audience", "offer", "channel"],
            "min_score": 7.0,
            "notes": "sample",
        },
    )
    fixtures = runner.load_fixtures(tmp_path)

    records = runner.run_records(fixtures, dry_run=True, strategy="arbiter_full_loop", compare=True)

    assert len(records) == 2
    strategies = {record["strategy"] for record in records}
    assert strategies == {"baseline_single_model", "arbiter_full_loop"}
    assert all(record["dry_run"] is True for record in records)
    assert all(record["team_mode_recommended"] is False for record in records)


def test_main_writes_dry_run_jsonl_results(tmp_path):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    results_path = tmp_path / "results.jsonl"
    fixture_file = fixtures_dir / "sample.jsonl"
    _write_fixture(
        fixture_file,
        {
            "id": "fixture-1",
            "task_mode": "Writing & Content",
            "task": "Write a memo.",
            "expected_keywords": ["memo", "argument"],
            "min_score": 7.1,
            "notes": "sample",
        },
    )

    exit_code = runner.main(
        [
            "--fixtures-root",
            str(fixtures_dir),
            "--dry-run",
            "--compare",
            "--output",
            "jsonl",
            "--results-path",
            str(results_path),
        ]
    )

    assert exit_code == 0
    lines = results_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    payloads = [json.loads(line) for line in lines]
    assert {item["strategy"] for item in payloads} == {"baseline_single_model", "arbiter_full_loop"}


def test_main_writes_dry_run_csv_results(tmp_path):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    results_path = tmp_path / "results.csv"
    fixture_file = fixtures_dir / "sample.jsonl"
    _write_fixture(
        fixture_file,
        {
            "id": "fixture-1",
            "task_mode": "Software & IT",
            "task": (
                "Design a production-ready full-stack support dashboard with a Python backend API, "
                "React frontend, SQL database, auth, Docker deployment, testing, monitoring, and CI/CD."
            ),
            "expected_keywords": ["function", "validation"],
            "min_score": 7.4,
            "notes": "sample",
            "expected_team_mode": True,
        },
    )

    exit_code = runner.main(
        [
            "--fixtures-root",
            str(fixtures_dir),
            "--dry-run",
            "--output",
            "csv",
            "--results-path",
            str(results_path),
        ]
    )

    assert exit_code == 0
    with results_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["fixture_id"] == "fixture-1"
    assert rows[0]["team_mode_recommended"] == "True"
    assert rows[0]["expected_team_mode"] == "True"


def test_dry_run_records_include_team_metadata_for_complex_software_task(tmp_path):
    fixture_file = tmp_path / "sample.jsonl"
    _write_fixture(
        fixture_file,
        {
            "id": "fixture-1",
            "task_mode": "Software & IT",
            "task": (
                "Design a production-ready full-stack customer support platform with a Python backend API, "
                "React frontend, SQL database, auth, Docker deployment, testing, monitoring, caching, and CI/CD."
            ),
            "expected_keywords": ["platform", "api", "database", "deployment"],
            "min_score": 7.5,
            "notes": "sample",
            "expected_team_mode": True,
            "tags": ["software-team", "full-stack"],
        },
    )
    fixtures = runner.load_fixtures(tmp_path)

    records = runner.run_records(fixtures, dry_run=True, strategy="arbiter_full_loop", compare=False)

    assert len(records) == 1
    record = records[0]
    assert record["team_mode_recommended"] is True
    assert record["team_mode_used"] is True
    assert record["expected_team_mode"] is True
    assert "backend" in record["detected_domains"]
    assert "frontend" in record["detected_domains"]
    assert "Lead Software Architect" in record["team_roles"]


def test_run_records_stops_when_cost_cap_is_reached():
    fixtures = [
        {"id": "fixture-1", "task_mode": "General Problem Solving", "task": "A", "min_score": 7.0, "notes": ""},
        {"id": "fixture-2", "task_mode": "General Problem Solving", "task": "B", "min_score": 7.0, "notes": ""},
        {"id": "fixture-3", "task_mode": "General Problem Solving", "task": "C", "min_score": 7.0, "notes": ""},
    ]

    records = runner.run_records(
        fixtures,
        dry_run=True,
        strategy="arbiter_full_loop",
        compare=False,
        max_total_cost=0.002,
    )

    assert 1 <= len(records) < len(fixtures)
    assert sum(float(record["total_cost"]) for record in records) >= 0.002


def test_record_records_to_benchmark_store_uses_local_store(monkeypatch):
    recorded = []

    class FakeStore:
        def record_run(self, **kwargs):
            recorded.append(kwargs)
            return kwargs

    monkeypatch.setattr(
        "arbiter.infra.benchmark_store.get_benchmark_store",
        lambda: FakeStore(),
    )

    count = runner.record_records_to_benchmark_store(
        [
            {
                "fixture_id": "fixture-1",
                "task_mode": "Writing & Content",
                "strategy": "arbiter_full_loop",
                "score": 8.1,
                "verification_status": "VERIFIED",
                "ship_readiness": "READY",
                "iteration_count": 2,
                "total_cost": 0.0,
                "dry_run": True,
            }
        ]
    )

    assert count == 1
    assert len(recorded) == 1
    assert recorded[0]["benchmark_mode"] is True
    assert recorded[0]["benchmark_pack"] == "evals"
    assert recorded[0]["stop_reason"] == "dry-run-eval"


def test_record_records_to_benchmark_store_stops_cleanly_when_store_is_blocked(monkeypatch):
    class FakeStore:
        def record_run(self, **kwargs):
            raise PermissionError("blocked")

    monkeypatch.setattr(
        "arbiter.infra.benchmark_store.get_benchmark_store",
        lambda: FakeStore(),
    )

    count = runner.record_records_to_benchmark_store(
        [
            {
                "fixture_id": "fixture-1",
                "task_mode": "Writing & Content",
                "strategy": "arbiter_full_loop",
                "score": 8.1,
                "verification_status": "VERIFIED",
                "ship_readiness": "READY",
                "iteration_count": 2,
                "total_cost": 0.0,
                "dry_run": True,
            }
        ]
    )

    assert count == 0


def test_write_results_falls_back_to_tmp_when_file_write_is_blocked(monkeypatch, tmp_path):
    records = [
        {
            "fixture_id": "fixture-1",
            "task_mode": "Writing & Content",
            "strategy": "arbiter_full_loop",
            "score": 8.0,
            "verification_status": "VERIFIED",
            "ship_readiness": "READY",
            "iteration_count": 2,
            "total_cost": 0.0,
            "pass": True,
            "dry_run": True,
            "min_score": 7.0,
            "notes": "",
            "output_excerpt": "ok",
        }
    ]
    blocked_path = tmp_path / "blocked" / "results.jsonl"
    real_open = Path.open

    def fake_open(path_obj, *args, **kwargs):
        if Path(path_obj) == blocked_path:
            raise PermissionError("blocked")
        return real_open(path_obj, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)
    output_path = runner.write_results(records, "jsonl", blocked_path)

    assert output_path != blocked_path
    assert output_path.exists()


def test_main_reports_fallback_results_path(monkeypatch, tmp_path, capsys):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    blocked_path = tmp_path / "blocked" / "results.jsonl"
    fixture_file = fixtures_dir / "sample.jsonl"
    _write_fixture(
        fixture_file,
        {
            "id": "fixture-1",
            "task_mode": "Writing & Content",
            "task": "Write a memo.",
            "expected_keywords": ["memo", "argument"],
            "min_score": 7.1,
            "notes": "sample",
        },
    )

    fallback_path = tmp_path / "fallback.jsonl"
    monkeypatch.setattr(runner, "write_results", lambda records, output_format, results_path: fallback_path)

    exit_code = runner.main(
        [
            "--fixtures-root",
            str(fixtures_dir),
            "--dry-run",
            "--results-path",
            str(blocked_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["results_path"] == str(fallback_path)


def test_main_reports_blocked_benchmark_store(monkeypatch, tmp_path, capsys):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    fixture_file = fixtures_dir / "sample.jsonl"
    _write_fixture(
        fixture_file,
        {
            "id": "fixture-1",
            "task_mode": "Writing & Content",
            "task": "Write a memo.",
            "expected_keywords": ["memo", "argument"],
            "min_score": 7.1,
            "notes": "sample",
        },
    )

    monkeypatch.setattr(runner, "record_records_to_benchmark_store", lambda records: 0)

    exit_code = runner.main(
        [
            "--fixtures-root",
            str(fixtures_dir),
            "--dry-run",
            "--record-benchmark-store",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["recorded_benchmarks"] == 0
    assert payload["benchmark_store_blocked"] is True
