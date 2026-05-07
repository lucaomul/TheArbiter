# The Arbiter Architecture

## System Purpose

The Arbiter is a governed multi-agent loop for tasks where answer quality matters more than one-shot speed. It does not try to be a general-purpose arbitrary agent graph builder. Its core product idea is narrower and stronger:

- audit the brief before spending critic budget
- draft with a primary agent
- critique in parallel
- compress disagreement into a repair brief
- verify the result deterministically
- decide trust and readiness separately from raw fluency

## End-to-End Pipeline

```text
User Brief
   |
   v
Evidence ingestion + retrieval (optional)
   |
   v
Auditor
   |---- needs clarification ----> User clarification -> Auditor
   |
   v
Architect
   |
   v
Preflight
   |---- fail ----> diagnostic stop / corrective guidance
   |
   v
Tech Critic --------\
                      > Janitor -> retry brief
Logic Critic -------/
   |
   v
Final Verifier
   |
   v
Score calibration + readiness decision
   |
   +--> retry loop
   |
   +--> final result
```

## Role Responsibilities

### Auditor
- checks whether the request is clear enough to proceed
- asks bounded clarification questions when the brief is underspecified
- is mode-aware, so a writing task is not audited like a software ticket

### Architect
- produces the primary deliverable
- follows task-mode guidance and delivery contracts
- is the main target of the retry loop

### Dynamic Software Architect Team
For larger `Software & IT` tasks, the Architect step can expand into a specialist planning pod instead of staying single-threaded.

Activation is additive and gated:
- task mode must be `Software & IT`
- the router must detect enough complexity signals
- simple coding tasks stay on the normal Architect path

Core specialist roles:
- `Lead Software Architect`
- `Backend Architect`
- `Frontend Architect`
- `Database Architect`
- `DevOps & Reliability Architect`

Optional specialist roles:
- `Security Architect`
- `QA/Test Architect`
- `Integration Architect`
- `Performance Architect`

The flow is:
1. team router inspects the brief
2. if the task is large enough, the UI can require explicit user approval before the expanded team path is used
3. lead specialist publishes a shared architecture blueprint
4. other specialists work in parallel when safe
5. the plans are synthesized into one implementation-oriented software package
6. the existing critics, Janitor, verifier, and stopping logic stay unchanged

This improves large software-task quality by giving the downstream review loop clearer subsystem boundaries, better handoffs, and more explicit implementation order.

### Tech Critic
- checks implementation rigor, operational feasibility, execution quality, and technical defects

### Logic Critic
- checks reasoning quality, scope coverage, coherence, tradeoffs, and structural completeness

### Janitor
- compresses the critic disagreement into a repair-oriented retry brief
- keeps the next round focused instead of feeding raw review noise back to the Architect

### Final Verifier
- applies deterministic validation where possible
- calibrates score honesty
- helps separate "sounds good" from "looks safe enough to trust"

## Data Flow

### Evidence layer
The input path can now carry supporting materials instead of only raw prompt text.

Supported evidence inputs:
- uploaded files such as PDF, DOCX, TXT, Markdown, JSON, CSV, and code/text documents
- URL-based reference material

Evidence flow:
1. extract readable text from each source
2. chunk large sources into smaller passages
3. rank chunks against the active task with a lightweight local retrieval pass
4. inject the top excerpts into the Architect-facing task payload
5. surface source names, warnings, and retrieved snippets in the UI/API
6. use attached-source metadata during verification for source/quote-sensitive tasks

### 1. Intake state
The orchestrator creates an `ArbiterState` object that carries:
- user input
- task mode
- optional evidence bundle
- selected models
- iteration history
- costs
- best solution metadata
- adaptive control signals

### 2. Iteration records
Each round creates an `IterationRecord` that captures:
- critic scores
- critic critiques
- Janitor repair guidance
- verification outputs
- readiness signals
- solution snapshot

Those records are serialized into `iteration_history` and are now stored via dataclass-driven serialization instead of manual field mapping.

### 3. Verification chain
Verification contributes deterministic pressure after the critics score the round.

Inputs include:
- preflight outcomes
- confirmed defects
- output modality checks
- code / JSON / SQL validation where appropriate

Outputs include:
- verification status
- verification score contribution
- calibrated score
- readiness state

## Score Model

The Arbiter intentionally distinguishes:

- `Critic Average`
  - raw weighted score from Tech Critic and Logic Critic
- `Final Verified Score`
  - final round score after verification pressure
- `Verification Status`
  - `VERIFIED`, `CAUTION`, `FAILED`, `BLOCKED`
- `Readiness`
  - `READY`, `CLOSE`, `NEEDS REVIEW`, `BLOCKED`

This distinction is central to the system. The critics can like a result while the verifier still marks it cautionary.

## Memory Lifecycle

The native memory store is the authoritative long-term store. It records:
- task text and task mode
- issue tokens and repair contracts
- score and verification metadata
- memory status and lifecycle
- project notes

Current lifecycle states:
- `active`
- `caution`
- `conflicted`
- `obsolete`

Memory writes are now append-only during a session for new entries, with explicit `flush()` support for compacting and persisting updated lifecycle/versioning state.

## Persistence Layers

### Native memory
- JSONL-backed
- always available
- supports retrieval, versioning, and project notes

### Optional Chroma
- adds semantic retrieval on top of native memory
- remains optional and gracefully absent when not installed

### Optional SQL persistence
- SQLAlchemy 2.0 + Alembic scaffold
- SQLite by default
- PostgreSQL-compatible target design
- stores runs, iterations, and memory entries

## Service Surfaces

### Streamlit workspace
- main product UI
- optimized for interactive runs, oversight, and iteration review

### Analytics dashboard
- separate Streamlit surface
- explores runs, score trends, benchmarks, and memory signals

### FastAPI layer
- exposes health, models, and run execution routes
- supports production-safe auth behavior

## Observability

Current observability includes:
- structured logging
- run/iteration context
- model/provider metadata
- latency
- token/cost aggregation
- per-run and per-agent usage tracking

## Design Boundaries

The Arbiter deliberately does not try to:
- be an unrestricted autonomous agent swarm
- hide uncertainty behind a single magic score
- treat every domain like a software task
- assume optional dependencies are always present

Its product value comes from governed quality loops, not from pretending every task is safe to automate blindly.
