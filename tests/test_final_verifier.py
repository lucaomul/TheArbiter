import pytest

from arbiter.core.final_verifier import FinalVerifier
from arbiter.models.evidence import EvidenceBundle, EvidenceSource


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

ZERO_ARG_PYTHON_SOLUTION = """```python
def ping():
    return "ok"
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
    assert result.score == 0.68


def test_verifier_runs_safe_zero_arg_python_smoke_check():
    result = FinalVerifier().verify("Software & IT", "Build a python helper", ZERO_ARG_PYTHON_SOLUTION)

    smoke = next(item for item in result.checks if item["name"] == "python_smoke_execution")
    assert smoke["status"] == "pass"


def test_verifier_marks_unsafe_python_side_effects_as_caution():
    solution = """```python
import os

def list_files():
    return os.listdir(".")
```"""
    result = FinalVerifier().verify("Software & IT", "Build a python helper", solution)

    safety = next(item for item in result.checks if item["name"] == "python_static_safety")
    assert safety["status"] == "caution"


def test_verifier_accepts_parseable_json_when_explicitly_requested():
    result = FinalVerifier().verify(
        "General Problem Solving",
        "Return JSON with keys name and status.",
        '{"name": "arbiter", "status": "ok"}',
    )

    json_check = next(item for item in result.checks if item["name"] == "expected_json_output")
    assert json_check["status"] == "pass"


def test_verifier_marks_malformed_json_as_caution_when_requested():
    result = FinalVerifier().verify(
        "General Problem Solving",
        "Return JSON with keys name and status.",
        '{"name": "arbiter", "status": }',
    )

    json_check = next(item for item in result.checks if item["name"] == "expected_json_output")
    assert json_check["status"] == "caution"


def test_verifier_marks_unsupported_external_statistics_as_caution():
    solution = (
        "According to industry average data, 68% of dental clinics switch vendors within 90 days, "
        "and the market is worth $4.2 billion. Audience: dental clinics. Offer: automation."
    )
    result = FinalVerifier().verify(
        "Marketing & Growth",
        "Create a go-to-market plan for a dental SaaS.",
        solution,
    )

    grounding = next(item for item in result.checks if item["name"] == "grounding_discipline")
    assert grounding["status"] == "caution"


def test_verifier_allows_labeled_illustrative_targets():
    solution = (
        "Audience: independent clinics. Offer: recall automation. Channel: outbound email. CTA: book a demo. "
        "Assumption: illustrative target CAC is $250 during the first 30 days while the team tunes messaging."
    )
    result = FinalVerifier().verify(
        "Marketing & Growth",
        "Create a go-to-market plan for a dental SaaS.",
        solution,
    )

    grounding = next(item for item in result.checks if item["name"] == "grounding_discipline")
    assert grounding["status"] == "pass"


def test_verifier_marks_missing_requested_sources_as_caution():
    result = FinalVerifier().verify(
        "General Problem Solving",
        "Recommend how agencies should use AI in client delivery, with sources.",
        "Recommendation: start with internal QA workflows, then widen usage carefully.",
    )

    source_check = next(item for item in result.checks if item["name"] == "expected_sources")
    assert source_check["status"] == "caution"


def test_verifier_accepts_explicit_sources_when_requested():
    result = FinalVerifier().verify(
        "General Problem Solving",
        "Recommend how agencies should use AI in client delivery, with sources.",
        (
            "Recommendation: start with internal QA workflows, then widen usage carefully.\n\n"
            "Sources:\n"
            "- https://example.com/agency-ai-report\n"
            "- https://example.com/ops-reliability-study"
        ),
    )

    source_check = next(item for item in result.checks if item["name"] == "expected_sources")
    assert source_check["status"] == "pass"


def test_verifier_accepts_attached_source_name_as_source_marker():
    evidence = EvidenceBundle(
        query="Use the attached source.",
        sources=[
            EvidenceSource(
                source_id="src-1",
                name="customer-brief.docx",
                source_type="file",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                extracted_text="The rollout should begin with governance and staged deployment.",
            )
        ],
    )
    result = FinalVerifier().verify(
        "General Problem Solving",
        "Recommend how agencies should use AI in client delivery, with sources.",
        "Recommendation: begin with internal QA workflows. [Source: customer-brief.docx]",
        evidence_bundle=evidence,
    )

    source_check = next(item for item in result.checks if item["name"] == "expected_sources")
    assert source_check["status"] == "pass"


def test_verifier_marks_missing_requested_quotes_as_caution():
    result = FinalVerifier().verify(
        "Writing & Content",
        "Write a short note about responsible AI adoption with two direct quotes and sources.",
        (
            "Responsible adoption should start with governance and rollout discipline.\n\n"
            "Sources:\n- https://example.com/report"
        ),
    )

    quote_check = next(item for item in result.checks if item["name"] == "expected_quotes")
    assert quote_check["status"] == "caution"


def test_verifier_accepts_explicit_quotes_when_requested():
    result = FinalVerifier().verify(
        "Writing & Content",
        "Write a short note about responsible AI adoption with two direct quotes and sources.",
        (
            "\"Reliability comes before scale when teams are still learning where AI fails.\" — Example Report\n"
            "\"Operational discipline is what turns AI experiments into repeatable systems.\" — Example Study\n\n"
            "Sources:\n- https://example.com/report\n- https://example.com/study"
        ),
    )

    quote_check = next(item for item in result.checks if item["name"] == "expected_quotes")
    assert quote_check["status"] == "pass"


def test_verifier_checks_quotes_against_attached_source_material():
    evidence = EvidenceBundle(
        query="Quote the source",
        sources=[
            EvidenceSource(
                source_id="src-1",
                name="report.pdf",
                source_type="file",
                media_type="application/pdf",
                extracted_text=(
                    "Reliability comes before scale when teams are still learning where AI fails. "
                    "Operational discipline turns experiments into repeatable systems."
                ),
            )
        ],
    )
    result = FinalVerifier().verify(
        "Writing & Content",
        "Write a short note about responsible AI adoption with two direct quotes and sources.",
        (
            "\"Reliability comes before scale when teams are still learning where AI fails.\" [Source: report.pdf]\n"
            "\"Operational discipline turns experiments into repeatable systems.\" [Source: report.pdf]"
        ),
        evidence_bundle=evidence,
    )

    quote_check = next(item for item in result.checks if item["name"] == "expected_quotes")
    assert quote_check["status"] == "pass"


def test_verifier_marks_unmatched_quotes_from_attached_sources_as_caution():
    evidence = EvidenceBundle(
        query="Quote the source",
        sources=[
            EvidenceSource(
                source_id="src-1",
                name="report.pdf",
                source_type="file",
                media_type="application/pdf",
                extracted_text="Reliability comes before scale when teams are still learning where AI fails.",
            )
        ],
    )
    result = FinalVerifier().verify(
        "Writing & Content",
        "Write a short note about responsible AI adoption with two direct quotes and sources.",
        "\"A completely different claim that is not in the report.\" [Source: report.pdf]",
        evidence_bundle=evidence,
    )

    quote_check = next(item for item in result.checks if item["name"] == "expected_quotes")
    assert quote_check["status"] == "caution"


def test_verifier_executes_standalone_sql_when_requested():
    solution = """```sql
CREATE TABLE demo (id INTEGER PRIMARY KEY, name TEXT);
INSERT INTO demo (name) VALUES ('Arbiter');
SELECT * FROM demo;
```"""
    result = FinalVerifier().verify(
        "Software & IT",
        "Write a SQL script that creates a table and inserts a row.",
        solution,
    )

    sql_check = next(item for item in result.checks if item["name"] == "expected_sql_output")
    assert sql_check["status"] == "pass"


def test_verifier_marks_schema_dependent_sql_as_caution():
    result = FinalVerifier().verify(
        "Software & IT",
        "Write a SQL query that selects all users from the production database.",
        "SELECT * FROM users;",
    )

    sql_check = next(item for item in result.checks if item["name"] == "expected_sql_output")
    assert sql_check["status"] == "caution"


@pytest.mark.parametrize(
    ("task_mode", "task_text", "solution"),
    [
        (
            "Marketing & Growth",
            "Create a dental clinic go-to-market plan.",
            "Audience: independent dental clinics. Offer: automated recalls. Channel mix: email, outbound, local partnerships. KPI: booked demos.",
        ),
        (
            "Business & Operations",
            "Design an onboarding workflow for a 15-person agency.",
            "Owner: operations lead.\nStep 1: intake.\nStep 2: handoff.\nSLA: 24 hours.\nEscalation: delivery lead.",
        ),
        (
            "Writing & Content",
            "Write a founder memo about reliability before AI features.",
            "Reliability should come first because trust compounds. For example, product discipline reduces rework.\n\nHowever, ambitious features still matter when the core system is stable.",
        ),
        (
            "Personal Planning",
            "Build a 90-day plan for side business and health.",
            "Phase 1: stabilize sleep.\nNext step: set weekly priorities.\nTimeline: 12 weeks.\nRisk: overload.\nMetric: sleep consistency.",
        ),
        (
            "General Problem Solving",
            "Recommend whether a service business should productize.",
            "Recommendation: phase the transition. Option A preserves delivery quality. Tradeoff: slower packaging. Next action: pilot one offer.",
        ),
    ],
)
def test_verifier_recognizes_non_software_deliverables(task_mode, task_text, solution):
    result = FinalVerifier().verify(task_mode, task_text, solution)

    assert result.status in {"VERIFIED", "CAUTION"}
