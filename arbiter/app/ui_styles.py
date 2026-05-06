UI_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
    --bg: #f5f5f4;
    --surface: #ffffff;
    --surface-soft: #f7f7f5;
    --border: #ddddda;
    --text: #171717;
    --text-soft: #666666;
    --title: #0a0a0a;
    --primary: #111111;
    --success: #111111;
    --warning: #333333;
    --danger: #000000;
    --shadow: 0 12px 30px rgba(0, 0, 0, 0.05);
}

.stApp {
    background: linear-gradient(180deg, var(--bg) 0%, #efefec 100%);
    color: var(--text);
    font-family: 'Inter', sans-serif;
}

p,
li,
label,
div,
span {
    color: inherit;
}

[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {
    color: var(--text) !important;
    line-height: 1.65;
}

[data-testid="stCaptionContainer"] {
    color: #4f4f4a !important;
    font-size: 0.84rem !important;
    line-height: 1.55 !important;
}

@keyframes fade-rise {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes subtle-pulse {
    0%, 100% {
        box-shadow: 0 0 0 0 rgba(17, 17, 17, 0.08);
    }
    50% {
        box-shadow: 0 0 0 8px rgba(17, 17, 17, 0.03);
    }
}

@keyframes draft-scan {
    0% {
        transform: translateX(-110%);
    }
    100% {
        transform: translateX(110%);
    }
}

@keyframes debate-left {
    0% {
        transform: translateX(-14px);
        opacity: 0.6;
    }
    50% {
        transform: translateX(6px);
        opacity: 1;
    }
    100% {
        transform: translateX(-14px);
        opacity: 0.6;
    }
}

@keyframes debate-right {
    0% {
        transform: translateX(14px);
        opacity: 0.6;
    }
    50% {
        transform: translateX(-6px);
        opacity: 1;
    }
    100% {
        transform: translateX(14px);
        opacity: 0.6;
    }
}

@keyframes janitor-sweep {
    0% {
        transform: translateX(-120%);
        opacity: 0;
    }
    20% {
        opacity: 0.95;
    }
    100% {
        transform: translateX(135%);
        opacity: 0;
    }
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #111111 0%, #181818 100%) !important;
    border-right: 1px solid rgba(255,255,255,0.06);
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] li,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stCheckbox,
[data-testid="stSidebar"] .stRadio {
    color: #edf2f7 !important;
}

.stTextArea textarea,
.stTextInput input,
.stNumberInput input,
.stSelectbox [data-baseweb="select"] > div {
    background: var(--surface) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 14px !important;
    caret-color: var(--text) !important;
}

.stTextArea textarea::placeholder,
.stTextInput input::placeholder,
.stNumberInput input::placeholder {
    color: #8a8a84 !important;
    opacity: 1 !important;
}

.stTextArea textarea:focus,
.stTextInput input:focus,
.stNumberInput input:focus {
    border-color: #111111 !important;
    box-shadow: 0 0 0 1px #111111 !important;
    outline: none !important;
}

[data-testid="stSidebar"] .stTextArea textarea,
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stNumberInput input,
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div {
    background: rgba(255,255,255,0.08) !important;
    color: #edf2f7 !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    caret-color: #ffffff !important;
}

[data-testid="stSidebar"] .stTextArea textarea::placeholder,
[data-testid="stSidebar"] .stTextInput input::placeholder,
[data-testid="stSidebar"] .stNumberInput input::placeholder {
    color: rgba(237, 242, 247, 0.64) !important;
    opacity: 1 !important;
}

[data-testid="stSidebar"] .stTextArea textarea:focus,
[data-testid="stSidebar"] .stTextInput input:focus,
[data-testid="stSidebar"] .stNumberInput input:focus {
    border-color: rgba(255,255,255,0.9) !important;
    box-shadow: 0 0 0 1px rgba(255,255,255,0.85) !important;
    outline: none !important;
}

.stButton > button {
    border-radius: 14px !important;
    border: 1px solid #111111 !important;
    background: linear-gradient(180deg, #111111, #1f1f1f) !important;
    color: #ffffff !important;
    font-weight: 700 !important;
    box-shadow: 0 8px 20px rgba(0,0,0,0.12);
    transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.stButton > button *,
.stButton > button p,
.stButton > button span,
.stButton > button div {
    color: #ffffff !important;
    fill: #ffffff !important;
}

.stButton > button:hover {
    border-color: #111111 !important;
    background: linear-gradient(180deg, #2a2a2a, #111111) !important;
    color: #ffffff !important;
    transform: translateY(-1px);
    box-shadow: 0 12px 24px rgba(0,0,0,0.16);
}

[data-testid="stFormSubmitButton"] > button {
    border-radius: 14px !important;
    border: 1px solid #111111 !important;
    background: #111111 !important;
    color: #ffffff !important;
    font-weight: 700 !important;
}

[data-testid="stFormSubmitButton"] > button *,
[data-testid="stFormSubmitButton"] > button p,
[data-testid="stFormSubmitButton"] > button span,
[data-testid="stFormSubmitButton"] > button div {
    color: #ffffff !important;
    fill: #ffffff !important;
}

[data-testid="stFormSubmitButton"] > button:hover {
    background: #2a2a2a !important;
    color: #ffffff !important;
}

[data-testid="stMetric"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 18px !important;
    box-shadow: var(--shadow);
    padding: 14px 16px !important;
    animation: fade-rise 0.32s ease both;
    overflow: visible !important;
    min-height: 112px !important;
}

[data-testid="stMetricLabel"] {
    color: var(--text-soft) !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.68rem !important;
    white-space: normal !important;
    word-break: normal !important;
    overflow-wrap: break-word !important;
    hyphens: none !important;
    line-height: 1.35 !important;
    overflow: visible !important;
    text-overflow: clip !important;
}

[data-testid="stMetricValue"] {
    color: var(--title) !important;
    font-weight: 800 !important;
    white-space: normal !important;
    word-break: normal !important;
    overflow-wrap: break-word !important;
    hyphens: none !important;
    line-height: 1.15 !important;
    font-size: 1.35rem !important;
    overflow: visible !important;
    text-overflow: clip !important;
}

[data-testid="stMetricLabel"] > div,
[data-testid="stMetricValue"] > div {
    white-space: normal !important;
    word-break: normal !important;
    overflow-wrap: break-word !important;
    hyphens: none !important;
    overflow: visible !important;
    text-overflow: clip !important;
}

[data-testid="stExpander"] details {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 16px !important;
    box-shadow: var(--shadow);
}

[data-testid="stExpander"] summary {
    background: #ffffff !important;
    color: var(--text) !important;
    border-radius: 16px !important;
}

[data-testid="stExpander"] summary * {
    color: var(--text) !important;
    fill: var(--text) !important;
}

[data-testid="stExpander"] details[open] > summary {
    background: #111111 !important;
    color: #ffffff !important;
    border-bottom-left-radius: 0 !important;
    border-bottom-right-radius: 0 !important;
}

[data-testid="stExpander"] details[open] > summary * {
    color: #ffffff !important;
    fill: #ffffff !important;
}

.agent-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 18px 20px;
    margin-bottom: 16px;
    box-shadow: var(--shadow);
    animation: fade-rise 0.34s ease both;
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.agent-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 16px 30px rgba(0,0,0,0.08);
}

.architect-section-label {
    margin: 14px 0 8px;
    color: var(--text-soft);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.72rem;
    font-weight: 700;
}

.architect-notes {
    margin-top: 10px;
    padding: 14px 16px;
    border-radius: 14px;
    background: var(--surface-soft);
    border: 1px solid var(--border);
    color: var(--text);
    line-height: 1.7;
}

.retry-brief-block {
    background: #fafaf8;
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 14px 16px;
    color: var(--text);
    box-shadow: var(--shadow);
}

.retry-brief-block pre {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--text);
    font-size: 0.9rem;
    line-height: 1.65;
    font-family: 'IBM Plex Mono', monospace;
}

[data-testid="stCodeBlock"] pre,
[data-testid="stCodeBlock"] code {
    white-space: pre-wrap !important;
    word-break: break-word !important;
}

.status-strip {
    display: inline-flex;
    align-items: center;
    gap: 12px;
    margin: 2px 0 18px;
    padding: 10px 14px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.88);
    border: 1px solid var(--border);
    box-shadow: 0 8px 18px rgba(0, 0, 0, 0.05);
    animation: fade-rise 0.24s ease both;
}

.status-strip-label {
    color: var(--text-soft);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.7rem;
    font-weight: 700;
}

.status-strip-value {
    color: var(--title);
    font-size: 0.92rem;
    font-weight: 800;
}

.summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
    gap: 12px;
    margin: 8px 0 14px;
}

.summary-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: var(--shadow);
    padding: 14px 16px;
    min-height: 96px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

.summary-card-label {
    color: var(--text-soft);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.68rem;
    line-height: 1.35;
    margin-bottom: 8px;
    word-break: normal;
    overflow-wrap: normal;
    hyphens: none;
}

.summary-card-value {
    color: var(--title);
    font-weight: 800;
    font-size: clamp(1rem, 1.3vw, 1.25rem);
    line-height: 1.15;
    word-break: normal;
    overflow-wrap: break-word;
    hyphens: none;
}

.court-flow {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 10px;
    margin-bottom: 20px;
}

.court-step {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 14px;
    box-shadow: var(--shadow);
    animation: fade-rise 0.28s ease both;
}

.court-flow-label {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-soft);
    margin-bottom: 6px;
    line-height: 1.35;
    white-space: normal;
}

.court-chip {
    display: inline-flex;
    align-items: center;
    padding: 6px 10px;
    border-radius: 999px;
    background: #f0f0ee;
    color: var(--text-soft);
    border: 1px solid #d7d7d4;
    font-size: 0.75rem;
    font-weight: 700;
}

.court-chip.done {
    background: #ececeb;
    color: #111111;
    border-color: #ccccca;
}

.court-chip.active {
    background: #111111;
    color: #ffffff;
    border-color: #111111;
    animation: subtle-pulse 1.9s ease-in-out infinite;
}

.court-chip.warn {
    background: #d4d4d1;
    color: #111111;
    border-color: #bdbdb9;
}

.deliberation-scene {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
    margin: 0 0 24px;
}

.scene-card {
    position: relative;
    overflow: hidden;
    background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(249,249,247,0.98));
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 18px 18px 16px;
    box-shadow: var(--shadow);
    animation: fade-rise 0.36s ease both;
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.scene-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 16px 28px rgba(0,0,0,0.08);
}

.scene-card::before {
    content: "";
    position: absolute;
    inset: 0 auto auto 0;
    width: 100%;
    height: 2px;
    background: #111111;
    opacity: 0.08;
}

.scene-card.scene-active {
    border-color: #111111;
    box-shadow: 0 16px 32px rgba(0,0,0,0.09);
}

.scene-card.scene-done {
    border-color: #c7c7c2;
}

.scene-card.scene-warn {
    border-color: #8a8a84;
    background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(242,242,239,0.98));
}

.scene-topline {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
}

.scene-eyebrow {
    color: var(--text-soft);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.7rem;
    font-weight: 700;
}

.scene-badge {
    display: inline-flex;
    align-items: center;
    min-height: 28px;
    padding: 5px 10px;
    border-radius: 999px;
    background: #efefec;
    border: 1px solid #d6d6d1;
    color: #444444;
    font-size: 0.74rem;
    font-weight: 700;
    white-space: nowrap;
}

.scene-active .scene-badge {
    background: #111111;
    border-color: #111111;
    color: #ffffff;
}

.scene-warn .scene-badge {
    background: #d9d9d4;
    border-color: #bdbdb7;
    color: #111111;
}

.scene-title {
    color: var(--title);
    font-size: 1rem;
    font-weight: 700;
    margin-bottom: 14px;
}

.scene-motif {
    position: relative;
    min-height: 88px;
    border-radius: 16px;
    background: linear-gradient(180deg, #f7f7f5, #f1f1ee);
    border: 1px solid #e1e1dc;
    overflow: hidden;
    margin-bottom: 12px;
}

.scene-note {
    color: var(--text-soft);
    font-size: 0.9rem;
    line-height: 1.6;
}

.draft-motif {
    padding: 18px 16px;
}

.draft-motif span {
    display: block;
    height: 9px;
    margin-bottom: 10px;
    border-radius: 999px;
    background: linear-gradient(90deg, #d8d8d2 0%, #cfcfc9 100%);
    position: relative;
    overflow: hidden;
}

.draft-motif span:nth-child(1) { width: 88%; }
.draft-motif span:nth-child(2) { width: 74%; }
.draft-motif span:nth-child(3) { width: 93%; }
.draft-motif span:nth-child(4) { width: 61%; margin-bottom: 0; }

.scene-active .draft-motif span::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, transparent 0%, rgba(17,17,17,0.16) 50%, transparent 100%);
    animation: draft-scan 1.8s linear infinite;
}

.debate-motif {
    display: grid;
    grid-template-rows: 1fr 1fr;
    gap: 10px;
    padding: 16px;
}

.debate-lane {
    display: flex;
    gap: 8px;
    align-items: center;
}

.debate-lane span {
    flex: 1 1 auto;
    height: 12px;
    border-radius: 999px;
    background: linear-gradient(90deg, #d4d4ce 0%, #c3c3bc 100%);
}

.debate-lane.left span:nth-child(1) { flex: 0.9; }
.debate-lane.left span:nth-child(2) { flex: 1.15; }
.debate-lane.left span:nth-child(3) { flex: 0.7; }
.debate-lane.right span:nth-child(1) { flex: 0.7; }
.debate-lane.right span:nth-child(2) { flex: 1.2; }
.debate-lane.right span:nth-child(3) { flex: 0.95; }

.scene-active .debate-lane.left {
    animation: debate-left 1.4s ease-in-out infinite;
}

.scene-active .debate-lane.right {
    animation: debate-right 1.4s ease-in-out infinite;
}

.cleanup-motif {
    display: flex;
    align-items: center;
    padding: 16px;
}

.cleanup-stack {
    width: 100%;
}

.cleanup-stack span {
    display: block;
    width: 100%;
    height: 10px;
    margin-bottom: 11px;
    border-radius: 999px;
    background: linear-gradient(90deg, #d7d7d1 0%, #c9c9c3 100%);
}

.cleanup-stack span:nth-child(2) { width: 82%; }
.cleanup-stack span:nth-child(3) { width: 68%; margin-bottom: 0; }

.cleanup-sweep {
    position: absolute;
    top: 14px;
    bottom: 14px;
    width: 34%;
    border-radius: 18px;
    background: linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(17,17,17,0.08) 48%, rgba(255,255,255,0) 100%);
    opacity: 0;
}

.scene-active .cleanup-sweep {
    animation: janitor-sweep 1.9s ease-in-out infinite;
}

.scene-done .cleanup-stack span {
    background: linear-gradient(90deg, #bdbdb7 0%, #a8a8a2 100%);
}

.cost-label {
    font-size: 0.68rem;
    color: #b8c6d8;
    margin-bottom: 4px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    white-space: nowrap;
}

.cost-value {
    font-size: 0.95rem;
    color: #ffffff;
    font-weight: 700;
    margin-bottom: 10px;
}

.iter-bar {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 10px 12px;
    margin-bottom: 8px;
    font-size: 0.75rem;
    color: #e1e8f0;
}

.luca-branding {
    padding: 16px;
    border-radius: 16px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    text-align: center;
    margin-top: 24px;
}

.luca-name {
    font-weight: 700;
    color: #ffffff;
    font-size: 0.82rem;
}

.luca-link {
    color: #d5dfeb;
    text-decoration: none;
    font-size: 0.72rem;
    margin: 0 8px;
}

.luca-link:hover {
    color: #ffffff;
}

.lab-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 16px;
    box-shadow: var(--shadow);
    animation: fade-rise 0.32s ease both;
}

.lab-card-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-soft);
    margin-bottom: 8px;
}

.lab-card-text {
    color: var(--text);
    line-height: 1.65;
}

.stAlert {
    border-radius: 16px !important;
    border: 1px solid var(--border) !important;
    animation: fade-rise 0.24s ease both;
}

[data-testid="stAlertContentSuccess"],
[data-testid="stAlertContentInfo"],
[data-testid="stAlertContentWarning"],
[data-testid="stAlertContentError"] {
    color: var(--text) !important;
}

.stCodeBlock, pre, code {
    font-family: 'IBM Plex Mono', monospace !important;
}

@media (max-width: 1100px) {
    .court-flow {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .deliberation-scene {
        grid-template-columns: 1fr;
    }
}

@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        animation: none !important;
        transition: none !important;
        scroll-behavior: auto !important;
    }
}
</style>
"""
