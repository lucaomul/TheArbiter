from arbiter.models.state import ArbiterState
from arbiter.models.result import ArbiterResult
from arbiter.core.agent_runner import AgentRunner
from arbiter.core.iteration_engine import IterationEngine
from arbiter.prompts.registry import PromptRegistry
from arbiter.config.settings import PRICES


class ArbiterOrchestrator:
    """
    Central controller. Accepts user input, coordinates the pipeline,
    returns a structured result.

    No business logic here — only flow control.
    """

    def __init__(
        self,
        task_mode: str = "Software & IT",
        auto_mode: bool = True,
        target_score: float = 8.0,
        max_iterations: int = 5,
        auditor_model: str = "gemini-2.5-flash",
        on_iteration_complete=None,
    ):
        self.task_mode    = task_mode
        self.auto_mode    = auto_mode
        self.target_score = target_score
        self.max_iter     = max_iterations
        self.auditor_model = auditor_model
        self.on_iteration_complete = on_iteration_complete

    def run(
        self,
        user_input: str,
        clarification: str = "",
        manual_override: str = "",
    ) -> ArbiterResult:

        registry = PromptRegistry(task_mode=self.task_mode)
        runner = AgentRunner(registry)

        # ── 1. Build state ────────────────────────────────────
        state            = ArbiterState(user_input=user_input, task_mode=self.task_mode)
        state.current_task = registry.build_task_payload(user_input)

        if clarification:
            state.current_task += f"\nAdditional context: {clarification}"

        # ── 2. Audit (optional — skip if already clarified) ───
        if not clarification:
            audit_result, audit_model = self._run_audit(runner, state.current_task)
            state.track_cost("Auditor", PRICES.get(audit_model, 0.001))
            state.record_model_usage("Auditor", audit_model)

            if not audit_result.get("clear", True):
                # Surface questions to caller — caller decides what to do
                return ArbiterResult(
                    best_solution="",
                    best_score=0.0,
                    iteration_count=0,
                    debug_info={
                        "needs_clarification": True,
                        "questions": audit_result.get("questions", []),
                        "model_usage": state.model_usage,
                    },
                    messages=state.messages,
                    costs=state.costs,
                    iteration_history=[],
                )

        # ── 3. Iterate ────────────────────────────────────────
        engine = IterationEngine(
            registry=registry,
            auto_mode=self.auto_mode,
            target_score=self.target_score,
            max_iterations=self.max_iter,
            on_iteration_complete=self.on_iteration_complete,
        )

        return engine.execute(state, manual_override=manual_override)

    def _run_audit(self, runner: AgentRunner, task: str) -> tuple[dict, str]:
        return runner.run_auditor(task)
