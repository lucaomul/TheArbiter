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
from arbiter.prompts.registry import PromptRegistry
from arbiter.infra.model_selector import get_model_selector
from arbiter.infra.performance_store import get_performance_store
from arbiter.infra.decision_log import DecisionLog
from arbiter.config.settings import PRICES, SETTINGS
from arbiter.infra.plugin_registry import provider_for_model
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
        prompt = self.registry.get("Auditor")
        attempted = []
        for model in self._candidate_models("Auditor", context):
            attempted.append(model)
            agent = AuditorAgent(model=model, system_prompt=prompt)
            result = agent.audit(task)
            self._capture_call_metadata("Auditor", agent)
            if not result.get("provider_error"):
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
            self._handle_provider_error(model, result)
        return result, attempted[-1] if attempted else ""

    def run_architect(self, task: str, history: str = "", context: dict = None) -> str:
        prompt = self.registry.get("Architect")
        attempted = []
        last_solution = ""
        for model in self._candidate_models("Architect", context):
            attempted.append(model)
            agent = ArchitectAgent(model=model, system_prompt=prompt)
            solution = agent.generate(task, history=history)
            self._capture_call_metadata("Architect", agent)
            error_payload = BaseAgent.error_payload(solution)
            if not error_payload or not error_payload.get("provider_error"):
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
        error_payload = BaseAgent.error_payload(raw)
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
