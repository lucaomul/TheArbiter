# Benchmarks and Evals

## Purpose

The eval suite is designed to make regression and comparison work practical without turning the project into a fake leaderboard machine.

It currently focuses on:
- representative fixture coverage across all six task modes
- repeatable local or CI execution
- dry-run support with no external API calls
- comparable outputs from a baseline single-model path and the full Arbiter path

## Fixture Layout

Fixtures live in:

```text
evals/fixtures/
```

Current task families:
- `software_it.jsonl`
- `marketing_growth.jsonl`
- `business_operations.jsonl`
- `writing_content.jsonl`
- `personal_planning.jsonl`
- `general_problem_solving.jsonl`

Each JSONL row includes:
- `id`
- `task_mode`
- `task`
- `expected_keywords`
- `min_score`
- `notes`

## Running the Suite

### Dry-run mode

Dry-run mode is CI-safe and does not call real providers.

```bash
python -m evals.runner --dry-run
```

### Compare baseline vs Arbiter

```bash
python -m evals.runner --compare --output jsonl
```

### CSV output

```bash
python -m evals.runner --dry-run --output csv
```

## Output Fields

Each record includes:
- `fixture_id`
- `task_mode`
- `strategy`
- `score`
- `verification_status`
- `ship_readiness`
- `iteration_count`
- `total_cost`
- `pass`

## Reading the Results

Important interpretation rules:

- dry-run scores are synthetic and useful for regression checks
- non-dry-run outputs are operational measurements, not formal scientific benchmarks
- cost numbers are estimates unless they come from real provider usage metadata
- pass/fail is driven by fixture `min_score`, which is a practical threshold, not a claim of universal quality

## Sample Dry-Run Summary

Example:

```json
{
  "dry_run": true,
  "fixtures": 30,
  "results_path": "evals/results/eval_results.jsonl",
  "summary": {
    "records": 30,
    "strategies": {
      "arbiter_full_loop": {
        "count": 30,
        "pass_count": 30,
        "avg_score": 7.82,
        "avg_cost": 0.001377
      }
    }
  }
}
```

Treat summaries like this as engineering telemetry, not marketing proof.

## CI Usage

CI currently runs:

```bash
python -m evals.runner --dry-run
```

This protects:
- fixture loading
- result writing
- summary generation
- dry-run behavior staying executable

## Recommended Next Steps

As the suite matures, the highest-value improvements are:
- richer domain-specific expected signals
- more realistic baseline comparison runs
- historical result archiving
- benchmark trend reporting in the analytics dashboard
