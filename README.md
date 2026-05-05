# The Arbiter

Arbiter is a multi-agent AI orchestration system built to improve answer quality through structured disagreement, repair loops, and memory-guided iteration.

Instead of trusting one model to get everything right in one shot, Arbiter coordinates specialized roles:
- `Auditor` checks whether the request is specific enough before the build starts.
- `Architect` produces the solution.
- `Tech Critic` evaluates implementation or execution quality.
- `Logic Critic` evaluates completeness, reasoning, and requirement coverage.
- `Janitor` consolidates findings into a clean repair brief and becomes the default retry source for broken rounds.

The project is designed to work across multiple task modes such as:
- `Software & IT`
- `Marketing & Growth`
- `Business & Operations`
- `Writing & Content`
- `Personal Planning`

## What makes Arbiter different

- `Local preflight validation` catches structural failures before expensive critique loops.
- `Janitor-led retries` turn noisy multi-agent feedback into one actionable repair brief.
- `Provider lock + stable mode` keep runs predictable and stop silent cross-provider drift.
- `Memory lifecycle management` distinguishes trusted memories from diagnostic or obsolete ones.
- `Targeted retrieval` gives the Architect access to similar past failures and repair patterns.
- `Sandbox test mode` supports local Ollama experiments without destabilizing the main app.

## Current architecture

The main modular app lives in:

```text
arbiter/
  agents/
  app/
  config/
  core/
  infra/
  models/
  prompts/
```

Important files:
- `arbiter/app/streamlit_app.py` — main UI
- `arbiter/app/app_test.py` — local/sandbox UI for Ollama and testing
- `arbiter/core/orchestrator.py` — high-level flow
- `arbiter/core/iteration_engine.py` — Architect / critics / Janitor loop
- `arbiter/core/preflight.py` — deterministic validation
- `arbiter/infra/memory_store.py` — structured memory + optional Chroma retrieval
- `arbiter/infra/model_selector.py` — provider-aware model selection, lock, fallback, cooldowns
- `arbiter/prompts/registry.py` — task-mode prompt assembly and Architect history injection

## Main workflow

1. User enters a task.
2. `Auditor` checks for missing context.
3. `Architect` generates a solution.
4. `Preflight` checks for hard structural issues.
5. `Tech Critic` and `Logic Critic` review the output.
6. `Janitor` consolidates the findings into:
   - summary
   - preserve list
   - pending issues
   - repair brief
7. Arbiter either:
   - accepts a valid round
   - retries with Janitor context
   - or stops with an honest diagnostic/provider-limited state

## Memory system

Arbiter includes a hybrid memory layer:
- structured JSONL run history
- optional Chroma retrieval
- deterministic lightweight local embeddings

Each memory entry is classified as one of:
- `active`
- `caution`
- `conflicted`
- `obsolete`

This means Arbiter does not treat all past runs as equally trustworthy.

The Architect receives retrieved learning context from similar prior tasks, including:
- reusable repair patterns
- similar preflight failures
- lessons from stronger prior runs

This is not full model training, but it gives Arbiter a practical lightweight learning loop.

## Scoring model

Scoring is task-mode aware.

Examples:
- `Software & IT` weights technical quality more heavily.
- `Writing & Content` and `Marketing & Growth` weight logic/completeness more heavily.

Critics are also separated into:
- `Confirmed Defects`
- `Risks / Assumptions`
- `Improvements`

Only confirmed defects should strongly affect scores.

## Provider behavior

Arbiter supports multiple providers and can run with:
- Groq
- Gemini
- OpenAI
- Ollama (sandbox/test mode)

Important runtime controls:
- `Provider Lock`
  Keeps runs inside one provider family unless you explicitly allow mixed fallback.
- `Stable Mode`
  Disables exploration, reduces hidden escalation, and makes testing more repeatable.

## Running the app

### Main app

```bash
cd /Users/lucaomul/TheArbiter
python3 -m streamlit run arbiter/app/streamlit_app.py
```

### Sandbox / test app

```bash
cd /Users/lucaomul/TheArbiter
python3 -m streamlit run arbiter/app/app_test.py
```

## Environment variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=...
GEMINI_API_KEY=...
GROQ_API_KEY=...
```

If you want to use Ollama locally, start it separately:

```bash
ollama serve
```

## Recommended local testing flow

For low-cost iteration:
- use `app_test.py`
- enable `Ollama Test Mode`
- keep the main app for the more stable primary experience

Suggested local role split:
- Architect: `qwen2.5-coder:7b`
- Auditor: `llama3.1:8b`
- Tech Critic: `qwen2.5-coder:7b`
- Logic Critic: `llama3.1:8b`
- Janitor: `llama3.1:8b`

## Notes about runtime artifacts

The following should generally stay local:
- `.env`
- `.arbiter_memory/`
- virtual environments
- local caches

Arbiter’s memory store is useful for your personal learning loop, but it is runtime state, not source code.

## Project direction

Arbiter is moving toward:
- stronger multi-agent coordination
- better retry intelligence
- more trustworthy memory
- cleaner UX
- lower-cost local testing
- domain-aware validation beyond software only

## Author

Luca Crăciun

- GitHub: [github.com/lucaomul](https://github.com/lucaomul)
- LinkedIn: [linkedin.com/in/gabriel-luca-craciun-25ba95295](https://www.linkedin.com/in/gabriel-luca-craciun-25ba95295)

