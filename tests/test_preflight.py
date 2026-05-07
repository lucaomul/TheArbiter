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


def test_preflight_flags_unsupported_external_statistics_without_source():
    task = "Create a go-to-market plan for a dental SaaS."
    solution = (
        "According to industry average data, 68% of clinics switch vendors within 90 days, "
        "and the market is worth $4.2 billion. Audience: dental clinics. Offer: automation."
    )
    result = PreflightValidator().validate("Marketing & Growth", task, solution)

    assert any("precise external facts or statistics" in issue for issue in result.issues)


def test_preflight_allows_labeled_illustrative_metrics():
    task = "Create a go-to-market plan for a dental SaaS."
    solution = (
        "Audience: dental clinics\nOffer: automation\nChannel: outbound email\nCTA: book a demo\n"
        "Assumption: illustrative target CAC is $250 during the first 30 days."
    )
    result = PreflightValidator().validate("Marketing & Growth", task, solution)

    assert result.passed is True


def test_preflight_flags_missing_requested_sources():
    task = "Write a recommendation memo about AI usage in agencies, with sources."
    solution = "Recommendation: start with internal QA workflows and measured rollout."
    result = PreflightValidator().validate("Writing & Content", task, solution)

    assert any("asked for sources or citations" in issue for issue in result.issues)


def test_preflight_accepts_explicit_sources_when_requested():
    task = "Write a recommendation memo about AI usage in agencies, with sources."
    solution = (
        "Recommendation: start with internal QA workflows and measured rollout. "
        "That sequencing keeps client risk lower, gives the team a clean way to observe failure modes, "
        "and helps leaders decide where AI actually improves delivery instead of merely adding novelty. "
        "A strong memo should tie adoption to safeguards, operator visibility, and a phased rollout model "
        "so the team can learn without overcommitting too early. "
        "It should also explain why disciplined rollout protects trust, reduces cleanup work, and creates a better base "
        "for later expansion into more ambitious automation. "
        "The memo should make the recommendation feel operationally grounded rather than hype-driven, "
        "and it should leave the team with a practical bias toward controlled adoption, measurable checkpoints, "
        "and visible review loops before expanding AI deeper into client-facing work.\n\n"
        "Sources:\n"
        "- https://example.com/agency-ai-report\n"
        "- https://example.com/ops-reliability-study"
    )
    result = PreflightValidator().validate("Writing & Content", task, solution)

    assert result.passed is True


def test_preflight_flags_missing_requested_quotes():
    task = "Write a short note about responsible AI adoption with direct quotes and sources."
    solution = (
        "Responsible adoption should start with governance and rollout discipline.\n\n"
        "Sources:\n- https://example.com/report"
    )
    result = PreflightValidator().validate("Writing & Content", task, solution)

    assert any("asked for direct quotes" in issue for issue in result.issues)


def test_preflight_accepts_explicit_quotes_when_requested():
    task = "Write a short note about responsible AI adoption with direct quotes and sources."
    solution = (
        "\"Reliability comes before scale when teams are still learning where AI fails.\" — Example Report\n"
        "\"Operational discipline is what turns AI experiments into repeatable systems.\" — Example Study\n\n"
        "These quotes reinforce the case for careful rollout, visible safeguards, and disciplined iteration "
        "before broader deployment. They support a practical recommendation: teams should adopt AI in stages, "
        "tie each stage to visible review criteria, and avoid expanding usage faster than their governance and "
        "operator feedback loops can support. A credible note should connect the quoted evidence to rollout behavior, "
        "explain why unstructured expansion creates cleanup cost, and make the trust case legible for both builders "
        "and leaders who need to sequence adoption responsibly.\n\n"
        "Sources:\n"
        "- https://example.com/report\n"
        "- https://example.com/study"
    )
    result = PreflightValidator().validate("Writing & Content", task, solution)

    assert result.passed is True


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
