from arbiter.config.settings import SETTINGS
from arbiter.core.iteration_engine import IterationEngine
from arbiter.models.state import ArbiterState


class FakeRegistry:
    def build_architect_history(self, _state, manual_override=""):
        return f"manual_override={manual_override}"


class FakeDecisionLog:
    @staticmethod
    def to_dict_list():
        return []


class FakeRunner:
    def __init__(self):
        self.current_iteration = 0
        self.decision_log = FakeDecisionLog()

    def run_architect(self, task, history="", context=None):
        return (
            """```python
def build_schedule(staff):
    assignments = []
    for member in staff:
        assignments.append({"name": member, "shift": "day"})
    return assignments
```""",
            "demo-architect",
        )

    def run_specialist(self, role, task, history="", context=None, selection_role="Architect"):
        specialist_outputs = {
            "Software Architect": "Objective\nShip a staffing dashboard.\n\nFile Map\n- app.py\n- templates/index.html",
        }
        return specialist_outputs.get(role, "specialist output"), f"demo-{role.lower().replace(' ', '-')}"

    def run_software_specialist(self, role, task, history="", context=None, selection_role="Architect", model_candidates=None):
        from arbiter.models.team import SpecialistPlan

        specialist_outputs = {
            "Lead Software Architect": SpecialistPlan(
                role=role,
                scope="Define the staffing dashboard blueprint.",
                recommendations=["Split the build into backend, frontend, database, and operations workstreams."],
                risks=["Subsystem contracts could drift."],
                dependencies=["Shared API contract."],
                interfaces=["REST endpoints for schedules and assignments."],
                implementation_steps=["Publish the shared delivery blueprint first."],
                open_questions=[],
                implementation_artifact="File map: api/, web/, db/, deploy/.",
            ),
            "Backend Architect": SpecialistPlan(
                role=role,
                scope="Scheduler API and business rules.",
                recommendations=["Implement the schedule generator as a service layer."],
                risks=["Validation gaps could allow invalid shift assignments."],
                dependencies=["Shared schema contract."],
                interfaces=["POST /schedules, GET /schedules/{id}"],
                implementation_steps=["Implement schedule generation helpers and validation rules."],
                open_questions=[],
                implementation_artifact="def create_schedule_service():\n    return 'service'",
            ),
            "Frontend Architect": SpecialistPlan(
                role=role,
                scope="Dashboard UI and operator flow.",
                recommendations=["Use a simple responsive admin shell with schedule status cards."],
                risks=["UI could drift from backend field names."],
                dependencies=["Stable response payloads from the backend."],
                interfaces=["Schedule dashboard, assignment form."],
                implementation_steps=["Build the dashboard shell and status views."],
                open_questions=[],
                implementation_artifact="<div id='dashboard'></div>",
            ),
            "Database Architect": SpecialistPlan(
                role=role,
                scope="Persistence schema and data integrity.",
                recommendations=["Create schedule and assignment tables with clear foreign keys."],
                risks=["Loose constraints could allow inconsistent staff assignments."],
                dependencies=["Backend validation rules."],
                interfaces=["schedules, assignments"],
                implementation_steps=["Design normalized schedule tables and migration order."],
                open_questions=[],
                implementation_artifact="CREATE TABLE schedules (id INTEGER PRIMARY KEY);",
            ),
            "DevOps & Reliability Architect": SpecialistPlan(
                role=role,
                scope="Runtime, deployment, and observability.",
                recommendations=["Containerize the stack and add health/metrics endpoints."],
                risks=["Runtime drift across environments."],
                dependencies=["Stable build and env var contracts."],
                interfaces=["Docker Compose and health checks."],
                implementation_steps=["Define local and deployment runtime expectations."],
                open_questions=[],
                implementation_artifact="services:\n  api:\n    healthcheck: enabled",
            ),
        }
        chosen_model = (model_candidates or [f"demo-{role.lower().replace(' ', '-')}"])[0]
        return specialist_outputs[role], chosen_model

    def run_tech_critic(self, solution, context=None):
        return (
            {
                "score": 8,
                "critique": "Implementation is coherent.",
                "fix_suggestion": "Tighten validation.",
                "confirmed_defects": [],
                "issues": [],
                "repair_contract": ["Add edge-case validation."],
            },
            "demo-tech",
        )

    def run_logic_critic(self, solution, context=None, extra_instruction=""):
        return (
            {
                "score": 8,
                "critique": "Reasoning is consistent.",
                "fix_suggestion": "Clarify constraints.",
                "confirmed_defects": [],
                "issues": [],
                "repair_contract": ["Clarify the fallback scheduling path."],
            },
            "demo-logic",
        )

    def run_janitor(self, payload, context=None):
        return (
            {
                "summary": "Mostly clean result.",
                "primary_subsystem": "scheduler",
                "resolved": ["Core flow is consistent."],
                "pending": ["Validation can be stronger."],
                "regressed": [],
                "preserve": ["Keep the simple assignment loop."],
                "repair_brief": ["Add better validation."],
            },
            "demo-janitor",
        )

    def run_critic_debate(self, solution, tech_result, logic_result):
        return (
            {
                "tech_focus": "validation",
                "logic_focus": "constraints",
                "combined_fix": "Strengthen validation and clarify constraints.",
            },
            "demo-debate",
        )

    @staticmethod
    def latest_call_cost(role, fallback_model=""):
        return 0.0

    @staticmethod
    def latest_call_metadata(role):
        return {}

    @staticmethod
    def set_call_metadata(role, metadata):
        return None


class FakeMemory:
    @staticmethod
    def record_iteration(**kwargs):
        return {
            "memory_status": "ACCEPT",
            "consensus_score": 0.8,
            "memory_reasons": ["Stored for reuse."],
            "related_memory_ids": [],
        }

    @staticmethod
    def stats():
        return {"count": 0, "memory_lifecycle": {}}


class FakeBenchmarks:
    @staticmethod
    def record_run(**kwargs):
        return None

    @staticmethod
    def stats():
        return {"count": 0}

    @staticmethod
    def by_task_mode():
        return {}

    @staticmethod
    def by_strategy():
        return {}

    @staticmethod
    def by_case():
        return {}

    @staticmethod
    def recent_runs(limit):
        return []


def test_iteration_engine_executes_full_mocked_run(monkeypatch):
    monkeypatch.setattr(SETTINGS, "critic_debate_enabled", False)
    monkeypatch.setattr("arbiter.core.iteration_engine.save_memory_entry_sync", lambda entry: None)
    monkeypatch.setattr("arbiter.core.iteration_engine.save_iteration_sync", lambda run_id, record: None)
    monkeypatch.setattr("arbiter.core.iteration_engine.save_run_sync", lambda payload: payload["id"])

    engine = IterationEngine(
        registry=FakeRegistry(),
        auto_mode=False,
        target_score=8.0,
        max_iterations=2,
        stable_mode=False,
    )
    engine.runner = FakeRunner()
    engine.memory = FakeMemory()
    engine.benchmarks = FakeBenchmarks()

    state = ArbiterState(user_input="Build a scheduler", task_mode="Software & IT")
    state.current_task = "Build a Python employee scheduler."

    result = engine.execute(state)

    assert result.iteration_count == 1
    assert result.best_score >= 1.0
    assert len(result.iteration_history) == 1
    assert result.iteration_history[0]["tech"] == 8
    assert result.iteration_history[0]["logic"] == 8
    assert result.debug_info["stop_reason"] == "Manual mode — single cycle."


def test_iteration_engine_activates_software_team_for_large_task(monkeypatch):
    monkeypatch.setattr(SETTINGS, "critic_debate_enabled", False)
    monkeypatch.setattr(SETTINGS, "software_team_enabled", True)
    monkeypatch.setattr(SETTINGS, "software_team_min_complexity_score", 3)
    monkeypatch.setattr("arbiter.core.iteration_engine.save_memory_entry_sync", lambda entry: None)
    monkeypatch.setattr("arbiter.core.iteration_engine.save_iteration_sync", lambda run_id, record: None)
    monkeypatch.setattr("arbiter.core.iteration_engine.save_run_sync", lambda payload: payload["id"])

    engine = IterationEngine(
        registry=FakeRegistry(),
        auto_mode=False,
        target_score=8.0,
        max_iterations=2,
        stable_mode=False,
    )
    engine.runner = FakeRunner()
    engine.memory = FakeMemory()
    engine.benchmarks = FakeBenchmarks()

    state = ArbiterState(
        user_input=(
            "Build a production-ready full-stack staffing dashboard with a Python API, responsive frontend, "
            "SQL database, Docker deployment, CI/CD, tests, monitoring, websocket updates, and auth for managers."
        ),
        task_mode="Software & IT",
    )
    state.current_task = state.user_input
    state.software_team_user_approved = True
    state.software_team_profile = "dream"

    result = engine.execute(state)

    assert result.iteration_count == 1
    assert result.iteration_history[0]["software_team_active"] is True
    assert result.iteration_history[0]["software_team_profile"] == "dream"
    assert "Frontend Architect" in result.iteration_history[0]["software_team_specialists"]
    assert "Database Architect" in result.iteration_history[0]["software_team_specialists"]
    assert result.debug_info["software_team"]["use_team"] is True
    assert result.debug_info["software_team"]["selected_profile"] == "dream"
