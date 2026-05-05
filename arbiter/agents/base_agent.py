import json
import re
from arbiter.infra.llm_client import get_llm_client
from arbiter.infra.cache import get_cache
from arbiter.infra.model_selector import provider_for_model


class BaseAgent:
    """
    Stateless agent. Receives a prompt, returns a string.
    All state lives in ArbiterState, not here.
    """

    def __init__(self, name: str, provider: str, model: str, system_prompt: str):
        self.name          = name
        self.provider      = provider
        self.model         = model
        self.system_prompt = system_prompt
        self._client       = get_llm_client()
        self._cache        = get_cache()

    def run(self, user_prompt: str, history: str = "", force_json: bool = False) -> str:
        full_prompt = (
            f"=== PREVIOUS ITERATION CONTEXT ===\n{history}\n\n"
            f"=== CURRENT TASK ===\n{user_prompt}"
            if history else user_prompt
        )

        # Check cache
        cached = self._cache.get(self.provider, self.model, full_prompt)
        if cached:
            return cached

        response = self._client.generate(
            provider=self.provider,
            model=self.model,
            system_prompt=self.system_prompt,
            user_prompt=full_prompt,
            force_json=force_json and self.provider == "openai",
            temperature=0.1 if self.name != "Architect" else 0.4,
        )

        if self.is_cacheable_response(response):
            self._cache.set(self.provider, self.model, full_prompt, response)
        return response

    @staticmethod
    def is_cacheable_response(response: str) -> bool:
        raw = str(response or "").strip()
        if not raw.startswith("{"):
            return True
        parsed = BaseAgent.clean_json(raw)
        if not isinstance(parsed, dict):
            return True
        critique = str(parsed.get("critique", "")).lower()
        if parsed.get("provider_error"):
            return False
        if parsed.get("error_type") in {"rate_limit", "model_decommissioned", "provider_error"}:
            return False
        if critique.startswith("llm call failed") or "api error:" in critique:
            return False
        return True

    @staticmethod
    def error_payload(raw: str):
        text = str(raw or "").strip()
        if not text.startswith("{"):
            return None
        parsed = BaseAgent.clean_json(text)
        if not isinstance(parsed, dict):
            return None
        critique = str(parsed.get("critique", "")).lower()
        if parsed.get("provider_error") or parsed.get("error_type") or critique.startswith("llm call failed") or "api error:" in critique:
            return parsed
        return None

    @staticmethod
    def clean_json(raw: str) -> dict:
        raw_str = str(raw).strip()
        try:
            return json.loads(raw_str)
        except Exception:
            pass

        fenced = re.findall(r"```(?:json)?\s*(.*?)```", raw_str, re.DOTALL | re.IGNORECASE)
        for block in fenced:
            try:
                return json.loads(block.strip())
            except Exception:
                continue

        decoder = json.JSONDecoder()
        for idx, char in enumerate(raw_str):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(raw_str[idx:])
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                continue

        return {
            "parse_error":    True,
            "raw_output":     raw_str,
            "score":          1,
            "critique":       "Response was not valid JSON.",
            "fix_suggestion": "Retry with stricter JSON formatting.",
            "confirmed_defects": [],
            "risks": [],
            "improvements": [],
            "issues":         [],
            "repair_contract": [],
            "clear":          True,
            "questions":      [],
        }

    @staticmethod
    def normalize(data: dict, default_score: int = 1) -> dict:
        result = dict(data or {})
        try:
            score = int(result.get("score", default_score))
        except Exception:
            score = default_score
        result["score"]          = max(1, min(10, score))
        result["critique"]       = str(result.get("critique", "")).strip() or "No critique returned."
        result["fix_suggestion"] = str(result.get("fix_suggestion", "")).strip() or "No fix suggestion returned."
        for key in ("confirmed_defects", "risks", "improvements"):
            value = result.get(key, [])
            if not isinstance(value, list):
                value = [str(value)]
            result[key] = [str(item).strip() for item in value if str(item).strip()][:6]
        issues = result.get("issues", [])
        if not isinstance(issues, list):
            issues = [str(issues)]
        result["issues"] = [str(item).strip() for item in issues if str(item).strip()][:6]

        repair_contract = result.get("repair_contract", [])
        if not isinstance(repair_contract, list):
            repair_contract = [str(repair_contract)]
        result["repair_contract"] = [str(item).strip() for item in repair_contract if str(item).strip()][:6]

        if not result["issues"]:
            if result["confirmed_defects"]:
                result["issues"] = list(result["confirmed_defects"])
            elif result["risks"]:
                result["issues"] = list(result["risks"])
            elif result["improvements"]:
                result["issues"] = list(result["improvements"])
            elif result["critique"]:
                result["issues"] = [result["critique"]]
        if not result["repair_contract"] and result["fix_suggestion"]:
            result["repair_contract"] = [result["fix_suggestion"]]

        # Avoid punishing speculative issues like confirmed defects.
        if not result["confirmed_defects"]:
            if result["risks"] and result["score"] < 7:
                result["score"] = 7
            elif result["improvements"] and not result["risks"] and result["score"] < 8:
                result["score"] = 8

        critique_lower = result["critique"].lower()
        result["provider_error"] = (
            bool(result.get("provider_error"))
            or critique_lower.startswith("llm call failed")
            or "api error:" in critique_lower
            or "model_decommissioned" in critique_lower
            or "rate_limit_exceeded" in critique_lower
            or "rate limit reached" in critique_lower
        )
        if "error_type" not in result:
            if "rate_limit_exceeded" in critique_lower or "rate limit reached" in critique_lower:
                result["error_type"] = "rate_limit"
            elif "model_decommissioned" in critique_lower or "decommissioned" in critique_lower:
                result["error_type"] = "model_decommissioned"
            elif result["provider_error"]:
                result["error_type"] = "provider_error"
        return result


class ArchitectAgent(BaseAgent):
    def __init__(self, model: str, system_prompt: str):
        provider = provider_for_model(model, "openai")
        super().__init__("Architect", provider, model, system_prompt)

    def generate(self, task: str, history: str = "") -> str:
        return self.run(task, history=history, force_json=False)


class TechCriticAgent(BaseAgent):
    def __init__(self, model: str, system_prompt: str):
        provider = provider_for_model(model, "gemini")
        super().__init__("Tech Critic", provider, model, system_prompt)

    def evaluate(self, solution: str) -> dict:
        raw = self.run(solution, force_json=False)
        return self.normalize(self.clean_json(raw))


class LogicCriticAgent(BaseAgent):
    def __init__(self, model: str, system_prompt: str):
        provider = provider_for_model(model, "groq")
        super().__init__("Logic Critic", provider, model, system_prompt)

    def evaluate(self, solution: str, extra_instruction: str = "") -> dict:
        prompt = solution
        if extra_instruction:
            prompt = f"{extra_instruction}\n\nSOLUTION TO REVIEW:\n{solution}"
        raw = self.run(prompt, force_json=False)
        return self.normalize(self.clean_json(raw))


class AuditorAgent(BaseAgent):
    def __init__(self, model: str, system_prompt: str):
        provider = provider_for_model(model, "gemini")
        super().__init__("Auditor", provider, model, system_prompt)

    def audit(self, task: str) -> dict:
        raw = self.run(task, force_json=False)
        result = self.clean_json(raw)
        if result.get("parse_error"):
            return {"clear": False, "questions": ["Could not parse auditor response. Please rephrase your task."]}
        return result


class RepairAgent(BaseAgent):
    def __init__(self, model: str, system_prompt: str):
        provider = provider_for_model(model, "openai")
        super().__init__("Repair", provider, model, system_prompt)

    def repair(self, broken_output: str) -> dict:
        prompt = (
            "Repair this malformed critic output into valid JSON with keys "
            "score, critique, fix_suggestion, confirmed_defects, risks, improvements, issues, and repair_contract.\n\n"
            f"RAW OUTPUT:\n{broken_output}"
        )
        raw    = self.run(prompt, force_json=True)
        result = self.clean_json(raw)
        if result.get("parse_error"):
            return None
        result["repaired"] = True
        return result


class JanitorAgent(BaseAgent):
    def __init__(self, model: str, system_prompt: str):
        provider = provider_for_model(model, "groq")
        super().__init__("Janitor", provider, model, system_prompt)

    def consolidate(self, payload: str) -> dict:
        raw = self.run(payload, force_json=False)
        return self.normalize_janitor(self.clean_json(raw))

    @staticmethod
    def normalize_janitor(data: dict) -> dict:
        result = dict(data or {})
        for key in ("resolved", "pending", "regressed", "preserve", "repair_brief"):
            value = result.get(key, [])
            if not isinstance(value, list):
                value = [str(value)]
            result[key] = [str(item).strip() for item in value if str(item).strip()][:6]
        result["summary"] = str(result.get("summary", "")).strip()
        result["primary_subsystem"] = str(result.get("primary_subsystem", "")).strip()
        critique_lower = str(result.get("critique", "")).lower()
        result["provider_error"] = (
            bool(result.get("provider_error"))
            or critique_lower.startswith("llm call failed")
            or "api error:" in critique_lower
            or "rate_limit_exceeded" in critique_lower
            or "rate limit reached" in critique_lower
        )
        return result
