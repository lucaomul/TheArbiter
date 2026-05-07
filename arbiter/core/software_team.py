from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import time

from arbiter.agents.software_team import fallback_specialist_plan, synthesize_team_plan
from arbiter.config.settings import SETTINGS
from arbiter.core.software_team_profiles import (
    TEAM_PROFILE_DEFINITIONS,
    normalize_team_profile,
    profile_model_for_role,
)
from arbiter.core.team_router import TeamRouter
from arbiter.infra.structured_logging import get_logger
from arbiter.models.state import ArbiterState
from arbiter.models.team import SpecialistPlan, TeamRoutingDecision

logger = get_logger(__name__)


class SoftwareTeamPlanner:
    """Compatibility facade for older local software-pod experiments."""

    def __init__(self):
        self.router = TeamRouter()

    def assess(self, task_mode: str, task_text: str) -> TeamRoutingDecision:
        return self.router.route(task_mode, task_text)


class SoftwareTeamCoordinator:
    def __init__(self, runner):
        self.runner = runner
        self.router = TeamRouter()

    def route(self, task_mode: str, user_input: str) -> TeamRoutingDecision:
        return self.router.route(task_mode, user_input)

    def build_solution(
        self,
        state: ArbiterState,
        history: str,
        context: dict,
        run_id: str,
        iteration: int,
    ) -> tuple[str, str, dict]:
        decision = self.route(state.task_mode, state.user_input)
        logger.info(
            "software_team_routing_decision",
            extra={
                "run_id": run_id,
                "iteration": iteration,
                "agent_name": "Software Team Router",
                "detected_domains": ",".join(decision.detected_domains),
                "use_team": decision.use_team,
            },
        )
        if not decision.use_team:
            return "", "", decision.model_dump()

        specialist_plans: list[SpecialistPlan] = []
        role_models: dict[str, str] = {}
        failure_reasons: dict[str, str] = {}
        selected_profile = self._resolve_profile(state, decision)
        profile_config = TEAM_PROFILE_DEFINITIONS[selected_profile]
        base_context = {
            **(context or {}),
            "force_quality": selected_profile == "dream",
            "iteration": iteration,
            "software_team_profile": selected_profile,
        }
        roles = list(decision.suggested_roles or [])
        if "Lead Software Architect" not in roles:
            roles.insert(0, "Lead Software Architect")

        lead_role = "Lead Software Architect"
        lead_started = time.perf_counter()
        logger.info(
            "software_team_specialist_started",
            extra={
                "run_id": run_id,
                "iteration": iteration,
                "role": lead_role,
                "agent_name": lead_role,
                "detected_domains": ",".join(decision.detected_domains),
                "use_team": True,
            },
        )
        lead_plan, lead_model = self._run_specialist_with_timeout(
            role=lead_role,
            payload=self._lead_payload(state.current_task, decision, selected_profile),
            history=history,
            context=base_context,
            model_candidates=self._role_model_candidates(lead_role, selected_profile),
        )
        self._record_specialist_usage(state, lead_role, lead_model)
        role_models[lead_role] = lead_model
        lead_failure = self._plan_failure_reason(lead_plan)
        if lead_failure:
            failure_reasons[lead_role] = lead_failure
            logger.warning(
                "software_team_specialist_failed",
                extra={
                    "run_id": run_id,
                    "iteration": iteration,
                    "role": lead_role,
                    "agent_name": lead_role,
                    "detected_domains": ",".join(decision.detected_domains),
                    "use_team": True,
                    "latency_ms": round((time.perf_counter() - lead_started) * 1000.0, 2),
                    "failure_reason": lead_failure,
                },
            )
        else:
            logger.info(
                "software_team_specialist_completed",
                extra={
                    "run_id": run_id,
                    "iteration": iteration,
                    "role": lead_role,
                    "agent_name": lead_role,
                    "detected_domains": ",".join(decision.detected_domains),
                    "use_team": True,
                    "latency_ms": round((time.perf_counter() - lead_started) * 1000.0, 2),
                },
            )
        specialist_plans.append(lead_plan)

        other_roles = [role for role in roles if role != lead_role]
        if other_roles:
            if getattr(SETTINGS, "software_team_parallel", True):
                other_plans = self._run_specialists_parallel(
                    state=state,
                    decision=decision,
                    roles=other_roles,
                    lead_plan=lead_plan,
                    run_id=run_id,
                    iteration=iteration,
                    context=base_context,
                    selected_profile=selected_profile,
                )
            else:
                other_plans = self._run_specialists_sequential(
                    state=state,
                    decision=decision,
                    roles=other_roles,
                    lead_plan=lead_plan,
                    run_id=run_id,
                    iteration=iteration,
                    context=base_context,
                    selected_profile=selected_profile,
                )
            for role, plan, model, failure in other_plans:
                specialist_plans.append(plan)
                role_models[role] = model
                if failure:
                    failure_reasons[role] = failure

        logger.info(
            "software_team_synthesis_started",
            extra={
                "run_id": run_id,
                "iteration": iteration,
                "agent_name": "Software Team Synthesizer",
                "detected_domains": ",".join(decision.detected_domains),
                "use_team": True,
            },
        )
        synthesis_started = time.perf_counter()
        team_plan = synthesize_team_plan(
            user_input=state.current_task,
            task_mode=state.task_mode,
            specialist_plans=specialist_plans,
            routing_decision=decision,
            selected_profile=selected_profile,
        )
        latency_ms = round((time.perf_counter() - synthesis_started) * 1000.0, 2)
        logger.info(
            "software_team_synthesis_completed",
            extra={
                "run_id": run_id,
                "iteration": iteration,
                "agent_name": "Software Team Synthesizer",
                "detected_domains": ",".join(decision.detected_domains),
                "use_team": True,
                "latency_ms": latency_ms,
            },
        )
        metadata = team_plan.model_dump()
        metadata["complexity_score"] = decision.complexity_score
        metadata["role_models"] = role_models
        metadata["selected_profile"] = selected_profile
        metadata["selected_profile_label"] = profile_config["label"]
        metadata["selected_profile_description"] = profile_config["description"]
        metadata["failure_reasons"] = failure_reasons
        metadata["specialist_summaries"] = [
            {
                "role": plan.role,
                "scope": plan.scope,
                "top_recommendation": plan.recommendations[0] if plan.recommendations else "",
                "risk": plan.risks[0] if plan.risks else "",
            }
            for plan in specialist_plans
        ]
        return team_plan.final_recommendation, lead_model or role_models.get(lead_role, ""), metadata

    def _run_specialist_with_timeout(
        self,
        role: str,
        payload: str,
        history: str,
        context: dict,
        model_candidates: list[str] | None = None,
    ) -> tuple[SpecialistPlan, str]:
        timeout_seconds = max(1, int(getattr(SETTINGS, "software_team_timeout_seconds", 60) or 60))
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="arbiter-team-single")
        future = executor.submit(
            self.runner.run_software_specialist,
            role,
            payload,
            history,
            context,
            "Architect",
            model_candidates,
        )
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError:
            failure = f"{role} timed out after {timeout_seconds}s."
            return fallback_specialist_plan(role, failure), ""
        except Exception as exc:
            failure = str(exc).strip() or "unknown specialist exception"
            return fallback_specialist_plan(role, failure), ""
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _run_specialists_parallel(
        self,
        state: ArbiterState,
        decision: TeamRoutingDecision,
        roles: list[str],
        lead_plan: SpecialistPlan,
        run_id: str,
        iteration: int,
        context: dict,
        selected_profile: str,
    ) -> list[tuple[str, SpecialistPlan, str, str]]:
        timeout_seconds = max(1, int(getattr(SETTINGS, "software_team_timeout_seconds", 60) or 60))
        results: list[tuple[str, SpecialistPlan, str, str]] = []
        executor = ThreadPoolExecutor(max_workers=max(1, len(roles)), thread_name_prefix="arbiter-team")
        futures = {}
        started = {}
        try:
            for role in roles:
                payload = self._specialist_payload(role, state.current_task, lead_plan, decision, selected_profile)
                logger.info(
                    "software_team_specialist_started",
                    extra={
                        "run_id": run_id,
                        "iteration": iteration,
                        "role": role,
                        "agent_name": role,
                        "detected_domains": ",".join(decision.detected_domains),
                        "use_team": True,
                    },
                )
                started[role] = time.perf_counter()
                futures[role] = executor.submit(
                    self.runner.run_software_specialist,
                    role,
                    payload,
                    "",
                    context,
                    "Architect",
                    self._role_model_candidates(role, selected_profile),
                )

            for role, future in futures.items():
                try:
                    plan, model = future.result(timeout=timeout_seconds)
                    self._record_specialist_usage(state, role, model)
                    failure = self._plan_failure_reason(plan)
                    latency_ms = round((time.perf_counter() - started[role]) * 1000.0, 2)
                    if failure:
                        logger.warning(
                            "software_team_specialist_failed",
                            extra={
                                "run_id": run_id,
                                "iteration": iteration,
                                "role": role,
                                "agent_name": role,
                                "detected_domains": ",".join(decision.detected_domains),
                                "use_team": True,
                                "latency_ms": latency_ms,
                                "failure_reason": failure,
                            },
                        )
                    else:
                        logger.info(
                            "software_team_specialist_completed",
                            extra={
                                "run_id": run_id,
                                "iteration": iteration,
                                "role": role,
                                "agent_name": role,
                                "detected_domains": ",".join(decision.detected_domains),
                                "use_team": True,
                                "latency_ms": latency_ms,
                            },
                        )
                    results.append((role, plan, model, failure))
                except FuturesTimeoutError:
                    latency_ms = round((time.perf_counter() - started[role]) * 1000.0, 2)
                    failure = f"{role} timed out after {timeout_seconds}s."
                    logger.warning(
                        "software_team_specialist_failed",
                        extra={
                            "run_id": run_id,
                            "iteration": iteration,
                            "role": role,
                            "agent_name": role,
                            "detected_domains": ",".join(decision.detected_domains),
                            "use_team": True,
                            "latency_ms": latency_ms,
                            "failure_reason": failure,
                        },
                    )
                    results.append((role, fallback_specialist_plan(role, failure), "", failure))
                except Exception as exc:
                    latency_ms = round((time.perf_counter() - started[role]) * 1000.0, 2)
                    failure = str(exc).strip() or "unknown specialist exception"
                    logger.warning(
                        "software_team_specialist_failed",
                        extra={
                            "run_id": run_id,
                            "iteration": iteration,
                            "role": role,
                            "agent_name": role,
                            "detected_domains": ",".join(decision.detected_domains),
                            "use_team": True,
                            "latency_ms": latency_ms,
                            "failure_reason": failure,
                        },
                        exc_info=exc,
                    )
                    results.append((role, fallback_specialist_plan(role, failure), "", failure))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return results

    def _run_specialists_sequential(
        self,
        state: ArbiterState,
        decision: TeamRoutingDecision,
        roles: list[str],
        lead_plan: SpecialistPlan,
        run_id: str,
        iteration: int,
        context: dict,
        selected_profile: str,
    ) -> list[tuple[str, SpecialistPlan, str, str]]:
        results: list[tuple[str, SpecialistPlan, str, str]] = []
        for role in roles:
            payload = self._specialist_payload(role, state.current_task, lead_plan, decision, selected_profile)
            logger.info(
                "software_team_specialist_started",
                extra={
                    "run_id": run_id,
                    "iteration": iteration,
                    "role": role,
                    "agent_name": role,
                    "detected_domains": ",".join(decision.detected_domains),
                    "use_team": True,
                },
            )
            started = time.perf_counter()
            try:
                plan, model = self._run_specialist_with_timeout(
                    role=role,
                    payload=payload,
                    history="",
                    context=context,
                    model_candidates=self._role_model_candidates(role, selected_profile),
                )
                self._record_specialist_usage(state, role, model)
                failure = self._plan_failure_reason(plan)
                latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
                if failure:
                    logger.warning(
                        "software_team_specialist_failed",
                        extra={
                            "run_id": run_id,
                            "iteration": iteration,
                            "role": role,
                            "agent_name": role,
                            "detected_domains": ",".join(decision.detected_domains),
                            "use_team": True,
                            "latency_ms": latency_ms,
                            "failure_reason": failure,
                        },
                    )
                else:
                    logger.info(
                        "software_team_specialist_completed",
                        extra={
                            "run_id": run_id,
                            "iteration": iteration,
                            "role": role,
                            "agent_name": role,
                            "detected_domains": ",".join(decision.detected_domains),
                            "use_team": True,
                            "latency_ms": latency_ms,
                        },
                    )
                results.append((role, plan, model, failure))
            except Exception as exc:
                latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
                failure = str(exc).strip() or "unknown specialist exception"
                logger.warning(
                    "software_team_specialist_failed",
                    extra={
                        "run_id": run_id,
                        "iteration": iteration,
                        "role": role,
                        "agent_name": role,
                        "detected_domains": ",".join(decision.detected_domains),
                        "use_team": True,
                        "latency_ms": latency_ms,
                        "failure_reason": failure,
                    },
                    exc_info=exc,
                )
                results.append((role, fallback_specialist_plan(role, failure), "", failure))
        return results

    def _record_specialist_usage(self, state: ArbiterState, role: str, model: str) -> None:
        state.track_cost(role, self.runner.latest_call_cost(role, model))
        state.record_model_usage(role, model, self.runner.latest_call_metadata(role))

    @staticmethod
    def _lead_payload(current_task: str, decision: TeamRoutingDecision, selected_profile: str) -> str:
        profile_label = TEAM_PROFILE_DEFINITIONS[normalize_team_profile(selected_profile)]["label"]
        return (
            f"{current_task}\n\n"
            "SOFTWARE TEAM ROUTING:\n"
            f"- Reason: {decision.reason}\n"
            f"- Selected team profile: {profile_label}\n"
            f"- Detected domains: {', '.join(decision.detected_domains) or 'none'}\n"
            f"- Selected roles: {', '.join(decision.suggested_roles) or 'none'}\n"
            "LEAD RESPONSIBILITIES:\n"
            "- Define the delivery blueprint, file boundaries, subsystem contracts, and acceptance criteria.\n"
            "- Make the handoffs explicit so the specialist roles can build without duplicating work.\n"
            "- Call out the riskiest seams between backend, frontend, data, and runtime concerns.\n"
            "Produce the shared architecture blueprint for the team."
        )

    @staticmethod
    def _specialist_payload(
        role: str,
        current_task: str,
        lead_plan: SpecialistPlan,
        decision: TeamRoutingDecision,
        selected_profile: str,
    ) -> str:
        profile_label = TEAM_PROFILE_DEFINITIONS[normalize_team_profile(selected_profile)]["label"]
        lead_brief = [f"Lead scope: {lead_plan.scope}"]
        if lead_plan.recommendations:
            lead_brief.append("Lead recommendations:")
            lead_brief.extend(f"- {item}" for item in lead_plan.recommendations)
        if lead_plan.interfaces:
            lead_brief.append("Lead interfaces:")
            lead_brief.extend(f"- {item}" for item in lead_plan.interfaces)
        if lead_plan.implementation_steps:
            lead_brief.append("Lead implementation steps:")
            lead_brief.extend(f"- {item}" for item in lead_plan.implementation_steps)
        return (
            f"{current_task}\n\n"
            "TEAM CONTEXT:\n"
            f"- Team profile: {profile_label}\n"
            f"- Detected domains: {', '.join(decision.detected_domains) or 'none'}\n"
            f"- Team roles: {', '.join(decision.suggested_roles) or 'none'}\n\n"
            "COORDINATION CONTRACT:\n"
            "- Stay inside your lane and do not rewrite the whole system.\n"
            "- Publish concrete dependencies and interfaces that adjacent specialists can rely on.\n"
            "- Prefer implementation-ready decisions over abstract guidance.\n"
            "- If another subsystem is unclear, record it as an open question instead of guessing.\n\n"
            "LEAD SOFTWARE ARCHITECT PLAN:\n"
            + "\n".join(line for line in lead_brief if line)
            + "\n\nReturn only your structured JSON specialist plan."
        )

    @staticmethod
    def _resolve_profile(state: ArbiterState, decision: TeamRoutingDecision) -> str:
        selected = normalize_team_profile(
            getattr(state, "software_team_profile", "") or decision.recommended_profile,
            default=decision.recommended_profile or "efficient",
        )
        state.software_team_profile = selected
        return selected

    @staticmethod
    def _role_model_candidates(role: str, selected_profile: str) -> list[str]:
        primary = profile_model_for_role(role, selected_profile)
        return [primary] if primary else []

    @staticmethod
    def _plan_failure_reason(plan: SpecialistPlan) -> str:
        scope = str(plan.scope or "").lower()
        if "could not complete a normal pass" in scope:
            return plan.risks[0] if plan.risks else "specialist failure"
        return ""
