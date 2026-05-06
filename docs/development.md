# Development Guide

## Local Setup

Create a local environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,api]"
```

If you want Chroma-backed retrieval too:

```bash
python -m pip install -e ".[dev,api,chromadb]"
```

## Main Commands

### Run the Streamlit workspace

```bash
python -m streamlit run arbiter/app/streamlit_app.py
```

### Run the analytics dashboard

```bash
python -m streamlit run arbiter/app/analytics_dashboard.py
```

### Run the API

```bash
python arbiter/api/run_server.py
```

### Run tests

```bash
python -m pytest --tb=short
```

### Run lint

```bash
python -m ruff check .
```

### Run dry-run evals

```bash
python -m evals.runner --dry-run
```

## Optional Dependency Behavior

The repo is intentionally tolerant of missing optional packages:

- no `chromadb` -> native memory still works
- no API/DB extras -> Streamlit app still works
- no DB driver -> persistence disables itself instead of crashing

When adding new optional features, preserve that pattern.

## Adding a New Task Mode

When introducing a new task mode, update the system in layers:

1. Add the mode to settings and task profile configuration.
2. Extend prompt construction in `arbiter/prompts/`.
3. Add preflight and modality expectations for the new domain.
4. Review critic scoring weights and delivery contract behavior.
5. Extend verification cautiously if there are deterministic checks that make sense.
6. Add eval fixtures and tests before treating the mode as mature.

## Adding a New Provider

Typical integration points:
- `arbiter/infra/plugin_registry.py`
- `arbiter/infra/model_catalog.py`
- `arbiter/infra/model_selector.py`
- `arbiter/infra/llm_client.py`
- `arbiter/config/settings.py` pricing tables or aliases

Requirements for a good provider integration:
- graceful failure behavior
- model/provider metadata attached to calls
- retry handling for rate limits
- cost estimation support where possible
- no hard dependency on the provider for tests

## Testing Guidance

Prefer:
- deterministic tests
- mocked provider responses
- behavioral assertions
- regression coverage for subtle state transitions

Avoid:
- real network calls
- brittle prompt snapshot assertions unless behavior truly depends on the literal text
- tests that require a running Streamlit session

## Memory Store Notes

The native memory store is authoritative.

Current design goals:
- append-only writes during a session for new entries
- explicit `flush()` for compact rewrite of updated lifecycle state
- in-memory indexing by task mode
- lifecycle/versioning that remains traceable instead of silently destructive

If you change memory semantics, add tests for:
- append behavior
- flush behavior
- retrieval behavior
- lifecycle updates

## Packaging Notes

- `pyproject.toml` is the primary packaging source of truth
- `requirements.txt` remains for backwards compatibility
- contributor installs should prefer editable extras

Useful install paths:

```bash
python -m pip install -e .
python -m pip install -e ".[api]"
python -m pip install -e ".[dev,api]"
python -m pip install -e ".[dev,api,chromadb]"
```
