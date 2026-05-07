import time

from arbiter.config.settings import SETTINGS
from arbiter.core.iteration_engine import IterationEngine
from arbiter.models.team import TeamRoutingDecision
from arbiter.models.state import ArbiterState


class FakeRegistry:
    pass


def _critic_result(score: int, issue: str) -> dict:
    return {
        "score": score,
        "critique": issue,
        "confirmed_defects": [issue],
        "issues": [issue],
        "fix_suggestion": f"Fix {issue}",
        "repair_contract": [f"Repair {issue}"],
    }


def test_critic_rerun_requires_overlap_and_same_score_band(monkeypatch):
    monkeypatch.setattr(SETTINGS, "critic_redundancy_score_band_check", True)

    assert IterationEngine._should_trigger_critic_rerun(
        _critic_result(8, "Missing validation"),
        _critic_result(8, "Missing validation"),
        overlap=1.0,
    )
    assert not IterationEngine._should_trigger_critic_rerun(
        _critic_result(8, "Missing validation"),
        _critic_result(4, "Missing validation"),
        overlap=1.0,
    )
    assert not IterationEngine._should_trigger_critic_rerun(
        _critic_result(8, "Missing validation"),
        _critic_result(8, "Different workflow"),
        overlap=0.3,
    )


def test_critic_rerun_band_check_can_be_disabled(monkeypatch):
    monkeypatch.setattr(SETTINGS, "critic_redundancy_score_band_check", False)

    assert IterationEngine._should_trigger_critic_rerun(
        _critic_result(8, "Missing validation"),
        _critic_result(4, "Missing validation"),
        overlap=1.0,
    )


def test_parallel_critics_return_results_even_when_completion_order_differs(monkeypatch):
    class FakeRunner:
        def __init__(self):
            self._metadata = {
                "Tech Critic": {"latency_ms": 50.0},
                "Logic Critic": {"latency_ms": 10.0},
            }

        def run_tech_critic(self, proposal, context):
            time.sleep(0.05)
            return _critic_result(8, "Missing validation"), "tech-model"

        def run_logic_critic(self, proposal, context):
            time.sleep(0.01)
            return _critic_result(7, "Broken fallback"), "logic-model"

        def set_call_metadata(self, role, metadata):
            self._metadata[role] = dict(metadata)

        def latest_call_metadata(self, role):
            return dict(self._metadata.get(role, {}))

    monkeypatch.setattr(SETTINGS, "parallel_critics", True)
    monkeypatch.setattr(SETTINGS, "critic_timeout_seconds", 2)

    engine = IterationEngine(FakeRegistry(), auto_mode=False)
    engine.runner = FakeRunner()

    t_res, t_model, l_res, l_model = engine._run_initial_critics(
        proposal="demo",
        context={},
        run_id="run-test",
        iteration=1,
    )

    assert t_model == "tech-model"
    assert l_model == "logic-model"
    assert t_res["score"] == 8
    assert l_res["score"] == 7


def test_janitor_payload_includes_software_team_context_when_active():
    state = ArbiterState(user_input="Build a platform", task_mode="Software & IT")
    state.software_team_plan = {
        "use_team": True,
        "detected_domains": ["backend", "frontend", "database"],
        "roles": ["Lead Software Architect", "Backend Architect", "Frontend Architect"],
        "architecture_summary": "Split the build into clear backend, frontend, and persistence lanes.",
        "cross_team_handoffs": [
            "Backend Architect: publish the REST contract before frontend integration.",
            "Frontend Architect: align field names with backend payloads.",
        ],
        "main_risks": ["API drift could break the UI."],
        "specialist_summaries": [
            {"role": "Backend Architect", "top_recommendation": "Define the service contract first."},
            {"role": "Frontend Architect", "top_recommendation": "Use the shared contract for UI state."},
        ],
    }

    payload = IterationEngine._build_janitor_payload(
        state=state,
        proposal="demo solution",
        preflight_issues=["Missing validation"],
        t_res=_critic_result(6, "Missing validation"),
        l_res=_critic_result(7, "Broken fallback flow"),
    )

    assert "SOFTWARE TEAM DOMAINS" in payload
    assert "SOFTWARE TEAM ROLES" in payload
    assert "CROSS-TEAM HANDOFFS" in payload
    assert "SPECIALIST SNAPSHOTS" in payload


def test_complex_team_recommendation_requires_explicit_approval():
    engine = IterationEngine(FakeRegistry(), auto_mode=False)
    state = ArbiterState(user_input="Build a full-stack platform", task_mode="Software & IT")
    state.software_team_user_approved = False

    engine.software_team.route = lambda task_mode, user_input: TeamRoutingDecision(
        use_team=True,
        reason="Complex software task detected.",
        detected_domains=["backend", "frontend", "database"],
        detected_technologies=["python", "react", "sql"],
        signal_reasons=["3 software domains", "multiple languages/frameworks"],
        suggested_roles=["Lead Software Architect", "Backend Architect", "Frontend Architect"],
        complexity_score=3,
        complexity_level="complex",
        estimated_team_size=3,
        estimated_cost_multiplier=1.4,
        estimated_latency_multiplier=1.2,
        requires_confirmation=True,
    )

    plan = engine._ensure_software_team_plan(state)

    assert plan["recommended"] is True
    assert plan["approval_missing"] is True
    assert plan["use_team"] is False
    assert plan["user_approved"] is False
    assert "normal architect path" in plan["reason"].lower()
