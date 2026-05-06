"""
core/learning/optimizer.py

Analyzes iteration history and recommends improvements.
Does NOT mutate state directly — returns recommendations only.
"""
from arbiter.config.settings import SETTINGS
from arbiter.infra.plugin_registry import get_plugin_registry
from arbiter.models.state import ArbiterState


class LearningOptimizer:
    @staticmethod
    def _quality_architect_model() -> str:
        registry = get_plugin_registry()
        preferred = getattr(SETTINGS, "architect_model_quality", "") or SETTINGS.architect_model
        resolved = registry.resolve_model_id(preferred)
        if registry.is_selectable(resolved, "Architect"):
            return resolved
        replacement = registry.recommended_replacement(resolved, "Architect")
        if replacement:
            return replacement
        for candidate in registry.candidates_for_role("Architect"):
            if candidate.quality_tier == "high" and registry.is_selectable(candidate.model_id, "Architect"):
                return candidate.model_id
        return resolved or SETTINGS.architect_model

    def optimize(self, state: ArbiterState) -> dict:
        if getattr(state, "stable_mode", False):
            history = state.iteration_history
            if not history:
                return {"mode": "stable"}
            latest = history[-1]
            recommendations = {"mode": "stable"}
            if latest["tech"] < 6:
                recommendations["focus"] = "tech_repair"
                recommendations["hint"] = (
                    f"Stable mode active. Keep the same selected model family and fix the technical defect set: {latest['tech_critique']}"
                )
            elif latest["logic"] < 7:
                recommendations["focus"] = "logic_repair"
                recommendations["hint"] = (
                    f"Stable mode active. Keep the same selected model family and address this logic gap: {latest['logic_critique']}"
                )
            else:
                recommendations["focus"] = "polish"
            return recommendations

        history = state.iteration_history
        if not history:
            return {}

        recommendations = {}
        latest  = history[-1]
        t_score = latest["tech"]
        l_score = latest["logic"]
        quality_model = self._quality_architect_model()

        if t_score < 6:
            recommendations["architect_model"] = quality_model
            recommendations["focus"] = "tech_repair"
            recommendations["hint"] = (
                f"Technical quality is below threshold ({t_score}/10). "
                f"Fix the broken subsystem: {latest['tech_critique']}"
            )

        if len(history) >= 2 and (state.tech_stall_count >= 1 or state.tech_regression_count >= 1 or state.tech_oscillation_count >= 1):
            recommendations["architect_model"] = quality_model
            recommendations["focus"] = "full_subsystem_rebuild"
            recommendations["hint"] = (
                "Recent cycles are drifting or oscillating. Stop incremental patching and rebuild the failing subsystem cleanly."
            )

        if state.rewrite_mode:
            recommendations["architect_model"] = quality_model
            recommendations["focus"] = "rewrite_mode"
            recommendations["hint"] = (
                "Rewrite mode active. Replace the broken subsystem with a simpler, safer implementation."
            )

        if state.tech_oscillation_count >= 1:
            recommendations["focus"] = "narrow_core_repair"
            recommendations["hint"] = (
                "Technical quality is oscillating. Narrow the scope to the broken core engine only."
            )

        if l_score < 7 and t_score >= 6:
            recommendations["focus"] = "logic_repair"
            recommendations["hint"]  = f"Logic gap: {latest['logic_critique']}"

        if t_score >= 8 and l_score >= 8:
            recommendations["focus"] = "polish"

        return recommendations
