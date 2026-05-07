from typing import Optional

from arbiter.agents.base_agent import (
    BaseAgent,
    ArchitectAgent,
    TechCriticAgent,
    LogicCriticAgent,
    AuditorAgent,
    JanitorAgent,
    RepairAgent,
)
from arbiter.agents.software_team import SoftwareTeamAgent
from arbiter.models.team import SpecialistPlan
from arbiter.prompts.registry import PromptRegistry
from arbiter.infra.model_selector import get_model_selector
from arbiter.infra.performance_store import get_performance_store
from arbiter.infra.decision_log import DecisionLog
from arbiter.config.settings import PRICES, SETTINGS
from arbiter.infra.plugin_registry import get_plugin_registry, provider_for_model
from arbiter.infra.structured_logging import get_logger

logger = get_logger(__name__)


class AgentRunner:
    """
    Executes agents using model selection.
    No direct API calls — delegates to agent classes which use LLMClient.
    """

    def __init__(self, registry: PromptRegistry):
        self.registry  = registry
        self.selector  = get_model_selector()
        self.perf      = get_performance_store()
        self.decision_log = DecisionLog()
        self.current_iteration = 0
        self._last_call_metadata: dict[str, dict] = {}

    def run_auditor(self, task: str, context: dict = None) -> dict:
        context = dict(context or {})
        prompt = self.registry.get("Auditor")
        attempted = []
        provider_failures = []
        llm_options = {
            "max_retries": int(context.get("auditor_max_retries", SETTINGS.auditor_rate_limit_retries)),
            "request_timeout_seconds": int(
                context.get("auditor_request_timeout_seconds", SETTINGS.auditor_request_timeout_seconds)
            ),
        }
        for model in self._auditor_candidate_models(context):
            attempted.append(model)
            agent = AuditorAgent(model=model, system_prompt=prompt)
            result = agent.audit(task, llm_options=llm_options)
            self._capture_call_metadata("Auditor", agent)
            if result.get("provider_error"):
                self._handle_provider_error(model, result)
                provider_failures.append(
                    {
                        "model": model,
                        "provider": provider_for_model(model, ""),
                        "error_type": str(result.get("error_type", "provider_error") or "provider_error"),
                        "retry_after_seconds": result.get("retry_after_seconds"),
                    }
                )
                continue

            if provider_failures:
                result = dict(result or {})
                result["fallback_used"] = True
                result["attempted_models"] = list(attempted)
                if not result.get("warning"):
                    result["warning"] = (
                        f"The Auditor switched to `{model}` after provider pressure on the initial intake lane."
                    )
                logger.info(
                    "auditor_completed",
                    extra={
                        "iteration": self.current_iteration,
                        "agent_name": "Auditor",
                        "model": model,
                        "provider": provider_for_model(model, ""),
                        "fallback_used": True,
                        "attempted_models": list(attempted),
                    },
                )
                return result, model
            logger.info(
                "auditor_completed",
                extra={
                    "iteration": self.current_iteration,
                    "agent_name": "Auditor",
                    "model": model,
                    "provider": provider_for_model(model, ""),
                },
            )
            return result, model

        return self._degraded_auditor_result(provider_failures, attempted), attempted[-1] if attempted else ""

    def run_architect(self, task: str, history: str = "", context: dict = None) -> str:
        prompt = self.registry.get("Architect")
        attempted = []
        last_solution = ""
        for model in self._candidate_models("Architect", context):
            attempted.append(model)
            agent = ArchitectAgent(model=model, system_prompt=prompt)
            solution = agent.generate(task, history=history)
            self._capture_call_metadata("Architect", agent)
            llm_result = agent.last_result()
            if not llm_result or llm_result.success:
                logger.info(
                    "architect_completed",
                    extra={
                        "iteration": self.current_iteration,
                        "agent_name": "Architect",
                        "model": model,
                        "provider": provider_for_model(model, ""),
                    },
                )
                return solution, model
            error_payload = BaseAgent.error_payload(solution, llm_result=llm_result) or {}
            self._handle_provider_error(model, error_payload)
            last_solution = solution
        return last_solution, attempted[-1] if attempted else ""

    def run_repair_round(self, repair_prompt: str, history: str = "", context: dict = None) -> tuple[str, str]:
        # Repairs still go through the architect path, but with a more explicit prompt.
        return self.run_architect(repair_prompt, history=history, context=context)

    def run_tech_critic(self, solution: str, context: dict = None) -> tuple[dict, str]:
        prompt = self.registry.get("Tech Critic")
        attempted = []
        for model in self._candidate_models("Tech Critic", context):
            attempted.append(model)
            agent = TechCriticAgent(model=model, system_prompt=prompt)
            result = agent.evaluate(solution)
            self._capture_call_metadata("Tech Critic", agent)
            if result.get("parse_error"):
                result = self._attempt_repair(result.get("raw_output", "")) or result
            if not result.get("provider_error"):
                self.perf.record("Tech Critic", model, result.get("score", 1))
                logger.info(
                    "tech_critic_completed",
                    extra={
                        "iteration": self.current_iteration,
                        "agent_name": "Tech Critic",
                        "model": model,
                        "provider": provider_for_model(model, ""),
                        "score": result.get("score", 1),
                    },
                )
                return result, model
            self._handle_provider_error(model, result)
        return result, attempted[-1] if attempted else ""

    def run_logic_critic(self, solution: str, context: dict = None, extra_instruction: str = "") -> tuple[dict, str]:
        prompt = self.registry.get("Logic Critic")
        attempted = []
        for model in self._candidate_models("Logic Critic", context):
            attempted.append(model)
            agent = LogicCriticAgent(model=model, system_prompt=prompt)
            result = agent.evaluate(solution, extra_instruction=extra_instruction)
            self._capture_call_metadata("Logic Critic", agent)
            if result.get("parse_error"):
                result = self._attempt_repair(result.get("raw_output", "")) or result
            if not result.get("provider_error"):
                self.perf.record("Logic Critic", model, result.get("score", 1))
                logger.info(
                    "logic_critic_completed",
                    extra={
                        "iteration": self.current_iteration,
                        "agent_name": "Logic Critic",
                        "model": model,
                        "provider": provider_for_model(model, ""),
                        "score": result.get("score", 1),
                    },
                )
                return result, model
            self._handle_provider_error(model, result)
        return result, attempted[-1] if attempted else ""

    def run_janitor(self, payload: str, context: dict = None) -> tuple[dict, str]:
        prompt = self.registry.get("Janitor")
        attempted = []
        for model in self._candidate_models("Janitor", context):
            attempted.append(model)
            agent = JanitorAgent(model=model, system_prompt=prompt)
            result = agent.consolidate(payload)
            self._capture_call_metadata("Janitor", agent)
            if not result.get("provider_error"):
                logger.info(
                    "janitor_completed",
                    extra={
                        "iteration": self.current_iteration,
                        "agent_name": "Janitor",
                        "model": model,
                        "provider": provider_for_model(model, ""),
                    },
                )
                return result, model
            self._handle_provider_error(model, result)
        return result, attempted[-1] if attempted else ""

    def run_specialist(
        self,
        role: str,
        task: str,
        history: str = "",
        context: dict = None,
        selection_role: str = "Architect",
    ) -> tuple[str, str]:
        prompt = self.registry.get(role)
        attempted = []
        last_solution = ""
        for model in self._candidate_models(selection_role, context):
            attempted.append(model)
            agent = ArchitectAgent(model=model, system_prompt=prompt)
            solution = agent.generate(task, history=history)
            self._capture_call_metadata(role, agent)
            llm_result = agent.last_result()
            if not llm_result or llm_result.success:
                logger.info(
                    "specialist_completed",
                    extra={
                        "iteration": self.current_iteration,
                        "agent_name": role,
                        "model": model,
                        "provider": provider_for_model(model, ""),
                    },
                )
                return solution, model
            error_payload = BaseAgent.error_payload(solution, llm_result=llm_result) or {}
            self._handle_provider_error(model, error_payload)
            last_solution = solution
        return last_solution, attempted[-1] if attempted else ""

    def run_software_specialist(
        self,
        role: str,
        task: str,
        history: str = "",
        context: dict = None,
        selection_role: str = "Architect",
        model_candidates: Optional[list[str]] = None,
    ) -> tuple[SpecialistPlan, str]:
        prompt = self.registry.get(role)
        attempted = []
        last_plan = None
        ordered_models = self._prepare_candidate_models(selection_role, context, model_candidates=model_candidates)
        for model in ordered_models:
            attempted.append(model)
            agent = SoftwareTeamAgent(role=role, model=model, system_prompt=prompt)
            plan = agent.plan(task, history=history)
            self._capture_call_metadata(role, agent)
            llm_result = agent.last_result()
            if not llm_result or llm_result.success:
                logger.info(
                    "specialist_completed",
                    extra={
                        "iteration": self.current_iteration,
                        "agent_name": role,
                        "model": model,
                        "provider": provider_for_model(model, ""),
                    },
                )
                return plan, model
            error_payload = BaseAgent.error_payload(llm_result.text, llm_result=llm_result) or {}
            self._handle_provider_error(model, error_payload)
            last_plan = plan
        fallback = last_plan or SpecialistPlan(
            role=role,
            scope=f"{role} did not complete a normal pass.",
            recommendations=[f"Retry the {role} pass with a fallback model."],
            risks=["No specialist output was produced."],
            dependencies=[],
            interfaces=[],
            implementation_steps=[],
            open_questions=["Should this lane be retried with a different model or narrower prompt?"],
            implementation_artifact="",
        )
        return fallback, attempted[-1] if attempted else ""

    def _prepare_candidate_models(
        self,
        agent: str,
        context: dict = None,
        model_candidates: Optional[list[str]] = None,
    ) -> list[str]:
        if not model_candidates:
            return self._candidate_models(agent, context)

        ordered = [str(model).strip() for model in model_candidates if str(model).strip()]
        expanded = list(ordered)
        for model in ordered:
            expanded.extend(self.selector.fallback_models(agent, model))

        seen = set()
        unique = []
        for model in expanded:
            if model and model not in seen:
                unique.append(model)
                seen.add(model)
        return unique or self._candidate_models(agent, context)

    def _auditor_candidate_models(self, context: dict = None) -> list[str]:
        context = dict(context or {})
        ordered = list(self._candidate_models("Auditor", context))
        if not context.get("allow_provider_fallback", SETTINGS.auditor_provider_fallback_enabled):
            return ordered

        registry = get_plugin_registry()
        preferred = [
            "gemini-2.5-flash",
            "claude-3-5-haiku-latest",
            "gpt-4o-mini",
            "gemini-2.5-pro",
            "claude-sonnet-4-20250514",
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
        ]
        extra = list(preferred)
        extra.extend(plugin.model_id for plugin in registry.candidates_for_role("Auditor"))

        seen = set()
        unique = []
        for model in ordered + extra:
            model = str(model or "").strip()
            if not model or model in seen:
                continue
            seen.add(model)
            if not registry.is_selectable(model, "Auditor"):
                continue
            if self.selector.is_temporarily_unavailable(model):
                continue
            unique.append(model)
        return unique or ordered

    @staticmethod
    def _degraded_auditor_result(provider_failures: list[dict], attempted_models: list[str]) -> dict:
        last_failure = dict(provider_failures[-1] if provider_failures else {})
        retry_after = last_failure.get("retry_after_seconds")
        base_message = (
            "The Auditor could not complete a normal intake pass because the available providers were limited. "
            "The case can still proceed, but intake review was degraded."
        )
        if last_failure.get("error_type") == "rate_limit" and retry_after:
            try:
                total = max(0, int(float(retry_after)))
                minutes, seconds = divmod(total, 60)
                retry_label = f"{minutes}m {seconds}s" if minutes else f"{seconds}s"
                base_message = (
                    f"{base_message} The last retry window reported by the provider was about {retry_label}."
                )
            except Exception:
                pass
        return {
            "clear": True,
            "questions": [],
            "provider_error": True,
            "provider_limited": any(
                str(item.get("error_type", "") or "") == "rate_limit" for item in provider_failures
            ),
            "warning": base_message,
            "error_type": str(last_failure.get("error_type", "provider_error") or "provider_error"),
            "retry_after_seconds": retry_after,
            "attempted_models": list(attempted_models),
            "attempted_providers": sorted(
                {
                    str(item.get("provider", "") or "")
                    for item in provider_failures
                    if str(item.get("provider", "") or "").strip()
                }
            ),
            "fallback_used": len(attempted_models) > 1,
        }

    def _attempt_repair(self, raw_output: str) -> Optional[dict]:
        prompt = self.registry.get("JSON Repair")
        last_result = None
        for model in self._candidate_models("Repair", {"force_quality": False}):
            agent = RepairAgent(model=model, system_prompt=prompt)
            result = agent.repair(raw_output)
            self._capture_call_metadata("Repair", agent)
            if result and not result.get("provider_error"):
                return result
            if result:
                self._handle_provider_error(model, result)
                last_result = result
        return last_result

    def run_critic_debate(self, solution: str, tech_result: dict, logic_result: dict) -> tuple[dict, str]:
        """
        Lightweight collaboration pass: critics see each other's outputs and produce
        a refined combined recommendation. Uses a cheap OpenAI-compatible model.
        """
        system_prompt = (
            "Act as a critic synthesis agent. Your job is to combine two critiques into one "
            "clear and practical refinement plan. Return valid JSON with exactly these keys: "
            "tech_focus, logic_focus, combined_fix, severity. "
            "Each of tech_focus, logic_focus, and combined_fix must be plain strings, not nested objects."
        )
        user_prompt = (
            f"SOLUTION:\n{solution}\n\n"
            f"TECH CRITIC:\n{tech_result}\n\n"
            f"LOGIC CRITIC:\n{logic_result}\n\n"
            "Return one refined combined critique in JSON with plain string values only."
        )
        agent = BaseAgent(
            name="Critic Debate",
            provider="groq",
            model="llama-3.1-8b-instant",
            system_prompt=system_prompt,
        )
        raw = agent.run(user_prompt, force_json=False)
        self._capture_call_metadata("Critic Debate", agent)
        llm_result = agent.last_result()
        error_payload = BaseAgent.error_payload(raw, llm_result=llm_result)
        if error_payload and error_payload.get("provider_error"):
            self._handle_provider_error("llama-3.1-8b-instant", error_payload)
            return ({
                "tech_focus": tech_result.get("fix_suggestion", ""),
                "logic_focus": logic_result.get("fix_suggestion", ""),
                "combined_fix": f"Tech: {tech_result.get('fix_suggestion','')} | Logic: {logic_result.get('fix_suggestion','')}",
                "severity": "high" if int(tech_result.get("score", 1)) <= 5 else "medium",
            }, "llama-3.1-8b-instant")
        result = BaseAgent.clean_json(raw)
        if result.get("parse_error"):
            return ({
                "tech_focus": tech_result.get("fix_suggestion", ""),
                "logic_focus": logic_result.get("fix_suggestion", ""),
                "combined_fix": f"Tech: {tech_result.get('fix_suggestion','')} | Logic: {logic_result.get('fix_suggestion','')}",
                "severity": "high" if int(tech_result.get("score", 1)) <= 5 else "medium",
            }, "llama-3.1-8b-instant")
        return self._normalize_debate_result(result), "llama-3.1-8b-instant"

    def _candidate_models(self, agent: str, context: dict = None) -> list[str]:
        context = context or {}
        primary_model, _ = self.selector.choose(
            agent,
            context,
            decision_log=self.decision_log,
            iteration=context.get("iteration", self.current_iteration),
        )
        fallbacks = self.selector.fallback_models(agent, primary_model)
        ordered = [primary_model] + [model for model in fallbacks if model != primary_model]
        seen = set()
        unique = []
        for model in ordered:
            if model and model not in seen:
                unique.append(model)
                seen.add(model)
        return unique

    def _handle_provider_error(self, model: str, result: dict):
        error_type = str(result.get("error_type", "provider_error"))
        retry_after = result.get("retry_after_seconds")
        if error_type == "rate_limit":
            cooldown = retry_after or SETTINGS.rate_limit_cooldown_seconds
        elif error_type == "model_decommissioned":
            cooldown = SETTINGS.decommission_cooldown_seconds
        elif error_type == "model_missing":
            cooldown = SETTINGS.decommission_cooldown_seconds
        else:
            cooldown = SETTINGS.provider_error_cooldown_seconds
        self.selector.mark_temporarily_unavailable(model, cooldown)
        self.decision_log.record(
            category="provider_cooldown",
            summary=f"{model} temporarily cooled down",
            reason=f"{error_type} triggered cooldown of {cooldown}s",
            confidence="high" if error_type in {"rate_limit", "model_decommissioned"} else "medium",
            iteration=self.current_iteration,
            metadata={
                "model": model,
                "error_type": error_type,
                "cooldown_seconds": cooldown,
            },
        )
        logger.warning(
            "provider_cooldown_applied",
            extra={
                "iteration": self.current_iteration,
                "agent_name": "Model Selector",
                "model": model,
                "provider": provider_for_model(model, ""),
                "error_type": error_type,
            },
        )

    def _capture_call_metadata(self, role: str, agent: BaseAgent):
        self._last_call_metadata[role] = agent.last_call_metadata()

    def latest_call_metadata(self, role: str) -> dict:
        return dict(self._last_call_metadata.get(role, {}))

    def set_call_metadata(self, role: str, metadata: dict) -> None:
        self._last_call_metadata[role] = dict(metadata or {})

    def latest_call_cost(self, role: str, fallback_model: str = "") -> float:
        metadata = self.latest_call_metadata(role)
        if metadata:
            try:
                return max(0.0, float(metadata.get("estimated_cost_usd", 0.0) or 0.0))
            except Exception:
                pass
        if fallback_model:
            return self.model_cost(fallback_model)
        return 0.0

    @staticmethod
    def _normalize_debate_result(result: dict) -> dict:
        def flatten(value):
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return " | ".join(str(item) for item in value if str(item).strip())
            if isinstance(value, dict):
                if "issues" in value and isinstance(value["issues"], list):
                    issues = [str(item).strip() for item in value["issues"] if str(item).strip()]
                    if issues:
                        return " | ".join(issues)
                if "repair_contract" in value and isinstance(value["repair_contract"], list):
                    steps = [str(item).strip() for item in value["repair_contract"] if str(item).strip()]
                    if steps:
                        return " | ".join(steps)
                if "refinement_plan" in value and isinstance(value["refinement_plan"], list):
                    steps = [str(item).strip() for item in value["refinement_plan"] if str(item).strip()]
                    if steps:
                        return " | ".join(steps)
                if "critique" in value:
                    return str(value["critique"])
            return str(value)

        return {
            "tech_focus": flatten(result.get("tech_focus", "")),
            "logic_focus": flatten(result.get("logic_focus", "")),
            "combined_fix": flatten(result.get("combined_fix", "")),
            "severity": str(result.get("severity", "medium")),
        }

    @staticmethod
    def model_cost(model: str) -> float:
        return PRICES.get(model, 0.001)
