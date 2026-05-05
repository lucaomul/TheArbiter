import streamlit as st
import re
import html
import json
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

try:
    from fpdf import FPDF
except ModuleNotFoundError:
    FPDF = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from arbiter.core.orchestrator import ArbiterOrchestrator
from arbiter.models.state import ArbiterState
from arbiter.config.settings import SETTINGS, TASK_PROFILES, PRICES
from arbiter.infra.cache import get_cache
from arbiter.infra.memory_store import get_memory_store
from arbiter.app.ui_styles import UI_CSS

load_dotenv(PROJECT_ROOT / ".env")

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
    "costs":             {"Architect": 0.0, "Tech Critic": 0.0, "Logic Critic": 0.0, "Critic Debate": 0.0, "Janitor": 0.0, "Auditor": 0.0, "Total": 0.0},
    "step":              "input",
    "iteration":         0,
    "current_solution":  "",
    "current_task":      "",
    "last_avg_score":    0,
    "iteration_history": [],
    "best_solution":     "",
    "best_iteration":    None,
    "last_tech_score":   None,
    "task_mode":         "Software & IT",
    "pending_questions": [],
    "rewrite_mode":      False,
    "tech_stall_count":  0,
    "score_plateau_count": 0,
    "tech_regression_count": 0,
    "recent_low_tech_count": 0,
    "tech_oscillation_count": 0,
    "preflight_events":  0,
    "repair_events":     0,
    "model_usage":       [],
    "memory_stats":      {"count": 0, "task_modes": {}},
    "unresolved_issues": {"tech": [], "logic": []},
    "latest_janitor_report": {},
    "latest_result_status": "IDLE",
    "run_id": "",
    "retry_override": "",
    "audit_status": "idle",
    "provider_lock": "groq",
    "stable_mode": True,
    "manual_feedback_enabled": False,
    "manual_feedback_text": "",
    "project_note_text": "",
    "model_preset": "Starter - Free Stable",
    "manual_model_selection": False,
    "selected_models": {
        "Architect": "llama-3.3-70b-versatile",
        "Auditor": "llama-3.3-70b-versatile",
        "Tech Critic": "llama-3.3-70b-versatile",
        "Logic Critic": "llama-3.3-70b-versatile",
        "Janitor": "llama-3.1-8b-instant",
        "Repair": "llama-3.1-8b-instant",
    },
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── CSS ──────────────────────────────────────────────────────
st.markdown(UI_CSS, unsafe_allow_html=True)


MODEL_PRESETS = {
    "Starter - Free Stable": {
        "description": "Best default for most people: cheap, stable, and easy to trust.",
        "provider_lock": "groq",
        "stable_mode": True,
        "models": {
            "Architect": "llama-3.3-70b-versatile",
            "Auditor": "llama-3.3-70b-versatile",
            "Tech Critic": "llama-3.3-70b-versatile",
            "Logic Critic": "llama-3.3-70b-versatile",
            "Janitor": "llama-3.1-8b-instant",
            "Repair": "llama-3.1-8b-instant",
        },
    },
    "Cheap Test - Groq Lite": {
        "description": "Lowest-cost Groq-only setup for quick tests, rough iterations, and lighter prompts.",
        "provider_lock": "groq",
        "stable_mode": True,
        "models": {
            "Architect": "llama-3.1-8b-instant",
            "Auditor": "llama-3.1-8b-instant",
            "Tech Critic": "llama-3.1-8b-instant",
            "Logic Critic": "llama-3.1-8b-instant",
            "Janitor": "llama-3.1-8b-instant",
            "Repair": "llama-3.1-8b-instant",
        },
    },
    "Software Builder": {
        "description": "Best preset for coding and technical build tasks with stronger checking.",
        "provider_lock": "mixed",
        "stable_mode": True,
        "models": {
            "Architect": "llama-3.3-70b-versatile",
            "Auditor": "claude-3-5-haiku-latest",
            "Tech Critic": "gemini-2.5-pro",
            "Logic Critic": "llama-3.3-70b-versatile",
            "Janitor": "llama-3.1-8b-instant",
            "Repair": "llama-3.1-8b-instant",
        },
    },
    "Strategy & Writing": {
        "description": "Best for marketing, writing, business, and planning tasks where logic and structure matter most.",
        "provider_lock": "mixed",
        "stable_mode": True,
        "models": {
            "Architect": "claude-sonnet-4-20250514",
            "Auditor": "claude-3-5-haiku-latest",
            "Tech Critic": "gemini-2.5-flash",
            "Logic Critic": "claude-sonnet-4-20250514",
            "Janitor": "claude-3-5-haiku-latest",
            "Repair": "llama-3.1-8b-instant",
        },
    },
    "Business Operator": {
        "description": "Balanced preset for workflows, SOPs, service design, and operations work.",
        "provider_lock": "mixed",
        "stable_mode": True,
        "models": {
            "Architect": "claude-sonnet-4-20250514",
            "Auditor": "llama-3.3-70b-versatile",
            "Tech Critic": "gemini-2.5-pro",
            "Logic Critic": "claude-sonnet-4-20250514",
            "Janitor": "claude-3-5-haiku-latest",
            "Repair": "llama-3.1-8b-instant",
        },
    },
    "Premium Claude Cross-Check": {
        "description": "High-quality mixed setup for difficult tasks when you want Claude in the main loop.",
        "provider_lock": "mixed",
        "stable_mode": False,
        "models": {
            "Architect": "claude-sonnet-4-20250514",
            "Auditor": "claude-3-5-haiku-latest",
            "Tech Critic": "gemini-2.5-pro",
            "Logic Critic": "claude-sonnet-4-20250514",
            "Janitor": "claude-3-5-haiku-latest",
            "Repair": "gpt-4o-mini",
        },
    },
}


# ── Helpers ──────────────────────────────────────────────────
def reset_run_state(keep_task_mode: bool = True):
    preserved_task_mode = st.session_state.task_mode if keep_task_mode else defaults["task_mode"]
    for key, value in defaults.items():
        if key == "task_mode":
            continue
        if isinstance(value, dict):
            st.session_state[key] = value.copy()
        elif isinstance(value, list):
            st.session_state[key] = list(value)
        else:
            st.session_state[key] = value
    st.session_state.task_mode = preserved_task_mode
    st.session_state.audit_status = "idle"


def get_available_models_for_role(role: str) -> list:
    from arbiter.infra.plugin_registry import get_plugin_registry

    registry = get_plugin_registry()
    models = [plugin.model_id for plugin in registry.candidates_for_role(role)]
    if role == "Logic Critic" and "gemini-2.5-flash" not in models:
        models.append("gemini-2.5-flash")
    return models


def apply_model_preset(name: str):
    preset = MODEL_PRESETS.get(name)
    if not preset:
        return
    st.session_state.provider_lock = preset["provider_lock"]
    st.session_state.stable_mode = preset["stable_mode"]
    st.session_state.selected_models = dict(preset["models"])


def build_retry_context() -> str:
    if not st.session_state.iteration_history:
        return st.session_state.retry_override or ""

    latest = st.session_state.iteration_history[-1]
    lines = []
    if st.session_state.retry_override:
        lines.append(st.session_state.retry_override.strip())
    if latest.get("preflight_issues"):
        lines.append("PREVIOUS PREFLIGHT ISSUES:")
        lines.extend(f"- {item}" for item in latest.get("preflight_issues", []))
    if latest.get("janitor_summary"):
        lines.append(f"JANITOR SUMMARY: {latest.get('janitor_summary')}")
    if latest.get("janitor_repair_brief"):
        lines.append("JANITOR REPAIR BRIEF:")
        lines.extend(f"- {item}" for item in latest.get("janitor_repair_brief", []))
    if st.session_state.current_solution:
        snippet = str(st.session_state.current_solution).strip()
        if len(snippet) > 1600:
            snippet = snippet[:1600] + "\n[truncated previous solution snapshot]"
        lines.append("LAST ATTEMPT SOLUTION SNAPSHOT:")
        lines.append(snippet)
    return "\n".join(line for line in lines if str(line).strip()).strip()


def build_effective_manual_override() -> str:
    janitor_context = build_retry_context()
    manual_text = str(st.session_state.manual_feedback_text or "").strip()
    if st.session_state.manual_feedback_enabled and manual_text:
        if janitor_context:
            return (
                f"{janitor_context}\n\n"
                "MANUAL FEEDBACK / PROJECT INSIGHTS:\n"
                f"{manual_text}"
            ).strip()
        return (
            "MANUAL FEEDBACK / PROJECT INSIGHTS:\n"
            f"{manual_text}"
        ).strip()
    return janitor_context


def format_retry_after(seconds) -> str:
    try:
        total = max(0, int(float(seconds)))
    except Exception:
        return ""
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_provider_error_message(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""

    parsed = None
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None

    if parsed and parsed.get("provider_error"):
        provider = str(parsed.get("provider", "provider")).upper()
        model = parsed.get("model") or "selected model"
        error_type = parsed.get("error_type") or "provider_error"
        retry_after = format_retry_after(parsed.get("retry_after_seconds"))
        if error_type == "rate_limit":
            suffix = f" Available again in about {retry_after}." if retry_after else ""
            return f"{provider} rate limit reached for `{model}`.{suffix}"
        if error_type == "model_decommissioned":
            return f"{provider} reported that `{model}` is no longer supported."
        critique = parsed.get("critique") or parsed.get("error") or text
        return str(critique)

    lower = text.lower()
    if "rate limit reached for model" in lower and "please try again in" in lower:
        model_match = re.search(r"model [`']?([^`' ]+)[`']?", text, re.IGNORECASE)
        retry_match = re.search(r"please try again in ([0-9hms\.\s]+)", text, re.IGNORECASE)
        provider = "Groq" if "groq" in lower else "Provider"
        model = model_match.group(1) if model_match else "selected model"
        retry = retry_match.group(1).strip().rstrip(".") if retry_match else ""
        suffix = f" Available again in about {retry}." if retry else ""
        return f"{provider} rate limit reached for `{model}`.{suffix}"

    return text


def detect_code_language(raw: str) -> str:
    text = html.unescape(str(raw)).strip()
    js_signals = [
        r"\bfunction\s+\w+\s*\(",
        r"\b(?:const|let|var)\s+\w+\s*=",
        r"=>\s*\{",
        r"\bconsole\.log\b",
    ]
    py_signals = [
        r"^\s*def\s+\w+\s*\(",
        r"^\s*import\s+\w+",
        r"^\s*from\s+\w+\s+import\s+",
    ]
    if any(re.search(p, text, re.MULTILINE) for p in js_signals):
        return "javascript"
    if any(re.search(p, text, re.MULTILINE) for p in py_signals):
        return "python"
    return "text"


def render_architect_content(content: str):
    """
    Renders architect output:
    - Code blocks → st.code() with line numbers (preserves styling)
    - Prose → styled notes panel
    """
    raw = html.unescape(str(content)).strip()
    raw = re.sub(r"^(?:JAVASCRIPT|JavaScript|JS)\s*:?[\n ]+", "", raw)
    raw = re.sub(r"(?im)^.*\[object Object\].*$", "", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
    show_line_numbers = st.session_state.task_mode == "Software & IT"

    code_matches = list(re.finditer(r"```(\w+)?\n?(.*?)```", raw, flags=re.DOTALL))

    if not code_matches:
        # No code blocks — check if it's raw code
        lang = detect_code_language(raw)
        if lang != "text":
            st.markdown('<div class="architect-section-label">Solution Code</div>', unsafe_allow_html=True)
            st.code(raw, language=lang, line_numbers=show_line_numbers)
        else:
            prose_html = html.escape(raw).replace("\n", "<br>")
            st.markdown('<div class="architect-section-label">Architect Response</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="architect-notes">{prose_html}</div>', unsafe_allow_html=True)
        return

    cursor = 0
    for match in code_matches:
        # Leading prose
        leading = raw[cursor:match.start()].strip()
        if leading:
            # Strip common filler headings
            leading = re.sub(
                r"^(Here(?:'s| is).{0,180}?:\s*)",
                "", leading, flags=re.IGNORECASE | re.DOTALL
            ).strip()
            if leading:
                insights_pattern = re.compile(
                    r"^\s*(?:architect insights|insights|notes|explanation)\s*:?\s*$",
                    re.IGNORECASE
                )
                leading = insights_pattern.sub("", leading).strip()
                if leading:
                    prose_html = html.escape(leading).replace("\n", "<br>")
                    st.markdown('<div class="architect-section-label">Architect Insights</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="architect-notes">{prose_html}</div>', unsafe_allow_html=True)

        # Code block
        lang      = (match.group(1) or "").lower() or detect_code_language(match.group(2) or "")
        code_body = (match.group(2) or "").strip()
        code_body = re.sub(r"(?im)^.*\[object Object\].*$", "", code_body)
        code_body = re.sub(r"\n{3,}", "\n\n", code_body).strip()

        if lang == "javascript":
            st.markdown('<div class="architect-section-label">Solution Code</div>', unsafe_allow_html=True)
            st.code(code_body, language="javascript", line_numbers=show_line_numbers)
        elif lang in ("python", "py"):
            st.markdown('<div class="architect-section-label">Solution Code</div>', unsafe_allow_html=True)
            st.code(code_body, language="python", line_numbers=show_line_numbers)
        else:
            st.markdown('<div class="architect-section-label">Solution Code</div>', unsafe_allow_html=True)
            st.code(code_body, language=lang or "text", line_numbers=show_line_numbers)

        cursor = match.end()

    # Trailing prose
    trailing = raw[cursor:].strip()
    if trailing:
        insights_pattern = re.compile(
            r"^\s*(?:architect insights|insights|notes|explanation)\s*:?\s*$",
            re.IGNORECASE
        )
        trailing = insights_pattern.sub("", trailing).strip()
        if trailing:
            prose_html = html.escape(trailing).replace("\n", "<br>")
            st.markdown('<div class="architect-section-label">Architect Insights</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="architect-notes">{prose_html}</div>', unsafe_allow_html=True)


def render_message(role: str, content: str):
    role_color = (
        "#ffaa00" if role == "Auditor"
        else "#ffffff" if role == "Architect"
        else "#00ffa3"
    )
    if role == "Architect":
        render_architect_content(content)
        return
    if role == "Critics":
        return

    st.markdown(f"""
    <div class="agent-card">
        <b style="color:{role_color};text-transform:uppercase;letter-spacing:2px;font-size:0.8rem;">{role}</b>
        <div style="margin-top:15px;line-height:1.6;">{content}</div>
    </div>
    """, unsafe_allow_html=True)


def sync_state_from_result(result):
    """Push orchestrator result back into Streamlit session state for UI."""
    st.session_state.messages          = result.messages
    merged_costs = dict(st.session_state.costs)
    for role, amount in result.costs.items():
        if role == "Total":
            continue
        merged_costs[role] = merged_costs.get(role, 0.0) + amount
    merged_costs["Total"] = sum(value for key, value in merged_costs.items() if key != "Total")
    st.session_state.costs             = merged_costs
    st.session_state.iteration         = result.iteration_count
    st.session_state.iteration_history = result.iteration_history
    st.session_state.best_solution     = result.best_solution
    st.session_state.best_iteration    = result.best_iteration
    st.session_state.current_solution  = result.debug_info.get("current_solution", result.best_solution)
    if result.iteration_history:
        st.session_state.last_avg_score  = result.iteration_history[-1]["avg"]
        st.session_state.last_tech_score = result.iteration_history[-1]["tech"]
    st.session_state.rewrite_mode = result.debug_info.get("rewrite_mode", False)
    st.session_state.tech_stall_count = result.debug_info.get("tech_stall_count", 0)
    st.session_state.score_plateau_count = result.debug_info.get("score_plateau_count", 0)
    st.session_state.tech_regression_count = result.debug_info.get("tech_regression_count", 0)
    st.session_state.recent_low_tech_count = result.debug_info.get("recent_low_tech_count", 0)
    st.session_state.tech_oscillation_count = result.debug_info.get("tech_oscillation_count", 0)
    st.session_state.preflight_events = result.debug_info.get("preflight_events", 0)
    st.session_state.repair_events = result.debug_info.get("repair_events", 0)
    st.session_state.model_usage = result.debug_info.get("model_usage", [])
    st.session_state.memory_stats = result.debug_info.get("memory_stats", {"count": 0, "task_modes": {}})
    st.session_state.unresolved_issues = result.debug_info.get("unresolved_issues", {"tech": [], "logic": []})
    st.session_state.latest_janitor_report = result.debug_info.get("latest_janitor_report", {})
    st.session_state.latest_result_status = result.debug_info.get("latest_result_status", "VALID")
    st.session_state.run_id = result.debug_info.get("run_id", "")


def render_telemetry_panel():
    if not st.session_state.iteration_history:
        return

    latest = st.session_state.iteration_history[-1]
    best = st.session_state.best_iteration
    weights = TASK_PROFILES[st.session_state.task_mode].get("score_weights", {"tech": 0.5, "logic": 0.5})
    current_label = "Diagnostic Avg" if latest.get("score_status") == "diagnostic" else "Current Avg"
    current_meta_prefix = "Diagnostic only" if latest.get("score_status") == "diagnostic" else "Tech"
    if best:
        best_value = f"CYCLE {best['iter']}"
        best_meta = f"Tech {best['tech']}/10 · Logic {best['logic']}/10 · Weighted Avg {best['avg']:.1f}"
    else:
        best_value = "NO VALID ROUND"
        best_meta = "Only diagnostic or blocked runs so far"

    st.markdown(f"""
    <div class="telemetry-grid">
        <div class="telemetry-card">
            <div class="telemetry-label">TASK MODE</div>
            <div class="telemetry-value">{html.escape(st.session_state.task_mode.upper())}</div>
            <div class="telemetry-meta">{html.escape(TASK_PROFILES[st.session_state.task_mode]['tag'])}</div>
        </div>
        <div class="telemetry-card">
            <div class="telemetry-label">{current_label.upper()}</div>
            <div class="telemetry-value">{latest['avg']:.1f}/10</div>
            <div class="telemetry-meta">{current_meta_prefix} {latest['tech']}/10 · Logic {latest['logic']}/10 · Weights T {weights['tech']:.2f} / L {weights['logic']:.2f}</div>
        </div>
        <div class="telemetry-card">
            <div class="telemetry-label">BEST ROUND</div>
            <div class="telemetry-value">{best_value}</div>
            <div class="telemetry-meta">{best_meta}</div>
        </div>
        <div class="telemetry-card">
            <div class="telemetry-label">ADAPTIVE STATE</div>
            <div class="telemetry-value">{'STABLE' if st.session_state.stable_mode else ('REWRITE' if st.session_state.rewrite_mode else 'REFINE')}</div>
            <div class="telemetry-meta">Provider {html.escape(st.session_state.provider_lock.upper())} · Preflight {st.session_state.preflight_events} · Repairs {st.session_state.repair_events}</div>
        </div>
        <div class="telemetry-card">
            <div class="telemetry-label">MEMORY</div>
            <div class="telemetry-value">{st.session_state.memory_stats.get('count', 0)} ENTRIES</div>
            <div class="telemetry-meta">Backend: {str(st.session_state.memory_stats.get('backend', 'native')).upper()} · Run {html.escape(st.session_state.run_id or 'n/a')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_memory_panel():
    if not st.session_state.iteration_history:
        return

    latest = st.session_state.iteration_history[-1]
    janitor_resolved = latest.get("janitor_resolved") or []
    janitor_pending = latest.get("janitor_pending") or []
    janitor_regressed = latest.get("janitor_regressed") or []
    memory_status = str(latest.get("memory_status", "ACCEPT"))
    memory_consensus = float(latest.get("memory_consensus_score", 0.0) or 0.0)
    memory_reasons = latest.get("memory_reasons") or []
    related_memory_ids = latest.get("related_memory_ids") or []
    lifecycle_stats = st.session_state.memory_stats.get("memory_lifecycle", {}) or {}
    project_notes_count = int(st.session_state.memory_stats.get("project_notes_count", 0) or 0)
    active_count = int(lifecycle_stats.get("active", 0) or 0)
    caution_count = int(lifecycle_stats.get("caution", 0) or 0)
    conflicted_count = int(lifecycle_stats.get("conflicted", 0) or 0)
    obsolete_count = int(lifecycle_stats.get("obsolete", 0) or 0)

    with st.expander("Working Memory", expanded=False):
        top = st.columns(6)
        top[0].metric("Current Entry", memory_status)
        top[1].metric("Consensus", f"{memory_consensus:.2f}")
        top[2].metric("Active", active_count)
        top[3].metric("Caution", caution_count)
        top[4].metric("Conflicted", conflicted_count)
        top[5].metric("Project Notes", project_notes_count)
        if obsolete_count:
            st.caption(f"Obsolete memories archived from active retrieval: {obsolete_count}")

        if memory_reasons:
            st.markdown("**Current Memory Trust Notes**")
            for reason in memory_reasons:
                st.markdown(f"- {reason}")

        if related_memory_ids:
            st.markdown("**Related Retrieved Memory IDs**")
            st.caption(", ".join(related_memory_ids[:5]))

        cols = st.columns(3)
        sections = [
            (cols[0], "Resolved", janitor_resolved),
            (cols[1], "Still Broken", janitor_pending),
            (cols[2], "Regressed Or New", janitor_regressed),
        ]
        for col, title, items in sections:
            with col:
                st.caption(title)
                if items:
                    for item in items:
                        st.markdown(f"- {item}")
                else:
                    st.caption("None")


def render_review_panel():
    if not st.session_state.iteration_history:
        return

    latest = st.session_state.iteration_history[-1]
    validity_status = latest.get("validity_status", "VALID")
    score_status = latest.get("score_status", "final")
    review_confidence = latest.get("review_confidence", "normal")
    overlap = float(latest.get("critic_overlap", 0.0) or 0.0)
    redundancy = bool(latest.get("critic_redundancy", False))
    janitor = {
        "summary": latest.get("janitor_summary", ""),
        "primary_subsystem": latest.get("janitor_primary_subsystem", ""),
        "resolved": latest.get("janitor_resolved", []),
        "pending": latest.get("janitor_pending", []),
        "regressed": latest.get("janitor_regressed", []),
        "preserve": latest.get("janitor_preserve", []),
        "repair_brief": latest.get("janitor_repair_brief", []),
    }
    memory_status = latest.get("memory_status", "ACCEPT")
    memory_consensus = float(latest.get("memory_consensus_score", 0.0) or 0.0)
    memory_reasons = latest.get("memory_reasons", []) or []
    tech_confirmed = latest.get("tech_confirmed_defects", []) or []
    tech_risks = latest.get("tech_risks", []) or []
    tech_improvements = latest.get("tech_improvements", []) or []
    logic_confirmed = latest.get("logic_confirmed_defects", []) or []
    logic_risks = latest.get("logic_risks", []) or []
    logic_improvements = latest.get("logic_improvements", []) or []

    status_note = (
        "The selected and fallback generation models were unavailable or rate-limited, so no valid solution was produced this round."
        if validity_status == "PROVIDER LIMITED"
        else
        "Diagnostic only. Preflight found a structural issue, so this score is not a final pass."
        if validity_status == "DIAGNOSTIC ONLY"
        else "One or more review agents failed, so this score is diagnostic and not eligible as a final pass."
        if validity_status == "REVIEW DEGRADED"
        else "Eligible as a final scored result."
    )

    def render_list(items, empty_text="None"):
        if items:
            for item in items:
                st.markdown(f"- {item}")
        else:
            st.caption(empty_text)

    with st.container(border=True):
        st.subheader("Review Summary")
        metric_cols = st.columns(5)
        metric_cols[0].metric("Status", validity_status)
        metric_cols[1].metric("Tech", f"{latest['tech']}/10")
        metric_cols[2].metric("Logic", f"{latest['logic']}/10")
        metric_cols[3].metric("Average", f"{latest['avg']:.1f}/10")
        metric_cols[4].metric("Confidence", review_confidence.upper())
        st.caption(f"Score type: {score_status.upper()} · {status_note}")

        if latest.get("preflight_issues"):
            st.error("Preflight Findings")
            render_list(latest.get("preflight_issues", []))

        provider_error_messages = []
        for critique in (latest.get("tech_critique", ""), latest.get("logic_critique", "")):
            raw = str(critique or "")
            lower = raw.lower()
            if lower.startswith("llm call failed") or "api error:" in lower or "model_decommissioned" in lower:
                provider_error_messages.append(format_provider_error_message(raw))
        if provider_error_messages:
            st.warning("Reviewer / provider error detected during this round.")
            render_list(provider_error_messages)

        if redundancy:
            st.warning(
                f"Critic redundancy detected. Tech and Logic feedback overlapped heavily ({overlap:.0%} token overlap). "
                "Arbiter reran the Logic Critic with a narrower brief and lowered review confidence."
            )

        with st.container(border=True):
            st.markdown("**Memory Consensus**")
            st.write(f"Status: {memory_status}")
            st.write(f"Consensus Score: {memory_consensus:.2f}")
            render_list(memory_reasons, empty_text="No memory notes.")

        st.markdown("### Janitor Verdict")
        st.markdown("**Summary**")
        st.write(janitor["summary"] or "None")
        st.markdown("**Primary Subsystem**")
        st.write(janitor["primary_subsystem"] or "None")

        cols = st.columns(3)
        with cols[0]:
            st.markdown("**Still Broken**")
            render_list(janitor["pending"])
        with cols[1]:
            st.markdown("**Preserve**")
            render_list(janitor["preserve"])
        with cols[2]:
            st.markdown("**Repair Brief**")
            render_list(janitor["repair_brief"])

        if validity_status in {"DIAGNOSTIC ONLY", "REVIEW DEGRADED", "PROVIDER LIMITED"}:
            retry_override = "\n".join(
                janitor.get("repair_brief", [])
                or latest.get("preflight_issues", [])
                or latest.get("tech_repair_contract", [])
                or latest.get("logic_repair_contract", [])
            )
            st.session_state.retry_override = retry_override
            st.info(
                "Janitor will be used automatically as the default retry source on the next run. "
                "If you want to add your own notes, use the Manual Feedback Checkpoint in the run panel."
            )
            if st.button("Open Retry Checkpoint", key="open_retry_checkpoint"):
                st.session_state.step = "negotiation"
                st.rerun()

    with st.expander("Tech Critic Details"):
        st.markdown(f"**Technical Audit:** {latest.get('tech_critique', 'No issues.')}")
        st.markdown("**Confirmed Defects**")
        render_list(tech_confirmed)
        st.markdown("**Risks / Assumptions**")
        render_list(tech_risks)
        st.markdown("**Improvements**")
        render_list(tech_improvements)
        if latest.get("tech_repair_contract"):
            st.markdown("**Tech Repair Contract**")
            render_list(latest.get("tech_repair_contract", []))

    with st.expander("Logic Critic Details"):
        st.markdown(f"**Logic Audit:** {latest.get('logic_critique', 'No issues.')}")
        st.markdown("**Confirmed Defects**")
        render_list(logic_confirmed)
        st.markdown("**Risks / Assumptions**")
        render_list(logic_risks)
        st.markdown("**Improvements**")
        render_list(logic_improvements)
        if latest.get("logic_repair_contract"):
            st.markdown("**Logic Repair Contract**")
            render_list(latest.get("logic_repair_contract", []))


# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<h1 style='color:#00ffa3;font-size:1.6rem;'>🛡️ ARBITER CORE</h1>", unsafe_allow_html=True)

    st.markdown("### 📊 RESOURCE DRAIN")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"<p class='cost-label'>ARCHITECT</p><p class='cost-value'>${st.session_state.costs['Architect']:.4f}</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='cost-label'>AUDITOR</p><p class='cost-value'>${st.session_state.costs['Auditor']:.4f}</p>", unsafe_allow_html=True)
    with c2:
        critic_total = (
            st.session_state.costs["Tech Critic"]
            + st.session_state.costs["Logic Critic"]
            + st.session_state.costs["Critic Debate"]
            + st.session_state.costs["Janitor"]
        )
        st.markdown(f"<p class='cost-label'>CRITICS</p><p class='cost-value'>${critic_total:.4f}</p>", unsafe_allow_html=True)
        st.markdown(f"<p class='cost-label'>TOTAL</p><p class='cost-value' style='color:#fff;font-size:1.1rem;'>${st.session_state.costs['Total']:.4f}</p>", unsafe_allow_html=True)

    if st.session_state.model_usage:
        latest_models = {}
        for item in st.session_state.model_usage:
            latest_models[item["role"]] = item["model"]
        st.markdown("<p style='font-size:0.7rem;color:#555;letter-spacing:2px;margin-top:12px;'>ACTIVE MODELS</p>", unsafe_allow_html=True)
        for role in ("Architect", "Architect Repair", "Auditor", "Tech Critic", "Logic Critic", "Critic Debate", "Janitor"):
            if role in latest_models:
                st.markdown(
                    f"<p class='cost-label'>{role.upper()}</p><p class='cost-value' style='font-size:0.75rem;'>{latest_models[role]}</p>",
                    unsafe_allow_html=True,
                )

    st.divider()

    st.markdown("<p style='font-size:0.7rem;color:#555;letter-spacing:2px;'>MISSION PROFILE</p>", unsafe_allow_html=True)
    st.session_state.task_mode = st.selectbox(
        "Task Mode",
        list(TASK_PROFILES.keys()),
        index=list(TASK_PROFILES.keys()).index(st.session_state.task_mode),
    )
    st.markdown("<p style='font-size:0.7rem;color:#555;letter-spacing:2px;'>AI STRATEGY</p>", unsafe_allow_html=True)
    preset_names = list(MODEL_PRESETS.keys())
    preset_name = st.selectbox(
        "AI Preset",
        preset_names,
        index=preset_names.index(st.session_state.model_preset) if st.session_state.model_preset in preset_names else 0,
        help="Start from a named model pack instead of guessing each role manually.",
    )
    if preset_name != st.session_state.model_preset:
        st.session_state.model_preset = preset_name
        if not st.session_state.manual_model_selection:
            apply_model_preset(preset_name)

    st.caption(MODEL_PRESETS[st.session_state.model_preset]["description"])
    st.session_state.manual_model_selection = st.checkbox(
        "Customize AI Roles Manually",
        value=st.session_state.manual_model_selection,
        help="Turn this on if you want to pick the model for each role yourself.",
    )

    if not st.session_state.manual_model_selection:
        apply_model_preset(st.session_state.model_preset)

    provider_lock_option = st.selectbox(
        "Provider Lock",
        ["groq", "gemini", "openai", "anthropic", "mixed"],
        index=["groq", "gemini", "openai", "anthropic", "mixed"].index(st.session_state.provider_lock if st.session_state.provider_lock in {"groq", "gemini", "openai", "anthropic", "mixed"} else "groq"),
        disabled=not st.session_state.manual_model_selection,
    )
    st.session_state.provider_lock = provider_lock_option
    st.session_state.stable_mode = st.toggle(
        "Stable Mode",
        value=st.session_state.stable_mode,
        help="Keeps the selected provider/model family fixed, disables exploration, and prevents hidden premium escalation.",
        disabled=not st.session_state.manual_model_selection,
    )

    st.markdown("<p style='font-size:0.7rem;color:#555;letter-spacing:2px;margin-top:12px;'>MODEL SELECTION</p>", unsafe_allow_html=True)
    role_order = ["Architect", "Auditor", "Tech Critic", "Logic Critic", "Janitor", "Repair"]
    role_labels = {
        "Architect": "Architect Brain",
        "Auditor": "Auditor",
        "Tech Critic": "Tech Critic",
        "Logic Critic": "Logic Engine",
        "Janitor": "Janitor",
        "Repair": "Repair",
    }
    role_models = {}
    for role in role_order:
        options = get_available_models_for_role(role)
        current_value = st.session_state.selected_models.get(role, options[0] if options else "")
        if current_value not in options and options:
            current_value = options[0]
        chosen = st.selectbox(
            role_labels[role],
            options,
            index=options.index(current_value) if options and current_value in options else 0,
            key=f"role_model_{role}",
            disabled=not st.session_state.manual_model_selection,
        )
        role_models[role] = chosen
    if st.session_state.manual_model_selection:
        st.session_state.selected_models = role_models
    else:
        role_models = dict(st.session_state.selected_models)

    # Push model choices into selector overrides
    from arbiter.infra.model_selector import get_model_selector
    from arbiter.infra.plugin_registry import provider_for_model
    sel = get_model_selector()
    sel.set_provider_lock("" if provider_lock_option == "mixed" else provider_lock_option)
    for role, model in role_models.items():
        sel.set_override(role, model)

    if any(provider_for_model(model, "") == "anthropic" for model in role_models.values()) and not os.getenv("ANTHROPIC_API_KEY"):
        st.warning("Claude/Anthropic models are selected, but `ANTHROPIC_API_KEY` is not set in your `.env` yet.")

    st.markdown("""
    <div style='background:rgba(255,170,0,0.05);border:1px solid rgba(255,170,0,0.2);
    border-radius:6px;padding:10px;margin-top:8px;font-size:0.65rem;color:#888;line-height:1.8;'>
    💡 <b style='color:#ffaa00;'>Preset tip:</b><br>
    Start with a named preset if you are not sure which AIs to use.<br>
    Turn on manual customization only when you want to control each role yourself.
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
                    T:{h['tech']} L:{h['logic']} AVG:{h['avg']:.1f}
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
        <div style='font-size:0.6rem;color:#444;margin-top:10px;letter-spacing:2px;'>ALPHA-SYSTEM v7.0</div>
    </div>
    """, unsafe_allow_html=True)


# ── Main header ──────────────────────────────────────────────
st.markdown(
    "<h1 style='text-align:center;letter-spacing:12px;margin-bottom:40px;'>"
    "THE <span style='color:#00ffa3;'>ARBITER</span></h1>",
    unsafe_allow_html=True,
)
render_telemetry_panel()

# ── Chat history ─────────────────────────────────────────────
for msg in st.session_state.messages:
    render_message(msg["role"], msg["content"])

render_review_panel()
render_memory_panel()


# ════════════════════════════════════════════════
# STEP 1: Input
# ════════════════════════════════════════════════
if st.session_state.step == "input":
    with st.form("arbiter_input_form", clear_on_submit=False):
        u_input = st.text_area(
            "OVERRIDE COMMAND:",
            placeholder="Describe your technical task in detail...",
            height=150,
        )
        submitted = st.form_submit_button("⚡ INITIALIZE COGNITIVE LOOP")
    st.caption("Arbiter will either ask for missing context or confirm that the task is clear enough to proceed.")
    if submitted and u_input:
        reset_run_state(keep_task_mode=True)
        st.session_state.current_task = u_input
        st.session_state.step = "audit"
        st.rerun()


# ════════════════════════════════════════════════
# STEP 2: Audit
# ════════════════════════════════════════════════
elif st.session_state.step == "audit":
    get_cache().clear()
    with st.spinner("Auditor checking task clarity..."):
        orchestrator = ArbiterOrchestrator(
            task_mode=st.session_state.task_mode,
            auto_mode=False,       # single audit run
            max_iterations=0,      # don't iterate yet
            stable_mode=st.session_state.stable_mode,
        )
        result = orchestrator.run(user_input=st.session_state.current_task)

    merged_costs = dict(st.session_state.costs)
    for role, amount in result.costs.items():
        if role == "Total":
            continue
        merged_costs[role] = merged_costs.get(role, 0.0) + amount
    merged_costs["Total"] = sum(value for key, value in merged_costs.items() if key != "Total")
    st.session_state.costs = merged_costs
    if result.debug_info.get("model_usage"):
        st.session_state.model_usage = result.debug_info.get("model_usage", [])

    if result.debug_info.get("needs_clarification"):
        st.session_state.pending_questions = result.debug_info.get("questions", [])
        st.session_state.audit_status = "needs_clarification"
        st.session_state.step = "clarification"
        st.rerun()
    else:
        st.session_state.pending_questions = []
        st.session_state.audit_status = "passed"
        st.session_state.step = "negotiation"
        st.rerun()


# ════════════════════════════════════════════════
# STEP 3: Clarification
# ════════════════════════════════════════════════
elif st.session_state.step == "clarification":
    if st.session_state.pending_questions:
        st.info("Auditor needs a bit more context before the build starts.")
        for question in st.session_state.pending_questions:
            st.markdown(f"- {question}")
    with st.form("arbiter_clarification_form", clear_on_submit=False):
        ans = st.text_area("PROVIDE ADDITIONAL DATA:", height=120)
        clarify_submitted = st.form_submit_button("RE-SYNCHRONIZE")
    if clarify_submitted:
        if ans.strip():
            st.session_state.current_task += f" | Additional context: {ans.strip()}"
        st.session_state.step = "negotiation"
        st.rerun()


# ════════════════════════════════════════════════
# STEP 4: Negotiation (main debate loop)
# ════════════════════════════════════════════════
elif st.session_state.step == "negotiation":
    if st.session_state.audit_status == "passed":
        st.success("Auditor check passed. The task is specific enough to proceed.")
    st.markdown(
        f"<p style='opacity:0.3;font-size:0.75rem;letter-spacing:1px;'>"
        f"CYCLE_INDEX: {st.session_state.iteration}</p>",
        unsafe_allow_html=True,
    )

    col_input, col_opt = st.columns([2, 1])
    with col_input:
        janitor_context = build_retry_context()
        if janitor_context:
            with st.expander("Janitor Retry Context", expanded=True):
                st.caption("This is the default rerun brief. Arbiter will use it automatically on the next run.")
                st.text_area(
                    "Janitor Context",
                    value=janitor_context,
                    height=220,
                    disabled=True,
                    label_visibility="collapsed",
                )

        st.session_state.manual_feedback_enabled = st.checkbox(
            "Add Manual Feedback Checkpoint",
            value=st.session_state.manual_feedback_enabled,
            help="Turn this on only when you want to inject personal instructions or extra project context.",
        )
        if st.session_state.manual_feedback_enabled:
            st.session_state.manual_feedback_text = st.text_area(
                "Manual Feedback / Extra Project Context",
                value=st.session_state.manual_feedback_text,
                placeholder="Add personal feedback, constraints, product context, or extra instructions here...",
                height=140,
            )
        else:
            st.session_state.manual_feedback_text = ""

        memory_store = get_memory_store()
        with st.expander("Project Memory / Notes", expanded=False):
            st.caption("Save durable project insights here. These notes persist across runs and can be retrieved automatically for similar future tasks.")
            if hasattr(memory_store, "retrieve_project_notes"):
                relevant_notes = memory_store.retrieve_project_notes(
                    st.session_state.task_mode,
                    st.session_state.current_task or "",
                    limit=3,
                )
                if relevant_notes:
                    st.markdown("**Relevant Saved Notes**")
                    for note in relevant_notes:
                        mode_label = note.get("task_mode") or "General"
                        st.markdown(f"- [{mode_label}] {note.get('text', '')}")
                else:
                    st.caption("No relevant project notes yet.")
            else:
                st.caption("Project notes will appear after a full app restart loads the updated memory module.")

            st.session_state.project_note_text = st.text_area(
                "Save a project note",
                value=st.session_state.project_note_text,
                placeholder="Example: For scheduling tasks, employee preferences come by email and non-responders are treated as flexible.",
                height=110,
            )
            if st.button("Save Project Note", key="save_project_note"):
                note_text = str(st.session_state.project_note_text or "").strip()
                if note_text and hasattr(memory_store, "add_project_note"):
                    memory_store.add_project_note(
                        text=note_text,
                        task_mode=st.session_state.task_mode,
                    )
                    st.session_state.project_note_text = ""
                    st.session_state.memory_stats = memory_store.stats()
                    st.success("Project note saved to persistent memory.")
                    st.rerun()
                elif note_text:
                    st.warning("Project notes need one full app restart before saving is available.")
    with col_opt:
        auto_mode      = st.checkbox("AUTONOMOUS MODE", value=False)
        target_score   = st.slider("Target score",   6, 10, 8) if auto_mode else 8.0
        max_iterations = st.number_input("Max iterations", 1, 8, 5) if auto_mode else 1

    if st.button("🚀 EXECUTE COGNITIVE DEBATE"):
        get_cache().clear()
        manual_override = build_effective_manual_override()
        with st.spinner("Running intelligence pipeline..."):
            orchestrator = ArbiterOrchestrator(
                task_mode=st.session_state.task_mode,
                auto_mode=auto_mode,
                target_score=float(target_score),
                max_iterations=int(max_iterations),
                stable_mode=st.session_state.stable_mode,
            )
            result = orchestrator.run(
                user_input=st.session_state.current_task,
                clarification="already_audited",   # skip re-audit
                manual_override=manual_override,
            )

        sync_state_from_result(result)
        st.session_state.retry_override = ""
        st.rerun()

    if st.session_state.iteration > 0:
        st.divider()
        if st.button("📥 GENERATE FINAL REPORT"):
            st.session_state.step = "export"
            st.rerun()


# ════════════════════════════════════════════════
# STEP 5: Export
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

    if FPDF is None:
        st.info("PDF export is unavailable because `fpdf` is not installed in this Python environment.")
    else:
        import re as _re
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        report_text = st.session_state.best_solution or st.session_state.current_solution
        clean_text  = _re.sub(r"<[^>]*>", "", report_text)
        pdf.multi_cell(0, 10, txt=clean_text.encode("latin-1", "replace").decode("latin-1"))
        pdf_output  = pdf.output(dest="S")
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
