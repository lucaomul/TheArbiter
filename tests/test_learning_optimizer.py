from arbiter.core.learning.optimizer import LearningOptimizer
from arbiter.models.state import ArbiterState


def make_state(*, stable_mode=False, tech=8, logic=8, rewrite_mode=False):
    state = ArbiterState(user_input="test", stable_mode=stable_mode)
    state.rewrite_mode = rewrite_mode
    state.iteration_history = [
        {
            "tech": tech,
            "logic": logic,
            "tech_critique": "Fix the broken subsystem",
            "logic_critique": "Tighten the argument",
        }
    ]
    state.last_tech_score = tech
    return state


def test_optimizer_returns_stable_mode_hint():
    result = LearningOptimizer().optimize(make_state(stable_mode=True, tech=5, logic=8))

    assert result["mode"] == "stable"
    assert result["focus"] == "tech_repair"


def test_optimizer_returns_logic_repair_when_logic_is_low():
    result = LearningOptimizer().optimize(make_state(stable_mode=False, tech=7, logic=6))

    assert result["focus"] == "logic_repair"


def test_optimizer_returns_polish_for_high_scores():
    result = LearningOptimizer().optimize(make_state(stable_mode=False, tech=8, logic=8))

    assert result["focus"] == "polish"


def test_optimizer_returns_rewrite_mode_when_enabled():
    state = make_state(stable_mode=False, tech=5, logic=7, rewrite_mode=True)
    state.tech_stall_count = 1

    result = LearningOptimizer().optimize(state)

    assert result["focus"] == "rewrite_mode"
    assert result["architect_model"] == "gpt-4o"


def test_optimizer_uses_configured_quality_model(monkeypatch):
    class FakeRegistry:
        @staticmethod
        def resolve_model_id(model_id: str) -> str:
            return "architect-premium"

        @staticmethod
        def is_selectable(model_id: str, role: str) -> bool:
            return model_id == "architect-premium" and role == "Architect"

        @staticmethod
        def recommended_replacement(model_id: str, role: str) -> str:
            return ""

        @staticmethod
        def candidates_for_role(role: str):
            return []

    monkeypatch.setattr("arbiter.core.learning.optimizer.get_plugin_registry", lambda: FakeRegistry())
    monkeypatch.setattr("arbiter.core.learning.optimizer.SETTINGS.architect_model_quality", "alias:premium")

    state = make_state(stable_mode=False, tech=5, logic=7, rewrite_mode=True)
    state.tech_stall_count = 1

    result = LearningOptimizer().optimize(state)

    assert result["architect_model"] == "architect-premium"
