import streamlit as st
import os
import json
import re
from agents import AIAgent
from prompts import AUDITOR_PROMPT, PROPOSER_PROMPT, CRITIC_PROMPT
from fpdf import FPDF
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Arbiter SaaS Pro", layout="wide")

# --- INITIALIZARE SESSION STATE ---
if "messages" not in st.session_state: st.session_state.messages = []
if "total_cost" not in st.session_state: st.session_state.total_cost = 0.0
if "current_solution" not in st.session_state: st.session_state.current_solution = ""
if "current_task" not in st.session_state: st.session_state.current_task = ""
if "step" not in st.session_state: st.session_state.step = "input"
# Culori implicite
if "bg_color" not in st.session_state: st.session_state.bg_color = "#0E1117"
if "text_color" not in st.session_state: st.session_state.text_color = "#FFFFFF"
if "accent_color" not in st.session_state: st.session_state.accent_color = "#00FFAA"

# --- COST TRACKER ---
def log_cost(model):
    costs = {"gpt-4o": 0.01, "gpt-4o-mini": 0.0005, "gemini-2.5-pro": 0.003, "llama-3.3-70b-versatile": 0.0007}
    st.session_state.total_cost += costs.get(model, 0.001)

# --- CUSTOM CSS (DYNAMIC THEMING) ---
st.markdown(f"""
    <style>
    .stApp {{
        background-color: {st.session_state.bg_color};
        color: {st.session_state.text_color};
    }}
    .chat-card {{
        background: rgba(255,255,255,0.05);
        padding: 20px;
        border-radius: 15px;
        border-left: 5px solid {st.session_state.accent_color};
        margin-bottom: 20px;
        color: {st.session_state.text_color};
    }}
    .stButton>button {{
        border: 2px solid {st.session_state.accent_color};
        background: transparent;
        color: {st.session_state.text_color};
        border-radius: 20px;
        transition: 0.3s;
    }}
    .stButton>button:hover {{
        background: {st.session_state.accent_color};
        color: black;
        box-shadow: 0 0 15px {st.session_state.accent_color};
    }}
    /* Stil pentru textul din input-uri sa fie vizibil pe fundal custom */
    .stTextArea textarea, .stTextInput input {{
        color: {st.session_state.text_color} !important;
    }}
    </style>
""", unsafe_allow_html=True)

# --- SIDEBAR: DESIGN & ADMIN ---
with st.sidebar:
    st.title("🛡️ Admin Panel")
    
    with st.expander("🎨 UI Customizer", expanded=True):
        st.session_state.bg_color = st.color_picker("Background", st.session_state.bg_color)
        st.session_state.text_color = st.color_picker("Text Color", st.session_state.text_color)
        st.session_state.accent_color = st.color_picker("Accent (Neon)", st.session_state.accent_color)
    
    st.divider()
    st.metric("Session Spend", f"${st.session_state.total_cost:.4f}")
    
    if st.button("🗑️ Reset All Sessions"):
        for key in st.session_state.keys():
            if key not in ["bg_color", "text_color", "accent_color"]: # Pastram culorile la reset
                del st.session_state[key]
        st.rerun()
        
    st.divider()
    p_mod = st.selectbox("Architect", ["gpt-4o", "gpt-4o-mini"])
    c_mod_1 = st.selectbox("Tech Critic", ["gemini-2.5-pro", "gemini-2.5-flash"])
    c_mod_2 = st.selectbox("Logic Critic", ["llama-3.3-70b-versatile"])

# --- MAIN APP FLOW ---
st.title("⚔️ The Arbiter SaaS")

# Afișăm istoricul de chat
for msg in st.session_state.messages:
    st.markdown(f"<div class='chat-card'><b>{msg['role']}:</b><br>{msg['content']}</div>", unsafe_allow_html=True)

# STEP 1: INPUT
if st.session_state.step == "input":
    u_input = st.text_area("What is the challenge?", placeholder="Enter task here...")
    if st.button("🚀 Start Audit"):
        auditor = AIAgent("Auditor", "gemini", c_mod_1, AUDITOR_PROMPT)
        with st.spinner("Analyzing requirements..."):
            res = AIAgent.clean_json(auditor.ask(u_input))
            log_cost(c_mod_1)
            if not res.get("clear", True):
                st.session_state.messages.append({"role": "Auditor", "content": f"Clarification needed: {', '.join(res.get('questions', []))}"})
                st.session_state.current_task = u_input
                st.session_state.step = "audit_fix"
                st.rerun()
            else:
                st.session_state.current_task = u_input
                st.session_state.step = "negotiation"
                st.rerun()

# STEP 2: AUDIT CLARIFICATION
elif st.session_state.step == "audit_fix":
    clarify = st.text_input("Answer the Auditor's questions:")
    if st.button("Update Task"):
        st.session_state.current_task += f" | Clarification: {clarify}"
        st.session_state.step = "negotiation"
        st.rerun()

# STEP 3: NEGOTIATION LOOP
elif st.session_state.step == "negotiation":
    col_run, col_pdf = st.columns([1, 1])
    
    with col_run:
        if st.button("🔄 Run/Continue Negotiation"):
            proposer = AIAgent("Architect", "openai", p_mod, PROPOSER_PROMPT)
            tech_critic = AIAgent("Tech Critic", "gemini", c_mod_1, CRITIC_PROMPT)
            logic_critic = AIAgent("Logic Critic", "groq", c_mod_2, CRITIC_PROMPT)
            
            # Memory string
            history_str = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages])

            with st.spinner("Architect is thinking..."):
                p_raw = proposer.ask(st.session_state.current_task, history=history_str)
                proposal = AIAgent.clean_json(p_raw).get("proposal", "")
                log_cost(p_mod)
                st.session_state.messages.append({"role": "Architect", "content": proposal})
                st.session_state.current_solution = proposal

            with st.spinner("Critics are debating..."):
                t_res = AIAgent.clean_json(tech_critic.ask(f"Task: {st.session_state.current_task}\nProposal: {proposal}"))
                l_res = AIAgent.clean_json(logic_critic.ask(f"Task: {st.session_state.current_task}\nProposal: {proposal}"))
                log_cost(c_mod_1)
                log_cost(c_mod_2)
                
                critique_summary = f"**Scores:** Tech {t_res.get('score')}/10, Logic {l_res.get('score')}/10\n\n**Feedback:** {t_res.get('critique')} | {l_res.get('critique')}"
                st.session_state.messages.append({"role": "Critics", "content": critique_summary})
            
            st.rerun()

    # STEP 4: EXPORT PDF
    if st.session_state.current_solution:
        with col_pdf:
            safe_fn = re.sub(r'[^a-zA-Z0-9]', '_', st.session_state.current_task[:20])
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "Arbiter Project Report", ln=True, align='C')
            pdf.ln(10)
            pdf.set_font("Arial", size=10)
            clean_content = st.session_state.current_solution.encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 10, txt=clean_content)
            
            st.download_button("📥 Download Final PDF", data=pdf.output(dest="S").encode("latin-1"), file_name=f"Arbiter_{safe_fn}.pdf")