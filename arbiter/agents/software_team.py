from __future__ import annotations

from typing import Optional

from arbiter.agents.base_agent import BaseAgent
from arbiter.infra.model_selector import provider_for_model
from arbiter.models.team import SpecialistPlan, TeamArchitecturePlan, TeamRoutingDecision


SPECIALIST_ROLE_LANES = {
    "Lead Software Architect": "Define system boundaries, file ownership, shared contracts, and the delivery sequence for the whole build.",
    "Backend Architect": "Own backend services, APIs, validation, integrations, and core business logic.",
    "Frontend Architect": "Own UI structure, routes, pages, components, states, and interaction flow.",
    "Database Architect": "Own schemas, persistence, migrations, data flow, and SQL/storage constraints.",
    "DevOps & Reliability Architect": "Own deployment, runtime reliability, observability, CI/CD, operational safeguards, and environment design.",
    "Security Architect": "Own auth, secrets, access control, secure defaults, threat reduction, and abuse-prevention concerns.",
    "QA/Test Architect": "Own test strategy, regression coverage, contract tests, end-to-end checks, and release confidence.",
    "Integration Architect": "Own cross-service contracts, handoffs, compatibility, and seams between subsystems.",
    "Performance Architect": "Own scaling risks, caching, hotspots, throughput, latency, and performance tradeoffs.",
}

SPECIALIST_JSON_SHAPE = """Return ONLY valid JSON in this exact shape:
{
  "role": "Role Name",
  "scope": "One short paragraph describing your lane.",
  "recommendations": ["recommendation 1"],
  "risks": ["risk 1"],
  "dependencies": ["dependency 1"],
  "interfaces": ["interface 1"],
  "implementation_steps": ["step 1"],
  "open_questions": ["question 1"],
  "implementation_artifact": "Optional concrete artifact, code sketch, config block, SQL, interface definition, or implementation notes."
}
"""

SOFTWARE_TEAM_PROMPTS = {
    role: (
        f"Act as the {role} for a coordinated software architecture team.\n"
        f"Your lane: {lane}\n\n"
        "Rules:\n"
        "- Stay inside your lane, but coordinate with the other roles through dependencies and interfaces.\n"
        "- You are not the entire team. Do not rewrite adjacent subsystems unless your lane depends on them.\n"
        "- Be concise, implementation-oriented, and specific.\n"
        "- Prefer actionable architecture and delivery guidance over abstract theory.\n"
        "- Publish stable contracts, handoffs, and assumptions that another specialist could implement against.\n"
        "- If your lane needs code, config, schema, or interface artifacts, include them in `implementation_artifact`.\n"
        "- Flag uncertainty honestly. Do not invent requirements, APIs, schema details, or infrastructure facts.\n"
        "- If something is uncertain, list it under `open_questions` rather than hallucinating certainty.\n\n"
        f"{SPECIALIST_JSON_SHAPE}"
    )
    for role, lane in SPECIALIST_ROLE_LANES.items()
}


class SoftwareTeamAgent(BaseAgent):
    def __init__(self, role: str, model: str, system_prompt: str):
        provider = provider_for_model(model, "openai")
        super().__init__(role, provider, model, system_prompt)
        self.role = role

    def plan(self, task: str, history: str = "") -> SpecialistPlan:
        raw = self.run(task, history=history, force_json=False)
        llm_result = self.last_result()
        error = BaseAgent.error_payload(raw, llm_result=llm_result)
        if error and error.get("provider_error"):
            return fallback_specialist_plan(self.role, f"Provider/model failure: {error.get('critique', 'unknown failure')}")
        return normalize_specialist_plan(self.role, BaseAgent.clean_json(raw), raw_output=raw)


def normalize_specialist_plan(role: str, data: dict, raw_output: str = "") -> SpecialistPlan:
    if not isinstance(data, dict) or data.get("parse_error"):
        return fallback_specialist_plan(
            role,
            "The specialist did not return valid JSON, so a conservative fallback plan was generated.",
        )

    def normalize_list(value, limit: int = 6) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        return [str(item).strip() for item in value if str(item).strip()][:limit]

    scope = str(data.get("scope", "") or "").strip()
    if not scope:
        scope = f"{role} lane for the current software task."

    plan = SpecialistPlan(
        role=str(data.get("role", role) or role),
        scope=scope,
        recommendations=normalize_list(data.get("recommendations")),
        risks=normalize_list(data.get("risks")),
        dependencies=normalize_list(data.get("dependencies")),
        interfaces=normalize_list(data.get("interfaces")),
        implementation_steps=normalize_list(data.get("implementation_steps")),
        open_questions=normalize_list(data.get("open_questions")),
        implementation_artifact=str(data.get("implementation_artifact", "") or "").strip(),
    )
    if not plan.recommendations and raw_output:
        plan.recommendations = [str(raw_output).strip()[:240]]
    return plan


def fallback_specialist_plan(role: str, failure_reason: str) -> SpecialistPlan:
    return SpecialistPlan(
        role=role,
        scope=f"{role} could not complete a normal pass.",
        recommendations=[f"Re-run or replace the {role} pass before finalizing this subsystem."],
        risks=[failure_reason],
        dependencies=[],
        interfaces=[],
        implementation_steps=["Treat this lane as partially missing and preserve the rest of the team output."],
        open_questions=["Should this specialist be retried with a different model or lane constraint?"],
        implementation_artifact="",
    )


def synthesize_team_plan(
    user_input: str,
    task_mode: str,
    specialist_plans: list[SpecialistPlan],
    routing_decision: Optional[TeamRoutingDecision] = None,
    selected_profile: str = "",
) -> TeamArchitecturePlan:
    use_team = bool(routing_decision.use_team) if routing_decision else bool(specialist_plans)
    roles = [plan.role for plan in specialist_plans]
    component_plan = _dedupe(
        [
            *[rec for plan in specialist_plans for rec in plan.recommendations[:2]],
            *[interface for plan in specialist_plans for interface in plan.interfaces[:1]],
        ]
    )[:10]
    handoffs = _dedupe(
        [
            f"{plan.role}: {item}"
            for plan in specialist_plans
            for item in (plan.dependencies[:2] + plan.interfaces[:2])
        ]
    )[:12]
    risks = _dedupe([risk for plan in specialist_plans for risk in plan.risks])[:10]
    implementation_order = _build_implementation_order(specialist_plans)

    architecture_summary_parts = [
        f"Task mode: {task_mode}.",
        f"Specialist roles used: {', '.join(roles) or 'none'}.",
    ]
    if routing_decision and routing_decision.detected_domains:
        architecture_summary_parts.append(
            f"Detected domains: {', '.join(routing_decision.detected_domains)}."
        )
    architecture_summary_parts.extend(
        [plan.scope for plan in specialist_plans[:3] if plan.scope]
    )
    architecture_summary = " ".join(part.strip() for part in architecture_summary_parts if part).strip()

    final_recommendation = _build_final_recommendation(
        user_input=user_input,
        specialist_plans=specialist_plans,
        architecture_summary=architecture_summary,
        component_plan=component_plan,
        handoffs=handoffs,
        implementation_order=implementation_order,
        risks=risks,
    )

    return TeamArchitecturePlan(
        use_team=use_team,
        roles=roles,
        specialist_plans=specialist_plans,
        architecture_summary=architecture_summary,
        component_plan=component_plan,
        cross_team_handoffs=handoffs,
        main_risks=risks,
        implementation_order=implementation_order,
        final_recommendation=final_recommendation,
        detected_domains=list(routing_decision.detected_domains) if routing_decision else [],
        routing_reason=str(routing_decision.reason or "") if routing_decision else "",
        selected_profile=str(selected_profile or ""),
        selected_profile_label="Dream Team" if str(selected_profile or "").strip().lower() == "dream" else ("Efficient Team" if str(selected_profile or "").strip().lower() == "efficient" else ""),
    )


def _dedupe(items: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def _build_implementation_order(plans: list[SpecialistPlan]) -> list[str]:
    preferred = [
        "Lead Software Architect",
        "Database Architect",
        "Backend Architect",
        "Frontend Architect",
        "Integration Architect",
        "Security Architect",
        "Performance Architect",
        "QA/Test Architect",
        "DevOps & Reliability Architect",
    ]
    by_role = {plan.role: plan for plan in plans}
    ordered_roles = [role for role in preferred if role in by_role] + [plan.role for plan in plans if plan.role not in preferred]
    return [
        f"{role}: {by_role[role].implementation_steps[0] if by_role[role].implementation_steps else by_role[role].scope}"
        for role in ordered_roles
    ]


def _build_final_recommendation(
    user_input: str,
    specialist_plans: list[SpecialistPlan],
    architecture_summary: str,
    component_plan: list[str],
    handoffs: list[str],
    implementation_order: list[str],
    risks: list[str],
) -> str:
    sections = [
        "Software Architect Team Summary",
        architecture_summary,
        "",
        "Requested Build",
        user_input.strip(),
        "",
        "Component Plan",
    ]
    sections.extend(f"- {item}" for item in component_plan or ["No component plan generated."])
    sections.extend(["", "Implementation Order"])
    sections.extend(f"- {item}" for item in implementation_order or ["No implementation order generated."])
    sections.extend(["", "Cross-Team Handoffs"])
    sections.extend(f"- {item}" for item in handoffs or ["No explicit handoffs generated."])
    if risks:
        sections.extend(["", "Main Risks"])
        sections.extend(f"- {item}" for item in risks)

    for plan in specialist_plans:
        sections.extend(["", plan.role, f"Scope: {plan.scope}"])
        if plan.recommendations:
            sections.append("Recommendations:")
            sections.extend(f"- {item}" for item in plan.recommendations)
        if plan.implementation_steps:
            sections.append("Implementation Steps:")
            sections.extend(f"- {item}" for item in plan.implementation_steps)
        if plan.interfaces:
            sections.append("Interfaces:")
            sections.extend(f"- {item}" for item in plan.interfaces)
        if plan.implementation_artifact:
            sections.extend(["Implementation Artifact:", plan.implementation_artifact.strip()])

    sections.extend(
        [
            "",
            "Final Recommendation",
            "Use the integrated specialist guidance above as the implementation package for the next build/review cycle.",
        ]
    )
    return "\n".join(str(section).strip() for section in sections if str(section).strip())
