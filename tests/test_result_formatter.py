from arbiter.app.result_formatter import ResultFormatter


def test_critique_html_contains_expected_sections():
    formatter = ResultFormatter()

    html = formatter.critique_html(
        t_score=8,
        l_score=7,
        avg=7.6,
        t_res={
            "critique": "Technical review found validation drift.",
            "fix_suggestion": "Tighten validation.",
            "issues": ["Validation misses empty input handling."],
            "repair_contract": ["Add input validation."],
        },
        l_res={
            "critique": "Logic review found unclear fallback rules.",
            "fix_suggestion": "Clarify fallback rules.",
            "issues": ["Fallback branch is underspecified."],
            "repair_contract": ["Specify fallback behavior."],
        },
        debate={"tech_focus": "validation", "logic_focus": "fallbacks", "combined_fix": "Tighten both."},
        raw_avg=7.5,
    )

    assert "CRITIC AVG: 7.5/10" in html
    assert "FINAL: 7.6/10" in html
    assert "Technical Audit:" in html
    assert "Logic Audit:" in html
    assert "REPAIR CONTRACT:" in html
    assert "CRITIC DEBATE:" in html


def test_preflight_blocked_html_preserves_cost_guardrail_message():
    formatter = ResultFormatter()

    html = formatter.preflight_blocked_html(
        ["Missing KPI definitions.", "No workflow owner specified."]
    )

    assert "LOCAL PREFLIGHT FAILED" in html
    assert "Blocked Before Critic Spend" in html
    assert "COST GUARDRAIL:" in html
    assert "Missing KPI definitions." in html
