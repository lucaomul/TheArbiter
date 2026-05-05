# The Arbiter — File Structure & Setup

## Folder Structure

```
arbiter/
│
├── app/
│   └── streamlit_app.py          ← UI only, zero business logic
│
├── core/
│   ├── orchestrator.py           ← Entry point, flow controller
│   ├── iteration_engine.py       ← Main debate loop
│   ├── agent_runner.py           ← Executes agents with model selection
│   ├── scoring.py                ← Converts critic output to numeric score
│   ├── stopping.py               ← Stop conditions (max iter, plateau, target)
│   └── learning/
│       └── optimizer.py          ← Analyzes history, returns recommendations
│
├── agents/
│   └── base_agent.py             ← BaseAgent + all agent classes
│                                   (ArchitectAgent, TechCriticAgent,
│                                    LogicCriticAgent, AuditorAgent, RepairAgent)
│
├── prompts/
│   ├── registry.py               ← Builds prompts with task mode injection
│   └── templates/
│       └── base.py               ← All prompt strings
│
├── infra/
│   ├── llm_client.py             ← Unified OpenAI/Gemini/Groq client
│   ├── model_selector.py         ← Picks best model by perf/cost ratio
│   ├── cache.py                  ← In-memory response cache
│   └── performance_store.py      ← Tracks model scores over time
│
├── models/
│   ├── state.py                  ← ArbiterState dataclass
│   └── result.py                 ← ArbiterResult dataclass
│
└── config/
    └── settings.py               ← All settings, prices, task profiles
```

## Setup

```bash
# 1. Create venv
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install streamlit openai google-generativeai requests \
            python-dotenv fpdf2 langchain

# 3. Create .env
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
GROQ_API_KEY=...

# 4. Run
streamlit run app/streamlit_app.py
```

## Key Design Decisions

- **UI has zero logic** — `streamlit_app.py` only renders and calls `ArbiterOrchestrator`
- **Agents are stateless** — all state lives in `ArbiterState`
- **Model selection is dynamic** — `ModelSelector` picks based on `avg_performance / cost`
- **Prompts are external** — all strings in `prompts/templates/base.py`, injected via `PromptRegistry`
- **Tech repair priority** — when tech score < 6, architect receives ONE clear instruction, nothing else
- **Cache avoids duplicate calls** — same prompt hash = instant return

## Flow

```
User Input
    ↓
ArbiterOrchestrator.run()
    ↓
AuditorAgent (check clarity)
    ↓
IterationEngine.execute()
    ├── ArchitectAgent.generate()
    ├── TechCriticAgent.evaluate()
    ├── LogicCriticAgent.evaluate()
    ├── Scorer.compute()
    ├── Stopper.should_stop()
    └── LearningOptimizer.optimize()
    ↓
ArbiterResult → streamlit_app.py renders
```
