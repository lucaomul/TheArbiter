from typing import Optional


class ResultFormatter:
    """
    Formats structured critic and preflight results for the current Streamlit UI.

    This keeps HTML construction out of core orchestration logic while preserving
    the same visible markup and copy.
    """

    @staticmethod
    def critique_html(
        t_score: int,
        l_score: int,
        avg: float,
        t_res: dict,
        l_res: dict,
        debate: Optional[dict] = None,
        raw_avg: Optional[float] = None,
    ) -> str:
        badge_cls = "" if avg >= 7 else "warning" if avg >= 5 else "danger"
        critic_average = float(raw_avg if raw_avg is not None else avg)
        score_line = (
            f"TECH: {t_score}/10 &nbsp;|&nbsp; LOGIC: {l_score}/10 "
            f"&nbsp;|&nbsp; CRITIC AVG: {critic_average:.1f}/10 "
            f"&nbsp;|&nbsp; FINAL: {avg:.1f}/10"
        )
        debate_block = ""
        if debate:
            debate_block = f"""
<div style='background:rgba(255,255,255,0.03);padding:12px;border-radius:8px;
            margin-top:12px;border-left:3px solid #7fffd0;'>
    <b>CRITIC DEBATE:</b><br>
    • Tech focus: {debate.get('tech_focus', 'n/a')}<br>
    • Logic focus: {debate.get('logic_focus', 'n/a')}<br>
    • Combined fix: {debate.get('combined_fix', 'n/a')}
</div>
"""
        tech_issues = t_res.get("issues", [])
        logic_issues = l_res.get("issues", [])
        tech_defects = t_res.get("confirmed_defects", [])
        logic_defects = l_res.get("confirmed_defects", [])
        tech_risks = t_res.get("risks", [])
        logic_risks = l_res.get("risks", [])
        tech_contract = t_res.get("repair_contract", [])
        logic_contract = l_res.get("repair_contract", [])
        tech_issue_block = ""
        logic_issue_block = ""
        tech_defect_block = ""
        logic_defect_block = ""
        tech_risk_block = ""
        logic_risk_block = ""
        if tech_issues:
            tech_issue_block = "<br><b style='color:#7fffd0;'>Full Technical Findings:</b><br>" + "<br>".join(
                f"• {issue}" for issue in tech_issues
            )
        if logic_issues:
            logic_issue_block = "<br><b style='color:#7fffd0;'>Full Logic Findings:</b><br>" + "<br>".join(
                f"• {issue}" for issue in logic_issues
            )
        if tech_defects:
            tech_defect_block = "<br><b style='color:#7fffd0;'>Confirmed Technical Defects:</b><br>" + "<br>".join(
                f"• {item}" for item in tech_defects[:4]
            )
        if logic_defects:
            logic_defect_block = "<br><b style='color:#7fffd0;'>Confirmed Logic Defects:</b><br>" + "<br>".join(
                f"• {item}" for item in logic_defects[:4]
            )
        if tech_risks:
            tech_risk_block = "<br><b style='color:#7fffd0;'>Technical Risks:</b><br>" + "<br>".join(
                f"• {item}" for item in tech_risks[:3]
            )
        if logic_risks:
            logic_risk_block = "<br><b style='color:#7fffd0;'>Logic Risks:</b><br>" + "<br>".join(
                f"• {item}" for item in logic_risks[:3]
            )
        repair_contract_block = ""
        if tech_contract or logic_contract:
            repair_contract_block = (
                "<div style='background:rgba(255,255,255,0.03);padding:12px;border-radius:8px;"
                "margin-top:12px;border-left:3px solid #ffaa00;'>"
                "<b>REPAIR CONTRACT:</b><br>"
                + ("<b>Tech:</b><br>" + "<br>".join(f"• {step}" for step in tech_contract) if tech_contract else "")
                + ("<br><b>Logic:</b><br>" + "<br>".join(f"• {step}" for step in logic_contract) if logic_contract else "")
                + "</div>"
            )
        return f"""
<div class="score-badge {badge_cls}">
    {score_line}
</div><br>
<b style='color:#00ffa3;'>Technical Audit:</b> {t_res.get('critique', 'No issues.')}{tech_defect_block}{tech_risk_block}{tech_issue_block}<br><br>
<b style='color:#00ffa3;'>Logic Audit:</b> {l_res.get('critique', 'No issues.')}{logic_defect_block}{logic_risk_block}{logic_issue_block}<br>
<div style='background:rgba(0,255,163,0.05);padding:12px;border-radius:8px;
            margin-top:15px;border-left:3px solid #00ffa3;'>
    <b>FIX PRIORITY:</b><br>
    • Tech: {t_res.get('fix_suggestion', 'None.')}<br>
    • Logic: {l_res.get('fix_suggestion', 'None.')}
</div>
{repair_contract_block}
{debate_block}
"""

    def preflight_diagnostic_html(
        self,
        preflight_issues: list[str],
        t_score: int,
        l_score: int,
        avg_score: float,
        t_res: dict,
        l_res: dict,
    ) -> str:
        return (
            "<div class=\"score-badge danger\">LOCAL PREFLIGHT FAILED</div><br>"
            "<b style='color:#ff6682;'>Detected Before Full Critic Loop:</b><br>"
            + "<br>".join(f"• {issue}" for issue in preflight_issues)
            + "<div style='background:rgba(255,170,0,0.06);padding:12px;border-radius:8px;"
            "margin-top:12px;border-left:3px solid #ffaa00;'>"
            "<b>DIAGNOSTIC CRITIC PASS:</b><br>"
            "Arbiter ran one bounded critic round anyway so the architect can see the broader failure set "
            "without entering a full paid loop."
            "</div><br>"
            + self.critique_html(t_score, l_score, avg_score, t_res, l_res, None)
        )

    @staticmethod
    def preflight_blocked_html(preflight_issues: list[str]) -> str:
        return (
            "<div class=\"score-badge danger\">LOCAL PREFLIGHT FAILED</div><br>"
            "<b style='color:#ff6682;'>Blocked Before Critic Spend:</b><br>"
            + "<br>".join(f"• {issue}" for issue in preflight_issues)
            + "<div style='background:rgba(255,68,102,0.06);padding:12px;border-radius:8px;"
            "margin-top:12px;border-left:3px solid #ff4466;'>"
            "<b>COST GUARDRAIL:</b><br>"
            "Stopped before critic calls because the architect output still failed local correctness checks. "
            "Gemini/Groq critic spend stays at zero in this case by design."
            "</div>"
        )
