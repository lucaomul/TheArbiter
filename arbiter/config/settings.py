from dataclasses import dataclass, field


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
    architect_model_cheap: str = "llama-3.1-8b-instant"
    tech_critic_model: str = "llama-3.3-70b-versatile"
    logic_critic_model: str = "llama-3.3-70b-versatile"
    auditor_model: str = "llama-3.3-70b-versatile"
    repair_model: str = "llama-3.1-8b-instant"

    # Cost threshold to switch to cheaper architect model
    cheap_model_threshold: float = 6.0

    # Exploration rate for model selector (0-1)
    exploration_rate: float = 0.0

    # Validation / repair
    enable_preflight: bool = True
    allow_repair_retry: bool = True
    max_preflight_repairs: int = 1
    allow_diagnostic_critics_on_preflight_fail: bool = True
    critic_debate_enabled: bool = True
    final_validation_enabled: bool = True

    # Provider resilience
    rate_limit_cooldown_seconds: int = 45 * 60
    provider_error_cooldown_seconds: int = 5 * 60
    decommission_cooldown_seconds: int = 7 * 24 * 60 * 60


SETTINGS = Settings()


PRICES: dict = {
    "gpt-4o":                  0.015,
    "gpt-4o-mini":             0.0006,
    "claude-sonnet-4-20250514": 0.003,
    "claude-3-5-haiku-latest":  0.0008,
    "gemini-2.5-pro":          0.003,
    "gemini-2.5-flash":        0.0001,
    "gemini-1.5-pro":          0.003,
    "gemini-1.5-flash":        0.0001,
    "llama-3.3-70b-versatile": 0.000001,
    "llama-3.1-8b-instant":    0.000001,
}


TASK_PROFILES: dict = {
    "Software & IT": {
        "tag": "Build Systems",
        "summary": "Code, debugging, automation, architecture, product engineering.",
        "auditor": "Prioritize stack, inputs/outputs, constraints, data shape, integrations, and edge cases.",
        "architect": "Behave like a senior engineer. Prefer concrete implementation, readable code, validation, and maintainability.",
        "execution": "Judge technical correctness, operational reliability, performance, and implementation quality.",
        "logic": "Judge completeness, consistency, flow, missing constraints, and hidden assumptions.",
        "delivery": "Lead with executable code and concise implementation insights.",
        "validator": "software",
        "score_weights": {"tech": 0.6, "logic": 0.4},
    },
    "Marketing & Growth": {
        "tag": "Drive Attention",
        "summary": "Campaigns, positioning, funnels, copy, offers, outreach, audience fit.",
        "auditor": "Clarify audience, objective, channel, budget, tone, offer, constraints, and success metric.",
        "architect": "Behave like a sharp growth strategist and conversion copy lead.",
        "execution": "Judge market fit, clarity, persuasion, channel realism, and likelihood of execution success.",
        "logic": "Judge strategic coherence, funnel completeness, and audience alignment.",
        "delivery": "Lead with the strategy or assets, then concise reasoning.",
        "validator": "marketing",
        "score_weights": {"tech": 0.4, "logic": 0.6},
    },
    "Business & Operations": {
        "tag": "Run Better",
        "summary": "Processes, SOPs, workflows, decision systems, team operations, service design.",
        "auditor": "Clarify business goal, current process, bottlenecks, stakeholders, resources, and constraints.",
        "architect": "Behave like an operations architect. Prefer scalable workflows and clarity of ownership.",
        "execution": "Judge practicality, efficiency, operational risk, and whether people could follow the solution.",
        "logic": "Judge process completeness, handoff integrity, missing dependencies, and policy contradictions.",
        "delivery": "Lead with the workflow or SOP, then short operational notes.",
        "validator": "operations",
        "score_weights": {"tech": 0.45, "logic": 0.55},
    },
    "Writing & Content": {
        "tag": "Shape Narrative",
        "summary": "Articles, scripts, posts, decks, messaging, structured writing.",
        "auditor": "Clarify audience, purpose, tone, format, desired outcome, and constraints.",
        "architect": "Behave like a strategist-editor. Prefer strong structure and compelling language.",
        "execution": "Judge readability, quality, persuasion, audience fit, and polish.",
        "logic": "Judge structure, coherence, completeness, and whether content achieves the intended purpose.",
        "delivery": "Lead with the deliverable itself, then short editorial notes.",
        "validator": "writing",
        "score_weights": {"tech": 0.4, "logic": 0.6},
    },
    "Personal Planning": {
        "tag": "Make Decisions",
        "summary": "Life admin, choices, planning, routines, prioritization, personal systems.",
        "auditor": "Clarify the real outcome, time horizon, tradeoffs, and personal constraints.",
        "architect": "Behave like a thoughtful strategic coach. Prefer realistic plans and concrete next actions.",
        "execution": "Judge practicality, realism, sustainability, and whether the plan can be acted on.",
        "logic": "Judge consistency, tradeoff handling, and whether the plan addresses the stated problem.",
        "delivery": "Lead with the plan and next actions, then concise rationale.",
        "validator": "planning",
        "score_weights": {"tech": 0.4, "logic": 0.6},
    },
    "General Problem Solving": {
        "tag": "Think Broadly",
        "summary": "Mixed problems that need structured thinking, options, and decision quality.",
        "auditor": "Clarify objective, constraints, stakes, timeframe, and what a successful answer looks like.",
        "architect": "Behave like a high-agency strategist. Prefer clarity, options, tradeoffs, and executable recommendations.",
        "execution": "Judge usefulness, practicality, actionability, and quality of the proposed solution.",
        "logic": "Judge structure, completeness, contradiction risk, and whether the recommendation matches the problem.",
        "delivery": "Lead with the best recommendation, then options and tradeoffs.",
        "validator": "general",
        "score_weights": {"tech": 0.5, "logic": 0.5},
    },
}
