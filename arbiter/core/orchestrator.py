from arbiter.models.state import ArbiterState
from arbiter.models.result import ArbiterResult
from arbiter.core.agent_runner import AgentRunner
from arbiter.core.iteration_engine import IterationEngine
from arbiter.prompts.registry import PromptRegistry
from arbiter.infra.evidence_store import get_evidence_store
from typing import Optional


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
        stable_mode: bool = False,
        benchmark_mode: bool = False,
        benchmark_strategy: str = "",
        benchmark_pack: str = "",
        benchmark_case_id: str = "",
        benchmark_case_title: str = "",
        on_iteration_complete=None,
    ):
        self.task_mode    = task_mode
        self.auto_mode    = auto_mode
        self.target_score = target_score
        self.max_iter     = max_iterations
        self.auditor_model = auditor_model
        self.stable_mode = stable_mode
        self.benchmark_mode = benchmark_mode
        self.benchmark_strategy = benchmark_strategy
        self.benchmark_pack = benchmark_pack
        self.benchmark_case_id = benchmark_case_id
        self.benchmark_case_title = benchmark_case_title
        self.on_iteration_complete = on_iteration_complete

    def run(
        self,
        user_input: str,
        clarification: str = "",
        manual_override: str = "",
        allow_complex_software_team: Optional[bool] = None,
        software_team_profile: str = "",
        supporting_materials: Optional[list[dict]] = None,
        supporting_urls: Optional[list[str]] = None,
    ) -> ArbiterResult:

        registry = PromptRegistry(task_mode=self.task_mode)
        runner = AgentRunner(registry)
        evidence_bundle = get_evidence_store().ingest(
            query=user_input,
            materials=supporting_materials or [],
            urls=supporting_urls or [],
        )

        # ── 1. Build state ────────────────────────────────────
        state            = ArbiterState(
            user_input=user_input,
            task_mode=self.task_mode,
            stable_mode=self.stable_mode,
            benchmark_mode=self.benchmark_mode,
            benchmark_strategy=self.benchmark_strategy,
            benchmark_pack=self.benchmark_pack,
            benchmark_case_id=self.benchmark_case_id,
            benchmark_case_title=self.benchmark_case_title,
            evidence_bundle=evidence_bundle,
        )
        state.current_task = registry.build_task_payload(user_input, evidence_bundle=evidence_bundle)
        state.software_team_user_approved = bool(allow_complex_software_team)
        state.software_team_profile = str(software_team_profile or "").strip().lower()

        if clarification:
            state.current_task += f"\nAdditional context: {clarification}"

        # ── 2. Audit (optional — skip if already clarified) ───
        if not clarification:
            audit_result, audit_model = self._run_audit(
                runner,
                state.current_task,
                context={
                    "stable_mode": self.stable_mode,
                    "allow_provider_fallback": True,
                },
            )
            state.track_cost("Auditor", runner.latest_call_cost("Auditor", audit_model))
            state.record_model_usage("Auditor", audit_model, runner.latest_call_metadata("Auditor"))
            audit_warning = str(audit_result.get("warning", "") or "").strip()
            if audit_warning:
                state.add_message("Auditor", audit_warning)
            audit_debug = {
                "audit_warning": audit_warning,
                "audit_provider_limited": bool(audit_result.get("provider_limited", False)),
                "audit_provider_error": bool(audit_result.get("provider_error", False)),
                "audit_fallback_used": bool(audit_result.get("fallback_used", False)),
                "audit_attempted_models": list(audit_result.get("attempted_models", []) or []),
                "audit_retry_after_seconds": audit_result.get("retry_after_seconds"),
                "audit_model": audit_model,
            }

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
                        **audit_debug,
                    },
                    messages=state.messages,
                    costs=state.costs,
                    iteration_history=[],
                )

            if self.max_iter <= 0:
                return ArbiterResult(
                    best_solution="",
                    best_score=0.0,
                    iteration_count=0,
                    debug_info={
                        "needs_clarification": False,
                        "questions": [],
                        "model_usage": state.model_usage,
                        **audit_debug,
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
            stable_mode=self.stable_mode,
            benchmark_mode=self.benchmark_mode,
            on_iteration_complete=self.on_iteration_complete,
        )

        return engine.execute(state, manual_override=manual_override)

    def _run_audit(self, runner: AgentRunner, task: str, context: Optional[dict] = None) -> tuple[dict, str]:
        return runner.run_auditor(task, context=context)
