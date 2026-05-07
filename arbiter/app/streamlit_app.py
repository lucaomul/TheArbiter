import streamlit as st
import streamlit.components.v1 as components
import re
import html
import json
import sys
import os
from importlib.metadata import PackageNotFoundError, version
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
from arbiter.core.team_router import TeamRouter
from arbiter.config.settings import TASK_PROFILES
from arbiter.infra.cache import get_cache
from arbiter.infra.memory_store import get_memory_store
from arbiter.infra.benchmark_suite import get_benchmark_packs, get_benchmark_cases, get_case_by_id
from arbiter.infra.plugin_registry import get_plugin_registry, provider_for_model
from arbiter.app.export_artifacts import export_solution_csv, export_solution_xlsx
from arbiter.app.ui_styles import UI_CSS
from arbiter.app.visual_summaries import build_visual_blueprint_html

try:
    from arbiter import __version__
except ImportError:
    try:
        __version__ = version("the-arbiter")
    except PackageNotFoundError:
        __version__ = "0.1.0"

load_dotenv(PROJECT_ROOT / ".env", override=True)
REGISTRY = get_plugin_registry()
TEAM_ROUTER = TeamRouter()
try:
    REGISTRY.sync_catalog_if_needed()
except Exception:
    pass

# ── Page config ─────────────────────────────────────────────
st.set_page_config(
    page_title="The Arbiter | Luca Crăciun",
    page_icon="•",
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
    "audit_round_count": 0,
    "audit_question_history": [],
    "audit_resolution_note": "",
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
    "benchmark_stats":   {"count": 0, "avg_score": 0.0, "avg_cost": 0.0, "avg_iterations": 0.0, "benchmark_runs": 0},
    "benchmark_by_task_mode": {},
    "benchmark_by_strategy": {},
    "benchmark_by_case": {},
    "recent_benchmarks": [],
    "decision_trace":    [],
    "unresolved_issues": {"tech": [], "logic": []},
    "latest_janitor_report": {},
    "latest_result_status": "IDLE",
    "run_id": "",
    "retry_override": "",
    "audit_status": "idle",
    "provider_lock": "groq",
    "stable_mode": True,
    "benchmark_mode": False,
    "benchmark_pack": get_benchmark_packs()[0],
    "benchmark_case_id": "",
    "benchmark_strategy": "arbiter_full_loop",
    "manual_feedback_enabled": False,
    "manual_feedback_text": "",
    "project_note_text": "",
    "task_draft": "",
    "task_input_seq": 0,
    "clarification_input_seq": 0,
    "manual_feedback_input_seq": 0,
    "project_note_input_seq": 0,
    "pending_auto_run": False,
    "run_in_progress": False,
    "software_team_consent": False,
    "software_team_warning_ack": False,
    "software_team_preview": {},
    "software_team_profile": "efficient",
    "supporting_materials": [],
    "supporting_urls": [],
    "supporting_urls_text": "",
    "evidence_preview": {},
    "auto_mode_enabled": False,
    "target_score_setting": 8,
    "max_iterations_setting": 5,
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


MAX_AUDIT_CLARIFICATION_ROUNDS = 3

TASK_INPUT_GUIDES = {
    "Software & IT": {
        "placeholder": "Describe the software task, bug, feature, architecture, or implementation problem you want solved...",
        "caption": "Give the product goal, current constraints, stack, expected behavior, and any error signals if they exist.",
    },
    "Marketing & Growth": {
        "placeholder": "Describe the market, audience, offer, growth goal, budget, and channel problem you want The Arbiter to solve...",
        "caption": "Good inputs mention ICP, offer, channels, timeline, KPIs, constraints, and what success should look like.",
    },
    "Business & Operations": {
        "placeholder": "Describe the operational workflow, team structure, bottleneck, or process design problem you want improved...",
        "caption": "Include roles, handoffs, SLAs, bottlenecks, escalation rules, tools, and any real-world constraints.",
    },
    "Writing & Content": {
        "placeholder": "Describe the content you need written, who it is for, the tone, structure, and what message it must land...",
        "caption": "Mention audience, format, tone, objective, key arguments, examples, and what the final piece should achieve.",
    },
    "Personal Planning": {
        "placeholder": "Describe the personal plan, decision, habit system, or roadmap you want structured clearly and realistically...",
        "caption": "The more useful inputs usually include goals, deadlines, tradeoffs, available time, energy limits, and blockers.",
    },
    "General Problem Solving": {
        "placeholder": "Describe the situation, decision, tradeoff, or open problem you want broken down into a strong recommendation...",
        "caption": "Include the context, decision options, risks, constraints, and what a good outcome would look like.",
    },
}

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
    preserved_ui = {
        "provider_lock": st.session_state.provider_lock,
        "stable_mode": st.session_state.stable_mode,
        "benchmark_mode": st.session_state.benchmark_mode,
        "benchmark_pack": st.session_state.benchmark_pack,
        "benchmark_case_id": st.session_state.benchmark_case_id,
        "benchmark_strategy": st.session_state.benchmark_strategy,
        "model_preset": st.session_state.model_preset,
        "manual_model_selection": st.session_state.manual_model_selection,
        "selected_models": dict(st.session_state.selected_models),
        "task_draft": st.session_state.task_draft,
        "task_input_seq": int(st.session_state.task_input_seq or 0) + 1,
        "auto_mode_enabled": st.session_state.auto_mode_enabled,
        "target_score_setting": st.session_state.target_score_setting,
        "max_iterations_setting": st.session_state.max_iterations_setting,
        "supporting_materials": list(st.session_state.supporting_materials or []),
        "supporting_urls": list(st.session_state.supporting_urls or []),
        "supporting_urls_text": st.session_state.supporting_urls_text,
        "software_team_profile": st.session_state.software_team_profile,
        "clarification_input_seq": int(st.session_state.clarification_input_seq or 0) + 1,
        "manual_feedback_input_seq": int(st.session_state.manual_feedback_input_seq or 0) + 1,
        "project_note_input_seq": int(st.session_state.project_note_input_seq or 0) + 1,
    }
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
    for key, value in preserved_ui.items():
        st.session_state[key] = value
    st.session_state.audit_status = "idle"
    st.session_state.audit_round_count = 0
    st.session_state.audit_question_history = []
    st.session_state.audit_resolution_note = ""


def get_available_models_for_role(role: str) -> list:
    models = [plugin.model_id for plugin in REGISTRY.candidates_for_role(role)]
    if (
        role == "Logic Critic"
        and "gemini-2.5-flash" not in models
        and registry_is_selectable("gemini-2.5-flash", role)
    ):
        models.append("gemini-2.5-flash")
    return models


def normalize_audit_question(text: str) -> str:
    value = str(text or "").strip().lower()
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def audit_questions_similar(left: str, right: str) -> bool:
    a = normalize_audit_question(left)
    b = normalize_audit_question(right)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if not a_tokens or not b_tokens:
        return False
    overlap = len(a_tokens & b_tokens) / max(len(a_tokens), len(b_tokens))
    return overlap >= 0.75


def sanitize_audit_questions(items, limit: int = 3) -> list[str]:
    cleaned = []
    for item in items or []:
        question = str(item or "").strip()
        if not question:
            continue
        if any(audit_questions_similar(question, existing) for existing in cleaned):
            continue
        cleaned.append(question)
        if len(cleaned) >= limit:
            break
    return cleaned


def get_software_team_preview(task_text: str, task_mode: str) -> dict:
    if task_mode != "Software & IT":
        return {}
    decision = TEAM_ROUTER.route(task_mode, task_text)
    return decision.model_dump()


def maybe_require_software_team_consent(task_text: str) -> bool:
    preview = get_software_team_preview(task_text, st.session_state.task_mode)
    st.session_state.software_team_preview = dict(preview or {})
    profile_options = dict(preview.get("profile_options", {}) or {})
    if profile_options:
        current_profile = str(st.session_state.software_team_profile or "").strip().lower()
        if current_profile not in profile_options:
            st.session_state.software_team_profile = str(preview.get("recommended_profile", "efficient") or "efficient")
    if preview.get("use_team") and preview.get("requires_confirmation") and not st.session_state.software_team_consent:
        st.session_state.pending_auto_run = False
        st.session_state.run_in_progress = False
        st.session_state.step = "team_consent"
        return True
    return False


def run_orchestrator_safe(orchestrator: ArbiterOrchestrator, **kwargs):
    try:
        return orchestrator.run(**kwargs)
    except TypeError as exc:
        message = str(exc)
        if "unexpected keyword argument 'software_team_profile'" not in message:
            raise
        fallback_kwargs = dict(kwargs)
        fallback_kwargs.pop("software_team_profile", None)
        return orchestrator.run(**fallback_kwargs)


def registry_resolve_model_id(model_id: str) -> str:
    if hasattr(REGISTRY, "resolve_model_id"):
        try:
            return str(REGISTRY.resolve_model_id(model_id) or "").strip()
        except Exception:
            pass
    return str(model_id or "").strip()


def registry_is_selectable(model_id: str, role: str = "") -> bool:
    resolved = registry_resolve_model_id(model_id)
    if hasattr(REGISTRY, "is_selectable"):
        try:
            return bool(REGISTRY.is_selectable(resolved, role))
        except Exception:
            pass
    try:
        plugin = REGISTRY.get(resolved) if hasattr(REGISTRY, "get") else None
        if plugin is None:
            return False
        if role and role not in getattr(plugin, "roles", []):
            return False
        if not getattr(plugin, "enabled", True):
            return False
        if str(getattr(plugin, "availability", "available") or "").lower() in {
            "deprecated",
            "unavailable",
        }:
            return False
        return True
    except Exception:
        return False


def registry_recommended_replacement(model_id: str, role: str = "") -> str:
    resolved = registry_resolve_model_id(model_id)
    if hasattr(REGISTRY, "recommended_replacement"):
        try:
            return str(REGISTRY.recommended_replacement(resolved, role) or "").strip()
        except Exception:
            pass
    options = get_available_models_for_role(role)
    return options[0] if options else resolved


def normalize_role_model(role: str, model_id: str) -> str:
    resolved = registry_resolve_model_id(model_id)
    if registry_is_selectable(resolved, role):
        return resolved
    replacement = registry_recommended_replacement(resolved, role)
    if replacement:
        return replacement
    options = get_available_models_for_role(role)
    return options[0] if options else resolved


def apply_model_preset(name: str):
    preset = MODEL_PRESETS.get(name)
    if not preset:
        return
    st.session_state.provider_lock = preset["provider_lock"]
    st.session_state.stable_mode = preset["stable_mode"]
    st.session_state.selected_models = {
        role: normalize_role_model(role, model_id)
        for role, model_id in dict(preset["models"]).items()
    }


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


def get_case_flow_status() -> list[tuple[str, str]]:
    step = st.session_state.step
    run_in_progress = bool(st.session_state.run_in_progress)
    has_result = bool(st.session_state.iteration_history) and not run_in_progress
    audit_status = st.session_state.audit_status
    latest_status = st.session_state.latest_result_status

    intake = "active" if step in {"input", "audit", "clarification"} and not has_result else "done" if st.session_state.current_task else "idle"
    architect = "active" if step == "negotiation" and run_in_progress else "done" if has_result else "idle"
    critics = "active" if step == "negotiation" and run_in_progress else "done" if has_result else "idle"
    janitor = "active" if step == "negotiation" and run_in_progress else "done" if has_result and st.session_state.latest_janitor_report else "idle"
    verdict = "done" if has_result else "idle"

    if audit_status == "needs_clarification":
        intake = "warn"
    if latest_status in {"DIAGNOSTIC ONLY", "REVIEW DEGRADED", "PROVIDER LIMITED"}:
        verdict = "warn"

    return [
        ("Case Intake", intake),
        ("Architect Draft", architect),
        ("Counsel Debate", critics),
        ("Janitor Brief", janitor),
        ("Final Order", verdict),
    ]


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
        if not retry_after:
            embedded = " ".join(
                str(parsed.get(key, "") or "")
                for key in ("critique", "error", "fix_suggestion")
            )
            retry_match = re.search(r"please try again in ([0-9hms\.\s]+)", embedded, re.IGNORECASE)
            retry_after = retry_match.group(1).strip().rstrip(".") if retry_match else ""
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


def normalize_visible_message(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""

    parsed = None
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None

    if isinstance(parsed, dict) and parsed.get("provider_error"):
        primary = format_provider_error_message(text)
        fix = str(parsed.get("fix_suggestion") or "").strip()
        if fix and fix.lower() not in primary.lower():
            return f"{primary} {fix}".strip()
        return primary

    return format_provider_error_message(text)


def mask_text(text: str, visible: int = 140) -> str:
    raw = " ".join(str(text or "").split())
    if len(raw) <= visible:
        return "*" * max(len(raw), 12)
    head = raw[: visible // 2]
    tail = raw[-(visible // 2):]
    hidden_len = max(len(raw) - len(head) - len(tail), 24)
    return f"{head} {'*' * min(hidden_len, 120)} {tail}"


def render_summary_cards(items):
    cards = []
    for label, value in items:
        cards.append(
            "<div class='summary-card'>"
            f"<div class='summary-card-label'>{html.escape(str(label))}</div>"
            f"<div class='summary-card-value'>{html.escape(str(value))}</div>"
            "</div>"
        )
    st.markdown("<div class='summary-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def count_eval_fixtures() -> int:
    fixtures_dir = PROJECT_ROOT / "evals" / "fixtures"
    total = 0
    for path in fixtures_dir.glob("*.jsonl"):
        try:
            with path.open("r", encoding="utf-8") as handle:
                total += sum(1 for line in handle if line.strip())
        except Exception:
            continue
    return total


def provider_catalog_rows() -> list[dict]:
    providers = sorted(
        {
            plugin.provider
            for model_id in REGISTRY.all_model_ids()
            for plugin in [REGISTRY.get(model_id)]
            if plugin is not None
        }
    )
    rows = []
    for provider in providers:
        state = dict(REGISTRY.provider_state(provider) or {})
        models = list(state.get("models", []) or [])
        total_count = 0
        available_count = 0
        for model_id in REGISTRY.all_model_ids():
            plugin = REGISTRY.get(model_id)
            if plugin is None or plugin.provider != provider:
                continue
            total_count += 1
            if REGISTRY.is_model_available(model_id):
                available_count += 1
        rows.append(
            {
                "provider": provider,
                "catalog_status": str(state.get("status", "static") or "static"),
                "catalog_models": len(models),
                "registry_models": total_count,
                "available_models": available_count,
            }
        )
    return rows


def render_case_flow_panel():
    flow = get_case_flow_status()
    blocks = []
    for label, status in flow:
        css = {
            "done": "court-chip done",
            "active": "court-chip active",
            "warn": "court-chip warn",
            "idle": "court-chip",
        }.get(status, "court-chip")
        readable = {
            "done": "Done",
            "active": "Running",
            "warn": "Attention",
            "idle": "Waiting",
        }.get(status, "Waiting")
        blocks.append(
            "<div class='court-step'>"
            f"<div class='court-flow-label'>{html.escape(label)}</div>"
            f"<span class='{css}'>{readable}</span>"
            "</div>"
        )
    st.markdown(
        "<div class='court-flow'>" + "".join(blocks) + "</div>",
        unsafe_allow_html=True,
    )


def render_deliberation_scene():
    flow_map = dict(get_case_flow_status())
    step = st.session_state.step
    audit_status = st.session_state.audit_status
    run_in_progress = bool(st.session_state.run_in_progress)
    has_result = bool(st.session_state.iteration_history) and not run_in_progress
    pipeline_running = step == "negotiation" and run_in_progress
    auditor_only = step in {"audit", "clarification"} and not run_in_progress and not has_result

    if step == "input" and not st.session_state.current_task and not has_result and not run_in_progress:
        return

    architect_status = flow_map.get("Architect Draft", "idle")
    critics_status = flow_map.get("Counsel Debate", "idle")
    janitor_status = flow_map.get("Janitor Brief", "idle")
    verdict_status = flow_map.get("Final Order", "idle")
    auditor_status = (
        "warn" if audit_status == "needs_clarification"
        else "done" if audit_status == "passed"
        else "active" if step == "audit"
        else "idle"
    )

    def scene_state_css(status: str) -> str:
        return {
            "done": "scene-done",
            "active": "scene-active",
            "warn": "scene-warn",
            "idle": "scene-idle",
        }.get(status, "scene-idle")

    def scene_badge(status: str) -> str:
        return {
            "done": "Settled",
            "active": "In motion",
            "warn": "Needs revision",
            "idle": "Standing by",
        }.get(status, "Standing by")

    janitor_note = "Consolidating the dispute into one cleaner retry brief."
    if janitor_status == "done" and verdict_status == "warn":
        janitor_note = "Cleanup completed, but the order still needs another pass."
    elif janitor_status == "done":
        janitor_note = "Cleanup complete and ready for the final order."

    auditor_note = "Reading the case brief and checking whether the request has enough context."
    if auditor_status == "done":
        auditor_note = "Context approved. The case can move straight into deliberation."
    elif auditor_status == "warn":
        auditor_note = "More context is required before the case can move forward."

    def scene_card(title: str, eyebrow: str, badge_status: str, note: str, body_html: str) -> str:
        return (
            f"<div class='arb-figure-card {scene_state_css(badge_status)}'>"
            "<div class='arb-figure-topline'>"
            f"<span class='arb-figure-eyebrow'>{html.escape(eyebrow)}</span>"
            f"<span class='arb-figure-badge'>{html.escape(scene_badge(badge_status))}</span>"
            "</div>"
            f"<div class='arb-figure-title'>{html.escape(title)}</div>"
            f"<div class='arb-figure-stage'>{body_html}</div>"
            f"<div class='arb-figure-note'>{html.escape(note)}</div>"
            "</div>"
        )

    architect_svg = """
    <svg class='arb-figure-svg architect-svg' viewBox='0 0 320 180' aria-hidden='true'>
        <rect x='184' y='28' width='96' height='82' rx='8' class='board-frame'></rect>
        <rect x='194' y='38' width='76' height='62' rx='5' class='board-surface'></rect>
        <line x1='196' y1='110' x2='188' y2='154' class='board-leg'></line>
        <line x1='276' y1='110' x2='284' y2='154' class='board-leg'></line>
        <path d='M208 58 L244 72 L216 88' class='board-sketch'></path>
        <path d='M222 52 L256 62 L248 90' class='board-sketch board-sketch-soft'></path>
        <circle cx='86' cy='58' r='14' class='figure-stroke'></circle>
        <line x1='86' y1='72' x2='86' y2='116' class='figure-stroke'></line>
        <line x1='86' y1='84' x2='66' y2='104' class='figure-stroke'></line>
        <line x1='86' y1='84' x2='104' y2='96' class='figure-stroke'></line>
        <line x1='86' y1='116' x2='70' y2='148' class='figure-stroke'></line>
        <line x1='86' y1='116' x2='102' y2='148' class='figure-stroke'></line>
        <g class='drawing-arm'>
            <line x1='86' y1='84' x2='126' y2='78' class='figure-stroke'></line>
            <line x1='126' y1='78' x2='172' y2='74' class='figure-stroke'></line>
            <circle cx='174' cy='74' r='3.5' class='pen-tip'></circle>
        </g>
        <path d='M172 74 C188 66, 200 62, 214 60' class='draw-trace'></path>
        <path d='M176 80 C196 86, 210 90, 226 92' class='draw-trace draw-trace-2'></path>
        <line x1='26' y1='154' x2='298' y2='154' class='ground-line'></line>
    </svg>
    """

    critics_svg = """
    <svg class='arb-figure-svg critics-svg' viewBox='0 0 320 180' aria-hidden='true'>
        <g class='critic critic-left'>
            <circle cx='82' cy='64' r='14' class='figure-stroke'></circle>
            <line x1='82' y1='78' x2='82' y2='120' class='figure-stroke'></line>
            <line x1='82' y1='90' x2='60' y2='106' class='figure-stroke'></line>
            <line x1='82' y1='90' x2='108' y2='92' class='figure-stroke'></line>
            <line x1='82' y1='120' x2='68' y2='150' class='figure-stroke'></line>
            <line x1='82' y1='120' x2='96' y2='150' class='figure-stroke'></line>
        </g>
        <g class='critic critic-right'>
            <circle cx='238' cy='64' r='14' class='figure-stroke'></circle>
            <line x1='238' y1='78' x2='238' y2='120' class='figure-stroke'></line>
            <line x1='238' y1='90' x2='214' y2='92' class='figure-stroke'></line>
            <line x1='238' y1='90' x2='258' y2='108' class='figure-stroke'></line>
            <line x1='238' y1='120' x2='224' y2='150' class='figure-stroke'></line>
            <line x1='238' y1='120' x2='252' y2='150' class='figure-stroke'></line>
        </g>
        <g class='bubble bubble-left'>
            <rect x='36' y='18' width='92' height='30' rx='12' class='speech-bubble'></rect>
            <path d='M90 48 L82 58 L104 48' class='speech-tail'></path>
            <line x1='52' y1='31' x2='108' y2='31' class='speech-line'></line>
            <line x1='52' y1='38' x2='94' y2='38' class='speech-line'></line>
        </g>
        <g class='bubble bubble-right'>
            <rect x='190' y='18' width='92' height='30' rx='12' class='speech-bubble'></rect>
            <path d='M230 48 L246 58 L242 48' class='speech-tail'></path>
            <line x1='206' y1='31' x2='262' y2='31' class='speech-line'></line>
            <line x1='206' y1='38' x2='248' y2='38' class='speech-line'></line>
        </g>
        <line x1='24' y1='154' x2='296' y2='154' class='ground-line'></line>
    </svg>
    """

    janitor_svg = """
    <svg class='arb-figure-svg janitor-svg' viewBox='0 0 320 180' aria-hidden='true'>
        <circle cx='88' cy='58' r='14' class='figure-stroke'></circle>
        <line x1='88' y1='72' x2='88' y2='116' class='figure-stroke'></line>
        <line x1='88' y1='84' x2='66' y2='100' class='figure-stroke'></line>
        <line x1='88' y1='84' x2='72' y2='94' class='figure-stroke'></line>
        <line x1='88' y1='116' x2='72' y2='148' class='figure-stroke'></line>
        <line x1='88' y1='116' x2='102' y2='148' class='figure-stroke'></line>
        <g class='broom-arm'>
            <line x1='88' y1='84' x2='126' y2='96' class='figure-stroke'></line>
            <line x1='126' y1='96' x2='182' y2='132' class='figure-stroke broom-stick'></line>
            <path d='M182 132 L208 126 L212 142 L186 148 Z' class='broom-head'></path>
        </g>
        <g class='dust dust-one'>
            <circle cx='232' cy='142' r='4'></circle>
            <circle cx='244' cy='138' r='3'></circle>
            <circle cx='256' cy='144' r='5'></circle>
        </g>
        <g class='dust dust-two'>
            <circle cx='220' cy='146' r='3'></circle>
            <circle cx='236' cy='148' r='4'></circle>
            <circle cx='252' cy='150' r='3'></circle>
        </g>
        <line x1='26' y1='154' x2='298' y2='154' class='ground-line'></line>
    </svg>
    """

    auditor_svg = """
    <svg class='arb-figure-svg auditor-svg' viewBox='0 0 320 180' aria-hidden='true'>
        <circle cx='104' cy='58' r='14' class='figure-stroke'></circle>
        <line x1='104' y1='72' x2='104' y2='116' class='figure-stroke'></line>
        <line x1='104' y1='84' x2='84' y2='104' class='figure-stroke'></line>
        <line x1='104' y1='116' x2='90' y2='148' class='figure-stroke'></line>
        <line x1='104' y1='116' x2='118' y2='148' class='figure-stroke'></line>
        <g class='reader-arm'>
            <line x1='104' y1='84' x2='138' y2='88' class='figure-stroke'></line>
            <line x1='138' y1='88' x2='174' y2='92' class='figure-stroke'></line>
        </g>
        <rect x='170' y='56' width='68' height='82' rx='8' class='paper-sheet'></rect>
        <line x1='184' y1='78' x2='222' y2='78' class='paper-line'></line>
        <line x1='184' y1='90' x2='226' y2='90' class='paper-line'></line>
        <line x1='184' y1='102' x2='214' y2='102' class='paper-line'></line>
        <line x1='184' y1='114' x2='224' y2='114' class='paper-line'></line>
        <g class='approve-mark'>
            <circle cx='258' cy='52' r='16' class='mark-ring'></circle>
            <path d='M250 52 L257 59 L270 45' class='mark-stroke'></path>
        </g>
        <g class='reject-mark'>
            <circle cx='258' cy='52' r='16' class='mark-ring'></circle>
            <line x1='250' y1='44' x2='266' y2='60' class='mark-stroke'></line>
            <line x1='266' y1='44' x2='250' y2='60' class='mark-stroke'></line>
        </g>
        <line x1='26' y1='154' x2='298' y2='154' class='ground-line'></line>
    </svg>
    """

    scene_css = """
    <style>
    .arb-scene-wrap { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:0 0 24px; }
    .arb-scene-wrap.auditor-only { grid-template-columns:minmax(0,1fr); max-width:none; }
    .arb-figure-card { position:relative; display:flex; flex-direction:column; min-height:320px; padding:18px 18px 16px; border-radius:20px; background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(247,247,245,.98)); border:1px solid #ddddda; box-shadow:0 12px 30px rgba(0,0,0,.05); overflow:hidden; box-sizing:border-box; }
    .arb-figure-card::before { content:""; position:absolute; inset:0 auto auto 0; width:100%; height:2px; background:#111111; opacity:.08; }
    .arb-figure-card.scene-active { border-color:#111111; box-shadow:0 16px 34px rgba(0,0,0,.10); }
    .arb-figure-card.scene-warn { border-color:#9c9c96; background:linear-gradient(180deg,rgba(255,255,255,.98),rgba(242,242,239,.98)); }
    .arb-figure-topline { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }
    .arb-figure-eyebrow { color:#666666; text-transform:uppercase; letter-spacing:.08em; font-size:.7rem; font-weight:700; line-height:1.2; }
    .arb-figure-badge { display:inline-flex; align-items:center; justify-content:center; min-height:28px; padding:5px 10px; border-radius:999px; background:#efefec; border:1px solid #d6d6d1; color:#444444; font-size:.74rem; font-weight:700; white-space:nowrap; line-height:1; }
    .arb-figure-card.scene-active .arb-figure-badge { background:#111111; border-color:#111111; color:#ffffff; }
    .arb-figure-card.scene-warn .arb-figure-badge { background:#d9d9d4; border-color:#bdbdb7; color:#111111; }
    .arb-figure-title { color:#0a0a0a; font-size:1rem; font-weight:700; line-height:1.3; margin:0 0 14px; }
    .arb-figure-stage { position:relative; min-height:176px; border-radius:16px; background:linear-gradient(180deg,#f7f7f5,#f1f1ee); border:1px solid #e1e1dc; overflow:hidden; margin-bottom:14px; flex:0 0 auto; }
    .arb-figure-note { color:#555555; font-size:.9rem; line-height:1.6; margin-top:auto; }
    .arb-figure-svg { display:block; width:100%; height:176px; }
    .arb-figure-svg .figure-stroke, .arb-figure-svg .board-frame, .arb-figure-svg .board-leg, .arb-figure-svg .ground-line, .arb-figure-svg .speech-tail, .arb-figure-svg .speech-line, .arb-figure-svg .board-sketch, .arb-figure-svg .draw-trace, .arb-figure-svg .broom-stick, .arb-figure-svg .paper-line, .arb-figure-svg .mark-stroke { fill:none; stroke:#111111; stroke-width:4; stroke-linecap:round; stroke-linejoin:round; }
    .arb-figure-svg .board-surface, .arb-figure-svg .speech-bubble, .arb-figure-svg .paper-sheet, .arb-figure-svg .mark-ring { fill:rgba(255,255,255,.86); stroke:#111111; stroke-width:3; }
    .arb-figure-svg .paper-line { opacity:.55; stroke-width:3; }
    .arb-figure-svg .board-sketch-soft { opacity:.45; }
    .arb-figure-svg .pen-tip, .arb-figure-svg .broom-head, .arb-figure-svg .dust circle { fill:#111111; }
    .arb-figure-svg .draw-trace, .arb-figure-svg .draw-trace-2 { stroke-width:3; stroke-dasharray:42; stroke-dashoffset:42; }
    .architect-svg .drawing-arm, .critics-svg .critic-left, .critics-svg .critic-right { transform-box:fill-box; transform-origin:center; }
    .architect-svg .drawing-arm { transform-origin:86px 84px; }
    .critics-svg .critic-left { transform-origin:82px 100px; }
    .critics-svg .critic-right { transform-origin:238px 100px; }
    .janitor-svg .broom-arm { transform-origin:88px 84px; }
    .auditor-svg .reader-arm { transform-origin:104px 84px; }
    .pipeline-live .architect-svg { opacity:1; }
    .pipeline-live .critics-svg { opacity:.18; }
    .pipeline-live .janitor-svg { opacity:.16; }
    .critics-svg .bubble { opacity:.16; }
    .janitor-svg .dust { opacity:.16; }
    .auditor-svg .approve-mark, .auditor-svg .reject-mark { opacity:0; }
    @keyframes architect-draw { 0%,10%,100% { transform:rotate(-8deg); } 18% { transform:rotate(5deg); } 28% { transform:rotate(-6deg); } 33%,100% { transform:rotate(-8deg); } }
    @keyframes draw-trace { 0% { stroke-dashoffset:42; opacity:0; } 8% { opacity:.2; } 22% { stroke-dashoffset:0; opacity:1; } 30% { stroke-dashoffset:0; opacity:.35; } 33%,100% { stroke-dashoffset:0; opacity:0; } }
    @keyframes argue-left { 0%,33% { transform:rotate(0deg) translateY(0); } 43% { transform:rotate(-3deg) translateY(-1px); } 53% { transform:rotate(4deg) translateY(-2px); } 63% { transform:rotate(-2deg) translateY(0); } 66%,100% { transform:rotate(0deg) translateY(0); } }
    @keyframes argue-right { 0%,33% { transform:rotate(0deg) translateY(0); } 43% { transform:rotate(3deg) translateY(-1px); } 53% { transform:rotate(-4deg) translateY(-2px); } 63% { transform:rotate(2deg) translateY(0); } 66%,100% { transform:rotate(0deg) translateY(0); } }
    @keyframes bubble-left { 0%,33%,100% { opacity:.14; transform:translateY(0); } 38%,48% { opacity:1; transform:translateY(-3px); } 55%,100% { opacity:.14; transform:translateY(0); } }
    @keyframes bubble-right { 0%,46%,100% { opacity:.14; transform:translateY(0); } 52%,62% { opacity:1; transform:translateY(-3px); } 66%,100% { opacity:.14; transform:translateY(0); } }
    @keyframes janitor-arm { 0%,66%,100% { transform:rotate(0deg); } 76% { transform:rotate(6deg); } 88% { transform:rotate(-8deg); } }
    @keyframes dust-shift-one { 0%,66% { transform:translateX(0); opacity:.08; } 76% { transform:translateX(-10px); opacity:.5; } 88% { transform:translateX(-18px); opacity:.82; } 100% { transform:translateX(0); opacity:.08; } }
    @keyframes dust-shift-two { 0%,66% { transform:translateX(0); opacity:.08; } 80% { transform:translateX(-6px); opacity:.34; } 92% { transform:translateX(-10px); opacity:.62; } 100% { transform:translateX(0); opacity:.08; } }
    @keyframes auditor-arm { 0%,100% { transform:rotate(0deg); } 50% { transform:rotate(4deg); } }
    @keyframes mark-pop { 0%,100% { opacity:.24; transform:scale(.94); } 50% { opacity:1; transform:scale(1); } }
    @keyframes architect-presence { 0%,33% { opacity:1; } 36%,100% { opacity:.28; } }
    @keyframes critics-presence { 0%,33% { opacity:.18; } 38%,66% { opacity:1; } 70%,100% { opacity:.22; } }
    @keyframes janitor-presence { 0%,66% { opacity:.16; } 72%,100% { opacity:1; } }
    .pipeline-live .architect-svg { animation:architect-presence 3.6s linear infinite; }
    .pipeline-live .critics-svg { animation:critics-presence 3.6s linear infinite; }
    .pipeline-live .janitor-svg { animation:janitor-presence 3.6s linear infinite; }
    .pipeline-live .architect-svg .drawing-arm { animation:architect-draw 3.6s ease-in-out infinite; }
    .pipeline-live .architect-svg .draw-trace { animation:draw-trace 3.6s linear infinite; }
    .pipeline-live .architect-svg .draw-trace-2 { animation:draw-trace 3.6s linear infinite .15s; }
    .pipeline-live .critics-svg .critic-left { animation:argue-left 3.6s ease-in-out infinite; }
    .pipeline-live .critics-svg .critic-right { animation:argue-right 3.6s ease-in-out infinite; }
    .pipeline-live .critics-svg .bubble-left { animation:bubble-left 3.6s ease-in-out infinite; }
    .pipeline-live .critics-svg .bubble-right { animation:bubble-right 3.6s ease-in-out infinite; }
    .pipeline-live .janitor-svg .broom-arm { animation:janitor-arm 3.6s ease-in-out infinite; }
    .pipeline-live .janitor-svg .dust-one { animation:dust-shift-one 3.6s ease-in-out infinite; }
    .pipeline-live .janitor-svg .dust-two { animation:dust-shift-two 3.6s ease-in-out infinite; }
    .arb-figure-card.scene-active .auditor-svg .reader-arm { animation:auditor-arm 1.2s ease-in-out infinite; }
    .arb-figure-card.scene-done .auditor-svg .approve-mark { opacity:1; animation:mark-pop 1.4s ease-in-out infinite; }
    .arb-figure-card.scene-warn .auditor-svg .reject-mark { opacity:1; animation:mark-pop 1.4s ease-in-out infinite; }
    @media (max-width:760px) { .arb-scene-wrap { grid-template-columns:repeat(2,minmax(0,1fr)); } .arb-scene-wrap.auditor-only { grid-template-columns:minmax(0,1fr); max-width:none; } .arb-figure-card { min-height:284px; } }
    @media (max-width:560px) { .arb-scene-wrap { grid-template-columns:1fr; } }
    @media (prefers-reduced-motion:reduce) { .arb-scene-wrap *, .arb-scene-wrap *::before, .arb-scene-wrap *::after { animation:none !important; transition:none !important; } }
    </style>
    """

    scene_html = scene_css
    if auditor_only:
        scene_html += "<div class='arb-scene-wrap auditor-only'>"
        scene_html += scene_card(
            "Reading the case brief",
            "Auditor",
            auditor_status,
            auditor_note,
            auditor_svg,
        )
    else:
        live_class = " pipeline-live" if pipeline_running else ""
        scene_html += f"<div class='arb-scene-wrap{live_class}'>"
        scene_html += scene_card(
            "Drafting the case",
            "Architect",
            architect_status,
            "Building structure, logic, and executable detail.",
            architect_svg,
        )
        scene_html += scene_card(
            "Contesting the draft",
            "Counsel",
            critics_status,
            "Technical and logical counsel pressure-test the build.",
            critics_svg,
        )
        scene_html += scene_card(
            "Resolving the brief",
            "Janitor",
            janitor_status,
            janitor_note,
            janitor_svg,
        )
    scene_html += "</div>"
    components.html(scene_html, height=420 if auditor_only else 430, scrolling=False)


def render_product_header():
    st.title("The Arbiter")
    st.caption(
        "A multi-agent workspace where the architect drafts, counsel reviews, and the janitor resolves the brief into a cleaner final answer."
    )


def current_task_input_guide() -> dict:
    fallback = TASK_INPUT_GUIDES["General Problem Solving"]
    return TASK_INPUT_GUIDES.get(st.session_state.task_mode, fallback)


def parse_supporting_urls(raw: str) -> list[str]:
    pattern = re.compile(r"\b((?:https?://|www\.)[^\s<>()]+)", flags=re.IGNORECASE)
    items = []
    for match in pattern.findall(str(raw or "")):
        url = str(match or "").strip().rstrip(".,);]")
        if not url:
            continue
        if not re.match(r"^https?://", url, flags=re.IGNORECASE):
            url = f"https://{url}"
        if url not in items:
            items.append(url)
    return items[:8]


def serialize_uploaded_material(uploaded_file) -> dict:
    return {
        "name": str(getattr(uploaded_file, "name", "attachment") or "attachment"),
        "media_type": str(getattr(uploaded_file, "type", "") or ""),
        "bytes": uploaded_file.getvalue(),
        "source_type": "file",
    }


def attachment_file_types() -> list[str]:
    return [
        "pdf",
        "docx",
        "txt",
        "md",
        "markdown",
        "json",
        "csv",
        "html",
        "htm",
        "py",
        "js",
        "ts",
        "tsx",
        "jsx",
        "sql",
        "yaml",
        "yml",
        "xml",
        "log",
        "rst",
    ]


def render_pending_supporting_materials():
    materials = list(st.session_state.supporting_materials or [])
    urls = list(st.session_state.supporting_urls or [])
    if not materials and not urls:
        return
    with st.container(border=True):
        st.markdown("**Prepared Supporting Materials**")
        summary = st.columns(3)
        summary[0].metric("Files", len(materials))
        summary[1].metric("Links", len(urls))
        summary[2].metric("RAG", "Armed")
        if materials:
            st.caption(", ".join(item.get("name", "attachment") for item in materials[:6]))
        if urls:
            st.caption("Auto-detected links: " + " | ".join(urls[:4]))


def normalize_prose_markdown(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"(?m)^(#{1,6})(\S)", r"\1 \2", text)
    text = re.sub(r"(?m)^\s*(\*{3,}|_{3,})\s*(.+?)\s*(\*{3,}|_{3,})\s*$", r"**\2**", text)
    text = re.sub(r"(?m)^\s*(\*{2}|_{2})\s*(.+?)\s*(\*{2}|_{2})\s*$", r"**\2**", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def render_prose_block(title: str, content: str):
    normalized = normalize_prose_markdown(content)
    if not normalized:
        return
    st.markdown(f"<div class='architect-section-label'>{title}</div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(normalized)


def render_intelligence_signals():
    if not st.session_state.iteration_history:
        return

    latest = st.session_state.iteration_history[-1]
    janitor = st.session_state.latest_janitor_report or {}
    memory_stats = st.session_state.memory_stats or {}
    similar_cases_used = "YES" if memory_stats.get("count", 0) > 0 else "NO"
    st.markdown("##### Intelligence Signals")
    render_summary_cards(
        [
            ("Learning State", "ACTIVE" if st.session_state.iteration > 1 else "INITIAL"),
            ("Confidence", str(latest.get("review_confidence", "normal")).upper()),
            ("Similar Cases", similar_cases_used),
            ("Janitor Source", "READY" if janitor.get("repair_brief") else "LIGHT"),
        ]
    )
    st.caption(
        f"Verification: {str(latest.get('verification_status', 'UNVERIFIED')).upper()} · "
        f"Adaptive state: {'stable' if st.session_state.stable_mode else 'adaptive'} · "
        f"Retries this run: {max(st.session_state.iteration - 1, 0)} · "
        f"Preflight events: {st.session_state.preflight_events} · "
        f"Repair events: {st.session_state.repair_events}"
    )


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
    raw = html.unescape(normalize_visible_message(content)).strip()
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
            render_prose_block("Architect Response", raw)
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
                    render_prose_block("Architect Insights", leading)

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
            render_prose_block("Architect Insights", trailing)


def render_message(role: str, content: str):
    role_color = (
        "#8b5e1a" if role == "Auditor"
        else "#0f1b2d" if role == "Architect"
        else "#1f5eff"
    )
    if role == "Architect":
        render_architect_content(content)
        return
    if role == "Critics":
        return

    safe_content = html.escape(normalize_visible_message(content)).replace("\n", "<br>")
    st.markdown(f"""
    <div class="agent-card">
        <b style="color:{role_color};text-transform:uppercase;letter-spacing:2px;font-size:0.8rem;">{role}</b>
        <div style="margin-top:15px;line-height:1.6;">{safe_content}</div>
    </div>
    """, unsafe_allow_html=True)


def get_latest_message(role: str) -> str:
    for message in reversed(st.session_state.messages):
        if message.get("role") == role:
            return str(message.get("content", "") or "")
    return ""


def render_auditor_surface():
    if st.session_state.step == "input" and not st.session_state.current_task:
        return

    auditor_message = normalize_visible_message(get_latest_message("Auditor"))
    if st.session_state.audit_status == "needs_clarification" or st.session_state.pending_questions:
        with st.container(border=True):
            st.subheader("Auditor Intake")
            st.caption("The auditor is asking for more context before the case proceeds.")
            if auditor_message:
                st.write(auditor_message)
            elif st.session_state.pending_questions:
                for question in st.session_state.pending_questions:
                    st.markdown(f"- {question}")
    elif st.session_state.audit_status == "passed":
        with st.container(border=True):
            st.subheader("Auditor Intake")
            st.success("The brief is specific enough to proceed.")
            if st.session_state.audit_resolution_note:
                st.caption(st.session_state.audit_resolution_note)
            cleaned = str(auditor_message or "").strip().lower()
            if auditor_message and "specific enough to proceed" not in cleaned and "check passed" not in cleaned:
                st.write(auditor_message)


def render_architect_surface():
    architect_message = get_latest_message("Architect") or st.session_state.current_solution
    if not architect_message:
        return
    with st.container(border=True):
        st.subheader("Architect Draft")
        render_architect_content(architect_message)


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
    st.session_state.benchmark_stats = result.debug_info.get("benchmark_stats", {"count": 0, "avg_score": 0.0, "avg_cost": 0.0, "avg_iterations": 0.0, "benchmark_runs": 0})
    st.session_state.benchmark_by_task_mode = result.debug_info.get("benchmark_by_task_mode", {})
    st.session_state.benchmark_by_strategy = result.debug_info.get("benchmark_by_strategy", {})
    st.session_state.benchmark_by_case = result.debug_info.get("benchmark_by_case", {})
    st.session_state.recent_benchmarks = result.debug_info.get("recent_benchmarks", [])
    st.session_state.decision_trace = result.debug_info.get("decision_trace", [])
    st.session_state.unresolved_issues = result.debug_info.get("unresolved_issues", {"tech": [], "logic": []})
    st.session_state.latest_janitor_report = result.debug_info.get("latest_janitor_report", {})
    st.session_state.latest_result_status = result.debug_info.get("latest_result_status", "VALID")
    st.session_state.evidence_preview = result.debug_info.get("evidence", {})
    st.session_state.run_id = result.debug_info.get("run_id", "")


def execute_deliberation_run(auto_mode: bool, target_score: float, max_iterations: int, manual_override: str):
    st.session_state.run_in_progress = True
    try:
        with st.spinner("Running intelligence pipeline..."):
            orchestrator = ArbiterOrchestrator(
                task_mode=st.session_state.task_mode,
                auto_mode=auto_mode,
                target_score=target_score,
                max_iterations=max_iterations,
                stable_mode=st.session_state.stable_mode,
                benchmark_mode=st.session_state.benchmark_mode,
                benchmark_strategy=st.session_state.benchmark_strategy if st.session_state.benchmark_mode else "",
                benchmark_pack=st.session_state.benchmark_pack if st.session_state.benchmark_mode else "",
                benchmark_case_id=st.session_state.benchmark_case_id if st.session_state.benchmark_mode else "",
                benchmark_case_title=(get_case_by_id(st.session_state.benchmark_case_id) or {}).get("title", "") if st.session_state.benchmark_mode else "",
            )
        result = run_orchestrator_safe(
            orchestrator,
            user_input=st.session_state.current_task,
            clarification="already_audited",
            manual_override=manual_override,
            allow_complex_software_team=st.session_state.software_team_consent,
            software_team_profile=st.session_state.software_team_profile,
            supporting_materials=st.session_state.supporting_materials,
            supporting_urls=st.session_state.supporting_urls,
        )
        sync_state_from_result(result)
        st.session_state.retry_override = ""
    finally:
        st.session_state.run_in_progress = False


def get_runtime_health_snapshot() -> dict:
    memory_store = get_memory_store()
    issues = []
    checks = {
        "version": __version__,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "memory_entries_ready": (PROJECT_ROOT / ".arbiter_memory" / "memory_entries.jsonl").exists(),
        "project_notes_ready": (PROJECT_ROOT / ".arbiter_memory" / "project_notes.json").exists(),
        "project_notes_api": hasattr(memory_store, "retrieve_project_notes") and hasattr(memory_store, "add_project_note"),
        "memory_governance_api": hasattr(memory_store, "recent_entries") and hasattr(memory_store, "set_memory_lifecycle"),
        "memory_flush_api": hasattr(memory_store, "flush"),
        "decision_trace_ready": isinstance(st.session_state.decision_trace, list),
        "benchmark_suite_ready": bool(get_benchmark_packs()),
        "eval_fixtures": count_eval_fixtures(),
        "model_catalog_count": len(REGISTRY.all_model_ids()),
    }
    if not checks["memory_entries_ready"]:
        issues.append("Persistent memory file is missing.")
    if not checks["project_notes_ready"]:
        issues.append("Project notes file is missing.")
    if not checks["project_notes_api"]:
        issues.append("Project-notes API is not fully loaded. A full restart may be needed.")
    if not checks["memory_governance_api"]:
        issues.append("Memory governance controls are not fully loaded. A full restart may be needed.")
    if not checks["benchmark_suite_ready"]:
        issues.append("Benchmark suite could not load any benchmark scenarios.")
    if not checks["memory_flush_api"]:
        issues.append("Memory flush controls are not fully loaded. A full restart may be needed.")
    overall = "HEALTHY" if not issues else "ATTENTION"
    return {"overall": overall, "checks": checks, "issues": issues}


def render_health_and_decisions():
    snapshot = get_runtime_health_snapshot()
    st.markdown("#### System Health")
    top = st.columns(4)
    top[0].metric("Runtime", snapshot["overall"])
    top[1].metric("Version", snapshot["checks"]["version"])
    top[2].metric(
        "Memory",
        "READY" if snapshot["checks"]["memory_entries_ready"] and snapshot["checks"]["project_notes_ready"] else "CHECK",
    )
    top[3].metric(
        "Governance API",
        "READY" if snapshot["checks"]["memory_governance_api"] else "RESTART",
    )

    infra = st.columns(4)
    infra[0].metric("Python", snapshot["checks"]["python"])
    infra[1].metric("Eval Fixtures", snapshot["checks"]["eval_fixtures"])
    infra[2].metric("Model Catalog", snapshot["checks"]["model_catalog_count"])
    infra[3].metric("Flush API", "READY" if snapshot["checks"]["memory_flush_api"] else "RESTART")

    providers = st.columns(4)
    providers[0].metric("Groq", "YES" if os.getenv("GROQ_API_KEY") else "NO")
    providers[1].metric("OpenAI", "YES" if os.getenv("OPENAI_API_KEY") else "NO")
    providers[2].metric("Gemini", "YES" if os.getenv("GEMINI_API_KEY") else "NO")
    providers[3].metric("Claude", "YES" if os.getenv("ANTHROPIC_API_KEY") else "NO")

    provider_rows = provider_catalog_rows()
    if provider_rows:
        st.markdown("#### Provider Catalog Status")
        st.dataframe(provider_rows, use_container_width=True, hide_index=True)

    alias_rows = [
        {"alias": alias, "resolved_model": target or "unresolved"}
        for alias, target in sorted(REGISTRY.aliases().items())
    ]
    if alias_rows:
        st.markdown("#### Stable Alias Resolution")
        st.dataframe(alias_rows, use_container_width=True, hide_index=True)

    if snapshot["issues"]:
        st.warning("Runtime health needs attention.")
        for issue in snapshot["issues"]:
            st.markdown(f"- {issue}")
    else:
        st.caption("Runtime health checks passed. Memory, benchmark, and governance features are loaded.")

    st.markdown("#### Decision Trace")
    if st.session_state.decision_trace:
        for item in st.session_state.decision_trace[-8:]:
            st.markdown(
                f"- **{item.get('category', 'decision')}** · {item.get('summary', '')}  "
                f"`({item.get('confidence', 'n/a')})`"
            )
            if item.get("reason"):
                st.caption(item.get("reason"))
    else:
        st.caption("No decision trace recorded yet.")


def render_benchmark_panel():
    stats = st.session_state.benchmark_stats or {}
    st.markdown("#### Benchmark Overview")
    metric_cols = st.columns(5)
    metric_cols[0].metric("Stored Runs", stats.get("count", 0))
    metric_cols[1].metric("Avg Score", stats.get("avg_score", 0.0))
    metric_cols[2].metric("Avg Cost", f"${stats.get('avg_cost', 0.0):.4f}")
    metric_cols[3].metric("Avg Iters", stats.get("avg_iterations", 0.0))
    metric_cols[4].metric("Bench Runs", stats.get("benchmark_runs", 0))

    quality_cols = st.columns(4)
    quality_cols[0].metric("Valid Runs", stats.get("valid_runs", 0))
    quality_cols[1].metric("Valid Rate", f"{stats.get('valid_rate', 0.0)}%")
    quality_cols[2].metric("Verified Rate", f"{stats.get('verified_rate', 0.0)}%")
    quality_cols[3].metric("Ready Rate", f"{stats.get('ready_rate', 0.0)}%")

    secondary_quality_cols = st.columns(3)
    secondary_quality_cols[0].metric("Diagnostic Rate", f"{stats.get('diagnostic_rate', 0.0)}%")
    secondary_quality_cols[1].metric("Avg Valid Score", stats.get("avg_valid_score", 0.0))
    secondary_quality_cols[2].metric("Ready Runs", stats.get("ready_runs", 0))

    if stats.get("benchmark_runs", 0):
        st.caption(
            f"Benchmark-only runs are averaging {stats.get('avg_benchmark_score', 0.0)}/10 "
            "across the currently stored history."
        )

    summary_tab, strategy_tab, case_tab, recent_tab = st.tabs(
        ["By Task Mode", "By Strategy", "By Case", "Recent Runs"]
    )
    with summary_tab:
        if st.session_state.benchmark_by_task_mode:
            for mode, info in st.session_state.benchmark_by_task_mode.items():
                st.markdown(
                    f"- **{mode}** · runs {info.get('count', 0)} · avg score {info.get('avg_score', 0.0)} · "
                    f"avg cost ${info.get('avg_cost', 0.0):.4f} · avg iters {info.get('avg_iterations', 0.0)} · "
                    f"verified {info.get('verified_rate', 0.0)}% · ready {info.get('ready_rate', 0.0)}%"
                )
        else:
            st.caption("No task-mode benchmark data yet.")
    with strategy_tab:
        if st.session_state.benchmark_by_strategy:
            strategy_labels = {
                "arbiter_full_loop": "Arbiter Full Loop",
                "baseline_single_pass": "Baseline Single Pass",
                "manual_compare": "Manual Compare",
                "unlabeled": "Unlabeled",
            }
            for strategy, info in st.session_state.benchmark_by_strategy.items():
                label = strategy_labels.get(strategy, strategy.replace("_", " ").title())
                st.markdown(
                    f"- **{label}** · runs {info.get('count', 0)} · avg score {info.get('avg_score', 0.0)} · "
                    f"avg cost ${info.get('avg_cost', 0.0):.4f} · avg iters {info.get('avg_iterations', 0.0)} · "
                    f"valid {info.get('valid_rate', 0.0)}% · verified {info.get('verified_rate', 0.0)}% · "
                    f"ready {info.get('ready_rate', 0.0)}%"
                )
        else:
            st.caption("No strategy-labeled benchmark runs yet.")
    with case_tab:
        if st.session_state.benchmark_by_case:
            ranked_cases = sorted(
                st.session_state.benchmark_by_case.items(),
                key=lambda item: item[1].get("count", 0),
                reverse=True,
            )
            for case_id, info in ranked_cases[:8]:
                st.markdown(
                    f"- **{info.get('title', case_id)}** · {info.get('pack', 'General')} · "
                    f"runs {info.get('count', 0)} · avg score {info.get('avg_score', 0.0)} · "
                    f"avg cost ${info.get('avg_cost', 0.0):.4f}"
                )
        else:
            st.caption("No benchmark-case history yet.")
    with recent_tab:
        if st.session_state.recent_benchmarks:
            for run in reversed(st.session_state.recent_benchmarks[-6:]):
                st.markdown(
                    f"- `{run.get('run_id', 'n/a')}` · {run.get('task_mode', 'Unknown')} · "
                    f"score {run.get('best_score', 0.0)} · cost ${run.get('total_cost', 0.0):.4f} · "
                    f"{run.get('validity_status', 'UNKNOWN')} · {run.get('benchmark_strategy', 'unlabeled')}"
                )
        else:
            st.caption("No recent benchmark runs yet.")


def render_memory_governance():
    memory_store = get_memory_store()
    control_cols = st.columns([1.2, 1.8, 1.2])
    lifecycle_filter = control_cols[0].selectbox(
        "Memory Lifecycle Filter",
        ["all", "active", "caution", "conflicted", "obsolete"],
        index=0,
        key="memory_governance_filter",
    )
    memory_search = control_cols[1].text_input(
        "Search memory / notes",
        placeholder="Task text, note text, memory ID...",
        key="memory_governance_search",
    )
    if control_cols[2].button("Flush Store", key="flush_governance_store"):
        if hasattr(memory_store, "flush"):
            flushed = bool(memory_store.flush())
            st.session_state.memory_stats = memory_store.stats()
            if flushed:
                st.success("Memory store flushed to disk.")
            else:
                st.caption("No pending memory changes needed flushing.")
        else:
            st.warning("Flush control is not available in this runtime.")

    entries = memory_store.recent_entries(limit=20, include_obsolete=True) if hasattr(memory_store, "recent_entries") else []
    notes = memory_store.project_notes() if hasattr(memory_store, "project_notes") else []
    query = str(memory_search or "").strip().lower()
    if query:
        entries = [
            entry for entry in entries
            if query in " ".join(
                [
                    str(entry.get("memory_id", "")),
                    str(entry.get("task_mode", "")),
                    str(entry.get("task_text", "")),
                ]
            ).lower()
        ]
        notes = [
            note for note in notes
            if query in " ".join(
                [
                    str(note.get("note_id", "")),
                    str(note.get("task_mode", "")),
                    str(note.get("text", "")),
                ]
            ).lower()
        ]

    summary = st.columns(4)
    lifecycle_stats = st.session_state.memory_stats.get("memory_lifecycle", {}) or {}
    summary[0].metric("Visible Entries", len(entries))
    summary[1].metric("Visible Notes", len(notes))
    summary[2].metric("Active", int(lifecycle_stats.get("active", 0) or 0))
    summary[3].metric("Conflicted", int(lifecycle_stats.get("conflicted", 0) or 0))

    entry_tab, note_tab = st.tabs(["Memory Entries", "Project Notes"])

    with entry_tab:
        filtered_entries = [
            entry for entry in entries
            if lifecycle_filter == "all" or entry.get("memory_lifecycle") == lifecycle_filter
        ]
        if not filtered_entries:
            st.caption("No memory entries match this filter yet.")
        for entry in filtered_entries:
            title = (
                f"{entry.get('memory_lifecycle', 'caution').upper()} · "
                f"{entry.get('task_mode', 'Unknown')} · "
                f"{float(entry.get('avg_score', 0.0) or 0.0):.1f}/10"
            )
            with st.expander(title, expanded=False):
                st.caption(
                    f"{entry.get('memory_id', 'n/a')} · {entry.get('timestamp_utc', '')} · "
                    f"{entry.get('validity_status', 'UNKNOWN')} · {entry.get('score_status', 'final')}"
                )
                st.write(entry.get("task_text", ""))
                if entry.get("memory_reasons"):
                    st.markdown("**Trust Notes**")
                    for reason in entry.get("memory_reasons", []):
                        st.markdown(f"- {reason}")
                cols = st.columns(4)
                for label, lifecycle in zip(
                    cols,
                    ["active", "caution", "conflicted", "obsolete"],
                ):
                    if label.button(
                        lifecycle.title(),
                        key=f"mem_lifecycle_{entry.get('memory_id')}_{lifecycle}",
                    ):
                        if hasattr(memory_store, "set_memory_lifecycle"):
                            memory_store.set_memory_lifecycle(entry.get("memory_id", ""), lifecycle)
                            st.session_state.memory_stats = memory_store.stats()
                            st.rerun()

    with note_tab:
        if not notes:
            st.caption("No project notes stored yet.")
        for note in reversed(notes[-20:]):
            state_label = "ACTIVE" if note.get("active", True) else "INACTIVE"
            with st.expander(f"{state_label} · {note.get('task_mode', 'General')}", expanded=False):
                st.caption(f"{note.get('note_id', 'n/a')} · {note.get('timestamp_utc', '')}")
                st.write(note.get("text", ""))
                toggle_label = "Deactivate" if note.get("active", True) else "Reactivate"
                if st.button(toggle_label, key=f"note_toggle_{note.get('note_id')}"):
                    if hasattr(memory_store, "set_project_note_active"):
                        memory_store.set_project_note_active(note.get("note_id", ""), not note.get("active", True))
                        st.session_state.memory_stats = memory_store.stats()
                        st.rerun()


def render_benchmark_lab():
    st.markdown("#### Evaluation Lab")
    packs = get_benchmark_packs()
    if st.session_state.benchmark_pack not in packs:
        st.session_state.benchmark_pack = packs[0]
    selected_pack = st.selectbox(
        "Scenario Pack",
        packs,
        index=packs.index(st.session_state.benchmark_pack),
        help="Use named evaluation scenarios to compare Arbiter on repeatable tasks.",
    )
    st.session_state.benchmark_pack = selected_pack

    cases = get_benchmark_cases(pack=selected_pack)
    case_labels = [f"{case['title']} · {case['task_mode']}" for case in cases]
    case_index = 0
    if st.session_state.benchmark_case_id:
        for idx, case in enumerate(cases):
            if case["id"] == st.session_state.benchmark_case_id:
                case_index = idx
                break
    selected_label = st.selectbox("Scenario", case_labels, index=case_index)
    selected_case = cases[case_labels.index(selected_label)]
    st.session_state.benchmark_case_id = selected_case["id"]

    st.session_state.benchmark_strategy = st.radio(
        "Run Strategy",
        [
            "arbiter_full_loop",
            "baseline_single_pass",
        ],
        index=0 if st.session_state.benchmark_strategy != "baseline_single_pass" else 1,
        format_func=lambda item: {
            "arbiter_full_loop": "Arbiter Full Loop",
            "baseline_single_pass": "Baseline Single Pass",
        }.get(item, item),
        help="Baseline Single Pass keeps the run to one direct pass so you can compare it against the full Arbiter loop.",
    )

    meta = st.columns(3)
    meta[0].metric("Pack", selected_case["pack"])
    meta[1].metric("Mode", selected_case["task_mode"])
    meta[2].metric(
        "Strategy",
        "Full Loop" if st.session_state.benchmark_strategy == "arbiter_full_loop" else "Single Pass",
    )

    st.markdown(
        f"""
        <div class="lab-card">
            <div class="lab-card-label">Scenario Goal</div>
            <div class="lab-card-text">{html.escape(selected_case["goal"])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("**Masked Scenario Preview**")
    st.code(mask_text(selected_case["prompt"]), language="text")

    with st.expander("Reveal Full Scenario", expanded=False):
        st.code(selected_case["prompt"], language="text")

    cols = st.columns(2)
    if cols[0].button("Load Scenario Into Task", key="load_benchmark_case"):
        st.session_state.task_mode = selected_case["task_mode"]
        st.session_state.task_draft = selected_case["prompt"]
        st.session_state.current_task = selected_case["prompt"]
        st.session_state.task_input_seq += 1
        st.session_state.step = "input"
        st.success("Scenario loaded into the task editor.")
        st.rerun()
    if cols[1].button("Tag Current Task For Evaluation", key="tag_benchmark_case"):
        st.session_state.benchmark_mode = True
        st.session_state.current_task = st.session_state.current_task or st.session_state.task_draft
        st.success("Current task tagged for evaluation tracking.")


def render_advanced_hub():
    st.markdown("### Operator Console")
    st.caption("Internal evaluation, diagnostics, and memory governance live here.")
    tabs = st.tabs(["Evaluation Lab", "Metrics", "System Trace", "Run Memory", "Memory Governance"])
    with tabs[0]:
        render_benchmark_lab()
    with tabs[1]:
        render_benchmark_panel()
    with tabs[2]:
        render_health_and_decisions()
    with tabs[3]:
        render_memory_panel()
    with tabs[4]:
        render_memory_governance()


def render_telemetry_panel():
    if not st.session_state.iteration_history:
        return

    latest = st.session_state.iteration_history[-1]
    best = st.session_state.best_iteration
    weights = TASK_PROFILES[st.session_state.task_mode].get("score_weights", {"tech": 0.5, "logic": 0.5})
    raw_avg_score = float(latest.get("raw_avg_score", latest.get("avg", 0.0)) or 0.0)
    final_score = float(latest.get("avg", 0.0) or 0.0)
    current_label = "Diagnostic Final" if latest.get("score_status") == "diagnostic" else "Current Final"
    current_meta_prefix = "Diagnostic only" if latest.get("score_status") == "diagnostic" else "Current review"
    if best:
        best_value = f"Round {best['iter']}"
        best_meta = f"Technical {best['tech']}/10 · Logic {best['logic']}/10 · Weighted average {best['avg']:.1f}"
    else:
        best_value = "No valid round"
        best_meta = "Only diagnostic or blocked runs so far"
    render_summary_cards(
        [
            ("Task Mode", st.session_state.task_mode),
            (current_label, f"{final_score:.1f}/10"),
            ("Critic Avg", f"{raw_avg_score:.1f}/10"),
            ("Best Round", best_value),
            ("Adaptive State", "Stable" if st.session_state.stable_mode else ("Rewrite" if st.session_state.rewrite_mode else "Refine")),
            ("Memory", f"{st.session_state.memory_stats.get('count', 0)} entries"),
        ]
    )

    st.caption(
        f"{TASK_PROFILES[st.session_state.task_mode]['tag']} · "
        f"{current_meta_prefix} · Technical {latest['tech']}/10 · Logic {latest['logic']}/10 · "
        f"Technical weight {weights['tech']:.2f} / Logic weight {weights['logic']:.2f}"
    )
    st.caption(
        f"{best_meta} · Provider {st.session_state.provider_lock.upper()} · "
        f"Preflight {st.session_state.preflight_events} · Repairs {st.session_state.repair_events}"
    )
    if abs(final_score - raw_avg_score) > 0.01:
        st.caption(f"Verification pressure changed the round from {raw_avg_score:.1f}/10 to {final_score:.1f}/10.")


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

        controls = st.columns([1.2, 1.2, 3])
        if controls[0].button("Flush Memory Store", key="flush_memory_store"):
            if hasattr(get_memory_store(), "flush"):
                flushed = bool(get_memory_store().flush())
                st.session_state.memory_stats = get_memory_store().stats()
                if flushed:
                    st.success("Memory store flushed to disk.")
                else:
                    st.caption("No pending memory changes needed flushing.")
            else:
                st.warning("Flush control is not available in this runtime.")
        controls[1].metric("Retrieved IDs", len(related_memory_ids))
        controls[2].caption(
            "Session writes append new entries immediately. Flush rewrites lifecycle/versioning updates into the durable store when needed."
        )

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
    verification_status = str(latest.get("verification_status", "UNVERIFIED")).upper()
    verification_score = float(latest.get("verification_score", 0.0) or 0.0)
    verification_summary = str(latest.get("verification_summary", "") or "").strip()
    verification_checks = latest.get("verification_checks", []) or []
    ship_readiness = str(latest.get("ship_readiness", "UNASSESSED")).upper()
    raw_avg_score = float(latest.get("raw_avg_score", latest.get("avg", 0.0)) or 0.0)
    calibrated_score = float(latest.get("avg", 0.0) or 0.0)
    tech_confirmed = latest.get("tech_confirmed_defects", []) or []
    tech_risks = latest.get("tech_risks", []) or []
    tech_improvements = latest.get("tech_improvements", []) or []
    logic_confirmed = latest.get("logic_confirmed_defects", []) or []
    logic_risks = latest.get("logic_risks", []) or []
    logic_improvements = latest.get("logic_improvements", []) or []
    software_team_used = bool(latest.get("software_team_active", False))
    software_team_domains = latest.get("software_team_detected_domains", []) or latest.get("software_team_signals", []) or []
    software_team_technologies = latest.get("software_team_detected_technologies", []) or []
    software_team_roles = latest.get("software_team_roles", []) or latest.get("software_team_specialists", []) or []
    software_team_reason = str(latest.get("software_team_reason", "") or latest.get("software_team_summary", "")).strip()
    software_team_signal_reasons = latest.get("software_team_signal_reasons", []) or []
    software_team_complexity_score = int(latest.get("software_team_complexity_score", 0) or 0)
    software_team_complexity_level = str(latest.get("software_team_complexity_level", "standard") or "standard")
    software_team_recommended = bool(latest.get("software_team_recommended", software_team_used))
    software_team_approval_missing = bool(latest.get("software_team_approval_missing", False))
    software_team_user_approved = bool(latest.get("software_team_user_approved", False))
    software_team_profile = str(latest.get("software_team_profile", "") or "").strip()
    software_team_estimated_cost_multiplier = float(latest.get("software_team_estimated_cost_multiplier", 1.0) or 1.0)
    software_team_estimated_latency_multiplier = float(latest.get("software_team_estimated_latency_multiplier", 1.0) or 1.0)
    software_team_architecture_summary = str(latest.get("software_team_architecture_summary", "") or "").strip()
    software_team_specialist_summaries = latest.get("software_team_specialist_summaries", []) or []
    software_team_role_models = dict(latest.get("software_team_role_models", {}) or {})

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

    def verification_ui_message(status: str, score: float, summary: str) -> tuple[str, str]:
        clean_summary = str(summary or "").strip()
        if str(status or "").upper() == "BLOCKED":
            return (
                "warning",
                clean_summary
                or "Verification was blocked by a provider or process failure. This does not confirm the content is wrong; it means the review chain could not finish cleanly.",
            )
        if clean_summary:
            return ("info", f"Verification {score:.2f} · {clean_summary}")
        return ("info", "")

    with st.container(border=True):
        st.subheader("The Arbiter Order")
        score_delta = calibrated_score - raw_avg_score
        render_summary_cards(
            [
                ("Status", validity_status),
                ("Technical Score", f"{latest['tech']}/10"),
                ("Logic Score", f"{latest['logic']}/10"),
                ("Critic Average", f"{raw_avg_score:.1f}/10"),
                ("Final Verified Score", f"{calibrated_score:.1f}/10"),
                ("Verification Pressure", f"{score_delta:+.1f}"),
                ("Confidence", review_confidence.upper()),
                ("Verification", verification_status),
                ("Readiness", ship_readiness),
            ]
        )
        if abs(calibrated_score - raw_avg_score) > 0.01:
            st.caption(
                f"Score type: {score_status.upper()} · Critics averaged {raw_avg_score:.1f}/10, "
                f"then verification adjusted the final score to {calibrated_score:.1f}/10. · {status_note}"
            )
        else:
            st.caption(f"Score type: {score_status.upper()} · {status_note}")
        st.markdown(
            """
            <div class="arbiter-help-inline">
                <span>How these scores work</span>
                <span class="arbiter-help-icon" tabindex="0">?
                    <span class="arbiter-help-bubble">
                        <b>Critic Average</b> is the raw score from the technical and logic critics.
                        <br><br>
                        <b>Final Verified Score</b> is the final round score after deterministic verification
                        adjusts that critic average up or down based on caution points, confirmed defects,
                        and structural validation.
                    </span>
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        message_kind, message_text = verification_ui_message(
            verification_status,
            verification_score,
            verification_summary,
        )
        if message_text:
            if message_kind == "warning":
                st.warning(message_text)
            else:
                st.info(message_text)
        flagged_verification_checks = [
            item for item in verification_checks
            if str(item.get("status", "")).lower() in {"fail", "caution"}
        ]
        if flagged_verification_checks:
            st.markdown("**Verification Checks**")
            for item in flagged_verification_checks[:4]:
                label = str(item.get("name", "check")).replace("_", " ").title()
                detail = str(item.get("detail", "") or "").strip()
                st.markdown(f"- **{label}**: {detail}")

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
                "The Arbiter reran the Logic Critic with a narrower brief and lowered review confidence."
            )

        with st.container(border=True):
            render_summary_cards(
                [
                    ("Learning Status", memory_status),
                    ("Consensus", f"{memory_consensus:.2f}"),
                    ("Retry Source", "Janitor"),
                    ("Verifier Score", f"{verification_score:.2f}"),
                    ("Tech Defects", len(tech_confirmed)),
                    ("Logic Defects", len(logic_confirmed)),
                ]
            )

        st.markdown("### Janitor Resolution")
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

    if st.session_state.task_mode == "Software & IT":
        with st.expander("Software Architect Team", expanded=False):
            if not software_team_used and not software_team_recommended:
                st.caption("Not used for this task.")
            elif software_team_approval_missing:
                st.warning(
                    "A larger software team was recommended for this task, but explicit approval was not present. "
                    "The run stayed on the normal architect path."
                )
                summary_cards = st.columns(5)
                summary_cards[0].metric("Recommendation", "Yes")
                summary_cards[1].metric("Executed", "No")
                summary_cards[2].metric("Complexity", software_team_complexity_level.replace("_", " ").title())
                summary_cards[3].metric("Cost", f"{software_team_estimated_cost_multiplier:.2f}x")
                summary_cards[4].metric("Time", f"{software_team_estimated_latency_multiplier:.2f}x")
                if software_team_profile:
                    st.caption(f"Recommended profile: {software_team_profile.replace('_', ' ').title()}")
                if software_team_reason:
                    st.caption(software_team_reason)
                if software_team_domains:
                    st.markdown("**Detected Domains**")
                    st.caption(", ".join(software_team_domains))
                if software_team_roles:
                    st.markdown("**Recommended Roles**")
                    render_list(software_team_roles)
            else:
                summary_cards = st.columns(7)
                summary_cards[0].metric("Team Mode", "Used")
                summary_cards[1].metric("Profile", software_team_profile.replace("_", " ").title() or "Standard")
                summary_cards[2].metric("Complexity", software_team_complexity_level.replace("_", " ").title())
                summary_cards[3].metric("Signal Score", f"{software_team_complexity_score}/4")
                summary_cards[4].metric("Domains", len(software_team_domains))
                summary_cards[5].metric("Cost", f"{software_team_estimated_cost_multiplier:.2f}x")
                summary_cards[6].metric("Time", f"{software_team_estimated_latency_multiplier:.2f}x")
                if software_team_reason:
                    st.caption(software_team_reason)
                if software_team_user_approved:
                    st.caption("User approved the larger team path before execution.")
                if software_team_domains:
                    st.markdown("**Detected Domains**")
                    st.caption(", ".join(software_team_domains))
                if software_team_technologies:
                    st.markdown("**Detected Technologies / Frameworks**")
                    st.caption(", ".join(software_team_technologies))
                if software_team_signal_reasons:
                    st.markdown("**Activation Signals**")
                    render_list(software_team_signal_reasons)
                if software_team_roles:
                    st.markdown("**Roles Selected**")
                    render_list(software_team_roles)
                if software_team_role_models:
                    st.markdown("**Role To Model Routing**")
                    for role, model in software_team_role_models.items():
                        st.markdown(f"- **{role}** → `{model}`")
                if software_team_architecture_summary:
                    st.markdown("**Architecture Summary**")
                    st.write(software_team_architecture_summary)
                if software_team_specialist_summaries:
                    st.markdown("**Specialist Snapshots**")
                    for item in software_team_specialist_summaries:
                        role = str(item.get("role", "Specialist") or "Specialist")
                        top_line = str(item.get("top_recommendation", "") or item.get("scope", "")).strip()
                        risk = str(item.get("risk", "") or "").strip()
                        with st.container(border=True):
                            st.markdown(f"**{role}**")
                            if top_line:
                                st.caption(top_line)
                            if risk:
                                st.markdown(f"- Risk: {risk}")

    evidence_preview = dict(st.session_state.evidence_preview or {})
    with st.expander("Evidence Context", expanded=False):
        if not evidence_preview.get("source_count"):
            st.caption("No supporting files or links were used for this task.")
        else:
            sources = list(evidence_preview.get("sources", []) or [])
            retrieved_chunks = list(evidence_preview.get("retrieved_chunks", []) or [])
            warnings = list(evidence_preview.get("warnings", []) or [])
            summary_cards = st.columns(4)
            summary_cards[0].metric("Sources", int(evidence_preview.get("source_count", 0) or 0))
            summary_cards[1].metric("Retrieved Chunks", len(retrieved_chunks))
            summary_cards[2].metric("Warnings", int(evidence_preview.get("warning_count", 0) or 0))
            summary_cards[3].metric("RAG", "Used" if evidence_preview.get("rag_used") else "Idle")
            if sources:
                st.markdown("**Source Inventory**")
                for source in sources[:8]:
                    label = f"{source.get('name', 'source')} · {source.get('source_type', 'file')} · {source.get('char_count', 0)} chars"
                    st.markdown(f"- {label}")
            if warnings:
                st.markdown("**Evidence Warnings**")
                render_list(warnings)
            if retrieved_chunks:
                st.markdown("**Retrieved Evidence Excerpts**")
                for chunk in retrieved_chunks[:6]:
                    with st.container(border=True):
                        st.caption(
                            f"{chunk.get('source_name', 'source')} · chunk {int(chunk.get('index', 0)) + 1} · score {float(chunk.get('score', 0.0)):.2f}"
                        )
                        st.write(chunk.get("snippet", ""))

    with st.expander("Counsel Positions", expanded=False):
        counsel_left, counsel_right = st.columns(2)
        with counsel_left:
            with st.container(border=True):
                st.markdown("**Technical Counsel**")
                st.caption(normalize_visible_message(latest.get('tech_critique', 'No issues.')))
                render_summary_cards(
                    [
                        ("Confirmed Defects", len(tech_confirmed)),
                        ("Risks", len(tech_risks)),
                        ("Repair Steps", len(latest.get("tech_repair_contract", []) or [])),
                    ]
                )
                if tech_confirmed:
                    render_list(tech_confirmed[:3])
                if tech_risks:
                    st.caption("Top technical risk")
                    st.markdown(f"- {tech_risks[0]}")
                if latest.get("tech_repair_contract"):
                    st.caption("Top technical repair step")
                    st.markdown(f"- {latest.get('tech_repair_contract', [])[0]}")
        with counsel_right:
            with st.container(border=True):
                st.markdown("**Logic Counsel**")
                st.caption(normalize_visible_message(latest.get('logic_critique', 'No issues.')))
                render_summary_cards(
                    [
                        ("Confirmed Defects", len(logic_confirmed)),
                        ("Risks", len(logic_risks)),
                        ("Repair Steps", len(latest.get("logic_repair_contract", []) or [])),
                    ]
                )
                if logic_confirmed:
                    render_list(logic_confirmed[:3])
                if logic_risks:
                    st.caption("Top logic risk")
                    st.markdown(f"- {logic_risks[0]}")
                if latest.get("logic_repair_contract"):
                    st.caption("Top logic repair step")
                    st.markdown(f"- {latest.get('logic_repair_contract', [])[0]}")

    with st.expander("Review Transcript", expanded=False):
        st.markdown("**Technical Counsel**")
        st.markdown("Confirmed Defects")
        render_list(tech_confirmed)
        st.markdown("Risks / Assumptions")
        render_list(tech_risks)
        if latest.get("tech_repair_contract"):
            st.markdown("Technical Repair Contract")
            render_list(latest.get("tech_repair_contract", []))
        if tech_improvements:
            st.markdown("Technical Improvements")
            render_list(tech_improvements)

        st.markdown("---")
        st.markdown("**Logic Counsel**")
        st.markdown("Confirmed Defects")
        render_list(logic_confirmed)
        st.markdown("Risks / Assumptions")
        render_list(logic_risks)
        if latest.get("logic_repair_contract"):
            st.markdown("Logic Repair Contract")
            render_list(latest.get("logic_repair_contract", []))
        if logic_improvements:
            st.markdown("Logic Improvements")
            render_list(logic_improvements)


def render_visual_blueprint():
    if not st.session_state.iteration_history:
        return

    latest = st.session_state.iteration_history[-1]
    janitor = {
        "pending": latest.get("janitor_pending", []),
        "preserve": latest.get("janitor_preserve", []),
    }
    solution = get_latest_message("Architect") or st.session_state.current_solution or latest.get("solution", "")
    visual_html = build_visual_blueprint_html(
        st.session_state.task_mode,
        st.session_state.current_task or st.session_state.task_draft,
        solution,
        janitor_report=janitor,
    )
    if not visual_html:
        return

    st.markdown("### Visual Blueprint")
    st.markdown(
        "A mode-aware schematic view of the current answer, rendered directly from the result without image generation.",
    )
    st.markdown(visual_html, unsafe_allow_html=True)


# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<h1 style='color:#ffffff;font-size:1.45rem;margin-bottom:0;'>The Arbiter</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color:#b6c4d6;font-size:0.78rem;margin-top:4px;'>Deliberation workspace</p>", unsafe_allow_html=True)

    st.markdown("### Cost Overview")
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

    st.divider()

    st.markdown("<p style='font-size:0.7rem;color:#b6c4d6;letter-spacing:2px;'>WORKFLOW</p>", unsafe_allow_html=True)
    st.session_state.task_mode = st.selectbox(
        "Task Mode",
        list(TASK_PROFILES.keys()),
        index=list(TASK_PROFILES.keys()).index(st.session_state.task_mode),
    )
    st.markdown("<p style='font-size:0.7rem;color:#b6c4d6;letter-spacing:2px;'>AI STRATEGY</p>", unsafe_allow_html=True)
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

    if st.session_state.manual_model_selection:
        provider_lock_option = st.selectbox(
            "Provider Lock",
            ["groq", "gemini", "openai", "anthropic", "mixed"],
            index=["groq", "gemini", "openai", "anthropic", "mixed"].index(st.session_state.provider_lock if st.session_state.provider_lock in {"groq", "gemini", "openai", "anthropic", "mixed"} else "groq"),
        )
        st.session_state.provider_lock = provider_lock_option
        st.session_state.stable_mode = st.toggle(
            "Stable Mode",
            value=st.session_state.stable_mode,
            help="Keeps the selected provider/model family fixed, disables exploration, and prevents hidden premium escalation.",
        )
    else:
        provider_lock_option = st.session_state.provider_lock

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
    if st.session_state.manual_model_selection:
        st.markdown("<p style='font-size:0.7rem;color:#b6c4d6;letter-spacing:2px;margin-top:12px;'>MODEL SELECTION</p>", unsafe_allow_html=True)
        for role in role_order:
            options = get_available_models_for_role(role)
            current_value = normalize_role_model(role, st.session_state.selected_models.get(role, options[0] if options else ""))
            if current_value not in options and options:
                current_value = options[0]
            chosen = st.selectbox(
                role_labels[role],
                options,
                index=options.index(current_value) if options and current_value in options else 0,
                key=f"role_model_{role}",
            )
            role_models[role] = chosen
    else:
        role_models = dict(st.session_state.selected_models)
    if st.session_state.manual_model_selection:
        st.session_state.selected_models = role_models

    # Push model choices into selector overrides
    from arbiter.infra.model_selector import get_model_selector
    sel = get_model_selector()
    sel.set_provider_lock("" if provider_lock_option == "mixed" else provider_lock_option)
    for role, model in role_models.items():
        normalized_model = normalize_role_model(role, model)
        sel.set_override(role, normalized_model)
        role_models[role] = normalized_model

    if any(provider_for_model(model, "") == "anthropic" for model in role_models.values()) and not os.getenv("ANTHROPIC_API_KEY"):
        st.warning("Claude/Anthropic models are selected, but `ANTHROPIC_API_KEY` is not set in your `.env` yet.")

    st.info("Start with a preset. Only open manual model control when you need role-level tuning.")

    st.divider()

    st.markdown("<p style='font-size:0.7rem;color:#b6c4d6;letter-spacing:2px;'>DANGER ZONE</p>", unsafe_allow_html=True)
    if st.button("🔴 EMERGENCY PURGE"):
        st.session_state.clear()
        st.rerun()

    st.markdown("""
    <div class="luca-branding">
        <div class="luca-name">Built by Luca Crăciun</div>
        <div class="luca-links-row">
            <a href="https://github.com/lucaomul" class="luca-link">GitHub</a>
            <a href="https://www.linkedin.com/in/gabriel-luca-craciun-25ba95295" class="luca-link">LinkedIn</a>
        </div>
        <div class="luca-meta">The Arbiter product build</div>
    </div>
    """, unsafe_allow_html=True)


# ── Main header ──────────────────────────────────────────────
render_product_header()
render_telemetry_panel()
render_case_flow_panel()
render_deliberation_scene()

if st.session_state.iteration_history:
    left_col, right_col = st.columns([1.12, 0.88])
    with left_col:
        render_architect_surface()
    with right_col:
        render_review_panel()
        render_intelligence_signals()
    render_visual_blueprint()
elif st.session_state.step in {"audit", "clarification"} or (
    st.session_state.step == "negotiation" and st.session_state.audit_status == "passed" and not st.session_state.iteration_history
):
    render_auditor_surface()

# ════════════════════════════════════════════════
# STEP 1: Input
# ════════════════════════════════════════════════
if st.session_state.step == "input":
    input_guide = current_task_input_guide()
    with st.form("arbiter_input_form", clear_on_submit=False):
        st.markdown(
            """
            <div class="arbiter-intake-header">
                <div class="arbiter-intake-eyebrow">Case Intake</div>
                <div class="arbiter-intake-title">Brief The Arbiter</div>
                <div class="arbiter-intake-subtitle">
                    Define the objective, constraints, and the output you want with enough specificity for a high-trust review.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.session_state.auto_mode_enabled = st.checkbox(
            "Autonomous mode",
            value=st.session_state.auto_mode_enabled,
            help="Let The Arbiter run multiple rounds toward a target score instead of a single pass.",
        )
        if st.session_state.auto_mode_enabled:
            run_cols = st.columns(2)
            with run_cols[0]:
                st.session_state.target_score_setting = st.slider(
                    "Minimum acceptable score",
                    6,
                    10,
                    int(st.session_state.target_score_setting),
                )
            with run_cols[1]:
                st.session_state.max_iterations_setting = st.number_input(
                    "Max iterations",
                    min_value=1,
                    max_value=8,
                    value=int(st.session_state.max_iterations_setting),
                )
        task_input_key = f"task_input_{st.session_state.task_input_seq}"
        u_input = st.text_area(
            "Task Brief",
            value=st.session_state.task_draft,
            placeholder=input_guide["placeholder"],
            height=150,
            key=task_input_key,
            label_visibility="collapsed",
        )
        action_cols = st.columns([1.55, 1.16, 0.2, 5.09], gap="small")
        with action_cols[0]:
            submitted = st.form_submit_button("Start Review", use_container_width=True)
        with action_cols[1]:
            uploaded_materials = st.file_uploader(
                "Attach a File",
                type=attachment_file_types(),
                accept_multiple_files=True,
                label_visibility="collapsed",
                help="Attach supporting evidence files.",
                width="stretch",
            )
        with action_cols[2]:
            st.markdown(
                """
                <div class="arbiter-help-inline arbiter-intake-help">
                    <span class="arbiter-help-icon" tabindex="0">?
                        <span class="arbiter-help-bubble">
                            Paste links directly into the main brief.
                            <br><br>
                            Supported files: PDF, DOCX, TXT, Markdown, JSON, CSV, HTML, SQL, XML, logs, and common code/text documents.
                        </span>
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.markdown(
        f"""
        <div class="arbiter-intake-note">
            <span class="arbiter-intake-note-label">Best input:</span>
            <span>{html.escape(input_guide["caption"])}</span>
            <span class="arbiter-intake-note-separator">•</span>
            <span>The Arbiter will either ask for missing context or confirm that the task is clear enough to proceed.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_pending_supporting_materials()
    if submitted and u_input:
        serialized_materials = [serialize_uploaded_material(item) for item in (uploaded_materials or [])]
        parsed_urls = parse_supporting_urls(u_input)
        reset_run_state(keep_task_mode=True)
        st.session_state.task_draft = ""
        st.session_state.task_input_seq += 1
        st.session_state.current_task = u_input
        st.session_state.supporting_materials = serialized_materials
        st.session_state.supporting_urls = parsed_urls
        st.session_state.supporting_urls_text = ""
        st.session_state.evidence_preview = {}
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
        result = run_orchestrator_safe(
            orchestrator,
            user_input=st.session_state.current_task,
            allow_complex_software_team=st.session_state.software_team_consent,
            software_team_profile=st.session_state.software_team_profile,
            supporting_materials=st.session_state.supporting_materials,
            supporting_urls=st.session_state.supporting_urls,
        )

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
        questions = sanitize_audit_questions(result.debug_info.get("questions", []), limit=3)
        history = list(st.session_state.audit_question_history or [])
        new_questions = [
            question for question in questions
            if not any(audit_questions_similar(question, existing) for existing in history)
        ]

        st.session_state.audit_round_count = int(st.session_state.audit_round_count or 0) + 1
        round_count = st.session_state.audit_round_count
        repeated_only = bool(questions) and not new_questions
        reached_cap = round_count >= MAX_AUDIT_CLARIFICATION_ROUNDS

        if repeated_only or reached_cap:
            st.session_state.pending_questions = []
            st.session_state.audit_status = "passed"
            st.session_state.audit_question_history = history + list(questions)
            st.session_state.audit_resolution_note = (
                "Auditor clarification limit reached. Proceeding with the current context to avoid an intake loop."
                if reached_cap
                else "Auditor began repeating the same clarification themes. Proceeding with the current context to avoid a loop."
            )
            if not maybe_require_software_team_consent(st.session_state.current_task):
                st.session_state.step = "negotiation"
                st.session_state.pending_auto_run = True
                st.session_state.run_in_progress = True
        else:
            st.session_state.pending_questions = new_questions or questions
            st.session_state.audit_question_history = history + list(st.session_state.pending_questions)
            st.session_state.audit_status = "needs_clarification"
            st.session_state.audit_resolution_note = ""
            st.session_state.step = "clarification"
        st.rerun()
    else:
        st.session_state.pending_questions = []
        st.session_state.audit_status = "passed"
        st.session_state.audit_round_count = 0
        st.session_state.audit_question_history = []
        st.session_state.audit_resolution_note = ""
        if not maybe_require_software_team_consent(st.session_state.current_task):
            st.session_state.step = "negotiation"
            st.session_state.pending_auto_run = True
            st.session_state.run_in_progress = True
        st.rerun()


# ════════════════════════════════════════════════
# STEP 3: Clarification
# ════════════════════════════════════════════════
elif st.session_state.step == "clarification":
    st.caption("Respond to the Auditor below so the case can proceed.")
    clarification_key = f"clarification_input_{st.session_state.clarification_input_seq}"
    with st.form("arbiter_clarification_form", clear_on_submit=False):
        ans = st.text_area("PROVIDE ADDITIONAL DATA:", height=120, key=clarification_key)
        clarify_submitted = st.form_submit_button("RE-SYNCHRONIZE")
    if clarify_submitted:
        if ans.strip():
            st.session_state.current_task += f"\nAdditional context:\n{ans.strip()}"
            merged_urls = list(st.session_state.supporting_urls or [])
            for url in parse_supporting_urls(ans):
                if url not in merged_urls:
                    merged_urls.append(url)
            st.session_state.supporting_urls = merged_urls[:8]
        st.session_state.clarification_input_seq += 1
        st.session_state.step = "audit"
        st.rerun()


# ════════════════════════════════════════════════
# STEP 4: Software Team Consent
# ════════════════════════════════════════════════
elif st.session_state.step == "team_consent":
    preview = dict(st.session_state.software_team_preview or {})
    roles = list(preview.get("suggested_roles", []) or [])
    domains = list(preview.get("detected_domains", []) or [])
    technologies = list(preview.get("detected_technologies", []) or [])
    signal_reasons = list(preview.get("signal_reasons", []) or [])
    complexity_score = int(preview.get("complexity_score", 0) or 0)
    complexity_level = str(preview.get("complexity_level", "complex") or "complex").replace("_", " ").title()
    profile_options = dict(preview.get("profile_options", {}) or {})
    profile_ids = list(profile_options.keys()) or ["efficient", "dream"]
    current_profile = str(st.session_state.software_team_profile or "").strip().lower()
    if current_profile not in profile_ids:
        current_profile = str(preview.get("recommended_profile", profile_ids[0]) or profile_ids[0])
        st.session_state.software_team_profile = current_profile
    selected_profile = st.radio(
        "Specialist team profile",
        options=profile_ids,
        index=profile_ids.index(current_profile),
        format_func=lambda value: str(profile_options.get(value, {}).get("label", value.replace("_", " ").title())),
        horizontal=True,
    )
    st.session_state.software_team_profile = selected_profile
    selected_profile_meta = dict(profile_options.get(selected_profile, {}) or {})
    estimated_cost_multiplier = float(
        selected_profile_meta.get("estimated_cost_multiplier", preview.get("estimated_cost_multiplier", 1.0)) or 1.0
    )
    estimated_latency_multiplier = float(
        selected_profile_meta.get("estimated_latency_multiplier", preview.get("estimated_latency_multiplier", 1.0)) or 1.0
    )
    selected_profile_label = str(selected_profile_meta.get("label", selected_profile.replace("_", " ").title()) or "")
    selected_profile_description = str(selected_profile_meta.get("description", "") or "").strip()
    selected_role_models = dict(selected_profile_meta.get("role_models", {}) or {})
    recommended_profile = str(preview.get("recommended_profile", "") or "").strip()

    st.warning(
        "This Software & IT task looks large enough to activate the Software Architect Team. "
        "That increases coordination quality, but it also increases time and cost."
    )
    render_summary_cards(
        [
            ("Complexity", complexity_level),
            ("Profile", selected_profile_label),
            ("Signal Score", f"{complexity_score}/4"),
            ("Domains", len(domains)),
            ("Roles", len(roles)),
            ("Cost Impact", f"{estimated_cost_multiplier:.2f}x"),
            ("Time Impact", f"{estimated_latency_multiplier:.2f}x"),
        ]
    )
    if recommended_profile:
        st.caption(
            f"Recommended profile: {str(profile_options.get(recommended_profile, {}).get('label', recommended_profile.replace('_', ' ').title()))}."
        )
    if selected_profile_description:
        st.info(selected_profile_description)
    reason = str(preview.get("reason", "") or "").strip()
    if reason:
        st.caption(reason)
    if domains:
        st.markdown("**Detected Domains**")
        st.caption(", ".join(domains))
    if technologies:
        st.markdown("**Detected Technologies / Frameworks**")
        st.caption(", ".join(technologies))
    if signal_reasons:
        st.markdown("**Why The Task Was Classified As Large**")
        for item in signal_reasons:
            st.markdown(f"- {item}")
    if roles:
        st.markdown("**Specialist Team That Will Be Activated**")
        for role in roles:
            st.markdown(f"- {role}")
    if selected_role_models:
        st.markdown("**Role To Model Routing**")
        for role, model in selected_role_models.items():
            st.markdown(f"- **{role}** → `{model}`")

    st.session_state.software_team_warning_ack = st.checkbox(
        f"I understand this task will use the {selected_profile_label} and may take longer and cost more than the standard architect path.",
        value=st.session_state.software_team_warning_ack,
    )

    consent_cols = st.columns(2)
    if consent_cols[0].button(f"Proceed With {selected_profile_label}", use_container_width=True):
        if not st.session_state.software_team_warning_ack:
            st.error("Please confirm that you accept the larger team, time, and cost impact before proceeding.")
        else:
            st.session_state.software_team_consent = True
            st.session_state.step = "negotiation"
            st.session_state.pending_auto_run = True
            st.session_state.run_in_progress = True
            st.rerun()
    if consent_cols[1].button("Go Back And Simplify Scope", use_container_width=True):
        st.session_state.task_draft = st.session_state.current_task or st.session_state.task_draft
        st.session_state.step = "input"
        st.session_state.pending_auto_run = False
        st.session_state.run_in_progress = False
        st.rerun()


# ════════════════════════════════════════════════
# STEP 5: Negotiation (main debate loop)
# ════════════════════════════════════════════════
elif st.session_state.step == "negotiation":
    round_number = max(int(st.session_state.iteration or 0) + 1, 1)
    st.markdown(
        (
            "<div class='status-strip'>"
            "<span class='status-strip-label'>Deliberation Round</span>"
            f"<span class='status-strip-value'>{round_number}</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    col_input, col_opt = st.columns([2, 1])
    with col_input:
        janitor_context = build_retry_context()
        if janitor_context:
            with st.expander("Janitor Retry Context", expanded=False):
                st.caption("This is the default rerun brief. Arbiter will use it automatically on the next run.")
                retry_html = html.escape(janitor_context)
                st.markdown(
                    f"<div class='retry-brief-block'><pre>{retry_html}</pre></div>",
                    unsafe_allow_html=True,
                )

        st.session_state.manual_feedback_enabled = st.checkbox(
            "Add Manual Feedback Checkpoint",
            value=st.session_state.manual_feedback_enabled,
            help="Turn this on only when you want to inject personal instructions or extra project context.",
        )
        if st.session_state.manual_feedback_enabled:
            manual_feedback_key = f"manual_feedback_input_{st.session_state.manual_feedback_input_seq}"
            st.session_state.manual_feedback_text = st.text_area(
                "Manual Feedback / Extra Project Context",
                placeholder="Add personal feedback, constraints, product context, or extra instructions here...",
                height=140,
                key=manual_feedback_key,
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

            project_note_key = f"project_note_input_{st.session_state.project_note_input_seq}"
            st.session_state.project_note_text = st.text_area(
                "Save a project note",
                placeholder="Example: For scheduling tasks, employee preferences come by email and non-responders are treated as flexible.",
                height=110,
                key=project_note_key,
            )
            if st.button("Save Project Note", key="save_project_note"):
                note_text = str(st.session_state.project_note_text or "").strip()
                if note_text and hasattr(memory_store, "add_project_note"):
                    memory_store.add_project_note(
                        text=note_text,
                        task_mode=st.session_state.task_mode,
                    )
                    st.session_state.project_note_text = ""
                    st.session_state.project_note_input_seq += 1
                    st.session_state.memory_stats = memory_store.stats()
                    st.success("Project note saved to persistent memory.")
                    st.rerun()
                elif note_text:
                    st.warning("Project notes need one full app restart before saving is available.")

        st.markdown("<div class='arbiter-run-actions'>", unsafe_allow_html=True)
        action_cols = st.columns(2)
        with action_cols[0]:
            if st.button("EXECUTE COGNITIVE DEBATE", use_container_width=True):
                st.session_state.pending_auto_run = True
                st.session_state.run_in_progress = True
                st.rerun()
        with action_cols[1]:
            generate_disabled = st.session_state.iteration <= 0
            if st.button(
                "GENERATE FINAL REPORT",
                use_container_width=True,
                disabled=generate_disabled,
            ):
                st.session_state.step = "export"
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    with col_opt:
        with st.container(border=True):
            st.markdown("**Run Profile**")
            st.caption("Autonomous settings are chosen before the Auditor intake.")
            render_summary_cards(
                [
                    ("Mode", "Autonomous" if st.session_state.auto_mode_enabled else "Single Pass"),
                    ("Minimum Score", str(st.session_state.target_score_setting if st.session_state.auto_mode_enabled else 8)),
                    ("Max Iterations", str(st.session_state.max_iterations_setting if st.session_state.auto_mode_enabled else 1)),
                    ("Provider", st.session_state.provider_lock.upper()),
                ]
            )
        team_preview = dict(st.session_state.software_team_preview or {})
        if team_preview.get("use_team"):
            with st.container(border=True):
                st.markdown("**Large Task Notice**")
                selected_preview_profile = str(st.session_state.software_team_profile or team_preview.get("recommended_profile", "") or "").strip()
                preview_profile_meta = dict((team_preview.get("profile_options", {}) or {}).get(selected_preview_profile, {}) or {})
                render_summary_cards(
                    [
                        ("Team Mode", "Approved" if st.session_state.software_team_consent else "Pending"),
                        ("Profile", selected_preview_profile.replace("_", " ").title() or "Pending"),
                        ("Complexity", str(team_preview.get("complexity_level", "complex")).replace("_", " ").title()),
                        ("Roles", len(team_preview.get("suggested_roles", []) or [])),
                        ("Cost", f"{float(preview_profile_meta.get('estimated_cost_multiplier', team_preview.get('estimated_cost_multiplier', 1.0)) or 1.0):.2f}x"),
                    ]
                )
                st.caption(str(team_preview.get("reason", "") or ""))
        st.session_state.benchmark_mode = False

    effective_auto_mode = bool(st.session_state.auto_mode_enabled)
    effective_target_score = float(st.session_state.target_score_setting if st.session_state.auto_mode_enabled else 8.0)
    effective_max_iterations = int(st.session_state.max_iterations_setting if st.session_state.auto_mode_enabled else 1)
    if st.session_state.benchmark_mode and st.session_state.benchmark_strategy == "baseline_single_pass":
        effective_auto_mode = False
        effective_target_score = 8.0
        effective_max_iterations = 1

    if st.session_state.pending_auto_run:
        st.session_state.pending_auto_run = False
        get_cache().clear()
        manual_override = build_effective_manual_override()
        execute_deliberation_run(
            auto_mode=effective_auto_mode,
            target_score=effective_target_score,
            max_iterations=effective_max_iterations,
            manual_override=manual_override,
        )
        st.rerun()


# ════════════════════════════════════════════════
# STEP 6: Export
# ════════════════════════════════════════════════
elif st.session_state.step == "export":
    st.balloons()
    st.markdown("""
    <div class='agent-card' style='text-align:center;'>
        <h2 style='color:#111111;'>MISSION COMPLETE</h2>
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

    report_text = st.session_state.best_solution or st.session_state.current_solution
    export_metadata = {
        "Run ID": st.session_state.run_id or "untracked",
        "Task Mode": st.session_state.task_mode,
        "Iterations": st.session_state.iteration,
        "Total Cost USD": st.session_state.costs.get("Total", 0.0),
        "Evidence Sources": len(st.session_state.supporting_materials or []),
    }
    if st.session_state.best_iteration:
        export_metadata.update(
            {
                "Best Iteration": st.session_state.best_iteration.get("iter", ""),
                "Technical Score": st.session_state.best_iteration.get("tech", ""),
                "Logic Score": st.session_state.best_iteration.get("logic", ""),
                "Average Score": st.session_state.best_iteration.get("avg", ""),
            }
        )

    csv_output = export_solution_csv(report_text, metadata=export_metadata)
    xlsx_output = export_solution_xlsx(report_text, metadata=export_metadata)

    col_pdf, col_csv, col_xlsx = st.columns(3)

    if FPDF is None:
        col_pdf.info("PDF export is unavailable because `fpdf2` is not installed.")
    else:
        import re as _re

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        clean_text = _re.sub(r"<[^>]*>", "", report_text)
        pdf.multi_cell(0, 10, text=clean_text.encode("latin-1", "replace").decode("latin-1"))
        pdf_output = pdf.output()
        if isinstance(pdf_output, str):
            pdf_output = pdf_output.encode("latin-1")
        else:
            pdf_output = bytes(pdf_output)

        col_pdf.download_button(
            label="DOWNLOAD REPORT (PDF)",
            data=pdf_output,
            file_name="The_Arbiter_Report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    col_csv.download_button(
        label="DOWNLOAD REPORT (CSV)",
        data=csv_output,
        file_name="The_Arbiter_Report.csv",
        mime="text/csv",
        use_container_width=True,
    )
    col_xlsx.download_button(
        label="DOWNLOAD REPORT (XLSX)",
        data=xlsx_output,
        file_name="The_Arbiter_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.caption(
        "Spreadsheet exports preserve markdown tables when present and fall back to a clean section-by-section workbook when the answer is prose."
    )

    if st.button("RESTART SYSTEM"):
        st.session_state.clear()
        st.rerun()
