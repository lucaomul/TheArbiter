from arbiter.config.settings import TASK_PROFILES


class Scorer:
    """
    Converts critic outputs into a numeric score.
    """

    def compute(self, tech_result: dict, logic_result: dict, task_mode: str = "General Problem Solving") -> float:
        tech_score = self._extract(tech_result)
        logic_score = self._extract(logic_result)
        profile = TASK_PROFILES.get(task_mode, TASK_PROFILES["General Problem Solving"])
        weights = profile.get("score_weights", {"tech": 0.5, "logic": 0.5})
        tech_weight = float(weights.get("tech", 0.5))
        logic_weight = float(weights.get("logic", 0.5))
        total = tech_weight + logic_weight
        if total <= 0:
            tech_weight, logic_weight, total = 0.5, 0.5, 1.0
        return round(((tech_score * tech_weight) + (logic_score * logic_weight)) / total, 2)

    def compute_with_breakdown(
        self,
        tech_result: dict,
        logic_result: dict,
        task_mode: str = "General Problem Solving",
    ) -> dict:
        tech_score = self._extract(tech_result)
        logic_score = self._extract(logic_result)
        profile = TASK_PROFILES.get(task_mode, TASK_PROFILES["General Problem Solving"])
        weights = profile.get("score_weights", {"tech": 0.5, "logic": 0.5})
        tw = float(weights.get("tech", 0.5))
        lw = float(weights.get("logic", 0.5))
        total = tw + lw
        if total <= 0:
            tw, lw, total = 0.5, 0.5, 1.0
        weighted = round(((tech_score * tw) + (logic_score * lw)) / total, 2)
        dominant_gap = "tech" if tech_score < logic_score else "logic" if logic_score < tech_score else "balanced"
        confidence = "high" if weighted >= 8.0 else "medium" if weighted >= 6.0 else "low"
        return {
            "tech_raw": tech_score,
            "logic_raw": logic_score,
            "tech_weight": round(tw / total, 4),
            "logic_weight": round(lw / total, 4),
            "weighted_avg": weighted,
            "simple_avg": round((tech_score + logic_score) / 2, 2),
            "dominant_gap": dominant_gap,
            "confidence": confidence,
        }

    def _extract(self, result: dict, default: int = 1) -> int:
        try:
            return max(1, min(10, int(result.get("score", default))))
        except Exception:
            return default
