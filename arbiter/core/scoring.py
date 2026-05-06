from arbiter.config.settings import TASK_PROFILES


class Scorer:
    """
    Converts critic outputs into a numeric score.
    """

    def compute(self, tech_result: dict, logic_result: dict, task_mode: str = "General Problem Solving") -> float:
        t = self._extract(tech_result)
        l = self._extract(logic_result)
        profile = TASK_PROFILES.get(task_mode, TASK_PROFILES["General Problem Solving"])
        weights = profile.get("score_weights", {"tech": 0.5, "logic": 0.5})
        tech_weight = float(weights.get("tech", 0.5))
        logic_weight = float(weights.get("logic", 0.5))
        total = tech_weight + logic_weight
        if total <= 0:
            tech_weight, logic_weight, total = 0.5, 0.5, 1.0
        return round(((t * tech_weight) + (l * logic_weight)) / total, 2)

    def compute_with_breakdown(
        self,
        tech_result: dict,
        logic_result: dict,
        task_mode: str = "General Problem Solving",
    ) -> dict:
        t = self._extract(tech_result)
        l = self._extract(logic_result)
        profile = TASK_PROFILES.get(task_mode, TASK_PROFILES["General Problem Solving"])
        weights = profile.get("score_weights", {"tech": 0.5, "logic": 0.5})
        tw = float(weights.get("tech", 0.5))
        lw = float(weights.get("logic", 0.5))
        total = tw + lw
        if total <= 0:
            tw, lw, total = 0.5, 0.5, 1.0
        weighted = round(((t * tw) + (l * lw)) / total, 2)
        dominant_gap = "tech" if t < l else "logic" if l < t else "balanced"
        confidence = "high" if weighted >= 8.0 else "medium" if weighted >= 6.0 else "low"
        return {
            "tech_raw": t,
            "logic_raw": l,
            "tech_weight": round(tw / total, 4),
            "logic_weight": round(lw / total, 4),
            "weighted_avg": weighted,
            "simple_avg": round((t + l) / 2, 2),
            "dominant_gap": dominant_gap,
            "confidence": confidence,
        }

    def _extract(self, result: dict, default: int = 1) -> int:
        try:
            return max(1, min(10, int(result.get("score", default))))
        except Exception:
            return default
