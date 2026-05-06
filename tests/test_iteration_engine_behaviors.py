import time

from arbiter.config.settings import SETTINGS
from arbiter.core.iteration_engine import IterationEngine


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
