from arbiter.models.state import ArbiterState
from arbiter.config.settings import SETTINGS


class Stopper:
    """
    Decides when to stop the iteration loop.
    All thresholds come from Settings — nothing hardcoded.
    """

    def __init__(
        self,
        max_iterations: int = None,
        target_score: float = None,
        plateau_rounds: int = None,
        auto_mode: bool = True,
    ):
        self.max_iterations = max_iterations or SETTINGS.max_iterations
        self.target_score   = target_score   or SETTINGS.target_score
        self.plateau_rounds = plateau_rounds or SETTINGS.plateau_rounds
        self.auto_mode      = auto_mode

    def should_stop(self, state: ArbiterState) -> tuple[bool, str]:
        """
        Returns (should_stop: bool, reason: str)
        """
        # Always stop in manual mode after 1 cycle
        if not self.auto_mode:
            return True, "Manual mode — single cycle."

        # Max iterations
        if state.iteration >= self.max_iterations:
            return True, f"Max iterations ({self.max_iterations}) reached."

        latest = state.iteration_history[-1] if state.iteration_history else {}
        verification_status = str(latest.get("verification_status", "UNVERIFIED")).upper()

        # Ideal ceiling
        if state.last_avg_score >= 9.95:
            return True, f"Near-perfect score reached — avg: {state.last_avg_score:.1f}."

        if verification_status == "VERIFIED" and state.last_avg_score >= 9.5:
            return True, f"High-confidence result reached — avg: {state.last_avg_score:.1f}."

        # Target score acts as a floor, not an instant stop.
        if state.last_avg_score >= self.target_score and self._is_satisfactory_plateau(state):
            return True, (
                f"Minimum target {self.target_score} was reached and later rounds plateaued "
                f"around {state.last_avg_score:.1f}."
            )

        if state.recent_low_tech_count >= 2:
            return True, "Failure-budget guardrail triggered — too many recent low technical scores."

        if state.score_plateau_count >= 1 and state.last_tech_score is not None and state.last_tech_score <= SETTINGS.rewrite_trigger_score:
            return True, "Cost guardrail triggered — repeated low technical score pattern."

        if state.tech_regression_count >= 1 and state.last_tech_score is not None and state.last_tech_score <= SETTINGS.rewrite_trigger_score:
            return True, "Regression guardrail triggered — technical quality worsened after a prior attempt."

        if state.tech_oscillation_count >= 1:
            return True, "Oscillation guardrail triggered — technical quality is bouncing in the same low band."

        # Plateau detection
        if self._is_plateau(state):
            return True, "Score plateau detected — no improvement over last rounds."

        return False, ""

    def _is_plateau(self, state: ArbiterState) -> bool:
        history = state.iteration_history
        if len(history) < self.plateau_rounds:
            return False
        recent_scores = [h["avg"] for h in history[-self.plateau_rounds:]]
        return len(set(recent_scores)) == 1

    def _is_satisfactory_plateau(self, state: ArbiterState) -> bool:
        history = state.iteration_history
        if len(history) < 2:
            return False
        recent = history[-2:]
        if not all(float(item.get("avg", 0.0) or 0.0) >= self.target_score for item in recent):
            return False
        improvement = float(recent[-1].get("avg", 0.0) or 0.0) - float(recent[-2].get("avg", 0.0) or 0.0)
        same_verification = str(recent[-1].get("verification_status", "")) == str(recent[-2].get("verification_status", ""))
        return improvement <= 0.15 and same_verification
