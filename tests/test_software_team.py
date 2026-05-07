from arbiter.config.settings import SETTINGS
from arbiter.core.software_team import SoftwareTeamCoordinator, SoftwareTeamPlanner
from arbiter.core.team_router import TeamRouter
from arbiter.models.state import ArbiterState
from arbiter.models.team import SpecialistPlan, TeamRoutingDecision


def _complex_full_stack_task() -> str:
    return (
        "Design a production-ready full-stack platform for managing customer support operations. "
        "It needs a responsive frontend, a Python backend API, role-based auth, a SQL database "
        "schema, Docker deployment, CI/CD, monitoring, caching, and websocket notifications. "
        "Include architecture, scaling considerations, testing strategy, and how the services "
        "integrate across the system."
    )


def _complex_multi_tenant_saas_task() -> str:
    return (
        "Design a multi-tenant SaaS admin dashboard for managing customer workspaces, billing, roles, "
        "audit logs, and support tickets. Cover the React frontend, Python API layer, SQL persistence "
        "model, auth and security model, background jobs, Docker deployment, observability, and how "
        "CI/CD should validate the system before release."
    )


def test_team_router_does_not_activate_for_small_software_task(monkeypatch):
    monkeypatch.setattr(SETTINGS, "software_team_enabled", True)
    monkeypatch.setattr(SETTINGS, "software_team_min_complexity_score", 3)

    decision = TeamRouter().route(
        "Software & IT",
        "Write a Python function that normalizes email addresses.",
    )

    assert decision.use_team is False
    assert decision.suggested_roles == []
    assert decision.complexity_score < 3
    assert decision.active is False
    assert decision.complexity_level == "standard"
    assert decision.requires_confirmation is False


def test_team_router_activates_for_complex_full_stack_task(monkeypatch):
    monkeypatch.setattr(SETTINGS, "software_team_enabled", True)
    monkeypatch.setattr(SETTINGS, "software_team_min_complexity_score", 3)

    decision = TeamRouter().route("Software & IT", _complex_full_stack_task())

    assert decision.use_team is True
    assert decision.complexity_score >= 3
    assert "backend" in decision.detected_domains
    assert "frontend" in decision.detected_domains
    assert "database" in decision.detected_domains
    assert "python" in decision.detected_technologies
    assert decision.signal_reasons
    assert "devops" not in decision.detected_domains
    assert "Lead Software Architect" in decision.suggested_roles
    assert "Backend Architect" in decision.suggested_roles
    assert "Frontend Architect" in decision.suggested_roles
    assert "Database Architect" in decision.suggested_roles
    assert "DevOps & Reliability Architect" in decision.suggested_roles
    assert "Security Architect" in decision.suggested_roles
    assert "QA/Test Architect" in decision.suggested_roles
    assert decision.complexity_level in {"complex", "very_complex"}
    assert decision.estimated_cost_multiplier > 1.0
    assert decision.estimated_latency_multiplier > 1.0
    assert decision.requires_confirmation is True


def test_software_team_planner_keeps_v1_shape_via_properties(monkeypatch):
    monkeypatch.setattr(SETTINGS, "software_team_enabled", True)
    monkeypatch.setattr(SETTINGS, "software_team_min_complexity_score", 3)

    plan = SoftwareTeamPlanner().assess("Software & IT", _complex_full_stack_task())

    assert plan.active is True
    assert "Backend Architect" in plan.specialists
    assert isinstance(plan.signals, list)
    assert plan.summary


def test_team_router_activates_for_broad_multi_surface_saas_task(monkeypatch):
    monkeypatch.setattr(SETTINGS, "software_team_enabled", True)
    monkeypatch.setattr(SETTINGS, "software_team_min_complexity_score", 3)

    decision = TeamRouter().route("Software & IT", _complex_multi_tenant_saas_task())

    assert decision.use_team is True
    assert decision.complexity_score >= 3
    assert "frontend" in decision.detected_domains
    assert "database" in decision.detected_domains
    assert "auth" in decision.detected_domains
    assert "DevOps & Reliability Architect" in decision.suggested_roles


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run_software_specialist(self, role, task, history="", context=None, selection_role="Architect", model_candidates=None):
        self.calls.append({"role": role, "model_candidates": list(model_candidates or [])})
        chosen_model = (model_candidates or [f"demo-{role.lower().replace(' ', '-')}"])[0]
        if role == "Lead Software Architect":
            return (
                SpecialistPlan(
                    role=role,
                    scope="Define the shared system blueprint and delivery sequence.",
                    recommendations=["Split the build into backend, frontend, database, and operations workstreams."],
                    risks=["Cross-team contract drift."],
                    dependencies=["Each specialist must honor the published API contracts."],
                    interfaces=["Shared REST API and schema contracts."],
                    implementation_steps=["Define the service boundaries and contracts first."],
                    open_questions=["Should notifications be synchronous or queued?"],
                    implementation_artifact="File map: api/, web/, db/, deploy/.",
                ),
                chosen_model,
            )
        if role == "Backend Architect":
            raise RuntimeError("backend provider outage")
        if role == "Frontend Architect":
            return (
                SpecialistPlan(
                    role=role,
                    scope="Design the operator dashboard and interaction flow.",
                    recommendations=["Use a route-driven admin UI with clear status panels."],
                    risks=["State mismatch if API contracts drift."],
                    dependencies=["Stable backend contracts for dashboard and auth flows."],
                    interfaces=["GET /tickets, POST /tickets/{id}/assign"],
                    implementation_steps=["Model the admin shell and primary ticket views."],
                    open_questions=[],
                    implementation_artifact="<main id='dashboard-shell'></main>",
                ),
                chosen_model,
            )
        return (
            SpecialistPlan(
                role=role,
                scope=f"{role} covers its specialist lane.",
                recommendations=[f"{role} recommends a focused implementation path."],
                risks=[f"{role} has one known delivery risk."],
                dependencies=[f"{role} depends on the shared architecture contract."],
                interfaces=[f"{role} publishes a stable interface description."],
                implementation_steps=[f"{role} starts after the shared contracts are agreed."],
                open_questions=[],
                    implementation_artifact="",
            ),
            chosen_model,
        )

    @staticmethod
    def latest_call_cost(role, fallback_model=""):
        return 0.0

    @staticmethod
    def latest_call_metadata(role):
        return {}


def test_software_team_handles_specialist_failure_gracefully(monkeypatch):
    monkeypatch.setattr(SETTINGS, "software_team_parallel", True)
    monkeypatch.setattr(SETTINGS, "software_team_timeout_seconds", 2)

    runner = FakeRunner()
    coordinator = SoftwareTeamCoordinator(runner)
    decision = TeamRoutingDecision(
        use_team=True,
        reason="Complex full-stack request.",
        detected_domains=["backend", "frontend", "database", "auth", "docker"],
        suggested_roles=[
            "Lead Software Architect",
            "Backend Architect",
            "Frontend Architect",
            "Database Architect",
            "DevOps & Reliability Architect",
        ],
        complexity_score=4,
    )
    monkeypatch.setattr(coordinator, "route", lambda task_mode, user_input: decision)

    state = ArbiterState(user_input=_complex_full_stack_task(), task_mode="Software & IT")
    state.current_task = state.user_input
    state.software_team_profile = "dream"

    solution, model, metadata = coordinator.build_solution(
        state=state,
        history="",
        context={"force_quality": True},
        run_id="run-team-1",
        iteration=1,
    )

    assert model == "gpt-4o"
    assert metadata["use_team"] is True
    assert metadata["selected_profile"] == "dream"
    assert metadata["selected_profile_label"] == "Dream Team"
    assert metadata["roles"][0] == "Lead Software Architect"
    assert metadata["failure_reasons"]["Backend Architect"] == "backend provider outage"
    assert any(item["role"] == "Backend Architect" for item in metadata["specialist_summaries"])
    assert metadata["role_models"]["Lead Software Architect"] == "gpt-4o"
    assert "Software Architect Team Summary" in solution
    assert "Frontend Architect" in solution
    assert "Implementation Artifact:" in solution
    lead_call = next(item for item in runner.calls if item["role"] == "Lead Software Architect")
    assert lead_call["model_candidates"][0] == "gpt-4o"


def test_team_router_exposes_profile_options(monkeypatch):
    monkeypatch.setattr(SETTINGS, "software_team_enabled", True)
    monkeypatch.setattr(SETTINGS, "software_team_min_complexity_score", 3)

    decision = TeamRouter().route("Software & IT", _complex_full_stack_task())

    assert decision.profile_options["efficient"]["label"] == "Efficient Team"
    assert decision.profile_options["dream"]["label"] == "Dream Team"
    assert decision.recommended_profile in {"efficient", "dream"}
    assert decision.profile_options["dream"]["role_models"]["Lead Software Architect"] == "gpt-4o"
