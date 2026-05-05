import streamlit as st
import html
import sys
import json
from pathlib import Path
from urllib import error, request
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from arbiter.app.ui_styles import UI_CSS
from arbiter.core.orchestrator import ArbiterOrchestrator
from arbiter.config.settings import TASK_PROFILES
from arbiter.infra.model_selector import get_model_selector

load_dotenv(PROJECT_ROOT / ".env")

st.set_page_config(
    page_title="Arbiter Test Bench",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(UI_CSS, unsafe_allow_html=True)

OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def render_items(items, empty_text="None"):
    if items:
        for item in items:
            st.markdown(f"- {item}")
    else:
        st.caption(empty_text)


def fetch_ollama_health():
    info = {
        "reachable": False,
        "version": "",
        "models": [],
        "error": "",
    }
    try:
        req = request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
        info["reachable"] = True
        info["models"] = [model.get("name", "") for model in data.get("models", []) if model.get("name")]
    except Exception as exc:
        info["error"] = str(exc)

    if info["reachable"]:
        try:
            req = request.Request(f"{OLLAMA_BASE_URL}/api/version", method="GET")
            with request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode("utf-8"))
            info["version"] = data.get("version", "")
        except Exception:
            pass
    return info


def render_result(result):
    if result.debug_info.get("needs_clarification"):
        st.warning("Auditor requested clarification before build.")
        render_items(result.debug_info.get("questions", []), empty_text="No clarification questions.")
        return

    latest = result.iteration_history[-1] if result.iteration_history else {}
    janitor = result.debug_info.get("latest_janitor_report", {}) or {}

    cols = st.columns(5)
    cols[0].metric("Status", latest.get("validity_status", "IDLE"))
    cols[1].metric("Tech", f"{latest.get('tech', 0)}/10")
    cols[2].metric("Logic", f"{latest.get('logic', 0)}/10")
    cols[3].metric("Average", f"{latest.get('avg', 0.0):.1f}/10")
    cols[4].metric("Run Cost", f"${result.costs.get('Total', 0.0):.4f}")
    st.caption(result.debug_info.get("stop_reason", "No stop reason."))

    st.subheader("Janitor Summary")
    st.write(janitor.get("summary", "") or "None")

    janitor_cols = st.columns(3)
    with janitor_cols[0]:
        st.markdown("**Pending**")
        render_items(janitor.get("pending", []))
    with janitor_cols[1]:
        st.markdown("**Preserve**")
        render_items(janitor.get("preserve", []))
    with janitor_cols[2]:
        st.markdown("**Repair Brief**")
        render_items(janitor.get("repair_brief", []))

    st.subheader("Architect Output")
    solution = result.best_solution or result.debug_info.get("current_solution", "")
    if solution:
        if "```" in solution:
            st.markdown(solution)
        else:
            st.text_area("Latest Solution", value=solution, height=320)
    else:
        st.caption("No solution returned.")

    with st.expander("Iteration History"):
        st.json(result.iteration_history)

    with st.expander("Debug Info"):
        st.json(result.debug_info)


with st.sidebar:
    st.markdown("<h1 style='color:#00ffa3;font-size:1.5rem;'>🧪 TEST BENCH</h1>", unsafe_allow_html=True)
    st.caption("Use this sandbox to test prompts, models, and review behavior without changing the production UI flow.")
    task_mode = st.selectbox("Task Mode", list(TASK_PROFILES.keys()), index=0)
    use_ollama_test_mode = st.checkbox("Ollama Test Mode", value=False)
    if use_ollama_test_mode:
        st.caption("Prefix-free local model names will be wrapped as `ollama:<model>` automatically.")
        health = fetch_ollama_health()
        if health["reachable"]:
            st.success(f"Ollama reachable at {OLLAMA_BASE_URL}")
            if health["version"]:
                st.caption(f"Version: {health['version']}")
            if health["models"]:
                with st.expander("Local Ollama Models", expanded=False):
                    for model_name in health["models"]:
                        st.markdown(f"- `{model_name}`")
            else:
                st.warning("Ollama is running, but no local models were found yet.")
        else:
            st.error("Ollama is not reachable locally.")
            st.caption("Start the local server before using Ollama Test Mode.")
            if health["error"]:
                st.caption(f"Health check error: {health['error']}")
        with st.expander("Recommended Local Setup", expanded=False):
            st.markdown("- `Architect`: `qwen2.5-coder:7b`")
            st.markdown("- `Auditor`: `llama3.1:8b`")
            st.markdown("- `Tech Critic`: `qwen2.5-coder:7b`")
            st.markdown("- `Logic Critic`: `llama3.1:8b`")
            st.markdown("- `Janitor`: `llama3.1:8b`")
        architect_model_name = st.text_input("Ollama Architect", value="qwen2.5-coder:7b")
        auditor_model_name = st.text_input("Ollama Auditor", value="llama3.1:8b")
        tech_model_name = st.text_input("Ollama Tech Critic", value="qwen2.5-coder:7b")
        logic_model_name = st.text_input("Ollama Logic Critic", value="llama3.1:8b")
        janitor_model_name = st.text_input("Ollama Janitor", value="llama3.1:8b")
        architect_model = f"ollama:{architect_model_name.strip()}" if architect_model_name.strip() else "ollama:qwen2.5-coder:7b"
        auditor_model = f"ollama:{auditor_model_name.strip()}" if auditor_model_name.strip() else "ollama:llama3.1:8b"
        tech_model = f"ollama:{tech_model_name.strip()}" if tech_model_name.strip() else "ollama:qwen2.5-coder:7b"
        logic_model = f"ollama:{logic_model_name.strip()}" if logic_model_name.strip() else "ollama:llama3.1:8b"
        janitor_model = f"ollama:{janitor_model_name.strip()}" if janitor_model_name.strip() else "ollama:llama3.1:8b"
    else:
        architect_model = st.selectbox("Architect", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gpt-4o", "gpt-4o-mini"])
        auditor_model = st.selectbox("Auditor", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemini-2.5-flash", "gemini-2.5-pro"])
        tech_model = st.selectbox("Tech Critic", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemini-2.5-flash", "gemini-2.5-pro"])
        logic_model = st.selectbox("Logic Critic", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemini-2.5-flash"])
        janitor_model = "llama-3.1-8b-instant"
    auto_mode = st.checkbox("Autonomous Mode", value=False)
    target_score = st.slider("Target Score", 6, 10, 8) if auto_mode else 8
    max_iterations = st.number_input("Max Iterations", 1, 8, 3) if auto_mode else 1

    selector = get_model_selector()
    selector.set_override("Architect", architect_model)
    selector.set_override("Auditor", auditor_model)
    selector.set_override("Tech Critic", tech_model)
    selector.set_override("Logic Critic", logic_model)
    selector.set_override("Janitor", janitor_model)
    selector.set_override("Repair", janitor_model if use_ollama_test_mode else "llama-3.1-8b-instant")

st.markdown(
    "<h1 style='text-align:center;letter-spacing:10px;'>ARBITER <span style='color:#00ffa3;'>TEST BENCH</span></h1>",
    unsafe_allow_html=True,
)

task = st.text_area("Task", placeholder="Paste a prompt to stress-test the loop...", height=180)
extra_context = st.text_area("Additional Context (Optional)", height=90)
manual_override = st.text_input("Manual Override (Optional)")

if st.button("Run Sandbox"):
    with st.spinner("Running sandbox pipeline..."):
        orchestrator = ArbiterOrchestrator(
            task_mode=task_mode,
            auto_mode=auto_mode,
            target_score=float(target_score),
            max_iterations=int(max_iterations),
        )
        result = orchestrator.run(
            user_input=task,
            clarification=extra_context.strip(),
            manual_override=manual_override.strip(),
        )
    render_result(result)
