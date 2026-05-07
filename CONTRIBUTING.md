# Contributing to The Arbiter

Thanks for contributing to The Arbiter.

The project is built around one simple constraint: **quality and trust matter more than one-shot fluency**. Contributions should strengthen the product's reliability, clarity, and verification story instead of adding novelty for its own sake.

## Development Setup

Create a local environment and install the contributor extras:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,api]"
```

If you also want Chroma-backed memory retrieval:

```bash
python -m pip install -e ".[dev,api,chromadb]"
```

If you prefer short commands, the root `Makefile` provides:

```bash
make install-dev
make lint
make test
make eval-dry-run
```

If `.venv/bin/python` exists, the Make targets use it automatically.

## Contribution Rules

- Keep changes additive and backwards compatible unless a breaking change is explicitly justified.
- Prefer hardening, tests, observability, and verification quality over broad rewrites.
- Keep tests fully offline. Do not introduce real provider calls into the test suite.
- Preserve graceful degradation when optional dependencies are missing.
- If you change scoring, verification, memory, or routing behavior, add regression coverage.

## Before Opening a Pull Request

Run:

```bash
python -m ruff check .
python -m pytest --tb=short
python -m evals.runner --dry-run
```

If an optional feature is involved, include a short note describing:
- what happens with the dependency installed
- what happens without it

## Where to Make Changes

Common integration points:

- `arbiter/core/`
  - orchestration, scoring, stopping, verification, team routing
- `arbiter/agents/`
  - agent wrappers and structured response handling
- `arbiter/prompts/`
  - role instructions and task-mode prompt logic
- `arbiter/infra/`
  - memory, providers, logging, model selection, persistence
- `arbiter/app/`
  - Streamlit workspace and analytics dashboard
- `arbiter/api/`
  - FastAPI routes, schemas, auth, and middleware
- `evals/`
  - benchmark fixtures and offline regression runner
- `tests/`
  - deterministic unit and integration coverage

## Adding a New Task Mode

When introducing a new task mode:

1. Add the configuration and profile.
2. Extend prompt construction for that mode.
3. Update preflight expectations and delivery contracts.
4. Review critic weighting and scoring behavior.
5. Add verifier checks only where deterministic validation genuinely helps.
6. Add eval fixtures and offline tests before treating the mode as mature.

## Adding a New Provider

Provider integrations should be conservative and observable.

Requirements:

- attach model/provider metadata to calls
- handle rate limits and retries explicitly
- estimate cost when usage data is incomplete
- degrade safely if credentials or optional packages are missing
- keep tests mocked and offline

Typical integration points:

- `arbiter/infra/plugin_registry.py`
- `arbiter/infra/model_catalog.py`
- `arbiter/infra/model_selector.py`
- `arbiter/infra/llm_client.py`
- `arbiter/config/settings.py`

## Pull Request Style

- Keep diffs focused.
- Explain behavior changes, not just file changes.
- If a change affects trust, verification, or readiness, mention that explicitly.
- Avoid bundling unrelated formatting churn with product logic.

## Documentation Expectations

If you add or materially change a feature, update the relevant docs:

- `README.md`
- `docs/architecture.md`
- `docs/api.md`
- `docs/benchmarks.md`
- `docs/development.md`

The project should stay honest. If something is experimental, say so plainly.
