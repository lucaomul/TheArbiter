from dataclasses import dataclass

from arbiter.models.state import ArbiterState, IterationRecord


@dataclass
class ExtendedIterationRecord(IterationRecord):
    extra_marker: str = "extended"


def make_record(**overrides) -> IterationRecord:
    base = {
        "iter": 1,
        "tech": 7,
        "logic": 8,
        "avg": 7.5,
        "tech_critique": "Tech critique",
        "logic_critique": "Logic critique",
        "fix": "Fix it",
        "solution": "Solution body",
    }
    base.update(overrides)
    return IterationRecord(**base)


def test_add_iteration_serializes_all_dataclass_fields():
    state = ArbiterState(user_input="test")
    record = ExtendedIterationRecord(
        iter=1,
        tech=8,
        logic=8,
        avg=8.0,
        tech_critique="Tech critique",
        logic_critique="Logic critique",
        fix="Fix it",
        solution="Solution body",
    )

    state.add_iteration(record)

    assert state.iteration_history[-1]["extra_marker"] == "extended"
    assert state.iteration_history[-1]["raw_avg_score"] == 8.0


def test_track_cost_accumulates_total_and_role():
    state = ArbiterState(user_input="test")

    state.track_cost("Architect", 0.2)
    state.track_cost("Architect", 0.3)

    assert state.costs["Architect"] == 0.5
    assert state.costs["Total"] == 0.5


def test_update_best_prefers_verified_iteration_bonus():
    state = ArbiterState(user_input="test")
    state.update_best(8.0, "first", {"iter": 1, "tech": 8, "logic": 8, "avg": 8.0, "verification_status": "CAUTION"})
    state.update_best(7.8, "second", {"iter": 2, "tech": 8, "logic": 8, "avg": 7.8, "verification_status": "VERIFIED"})

    assert state.best_solution == "second"
    assert state.best_iteration["iter"] == 2


def test_add_iteration_updates_rewrite_mode_on_repeated_low_tech():
    state = ArbiterState(user_input="test")

    state.add_iteration(make_record(iter=1, tech=5, logic=7, avg=6.0))
    state.add_iteration(make_record(iter=2, tech=5, logic=7, avg=6.0))

    assert state.rewrite_mode is True
    assert state.tech_stall_count >= 1
