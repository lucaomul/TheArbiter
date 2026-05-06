from copy import deepcopy

from arbiter.config.settings import TASK_PROFILES
from arbiter.core.scoring import Scorer


def test_compute_uses_software_weights():
    score = Scorer().compute({"score": 8}, {"score": 6}, task_mode="Software & IT")
    assert score == 7.2


def test_compute_uses_marketing_weights():
    score = Scorer().compute({"score": 8}, {"score": 6}, task_mode="Marketing & Growth")
    assert score == 6.8


def test_compute_defaults_missing_scores_to_one():
    score = Scorer().compute({}, {"score": 7}, task_mode="General Problem Solving")
    assert score == 4.0


def test_compute_handles_zero_weights():
    original = deepcopy(TASK_PROFILES["General Problem Solving"])
    TASK_PROFILES["General Problem Solving"]["score_weights"] = {"tech": 0.0, "logic": 0.0}
    try:
        score = Scorer().compute({"score": 4}, {"score": 6}, task_mode="General Problem Solving")
    finally:
        TASK_PROFILES["General Problem Solving"] = original
    assert score == 5.0


def test_compute_with_breakdown_reports_dominant_gap():
    breakdown = Scorer().compute_with_breakdown(
        {"score": 4},
        {"score": 8},
        task_mode="Business & Operations",
    )
    assert breakdown["dominant_gap"] == "tech"
    assert breakdown["weighted_avg"] == 6.2
