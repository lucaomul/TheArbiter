from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional
import re
import time
from uuid import uuid4

from arbiter.app.result_formatter import ResultFormatter
from arbiter.models.state import ArbiterState, IterationRecord
from arbiter.models.result import ArbiterResult
from arbiter.core.agent_runner import AgentRunner
from arbiter.agents.base_agent import BaseAgent
from arbiter.core.scoring import Scorer
from arbiter.core.stopping import Stopper
from arbiter.core.learning.optimizer import LearningOptimizer
from arbiter.core.preflight import PreflightValidator
from arbiter.core.final_verifier import FinalVerifier, VerificationResult
from arbiter.prompts.registry import PromptRegistry
from arbiter.config.settings import SETTINGS
from arbiter.infra.memory_store import get_memory_store
from arbiter.infra.benchmark_store import get_benchmark_store
from arbiter.infra.db import save_iteration_sync, save_memory_entry_sync, save_run_sync
from arbiter.infra.structured_logging import get_logger

logger = get_logger(__name__)


class IterationEngine:
    """
    Runs the iterative improvement loop.
    No UI logic here — pure orchestration.
    """

    def __init__(
        self,
        registry: PromptRegistry,
        auto_mode: bool = True,
        target_score: float = 8.0,
        max_iterations: int = 5,
        stable_mode: bool = False,
        benchmark_mode: bool = False,
        on_iteration_complete=None,
    ):
        self.runner    = AgentRunner(registry)
        self.registry  = registry
        self.scorer    = Scorer()
        self.stopper   = Stopper(
            max_iterations=max_iterations,
            target_score=target_score,
            auto_mode=auto_mode,
        )
        self.optimizer = LearningOptimizer()
        self.preflight = PreflightValidator()
        self.verifier = FinalVerifier()
        self.memory = get_memory_store()
        self.benchmarks = get_benchmark_store()
        self.formatter = ResultFormatter()
        self.stable_mode = stable_mode
        self.benchmark_mode = benchmark_mode
        # Optional callback: on_iteration_complete(state, record) for UI updates
        self.on_iteration_complete = on_iteration_complete

    def execute(self, state: ArbiterState, manual_override: str = "") -> ArbiterResult:
        stop, reason = False, ""
        run_id = f"run-{uuid4().hex[:12]}"

        while not stop:
            state.iteration += 1
            self.runner.current_iteration = state.iteration
            logger.info(
                "iteration_started",
                extra={"run_id": run_id, "iteration": state.iteration},
            )
            recommendations = self.optimizer.optimize(state)

            # Context for model selector
            context = {
                "last_tech_score": state.last_tech_score,
                "force_quality":   recommendations.get("architect_model") == "gpt-4o" and not self.stable_mode,
                "stable_mode": self.stable_mode,
                "iteration": state.iteration,
            }

            # ── 1. Build history string ──────────────────────
            history_str = self.registry.build_architect_history(
                state,
                manual_override=manual_override,
            )
            if recommendations.get("hint"):
                history_str = (
                    f"OPTIMIZER DIRECTIVE:\n{recommendations['hint']}\n\n"
                    + history_str
                ).strip()

            # ── 2. Architect ─────────────────────────────────
            proposal, arch_model = self.runner.run_architect(
                state.current_task,
                history=history_str,
                context=context,
            )
            state.track_cost("Architect", self.runner.latest_call_cost("Architect", arch_model))
            state.record_model_usage("Architect", arch_model, self.runner.latest_call_metadata("Architect"))

            proposal_error = BaseAgent.error_payload(proposal)
            if proposal_error and proposal_error.get("provider_error"):
                logger.warning(
                    "architect_provider_blocked",
                    extra={
                        "run_id": run_id,
                        "iteration": state.iteration,
                        "model": arch_model,
                        "provider": proposal_error.get("provider", ""),
                    },
                )
                state.current_solution = ""
                state.add_message(
                    "Architect",
                    (
                        "Architect generation was blocked by a provider/model issue.\n\n"
                        f"{proposal_error.get('critique', 'Provider error.')}\n\n"
                        f"{proposal_error.get('fix_suggestion', 'Retry later or use a different model.')}"
                    ),
                )
                record = IterationRecord(
                    iter=state.iteration,
                    tech=1,
                    logic=1,
                    avg=1.0,
                    validity_status="PROVIDER LIMITED",
                    score_status="diagnostic",
                    review_confidence="low",
                    verification_status="BLOCKED",
                    verification_score=0.0,
                    verification_summary="Verification was blocked because a provider or model failed during the review chain. This is a process failure, not a confirmed content failure.",
                    verification_checks=[{"name": "provider_gate", "status": "fail", "detail": "Architect generation was blocked by a provider issue."}],
                    ship_readiness="BLOCKED",
                    tech_critique=proposal_error.get("critique", "Architect provider error."),
                    logic_critique="Architect generation did not complete, so no logic review was run.",
                    fix=proposal_error.get("fix_suggestion", "Retry later or switch models."),
                    solution="",
                    preflight_issues=["Architect could not produce a solution because the selected and fallback models were unavailable or rate-limited."],
                    tech_issues=[proposal_error.get("critique", "Architect provider error.")],
                    logic_issues=[],
                    architect_model=arch_model,
                    tech_model="",
                    logic_model="",
                )
                state.add_iteration(record)
                memory_entry = self.memory.record_iteration(
                    task_mode=state.task_mode,
                    task_text=state.current_task or state.user_input,
                    iteration=record.iter,
                    avg_score=record.avg,
                    preflight_issues=record.preflight_issues,
                    tech_issues=record.tech_issues,
                    logic_issues=record.logic_issues,
                    tech_repair_contract=[],
                    logic_repair_contract=[],
                    architect_model=record.architect_model,
                    tech_model=record.tech_model,
                    logic_model=record.logic_model,
                    validity_status=record.validity_status,
                    score_status=record.score_status,
                    review_confidence=record.review_confidence,
                    verification_status=record.verification_status,
                    verification_score=record.verification_score,
                    verification_summary=record.verification_summary,
                    ship_readiness=record.ship_readiness,
                    run_id=run_id,
                    source_trace={
                        "architect_model": record.architect_model,
                        "validity_status": record.validity_status,
                        "score_status": record.score_status,
                        "iteration": record.iter,
                    },
                )
                record.memory_status = memory_entry.get("memory_status", "ACCEPT")
                record.memory_consensus_score = memory_entry.get("consensus_score", 0.0)
                record.memory_reasons = memory_entry.get("memory_reasons", [])
                record.related_memory_ids = memory_entry.get("related_memory_ids", [])
                if state.iteration_history:
                    state.iteration_history[-1]["memory_status"] = record.memory_status
                    state.iteration_history[-1]["memory_consensus_score"] = record.memory_consensus_score
                    state.iteration_history[-1]["memory_reasons"] = record.memory_reasons
                    state.iteration_history[-1]["related_memory_ids"] = record.related_memory_ids
                save_memory_entry_sync(memory_entry)
                self._persist_iteration_record(run_id, record)
                stop = True
                reason = proposal_error.get("fix_suggestion", "Architect provider error.")
                break

            preflight_issues = []
            if SETTINGS.enable_preflight:
                validation = self.preflight.validate(state.task_mode, state.current_task, proposal)
                preflight_issues = validation.issues

            if preflight_issues and SETTINGS.allow_repair_retry:
                logger.info(
                    "preflight_repair_triggered",
                    extra={
                        "run_id": run_id,
                        "iteration": state.iteration,
                        "issue_count": len(preflight_issues),
                    },
                )
                state.preflight_events += 1
                repair_prompt = self.preflight.build_repair_prompt(
                    state.current_task,
                    proposal,
                    preflight_issues,
                )
                proposal, repair_model = self.runner.run_repair_round(
                    repair_prompt,
                    history=history_str,
                    context={**context, "force_quality": True},
                )
                state.track_cost("Architect", self.runner.latest_call_cost("Architect", repair_model))
                state.record_model_usage("Architect Repair", repair_model, self.runner.latest_call_metadata("Architect"))
                state.repair_events += 1
                validation = self.preflight.validate(state.task_mode, state.current_task, proposal)
                preflight_issues = validation.issues

            state.current_solution = proposal
            state.add_message("Architect", proposal)

            if preflight_issues:
                logger.warning(
                    "preflight_failed",
                    extra={
                        "run_id": run_id,
                        "iteration": state.iteration,
                        "issue_count": len(preflight_issues),
                    },
                )
                t_score = 1
                l_score = 1
                avg_score = 1.0
                critic_overlap = 0.0
                critic_redundancy = False
                t_res = {
                    "critique": "Preflight validation failed before critic execution.",
                    "fix_suggestion": "Repair the listed preflight issues and return a complete corrected solution.",
                }
                l_res = {
                    "critique": "Preflight validation failed before critic execution.",
                    "fix_suggestion": "Repair the listed preflight issues and return a complete corrected solution.",
                }
                tech_model = ""
                logic_model = ""
                janitor_report = {}

                if SETTINGS.allow_diagnostic_critics_on_preflight_fail:
                    diagnostic_context = {**context, "force_quality": False}
                    t_res, tech_model, l_res, logic_model = self._run_initial_critics(
                        proposal,
                        diagnostic_context,
                        run_id=run_id,
                        iteration=state.iteration,
                    )
                    self._record_role_call(state, "Tech Critic", "Tech Critic", tech_model)
                    self._record_role_call(state, "Logic Critic", "Logic Critic", logic_model)
                    critic_overlap = self._critic_overlap(t_res, l_res)
                    critic_redundancy = self._should_trigger_critic_rerun(t_res, l_res, critic_overlap)
                    if critic_redundancy:
                        extra_instruction = (
                            "You are the Logic Critic. Do NOT repeat the technical review. "
                            "Focus only on missing requirements, flow gaps, contradictions, business-rule coverage, "
                            "unsupported assumptions, and end-to-end completeness. "
                            "Do not talk about generic try-catch, API exception handling, or code-level implementation defects "
                            "unless they directly create a distinct logical gap."
                        )
                        rerun_logic, rerun_logic_model = self.runner.run_logic_critic(
                            proposal,
                            diagnostic_context,
                            extra_instruction=extra_instruction,
                        )
                        rerun_overlap = self._critic_overlap(t_res, rerun_logic)
                        self._record_role_call(state, "Logic Critic", "Logic Critic Recheck", rerun_logic_model)
                        if rerun_overlap < critic_overlap:
                            l_res = rerun_logic
                            logic_model = rerun_logic_model
                            critic_overlap = rerun_overlap
                        critic_redundancy = self._should_trigger_critic_rerun(t_res, l_res, critic_overlap)
                    t_score = t_res.get("score", 1)
                    l_score = l_res.get("score", 1)
                    avg_score = self.scorer.compute(t_res, l_res, task_mode=state.task_mode)
                    janitor_payload = self._build_janitor_payload(state, proposal, preflight_issues, t_res, l_res)
                    janitor_report, janitor_model = self.runner.run_janitor(janitor_payload, context)
                    janitor_report = self._filter_janitor_report(janitor_report, preflight_issues, t_res, l_res)
                    state.record_model_usage("Janitor", janitor_model, self.runner.latest_call_metadata("Janitor"))
                    state.track_cost("Janitor", self.runner.latest_call_cost("Janitor", janitor_model))

                    preflight_html = self.formatter.preflight_diagnostic_html(
                        preflight_issues,
                        t_score,
                        l_score,
                        avg_score,
                        t_res,
                        l_res,
                    )
                    stop_reason = "Preflight failed after repair; completed one diagnostic critic pass."
                    fix_text = (
                        "Preflight: " + " | ".join(preflight_issues)
                        + f" || Tech: {t_res.get('fix_suggestion','')}"
                        + f" | Logic: {l_res.get('fix_suggestion','')}"
                    )
                    diagnostic_provider_error = bool(t_res.get("provider_error") or l_res.get("provider_error"))
                else:
                    preflight_html = self.formatter.preflight_blocked_html(preflight_issues)
                    stop_reason = "Preflight validation failed."
                    fix_text = "Repair the listed preflight issues and return a complete corrected solution."
                    diagnostic_provider_error = False

                state.add_message("Critics", preflight_html)
                record = IterationRecord(
                    iter=state.iteration,
                    tech=t_score,
                    logic=l_score,
                    avg=avg_score,
                    validity_status="DIAGNOSTIC ONLY",
                    score_status="diagnostic",
                    review_confidence="low" if (critic_redundancy or diagnostic_provider_error) else "normal",
                    verification_status="BLOCKED",
                    verification_score=0.0,
                    verification_summary="Structural preflight issues blocked final verification.",
                    verification_checks=[{"name": "preflight_gate", "status": "fail", "detail": "Preflight issues must be repaired before a clean verification pass."}],
                    ship_readiness="BLOCKED",
                    critic_overlap=critic_overlap if SETTINGS.allow_diagnostic_critics_on_preflight_fail else 0.0,
                    critic_redundancy=critic_redundancy if SETTINGS.allow_diagnostic_critics_on_preflight_fail else False,
                    tech_confirmed_defects=t_res.get("confirmed_defects", []),
                    tech_risks=t_res.get("risks", []),
                    tech_improvements=t_res.get("improvements", []),
                    logic_confirmed_defects=l_res.get("confirmed_defects", []),
                    logic_risks=l_res.get("risks", []),
                    logic_improvements=l_res.get("improvements", []),
                    tech_critique=t_res.get("critique", "Preflight validation failed before critic execution."),
                    logic_critique=l_res.get("critique", "Preflight validation failed before critic execution."),
                    fix=fix_text,
                    solution=proposal,
                    preflight_issues=preflight_issues,
                    tech_issues=t_res.get("issues", []),
                    logic_issues=l_res.get("issues", []),
                    tech_repair_contract=t_res.get("repair_contract", []),
                    logic_repair_contract=l_res.get("repair_contract", []),
                    janitor_summary=janitor_report.get("summary", ""),
                    janitor_primary_subsystem=janitor_report.get("primary_subsystem", ""),
                    janitor_resolved=janitor_report.get("resolved", []),
                    janitor_pending=janitor_report.get("pending", []),
                    janitor_regressed=janitor_report.get("regressed", []),
                    janitor_preserve=janitor_report.get("preserve", []),
                    janitor_repair_brief=janitor_report.get("repair_brief", []),
                    architect_model=arch_model,
                    tech_model=tech_model,
                    logic_model=logic_model,
                )
                state.add_iteration(record)
                memory_entry = self.memory.record_iteration(
                    task_mode=state.task_mode,
                    task_text=state.current_task or state.user_input,
                    iteration=record.iter,
                    avg_score=record.avg,
                    preflight_issues=record.preflight_issues,
                    tech_issues=record.tech_confirmed_defects or record.tech_issues,
                    logic_issues=record.logic_confirmed_defects or record.logic_issues,
                    tech_repair_contract=record.tech_repair_contract,
                    logic_repair_contract=record.logic_repair_contract,
                    architect_model=record.architect_model,
                    tech_model=record.tech_model,
                    logic_model=record.logic_model,
                    validity_status=record.validity_status,
                    score_status=record.score_status,
                    review_confidence=record.review_confidence,
                    verification_status=record.verification_status,
                    verification_score=record.verification_score,
                    verification_summary=record.verification_summary,
                    ship_readiness=record.ship_readiness,
                    run_id=run_id,
                    source_trace={
                        "architect_model": record.architect_model,
                        "tech_model": record.tech_model,
                        "logic_model": record.logic_model,
                        "validity_status": record.validity_status,
                        "score_status": record.score_status,
                        "iteration": record.iter,
                    },
                )
                record.memory_status = memory_entry.get("memory_status", "ACCEPT")
                record.memory_consensus_score = memory_entry.get("consensus_score", 0.0)
                record.memory_reasons = memory_entry.get("memory_reasons", [])
                record.related_memory_ids = memory_entry.get("related_memory_ids", [])
                if state.iteration_history:
                    state.iteration_history[-1]["memory_status"] = record.memory_status
                    state.iteration_history[-1]["memory_consensus_score"] = record.memory_consensus_score
                    state.iteration_history[-1]["memory_reasons"] = record.memory_reasons
                    state.iteration_history[-1]["related_memory_ids"] = record.related_memory_ids
                save_memory_entry_sync(memory_entry)
                self._persist_iteration_record(run_id, record)
                stop = True
                reason = stop_reason
                break

            # ── 3. Critics (sequential — parallel optional) ──
            t_res, t_model, l_res, l_model = self._run_initial_critics(
                proposal,
                context,
                run_id=run_id,
                iteration=state.iteration,
            )
            self._record_role_call(state, "Tech Critic", "Tech Critic", t_model)
            self._record_role_call(state, "Logic Critic", "Logic Critic", l_model)

            critic_overlap = self._critic_overlap(t_res, l_res)
            critic_redundancy = self._should_trigger_critic_rerun(t_res, l_res, critic_overlap)
            if critic_redundancy:
                extra_instruction = (
                    "You are the Logic Critic. Do NOT repeat the technical review. "
                    "Focus only on missing requirements, flow gaps, contradictions, business-rule coverage, "
                    "unsupported assumptions, and end-to-end completeness. "
                    "Do not talk about generic try-catch, API exception handling, or code-level implementation defects "
                    "unless they directly create a distinct logical gap."
                )
                rerun_logic, rerun_logic_model = self.runner.run_logic_critic(
                    proposal,
                    context,
                    extra_instruction=extra_instruction,
                )
                rerun_overlap = self._critic_overlap(t_res, rerun_logic)
                self._record_role_call(state, "Logic Critic", "Logic Critic Recheck", rerun_logic_model)
                if rerun_overlap < critic_overlap:
                    l_res = rerun_logic
                    l_model = rerun_logic_model
                    critic_overlap = rerun_overlap
                critic_redundancy = self._should_trigger_critic_rerun(t_res, l_res, critic_overlap)

            if SETTINGS.critic_debate_enabled:
                debate, debate_model = self.runner.run_critic_debate(proposal, t_res, l_res)
                state.track_cost("Critic Debate", self.runner.latest_call_cost("Critic Debate", debate_model))
                state.record_model_usage("Critic Debate", debate_model, self.runner.latest_call_metadata("Critic Debate"))
            else:
                debate = {}

            janitor_payload = self._build_janitor_payload(state, proposal, preflight_issues, t_res, l_res)
            janitor_report, janitor_model = self.runner.run_janitor(janitor_payload, context)
            janitor_report = self._filter_janitor_report(janitor_report, preflight_issues, t_res, l_res)
            state.record_model_usage("Janitor", janitor_model, self.runner.latest_call_metadata("Janitor"))
            state.track_cost("Janitor", self.runner.latest_call_cost("Janitor", janitor_model))

            # ── 4. Score ─────────────────────────────────────
            raw_avg_score = self.scorer.compute(t_res, l_res, task_mode=state.task_mode)
            t_score   = t_res.get("score", 1)
            l_score   = l_res.get("score", 1)
            provider_error = bool(t_res.get("provider_error") or l_res.get("provider_error"))
            validity_status = "REVIEW DEGRADED" if provider_error else "VALID"
            score_status = "diagnostic" if provider_error else "final"
            verification = self._run_verification(
                state=state,
                proposal=proposal,
                preflight_issues=preflight_issues,
                tech_result=t_res,
                logic_result=l_res,
                provider_error=provider_error,
            )
            avg_score = self._calibrate_score(raw_avg_score, verification)
            review_confidence = self._derive_review_confidence(
                critic_redundancy=critic_redundancy,
                provider_error=provider_error,
                verification=verification,
            )
            ship_readiness = self._derive_ship_readiness(
                validity_status=validity_status,
                verification=verification,
                tech_result=t_res,
                logic_result=l_res,
                review_confidence=review_confidence,
            )
            logger.info(
                "iteration_scored",
                extra={
                    "run_id": run_id,
                    "iteration": state.iteration,
                    "score": avg_score,
                    "verification_status": verification.status,
                    "ship_readiness": ship_readiness,
                },
            )

            # ── 5. Build critique message ────────────────────
            critique_content = self._build_critique_html(
                t_score,
                l_score,
                avg_score,
                t_res,
                l_res,
                debate,
                raw_avg=raw_avg_score,
            )
            state.add_message("Critics", critique_content)

            # ── 6. Save iteration record ─────────────────────
            record = IterationRecord(
                iter=state.iteration,
                tech=t_score,
                logic=l_score,
                avg=avg_score,
                validity_status=validity_status,
                score_status=score_status,
                review_confidence=review_confidence,
                verification_status=verification.status,
                verification_score=verification.score,
                verification_summary=verification.summary,
                verification_checks=verification.checks,
                ship_readiness=ship_readiness,
                critic_overlap=critic_overlap,
                critic_redundancy=critic_redundancy,
                tech_confirmed_defects=t_res.get("confirmed_defects", []),
                tech_risks=t_res.get("risks", []),
                tech_improvements=t_res.get("improvements", []),
                logic_confirmed_defects=l_res.get("confirmed_defects", []),
                logic_risks=l_res.get("risks", []),
                logic_improvements=l_res.get("improvements", []),
                tech_critique=t_res.get("critique", ""),
                logic_critique=l_res.get("critique", ""),
                fix=f"Tech: {t_res.get('fix_suggestion','')} | Logic: {l_res.get('fix_suggestion','')}",
                solution=proposal,
                raw_avg_score=raw_avg_score,
                tech_issues=t_res.get("issues", []),
                logic_issues=l_res.get("issues", []),
                tech_repair_contract=t_res.get("repair_contract", []),
                logic_repair_contract=l_res.get("repair_contract", []),
                janitor_summary=janitor_report.get("summary", ""),
                janitor_primary_subsystem=janitor_report.get("primary_subsystem", ""),
                janitor_resolved=janitor_report.get("resolved", []),
                janitor_pending=janitor_report.get("pending", []),
                janitor_regressed=janitor_report.get("regressed", []),
                janitor_preserve=janitor_report.get("preserve", []),
                janitor_repair_brief=janitor_report.get("repair_brief", []),
                architect_model=arch_model,
                tech_model=t_model,
                logic_model=l_model,
            )
            state.add_iteration(record)
            memory_entry = self.memory.record_iteration(
                task_mode=state.task_mode,
                task_text=state.current_task or state.user_input,
                iteration=record.iter,
                avg_score=record.avg,
                preflight_issues=record.preflight_issues,
                tech_issues=record.tech_confirmed_defects or record.tech_issues,
                logic_issues=record.logic_confirmed_defects or record.logic_issues,
                tech_repair_contract=record.tech_repair_contract,
                logic_repair_contract=record.logic_repair_contract,
                architect_model=record.architect_model,
                tech_model=record.tech_model,
                logic_model=record.logic_model,
                validity_status=record.validity_status,
                score_status=record.score_status,
                review_confidence=record.review_confidence,
                verification_status=record.verification_status,
                verification_score=record.verification_score,
                verification_summary=record.verification_summary,
                ship_readiness=record.ship_readiness,
                run_id=run_id,
                source_trace={
                    "architect_model": record.architect_model,
                    "tech_model": record.tech_model,
                    "logic_model": record.logic_model,
                    "validity_status": record.validity_status,
                    "score_status": record.score_status,
                    "iteration": record.iter,
                },
            )
            record.memory_status = memory_entry.get("memory_status", "ACCEPT")
            record.memory_consensus_score = memory_entry.get("consensus_score", 0.0)
            record.memory_reasons = memory_entry.get("memory_reasons", [])
            record.related_memory_ids = memory_entry.get("related_memory_ids", [])
            if state.iteration_history:
                state.iteration_history[-1]["memory_status"] = record.memory_status
                state.iteration_history[-1]["memory_consensus_score"] = record.memory_consensus_score
                state.iteration_history[-1]["memory_reasons"] = record.memory_reasons
                state.iteration_history[-1]["related_memory_ids"] = record.related_memory_ids
            save_memory_entry_sync(memory_entry)
            self._persist_iteration_record(run_id, record)

            # Optional UI callback
            if self.on_iteration_complete:
                self.on_iteration_complete(state, record)

            # ── 7. Stop check ────────────────────────────────
            stop, reason = self.stopper.should_stop(state)
            logger.info(
                "iteration_finished",
                extra={
                    "run_id": run_id,
                    "iteration": state.iteration,
                    "score": state.last_avg_score,
                    "stop": stop,
                },
            )

        latest_validity = state.iteration_history[-1]["validity_status"] if state.iteration_history else "IDLE"
        latest_score_status = state.iteration_history[-1].get("score_status", "final") if state.iteration_history else "final"
        latest_verification_status = state.iteration_history[-1].get("verification_status", "UNVERIFIED") if state.iteration_history else "UNVERIFIED"
        latest_ship_readiness = state.iteration_history[-1].get("ship_readiness", "UNASSESSED") if state.iteration_history else "UNASSESSED"
        logger.info(
            "run_completed",
            extra={
                "run_id": run_id,
                "iteration": state.iteration,
                "score": state.best_iteration["avg"] if state.best_iteration else state.last_avg_score,
                "validity_status": latest_validity,
            },
        )
        self.benchmarks.record_run(
            task_mode=state.task_mode,
            run_id=run_id,
            best_score=state.best_iteration["avg"] if state.best_iteration else state.last_avg_score,
            iteration_count=state.iteration,
            total_cost=state.costs.get("Total", 0.0),
            validity_status=latest_validity,
            score_status=latest_score_status,
            verification_status=latest_verification_status,
            ship_readiness=latest_ship_readiness,
            stop_reason=reason,
            preflight_events=state.preflight_events,
            repair_events=state.repair_events,
            benchmark_mode=state.benchmark_mode,
            benchmark_strategy=state.benchmark_strategy,
            benchmark_pack=state.benchmark_pack,
            benchmark_case_id=state.benchmark_case_id,
            benchmark_case_title=state.benchmark_case_title,
        )
        self._persist_run_summary(
            run_id=run_id,
            state=state,
            reason=reason,
            latest_validity=latest_validity,
            latest_verification_status=latest_verification_status,
            latest_ship_readiness=latest_ship_readiness,
        )

        return ArbiterResult(
            best_solution=state.best_solution or state.current_solution,
            best_score=state.best_iteration["avg"] if state.best_iteration else state.last_avg_score,
            iteration_count=state.iteration,
            best_iteration=state.best_iteration,
            costs=state.costs,
            messages=state.messages,
            iteration_history=state.iteration_history,
            debug_info={
                "stop_reason": reason,
                "rewrite_mode": state.rewrite_mode,
                "stable_mode": state.stable_mode,
                "tech_stall_count": state.tech_stall_count,
                "score_plateau_count": state.score_plateau_count,
                "tech_regression_count": state.tech_regression_count,
                "recent_low_tech_count": state.recent_low_tech_count,
                "tech_oscillation_count": state.tech_oscillation_count,
                "preflight_events": state.preflight_events,
                "repair_events": state.repair_events,
                "unresolved_issues": state.unresolved_issues,
                "model_usage": state.model_usage,
                "memory_stats": self.memory.stats(),
                "benchmark_stats": self.benchmarks.stats(),
                "benchmark_by_task_mode": self.benchmarks.by_task_mode(),
                "benchmark_by_strategy": self.benchmarks.by_strategy(),
                "benchmark_by_case": self.benchmarks.by_case(),
                "recent_benchmarks": self.benchmarks.recent_runs(8),
                "decision_trace": self.runner.decision_log.to_dict_list(),
                "current_solution": state.current_solution,
                "latest_janitor_report": state.latest_janitor_report,
                "latest_result_status": latest_validity,
                "run_id": run_id,
            },
        )

    @staticmethod
    def _build_janitor_payload(state: ArbiterState, proposal: str, preflight_issues: list, t_res: dict, l_res: dict) -> str:
        unresolved = getattr(state, "unresolved_issues", {"tech": [], "logic": []})
        tech_defects = (t_res.get("confirmed_defects") or [])[:4]
        logic_defects = (l_res.get("confirmed_defects") or [])[:4]
        tech_fix = str(t_res.get("fix_suggestion", "") or "").strip()[:120]
        logic_fix = str(l_res.get("fix_suggestion", "") or "").strip()[:120]
        latest_solution = str(proposal or "").strip()
        if len(latest_solution) > 800:
            latest_solution = latest_solution[:800].rstrip() + "\n[truncated solution excerpt]"
        tech_contract = [str(item).strip() for item in (t_res.get("repair_contract") or []) if str(item).strip()][:4]
        logic_contract = [str(item).strip() for item in (l_res.get("repair_contract") or []) if str(item).strip()][:4]
        unresolved_tech = [str(item).strip() for item in (unresolved.get("tech") or []) if str(item).strip()][:6]
        unresolved_logic = [str(item).strip() for item in (unresolved.get("logic") or []) if str(item).strip()][:6]

        def section(title: str, items: list[str], empty_text: str = "- None") -> str:
            if not items:
                return f"{title}:\n{empty_text}\n"
            return title + ":\n" + "\n".join(f"- {item}" for item in items) + "\n"

        return (
            "TASK MODE:\n"
            f"{state.task_mode}\n\n"
            "LATEST SOLUTION:\n"
            f"{latest_solution}\n\n"
            + section("PREFLIGHT ISSUES", [str(item).strip() for item in preflight_issues if str(item).strip()])
            + "\n"
            + section("TECH CONFIRMED DEFECTS", tech_defects)
            + f"TECH FIX SUGGESTION:\n- {tech_fix or 'No fix suggestion.'}\n"
            + section("TECH REPAIR CONTRACT", tech_contract)
            + "\n"
            + section("LOGIC CONFIRMED DEFECTS", logic_defects)
            + f"LOGIC FIX SUGGESTION:\n- {logic_fix or 'No fix suggestion.'}\n"
            + section("LOGIC REPAIR CONTRACT", logic_contract)
            + "\n"
            + section("PREVIOUS UNRESOLVED TECH ISSUES", unresolved_tech)
            + section("PREVIOUS UNRESOLVED LOGIC ISSUES", unresolved_logic)
        )

    @staticmethod
    def _persist_iteration_record(run_id: str, record: IterationRecord) -> None:
        save_iteration_sync(
            run_id,
            {
                "iteration_number": record.iter,
                "tech_score": record.tech,
                "logic_score": record.logic,
                "avg_score": record.avg,
                "ship_readiness": record.ship_readiness,
                "verification_status": record.verification_status,
                "verification_score": record.verification_score,
                "architect_model": record.architect_model,
                "tech_model": record.tech_model,
                "logic_model": record.logic_model,
                "preflight_issues": list(record.preflight_issues or []),
                "tech_issues": list(record.tech_confirmed_defects or record.tech_issues or []),
                "logic_issues": list(record.logic_confirmed_defects or record.logic_issues or []),
                "janitor_summary": record.janitor_summary,
                "solution": record.solution,
            },
        )

    @staticmethod
    def _persist_run_summary(
        run_id: str,
        state: ArbiterState,
        reason: str,
        latest_validity: str,
        latest_verification_status: str,
        latest_ship_readiness: str,
    ) -> None:
        save_run_sync(
            {
                "id": run_id,
                "task_mode": state.task_mode,
                "user_input": state.user_input,
                "best_score": state.best_iteration["avg"] if state.best_iteration else state.last_avg_score,
                "best_solution": state.best_solution or state.current_solution,
                "iteration_count": state.iteration,
                "total_cost_usd": state.costs.get("Total", 0.0),
                "stop_reason": reason,
                "ship_readiness": latest_ship_readiness,
                "verification_status": latest_verification_status,
                "validity_status": latest_validity,
                "run_metadata": {
                    "stable_mode": state.stable_mode,
                    "benchmark_mode": state.benchmark_mode,
                    "benchmark_strategy": state.benchmark_strategy,
                    "benchmark_pack": state.benchmark_pack,
                    "benchmark_case_id": state.benchmark_case_id,
                    "benchmark_case_title": state.benchmark_case_title,
                    "model_usage": state.model_usage[-25:],
                    "preflight_events": state.preflight_events,
                    "repair_events": state.repair_events,
                },
            }
        )

    @staticmethod
    def _critic_timeout_result(role: str, timeout_seconds: int) -> dict:
        critique = f"{role} timed out after {timeout_seconds}s before returning a review."
        fix = "Retry the critic pass or switch to a more reliable model."
        return {
            "score": 1,
            "critique": critique,
            "fix_suggestion": fix,
            "confirmed_defects": [],
            "risks": [],
            "improvements": [],
            "issues": [critique],
            "repair_contract": [fix],
            "provider_error": True,
            "error_type": "timeout",
        }

    @staticmethod
    def _critic_execution_error_result(role: str, exc: Exception) -> dict:
        message = f"{role} failed before returning a review: {str(exc).strip() or 'unknown execution error'}"
        fix = "Retry the critic pass or switch to a different model."
        return {
            "score": 1,
            "critique": message,
            "fix_suggestion": fix,
            "confirmed_defects": [],
            "risks": [],
            "improvements": [],
            "issues": [message],
            "repair_contract": [fix],
            "provider_error": True,
            "error_type": "execution_error",
        }

    @staticmethod
    def _critic_failure_metadata(role: str, error_type: str, latency_ms: float = 0.0) -> dict:
        return {
            "provider": "",
            "model": "",
            "agent_name": role,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "cost_method": error_type,
            "cached": False,
            "latency_ms": latency_ms,
            "error_type": error_type,
        }

    def _record_role_call(self, state: ArbiterState, cost_role: str, usage_role: str, model: str) -> None:
        state.track_cost(cost_role, self.runner.latest_call_cost(cost_role, model))
        state.record_model_usage(usage_role, model, self.runner.latest_call_metadata(cost_role))

    def _run_initial_critics(
        self,
        proposal: str,
        context: dict,
        run_id: str,
        iteration: int,
    ) -> tuple[dict, str, dict, str]:
        started_at = time.perf_counter()
        if not SETTINGS.parallel_critics:
            tech_result, tech_model = self.runner.run_tech_critic(proposal, context)
            logic_result, logic_model = self.runner.run_logic_critic(proposal, context)
            return tech_result, tech_model, logic_result, logic_model

        timeout_seconds = max(1, int(getattr(SETTINGS, "critic_timeout_seconds", 45) or 45))
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="arbiter-critic")
        tech_future = executor.submit(self.runner.run_tech_critic, proposal, context)
        logic_future = executor.submit(self.runner.run_logic_critic, proposal, context)

        try:
            try:
                tech_result, tech_model = tech_future.result(timeout=timeout_seconds)
            except FuturesTimeoutError:
                tech_result, tech_model = self._critic_timeout_result("Tech Critic", timeout_seconds), ""
                self.runner.set_call_metadata(
                    "Tech Critic",
                    self._critic_failure_metadata("Tech Critic", "timeout", timeout_seconds * 1000),
                )
                logger.warning(
                    "critic_timeout",
                    extra={
                        "run_id": run_id,
                        "iteration": iteration,
                        "agent_name": "Tech Critic",
                        "latency_ms": timeout_seconds * 1000,
                    },
                )
            except Exception as exc:
                tech_result, tech_model = self._critic_execution_error_result("Tech Critic", exc), ""
                self.runner.set_call_metadata(
                    "Tech Critic",
                    self._critic_failure_metadata("Tech Critic", "execution_error"),
                )
                logger.warning(
                    "critic_execution_error",
                    extra={
                        "run_id": run_id,
                        "iteration": iteration,
                        "agent_name": "Tech Critic",
                    },
                    exc_info=exc,
                )

            try:
                logic_result, logic_model = logic_future.result(timeout=timeout_seconds)
            except FuturesTimeoutError:
                logic_result, logic_model = self._critic_timeout_result("Logic Critic", timeout_seconds), ""
                self.runner.set_call_metadata(
                    "Logic Critic",
                    self._critic_failure_metadata("Logic Critic", "timeout", timeout_seconds * 1000),
                )
                logger.warning(
                    "critic_timeout",
                    extra={
                        "run_id": run_id,
                        "iteration": iteration,
                        "agent_name": "Logic Critic",
                        "latency_ms": timeout_seconds * 1000,
                    },
                )
            except Exception as exc:
                logic_result, logic_model = self._critic_execution_error_result("Logic Critic", exc), ""
                self.runner.set_call_metadata(
                    "Logic Critic",
                    self._critic_failure_metadata("Logic Critic", "execution_error"),
                )
                logger.warning(
                    "critic_execution_error",
                    extra={
                        "run_id": run_id,
                        "iteration": iteration,
                        "agent_name": "Logic Critic",
                    },
                    exc_info=exc,
                )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        wall_time_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
        tech_latency_ms = float(self.runner.latest_call_metadata("Tech Critic").get("latency_ms", 0.0) or 0.0)
        logic_latency_ms = float(self.runner.latest_call_metadata("Logic Critic").get("latency_ms", 0.0) or 0.0)
        serial_estimate_ms = round(tech_latency_ms + logic_latency_ms, 2)
        latency_saved_ms = round(max(0.0, serial_estimate_ms - wall_time_ms), 2)
        logger.info(
            "parallel_critics_completed",
            extra={
                "run_id": run_id,
                "iteration": iteration,
                "critic_wall_time_ms": wall_time_ms,
                "serial_estimate_ms": serial_estimate_ms,
                "latency_saved_ms": latency_saved_ms,
            },
        )
        return tech_result, tech_model, logic_result, logic_model

    def _run_verification(
        self,
        state: ArbiterState,
        proposal: str,
        preflight_issues: list,
        tech_result: dict,
        logic_result: dict,
        provider_error: bool,
    ) -> VerificationResult:
        if not SETTINGS.final_validation_enabled:
            return VerificationResult(
                status="UNVERIFIED",
                confidence="normal",
                score=0.0,
                summary="Deterministic verification is disabled for this environment.",
                checks=[],
            )
        return self.verifier.verify(
            task_mode=state.task_mode,
            task_text=state.current_task or state.user_input,
            solution=proposal,
            preflight_issues=preflight_issues,
            tech_confirmed_defects=tech_result.get("confirmed_defects", []),
            logic_confirmed_defects=logic_result.get("confirmed_defects", []),
            provider_error=provider_error,
        )

    @staticmethod
    def _calibrate_score(raw_avg_score: float, verification: VerificationResult) -> float:
        base = float(raw_avg_score or 0.0)
        if verification.status == "VERIFIED" and verification.score >= 0.85:
            return round(base, 2)

        if verification.status == "VERIFIED":
            return round(max(1.0, base * 0.97), 2)

        verification_equivalent = float(verification.score or 0.0) * 10.0

        if verification.status == "CAUTION":
            blended = round((base * 0.75) + (verification_equivalent * 0.25), 2)
            return max(1.0, min(blended, 8.0))
        if verification.status == "FAILED":
            blended = round((base * 0.60) + (verification_equivalent * 0.40), 2)
            return max(1.0, min(blended, 6.0))
        if verification.status == "BLOCKED":
            blended = round((base * 0.50) + (verification_equivalent * 0.50), 2)
            return max(1.0, min(blended, 5.0))
        return max(1.0, min(10.0, round(base, 2)))

    @staticmethod
    def _derive_review_confidence(critic_redundancy: bool, provider_error: bool, verification: VerificationResult) -> str:
        if provider_error or verification.status in {"FAILED", "BLOCKED"}:
            return "low"
        if critic_redundancy or verification.status == "CAUTION":
            return "guarded"
        if verification.status == "VERIFIED":
            return "high"
        return "normal"

    @staticmethod
    def _derive_ship_readiness(
        validity_status: str,
        verification: VerificationResult,
        tech_result: dict,
        logic_result: dict,
        review_confidence: str,
    ) -> str:
        confirmed = len(tech_result.get("confirmed_defects", []) or []) + len(logic_result.get("confirmed_defects", []) or [])
        if validity_status != "VALID" or verification.status in {"FAILED", "BLOCKED"}:
            return "BLOCKED"
        if confirmed > 0:
            return "NEEDS REVIEW"
        if verification.status == "CAUTION" or review_confidence in {"guarded", "low"}:
            return "CLOSE"
        if verification.status == "VERIFIED" and review_confidence in {"high", "normal"}:
            return "READY"
        return "UNASSESSED"

    @staticmethod
    def _tokenize_text(text: str) -> set:
        tokens = re.findall(r"[a-z0-9_]+", str(text or "").lower())
        stopwords = {
            "the", "and", "for", "with", "that", "this", "from", "into", "your", "when",
            "then", "than", "have", "will", "what", "where", "which", "should", "could",
            "would", "there", "their", "about", "after", "before", "only", "also", "just",
            "does", "did", "not", "are", "was", "were", "been", "being", "them", "they",
            "issue", "issues", "logic", "technical", "audit", "solution",
        }
        return {token for token in tokens if len(token) > 2 and token not in stopwords}

    @classmethod
    def _matches_anchor(cls, item: str, anchors: list) -> bool:
        item_text = str(item or "").strip()
        if not item_text:
            return False
        item_tokens = cls._tokenize_text(item_text)
        for anchor in anchors:
            anchor_text = str(anchor or "").strip()
            if not anchor_text:
                continue
            if item_text.lower() in anchor_text.lower() or anchor_text.lower() in item_text.lower():
                return True
            anchor_tokens = cls._tokenize_text(anchor_text)
            if not item_tokens or not anchor_tokens:
                continue
            overlap = len(item_tokens & anchor_tokens) / len(item_tokens | anchor_tokens)
            if overlap >= 0.28:
                return True
        return False

    @classmethod
    def _filter_janitor_report(cls, janitor_report: dict, preflight_issues: list, t_res: dict, l_res: dict) -> dict:
        report = dict(janitor_report or {})
        anchors = list(preflight_issues or [])
        anchors.extend(t_res.get("confirmed_defects", []) or [])
        anchors.extend(l_res.get("confirmed_defects", []) or [])
        if not anchors:
            report["pending"] = []
            report["regressed"] = []
            if not (preflight_issues or t_res.get("confirmed_defects") or l_res.get("confirmed_defects")):
                report["repair_brief"] = []
            return report

        pending = [item for item in report.get("pending", []) if cls._matches_anchor(item, anchors)]
        regressed = [item for item in report.get("regressed", []) if cls._matches_anchor(item, anchors)]
        report["pending"] = pending[:6]
        report["regressed"] = regressed[:6]
        if not report["pending"] and not report["regressed"]:
            report["repair_brief"] = []
        else:
            report["repair_brief"] = list(report.get("repair_brief", []))[:6]
        return report

    @staticmethod
    def _normalize_issue_tokens(result: dict) -> set:
        text_parts = []
        text_parts.extend(result.get("confirmed_defects", []) or [])
        text_parts.extend(result.get("issues", []) or [])
        text_parts.append(result.get("critique", ""))
        raw = " ".join(str(part) for part in text_parts if str(part).strip()).lower()
        tokens = re.findall(r"[a-z0-9_]+", raw)
        stopwords = {
            "the", "and", "for", "with", "that", "this", "from", "into", "your", "when",
            "then", "than", "have", "will", "what", "where", "which", "should", "could",
            "would", "there", "their", "about", "after", "before", "only", "also", "just",
            "does", "did", "not", "are", "was", "were", "been", "being", "them", "they",
            "issue", "issues", "logic", "technical", "audit", "solution",
        }
        return {token for token in tokens if len(token) > 2 and token not in stopwords}

    @classmethod
    def _critic_overlap(cls, tech_result: dict, logic_result: dict) -> float:
        tech_tokens = cls._normalize_issue_tokens(tech_result)
        logic_tokens = cls._normalize_issue_tokens(logic_result)
        if not tech_tokens or not logic_tokens:
            return 0.0
        return len(tech_tokens & logic_tokens) / len(tech_tokens | logic_tokens)

    @staticmethod
    def _critics_in_same_redundancy_band(tech_result: dict, logic_result: dict) -> bool:
        tech_score = int(tech_result.get("score", 0) or 0)
        logic_score = int(logic_result.get("score", 0) or 0)
        return (tech_score <= 5 and logic_score <= 5) or (tech_score >= 7 and logic_score >= 7)

    @classmethod
    def _should_trigger_critic_rerun(
        cls,
        tech_result: dict,
        logic_result: dict,
        overlap: Optional[float] = None,
    ) -> bool:
        critic_overlap = float(cls._critic_overlap(tech_result, logic_result) if overlap is None else overlap)
        if critic_overlap < 0.72:
            return False
        if not SETTINGS.critic_redundancy_score_band_check:
            return True
        return cls._critics_in_same_redundancy_band(tech_result, logic_result)

    def _build_critique_html(
        self,
        t_score: int,
        l_score: int,
        avg: float,
        t_res: dict,
        l_res: dict,
        debate: Optional[dict] = None,
        raw_avg: Optional[float] = None,
    ) -> str:
        return self.formatter.critique_html(
            t_score=t_score,
            l_score=l_score,
            avg=avg,
            t_res=t_res,
            l_res=l_res,
            debate=debate,
            raw_avg=raw_avg,
        )
