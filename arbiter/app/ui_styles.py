UI_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@300;500;700&display=swap');

.stApp {
    background:
        radial-gradient(circle at top left, rgba(0,255,163,0.10), transparent 22%),
        radial-gradient(circle at top right, rgba(37,99,235,0.10), transparent 20%),
        linear-gradient(180deg, #040507 0%, #080b10 45%, #050608 100%);
    color: #e0e2e6;
    font-family: 'Space Grotesk', sans-serif;
}

.stApp::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background-image:
        linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
    background-size: 32px 32px;
    mask-image: radial-gradient(circle at center, black 35%, transparent 85%);
    opacity: 0.18;
    z-index: 0;
}

.agent-card {
    background: linear-gradient(180deg, rgba(10,14,19,0.94), rgba(7,10,14,0.96));
    border: 1px solid rgba(135,154,173,0.16);
    border-radius: 18px;
    padding: 24px 26px;
    margin-bottom: 22px;
    box-shadow:
        0 18px 60px rgba(0,0,0,0.35),
        inset 0 1px 0 rgba(255,255,255,0.04);
    backdrop-filter: blur(18px);
    transition: 0.25s ease;
}
.agent-card:hover {
    transform: translateY(-1px);
    border-color: rgba(0,255,163,0.35);
    box-shadow:
        0 20px 60px rgba(0,0,0,0.38),
        0 0 0 1px rgba(0,255,163,0.08),
        inset 0 1px 0 rgba(255,255,255,0.05);
}

.score-badge {
    display: inline-block;
    padding: 7px 16px;
    border-radius: 999px;
    background: rgba(0,255,163,0.1);
    border: 1px solid rgba(0,255,163,0.45);
    color: #00ffa3;
    font-weight: 700;
    margin-bottom: 15px;
    box-shadow: 0 0 10px rgba(0,255,163,0.2);
    letter-spacing: 0.08em;
    font-size: 0.72rem;
}
.score-badge.warning {
    border-color: rgba(255,170,0,0.45);
    color: #ffaa00;
    background: rgba(255,170,0,0.1);
    box-shadow: 0 0 10px rgba(255,170,0,0.2);
}
.score-badge.danger {
    border-color: rgba(255,68,102,0.45);
    color: #ff4466;
    background: rgba(255,68,102,0.1);
    box-shadow: 0 0 10px rgba(255,68,102,0.2);
}

.luca-branding {
    padding: 22px;
    border-radius: 18px;
    background: linear-gradient(180deg, rgba(0,255,163,0.06), rgba(8,10,13,0.92));
    border: 1px solid rgba(0,255,163,0.18);
    text-align: center;
    margin-top: 30px;
    box-shadow: 0 14px 40px rgba(0,0,0,0.25);
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
    border: 1px solid rgba(0,255,163,0.35) !important;
    background: linear-gradient(180deg, rgba(0,255,163,0.08), rgba(0,255,163,0.03)) !important;
    color: #00ffa3 !important;
    text-transform: uppercase;
    letter-spacing: 2px;
    font-weight: 700;
    width: 100%;
    padding: 11px 14px;
    transition: 0.4s;
    border-radius: 14px !important;
    box-shadow: 0 10px 30px rgba(0,0,0,0.18);
}
.stButton>button:hover {
    background: #00ffa3 !important;
    color: #000 !important;
    box-shadow: 0 0 25px #00ffa3;
}

[data-testid="stSidebar"] {
    background:
        linear-gradient(180deg, rgba(6,9,12,0.98), rgba(8,10,13,0.98)) !important;
    border-right: 1px solid rgba(255,255,255,0.06);
}

.cost-label {
    font-size: 0.68rem;
    color: #7d8790;
    margin-bottom: 4px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    white-space: nowrap;
}
.cost-value {
    font-size: 0.92rem;
    color: #f5fffb;
    font-weight: 700;
    margin-bottom: 10px;
}

.iter-bar {
    background: linear-gradient(180deg, rgba(0,255,163,0.05), rgba(255,255,255,0.01));
    border: 1px solid rgba(0,255,163,0.12);
    border-radius: 12px;
    padding: 11px 14px;
    margin-bottom: 8px;
    font-size: 0.75rem;
    color: #9aa6ad;
}

.telemetry-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
    margin-bottom: 28px;
}
.telemetry-card {
    position: relative;
    overflow: hidden;
    background: linear-gradient(180deg, rgba(12,16,21,0.95), rgba(7,10,14,0.96));
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 18px;
    padding: 18px;
    box-shadow: 0 18px 48px rgba(0,0,0,0.25);
}
.telemetry-card::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(0,255,163,0.10), transparent 42%);
    pointer-events: none;
}
.telemetry-label {
    font-size: 0.64rem;
    letter-spacing: 0.18em;
    color: #7a848c;
    margin-bottom: 8px;
    text-transform: uppercase;
}
.telemetry-value {
    font-size: 1.2rem;
    color: #f8fffc;
    font-weight: 700;
    letter-spacing: -0.02em;
}
.telemetry-meta {
    margin-top: 8px;
    font-size: 0.75rem;
    color: #9aa6ad;
    line-height: 1.5;
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
    padding: 16px 18px;
    border-radius: 16px;
    background: linear-gradient(180deg, rgba(255,255,255,0.025), rgba(255,255,255,0.015));
    border: 1px solid rgba(255,255,255,0.06);
    line-height: 1.75;
    color: #d8dde2;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
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

[data-testid="stMetric"] {
    background: linear-gradient(180deg, rgba(11,15,20,0.92), rgba(8,10,14,0.95));
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 18px;
    padding: 14px 16px;
    box-shadow: 0 14px 40px rgba(0,0,0,0.18);
}
[data-testid="stMetricLabel"] {
    color: #7f8b95 !important;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.65rem !important;
}
[data-testid="stMetricValue"] {
    color: #f7fffb !important;
    font-family: 'Space Grotesk', sans-serif !important;
}

.stTextArea textarea,
.stTextInput input {
    background: rgba(10,14,19,0.92) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 16px !important;
    color: #ecf3f7 !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
}

.stSelectbox [data-baseweb="select"] > div,
.stNumberInput input {
    background: rgba(10,14,19,0.92) !important;
    border-radius: 14px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
}

.stAlert {
    border-radius: 16px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
}
@media (max-width: 900px) {
    .telemetry-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}
</style>
"""
