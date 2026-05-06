from collections import defaultdict
from typing import Optional


BENCHMARK_CASES = [
    {
        "id": "software_scheduler",
        "pack": "Software Essentials",
        "task_mode": "Software & IT",
        "title": "Google Apps Script Workforce Scheduler",
        "prompt": (
            "Build a Google Apps Script workforce scheduler for a monthly rota using Google Sheets. "
            "Read employees, shift requirements, and prior shift history from Staff, Requirements, Schedule, "
            "and History sheets. Respect max weekly hours, min weekly hours, unavailable dates, approved off-days, "
            "and at least 10 hours of rest between shifts. Never assign more than one shift to the same employee on the same day. "
            "Batch-write the final schedule. Avoid hidden global dependencies and return complete executable code."
        ),
        "goal": "Test multi-function correctness, scheduling rules, and preflight robustness.",
    },
    {
        "id": "software_fastapi_booking",
        "pack": "Software Essentials",
        "task_mode": "Software & IT",
        "title": "FastAPI Booking Backend",
        "prompt": (
            "Build a Python FastAPI booking backend with JWT auth, user roles, reservations, admin approval flow, "
            "rate limiting, and SQLite persistence. Return complete runnable code with models, routes, validation, "
            "startup instructions, and proper double-booking protection."
        ),
        "goal": "Test code completeness, auth flow, validation, and backend architecture quality.",
    },
    {
        "id": "marketing_legaltech_growth",
        "pack": "Growth & GTM",
        "task_mode": "Marketing & Growth",
        "title": "Legal-Tech Growth Engine",
        "prompt": (
            "Design a 30-day B2B SaaS growth engine for a niche legal-tech product serving small law firms. "
            "Include channel strategy, messaging angles, KPI targets, budget allocation, and fallback logic if paid acquisition underperforms."
        ),
        "goal": "Test channel logic, KPI rigor, and practical execution quality.",
    },
    {
        "id": "marketing_creator_offer",
        "pack": "Growth & GTM",
        "task_mode": "Marketing & Growth",
        "title": "Creator Offer Funnel",
        "prompt": (
            "Design a 21-day launch plan for a creator selling a premium cohort-based course. "
            "Include lead magnet logic, landing page messaging, email sequence structure, conversion metrics, and launch-week contingency plans."
        ),
        "goal": "Test offer clarity, funnel completeness, and conversion reasoning.",
    },
    {
        "id": "ops_service_framework",
        "pack": "Operations & Systems",
        "task_mode": "Business & Operations",
        "title": "Client Service Operating Framework",
        "prompt": (
            "Create an operations framework for a 20-person client service business with handoffs, SLAs, escalation rules, "
            "ownership boundaries, weekly operating rhythm, and lightweight implementation guidance for Asana, ClickUp, or Monday."
        ),
        "goal": "Test process design, ownership clarity, and system-level completeness.",
    },
    {
        "id": "ops_recruitment_workflow",
        "pack": "Operations & Systems",
        "task_mode": "Business & Operations",
        "title": "Recruitment Workflow System",
        "prompt": (
            "Design a repeatable recruiting operations workflow for a startup hiring across sales, support, and engineering. "
            "Include intake, evaluation stages, scorecards, handoffs, SLAs, hiring manager responsibilities, and exception handling."
        ),
        "goal": "Test workflow rigor, exception handling, and operating-system thinking.",
    },
    {
        "id": "writing_ai_failures",
        "pack": "Writing & Editorial",
        "task_mode": "Writing & Content",
        "title": "Why AI Automations Fail",
        "prompt": (
            "Write a publish-ready article on why AI automations fail in operations, with examples, counterarguments, "
            "practical lessons, and a strong conclusion. Keep it sharp, credible, and practical."
        ),
        "goal": "Test structure, argument quality, and editorial usefulness.",
    },
    {
        "id": "writing_founder_memo",
        "pack": "Writing & Editorial",
        "task_mode": "Writing & Content",
        "title": "Founder Strategy Memo",
        "prompt": (
            "Write a founder memo explaining why a product team should prioritize reliability, observability, and operational discipline "
            "before chasing advanced AI features. Include tradeoffs, objections, and a decision framework."
        ),
        "goal": "Test persuasive clarity, structure, and balance.",
    },
    {
        "id": "planning_90_day_balance",
        "pack": "Planning & Execution",
        "task_mode": "Personal Planning",
        "title": "90-Day Balance Plan",
        "prompt": (
            "Build a 90-day execution plan balancing a full-time job, a side business, health, and debt reduction. "
            "Break it into phases, weekly priorities, realistic tradeoffs, risk points, and simple tracking metrics."
        ),
        "goal": "Test realism, sustainability, and prioritization quality.",
    },
    {
        "id": "planning_founder_reset",
        "pack": "Planning & Execution",
        "task_mode": "Personal Planning",
        "title": "Founder Reset Plan",
        "prompt": (
            "Create a 6-week reset plan for an overwhelmed solo founder who needs to stabilize sleep, reduce reactive work, "
            "regain product focus, and rebuild a healthier weekly operating rhythm."
        ),
        "goal": "Test prioritization, constraint realism, and execution clarity.",
    },
]


def get_benchmark_packs() -> list[str]:
    return list(dict.fromkeys(case["pack"] for case in BENCHMARK_CASES))


def get_benchmark_cases(pack: Optional[str] = None, task_mode: Optional[str] = None) -> list[dict]:
    cases = BENCHMARK_CASES
    if pack:
        cases = [case for case in cases if case["pack"] == pack]
    if task_mode:
        cases = [case for case in cases if case["task_mode"] == task_mode]
    return cases


def get_case_by_id(case_id: str) -> Optional[dict]:
    for case in BENCHMARK_CASES:
        if case["id"] == case_id:
            return case
    return None


def grouped_by_pack() -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for case in BENCHMARK_CASES:
        grouped[case["pack"]].append(case)
    return dict(grouped)
