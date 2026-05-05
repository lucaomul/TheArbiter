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

        # Target score reached
        if state.last_avg_score >= self.target_score:
            return True, f"Target score {self.target_score} reached — avg: {state.last_avg_score:.1f}."

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
