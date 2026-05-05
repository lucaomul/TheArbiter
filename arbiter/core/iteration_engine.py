from typing import Optional
import re
from uuid import uuid4

from arbiter.models.state import ArbiterState, IterationRecord
from arbiter.models.result import ArbiterResult
from arbiter.core.agent_runner import AgentRunner
from arbiter.agents.base_agent import BaseAgent
from arbiter.core.scoring import Scorer
from arbiter.core.stopping import Stopper
from arbiter.core.learning.optimizer import LearningOptimizer
from arbiter.core.preflight import PreflightValidator
from arbiter.prompts.registry import PromptRegistry
from arbiter.config.settings import SETTINGS
from arbiter.infra.memory_store import get_memory_store


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
        self.memory = get_memory_store()
        self.stable_mode = stable_mode
        # Optional callback: on_iteration_complete(state, record) for UI updates
        self.on_iteration_complete = on_iteration_complete

    def execute(self, state: ArbiterState, manual_override: str = "") -> ArbiterResult:
        stop, reason = False, ""
        run_id = f"run-{uuid4().hex[:12]}"

        while not stop:
            state.iteration += 1
            recommendations = self.optimizer.optimize(state)

            # Context for model selector
            context = {
                "last_tech_score": state.last_tech_score,
                "force_quality":   recommendations.get("architect_model") == "gpt-4o" and not self.stable_mode,
                "stable_mode": self.stable_mode,
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
            state.track_cost("Architect", self.runner.model_cost(arch_model))
            state.record_model_usage("Architect", arch_model)

            proposal_error = BaseAgent.error_payload(proposal)
            if proposal_error and proposal_error.get("provider_error"):
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
                stop = True
                reason = proposal_error.get("fix_suggestion", "Architect provider error.")
                break

            preflight_issues = []
            if SETTINGS.enable_preflight:
                validation = self.preflight.validate(state.task_mode, state.current_task, proposal)
                preflight_issues = validation.issues

            if preflight_issues and SETTINGS.allow_repair_retry:
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
                state.track_cost("Architect", self.runner.model_cost(repair_model))
                state.record_model_usage("Architect Repair", repair_model)
                state.repair_events += 1
                validation = self.preflight.validate(state.task_mode, state.current_task, proposal)
                preflight_issues = validation.issues

            state.current_solution = proposal
            state.add_message("Architect", proposal)

            if preflight_issues:
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
                    t_res, tech_model = self.runner.run_tech_critic(proposal, {**context, "force_quality": False})
                    l_res, logic_model = self.runner.run_logic_critic(proposal, {**context, "force_quality": False})
                    state.track_cost("Tech Critic", self.runner.model_cost(tech_model))
                    state.track_cost("Logic Critic", self.runner.model_cost(logic_model))
                    state.record_model_usage("Tech Critic", tech_model)
                    state.record_model_usage("Logic Critic", logic_model)
                    critic_overlap = self._critic_overlap(t_res, l_res)
                    critic_redundancy = critic_overlap >= 0.72
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
                            {**context, "force_quality": False},
                            extra_instruction=extra_instruction,
                        )
                        rerun_overlap = self._critic_overlap(t_res, rerun_logic)
                        state.track_cost("Logic Critic", self.runner.model_cost(rerun_logic_model))
                        state.record_model_usage("Logic Critic Recheck", rerun_logic_model)
                        if rerun_overlap < critic_overlap:
                            l_res = rerun_logic
                            logic_model = rerun_logic_model
                            critic_overlap = rerun_overlap
                        critic_redundancy = critic_overlap >= 0.72
                    t_score = t_res.get("score", 1)
                    l_score = l_res.get("score", 1)
                    avg_score = self.scorer.compute(t_res, l_res, task_mode=state.task_mode)
                    janitor_payload = self._build_janitor_payload(state, proposal, preflight_issues, t_res, l_res)
                    janitor_report, janitor_model = self.runner.run_janitor(janitor_payload, context)
                    janitor_report = self._filter_janitor_report(janitor_report, preflight_issues, t_res, l_res)
                    state.record_model_usage("Janitor", janitor_model)
                    state.track_cost("Janitor", self.runner.model_cost(janitor_model))

                    preflight_html = (
                        "<div class=\"score-badge danger\">LOCAL PREFLIGHT FAILED</div><br>"
                        "<b style='color:#ff6682;'>Detected Before Full Critic Loop:</b><br>"
                        + "<br>".join(f"• {issue}" for issue in preflight_issues)
                        + "<div style='background:rgba(255,170,0,0.06);padding:12px;border-radius:8px;"
                        "margin-top:12px;border-left:3px solid #ffaa00;'>"
                        "<b>DIAGNOSTIC CRITIC PASS:</b><br>"
                        "Arbiter ran one bounded critic round anyway so the architect can see the broader failure set "
                        "without entering a full paid loop."
                        "</div><br>"
                        + self._build_critique_html(t_score, l_score, avg_score, t_res, l_res, None)
                    )
                    stop_reason = "Preflight failed after repair; completed one diagnostic critic pass."
                    fix_text = (
                        "Preflight: " + " | ".join(preflight_issues)
                        + f" || Tech: {t_res.get('fix_suggestion','')}"
                        + f" | Logic: {l_res.get('fix_suggestion','')}"
                    )
                    diagnostic_provider_error = bool(t_res.get("provider_error") or l_res.get("provider_error"))
                else:
                    preflight_html = (
                        "<div class=\"score-badge danger\">LOCAL PREFLIGHT FAILED</div><br>"
                        "<b style='color:#ff6682;'>Blocked Before Critic Spend:</b><br>"
                        + "<br>".join(f"• {issue}" for issue in preflight_issues)
                        + "<div style='background:rgba(255,68,102,0.06);padding:12px;border-radius:8px;"
                        "margin-top:12px;border-left:3px solid #ff4466;'>"
                        "<b>COST GUARDRAIL:</b><br>"
                        "Stopped before critic calls because the architect output still failed local correctness checks. "
                        "Gemini/Groq critic spend stays at zero in this case by design."
                        "</div>"
                    )
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
                stop = True
                reason = stop_reason
                break

            # ── 3. Critics (sequential — parallel optional) ──
            t_res, t_model = self.runner.run_tech_critic(proposal, context)
            l_res, l_model = self.runner.run_logic_critic(proposal, context)

            state.track_cost("Tech Critic",  self.runner.model_cost(t_model))
            state.track_cost("Logic Critic", self.runner.model_cost(l_model))
            state.record_model_usage("Tech Critic", t_model)
            state.record_model_usage("Logic Critic", l_model)

            critic_overlap = self._critic_overlap(t_res, l_res)
            critic_redundancy = critic_overlap >= 0.72
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
                state.track_cost("Logic Critic", self.runner.model_cost(rerun_logic_model))
                state.record_model_usage("Logic Critic Recheck", rerun_logic_model)
                if rerun_overlap < critic_overlap:
                    l_res = rerun_logic
                    l_model = rerun_logic_model
                    critic_overlap = rerun_overlap
                critic_redundancy = critic_overlap >= 0.72

            if SETTINGS.critic_debate_enabled:
                debate, debate_model = self.runner.run_critic_debate(proposal, t_res, l_res)
                state.track_cost("Critic Debate", self.runner.model_cost(debate_model))
                state.record_model_usage("Critic Debate", debate_model)
            else:
                debate = {}

            janitor_payload = self._build_janitor_payload(state, proposal, preflight_issues, t_res, l_res)
            janitor_report, janitor_model = self.runner.run_janitor(janitor_payload, context)
            janitor_report = self._filter_janitor_report(janitor_report, preflight_issues, t_res, l_res)
            state.record_model_usage("Janitor", janitor_model)
            state.track_cost("Janitor", self.runner.model_cost(janitor_model))

            # ── 4. Score ─────────────────────────────────────
            avg_score = self.scorer.compute(t_res, l_res, task_mode=state.task_mode)
            t_score   = t_res.get("score", 1)
            l_score   = l_res.get("score", 1)
            provider_error = bool(t_res.get("provider_error") or l_res.get("provider_error"))
            validity_status = "REVIEW DEGRADED" if provider_error else "VALID"
            score_status = "diagnostic" if provider_error else "final"
            review_confidence = "low" if (critic_redundancy or provider_error) else "normal"

            # ── 5. Build critique message ────────────────────
            critique_content = self._build_critique_html(t_score, l_score, avg_score, t_res, l_res, debate)
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

            # Optional UI callback
            if self.on_iteration_complete:
                self.on_iteration_complete(state, record)

            # ── 7. Stop check ────────────────────────────────
            stop, reason = self.stopper.should_stop(state)

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
                "current_solution": state.current_solution,
                "latest_janitor_report": state.latest_janitor_report,
                "latest_result_status": state.iteration_history[-1]["validity_status"] if state.iteration_history else "IDLE",
                "run_id": run_id,
            },
        )

    @staticmethod
    def _build_janitor_payload(state: ArbiterState, proposal: str, preflight_issues: list, t_res: dict, l_res: dict) -> str:
        unresolved = getattr(state, "unresolved_issues", {"tech": [], "logic": []})
        return (
            "TASK MODE:\n"
            f"{state.task_mode}\n\n"
            "LATEST SOLUTION:\n"
            f"{proposal}\n\n"
            "PREFLIGHT ISSUES:\n"
            f"{preflight_issues}\n\n"
            "TECH CONFIRMED DEFECTS:\n"
            f"{t_res.get('confirmed_defects', [])}\n\n"
            "TECH RISKS:\n"
            f"{t_res.get('risks', [])}\n\n"
            "TECH IMPROVEMENTS:\n"
            f"{t_res.get('improvements', [])}\n\n"
            "TECH CRITIC FINDINGS:\n"
            f"{t_res}\n\n"
            "LOGIC CONFIRMED DEFECTS:\n"
            f"{l_res.get('confirmed_defects', [])}\n\n"
            "LOGIC RISKS:\n"
            f"{l_res.get('risks', [])}\n\n"
            "LOGIC IMPROVEMENTS:\n"
            f"{l_res.get('improvements', [])}\n\n"
            "LOGIC CRITIC FINDINGS:\n"
            f"{l_res}\n\n"
            "PREVIOUS UNRESOLVED ISSUES:\n"
            f"{unresolved}\n"
        )

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
    def _build_critique_html(t_score: int, l_score: int, avg: float, t_res: dict, l_res: dict, debate: Optional[dict] = None) -> str:
        badge_cls = (
            "" if avg >= 7
            else "warning" if avg >= 5
            else "danger"
        )
        debate_block = ""
        if debate:
            debate_block = f"""
<div style='background:rgba(255,255,255,0.03);padding:12px;border-radius:8px;
            margin-top:12px;border-left:3px solid #7fffd0;'>
    <b>CRITIC DEBATE:</b><br>
    • Tech focus: {debate.get('tech_focus', 'n/a')}<br>
    • Logic focus: {debate.get('logic_focus', 'n/a')}<br>
    • Combined fix: {debate.get('combined_fix', 'n/a')}
</div>
"""
        tech_issues = t_res.get("issues", [])
        logic_issues = l_res.get("issues", [])
        tech_contract = t_res.get("repair_contract", [])
        logic_contract = l_res.get("repair_contract", [])
        tech_issue_block = ""
        logic_issue_block = ""
        if tech_issues:
            tech_issue_block = "<br><b style='color:#7fffd0;'>Full Technical Findings:</b><br>" + "<br>".join(
                f"• {issue}" for issue in tech_issues
            )
        if logic_issues:
            logic_issue_block = "<br><b style='color:#7fffd0;'>Full Logic Findings:</b><br>" + "<br>".join(
                f"• {issue}" for issue in logic_issues
            )
        repair_contract_block = ""
        if tech_contract or logic_contract:
            repair_contract_block = (
                "<div style='background:rgba(255,255,255,0.03);padding:12px;border-radius:8px;"
                "margin-top:12px;border-left:3px solid #ffaa00;'>"
                "<b>REPAIR CONTRACT:</b><br>"
                + ("<b>Tech:</b><br>" + "<br>".join(f"• {step}" for step in tech_contract) if tech_contract else "")
                + ("<br><b>Logic:</b><br>" + "<br>".join(f"• {step}" for step in logic_contract) if logic_contract else "")
                + "</div>"
            )
        return f"""
<div class="score-badge {badge_cls}">
    TECH: {t_score}/10 &nbsp;|&nbsp; LOGIC: {l_score}/10 &nbsp;|&nbsp; AVG: {avg:.1f}/10
</div><br>
<b style='color:#00ffa3;'>Technical Audit:</b> {t_res.get('critique', 'No issues.')}{tech_issue_block}<br><br>
<b style='color:#00ffa3;'>Logic Audit:</b> {l_res.get('critique', 'No issues.')}{logic_issue_block}<br>
<div style='background:rgba(0,255,163,0.05);padding:12px;border-radius:8px;
            margin-top:15px;border-left:3px solid #00ffa3;'>
    <b>FIX PRIORITY:</b><br>
    • Tech: {t_res.get('fix_suggestion', 'None.')}<br>
    • Logic: {l_res.get('fix_suggestion', 'None.')}
</div>
{repair_contract_block}
{debate_block}
"""
