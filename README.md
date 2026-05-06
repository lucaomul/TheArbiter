# The Arbiter

**The Arbiter is a multi-agent AI orchestration workspace that audits the brief, drafts the solution, challenges it with specialist critics, cleans the dispute into a repair brief, and improves the result through controlled retries, persistent memory, and verification-aware trust signals.**

This project exists because one-shot prompting is not enough for serious work.

If you care about:
- better output quality
- fewer hallucinated “wins”
- clearer retry logic
- tighter control over cost and provider behavior
- reusable learning across repeated tasks

then you need more than a single model with a nice prompt.

You need a system.

The Arbiter is that system.

---

## What The Arbiter Does

The Arbiter coordinates a structured intelligence loop across multiple AI roles:

- `Auditor`
  checks whether the brief is specific enough to build against

- `Architect`
  produces the main solution

- `Tech Critic`
  tests execution quality, technical correctness, implementation rigor, and operational feasibility

- `Logic Critic`
  tests reasoning quality, completeness, requirement coverage, and structural coherence

- `Janitor`
  consolidates the dispute into a cleaner repair brief and becomes the default retry source

Before and after that loop, The Arbiter also applies:

- `Preflight validation`
  fast deterministic checks that catch structural failures before spending on unnecessary review

- `Deterministic verification`
  grounded post-generation checks that calibrate confidence and make the score more truthful

- `Persistent memory`
  stored repair patterns, trusted history, and project notes that can be retrieved on similar future tasks

The result is a system that does not just generate answers.
It **builds, challenges, repairs, and learns**.

---

## Why It Matters

Most AI products still behave like this:

1. send prompt
2. get answer
3. hope it is right

That breaks fast when the task has:
- real constraints
- real ambiguity
- multiple moving parts
- implementation details
- business consequences

The Arbiter is designed to reduce that fragility.

Instead of trusting a single first answer, it introduces:
- role separation
- explicit failure handling
- Janitor-led retries
- model and provider controls
- verification-aware trust signals
- memory-guided improvement

This makes it much closer to an **AI reasoning and quality-control platform** than a prompt wrapper.

---

## What Makes The Arbiter Different

### 1. It separates roles on purpose
Generation, review, repair, and consolidation are not collapsed into one vague “agent loop.”

That means the system can:
- ask for missing information early
- challenge the draft from multiple angles
- avoid feeding raw noisy criticism directly back into the generator

### 2. It distinguishes score from trust
The Arbiter does not treat “high score” as the same thing as “safe result.”

It tracks:
- `score`
- `validity`
- `confidence`
- `verification`
- `readiness`

So a result can look strong and still be marked as needing review, caution, or further work.

### 3. It uses Janitor-led retries
Retries are not driven by a messy wall of critic text.

The Janitor compresses the situation into:
- what is still broken
- what was resolved
- what regressed
- what to preserve
- what the next repair must do

This makes second and third passes much more stable.

### 4. It learns across runs
The Arbiter stores:
- run history
- repair patterns
- memory trust states
- manual project notes

It does not just remember “what happened.”
It remembers **what is worth reusing**.

### 5. It gives the operator real control
The system supports:
- Groq
- OpenAI
- Gemini
- Anthropic / Claude
- Ollama for local testing

And exposes:
- AI presets
- manual role-by-role selection
- provider lock
- stable mode
- autonomous loop settings

That means you can trade off cost, speed, stability, and quality consciously instead of guessing.

---

## Core Capabilities

### Multi-agent orchestration
The Arbiter turns a single AI request into a controlled decision flow across multiple roles with distinct responsibilities.

### Preflight before critic spend
Broken or incomplete outputs can be caught before the system burns extra cost on full review rounds.

### Verification-aware scoring
The final score is no longer just “what the critics felt.”
Deterministic verification now lightly calibrates the final number so an `8/10` is closer to a real `8/10`.

### Readiness signals
Each result can be surfaced as:
- `READY`
- `CLOSE`
- `NEEDS REVIEW`
- `BLOCKED`

This is much more practical than a raw score alone.

### Memory lifecycle management
Memory entries are governed as:
- `active`
- `caution`
- `conflicted`
- `obsolete`

This helps The Arbiter reuse good lessons without turning every past run into permanent truth.

### Benchmark and evaluation tracking
The project tracks:
- score
- cost
- iterations
- validity rate
- verified rate
- ready rate

So improvements can be measured over time, not just felt.

### Local experimentation
There is a sandbox path for local/Ollama testing so prompt and orchestration behavior can be improved without constantly paying for API calls.

---

## Cost and Efficiency Model

The Arbiter is not “cheap” because it uses fewer ideas.
It is cheaper because it is designed to spend model calls more deliberately.

This matters because multi-agent systems can easily become more expensive than a single model if they:
- review broken drafts too early
- rerun with noisy feedback
- drift across providers silently
- keep paying premium models for experimentation that should have happened locally

The Arbiter is built to reduce exactly that waste.

### Where cost control comes from

#### 1. Preflight blocks bad spend early
Before paying for full critic review, The Arbiter runs a deterministic preflight pass.

That means obviously broken outputs can be stopped before they trigger:
- Tech Critic
- Logic Critic
- Janitor
- extra retry cycles

In failure-heavy workflows, that can save `~1 full review round` on bad drafts.

#### 2. Janitor reduces retry waste
Instead of feeding the Architect a messy wall of multi-agent criticism, the Janitor converts it into:
- what is still broken
- what regressed
- what to preserve
- what the next retry must do

That can cut `~1–2 noisy repair cycles` in drift-heavy runs.

#### 3. Model control prevents accidental overspend
The Arbiter supports:
- presets
- manual role selection
- provider lock
- stable mode
- local Ollama testing

So you can decide when to use:
- cheaper Groq paths
- mixed-provider review diversity
- premium Claude or OpenAI paths
- local experimentation before paid runs

This is important because cost should be a product choice, not a hidden side effect.

#### 4. Memory reduces repeated context rebuild
When tasks are similar, The Arbiter can reuse:
- trusted repair patterns
- prior defect history
- project notes
- past successful resolution logic

That does not guarantee fewer calls every time, but it can improve convergence and reduce repeated “start from zero” behavior on recurring task families.

#### 5. Verification reduces false confidence
A system that accepts weak outputs too early creates hidden downstream cost:
- bad implementation
- wasted retries later
- human cleanup
- unreliable delivery

By separating:
- score
- confidence
- verification
- readiness

The Arbiter tries to reduce the very expensive mistake of treating a nice-looking result as a finished one.

### Practical cost interpretation

Use The Arbiter like this:
- `cheap exploration`
  local/Ollama or low-cost Groq presets for testing behavior
- `controlled production`
  stable provider-locked runs for real delivery
- `premium escalation`
  stronger models only when the task actually justifies them

### Directional efficiency benefits

These are **architecture-level estimates**, not formal benchmark claims:

- `~1 full critic round avoided`
  when preflight blocks structurally broken outputs before full review spend

- `~1–2 retries reduced`
  when Janitor compresses reviewer noise into a cleaner repair brief

- `~lower experimentation spend`
  when local/Ollama or cheaper presets are used before premium runs

- `~faster convergence on repeated task families`
  when memory and prior repair patterns are reused intelligently

- `~higher operator trust`
  because provider issues, blocked states, verification, and readiness are made explicit

In short, The Arbiter is designed to reduce:
- blind prompting
- duplicated review spend
- unstable retries
- hidden fallback cost
- false “good enough” wins

and increase:
- cost awareness
- controllability
- reuse
- clarity
- trust

---

## Task Modes

The Arbiter is not software-only.

It supports task-aware behavior across:
- `Software & IT`
- `Marketing & Growth`
- `Business & Operations`
- `Writing & Content`
- `Personal Planning`
- `General Problem Solving`

Each mode changes:
- auditing emphasis
- generation guidance
- review weighting
- validation expectations

That means a software task and a growth strategy task are not scored with the same naive rubric.

---

## How The Loop Works

1. User submits a task
2. Auditor checks whether the task is clear enough
3. Architect produces the draft
4. Preflight validates the draft locally
5. Critics evaluate technical and logical quality
6. Janitor consolidates the dispute
7. The Arbiter either:
   - accepts the result
   - retries with Janitor context
   - or stops honestly with a diagnostic / blocked / review-degraded state

This is not just “loop until number gets bigger.”
It is a governed improvement cycle.

---

## Product UX

The current app is designed as a product workspace, not a debug console.

The visible surface emphasizes:
- the brief
- the draft
- the final order
- Janitor resolution
- intelligence signals
- animated role flow

Internal systems like benchmarking, memory governance, and diagnostics can stay in the backend or be exposed selectively when needed.

The point is for the user to feel:
- what The Arbiter is doing
- why it made that decision
- whether the result is actually trustworthy

without forcing them to stare at raw internals all the time.

---

## Repository Structure

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

Key modules:

- [`arbiter/app/streamlit_app.py`](arbiter/app/streamlit_app.py)
  main production UI

- [`arbiter/app/app_test.py`](arbiter/app/app_test.py)
  sandbox / local experimentation surface

- [`arbiter/core/orchestrator.py`](arbiter/core/orchestrator.py)
  high-level control flow

- [`arbiter/core/iteration_engine.py`](arbiter/core/iteration_engine.py)
  main intelligence loop

- [`arbiter/core/preflight.py`](arbiter/core/preflight.py)
  deterministic structural validation

- [`arbiter/core/final_verifier.py`](arbiter/core/final_verifier.py)
  grounded post-generation verification layer

- [`arbiter/infra/model_selector.py`](arbiter/infra/model_selector.py)
  provider lock, role overrides, fallback, cooldown logic

- [`arbiter/infra/memory_store.py`](arbiter/infra/memory_store.py)
  persistent run memory, lifecycle control, project notes, retrieval

- [`arbiter/infra/benchmark_store.py`](arbiter/infra/benchmark_store.py)
  run-level metrics and evaluation history

- [`arbiter/prompts/registry.py`](arbiter/prompts/registry.py)
  task-aware prompt construction and memory-aware Architect context

---

## Installation

Create and activate your environment, then install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Set your provider keys in `.env` as needed:

```env
GROQ_API_KEY=...
OPENAI_API_KEY=...
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=...
```

You do not need all providers at once.

---

## Running The App

Main app:

```bash
python3 -m streamlit run arbiter/app/streamlit_app.py
```

Sandbox / local testing:

```bash
python3 -m streamlit run arbiter/app/app_test.py
```

---

## Recommended Usage Modes

### Starter - Free Stable
Best default for most users:
- Groq-first
- stable
- cheap
- predictable

### Cheap Test - Groq Lite
Good for quick rough iterations and lower-cost experimentation.

### Software Builder
Best for technical build tasks with stronger review pressure.

### Strategy & Writing
Better suited for structured reasoning, positioning, writing, and planning.

### Business Operator
Good fit for workflows, SOPs, service design, and operating systems.

### Premium Claude Cross-Check
For harder tasks where you want stronger model diversity and higher-end output quality.

---

## What The Arbiter Is Not

The Arbiter is not:
- a guaranteed-truth engine
- a perfect autonomous system
- a replacement for execution, testing, or human judgment in high-stakes cases

It is a system for producing **better, more challenge-tested, more interpretable outputs** than a single unchallenged model response.

That distinction matters.

---

## Current Status

The project is already far beyond “prompt demo” territory.

It currently has:
- a differentiated product identity
- a real multi-agent loop
- trust-aware memory
- verification-aware scoring
- benchmark instrumentation
- UI designed as a usable workspace

The next frontier is continued hardening:
- stronger domain-specific validators
- richer benchmark comparisons
- deeper execution verification
- more long-term calibration from real usage

In other words:
The Arbiter is already a serious system, and it is still getting sharper.

---

## Built By

**Luca Crăciun**  
The Arbiter product build

- GitHub: [github.com/lucaomul](https://github.com/lucaomul)
- LinkedIn: [gabriel-luca-craciun-25ba95295](https://www.linkedin.com/in/gabriel-luca-craciun-25ba95295)

---

## License

Add the license that matches your intended distribution model.
