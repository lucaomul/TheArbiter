# The Arbiter

**A multi-agent AI orchestration system for building, challenging, repairing, and improving outputs before they reach the user.**

Arbiter is built on a simple idea:

> high-quality AI systems should not trust a single model’s first answer.

Instead of relying on one LLM to generate and hope for the best, Arbiter runs a structured decision loop across specialized roles, deterministic validation, managed memory, and controlled retries.

The result is a system that is more robust, more transparent, and more production-minded than a one-shot prompt wrapper.

---

## Why this exists

Most AI applications still behave like this:
- prompt one model
- get one answer
- hope it is correct

That approach breaks down quickly for:
- software generation
- planning with constraints
- operational workflows
- high-ambiguity business tasks
- anything where one hallucinated assumption can poison the whole result

Arbiter addresses that by introducing:
- **role separation**
- **local validation before review spend**
- **critic disagreement**
- **Janitor-led repair synthesis**
- **persistent learning across runs**
- **explicit provider and model controls**

This is the kind of architecture you build when you care about correctness, controllability, and iteration quality, not just demo output.

---

## What Arbiter does

Arbiter coordinates multiple AI roles inside a structured loop:

- `Auditor`
  checks whether the request is complete enough to build against

- `Architect`
  generates the primary solution

- `Tech Critic`
  evaluates execution quality, implementation quality, technical correctness, and reliability

- `Logic Critic`
  evaluates requirement coverage, structure, reasoning, and completeness

- `Janitor`
  consolidates all findings into a clean repair brief and becomes the default retry source

Before critics even run, Arbiter also applies:

- `Preflight validation`
  deterministic local checks that catch hard structural issues early

And across runs, it keeps:

- `Persistent memory`
  retrieval of similar failures, repair patterns, and trusted prior lessons

This creates a system that is not just “multi-model,” but **multi-stage and self-correcting**.

---

## Core capabilities

### 1. Multi-agent orchestration
Arbiter separates generation, validation, criticism, and repair into distinct roles. This reduces the chance that one model silently grades its own work.

### 2. Preflight before critic spend
For software and other structured tasks, Arbiter runs cheap deterministic checks before expensive critique rounds. Broken outputs can be blocked, repaired, or downgraded before wasting more API calls.

### 3. Janitor-led retries
Instead of feeding raw noisy critic text back into the Architect, Arbiter uses the Janitor to produce:
- what is still broken
- what should be preserved
- what changed
- what the next repair must do

This makes retries much less chaotic.

### 4. Memory with trust states
Arbiter stores more than just “history.” Each memory entry is classified and managed as:
- `active`
- `caution`
- `conflicted`
- `obsolete`

So stronger valid runs can supersede weaker ones, and low-trust diagnostic runs do not silently become “truth.”

### 5. Task-mode-aware scoring
Arbiter does not use one naive scoring formula for everything.

Examples:
- `Software & IT` weights technical quality more heavily
- `Marketing & Growth` weights logic and strategic coherence more heavily
- `Writing & Content` weighs structure and outcome fit differently than code generation

### 6. Provider and model control
Arbiter supports:
- Groq
- OpenAI
- Gemini
- Anthropic / Claude
- Ollama (sandbox/testing mode)

And it exposes:
- `Provider Lock`
- `Stable Mode`
- model presets
- manual role-by-role control

That makes it much easier to operate predictably under real cost constraints.

---

## Expected efficiency gains

Arbiter is built to improve more than answer quality. It is also designed to reduce wasted runtime, wasted review cycles, and wasted API spend.

These are **directional architecture-level estimates**, not formal benchmark claims:

- `~1 full critic round avoided`
  on structurally broken outputs when preflight catches failures before the full review loop spends more money

- `~1–2 noisy retry cycles reduced`
  in drift-heavy runs when Janitor compresses multiple reviewer signals into one repair brief

- `~lower review waste in failure-heavy workflows`
  because invalid outputs can be blocked, repaired, downgraded, or stopped before they trigger repeated cross-agent churn

- `~faster convergence on similar tasks`
  when the Architect retrieves prior repair patterns, trusted memory, and project notes instead of rebuilding context from zero every time

- `~lower experimentation cost`
  when prompt, role, and retry behavior are tested through Groq budget presets or local Ollama flows before moving into more expensive configurations

- `~higher operator trust`
  because Arbiter makes run status, reviewer confidence, provider limits, retry structure, and memory state visible instead of burying them inside a single opaque response

In practical terms, Arbiter is meant to move AI usage away from:
- repeated blind prompting
- duplicated reviewer spend
- unstable retries
- silent provider drift

and toward:
- controlled iteration
- reusable learning
- explicit repair logic
- better cost/quality predictability

---

## What makes Arbiter different

There are plenty of “AI agents” projects. Most are thin wrappers around model calls.

Arbiter is different because it treats orchestration as a systems problem:

- **It separates roles intentionally**
  generation, review, repair, and consolidation are not collapsed into one vague loop

- **It models trust explicitly**
  not every run, memory, or score is treated as equally reliable

- **It gives the user real control**
  presets for simplicity, manual role configuration for advanced use

- **It distinguishes confirmed defects from speculation**
  critics separate:
  - confirmed defects
  - risks / assumptions
  - improvements

- **It is designed for repeated use**
  memory, retrieval, provider fallback, cooldowns, and retry structure all support long-lived operation

In other words, Arbiter is closer to a **small AI reasoning platform** than a simple prompt UI.

---

## System architecture

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

Important modules:

- `arbiter/app/streamlit_app.py`
  main production UI

- `arbiter/app/app_test.py`
  sandbox UI for local and experimental testing

- `arbiter/core/orchestrator.py`
  top-level control flow

- `arbiter/core/iteration_engine.py`
  Architect → preflight → critics → Janitor → scoring loop

- `arbiter/core/preflight.py`
  deterministic validation layer

- `arbiter/infra/model_selector.py`
  model routing, provider lock, fallback, cooldown logic

- `arbiter/infra/memory_store.py`
  persistent run memory, lifecycle management, project notes, retrieval

- `arbiter/prompts/registry.py`
  task-aware prompt construction and Architect history injection

---

## End-to-end flow

1. User submits a task
2. Auditor checks whether the task is sufficiently specified
3. Architect generates a solution
4. Preflight validates the output locally
5. Tech Critic and Logic Critic review the solution
6. Janitor consolidates the outcome into a repair brief
7. Arbiter either:
   - accepts the round
   - retries using Janitor context
   - or stops honestly with a diagnostic / provider-limited state

This is not just “loop until score improves.”
It is a controlled, role-aware, memory-aware decision cycle.

---

## Memory and lightweight learning

Arbiter includes three distinct memory layers:

### Working memory
Per-run context such as:
- latest solution
- resolved / pending / regressed issues
- Janitor repair brief

### Persistent run memory
Stored locally in:
- `.arbiter_memory/memory_entries.jsonl`
- optional Chroma store in `.arbiter_memory/chroma/`

This memory captures:
- task patterns
- preflight issues
- defect patterns
- repair lessons
- trust status

### Project memory / notes
Persistent manual notes stored separately so the user can save durable guidance for future similar tasks.

This is not full model training, but it is a useful form of **retrieval-guided adaptation**:
- better reuse of successful repair patterns
- less repetition of known failure shapes
- more context-aware Architect behavior over time

---

## Presets and model strategy

Arbiter now supports named presets so users do not need to understand every provider/model tradeoff to get started.

Examples include:
- `Starter - Free Stable`
- `Cheap Test - Groq Lite`
- `Software Builder`
- `Strategy & Writing`
- `Business Operator`
- `Premium Claude Cross-Check`

For advanced users, manual role-by-role configuration is also available for:
- Architect
- Auditor
- Tech Critic
- Logic Critic
- Janitor
- Repair

This dual approach keeps the system accessible for non-experts while still giving full control to power users.

---

## Supported task modes

Arbiter is designed to work across multiple domains, not just code:

- `Software & IT`
- `Marketing & Growth`
- `Business & Operations`
- `Writing & Content`
- `Personal Planning`
- `General Problem Solving`

The system adapts prompts, validation emphasis, and score weighting based on the selected mode.

---

## Running the project

### Main app

```bash
cd /Users/lucaomul/TheArbiter
python3 -m streamlit run arbiter/app/streamlit_app.py
```

### Sandbox / experimental app

```bash
cd /Users/lucaomul/TheArbiter
python3 -m streamlit run arbiter/app/app_test.py
```

---

## Environment variables

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=...
GEMINI_API_KEY=...
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...
```

If you want to use Ollama locally:

```bash
ollama serve
```

---

## Recommended usage

### If you want the simplest reliable path
Use a preset and keep manual customization off.

### If you want cost-efficient testing
Use:
- `Cheap Test - Groq Lite`
or the sandbox with Ollama

### If you want stronger software output
Use:
- `Software Builder`

### If you want stronger strategy / writing output
Use:
- `Strategy & Writing`

### If you want full control
Enable manual mode and pick providers/models role by role.

---

## Current direction

Arbiter is evolving toward a more serious AI systems layer, with emphasis on:
- stronger retry intelligence
- better trust-aware memory
- broader domain validation
- cleaner UX
- lower-cost experimentation
- more explicit reasoning transparency

The long-term goal is not just to orchestrate models, but to make the system progressively better at knowing:
- what failed
- what improved
- what should be reused
- what should no longer be trusted

---

## Author

**Luca Crăciun**

- GitHub: [github.com/lucaomul](https://github.com/lucaomul)
- LinkedIn: [linkedin.com/in/gabriel-luca-craciun-25ba95295](https://www.linkedin.com/in/gabriel-luca-craciun-25ba95295)

---

## Final thought

Arbiter is built around a principle that more AI products should adopt:

> AI systems become more useful when they are designed to doubt, inspect, and repair themselves before asking the user to trust them.
