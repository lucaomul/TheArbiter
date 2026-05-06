import html
import re
from typing import Dict, List, Optional, Tuple


def _strip_markdown(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"```.*?```", "", value, flags=re.DOTALL)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"^\s{0,3}#+\s*", "", value, flags=re.MULTILINE)
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    value = re.sub(r"\*(.*?)\*", r"\1", value)
    return value.strip()


def _clean_line(text: str, limit: int = 88) -> str:
    value = re.sub(r"\s+", " ", _strip_markdown(text)).strip(" -:\t")
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def _extract_bullets(text: str, limit: int = 8) -> List[str]:
    bullets = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^[-*]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            candidate = re.sub(r"^[-*]\s+|^\d+\.\s+", "", stripped)
            candidate = _clean_line(candidate, 110)
            if candidate and candidate not in bullets:
                bullets.append(candidate)
        if len(bullets) >= limit:
            break
    return bullets


def _extract_sentences(text: str, limit: int = 6) -> List[str]:
    value = _strip_markdown(text)
    parts = re.split(r"(?<=[.!?])\s+", value)
    cleaned = []
    for part in parts:
        candidate = _clean_line(part, 110)
        if candidate and len(candidate.split()) >= 4 and candidate not in cleaned:
            cleaned.append(candidate)
        if len(cleaned) >= limit:
            break
    return cleaned


def _extract_time_phases(text: str, limit: int = 5) -> List[str]:
    lines = []
    patterns = [
        r"\b(?:day|days|week|weeks|month|months)\s+\d+\b",
        r"\b(?:phase|sprint)\s+\d+\b",
        r"\b(?:week|day)\s+\d+\s*[-:]\s*.+",
    ]
    for line in str(text or "").splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if any(re.search(pattern, lowered) for pattern in patterns):
            lines.append(_clean_line(stripped))
        if len(lines) >= limit:
            break
    return lines


def _keyword_strength(text: str, keywords: List[Tuple[str, str]]) -> List[Tuple[str, int]]:
    lowered = str(text or "").lower()
    strengths = []
    for label, pattern in keywords:
        count = len(re.findall(pattern, lowered))
        if count > 0:
            strengths.append((label, count))
    strengths.sort(key=lambda item: (-item[1], item[0]))
    return strengths


def _collect_tags(text: str, terms: List[str], limit: int = 6) -> List[str]:
    lowered = str(text or "").lower()
    found = []
    for term in terms:
        if term.lower() in lowered and term not in found:
            found.append(term)
        if len(found) >= limit:
            break
    return found


def _make_nodes(items: List[str], fallback: List[str]) -> List[Dict[str, str]]:
    source = items or fallback
    nodes = []
    for index, item in enumerate(source[:5], start=1):
        if " - " in item:
            label, note = item.split(" - ", 1)
        elif ": " in item:
            label, note = item.split(": ", 1)
        else:
            words = item.split()
            label = " ".join(words[:3]) if len(words) > 3 else item
            note = item if len(words) > 3 else ""
        nodes.append(
            {
                "index": f"{index:02d}",
                "label": _clean_line(label, 42),
                "note": _clean_line(note or item, 92),
            }
        )
    return nodes


def _render_metric_rows(items: List[Tuple[str, int]]) -> str:
    if not items:
        return "<div class='visual-empty'>No measurable signals extracted yet.</div>"
    peak = max(score for _, score in items) or 1
    rows = []
    for label, score in items[:5]:
        width = max(18, min(100, int((score / peak) * 100)))
        rows.append(
            "<div class='visual-metric-row'>"
            f"<div class='visual-metric-label'>{html.escape(label)}</div>"
            "<div class='visual-metric-bar'><span "
            f"style='width:{width}%;'></span></div>"
            "</div>"
        )
    return "".join(rows)


def _render_tag_cloud(items: List[str], empty_text: str) -> str:
    if not items:
        return f"<div class='visual-empty'>{html.escape(empty_text)}</div>"
    return "".join(
        f"<span class='visual-tag'>{html.escape(item)}</span>"
        for item in items[:8]
    )


def _render_node_lane(nodes: List[Dict[str, str]]) -> str:
    return "".join(
        "<div class='visual-node'>"
        f"<div class='visual-node-index'>{html.escape(node['index'])}</div>"
        f"<div class='visual-node-label'>{html.escape(node['label'])}</div>"
        f"<div class='visual-node-note'>{html.escape(node['note'])}</div>"
        "</div>"
        for node in nodes
    )


def _build_marketing_blueprint(task_text: str, solution: str) -> Dict[str, object]:
    phases = _extract_time_phases(solution) or _extract_bullets(solution, limit=5)
    channels = _keyword_strength(
        solution,
        [
            ("Outbound", r"\boutbound\b|\bcold email\b"),
            ("Paid Ads", r"\bpaid\b|\bads?\b|\bgoogle ads\b|\bmeta ads\b"),
            ("Content", r"\bcontent\b|\bseo\b|\bblog\b"),
            ("Social", r"\bsocial\b|\blinkedin\b|\binstagram\b|\btiktok\b"),
            ("Referral", r"\breferral\b|\bpartner(ship)?s?\b"),
            ("Retargeting", r"\bretarget(ing)?\b"),
            ("Events", r"\bwebinar\b|\bevent\b"),
        ],
    )
    kpis = _collect_tags(
        solution,
        ["CAC", "CPL", "CTR", "Conversion", "Retention", "No-show", "Lead quality", "Pipeline"],
    )
    return {
        "title": "Go-To-Market Blueprint",
        "subtitle": "Launch sequence, channel pressure, and measurable signals from the current answer.",
        "nodes": _make_nodes(
            phases,
            ["Positioning", "Audience Fit", "Channel Launch", "Retargeting", "Iteration Loop"],
        ),
        "cards": [
            ("Channel Mix", _render_metric_rows(channels)),
            ("KPI Signals", _render_tag_cloud(kpis, "No explicit KPI signals extracted.")),
        ],
    }


def _build_operations_blueprint(task_text: str, solution: str) -> Dict[str, object]:
    steps = _extract_bullets(solution, limit=5) or _extract_sentences(solution, limit=5)
    governance = _keyword_strength(
        solution,
        [
            ("Ownership", r"\bowner(ship)?\b|\bresponsible\b"),
            ("Handoffs", r"\bhandoff\b|\btransition\b"),
            ("SLAs", r"\bsla\b|\bresponse time\b"),
            ("Escalation", r"\bescalat(e|ion)\b"),
            ("Quality Control", r"\bqa\b|\breview\b|\bquality\b"),
            ("Exceptions", r"\bexception\b|\bedge case\b"),
        ],
    )
    controls = _collect_tags(
        solution,
        ["Approval", "Escalation", "Review", "Queue", "SLA", "Audit trail", "Exception path"],
    )
    return {
        "title": "Operational Workflow Map",
        "subtitle": "Process stages, operating controls, and execution pressure points.",
        "nodes": _make_nodes(
            steps,
            ["Intake", "Assignment", "Execution", "Escalation", "Review"],
        ),
        "cards": [
            ("Governance Signals", _render_metric_rows(governance)),
            ("Control Layer", _render_tag_cloud(controls, "No explicit operating controls extracted.")),
        ],
    }


def _build_writing_blueprint(task_text: str, solution: str) -> Dict[str, object]:
    sections = _extract_bullets(solution, limit=5) or _extract_sentences(solution, limit=5)
    rhetoric = _keyword_strength(
        solution,
        [
            ("Examples", r"\bfor example\b|\bexample\b"),
            ("Contrast", r"\bhowever\b|\bbut\b|\bon the other hand\b"),
            ("Argument", r"\bbecause\b|\btherefore\b|\bthis means\b"),
            ("Evidence", r"\bdata\b|\bproof\b|\bevidence\b|\bresult\b"),
            ("Close", r"\bin conclusion\b|\bultimately\b|\bthe point is\b"),
        ],
    )
    anchors = _collect_tags(
        solution,
        ["Hook", "Objection", "Evidence", "Counterpoint", "Takeaway", "Thesis"],
    )
    return {
        "title": "Narrative Structure Map",
        "subtitle": "How the writing is sequenced, supported, and closed.",
        "nodes": _make_nodes(
            sections,
            ["Hook", "Core Claim", "Support", "Counterpoint", "Close"],
        ),
        "cards": [
            ("Rhetorical Weight", _render_metric_rows(rhetoric)),
            ("Story Anchors", _render_tag_cloud(anchors, "No strong narrative anchors extracted.")),
        ],
    }


def _build_planning_blueprint(task_text: str, solution: str) -> Dict[str, object]:
    phases = _extract_time_phases(solution) or _extract_bullets(solution, limit=5)
    pressure = _keyword_strength(
        solution,
        [
            ("Deadlines", r"\bdeadline\b|\bdue\b|\bby\b"),
            ("Priority", r"\bpriority\b|\bmust\b|\bcritical\b"),
            ("Review", r"\breview\b|\bcheck-in\b|\breflect\b"),
            ("Risk", r"\brisk\b|\bblocker\b|\bconstraint\b"),
            ("Recovery", r"\bfallback\b|\badjust\b|\brestart\b"),
        ],
    )
    anchors = _collect_tags(
        solution,
        ["Week 1", "Week 2", "Milestone", "Priority", "Review", "Fallback", "Constraint"],
    )
    return {
        "title": "Roadmap Snapshot",
        "subtitle": "Phases, pressure points, and planning anchors from the current answer.",
        "nodes": _make_nodes(
            phases,
            ["Stabilize", "Prioritize", "Execute", "Review", "Adjust"],
        ),
        "cards": [
            ("Planning Pressure", _render_metric_rows(pressure)),
            ("Timeline Anchors", _render_tag_cloud(anchors, "No explicit timeline anchors extracted.")),
        ],
    }


def _build_software_blueprint(task_text: str, solution: str) -> Dict[str, object]:
    flow_keywords = _collect_tags(
        solution,
        ["Input", "Validation", "State", "Assignment", "API", "Storage", "Output", "Error handling", "Batch write"],
        limit=5,
    )
    depth = _keyword_strength(
        solution,
        [
            ("Validation", r"\bvalidat(e|ion)\b|\bguard\b"),
            ("State", r"\bstate\b|\bmemory\b|\btrack\b"),
            ("Data Flow", r"\bload\b|\bmap\b|\btransform\b"),
            ("Error Handling", r"\berror\b|\bexception\b|\bfallback\b"),
            ("Output", r"\breturn\b|\bwrite\b|\bdisplay\b"),
        ],
    )
    bullets = _extract_bullets(solution, limit=5) or flow_keywords
    return {
        "title": "System Flow Snapshot",
        "subtitle": "A quick architecture reading of the current technical answer.",
        "nodes": _make_nodes(
            bullets,
            ["Input", "Validation", "Execution", "Persistence", "Output"],
        ),
        "cards": [
            ("Implementation Depth", _render_metric_rows(depth)),
            ("Flow Landmarks", _render_tag_cloud(flow_keywords, "No explicit component landmarks extracted.")),
        ],
    }


def _build_general_blueprint(task_text: str, solution: str) -> Dict[str, object]:
    phases = _extract_bullets(solution, limit=5) or _extract_sentences(solution, limit=5)
    signals = _keyword_strength(
        solution,
        [
            ("Tradeoffs", r"\btrade[- ]?off\b"),
            ("Risks", r"\brisk\b|\bdownside\b"),
            ("Decision", r"\bdecision\b|\bchoose\b|\brecommend\b"),
            ("Execution", r"\bexecute\b|\bimplement\b|\baction\b"),
            ("Review", r"\breview\b|\bmeasure\b|\btrack\b"),
        ],
    )
    anchors = _collect_tags(
        solution,
        ["Recommendation", "Tradeoff", "Risk", "Action", "Review", "Owner"],
    )
    return {
        "title": "Decision Blueprint",
        "subtitle": "A structured read of the current answer's logic and action flow.",
        "nodes": _make_nodes(
            phases,
            ["Frame", "Evaluate", "Choose", "Execute", "Review"],
        ),
        "cards": [
            ("Decision Signals", _render_metric_rows(signals)),
            ("Action Anchors", _render_tag_cloud(anchors, "No strong action anchors extracted.")),
        ],
    }


def _build_mode_blueprint(task_mode: str, task_text: str, solution: str) -> Dict[str, object]:
    mapping = {
        "Software & IT": _build_software_blueprint,
        "Marketing & Growth": _build_marketing_blueprint,
        "Business & Operations": _build_operations_blueprint,
        "Writing & Content": _build_writing_blueprint,
        "Personal Planning": _build_planning_blueprint,
        "General Problem Solving": _build_general_blueprint,
    }
    builder = mapping.get(task_mode, _build_general_blueprint)
    return builder(task_text, solution)


def build_visual_blueprint_html(
    task_mode: str,
    task_text: str,
    solution: str,
    janitor_report: Optional[dict] = None,
) -> str:
    if not str(solution or "").strip():
        return ""

    blueprint = _build_mode_blueprint(task_mode, task_text, solution)
    janitor_report = janitor_report or {}
    pending = janitor_report.get("pending") or []
    preserve = janitor_report.get("preserve") or []

    card_html = "".join(
        "<div class='visual-detail-card'>"
        f"<div class='visual-detail-label'>{html.escape(title)}</div>"
        f"<div class='visual-detail-body'>{body}</div>"
        "</div>"
        for title, body in blueprint["cards"]
    )

    if pending or preserve:
        repair_mix = []
        if preserve:
            repair_mix.append(
                "<div class='visual-detail-card'>"
                "<div class='visual-detail-label'>Preserve</div>"
                f"<div class='visual-detail-body'>{_render_tag_cloud([_clean_line(item, 48) for item in preserve], 'Nothing marked to preserve.')}</div>"
                "</div>"
            )
        if pending:
            repair_mix.append(
                "<div class='visual-detail-card'>"
                "<div class='visual-detail-label'>Pressure Points</div>"
                f"<div class='visual-detail-body'>{_render_tag_cloud([_clean_line(item, 48) for item in pending], 'No pressure points extracted.')}</div>"
                "</div>"
            )
        card_html += "".join(repair_mix)

    return (
        "<div class='visual-blueprint'>"
        "<div class='visual-blueprint-header'>"
        "<div>"
        "<div class='visual-eyebrow'>Visual Blueprint</div>"
        f"<div class='visual-title'>{html.escape(str(blueprint['title']))}</div>"
        f"<div class='visual-subtitle'>{html.escape(str(blueprint['subtitle']))}</div>"
        "</div>"
        f"<div class='visual-mode-badge'>{html.escape(task_mode)}</div>"
        "</div>"
        f"<div class='visual-node-lane'>{_render_node_lane(blueprint['nodes'])}</div>"
        f"<div class='visual-detail-grid'>{card_html}</div>"
        "</div>"
    )
