import streamlit as st
import os
import json
import re
import html
import textwrap
from fpdf import FPDF
from dotenv import load_dotenv

from agents import AIAgent, IterationMemory
from prompts import (
    AUDITOR_PROMPT,
    PROPOSER_PROMPT,
    TECH_CRITIC_PROMPT,
    LOGIC_CRITIC_PROMPT,
    JSON_REPAIR_PROMPT,
    ARCHITECT_FORMATTER_PROMPT,
)

load_dotenv()

# ── Page config ─────────────────────────────────────────────
st.set_page_config(
    page_title="The Arbiter | Luca Crăciun",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state ────────────────────────────────────────────
defaults = {
    "messages":          [],
    "costs":             {"Architect": 0.0, "Tech Critic": 0.0, "Logic Critic": 0.0, "Auditor": 0.0, "Total": 0.0},
    "step":              "input",
    "iteration":         0,
    "current_solution":  "",
    "current_task":      "",
    "last_avg_score":    0,
    "iteration_history": [],
    "architect_memory":  [],
    "best_solution":     "",
    "best_iteration":    None,
    "tech_stall_count":  0,
    "score_plateau_count": 0,
    "tech_regression_count": 0,
    "recent_low_tech_count": 0,
    "tech_oscillation_count": 0,
    "last_tech_score":   None,
    "rewrite_mode":      False,
    "unresolved_issues": {"tech": [], "logic": []},
    "repair_events":     0,
    "task_mode":         "Software & IT",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;500;700&display=swap');

.stApp {
    background: #050508;
    color: #e0e2e6;
    font-family: 'JetBrains Mono', monospace;
}

.agent-card {
    background: rgba(13,17,23,0.9);
    border: 1px solid rgba(0,255,163,0.2);
    border-radius: 12px;
    padding: 25px;
    margin-bottom: 20px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.8);
    transition: 0.3s ease;
}
.agent-card:hover {
    border-color: #00ffa3;
    box-shadow: 0 0 20px rgba(0,255,163,0.15);
}

.score-badge {
    display: inline-block;
    padding: 6px 18px;
    border-radius: 6px;
    background: rgba(0,255,163,0.1);
    border: 2px solid #00ffa3;
    color: #00ffa3;
    font-weight: 700;
    margin-bottom: 15px;
    box-shadow: 0 0 10px rgba(0,255,163,0.2);
}
.score-badge.warning {
    border-color: #ffaa00;
    color: #ffaa00;
    background: rgba(255,170,0,0.1);
    box-shadow: 0 0 10px rgba(255,170,0,0.2);
}
.score-badge.danger {
    border-color: #ff4466;
    color: #ff4466;
    background: rgba(255,68,102,0.1);
    box-shadow: 0 0 10px rgba(255,68,102,0.2);
}

.luca-branding {
    padding: 20px;
    border-radius: 12px;
    background: rgba(0,255,163,0.05);
    border: 1px solid rgba(0,255,163,0.2);
    text-align: center;
    margin-top: 30px;
}
.luca-name {
    font-weight: 700;
    color: #00ffa3;
    text-transform: uppercase;
    letter-spacing: 3px;
    font-size: 0.85rem;
}
.luca-link {
    color: #666;
    text-decoration: none;
    font-size: 0.7rem;
    margin: 0 10px;
    transition: 0.3s;
}
.luca-link:hover { color: #00ffa3; text-shadow: 0 0 5px #00ffa3; }

.stButton>button {
    border: 1px solid #00ffa3 !important;
    background: rgba(0,255,163,0.02) !important;
    color: #00ffa3 !important;
    text-transform: uppercase;
    letter-spacing: 2px;
    font-weight: 700;
    width: 100%;
    padding: 10px;
    transition: 0.4s;
}
.stButton>button:hover {
    background: #00ffa3 !important;
    color: #000 !important;
    box-shadow: 0 0 25px #00ffa3;
}

[data-testid="stSidebar"] {
    background-color: #080a0d !important;
    border-right: 1px solid #00ffa333;
}

.cost-label { font-size: 0.75rem; color: #888; margin-bottom: 2px; }
.cost-value { font-size: 0.9rem; color: #00ffa3; font-weight: bold; margin-bottom: 8px; }

.iter-bar {
    background: rgba(0,255,163,0.05);
    border: 1px solid rgba(0,255,163,0.15);
    border-radius: 8px;
    padding: 10px 16px;
    margin-bottom: 8px;
    font-size: 0.75rem;
    color: #888;
}

.telemetry-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 24px;
}
.telemetry-card {
    background: linear-gradient(180deg, rgba(0,255,163,0.06), rgba(8,10,13,0.95));
    border: 1px solid rgba(0,255,163,0.16);
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.25);
}
.telemetry-label {
    font-size: 0.68rem;
    letter-spacing: 2px;
    color: #7a848c;
    margin-bottom: 8px;
}
.telemetry-value {
    font-size: 1.15rem;
    color: #f5fffb;
    font-weight: 700;
}
.telemetry-meta {
    margin-top: 6px;
    font-size: 0.75rem;
    color: #9aa6ad;
}
.agent-role-tag {
    display: inline-block;
    margin-left: 10px;
    padding: 3px 8px;
    border-radius: 999px;
    border: 1px solid rgba(0,255,163,0.2);
    background: rgba(0,255,163,0.06);
    color: #7fffd0;
    font-size: 0.65rem;
    letter-spacing: 1px;
}
.architect-prose {
    margin-top: 15px;
    line-height: 1.7;
    color: #d8dde2;
    white-space: pre-wrap;
}
.architect-section-label {
    margin: 18px 0 10px;
    font-size: 0.72rem;
    letter-spacing: 2px;
    color: #7fffd0;
    text-transform: uppercase;
}
.architect-notes {
    margin-top: 12px;
    padding: 14px 16px;
    border-radius: 12px;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(0,255,163,0.12);
    line-height: 1.75;
    color: #d8dde2;
}
.code-shell {
    margin-top: 15px;
    border-radius: 14px;
    background:
        radial-gradient(circle at top right, rgba(0,255,163,0.08), transparent 38%),
        linear-gradient(180deg, rgba(5,9,13,0.98), rgba(2,5,8,0.98));
    border: 1px solid rgba(0,255,163,0.14);
    overflow-x: auto;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 18px 40px rgba(0,0,0,0.28);
}
.code-shell.javascript {
    border-color: rgba(255,208,0,0.22);
    background:
        radial-gradient(circle at top right, rgba(255,208,0,0.12), transparent 36%),
        linear-gradient(180deg, rgba(16,14,7,0.98), rgba(6,7,8,0.98));
}
.code-toolbar {
    margin: 0;
    padding: 16px;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    color: #eefbf6;
    line-height: 1.75;
}
.code-shell.javascript pre {
    color: #fff7cc;
}
.code-shell code {
    font-family: 'JetBrains Mono', monospace;
}
.delta-up { color: #7fffd0; }
.delta-flat { color: #ffaa00; }
.delta-down { color: #ff6682; }
@media (max-width: 900px) {
    .telemetry-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}
</style>
""", unsafe_allow_html=True)


# ── Cost tracker ─────────────────────────────────────────────
PRICES = {
    "gpt-4o":                  0.015,
    "gpt-4o-mini":             0.0006,
    "gemini-2.5-pro":          0.003,
    "gemini-2.5-flash":        0.0001,
    "gemini-1.5-pro":          0.003,
    "gemini-1.5-flash":        0.0001,
    "llama-3.3-70b-versatile": 0.0008,
}

REPAIR_PROVIDER = "openai"
REPAIR_MODEL = "gpt-4o-mini"
FORMATTER_PROVIDER = "openai"
FORMATTER_MODEL = "gpt-4o-mini"

TASK_PROFILES = {
    "Software & IT": {
        "tag": "Build Systems",
        "summary": "Code, debugging, automation, architecture, product engineering.",
        "auditor": "Prioritize stack, inputs/outputs, constraints, data shape, integrations, and edge cases.",
        "architect": "Behave like a senior engineer. Prefer concrete implementation, readable code, validation, and maintainability.",
        "execution": "Judge technical correctness, operational reliability, performance, and implementation quality.",
        "logic": "Judge completeness, consistency, flow, missing constraints, and hidden assumptions.",
    },
    "Marketing & Growth": {
        "tag": "Drive Attention",
        "summary": "Campaigns, positioning, funnels, copy, offers, outreach, audience fit.",
        "auditor": "Clarify audience, objective, channel, budget, tone, offer, constraints, and success metric.",
        "architect": "Behave like a sharp growth strategist and conversion copy lead. Prefer specific messaging, channel-aware tactics, and practical execution steps.",
        "execution": "Judge market fit, clarity, persuasion, channel realism, and likelihood of execution success.",
        "logic": "Judge strategic coherence, funnel completeness, audience alignment, and whether the plan actually solves the stated goal.",
    },
    "Business & Operations": {
        "tag": "Run Better",
        "summary": "Processes, SOPs, workflows, decision systems, team operations, service design.",
        "auditor": "Clarify business goal, current process, bottlenecks, stakeholders, resources, and constraints.",
        "architect": "Behave like an operations architect. Prefer scalable workflows, risk reduction, clarity of ownership, and realistic implementation sequencing.",
        "execution": "Judge practicality, efficiency, operational risk, and whether people could actually follow the solution.",
        "logic": "Judge process completeness, handoff integrity, missing dependencies, and policy contradictions.",
    },
    "Writing & Content": {
        "tag": "Shape Narrative",
        "summary": "Articles, scripts, posts, decks, messaging, structured writing.",
        "auditor": "Clarify audience, purpose, tone, format, desired outcome, and examples or constraints.",
        "architect": "Behave like a strategist-editor. Prefer strong structure, compelling language, clear voice, and useful specificity.",
        "execution": "Judge readability, quality, persuasion, audience fit, and polish.",
        "logic": "Judge structure, coherence, completeness, and whether the content actually achieves the intended purpose.",
    },
    "Personal Planning": {
        "tag": "Make Decisions",
        "summary": "Life admin, choices, planning, routines, prioritization, personal systems.",
        "auditor": "Clarify the real outcome, time horizon, tradeoffs, personal constraints, and preferred style of help.",
        "architect": "Behave like a thoughtful strategic coach. Prefer realistic plans, prioritization, emotional clarity, and concrete next actions.",
        "execution": "Judge practicality, realism, sustainability, and whether the plan can be acted on by a real person.",
        "logic": "Judge consistency, tradeoff handling, missing considerations, and whether the plan truly addresses the stated problem.",
    },
    "General Problem Solving": {
        "tag": "Think Broadly",
        "summary": "Mixed problems that need structured thinking, options, and decision quality.",
        "auditor": "Clarify objective, constraints, stakes, timeframe, and what a successful answer should look like.",
        "architect": "Behave like a high-agency strategist. Prefer clarity, options, tradeoffs, and executable recommendations.",
        "execution": "Judge usefulness, practicality, actionability, and quality of the proposed solution.",
        "logic": "Judge structure, completeness, contradiction risk, and whether the recommendation matches the problem.",
    },
}

def track_cost(role: str, model: str):
    cost = PRICES.get(model, 0.001)
    st.session_state.costs[role]    += cost
    st.session_state.costs["Total"] += cost


def get_task_profile() -> dict:
    return TASK_PROFILES.get(st.session_state.task_mode, TASK_PROFILES["General Problem Solving"])


def build_agent_instruction(base_prompt: str, role: str) -> str:
    profile = get_task_profile()
    role_guidance = {
        "Auditor": profile["auditor"],
        "Architect": profile["architect"],
        "Tech Critic": profile["execution"],
        "Logic Critic": profile["logic"],
        "JSON Repair": "Preserve the intended meaning while repairing malformed structured output.",
    }
    mode_note = (
        f"\n\nCURRENT TASK MODE: {st.session_state.task_mode}\n"
        f"MODE INTENT: {profile['summary']}\n"
        f"ROLE ADAPTATION: {role_guidance.get(role, profile['architect'])}"
    )
    return base_prompt + mode_note


def build_delivery_contract() -> str:
    if st.session_state.task_mode == "Software & IT":
        return (
            "DELIVERY FORMAT:\n"
            "- If the user asks for ready-to-paste code, lead with the full implementation immediately.\n"
            "- Use one clean, properly formatted code block for the main solution.\n"
            "- After the main code block, include a short section called 'Architect Insights' with 3-6 concise bullets explaining key decisions, assumptions, and any important caveats.\n"
            "- Include assumptions only if absolutely necessary, and keep them to 1-3 short lines.\n"
            "- Do not include bloated commentary or generic recap sections."
        )

    return (
        "DELIVERY FORMAT:\n"
        "- Lead with the actual solution.\n"
        "- Keep structure clear and useful.\n"
        "- Avoid generic filler and overexplaining."
    )


def build_task_payload(user_text: str) -> str:
    profile = get_task_profile()
    scheduling_blueprint = ""
    if is_scheduling_task(user_text):
        scheduling_blueprint = (
            "\nSCHEDULING BLUEPRINT:\n"
            "- Build around explicit helpers such as loadStaff/loadRequirements/buildShiftState/canWorkNextShift/assignShift/writeSchedule.\n"
            "- Enforce max-hours before assignment.\n"
            "- Enforce off-day and unavailable checks per employee per day, not as a global boolean shortcut.\n"
            "- Rest-period checks must use the previous assigned shift type and timestamp/day context.\n"
            "- Track explicit timing fields such as `lastShiftEndTime` and compare them against the next shift start time to enforce the 10-hour rest rule.\n"
            "- Prevent same-day DAY and NIGHT assignment for the same employee unless the task explicitly allows split shifts.\n"
            "- Build the schedule in memory first, then write it back in batches with setValues.\n"
            "- Do not call createTextFinder or setValue repeatedly inside assignment loops.\n"
            "- Every helper used by scheduling logic must be implemented in code.\n"
            "- Avoid hidden globals; pass scheduling data into helpers explicitly."
        )
    return (
        f"TASK MODE: {st.session_state.task_mode}\n"
        f"MODE SUMMARY: {profile['summary']}\n"
        f"{build_delivery_contract()}\n"
        f"{scheduling_blueprint}\n"
        f"USER REQUEST:\n{user_text.strip()}"
    )


def is_scheduling_task(text: str) -> bool:
    raw = str(text).lower()
    keywords = [
        "schedule", "shift", "roster", "staff", "workforce",
        "night shift", "day shift", "requirements", "hours",
    ]
    return sum(1 for keyword in keywords if keyword in raw) >= 2


def extract_primary_code(content: str) -> str:
    raw = normalize_architect_output(content)
    matches = list(re.finditer(r"```(\w+)?\n?(.*?)```", raw, flags=re.DOTALL))
    if matches:
        longest = max(matches, key=lambda match: len(match.group(2) or ""))
        body = (longest.group(2) or "").strip()
        return html.unescape(body)
    return raw


def latest_fix_text() -> str:
    if not st.session_state.iteration_history:
        return ""
    latest = st.session_state.iteration_history[-1]
    return " ".join([
        str(latest.get("tech_critique", "")),
        str(latest.get("logic_critique", "")),
        str(latest.get("fix", "")),
    ]).lower()


def has_batched_schedule_structure(code: str) -> bool:
    lowered = code.lower()

    explicit_structure_tokens = [
        "schedulematrix", "schedulegrid", "schedulemap", "assignmentsbyday",
        "assignmentsbyemployee", "scheduledata", "outputmatrix", "rows",
        "outputrows", "sheetdata", "resultmatrix",
    ]
    if any(token in lowered for token in explicit_structure_tokens):
        return True

    array_build_patterns = [
        r"(const|let|var)\s+\w+\s*=\s*\[\s*\]",
        r"array\s*\(",
        r"\.push\s*\(",
        r"\.map\s*\(",
        r"\.fill\s*\(",
    ]
    object_build_patterns = [
        r"(const|let|var)\s+\w+\s*=\s*\{\s*\}",
        r"\[\s*\w+\s*\]\s*=",
    ]
    batch_write_patterns = [
        r"\.setvalues\s*\(",
        r"\.appendrow\s*\(",
    ]

    builds_in_memory = (
        sum(bool(re.search(pattern, lowered)) for pattern in array_build_patterns) >= 2
        or (
            any(re.search(pattern, lowered) for pattern in array_build_patterns)
            and any(re.search(pattern, lowered) for pattern in object_build_patterns)
        )
    )
    writes_in_batch = any(re.search(pattern, lowered) for pattern in batch_write_patterns)

    return builds_in_memory and writes_in_batch


def find_placeholder_lines(text: str) -> list[str]:
    patterns = [
        r"\bTODO\b",
        r"\bimplement logic\b",
        r"\bexample logic\b",
        r"\bplaceholder\b",
        r"\bstub\b",
        r"\bto be implemented\b",
        r"\badd your\b",
    ]
    matches = []
    for line in str(text).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(re.search(pattern, stripped, flags=re.IGNORECASE) for pattern in patterns):
            matches.append(stripped[:180])
    return matches[:5]


def function_accepts_parameter(code: str, function_name: str, parameter_name: str) -> bool:
    match = re.search(
        rf"function\s+{re.escape(function_name)}\s*\(([^)]*)\)",
        code,
        flags=re.IGNORECASE,
    )
    if not match:
        return False
    params = match.group(1).lower()
    return parameter_name.lower() in params


def function_body_contains(code: str, function_name: str, pattern: str) -> bool:
    match = re.search(
        rf"function\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{(.*?)\n\}}",
        code,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return False
    return re.search(pattern, match.group(1), flags=re.IGNORECASE | re.DOTALL) is not None


def run_local_preflight(proposal: str, task_text: str) -> list[str]:
    raw = normalize_architect_output(proposal)
    code = extract_primary_code(proposal)
    lowered = code.lower()
    issues = []
    fix_text = latest_fix_text()

    if "[object object]" in raw.lower():
        issues.append("Remove all `[object Object]` garbage from the response.")

    placeholder_lines = find_placeholder_lines(raw)
    if placeholder_lines:
        issues.append(
            "Replace placeholders or example logic with fully implemented code. "
            f"Triggered by: {' | '.join(placeholder_lines)}"
        )

    if is_scheduling_task(task_text):
        required_signals = ["assign", "shift", "hours"]
        if sum(1 for signal in required_signals if signal in lowered) < 3:
            issues.append("Scheduling solution is too incomplete; include real assignment and hours-management logic.")

        if ".setvalue(" in lowered and re.search(r"(for|while)\s*\(", lowered):
            issues.append("Do not use `setValue` inside loops for schedule generation; build a matrix and write with `setValues` in batches.")

        if "createtextfinder(" in lowered and re.search(r"(for|while)\s*\(", lowered):
            issues.append("Do not call `createTextFinder` inside loops; precompute row/employee lookups once and reuse them.")

        if "writeschedule" in lowered:
            if "setvalues(" not in lowered:
                issues.append("`writeSchedule` should batch sheet updates with `setValues` instead of per-cell writes.")
            if not has_batched_schedule_structure(code):
                issues.append("`writeSchedule` should track assignments in a day/employee structure before writing to the sheet.")

        if "canworknextshift" in lowered:
            if "'day'" not in lowered and '"day"' not in lowered:
                issues.append("`canWorkNextShift` must explicitly handle DAY shifts.")
            if "'night'" not in lowered and '"night"' not in lowered:
                issues.append("`canWorkNextShift` must explicitly handle NIGHT shifts.")
            if "10" not in lowered and "rest" not in lowered:
                issues.append("`canWorkNextShift` must enforce the 10-hour rest rule in code.")
            same_day_guard = any(
                token in lowered for token in [
                    "currentdayshifts", "shiftsfortoday", "schedule[day]",
                    "assignedtoday", "same day", "current day",
                ]
            )
            if not same_day_guard:
                issues.append("`canWorkNextShift` must prevent assigning both DAY and NIGHT to the same employee on the same day.")
            last_shift_time_guard = any(
                token in lowered for token in [
                    "lastshiftend", "lastshiftendtime", "lastshifttime",
                    "shiftendtime", "resthours", "hourssince", "timediff",
                    "hoursbetween", "gettime()", "elapsedhours", "millisbetween",
                ]
            )
            if not last_shift_time_guard:
                issues.append("`canWorkNextShift` must use last shift end time or equivalent rest-hour calculation, not only shift type/day labels.")

        if "employeeData".lower() in fix_text and "fillschedule" in lowered:
            signature = re.search(r"function\s+fillSchedule\s*\(([^)]*)\)", code, flags=re.IGNORECASE)
            params = signature.group(1).lower() if signature else ""
            if "employeedata" not in params:
                issues.append("`fillSchedule` must accept `employeeData` as a parameter if it uses it.")

        if "staffdata" in fix_text and "assignshift" in lowered:
            if re.search(r"\bstaffData\b", code, flags=re.IGNORECASE) and not function_accepts_parameter(code, "assignShift", "staffData"):
                issues.append("`assignShift` must accept `staffData` as a parameter if it uses it.")
            if function_body_contains(code, "assignShift", r"\bstaffData\b") and not function_accepts_parameter(code, "assignShift", "staffData"):
                issues.append("`assignShift` uses `staffData` out of scope; pass it from `buildSchedule`.")

        if "max" in fix_text and "hour" in fix_text:
            max_hours_present = any(token in lowered for token in ["maxhours", "maximumhours", "max_hours"])
            hour_comparison_present = bool(re.search(r"(assigned|current|weekly)\w*hours?.{0,30}(>=|>|<|<=).{0,20}(maxhours|max_hours|maximumhours)", lowered))
            if not (max_hours_present and hour_comparison_present):
                issues.append("Check maximum hours before assigning a new shift.")

        if "createTextFinder".lower() in fix_text and "createtextfinder(" in lowered and re.search(r"(for|while)\s*\(", lowered):
            issues.append("Move `createTextFinder` out of loops and replace it with cached row/column lookups.")

        if "setvalue" in fix_text and ".setvalue(" in lowered and re.search(r"(for|while)\s*\(", lowered):
            issues.append("Replace repeated single-cell `setValue` writes with a single batched `setValues` write.")

        if "undefined" in fix_text or "scope" in fix_text:
            if re.search(r"\bemployeeData\b", code) and not re.search(r"(const|let|var)\s+employeeData\b", code):
                signature = re.search(r"function\s+\w+\s*\(([^)]*employeeData[^)]*)\)", code, flags=re.IGNORECASE)
                if not signature:
                    issues.append("A referenced `employeeData` variable appears out of scope; declare it or pass it into the function.")

    return issues[:5]


def build_preflight_repair_prompt(task_text: str, proposal: str, issues: list[str]) -> str:
    issue_lines = "\n".join(f"- {issue}" for issue in issues)
    extra_repair_guidance = ""
    issue_text = " ".join(issues).lower()
    if "too incomplete" in issue_text or "hours-management logic" in issue_text:
        extra_repair_guidance += (
            "Required minimum scheduling engine:\n"
            "- Implement a real data flow: load staff -> load requirements -> build employee state -> assign shifts -> write schedule.\n"
            "- Each employee state must track assigned hours, lastShiftEndTime, and assignmentsByDay.\n"
            "- Assignment logic must choose eligible employees, update assigned hours, update lastShiftEndTime, and record the assigned shift in assignmentsByDay.\n"
            "- Enforce maximum hours before assigning a shift.\n"
            "- Return a complete working function set, not helper fragments.\n\n"
            "Minimum expected functions:\n"
            "- loadStaffData(...)\n"
            "- loadRequirements(...)\n"
            "- canWorkNextShift(...)\n"
            "- assignShift(...)\n"
            "- buildSchedule(...)\n"
            "- writeSchedule(...)\n\n"
        )
    if "canworknextshift" in issue_text or "rest" in issue_text:
        extra_repair_guidance += (
            "Required repair shape for rest logic:\n"
            "- Store or derive `lastShiftEndTime` for each employee.\n"
            "- Compute the candidate shift start time for the current assignment.\n"
            "- Block the assignment when hoursBetween(lastShiftEndTime, candidateShiftStart) < 10.\n"
            "- Also block assigning both DAY and NIGHT on the same calendar day.\n\n"
        )
    if "same employee on the same day" in issue_text or "both day and night" in issue_text:
        extra_repair_guidance += (
            "Required repair shape for same-day shift exclusivity:\n"
            "- Keep an in-memory structure like `employeeState.assignmentsByDay[dayKey]`.\n"
            "- In `canWorkNextShift`, read the current day's assignments before approving a shift.\n"
            "- If the employee already has any shift recorded for that day, return false.\n"
            "- Only update `assignmentsByDay[dayKey]` after the assignment is actually accepted.\n\n"
            "Required implementation contract:\n"
            "- `employeeState.assignmentsByDay` must exist on every employee state object.\n"
            "- `canWorkNextShift(employeeState, dayKey, candidateShift, candidateStartTime)` must read `employeeState.assignmentsByDay[dayKey]`.\n"
            "- `assignShift(...)` must write the accepted shift back with something equivalent to `employeeState.assignmentsByDay[dayKey].push(candidateShift)`.\n"
            "- If the code does not include both the read check and the write-back, the repair is incomplete.\n\n"
            "Example expectation:\n"
            "const shiftsToday = employeeState.assignmentsByDay[dayKey] || [];\n"
            "if (shiftsToday.includes('DAY') || shiftsToday.includes('NIGHT')) return false;\n\n"
            "Example repair skeleton:\n"
            "function canWorkNextShift(employeeState, dayKey, candidateShift, candidateStartTime) {\n"
            "  const shiftsToday = employeeState.assignmentsByDay[dayKey] || [];\n"
            "  if (shiftsToday.length > 0) return false;\n"
            "  if (employeeState.lastShiftEndTime) {\n"
            "    const hoursSinceLastShift = (candidateStartTime.getTime() - employeeState.lastShiftEndTime.getTime()) / 36e5;\n"
            "    if (hoursSinceLastShift < 10) return false;\n"
            "  }\n"
            "  return true;\n"
            "}\n\n"
            "function assignShift(employeeState, dayKey, candidateShift, candidateStartTime) {\n"
            "  if (!canWorkNextShift(employeeState, dayKey, candidateShift, candidateStartTime)) return false;\n"
            "  employeeState.assignmentsByDay[dayKey] = employeeState.assignmentsByDay[dayKey] || [];\n"
            "  employeeState.assignmentsByDay[dayKey].push(candidateShift);\n"
            "  return true;\n"
            "}\n\n"
        )
    return (
        "LOCAL PREFLIGHT FAILED. Repair the solution before critic review.\n"
        "You must return the full corrected solution, not a diff or explanation-only response.\n"
        "Do not use TODOs, placeholders, stub comments, 'implement logic', or example code in the repaired answer.\n"
        f"{extra_repair_guidance}"
        "Failed checks:\n"
        f"{issue_lines}\n\n"
        "ORIGINAL TASK:\n"
        f"{task_text}\n\n"
        "CURRENT BROKEN SOLUTION:\n"
        f"{proposal}"
    )


def should_format_architect_output(output: str) -> bool:
    raw = html.unescape(str(output)).strip()
    if st.session_state.task_mode != "Software & IT":
        return False
    if "```" not in raw:
        return True
    if raw.startswith("JAVASCRIPT") or raw.startswith("JavaScript"):
        return True
    if len(raw.splitlines()) <= 8 and detect_code_language(raw) == "javascript":
        return True
    return False


def detect_code_language(raw: str) -> str:
    text = html.unescape(str(raw)).strip()

    js_signals = [
        r"\bfunction\s+\w+\s*\(",
        r"\b(?:const|let|var)\s+\w+\s*=",
        r"=>\s*\{",
        r"\bexport\s+(?:default|const|function|class)\b",
        r"\bdocument\.(?:querySelector|getElementById|createElement)\b",
        r"\bconsole\.log\b",
    ]
    py_signals = [
        r"^\s*def\s+\w+\s*\(",
        r"^\s*import\s+\w+",
        r"^\s*from\s+\w+\s+import\s+",
    ]

    if any(re.search(pattern, text, flags=re.MULTILINE) for pattern in js_signals):
        return "javascript"
    if any(re.search(pattern, text, flags=re.MULTILINE) for pattern in py_signals):
        return "python"
    return "text"


def prettify_javascript(code: str) -> str:
    text = html.unescape(str(code)).replace("\r\n", "\n").strip()
    if not text:
        return text

    text = re.sub(r"(?im)^.*\[object Object\].*$", "", text)
    text = re.sub(r";\s*(?=(?:function|const|let|var|if|for|while|return|Logger|SpreadsheetApp))", ";\n", text)
    text = re.sub(r"\{\s*(?=(?:function|const|let|var|if|for|while|return))", "{\n", text)
    text = re.sub(r"\}\s*(?=(?:function|const|let|var|if|for|while))", "}\n", text)
    text = re.sub(r"\s*}\s*else\s*{\s*", "\n} else {\n", text)
    text = re.sub(r";\s*}", ";\n}", text)
    text = re.sub(r"{\s*//", "{\n//", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    lines = [line.rstrip() for line in text.split("\n")]
    formatted = []
    indent = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if formatted and formatted[-1] != "":
                formatted.append("")
            continue

        closing_prefixes = len(re.match(r"^}+", line).group(0)) if re.match(r"^}+", line) else 0
        current_indent = max(indent - closing_prefixes, 0)
        formatted.append(("  " * current_indent) + line)

        open_count = line.count("{")
        close_count = line.count("}")
        indent = max(current_indent + open_count - close_count + closing_prefixes, 0)

    result = "\n".join(formatted).strip()
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def normalize_architect_output(output: str) -> str:
    raw = html.unescape(str(output)).strip()

    raw = re.sub(r"^(?:JAVASCRIPT|JavaScript|JS)\s*:?[\n ]+", "", raw)
    raw = re.sub(r"^(?:CODE|Snippet)\s*:?[\n ]+", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"(?im)^.*\[object Object\].*$", "", raw)
    raw = raw.replace("[object Object]", "")
    raw = re.sub(r"\n{3,}", "\n\n", raw)

    raw = raw.replace("≤", "<=").replace("≥", ">=")

    # Drop common filler lead-ins that make the answer look cheap.
    raw = re.sub(r"^(Here(?:'s| is).{0,180}?:\s*)", "", raw, flags=re.IGNORECASE | re.DOTALL)
    raw = re.sub(
        r"^(?:Below is|The following is|Here is)\s+(?:the\s+)?(?:JavaScript|JS)\s+(?:code|solution|snippet)\s*:\s*",
        "",
        raw,
        flags=re.IGNORECASE,
    )

    return raw


def format_architect_output(output: str) -> str:
    normalized = normalize_architect_output(output)
    return normalized


def update_issue_tracker(t_res: dict, l_res: dict, t_score: int):
    tech_issue = str(t_res.get("critique", "")).strip()
    logic_issue = str(l_res.get("critique", "")).strip()
    logic_score = int(l_res.get("score", 1))

    if tech_issue and tech_issue not in st.session_state.unresolved_issues["tech"]:
        st.session_state.unresolved_issues["tech"].append(tech_issue)
    if logic_issue and logic_issue not in st.session_state.unresolved_issues["logic"]:
        st.session_state.unresolved_issues["logic"].append(logic_issue)

    st.session_state.unresolved_issues["tech"] = st.session_state.unresolved_issues["tech"][-3:]
    st.session_state.unresolved_issues["logic"] = st.session_state.unresolved_issues["logic"][-3:]

    previous_tech_score = st.session_state.last_tech_score
    if previous_tech_score is None or t_score > previous_tech_score:
        st.session_state.tech_stall_count = 0
    else:
        st.session_state.tech_stall_count += 1

    if previous_tech_score is not None and t_score < previous_tech_score:
        st.session_state.tech_regression_count += 1
    else:
        st.session_state.tech_regression_count = 0

    latest = st.session_state.iteration_history[-1] if st.session_state.iteration_history else None
    if latest and latest.get("tech") == t_score and latest.get("logic") == logic_score:
        st.session_state.score_plateau_count += 1
    else:
        st.session_state.score_plateau_count = 0

    recent_tech_scores = [item.get("tech") for item in st.session_state.iteration_history[-2:]]
    recent_tech_scores.append(t_score)
    st.session_state.recent_low_tech_count = sum(
        1 for score in recent_tech_scores if score is not None and score <= 4
    )
    recent_band = [score for score in recent_tech_scores if score is not None]
    if len(recent_band) >= 3 and max(recent_band) <= 5 and min(recent_band) <= 4 and len(set(recent_band)) > 1:
        st.session_state.tech_oscillation_count += 1
    else:
        st.session_state.tech_oscillation_count = 0

    st.session_state.last_tech_score = t_score
    st.session_state.rewrite_mode = (
        t_score <= 5 and (
            st.session_state.tech_stall_count >= 1
            or st.session_state.tech_regression_count >= 1
            or st.session_state.score_plateau_count >= 1
            or st.session_state.recent_low_tech_count >= 2
            or st.session_state.tech_oscillation_count >= 1
        )
    )

    if t_score >= 7 and tech_issue:
        st.session_state.unresolved_issues["tech"] = [
            item for item in st.session_state.unresolved_issues["tech"] if item != tech_issue
        ]
    if logic_score >= 7 and logic_issue:
        st.session_state.unresolved_issues["logic"] = [
            item for item in st.session_state.unresolved_issues["logic"] if item != logic_issue
        ]


def build_priority_brief() -> str:
    brief_lines = []
    latest = st.session_state.iteration_history[-1] if st.session_state.iteration_history else None

    if latest:
        brief_lines.append(f"Top technical issue: {latest['tech_critique']}")
        brief_lines.append(f"Top logic issue: {latest['logic_critique']}")
        brief_lines.append(f"Required fixes from last round: {latest['fix']}")

    unresolved_tech = st.session_state.unresolved_issues["tech"][-2:]
    unresolved_logic = st.session_state.unresolved_issues["logic"][-2:]

    if unresolved_tech:
        brief_lines.append("Unresolved technical issues: " + " | ".join(unresolved_tech))
    if unresolved_logic:
        brief_lines.append("Unresolved logic issues: " + " | ".join(unresolved_logic))

    if st.session_state.tech_stall_count >= 1:
        brief_lines.append(
            f"Technical score has stalled for {st.session_state.tech_stall_count} round(s). "
            "Do not make cosmetic edits."
        )

    if st.session_state.tech_regression_count >= 1:
        brief_lines.append(
            f"Technical score regressed in the latest round. The recent changes made the solution worse. "
            "Revert the failing direction and replace it with a simpler, safer implementation."
        )

    if st.session_state.score_plateau_count >= 1:
        brief_lines.append(
            f"The exact score pair has repeated for {st.session_state.score_plateau_count + 1} consecutive rounds. "
            "Replace the failing implementation strategy instead of refining wording or formatting."
        )

    if st.session_state.recent_low_tech_count >= 2:
        brief_lines.append(
            f"Low-tech failure budget exceeded: {st.session_state.recent_low_tech_count} of the last 3 rounds scored 4/10 or below on technical quality. "
            "Abandon the current approach and return a substantially different implementation."
        )

    if st.session_state.tech_oscillation_count >= 1:
        brief_lines.append(
            "Technical score is oscillating within the same low-quality band. "
            "Stop rewriting the whole solution. Rebuild only the broken core subsystem with a simpler implementation."
        )

    if st.session_state.rewrite_mode:
        brief_lines.append(
            "Rewrite mode is ACTIVE. Replace the broken subsystem causing the recurring technical failure. "
            "Prefer a simpler, more reliable architecture over patching the current one."
        )

    if st.session_state.score_plateau_count >= 2:
        brief_lines.append(
            "Cost guardrail: this is the final retry for the current strategy. "
            "Return a materially different implementation or the run will stop."
        )

    return "\n".join([line for line in brief_lines if line]).strip()


def build_rewrite_contract() -> str:
    latest = st.session_state.iteration_history[-1] if st.session_state.iteration_history else None
    if not latest:
        return ""

    contract_lines = [
        "NON-NEGOTIABLE IMPLEMENTATION REQUIREMENTS:",
        f"- Fix this technical failure in code: {latest['tech_critique']}",
        f"- Fix this logic gap in code: {latest['logic_critique']}",
        f"- Mandatory repair targets: {latest['fix']}",
        "- Every function must receive the data it uses through parameters or clearly defined shared state.",
        "- Do not reference undefined variables, undefined helpers, or implied data structures.",
        "- Enforce all scheduling/business constraints in executable code, not just comments or explanations.",
        "- Return the complete working implementation, not a patch fragment.",
    ]
    return "\n".join(contract_lines)


def build_technical_fix_contract() -> str:
    latest = st.session_state.iteration_history[-1] if st.session_state.iteration_history else None
    if not latest:
        return ""

    tech_critique = str(latest.get("tech_critique", "")).strip()
    fix_text = str(latest.get("fix", "")).strip()

    contract_lines = [
        "TECHNICAL REPAIR CONTRACT:",
        f"- Primary objective: raise technical quality above the previous round's {latest['tech']}/10 score.",
        f"- Mandatory technical defect to eliminate: {tech_critique}",
        f"- Mandatory fix instruction: {fix_text}",
        "- Do not spend this round polishing prose, comments, or structure until the technical defect is resolved in code.",
        "- If the defect involves scope, every used identifier must be declared or passed explicitly.",
        "- If the defect involves correctness, implement the missing logic fully and make the control flow executable end-to-end.",
        "- If the defect involves performance, replace repeated expensive operations with cached lookups or batched writes.",
        "- Before returning, verify that the criticized technical bug can no longer occur in the new code.",
    ]
    return "\n".join(contract_lines)


def build_technical_checklist() -> str:
    latest = st.session_state.iteration_history[-1] if st.session_state.iteration_history else None
    if not latest:
        return ""

    tech_critique = str(latest.get("tech_critique", "")).lower()
    fix_text = str(latest.get("fix", "")).lower()
    combined = f"{tech_critique} {fix_text}"
    checklist = [
        "- All referenced variables/helpers are declared, passed in, or clearly defined in shared scope.",
        "- All required helper functions are fully implemented, not implied.",
        "- The main execution path can run from input to output without missing data or missing steps.",
    ]

    if any(token in combined for token in ["performance", "setvalue", "createtextfinder", "batch", "slow"]):
        checklist.append("- Expensive spreadsheet operations are batched or cached; no repeated single-cell writes/searches inside loops.")
    if any(token in combined for token in ["scope", "undefined", "parameter", "global"]):
        checklist.append("- Data used inside each function is passed by parameter or defined in that function/shared scope.")
    if any(token in combined for token in ["rest", "night", "day", "shift", "hours", "max"]):
        checklist.append("- Scheduling constraints are enforced in code: prior shift context, rest windows, and hour limits.")

    return "TECHNICAL SELF-CHECK BEFORE ANSWERING:\n" + "\n".join(checklist)


def build_core_repair_contract() -> str:
    if not st.session_state.iteration_history:
        return ""
    if not (st.session_state.tech_oscillation_count >= 1 and is_scheduling_task(st.session_state.current_task)):
        return ""

    latest = st.session_state.iteration_history[-1]
    return "\n".join([
        "NARROW REPAIR MODE:",
        "- Rebuild only the core scheduling engine and its directly required helpers.",
        "- Do not redesign unrelated UI/reporting/export parts in this round.",
        "- Return a compact but complete set of functions for: loading data, validating constraints, assigning shifts, and batch-writing the final schedule.",
        f"- The core defect to eliminate is: {latest['tech_critique']}",
        "- Prefer a smaller, deterministic implementation over a broad feature-heavy rewrite.",
    ])


def build_architect_history(manual_override: str) -> str:
    memory = IterationMemory(k=6, seed=st.session_state.architect_memory)
    memory_context = memory.context()
    history_lines = []

    if memory_context:
        history_lines.append(memory_context)
    if manual_override:
        history_lines.append(f"User instruction for this cycle: {manual_override}")

    priority_brief = build_priority_brief()
    if priority_brief:
        history_lines.append(priority_brief)

    technical_fix_contract = build_technical_fix_contract() if st.session_state.iteration_history else ""
    if technical_fix_contract:
        history_lines.append(technical_fix_contract)

    technical_checklist = build_technical_checklist() if st.session_state.iteration_history else ""
    if technical_checklist:
        history_lines.append(technical_checklist)

    core_repair_contract = build_core_repair_contract()
    if core_repair_contract:
        history_lines.append(core_repair_contract)

    rewrite_contract = build_rewrite_contract() if (
        st.session_state.rewrite_mode or st.session_state.score_plateau_count >= 1
    ) else ""
    if rewrite_contract:
        history_lines.append(rewrite_contract)

    for h in st.session_state.iteration_history[-3:]:
        history_lines.append(
            f"--- Iteration {h['iter']} feedback ---\n"
            f"Scores: Tech {h['tech']}/10, Logic {h['logic']}/10\n"
            f"Tech critique: {h['tech_critique']}\n"
            f"Logic critique: {h['logic_critique']}\n"
            f"Fix required: {h['fix']}"
        )

    return "\n\n".join(history_lines).strip()


def update_architect_memory(task: str, proposal: str, t_res: dict, l_res: dict):
    memory = IterationMemory(k=6, seed=st.session_state.architect_memory)
    compact_feedback = (
        f"Task: {task}\n"
        f"Produced solution summary: {proposal[:1200]}\n"
        f"Tech score: {t_res.get('score', 1)} | Tech critique: {t_res.get('critique', '')}\n"
        f"Logic score: {l_res.get('score', 1)} | Logic critique: {l_res.get('critique', '')}\n"
        f"Next fixes: Tech -> {t_res.get('fix_suggestion', '')} | Logic -> {l_res.get('fix_suggestion', '')}"
    )
    memory.add(task, compact_feedback)
    st.session_state.architect_memory = memory.dump()


def score_delta_text(metric: str, current_value: float) -> str:
    if not st.session_state.iteration_history:
        return "Baseline round"

    previous = st.session_state.iteration_history[-1].get(metric)
    if previous is None:
        return "Baseline round"

    delta = current_value - previous
    if delta > 0:
        return f"<span class='delta-up'>+{delta:.1f}</span> vs last cycle"
    if delta < 0:
        return f"<span class='delta-down'>{delta:.1f}</span> vs last cycle"
    return "<span class='delta-flat'>0.0</span> vs last cycle"


def render_telemetry_panel():
    if not st.session_state.iteration_history:
        return

    latest = st.session_state.iteration_history[-1]
    best = st.session_state.best_iteration or latest
    unresolved_tech = len(st.session_state.unresolved_issues["tech"])
    unresolved_logic = len(st.session_state.unresolved_issues["logic"])

    st.markdown(f"""
    <div class="telemetry-grid">
        <div class="telemetry-card">
            <div class="telemetry-label">TASK MODE</div>
            <div class="telemetry-value">{html.escape(st.session_state.task_mode.upper())}</div>
            <div class="telemetry-meta">{html.escape(get_task_profile()['tag'])}</div>
        </div>
        <div class="telemetry-card">
            <div class="telemetry-label">CURRENT AVG</div>
            <div class="telemetry-value">{latest['avg']:.1f}/10</div>
            <div class="telemetry-meta">{score_delta_text('avg', latest['avg'])}</div>
        </div>
        <div class="telemetry-card">
            <div class="telemetry-label">BEST ROUND</div>
            <div class="telemetry-value">CYCLE {best['iter']}</div>
            <div class="telemetry-meta">Tech {best['tech']}/10 · Logic {best['logic']}/10</div>
        </div>
        <div class="telemetry-card">
            <div class="telemetry-label">ADAPTIVE STATE</div>
            <div class="telemetry-value">{'REWRITE' if st.session_state.rewrite_mode else 'REFINE'}</div>
            <div class="telemetry-meta">Stall count {st.session_state.tech_stall_count}</div>
        </div>
        <div class="telemetry-card">
            <div class="telemetry-label">SYSTEM SIGNAL</div>
            <div class="telemetry-value">{st.session_state.repair_events} REPAIRS</div>
            <div class="telemetry-meta">{unresolved_tech} execution · {unresolved_logic} logic unresolved</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def split_architect_content(content: str):
    raw = normalize_architect_output(content)
    code_matches = list(re.finditer(r"```(\w+)?\n?(.*?)```", raw, flags=re.DOTALL))
    if not code_matches:
        insight_split = re.split(r"\n\s*(?:Architect Insights|Insights|Notes|Explanation)\s*:?\s*\n", raw, maxsplit=1, flags=re.IGNORECASE)
        if len(insight_split) == 2 and detect_code_language(insight_split[0]) == "javascript":
            return [
                ("code", "javascript", prettify_javascript(insight_split[0])),
                ("prose", insight_split[1].strip()),
            ]
        if detect_code_language(raw) == "javascript":
            return [("code", "javascript", prettify_javascript(raw))]
        return [("prose", raw)]

    blocks = []
    cursor = 0

    for match in code_matches:
        leading_text = raw[cursor:match.start()]
        if leading_text.strip():
            blocks.append(("prose", leading_text.strip()))

        language = (match.group(1) or detect_code_language(match.group(2))).lower()
        code_body = (match.group(2) or "").strip()
        code_body = re.sub(r"(?im)^.*\[object Object\].*$", "", code_body)
        code_body = re.sub(r"\n{3,}", "\n\n", code_body).strip()
        if language == "javascript":
            code_body = prettify_javascript(code_body)
        blocks.append(("code", language, code_body))
        cursor = match.end()

    trailing_text = raw[cursor:]
    if trailing_text.strip():
        blocks.append(("prose", trailing_text.strip()))

    return blocks


def render_code_block(code_body: str, language: str = "text"):
    try:
        st.code(code_body, language=language, line_numbers=True, wrap_lines=False)
    except TypeError:
        st.code(code_body, language=language)


def render_architect_content(content: str):
    blocks = split_architect_content(content)
    insights_heading_pattern = re.compile(r"^\s*(?:architect insights|insights|notes|explanation)\s*:?\s*$", re.IGNORECASE)

    for block in blocks:
        if block[0] == "code":
            _, language, code_body = block
            st.markdown("<div class='architect-section-label'>Solution Code</div>", unsafe_allow_html=True)
            render_code_block(code_body, language=language)
            continue

        prose = block[1].strip()
        if not prose:
            continue

        prose = insights_heading_pattern.sub("", prose).strip()
        prose_html = html.escape(prose).replace("\n", "<br>")
        st.markdown("<div class='architect-section-label'>Architect Insights</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='architect-notes'>{prose_html}</div>", unsafe_allow_html=True)


def execution_label() -> str:
    return "TECH" if st.session_state.task_mode == "Software & IT" else "EXECUTION"


# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<h1 style='color:#00ffa3;font-size:1.6rem;'>🛡️ ARBITER CORE</h1>", unsafe_allow_html=True)

    st.markdown("### 📊 RESOURCE DRAIN")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"<p class='cost-label'>ARCHITECT</p><p class='cost-value'>${st.session_state.costs['Architect']:.4f}</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='cost-label'>AUDITOR</p><p class='cost-value'>${st.session_state.costs['Auditor']:.4f}</p>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<p class='cost-label'>CRITICS</p><p class='cost-value'>${(st.session_state.costs['Tech Critic']+st.session_state.costs['Logic Critic']):.4f}</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='cost-label'>TOTAL</p><p class='cost-value' style='color:#fff;font-size:1.1rem;'>${st.session_state.costs['Total']:.4f}</p>", unsafe_allow_html=True)

    st.divider()

    st.markdown("<p style='font-size:0.7rem;color:#555;letter-spacing:2px;'>MODEL SELECTION</p>", unsafe_allow_html=True)
    st.session_state.task_mode = st.selectbox("Mission Profile", list(TASK_PROFILES.keys()), index=list(TASK_PROFILES.keys()).index(st.session_state.task_mode))
    p_mod   = st.selectbox("Architect Brain",  ["gpt-4o", "gpt-4o-mini"])
    c_mod_1 = st.selectbox("Auditor & Tech",   ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-pro"])
    c_mod_2 = st.selectbox("Logic Engine",     ["llama-3.3-70b-versatile"])
    st.markdown(f"<p style='font-size:0.7rem;color:#555;letter-spacing:1px;'>JSON REPAIR ENGINE: {REPAIR_MODEL}</p>", unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style='background:rgba(0,255,163,0.05);border:1px solid rgba(0,255,163,0.15);
        border-radius:10px;padding:12px;margin-top:10px;'>
            <div style='font-size:0.68rem;letter-spacing:2px;color:#7a848c;margin-bottom:6px;'>ACTIVE PROFILE</div>
            <div style='color:#f2fff9;font-weight:700;margin-bottom:6px;'>{st.session_state.task_mode}</div>
            <div style='font-size:0.76rem;color:#9aa6ad;line-height:1.6;'>{get_task_profile()['summary']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("""
    <div style='background:rgba(255,170,0,0.05);border:1px solid rgba(255,170,0,0.2);
    border-radius:6px;padding:10px;margin-top:8px;font-size:0.65rem;color:#888;line-height:1.8;'>
    💡 <b style='color:#ffaa00;'>Cost tip:</b><br>
    Use <b>gemini-2.5-flash</b> + <b>gpt-4o-mini</b> for early cycles.<br>
    Switch to <b>gpt-4o</b> only for the final pass.
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    if st.session_state.iteration_history:
        st.markdown("<p style='font-size:0.7rem;color:#555;letter-spacing:2px;'>ITERATION LOG</p>", unsafe_allow_html=True)
        for h in st.session_state.iteration_history:
            score_color = "#00ffa3" if h["avg"] >= 7 else ("#ffaa00" if h["avg"] >= 5 else "#ff4466")
            st.markdown(f"""
            <div class='iter-bar'>
                Cycle {h['iter']} &nbsp;·&nbsp;
                <span style='color:{score_color};font-weight:700;'>
                    {execution_label()[0]}:{h['tech']} L:{h['logic']} AVG:{h['avg']:.1f}
                </span>
            </div>
            """, unsafe_allow_html=True)
        st.divider()

    if st.button("🔴 EMERGENCY PURGE"):
        st.session_state.clear()
        st.rerun()

    st.markdown("""
    <div class="luca-branding">
        <div class="luca-name">Empowered by Luca Crăciun</div>
        <div style='margin-top:12px;'>
            <a href="https://github.com/lucaomul" class="luca-link">GITHUB</a>
            <a href="https://www.linkedin.com/in/gabriel-luca-craciun-25ba95295" class="luca-link">LINKEDIN</a>
        </div>
        <div style='font-size:0.6rem;color:#444;margin-top:10px;letter-spacing:2px;'>ALPHA-SYSTEM v5.0</div>
    </div>
    """, unsafe_allow_html=True)


# ── Main header ──────────────────────────────────────────────
st.markdown(
    "<h1 style='text-align:center;letter-spacing:12px;margin-bottom:40px;'>"
    "THE <span style='color:#00ffa3;'>ARBITER</span></h1>",
    unsafe_allow_html=True,
)
render_telemetry_panel()


def render_message(role: str, content: str):
    role_color = (
        "#ffaa00" if role == "Auditor"
        else "#ffffff" if role == "Architect"
        else "#00ffa3"
    )
    role_tags = {
        "Auditor": "Requirements Gate",
        "Architect": "Solution Forge",
        "Critics": "Dual Review",
    }
    role_tag = role_tags.get(role, "Agent")

    if role == "Architect":
        render_architect_content(content)
        return

    if role == "Auditor":
        body_html = f"<div style=\"margin-top:15px;line-height:1.6;\">{content}</div>"
        header_html = (
            f"<b style=\"color:{role_color};text-transform:uppercase;letter-spacing:2px;font-size:0.8rem;\">{role}</b>"
            f"<span class=\"agent-role-tag\">{role_tag}</span>"
        )
    else:
        body_html = f"<div style=\"margin-top:15px;line-height:1.6;\">{content}</div>"
        header_html = (
            f"<b style=\"color:{role_color};text-transform:uppercase;letter-spacing:2px;font-size:0.8rem;\">{role}</b>"
            f"<span class=\"agent-role-tag\">{role_tag}</span>"
        )

    card_html = textwrap.dedent(f"""\
<div class="agent-card">
{header_html}
{body_html}
</div>
""").strip()
    st.markdown(card_html, unsafe_allow_html=True)

# ── Chat history display ─────────────────────────────────────
for msg in st.session_state.messages:
    render_message(msg["role"], msg["content"])


# ════════════════════════════════════════════════
# STEP 1: Input & Audit
# ════════════════════════════════════════════════
if st.session_state.step == "input":
    st.markdown(
        f"""
        <div class='agent-card' style='padding:18px;'>
            <b style='color:#00ffa3;letter-spacing:2px;font-size:0.78rem;'>MISSION PROFILE</b>
            <div style='margin-top:10px;line-height:1.7;color:#cfd6db;'>
                <b>{st.session_state.task_mode}</b><br>
                {html.escape(get_task_profile()['summary'])}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    u_input = st.text_area(
        "OVERRIDE COMMAND:",
        placeholder="Describe your technical task in detail...",
        height=150,
    )
    if st.button("⚡ INITIALIZE COGNITIVE LOOP"):
        if u_input:
            auditor = AIAgent("Auditor", "gemini", c_mod_1, build_agent_instruction(AUDITOR_PROMPT, "Auditor"))
            task_payload = build_task_payload(u_input)
            res = auditor.ask_json(task_payload, max_retries=2)
            track_cost("Auditor", c_mod_1)

            if res.get("parse_error"):
                res = {
                    "clear": False,
                    "questions": [
                        "The Auditor returned malformed JSON. Please restate the task with stack, input/output, and constraints."
                    ],
                }

            if not res.get("clear", True):
                questions = "<br>".join([f"• {q}" for q in res.get("questions", [])])
                st.session_state.messages.append({
                    "role":    "Auditor",
                    "content": f"<b style='color:#ffaa00;'>MISSING SPECIFICATIONS:</b><br><br>{questions}",
                })
                st.session_state.current_task = task_payload
                st.session_state.step         = "clarification"
            else:
                st.session_state.current_task = task_payload
                st.session_state.step         = "negotiation"
            st.rerun()


# ════════════════════════════════════════════════
# STEP 2: Clarification
# ════════════════════════════════════════════════
elif st.session_state.step == "clarification":
    ans = st.text_input("PROVIDE ADDITIONAL DATA:")
    if st.button("RE-SYNCHRONIZE"):
        st.session_state.current_task += f"\nAdditional context: {ans}"
        st.session_state.step          = "negotiation"
        st.rerun()


# ════════════════════════════════════════════════
# STEP 3: Debate loop
# ════════════════════════════════════════════════
elif st.session_state.step == "negotiation":
    st.markdown(
        f"<p style='opacity:0.3;font-size:0.75rem;letter-spacing:1px;'>"
        f"CYCLE_INDEX: {st.session_state.iteration}</p>",
        unsafe_allow_html=True,
    )

    col_input, col_opt = st.columns([2, 1])
    with col_input:
        manual_override = st.text_input(
            "MANUAL FEEDBACK (Optional):",
            placeholder="Inject manual instructions for this cycle...",
        )
    with col_opt:
        auto_mode = st.checkbox("AUTONOMOUS MODE", value=False)
        if auto_mode:
            target_score   = st.slider("Target score", 6, 10, 8)
            max_iterations = st.number_input("Max iterations", 1, 8, 4)
        else:
            target_score   = 8
            max_iterations = 4

    if st.button("🚀 EXECUTE COGNITIVE DEBATE"):
        stop_debate = False

        while not stop_debate:
            st.session_state.iteration += 1

            with st.status(f"⚙️ Running Debate Cycle {st.session_state.iteration}...") as status:

                # ── Model selection: cheap for early rounds ──
                use_mini = (
                    auto_mode
                    and st.session_state.iteration < max_iterations
                    and st.session_state.last_avg_score < 6
                    and st.session_state.tech_stall_count == 0
                    and st.session_state.score_plateau_count == 0
                    and not st.session_state.rewrite_mode
                )
                if st.session_state.rewrite_mode or st.session_state.score_plateau_count >= 1:
                    arch_model = "gpt-4o"
                else:
                    arch_model = "gpt-4o-mini" if use_mini else p_mod

                # ── Build clean history for architect ──
                history_str = build_architect_history(manual_override)

                # ── Architect ──
                st.write(f"Architect formulating solution (model: {arch_model})...")
                proposer = AIAgent("Architect", "openai", arch_model, build_agent_instruction(PROPOSER_PROMPT, "Architect"))
                proposal = proposer.ask(st.session_state.current_task, history=history_str)
                proposal = format_architect_output(proposal)
                track_cost("Architect", arch_model)

                preflight_issues = run_local_preflight(proposal, st.session_state.current_task)
                if preflight_issues:
                    st.write("Local preflight failed. Requesting one immediate architectural repair before critic spend...")
                    repair_prompt = build_preflight_repair_prompt(
                        st.session_state.current_task,
                        proposal,
                        preflight_issues,
                    )
                    proposal = proposer.ask(repair_prompt, history=history_str)
                    proposal = format_architect_output(proposal)
                    track_cost("Architect", arch_model)
                    preflight_issues = run_local_preflight(proposal, st.session_state.current_task)

                st.session_state.messages.append({"role": "Architect", "content": proposal})
                st.session_state.current_solution = proposal

                if preflight_issues:
                    preflight_html = (
                        "<div class='score-badge danger'>LOCAL PREFLIGHT FAILED</div><br>"
                        "<b style='color:#ff6682;'>Blocked Before Critic Spend:</b><br>"
                        + "<br>".join(f"• {html.escape(issue)}" for issue in preflight_issues)
                        + "<div style='background:rgba(255,68,102,0.06);padding:12px;border-radius:8px;"
                        "margin-top:12px;border-left:3px solid #ff4466;'>"
                        "<b>COST GUARDRAIL:</b><br>"
                        "Stopped before critic calls because the architect output still failed local correctness checks."
                        "</div>"
                    )
                    st.session_state.messages.append({"role": "Critics", "content": preflight_html})
                    status.update(
                        label="🛑 Preflight blocked critic spend — architect output still failed local checks.",
                        state="complete",
                    )
                    stop_debate = True
                    break

                # ── Critics (separate prompts) ──
                st.write("Critics running independent evaluation...")
                tech_critic  = AIAgent("Tech Critic",  "gemini", c_mod_1, build_agent_instruction(TECH_CRITIC_PROMPT, "Tech Critic"))
                logic_critic = AIAgent("Logic Critic", "groq",   c_mod_2, build_agent_instruction(LOGIC_CRITIC_PROMPT, "Logic Critic"))
                repair_agent = AIAgent("JSON Repair", REPAIR_PROVIDER, REPAIR_MODEL, build_agent_instruction(JSON_REPAIR_PROMPT, "JSON Repair"))

                t_res = AIAgent.normalize_json_result(
                    tech_critic.ask_json(proposal, max_retries=2, repair_agent=repair_agent)
                )
                l_res = AIAgent.normalize_json_result(
                    logic_critic.ask_json(proposal, max_retries=2, repair_agent=repair_agent)
                )

                track_cost("Tech Critic",  c_mod_1)
                track_cost("Logic Critic", c_mod_2)
                if t_res.get("repaired"):
                    track_cost("Tech Critic", REPAIR_MODEL)
                    st.session_state.repair_events += 1
                if l_res.get("repaired"):
                    track_cost("Logic Critic", REPAIR_MODEL)
                    st.session_state.repair_events += 1

                t_score   = int(t_res.get("score", 1))
                l_score   = int(l_res.get("score", 1))
                avg_score = (t_score + l_score) / 2
                st.session_state.last_avg_score = avg_score
                update_issue_tracker(t_res, l_res, t_score)
                update_architect_memory(st.session_state.current_task, proposal, t_res, l_res)

                if not st.session_state.best_iteration or avg_score > st.session_state.best_iteration["avg"]:
                    st.session_state.best_iteration = {
                        "iter":  st.session_state.iteration,
                        "tech":  t_score,
                        "logic": l_score,
                        "avg":   avg_score,
                    }
                    st.session_state.best_solution = proposal

                badge_cls = (
                    "" if avg_score >= 7
                    else "warning" if avg_score >= 5
                    else "danger"
                )

                tech_parse_note = ""
                if t_res.get("parse_error"):
                    tech_parse_note = (
                        "<br><span style='color:#ff4466;'>Raw response preview:</span> "
                        f"<code>{t_res.get('raw_output', '')[:600]}</code>"
                    )
                elif t_res.get("repaired"):
                    tech_parse_note = "<br><span style='color:#ffaa00;'>Recovered via JSON repair.</span>"

                logic_parse_note = ""
                if l_res.get("parse_error"):
                    logic_parse_note = (
                        "<br><span style='color:#ff4466;'>Raw response preview:</span> "
                        f"<code>{l_res.get('raw_output', '')[:600]}</code>"
                    )
                elif l_res.get("repaired"):
                    logic_parse_note = "<br><span style='color:#ffaa00;'>Recovered via JSON repair.</span>"

                critique_html = f"""
                <div class="score-badge {badge_cls}">
                    {execution_label()}: {t_score}/10 &nbsp;|&nbsp; LOGIC: {l_score}/10 &nbsp;|&nbsp; AVG: {avg_score:.1f}/10
                </div><br>
                <b style='color:#00ffa3;'>{execution_label().title()} Audit:</b> {t_res.get('critique', 'No issues.')}{tech_parse_note}<br><br>
                <b style='color:#00ffa3;'>Logic Audit:</b> {l_res.get('critique', 'No issues.')}{logic_parse_note}<br>
                <div style='background:rgba(0,255,163,0.05);padding:12px;border-radius:8px;
                            margin-top:15px;border-left:3px solid #00ffa3;'>
                    <b>FIX PRIORITY:</b><br>
                    • {execution_label().title()}: {t_res.get('fix_suggestion', 'None.')}<br>
                    • Logic: {l_res.get('fix_suggestion', 'None.')}
                </div>
                <div style='background:rgba(255,170,0,0.05);padding:12px;border-radius:8px;
                            margin-top:12px;border-left:3px solid #ffaa00;'>
                    <b>ADAPTIVE MODE:</b><br>
                    • Tech stall count: {st.session_state.tech_stall_count}<br>
                    • Tech regression count: {st.session_state.tech_regression_count}<br>
                    • Recent low-tech rounds: {st.session_state.recent_low_tech_count}/3<br>
                    • Tech oscillation count: {st.session_state.tech_oscillation_count}<br>
                    • Score plateau count: {st.session_state.score_plateau_count}<br>
                    • Rewrite mode: {"ACTIVE" if st.session_state.rewrite_mode else "OFF"}
                </div>
                """
                if t_score <= 5 and (
                    st.session_state.score_plateau_count >= 1
                    or st.session_state.recent_low_tech_count >= 2
                    or st.session_state.tech_oscillation_count >= 1
                ):
                    guardrail_text = (
                        "Repeated low technical scores detected. "
                        "The app will stop after this repeated pattern instead of paying for more dead rounds."
                    )
                    critique_html += (
                        "<div style='background:rgba(255,68,102,0.06);padding:12px;border-radius:8px;"
                        "margin-top:12px;border-left:3px solid #ff4466;'>"
                        "<b>COST GUARDRAIL:</b><br>"
                        f"{guardrail_text}"
                        "</div>"
                    )
                st.session_state.messages.append({"role": "Critics", "content": critique_html})

                # ── Save iteration history ──
                st.session_state.iteration_history.append({
                    "iter":           st.session_state.iteration,
                    "tech":           t_score,
                    "logic":          l_score,
                    "avg":            avg_score,
                    "tech_critique":  t_res.get("critique", ""),
                    "logic_critique": l_res.get("critique", ""),
                    "fix":            f"Tech: {t_res.get('fix_suggestion','')} | Logic: {l_res.get('fix_suggestion','')}",
                })

                # ── Stop condition ──
                plateau_stop = (
                    auto_mode
                    and t_score <= 5
                    and st.session_state.score_plateau_count >= 1
                )
                regression_stop = (
                    auto_mode
                    and t_score <= 5
                    and st.session_state.tech_regression_count >= 1
                )
                failure_budget_stop = (
                    auto_mode
                    and st.session_state.recent_low_tech_count >= 2
                )
                oscillation_stop = (
                    auto_mode
                    and st.session_state.tech_oscillation_count >= 1
                )
                should_stop = (
                    not auto_mode
                    or plateau_stop
                    or regression_stop
                    or failure_budget_stop
                    or oscillation_stop
                    or avg_score >= target_score
                    or st.session_state.iteration >= max_iterations
                )

                if should_stop:
                    stop_debate = True
                    if oscillation_stop:
                        label = (
                            "🛑 Oscillation guardrail triggered — technical quality is bouncing in the same low band. "
                            "Stopped to avoid another unstable rewrite."
                        )
                    elif failure_budget_stop:
                        label = (
                            "🛑 Failure-budget guardrail triggered — too many recent low technical scores. "
                            "Stopped to avoid burning more budget on the same failure family."
                        )
                    elif plateau_stop:
                        label = (
                            f"🛑 Cost guardrail triggered — repeated {t_score}/{l_score} scores. "
                            "Stopped to avoid another low-value cycle."
                        )
                    elif regression_stop:
                        label = (
                            f"🛑 Regression guardrail triggered — technical score fell back to {t_score}/10. "
                            "Stopped to avoid paying for a worsening strategy."
                        )
                    else:
                        label = (
                            f"✅ Target reached — Avg: {avg_score:.1f}/10"
                            if avg_score >= target_score
                            else f"⚠️ Max iterations reached — Best: {avg_score:.1f}/10"
                        )
                    status.update(label=label, state="complete")
                else:
                    status.update(
                        label=f"Cycle {st.session_state.iteration} → {avg_score:.1f}/10 — re-iterating...",
                        state="running",
                    )

        st.rerun()

    if st.session_state.iteration > 0:
        st.divider()
        if st.button("📥 GENERATE FINAL REPORT"):
            st.session_state.step = "export"
            st.rerun()


# ════════════════════════════════════════════════
# STEP 4: Export
# ════════════════════════════════════════════════
elif st.session_state.step == "export":
    st.balloons()
    st.markdown("""
    <div class='agent-card' style='text-align:center;'>
        <h2 style='color:#00ffa3;'>MISSION COMPLETE</h2>
        <p style='opacity:0.7;'>The optimized solution is compiled and ready for deployment.</p>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.best_iteration:
        best = st.session_state.best_iteration
        st.markdown(f"""
        <div style='background:rgba(0,255,163,0.05);border:1px solid rgba(0,255,163,0.2);
        border-radius:8px;padding:16px;margin-bottom:20px;font-size:0.85rem;line-height:2;'>
            <b style='color:#00ffa3;'>Best iteration:</b> Cycle {best['iter']} &nbsp;·&nbsp;
            Tech {best['tech']}/10 &nbsp;·&nbsp; Logic {best['logic']}/10 &nbsp;·&nbsp;
            Avg {best['avg']:.1f}/10<br>
            <b style='color:#00ffa3;'>Total cost:</b> ${st.session_state.costs['Total']:.4f} &nbsp;·&nbsp;
            <b style='color:#00ffa3;'>Total iterations:</b> {st.session_state.iteration}
        </div>
        """, unsafe_allow_html=True)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    report_text = st.session_state.best_solution or st.session_state.current_solution
    clean_text = re.sub(r"<[^>]*>", "", report_text)
    pdf.multi_cell(0, 10, txt=clean_text.encode("latin-1", "replace").decode("latin-1"))
    pdf_output = pdf.output(dest="S")
    if isinstance(pdf_output, str):
        pdf_output = pdf_output.encode("latin-1")
    else:
        pdf_output = bytes(pdf_output)

    st.download_button(
        label="📥 DOWNLOAD REPORT (PDF)",
        data=pdf_output,
        file_name="Arbiter_Report.pdf",
        mime="application/pdf",
    )

    if st.button("🏁 RESTART SYSTEM"):
        st.session_state.clear()
        st.rerun()
