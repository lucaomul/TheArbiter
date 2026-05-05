import random
import time
from typing import Optional
from arbiter.config.settings import PRICES, SETTINGS
from arbiter.infra.performance_store import get_performance_store


# Candidate models per agent
AGENT_CANDIDATES: dict = {
    "Architect":    ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gpt-4o-mini", "gpt-4o"],
    "Tech Critic":  ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemini-2.5-flash", "gemini-2.5-pro"],
    "Logic Critic": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemini-2.5-flash"],
    "Auditor":      ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemini-2.5-flash", "gemini-2.5-pro"],
    "Janitor":      ["llama-3.1-8b-instant", "gpt-4o-mini"],
    "Repair":       ["llama-3.1-8b-instant", "gpt-4o-mini"],
}

# Provider mapping
MODEL_PROVIDER: dict = {
    "gpt-4o":                  "openai",
    "gpt-4o-mini":             "openai",
    "gemini-2.5-pro":          "gemini",
    "gemini-2.5-flash":        "gemini",
    "gemini-1.5-pro":          "gemini",
    "gemini-1.5-flash":        "gemini",
    "llama-3.3-70b-versatile": "groq",
    "llama-3.1-8b-instant":    "groq",
}


def provider_for_model(model: str, default: str = "openai") -> str:
    model_name = str(model or "").strip()
    if model_name.startswith("ollama:"):
        return "ollama"
    return MODEL_PROVIDER.get(model_name, default)


class ModelSelector:
    """
    Selects the best model for a given agent based on:
    - performance / cost ratio
    - exploration (occasional random choice)
    - manual override
    """

    def __init__(self):
        self._store = get_performance_store()
        self._overrides: dict = {}
        self._cooldowns: dict[str, float] = {}

    def set_override(self, agent: str, model: str):
        self._overrides[agent] = model

    def clear_override(self, agent: str):
        self._overrides.pop(agent, None)

    def mark_temporarily_unavailable(self, model: str, seconds: Optional[int] = None):
        cooldown = max(30, int(seconds or SETTINGS.provider_error_cooldown_seconds))
        self._cooldowns[model] = max(self._cooldowns.get(model, 0.0), time.time() + cooldown)

    def is_temporarily_unavailable(self, model: str) -> bool:
        until = self._cooldowns.get(model, 0.0)
        if until <= 0:
            return False
        if until <= time.time():
            self._cooldowns.pop(model, None)
            return False
        return True

    def seconds_remaining(self, model: str) -> int:
        if not self.is_temporarily_unavailable(model):
            return 0
        return max(0, int(self._cooldowns.get(model, 0.0) - time.time()))

    @staticmethod
    def _default_model_for_agent(agent: str) -> str:
        defaults = {
            "Architect": SETTINGS.architect_model,
            "Tech Critic": SETTINGS.tech_critic_model,
            "Logic Critic": SETTINGS.logic_critic_model,
            "Auditor": SETTINGS.auditor_model,
            "Janitor": "llama-3.1-8b-instant",
            "Repair": SETTINGS.repair_model,
        }
        return defaults.get(agent, "gpt-4o-mini")

    @staticmethod
    def _safe_last_tech_score(context: dict) -> int:
        raw = (context or {}).get("last_tech_score", 10)
        try:
            if raw is None:
                return 10
            return int(raw)
        except Exception:
            return 10

    def choose(self, agent: str, context: dict = None) -> tuple[str, str]:
        """
        Returns (model_name, provider).
        context can contain: {"force_quality": True, "last_tech_score": 4}
        """
        context = context or {}

        # Manual override
        if agent in self._overrides:
            model = self._overrides[agent]
            if self.is_temporarily_unavailable(model):
                fallbacks = self.fallback_models(agent, model)
                if fallbacks:
                    model = fallbacks[0]
            return model, provider_for_model(model)

        candidates = AGENT_CANDIDATES.get(agent, ["gpt-4o-mini"])
        available_candidates = [model for model in candidates if not self.is_temporarily_unavailable(model)]
        if available_candidates:
            candidates = available_candidates
        last_tech_score = self._safe_last_tech_score(context)
        default_model = self._default_model_for_agent(agent)

        # Force quality model when tech score is low
        if context.get("force_quality") or last_tech_score < 6:
            if agent == "Architect":
                model = SETTINGS.architect_model
                return model, provider_for_model(model)

        # Free-first / default-first behavior before enough history exists
        total_samples = sum(self._store.sample_count(agent, model) for model in candidates)
        if total_samples == 0 and default_model in candidates:
            return default_model, provider_for_model(default_model)

        # Exploration: try a random model occasionally
        if random.random() < SETTINGS.exploration_rate and len(candidates) > 1:
            model = random.choice(candidates)
            return model, provider_for_model(model)

        # Score = avg_performance / cost
        best_model = candidates[0]
        best_score = -1.0

        for model in candidates:
            avg_perf = self._store.average_score(agent, model)
            cost     = PRICES.get(model, 0.01)
            ratio    = avg_perf / cost if cost > 0 else avg_perf
            if ratio > best_score:
                best_score = ratio
                best_model = model

        return best_model, provider_for_model(best_model)

    def fallback_models(self, agent: str, current_model: str = "") -> list[str]:
        candidates = AGENT_CANDIDATES.get(agent, ["gpt-4o-mini"])
        ordered = [model for model in candidates if model != current_model]
        available = [model for model in ordered if not self.is_temporarily_unavailable(model)]
        return available or ordered


# Singleton
_selector = ModelSelector()


def get_model_selector() -> ModelSelector:
    return _selector
