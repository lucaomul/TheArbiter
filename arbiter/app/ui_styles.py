UI_CSS = """
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
"""
