import pytest

from arbiter.core.preflight import PreflightValidator


def test_placeholder_detection_flags_todo():
    result = PreflightValidator().validate("Software & IT", "build a script", "TODO: implement logic")
    assert any("Replace placeholders" in issue for issue in result.issues)


def test_scheduling_validation_flags_incomplete_logic():
    task = "Build a shift schedule generator with hours and staff requirements."
    solution = """```javascript
function assign() {
  return schedule;
}
```"""
    result = PreflightValidator().validate("Software & IT", task, solution)
    assert any("Scheduling solution is too incomplete" in issue for issue in result.issues)


def test_marketing_mode_rejects_code_shaped_output():
    task = "Create a 30-day dental clinic go-to-market plan."
    solution = """```python
def launch():
    print("campaign")
```"""
    result = PreflightValidator().validate("Marketing & Growth", task, solution)
    assert any("plain-language deliverable" in issue for issue in result.issues)


@pytest.mark.parametrize(
    ("task_mode", "task_text", "solution"),
    [
        (
            "Marketing & Growth",
            "Create a 30-day campaign plan for dental clinics.",
            "Audience: dental clinics\nOffer: automated recalls\nChannel: outbound email\nKPI: booked demos",
        ),
        (
            "Business & Operations",
            "Design an SOP for handling client escalations.",
            "Owner: support lead\nStep 1: triage\nStep 2: escalate\nSLA: 2 hours",
        ),
        (
            "Writing & Content",
            "Write a memo about product reliability.",
            (
                "Reliability matters because trust compounds over time and because teams move faster when "
                "they are not constantly cleaning up preventable failures. A credible memo should explain "
                "the tradeoff clearly, use examples, and land on a real recommendation instead of outline fragments. "
                "It should also show how better operational discipline reduces rework, lowers hidden cost, and makes "
                "future product bets easier to trust across the team. It should give leaders a way to reason about "
                "sequencing, make the downside of fragile execution visible, and explain why reliability is not the "
                "opposite of innovation but the condition that lets innovation survive contact with reality."
            ),
        ),
        (
            "Personal Planning",
            "Build a weekly planning system for a founder.",
            "Priority: sleep\nNext step: define the weekly top three\nRisk: overload\nFallback: minimum viable week",
        ),
        (
            "General Problem Solving",
            "Recommend whether to expand or stay focused.",
            "Recommendation: stay focused first.\nTradeoff: slower upside.\nNext action: validate core demand.",
        ),
    ],
)
def test_preflight_accepts_plain_language_non_software_outputs(task_mode, task_text, solution):
    result = PreflightValidator().validate(task_mode, task_text, solution)

    assert result.passed is True
