from arbiter.core.stopping import Stopper
from arbiter.models.state import ArbiterState


def make_state(iteration: int, avg_scores: list[float], last_tech: int = 7) -> ArbiterState:
    state = ArbiterState(user_input="test")
    state.iteration = iteration
    state.iteration_history = [
        {"avg": score, "verification_status": "VERIFIED", "tech": last_tech, "logic": last_tech}
        for score in avg_scores
    ]
    state.last_avg_score = avg_scores[-1] if avg_scores else 0.0
    state.last_tech_score = last_tech
    return state


def test_should_stop_on_max_iterations():
    state = make_state(iteration=3, avg_scores=[6.0, 6.2, 6.3])
    stop, reason = Stopper(max_iterations=3, auto_mode=True).should_stop(state)
    assert stop is True
    assert "Max iterations" in reason


def test_should_stop_when_target_reached_and_plateaued():
    state = make_state(iteration=2, avg_scores=[8.1, 8.2])
    stop, reason = Stopper(max_iterations=5, target_score=8.0, auto_mode=True).should_stop(state)
    assert stop is True
    assert "Minimum target" in reason


def test_should_stop_on_plateau_detection():
    state = make_state(iteration=3, avg_scores=[6.5, 6.5, 6.5])
    stopper = Stopper(max_iterations=5, target_score=8.5, plateau_rounds=3, auto_mode=True)
    stop, reason = stopper.should_stop(state)
    assert stop is True
    assert "plateau" in reason.lower()
