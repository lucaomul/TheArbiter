from arbiter.config.settings import TASK_PROFILES
from arbiter.infra.memory_store import get_memory_store
from arbiter.prompts.templates.base import (
    AUDITOR_PROMPT,
    JANITOR_PROMPT,
    PROPOSER_PROMPT,
    TECH_CRITIC_PROMPT,
    LOGIC_CRITIC_PROMPT,
    JSON_REPAIR_PROMPT,
)


class PromptRegistry:
    """
    Centralized prompt builder.
    Injects task mode context into base prompts.
    """

    def __init__(self, task_mode: str = "Software & IT"):
        self.task_mode = task_mode
        self.memory = get_memory_store()

    def _get_profile(self) -> dict:
        return TASK_PROFILES.get(self.task_mode, TASK_PROFILES["General Problem Solving"])

    def _inject_mode(self, base_prompt: str, role: str) -> str:
        profile = self._get_profile()
        role_guidance = {
            "Auditor":      profile["auditor"],
            "Architect":    profile["architect"],
            "Tech Critic":  profile["execution"],
            "Logic Critic": profile["logic"],
            "Janitor":      profile.get("janitor", profile["architect"]),
            "JSON Repair":  "Preserve intended meaning while repairing malformed structured output.",
        }
        role_playbook = (profile.get("role_playbooks") or {}).get(role, "")
        mode_note = (
            f"\n\nCURRENT TASK MODE: {self.task_mode}\n"
            f"MODE INTENT: {profile['summary']}\n"
            f"ROLE ADAPTATION: {role_guidance.get(role, profile['architect'])}"
        )
        if role_playbook:
            mode_note += f"\nROLE PLAYBOOK:\n{role_playbook}"
        return base_prompt + mode_note

    def get(self, role: str) -> str:
        base_map = {
            "Auditor":      AUDITOR_PROMPT,
            "Architect":    PROPOSER_PROMPT,
            "Tech Critic":  TECH_CRITIC_PROMPT,
            "Logic Critic": LOGIC_CRITIC_PROMPT,
            "Janitor":      JANITOR_PROMPT,
            "JSON Repair":  JSON_REPAIR_PROMPT,
        }
        base = base_map.get(role, PROPOSER_PROMPT)
        return self._inject_mode(base, role)

    def _build_delivery_contract(self) -> str:
        profile = self._get_profile()
        delivery = profile.get("delivery", "Lead with the solution.")
        if self.task_mode == "Software & IT":
            return (
                "DELIVERY FORMAT:\n"
                "- Lead with executable code when code is required.\n"
                "- Return the complete working implementation, not fragments.\n"
                "- After the main solution, add 3-5 short bullets under 'Architect Insights'.\n"
                f"- Task-mode delivery: {delivery}"
            )
        return (
            "DELIVERY FORMAT:\n"
            f"- {delivery}\n"
            "- Return the deliverable in plain business/content language by default.\n"
            "- Do not return executable code, code fences, JSON payloads, schemas, or technical implementation scaffolds unless the user explicitly asks for them.\n"
            "- If the task mentions a product or system but does not explicitly request implementation, respond with strategy, plan, messaging, operations, or content output instead of code.\n"
            "- Keep the response concrete, concise, and outcome-oriented."
        )

    @staticmethod
    def _truncate_solution(text: str, limit: int = 3500) -> str:
        raw = str(text or "").strip()
        if len(raw) <= limit:
            return raw
        return raw[:limit] + "\n\n[truncated previous solution for context]"

    @staticmethod
    def _normalize_issue_list(items) -> list:
        normalized = []
        for item in items or []:
            text = str(item or "").strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    def _build_issue_diff(self, recent: list) -> str:
        if len(recent) < 2:
            return ""

        previous = recent[-2]
        latest = recent[-1]

        prev_issues = self._normalize_issue_list(
            (previous.get("tech_confirmed_defects") or previous.get("tech_issues") or [])
            + (previous.get("logic_confirmed_defects") or previous.get("logic_issues") or [])
            + (previous.get("preflight_issues") or [])
        )
        latest_issues = self._normalize_issue_list(
            (latest.get("tech_confirmed_defects") or latest.get("tech_issues") or [])
            + (latest.get("logic_confirmed_defects") or latest.get("logic_issues") or [])
            + (latest.get("preflight_issues") or [])
        )

        resolved = [issue for issue in prev_issues if issue not in latest_issues][:5]
        still_broken = [issue for issue in latest_issues if issue in prev_issues][:5]
        regressed = [issue for issue in latest_issues if issue not in prev_issues][:5]

        if not (resolved or still_broken or regressed):
            return ""

        parts = ["ISSUE DIFF VS PREVIOUS ATTEMPT:"]
        if resolved:
            parts.append("RESOLVED:")
            parts.extend([f"- {issue}" for issue in resolved])
        if still_broken:
            parts.append("STILL BROKEN:")
            parts.extend([f"- {issue}" for issue in still_broken])
        if regressed:
            parts.append("REGRESSED OR NEW:")
            parts.extend([f"- {issue}" for issue in regressed])
        parts.append("Use this diff to avoid repeating already-fixed mistakes and to focus on the remaining breakpoints.")
        return "\n".join(parts)

    @staticmethod
    def _is_scheduling_task(text: str) -> bool:
        raw = str(text).lower()
        keywords = [
            "schedule", "shift", "roster", "staff", "workforce",
            "night shift", "day shift", "requirements", "hours",
        ]
        return sum(1 for keyword in keywords if keyword in raw) >= 2

    def build_task_payload(self, user_text: str) -> str:
        profile = self._get_profile()
        domain_blueprint = ""
        if self.task_mode == "Software & IT" and self._is_scheduling_task(user_text):
            domain_blueprint = (
                "\nSCHEDULING BLUEPRINT:\n"
                "- Build explicit helpers for loading data, eligibility checks, assignment, and schedule writing.\n"
                "- Track assignedHours, lastShiftEndTime, and assignmentsByDay in employee state.\n"
                "- Prevent same-day DAY/NIGHT conflicts and enforce a 10-hour rest window with real time values.\n"
                "- Build sheet updates in memory and write back in batches.\n"
            )
        return (
            f"TASK MODE: {self.task_mode}\n"
            f"MODE SUMMARY: {profile['summary']}\n"
            f"{self._build_delivery_contract()}\n"
            f"{domain_blueprint}"
            f"USER REQUEST:\n{user_text.strip()}"
        )

    def build_architect_history(self, state, manual_override: str = "") -> str:
        history_lines = []

        if manual_override:
            history_lines.append(f"USER MANUAL INSTRUCTION: {manual_override}")

        memory_summary = self.memory.summarize_for_architect(
            self.task_mode,
            state.current_task or state.user_input,
            unresolved_issues=state.unresolved_issues,
            limit=3,
        )
        if memory_summary:
            history_lines.append(memory_summary)

        janitor = getattr(state, "latest_janitor_report", {}) or {}
        if janitor.get("summary") or janitor.get("repair_brief"):
            janitor_lines = ["JANITOR REPAIR BRIEF:"]
            if janitor.get("summary"):
                janitor_lines.append(janitor["summary"])
            if janitor.get("primary_subsystem"):
                janitor_lines.append(f"Primary subsystem: {janitor['primary_subsystem']}")
            if janitor.get("resolved"):
                janitor_lines.append("Resolved:")
                janitor_lines.extend([f"- {item}" for item in janitor.get("resolved", [])])
            if janitor.get("pending"):
                janitor_lines.append("Pending:")
                janitor_lines.extend([f"- {item}" for item in janitor.get("pending", [])])
            if janitor.get("regressed"):
                janitor_lines.append("Regressed:")
                janitor_lines.extend([f"- {item}" for item in janitor.get("regressed", [])])
            if janitor.get("preserve"):
                janitor_lines.append("Preserve:")
                janitor_lines.extend([f"- {item}" for item in janitor.get("preserve", [])])
            if janitor.get("repair_brief"):
                janitor_lines.append("Repair brief:")
                janitor_lines.extend([f"- {item}" for item in janitor.get("repair_brief", [])])
            history_lines.append("\n".join(janitor_lines))

        recent = state.iteration_history[-2:]
        if not recent:
            return "\n\n".join(history_lines).strip()

        latest = recent[-1]
        t_score = latest["tech"]
        l_score = latest["logic"]

        if latest.get("solution"):
            history_lines.append(
                "LAST ATTEMPT SOLUTION:\n"
                "You must compare your new answer against this previous implementation and deliberately improve it.\n"
                "Do not ignore what you already wrote.\n\n"
                + self._truncate_solution(latest.get("solution", ""))
            )

        issue_diff = self._build_issue_diff(recent)
        if issue_diff:
            history_lines.append(issue_diff)

        history_lines.append(
            "ITERATION CONTRACT:\n"
            "- Technical defects take priority over polish.\n"
            "- Do not leave placeholders, undefined variables, or partial helpers.\n"
            "- Verify the criticized bug is eliminated before returning.\n"
        )

        if t_score < 6:
            tech_issues = latest.get("tech_confirmed_defects") or latest.get("tech_issues") or [latest["tech_critique"]]
            tech_contract = latest.get("tech_repair_contract") or [latest.get("fix", "").split("|")[0].strip()]
            history_lines.append(f"""
CRITICAL PRIORITY (TECH SCORE {t_score}/10 — BROKEN):

Your ONLY job this round: fix the known technical defect set in code.
Do NOT touch logic, structure, or comments until this is resolved.

TECHNICAL DEFECT SUMMARY:
{latest["tech_critique"]}

TECHNICAL ISSUE SET:
- """ + "\n- ".join(tech_issues) + f"""

REPAIR CONTRACT:
- """ + "\n- ".join(item for item in tech_contract if item) + """

Verify the fix eliminates this known technical issue set before returning.
""")
        elif l_score < 7:
            logic_issues = latest.get("logic_confirmed_defects") or latest.get("logic_issues") or [latest["logic_critique"]]
            logic_contract = latest.get("logic_repair_contract") or [
                latest.get("fix", "").split("|")[-1].strip() if "|" in latest.get("fix", "") else latest.get("fix", "")
            ]
            history_lines.append(f"""
PRIORITY (LOGIC SCORE {l_score}/10):

Technical quality is acceptable ({t_score}/10). Focus on logic gaps.

LOGIC GAP:
{latest["logic_critique"]}

LOGIC ISSUE SET:
- """ + "\n- ".join(logic_issues) + f"""

REPAIR CONTRACT:
- """ + "\n- ".join(item for item in logic_contract if item) + """
""")
        else:
            history_lines.append(f"""
POLISH PHASE (Tech {t_score}/10, Logic {l_score}/10):

Both scores are good. Minor improvements only.
Tech: {latest["tech_critique"]}
Logic: {latest["logic_critique"]}
""")

        if state.unresolved_issues["tech"]:
            history_lines.append(
                "UNRESOLVED TECHNICAL ISSUES:\n- " + "\n- ".join(state.unresolved_issues["tech"][-2:])
            )
        if state.unresolved_issues["logic"]:
            history_lines.append(
                "UNRESOLVED LOGIC ISSUES:\n- " + "\n- ".join(state.unresolved_issues["logic"][-2:])
            )

        if state.rewrite_mode:
            history_lines.append(
                "REWRITE MODE IS ACTIVE:\n"
                "- Replace the broken subsystem causing the repeated technical failure.\n"
                "- Prefer a smaller, safer implementation over a broad rewrite.\n"
            )

        if state.tech_regression_count >= 1:
            history_lines.append(
                "REGRESSION ALERT:\n"
                "- The previous revision made technical quality worse.\n"
                "- Stop patching around the bug.\n"
                "- Reconstruct the broken subsystem cleanly from the last attempt, preserving only the parts that were already working.\n"
                "- Your goal is not to make a small edit. Your goal is to produce a materially safer version than the last attempt.\n"
            )

        if state.tech_oscillation_count >= 1:
            history_lines.append(
                "NARROW REPAIR MODE:\n"
                "- Technical quality is oscillating in a low band.\n"
                "- Rebuild only the broken core subsystem for this round.\n"
                "- Do not recycle the same implementation shape if it already failed in adjacent rounds.\n"
            )

        if len(recent) >= 2:
            prev = recent[-2]
            history_lines.append(
                f"--- Previous round (Cycle {prev['iter']}) ---\n"
                f"Tech {prev['tech']}/10: {prev['tech_critique']}\n"
                f"Logic {prev['logic']}/10: {prev['logic_critique']}"
            )

        return "\n\n".join(history_lines).strip()
