from __future__ import annotations


PROFILE_ORDER = ["efficient", "dream"]


TEAM_PROFILE_DEFINITIONS = {
    "efficient": {
        "label": "Efficient Team",
        "description": "Keeps the larger specialist workflow, but routes the team through the lowest-cost reliable model lane first.",
        "cost_factor": 0.78,
        "latency_factor": 0.9,
        "default_model": "llama-3.3-70b-versatile",
        "role_models": {
            "Lead Software Architect": "llama-3.3-70b-versatile",
            "Backend Architect": "llama-3.3-70b-versatile",
            "Frontend Architect": "llama-3.3-70b-versatile",
            "Database Architect": "llama-3.3-70b-versatile",
            "DevOps & Reliability Architect": "llama-3.3-70b-versatile",
            "Security Architect": "llama-3.3-70b-versatile",
            "QA/Test Architect": "llama-3.3-70b-versatile",
            "Integration Architect": "llama-3.3-70b-versatile",
            "Performance Architect": "llama-3.3-70b-versatile",
        },
    },
    "dream": {
        "label": "Dream Team",
        "description": "Uses the strongest role-aware model routing available for maximum architectural depth, implementation quality, and cross-team coordination.",
        "cost_factor": 1.22,
        "latency_factor": 1.08,
        "default_model": "gpt-4o",
        "role_models": {
            "Lead Software Architect": "gpt-4o",
            "Backend Architect": "claude-sonnet-4-20250514",
            "Frontend Architect": "gpt-4o",
            "Database Architect": "gpt-4o",
            "DevOps & Reliability Architect": "claude-sonnet-4-20250514",
            "Security Architect": "claude-sonnet-4-20250514",
            "QA/Test Architect": "gpt-4o",
            "Integration Architect": "gpt-4o",
            "Performance Architect": "claude-sonnet-4-20250514",
        },
    },
}


def normalize_team_profile(profile: str, default: str = "efficient") -> str:
    candidate = str(profile or "").strip().lower()
    if candidate in TEAM_PROFILE_DEFINITIONS:
        return candidate
    return default


def recommended_team_profile(complexity_level: str, detected_domains: list[str] | None = None) -> str:
    domains = {str(item or "").strip().lower() for item in (detected_domains or []) if str(item or "").strip()}
    high_risk_domains = {
        "auth",
        "security",
        "deployment",
        "docker",
        "ci/cd",
        "monitoring",
        "scalability",
        "microservices",
        "queue",
        "websocket",
        "data pipeline",
        "cloud",
    }
    if str(complexity_level or "").strip().lower() == "very_complex":
        return "dream"
    if domains & high_risk_domains:
        return "dream"
    return "efficient"


def profile_model_for_role(role: str, profile: str) -> str:
    normalized = normalize_team_profile(profile)
    config = TEAM_PROFILE_DEFINITIONS.get(normalized, TEAM_PROFILE_DEFINITIONS["efficient"])
    return str(config.get("role_models", {}).get(role) or config.get("default_model") or "").strip()


def build_profile_options(
    roles: list[str],
    base_cost_multiplier: float,
    base_latency_multiplier: float,
    complexity_level: str,
    detected_domains: list[str] | None = None,
) -> tuple[str, dict[str, dict]]:
    recommended = recommended_team_profile(complexity_level, detected_domains)
    options: dict[str, dict] = {}
    for profile in PROFILE_ORDER:
        config = TEAM_PROFILE_DEFINITIONS[profile]
        role_models = {
            role: profile_model_for_role(role, profile)
            for role in roles
        }
        options[profile] = {
            "label": config["label"],
            "description": config["description"],
            "estimated_cost_multiplier": round(
                max(1.0, float(base_cost_multiplier or 1.0) * float(config["cost_factor"])),
                2,
            ),
            "estimated_latency_multiplier": round(
                max(1.0, float(base_latency_multiplier or 1.0) * float(config["latency_factor"])),
                2,
            ),
            "role_models": role_models,
            "recommended": profile == recommended,
        }
    return recommended, options
