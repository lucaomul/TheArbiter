from arbiter.core.final_verifier import FinalVerifier


PYTHON_SOLUTION = """```python
def build_plan(name: str) -> list[str]:
    steps = []
    steps.append(f"plan for {name}")
    steps.append("validate inputs")
    steps.append("generate output")
    steps.append("review constraints")
    steps.append("finalize output")
    return steps
```"""


def test_verifier_returns_verified_for_clean_software_output():
    result = FinalVerifier().verify("Software & IT", "Build a python helper", PYTHON_SOLUTION)
    assert result.status == "VERIFIED"


def test_verifier_returns_caution_when_confirmed_defects_exist():
    result = FinalVerifier().verify(
        "Software & IT",
        "Build a python helper",
        PYTHON_SOLUTION,
        tech_confirmed_defects=["missing validation"],
    )
    assert result.status == "CAUTION"


def test_verifier_returns_failed_for_wrong_output_shape_in_marketing():
    result = FinalVerifier().verify(
        "Marketing & Growth",
        "Design a go-to-market plan for dental clinics.",
        "```python\nprint('launch')\n```",
    )
    assert result.status == "FAILED"


def test_defect_penalty_reduces_verification_score():
    result = FinalVerifier().verify(
        "Software & IT",
        "Build a python helper",
        PYTHON_SOLUTION,
        tech_confirmed_defects=["a", "b"],
        logic_confirmed_defects=["c"],
    )
    assert result.status == "CAUTION"
    assert result.score == 0.66
