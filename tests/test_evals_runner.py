import csv
import json

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
        },
    )

    fixtures = runner.load_fixtures(tmp_path)

    assert len(fixtures) == 1
    assert fixtures[0]["id"] == "fixture-1"
    assert fixtures[0]["task_mode"] == "General Problem Solving"


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
            "task": "Build a helper.",
            "expected_keywords": ["function", "validation"],
            "min_score": 7.4,
            "notes": "sample",
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
