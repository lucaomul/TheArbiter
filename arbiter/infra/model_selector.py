"""
infra/model_selector.py

Plugin-aware model selector with backward-compatible helper methods.

This keeps the newer plugin registry architecture while still supporting the
older runner calls like:
- fallback_models(...)
- mark_temporarily_unavailable(...)
- seconds_remaining(...)
"""

import random
import time
from typing import Optional

from arbiter.config.settings import SETTINGS
from arbiter.infra.decision_log import DecisionLog
from arbiter.infra.performance_store import get_performance_store
from arbiter.infra.plugin_registry import ModelPlugin, get_plugin_registry, provider_for_model


class ModelSelector:
    """
    Picks the best model for an agent role.
    Transparent: every pick can be logged with reason and confidence.
    """

    def __init__(self):
        self._registry = get_plugin_registry()
        self._perf = get_performance_store()
        self._overrides: dict[str, str] = {}
        self._cooldowns: dict[str, float] = {}
        self._provider_lock: str = ""

    # ── Override API ──────────────────────────────────────────

    def set_override(self, agent: str, model_id: str):
        self._overrides[agent] = model_id

    def clear_override(self, agent: str):
        self._overrides.pop(agent, None)

    def set_provider_lock(self, provider: str = ""):
        self._provider_lock = str(provider or "").strip().lower()

    def clear_provider_lock(self):
        self._provider_lock = ""

    # ── Cooldown API (new + compatibility) ───────────────────

    def set_cooldown(self, model_id: str, until_timestamp: float):
        self._cooldowns[model_id] = until_timestamp

    def mark_temporarily_unavailable(self, model_id: str, seconds: Optional[int] = None):
        cooldown = max(30, int(seconds or SETTINGS.provider_error_cooldown_seconds))
        until = time.time() + cooldown
        self._cooldowns[model_id] = max(self._cooldowns.get(model_id, 0.0), until)

    def is_temporarily_unavailable(self, model_id: str) -> bool:
        until = self._cooldowns.get(model_id, 0.0)
        if until <= 0:
            return False
        if until <= time.time():
            self._cooldowns.pop(model_id, None)
            return False
        return True

    def seconds_remaining(self, model_id: str) -> int:
        if not self.is_temporarily_unavailable(model_id):
            return 0
        return max(0, int(self._cooldowns.get(model_id, 0.0) - time.time()))

    # ── Main entry point ──────────────────────────────────────

    def choose(
        self,
        agent: str,
        context: dict = None,
        decision_log: Optional[DecisionLog] = None,
        iteration: int = 0,
    ) -> tuple[str, str]:
        """
        Returns (model_id, provider).
        Logs the decision to decision_log if provided.
        """
        context = context or {}

        # 1. Manual override
        if agent in self._overrides:
            model_id = self._overrides[agent]
            if self._provider_lock and provider_for_model(model_id, "") != self._provider_lock:
                fallbacks = self.fallback_models(agent, "")
                if fallbacks:
                    model_id = fallbacks[0]
            if self.is_temporarily_unavailable(model_id):
                fallbacks = self.fallback_models(agent, model_id)
                if fallbacks:
                    model_id = fallbacks[0]
            provider = provider_for_model(model_id, "openai")
            self._log(
                decision_log,
                agent,
                model_id,
                provider,
                iteration,
                reason="Manual override via sidebar or programmatic set_override.",
                confidence="high",
                perf=None,
                cost=self._registry.cost_for(model_id),
            )
            return model_id, provider

        candidates = self._available_candidates(agent)
        if not candidates:
            candidates = self._registry.candidates_for_role(agent)

        if not candidates:
            self._log(
                decision_log,
                agent,
                "gpt-4o-mini",
                "openai",
                iteration,
                reason="No candidates found for role — using gpt-4o-mini as fallback.",
                confidence="low",
                perf=None,
                cost=None,
            )
            return "gpt-4o-mini", "openai"

        # 2. Force quality when tech score is critical
        force_quality = (
            context.get("force_quality")
            or (context.get("last_tech_score") is not None and context["last_tech_score"] < 6)
        )
        if force_quality and not context.get("stable_mode"):
            high_q = [c for c in candidates if c.quality_tier == "high"]
            if high_q:
                chosen = high_q[0]
                self._log(
                    decision_log,
                    agent,
                    chosen.model_id,
                    chosen.provider,
                    iteration,
                    reason=f"Force quality: tech score {context.get('last_tech_score', '?')} < 6.",
                    confidence="high",
                    perf=None,
                    cost=chosen.cost,
                )
                return chosen.model_id, chosen.provider

        # 3. Exploration
        if len(candidates) > 1 and random.random() < SETTINGS.exploration_rate:
            chosen = random.choice(candidates)
            self._log(
                decision_log,
                agent,
                chosen.model_id,
                chosen.provider,
                iteration,
                reason="Exploration mode — random candidate selected.",
                confidence="low",
                perf=None,
                cost=chosen.cost,
            )
            return chosen.model_id, chosen.provider

        # 4. Perf / cost ratio
        chosen, perf, ratio = self._best_by_ratio(agent, candidates)
        self._log(
            decision_log,
            agent,
            chosen.model_id,
            chosen.provider,
            iteration,
            reason=f"Best perf/cost ratio ({ratio:.1f}) from {len(candidates)} candidates.",
            confidence="high" if perf >= 7.0 else "medium",
            perf=perf,
            cost=chosen.cost,
        )
        return chosen.model_id, chosen.provider

    # ── Compatibility helpers for older runner code ──────────

    def fallback_models(self, agent: str, current_model: str = "") -> list[str]:
        candidates = self._registry.candidates_for_role(agent)
        if self._provider_lock:
            candidates = [plugin for plugin in candidates if plugin.provider == self._provider_lock]
        current_provider = provider_for_model(current_model, "")
        current_family = current_model.split(":", 1)[0] if ":" in current_model else current_model.split("-", 1)[0]

        def sort_key(plugin: ModelPlugin):
            same_provider = 0 if plugin.provider == current_provider else 1
            plugin_family = plugin.model_id.split(":", 1)[0] if ":" in plugin.model_id else plugin.model_id.split("-", 1)[0]
            same_family = 0 if plugin_family == current_family else 1
            quality_order = {"high": 0, "mid": 1, "low": 2}
            return (
                same_provider,
                same_family,
                quality_order.get(plugin.quality_tier, 9),
                plugin.cost,
                plugin.model_id,
            )

        ordered_plugins = sorted(
            [plugin for plugin in candidates if plugin.model_id != current_model],
            key=sort_key,
        )
        ordered = [plugin.model_id for plugin in ordered_plugins]
        available = [model_id for model_id in ordered if not self.is_temporarily_unavailable(model_id)]
        return available or ordered

    # ── Internals ─────────────────────────────────────────────

    def _available_candidates(self, agent: str) -> list[ModelPlugin]:
        now = time.time()
        candidates = [
            plugin for plugin in self._registry.candidates_for_role(agent)
            if self._cooldowns.get(plugin.model_id, 0.0) <= now
        ]
        if self._provider_lock:
            candidates = [plugin for plugin in candidates if plugin.provider == self._provider_lock]
        return candidates

    def _best_by_ratio(self, agent: str, candidates: list[ModelPlugin]) -> tuple[ModelPlugin, float, float]:
        best_plugin = candidates[0]
        best_perf = 5.0
        best_ratio = -1.0

        for plugin in candidates:
            avg_perf = self._perf.average_score(agent, plugin.model_id)
            cost = plugin.cost if plugin.cost > 0 else 0.000001
            ratio = avg_perf / cost
            if ratio > best_ratio:
                best_ratio = ratio
                best_plugin = plugin
                best_perf = avg_perf

        return best_plugin, best_perf, best_ratio

    @staticmethod
    def _log(
        log: Optional[DecisionLog],
        agent: str,
        model_id: str,
        provider: str,
        iteration: int,
        reason: str,
        confidence: str,
        perf: Optional[float],
        cost: Optional[float],
    ):
        if log is None:
            return
        log.model_selected(
            agent=agent,
            model=model_id,
            reason=reason,
            confidence=confidence,
            iteration=iteration,
            perf_score=perf,
            cost=cost,
        )


_selector = ModelSelector()


def get_model_selector() -> ModelSelector:
    return _selector
