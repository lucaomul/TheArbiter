from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    # Iteration control
    max_iterations: int = 5
    target_score: float = 8.0
    plateau_rounds: int = 2
    low_tech_threshold: int = 4
    rewrite_trigger_score: int = 5

    # Model defaults
    architect_model: str = "llama-3.3-70b-versatile"
    architect_model_quality: str = "alias:openai_primary"
    architect_model_cheap: str = "llama-3.1-8b-instant"
    tech_critic_model: str = "llama-3.3-70b-versatile"
    logic_critic_model: str = "llama-3.3-70b-versatile"
    auditor_model: str = "llama-3.3-70b-versatile"
    repair_model: str = "llama-3.1-8b-instant"

    # Cost threshold to switch to cheaper architect model
    cheap_model_threshold: float = 6.0

    # Exploration rate for model selector (0-1)
    exploration_rate: float = 0.15

    # Validation / repair
    enable_preflight: bool = True
    allow_repair_retry: bool = True
    max_preflight_repairs: int = 1
    allow_diagnostic_critics_on_preflight_fail: bool = True
    critic_debate_enabled: bool = True
    final_validation_enabled: bool = True
    parallel_critics: bool = True
    critic_timeout_seconds: int = 45
    critic_redundancy_score_band_check: bool = True

    # Provider resilience
    rate_limit_cooldown_seconds: int = 45 * 60
    provider_error_cooldown_seconds: int = 5 * 60
    decommission_cooldown_seconds: int = 7 * 24 * 60 * 60

    def __post_init__(self):
        if not 0.0 <= float(self.exploration_rate) <= 1.0:
            raise ValueError("Settings.exploration_rate must be between 0.0 and 1.0.")
        if int(self.max_iterations) < 1:
            raise ValueError("Settings.max_iterations must be >= 1.")
        if not 1.0 <= float(self.target_score) <= 10.0:
            raise ValueError("Settings.target_score must be between 1.0 and 10.0.")
        if int(self.plateau_rounds) < 1:
            raise ValueError("Settings.plateau_rounds must be >= 1.")


SETTINGS = Settings()


PRICES: dict = {
    "gpt-4o":                  0.015,
    "gpt-4o-mini":             0.0006,
    "claude-sonnet-4-20250514": 0.003,
    "claude-3-5-haiku-latest":  0.0008,
    "gemini-2.5-pro":          0.003,
    "gemini-2.5-pro-preview-05-06": 0.003,
    "gemini-2.5-flash":        0.0001,
    "gemini-1.5-pro":          0.003,
    "gemini-1.5-flash":        0.0001,
    "llama-3.3-70b-versatile": 0.000001,
    "llama-3.1-70b-versatile": 0.000001,
    "llama-3.1-8b-instant":    0.000001,
    "mixtral-8x7b-32768":      0.000001,
}


TOKEN_PRICING_USD_PER_MILLION: dict = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-latest": {"input": 0.80, "output": 4.00},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-pro-preview-05-06": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
}


def token_pricing_for_model(model: str) -> Optional[dict]:
    return TOKEN_PRICING_USD_PER_MILLION.get(model)


def estimate_token_cost_usd(
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> Optional[float]:
    pricing = token_pricing_for_model(model)
    if not pricing:
        return None
    input_cost = (max(0, int(prompt_tokens or 0)) / 1_000_000.0) * float(pricing["input"])
    output_cost = (max(0, int(completion_tokens or 0)) / 1_000_000.0) * float(pricing["output"])
    return round(input_cost + output_cost, 8)


TASK_PROFILES: dict = {
    "Software & IT": {
        "tag": "Build Systems",
        "summary": "Code, debugging, automation, architecture, product engineering.",
        "auditor": "Prioritize stack, inputs/outputs, constraints, data shape, integrations, and edge cases.",
        "architect": "Behave like a senior engineer. Prefer concrete implementation, readable code, validation, and maintainability.",
        "execution": "Judge technical correctness, operational reliability, performance, and implementation quality.",
        "logic": "Judge completeness, consistency, flow, missing constraints, and hidden assumptions.",
        "janitor": "Compress technical and logical defects into a clean repair contract that preserves working implementation and strips noisy advice.",
        "delivery": "Lead with executable code and concise implementation insights.",
        "validator": "software",
        "score_weights": {"tech": 0.6, "logic": 0.4},
        "role_playbooks": {
            "Auditor": (
                "- Confirm stack, runtime, entrypoint, dependencies, data contracts, and external integrations.\n"
                "- Ask about edge-case policies only when implementation depends on them.\n"
                "- Prioritize missing inputs, outputs, schemas, auth, environment, and success criteria."
            ),
            "Architect": (
                "- Produce working implementation, not advisory prose.\n"
                "- Favor explicit helpers, local scope correctness, validation, and testable flow.\n"
                "- Resolve known defect sets fully before polishing."
            ),
            "Tech Critic": (
                "- Hunt for correctness bugs, scope leaks, broken execution flow, data integrity issues, and performance hazards.\n"
                "- Penalize missing implementation, undefined variables, broken control flow, and unsafe write patterns heavily."
            ),
            "Logic Critic": (
                "- Focus on requirement coverage, end-to-end flow, edge-case handling, and policy consistency.\n"
                "- Do not repeat code-style bugs unless they create a distinct design gap."
            ),
            "Janitor": (
                "- Distill software findings into subsystem-level repair steps.\n"
                "- Preserve working modules, batch resolved defects, and keep the retry brief implementation-focused."
            ),
        },
    },
    "Marketing & Growth": {
        "tag": "Drive Attention",
        "summary": "Campaigns, positioning, funnels, copy, offers, outreach, audience fit.",
        "auditor": "Clarify audience, objective, channel, budget, tone, offer, constraints, and success metric.",
        "architect": "Behave like a sharp growth strategist and conversion copy lead.",
        "execution": "Judge market fit, clarity, persuasion, channel realism, and likelihood of execution success.",
        "logic": "Judge strategic coherence, funnel completeness, and audience alignment.",
        "janitor": "Condense the strategic debate into one tighter go-to-market or funnel repair brief, separating real gaps from nice-to-have ideas.",
        "delivery": "Lead with the strategy or assets, then concise reasoning.",
        "validator": "marketing",
        "score_weights": {"tech": 0.4, "logic": 0.6},
        "role_playbooks": {
            "Auditor": (
                "- Identify missing ICP, offer, channel, budget, timeline, positioning, and KPI definitions.\n"
                "- Ask only the questions that materially change campaign strategy or conversion logic."
            ),
            "Architect": (
                "- Deliver strategy, messaging, funnel logic, campaign structure, or copy assets in plain language.\n"
                "- Be specific about audience, offer, channels, budget allocation, and fallback logic.\n"
                "- Do not drift into code or product implementation unless explicitly asked."
            ),
            "Tech Critic": (
                "- Evaluate execution realism: channel fit, budget practicality, sequencing, measurement, and operator workload.\n"
                "- Penalize vague tactics, weak KPIs, unrealistic CAC/CPL assumptions, and missing contingencies."
            ),
            "Logic Critic": (
                "- Evaluate whether the strategy actually fits the ICP, objective, and funnel stage.\n"
                "- Check for broken positioning, missing funnel stages, contradiction between channels and goals, or weak offer logic."
            ),
            "Janitor": (
                "- Separate real strategy gaps from optional creative ideas.\n"
                "- Rewrite findings into a tighter GTM/funnel brief that the Architect can execute directly."
            ),
        },
    },
    "Business & Operations": {
        "tag": "Run Better",
        "summary": "Processes, SOPs, workflows, decision systems, team operations, service design.",
        "auditor": "Clarify business goal, current process, bottlenecks, stakeholders, resources, and constraints.",
        "architect": "Behave like an operations architect. Prefer scalable workflows and clarity of ownership.",
        "execution": "Judge practicality, efficiency, operational risk, and whether people could follow the solution.",
        "logic": "Judge process completeness, handoff integrity, missing dependencies, and policy contradictions.",
        "janitor": "Turn process criticism into one cleaner operating brief: owners, handoffs, escalations, controls, and what to preserve.",
        "delivery": "Lead with the workflow or SOP, then short operational notes.",
        "validator": "operations",
        "score_weights": {"tech": 0.45, "logic": 0.55},
        "role_playbooks": {
            "Auditor": (
                "- Clarify business objective, current workflow, actors, bottlenecks, SLAs, tools, and escalation rules.\n"
                "- Ask about missing ownership or policy only when the process cannot be designed without it."
            ),
            "Architect": (
                "- Produce SOPs, workflows, operating systems, or decision frameworks that people can actually follow.\n"
                "- Make ownership, triggers, handoffs, service levels, approvals, and exception paths explicit."
            ),
            "Tech Critic": (
                "- Evaluate operational feasibility, control quality, failure handling, workload realism, and execution overhead.\n"
                "- Penalize missing ownership, vague handoffs, no escalation path, and process fragility."
            ),
            "Logic Critic": (
                "- Check end-to-end completeness, dependency order, policy consistency, and exception coverage.\n"
                "- Flag broken loops, contradictory rules, missing approvals, or unowned process steps."
            ),
            "Janitor": (
                "- Consolidate process defects into the smallest possible repair plan.\n"
                "- Keep the retry brief focused on owners, handoffs, controls, and unresolved bottlenecks."
            ),
        },
    },
    "Writing & Content": {
        "tag": "Shape Narrative",
        "summary": "Articles, scripts, posts, decks, messaging, structured writing.",
        "auditor": "Clarify audience, purpose, tone, format, desired outcome, and constraints.",
        "architect": "Behave like a strategist-editor. Prefer strong structure and compelling language.",
        "execution": "Judge readability, quality, persuasion, audience fit, and polish.",
        "logic": "Judge structure, coherence, completeness, and whether content achieves the intended purpose.",
        "janitor": "Convert scattered editorial criticism into one concise rewrite brief: what to keep, what to sharpen, what to cut.",
        "delivery": "Lead with the deliverable itself, then short editorial notes.",
        "validator": "writing",
        "score_weights": {"tech": 0.4, "logic": 0.6},
        "role_playbooks": {
            "Auditor": (
                "- Clarify audience, publication format, tone, length, outcome, and point of view.\n"
                "- Ask about missing editorial constraints only when they materially change the writing."
            ),
            "Architect": (
                "- Write the actual content first: article, memo, script, post, or message.\n"
                "- Use strong structure, specific examples, and a clear narrative or argument.\n"
                "- Do not fall back to outline-only output unless explicitly asked."
            ),
            "Tech Critic": (
                "- Judge readability, rhythm, clarity, specificity, audience fit, and polish.\n"
                "- Penalize filler, generic phrasing, weak openings, thin support, and awkward structure."
            ),
            "Logic Critic": (
                "- Judge whether the piece fulfills its purpose, maintains coherent flow, and actually proves its main point.\n"
                "- Flag missing support, broken argument chains, repetition, or unclear takeaways."
            ),
            "Janitor": (
                "- Turn editorial critique into a practical rewrite brief.\n"
                "- Preserve strong lines or structure that already work, and focus the retry on the few changes that matter most."
            ),
        },
    },
    "Personal Planning": {
        "tag": "Make Decisions",
        "summary": "Life admin, choices, planning, routines, prioritization, personal systems.",
        "auditor": "Clarify the real outcome, time horizon, tradeoffs, and personal constraints.",
        "architect": "Behave like a thoughtful strategic coach. Prefer realistic plans and concrete next actions.",
        "execution": "Judge practicality, realism, sustainability, and whether the plan can be acted on.",
        "logic": "Judge consistency, tradeoff handling, and whether the plan addresses the stated problem.",
        "janitor": "Compress planning feedback into one realistic next-step brief that reduces friction instead of adding complexity.",
        "delivery": "Lead with the plan and next actions, then concise rationale.",
        "validator": "planning",
        "score_weights": {"tech": 0.4, "logic": 0.6},
        "role_playbooks": {
            "Auditor": (
                "- Clarify goal, time horizon, constraints, energy, obligations, tradeoffs, and what success looks like.\n"
                "- Ask only for the personal details needed to make the plan realistic."
            ),
            "Architect": (
                "- Produce a realistic plan with priorities, sequence, tradeoffs, and restart logic.\n"
                "- Keep it human-scale: concrete next actions, fallback days, and sustainable pacing."
            ),
            "Tech Critic": (
                "- Judge whether the plan is executable in real life: time load, sustainability, tracking burden, and friction.\n"
                "- Penalize overpacked routines, vague execution, and plans that depend on unrealistic discipline."
            ),
            "Logic Critic": (
                "- Judge whether the plan actually solves the stated problem and handles the main tradeoffs.\n"
                "- Flag missing contingencies, hidden contradictions, or advice that ignores the user's real constraints."
            ),
            "Janitor": (
                "- Reduce noisy planning feedback into one calm, realistic retry brief.\n"
                "- Preserve what is already actionable and cut complexity that will make the plan harder to follow."
            ),
        },
    },
    "General Problem Solving": {
        "tag": "Think Broadly",
        "summary": "Mixed problems that need structured thinking, options, and decision quality.",
        "auditor": "Clarify objective, constraints, stakes, timeframe, and what a successful answer looks like.",
        "architect": "Behave like a high-agency strategist. Prefer clarity, options, tradeoffs, and executable recommendations.",
        "execution": "Judge usefulness, practicality, actionability, and quality of the proposed solution.",
        "logic": "Judge structure, completeness, contradiction risk, and whether the recommendation matches the problem.",
        "janitor": "Consolidate broad reasoning into one sharp retry brief that keeps the strongest recommendation and removes drift.",
        "delivery": "Lead with the best recommendation, then options and tradeoffs.",
        "validator": "general",
        "score_weights": {"tech": 0.5, "logic": 0.5},
        "role_playbooks": {
            "Auditor": (
                "- Clarify objective, constraints, stakes, timeframe, decision criteria, and success conditions.\n"
                "- Ask only the missing questions that materially change the recommendation."
            ),
            "Architect": (
                "- Deliver the best recommendation first, then alternatives, tradeoffs, and next actions.\n"
                "- Prefer structured reasoning, explicit assumptions, and clear decision logic over abstraction."
            ),
            "Tech Critic": (
                "- Judge whether the recommendation can actually be executed, defended, and adapted.\n"
                "- Penalize vague actionability, weak mechanisms, and advice that sounds smart but cannot be used."
            ),
            "Logic Critic": (
                "- Judge structure, coherence, option quality, assumption handling, and recommendation fit.\n"
                "- Flag reasoning gaps, missing options, contradiction risk, or unsupported conclusions."
            ),
            "Janitor": (
                "- Boil the debate down to the essential decision corrections.\n"
                "- Preserve the strongest recommendation path while isolating the unresolved reasoning gaps."
            ),
        },
    },
}
