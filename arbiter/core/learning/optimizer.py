"""
core/learning/optimizer.py

Analyzes iteration history and recommends improvements.
Does NOT mutate state directly — returns recommendations only.
"""
from arbiter.models.state import ArbiterState


class LearningOptimizer:

    def optimize(self, state: ArbiterState) -> dict:
        history = state.iteration_history
        if not history:
            return {}

        recommendations = {}
        latest  = history[-1]
        t_score = latest["tech"]
        l_score = latest["logic"]

        if t_score < 6:
            recommendations["architect_model"] = "gpt-4o"
            recommendations["focus"] = "tech_repair"
            recommendations["hint"] = (
                f"Technical quality is below threshold ({t_score}/10). "
                f"Fix the broken subsystem: {latest['tech_critique']}"
            )

        if len(history) >= 2 and (state.tech_stall_count >= 1 or state.tech_regression_count >= 1 or state.tech_oscillation_count >= 1):
            recommendations["architect_model"] = "gpt-4o"
            recommendations["focus"] = "full_subsystem_rebuild"
            recommendations["hint"] = (
                "Recent cycles are drifting or oscillating. Stop incremental patching and rebuild the failing subsystem cleanly."
            )

        if state.rewrite_mode:
            recommendations["architect_model"] = "gpt-4o"
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
