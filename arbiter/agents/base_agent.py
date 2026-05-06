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
        self._last_call_metadata = {}

    def run(self, user_prompt: str, history: str = "", force_json: bool = False) -> str:
        full_prompt = (
            f"=== PREVIOUS ITERATION CONTEXT ===\n{history}\n\n"
            f"=== CURRENT TASK ===\n{user_prompt}"
            if history else user_prompt
        )

        # Check cache
        cached = self._cache.get(self.provider, self.model, full_prompt)
        if cached:
            metadata = self._client._build_usage_metadata(
                provider=self.provider,
                model=self.model,
                system_prompt=self.system_prompt,
                user_prompt=full_prompt,
                output_text=cached,
                usage={},
                latency_ms=0.0,
                cost_method="cache_hit",
                cached=True,
                agent_name=self.name,
            )
            self._client._set_last_call_metadata(metadata)
            self._last_call_metadata = self._client.get_last_call_metadata()
            return cached

        response = self._client.generate(
            provider=self.provider,
            model=self.model,
            system_prompt=self.system_prompt,
            user_prompt=full_prompt,
            force_json=force_json and self.provider == "openai",
            temperature=0.1 if self.name != "Architect" else 0.4,
            agent_name=self.name,
        )
        self._last_call_metadata = self._client.get_last_call_metadata()

        if self.is_cacheable_response(response):
            self._cache.set(self.provider, self.model, full_prompt, response)
        return response

    def last_call_metadata(self) -> dict:
        return dict(self._last_call_metadata or {})

    @staticmethod
    def extract_task_mode(task_text: str) -> str:
        match = re.search(r"^\s*TASK MODE:\s*(.+?)\s*$", str(task_text or ""), flags=re.MULTILINE)
        return str(match.group(1)).strip() if match else ""

    @staticmethod
    def extract_user_request(task_text: str) -> str:
        raw = str(task_text or "")
        if "USER REQUEST:" in raw:
            return raw.split("USER REQUEST:", 1)[-1].strip()
        return raw.strip()

    @staticmethod
    def explicit_code_request(task_mode: str, task_text: str) -> bool:
        if task_mode == "Software & IT":
            return True
        lowered = BaseAgent.extract_user_request(task_text).lower()
        strong_signals = [
            "write code",
            "provide code",
            "return code",
            "show code",
            "generate code",
            "code snippet",
            "python",
            "javascript",
            "typescript",
            "react",
            "streamlit",
            "html",
            "css",
            "sql query",
            "sql script",
            "api endpoint",
            "json schema",
            "build a web app",
            "build an app",
            "technical implementation",
        ]
        return any(signal in lowered for signal in strong_signals)

    @staticmethod
    def looks_like_wrong_modality_code(raw: str) -> bool:
        content = str(raw or "")
        if re.search(r"```[\w-]*", content):
            return True

        non_empty_lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not non_empty_lines:
            return False

        code_like_count = 0
        for line in non_empty_lines:
            if re.search(
                r"^\s*(def |class |function |const |let |var |import |from |SELECT |INSERT |UPDATE |CREATE )",
                line,
                flags=re.IGNORECASE,
            ):
                code_like_count += 1
                continue
            if re.search(r"[{};]|=>", line):
                code_like_count += 1
                continue
            if re.search(r"</?[a-z][^>]*>", line, flags=re.IGNORECASE):
                code_like_count += 1
                continue

        return code_like_count >= max(4, len(non_empty_lines) // 3)

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
            score = int(round(float(result.get("score", default_score))))
        except Exception:
            score = default_score
        result["score"]          = max(1, min(10, score))
        critique = str(result.get("critique", "")).strip() or "No critique returned."
        if len(critique) > 1200:
            critique = critique[:1200].rstrip() + "... [truncated]"
        fix_suggestion = str(result.get("fix_suggestion", "")).strip() or "No fix suggestion returned."
        if len(fix_suggestion) > 400:
            fix_suggestion = fix_suggestion[:400].rstrip() + "... [truncated]"
        result["critique"] = critique
        result["fix_suggestion"] = fix_suggestion
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
        response = self.run(task, history=history, force_json=False)
        task_mode = self.extract_task_mode(task)
        if not task_mode or task_mode == "Software & IT":
            return response
        if self.explicit_code_request(task_mode, task):
            return response
        if not self.looks_like_wrong_modality_code(response):
            return response

        rewrite_prompt = (
            "Your previous answer violated the required output mode for this task.\n"
            "You are handling a non-software request and must return the actual deliverable in plain language only.\n"
            "Do NOT return code, code fences, JSON, schemas, HTML, CSS, SQL, APIs, data models, or implementation scaffolds.\n"
            "Return only the real deliverable the user asked for: plan, strategy, copy, workflow, SOP, recommendation, or structured reasoning.\n\n"
            f"TASK MODE: {task_mode}\n\n"
            f"ORIGINAL USER REQUEST:\n{self.extract_user_request(task)}\n\n"
            "YOUR PREVIOUS INVALID ANSWER:\n"
            f"{response}"
        )
        rewritten = self.run(rewrite_prompt, history="", force_json=False)
        if not self.looks_like_wrong_modality_code(rewritten):
            return rewritten

        final_retry_prompt = (
            "Final correction.\n"
            "Return only a plain-language business deliverable.\n"
            "Use short headings and bullets if helpful, but absolutely no code, JSON, tables, schemas, or fenced blocks.\n"
            "Do not explain that you are correcting yourself. Just deliver the answer properly.\n\n"
            f"TASK MODE: {task_mode}\n\n"
            f"ORIGINAL USER REQUEST:\n{self.extract_user_request(task)}"
        )
        return self.run(final_retry_prompt, history="", force_json=False)


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

    @staticmethod
    def _question_lines(raw: str) -> list[str]:
        questions = []
        for line in str(raw or "").splitlines():
            text = str(line or "").strip()
            text = re.sub(r"^[\-\*\d\.\)\s]+", "", text).strip()
            if text.endswith("?") and len(text) > 12:
                questions.append(text)
        deduped = []
        for question in questions:
            lowered = question.lower()
            if lowered not in {item.lower() for item in deduped}:
                deduped.append(question)
        return deduped[:3]

    @staticmethod
    def _fallback_prompt_for_mode(task_mode: str) -> str:
        prompts = {
            "Software & IT": "What stack, constraints, or input/output details are still missing?",
            "Marketing & Growth": "What audience, offer, or success metric should this be optimized for?",
            "Business & Operations": "What process, ownership, or operational constraint still needs to be clarified?",
            "Writing & Content": "Who is this for, what format should it take, and what outcome should it achieve?",
            "Personal Planning": "What time horizon, goal, or personal constraint should shape the plan?",
            "General Problem Solving": "What objective, constraint, or success condition still needs to be clarified?",
        }
        return prompts.get(task_mode, prompts["General Problem Solving"])

    def _recover_audit_result(self, task: str, raw: str) -> dict:
        task_mode = self.extract_task_mode(task)
        text = str(raw or "").strip()
        lowered = text.lower()

        questions = self._question_lines(text)
        if questions:
            return {"clear": False, "questions": questions}

        approved_signals = (
            "specific enough to proceed",
            "clear enough to proceed",
            "approved",
            "sufficient context",
            '"clear": true',
        )
        if any(signal in lowered for signal in approved_signals):
            return {"clear": True, "questions": []}

        blocked_signals = (
            "need more context",
            "needs more context",
            "missing context",
            "missing information",
            "unclear",
            "ambiguous",
            "too vague",
            "not enough detail",
        )
        if any(signal in lowered for signal in blocked_signals):
            return {
                "clear": False,
                "questions": [self._fallback_prompt_for_mode(task_mode)],
            }

        provider_error = self.error_payload(text)
        if provider_error and provider_error.get("provider_error"):
            return {
                "clear": False,
                "questions": ["The Auditor could not complete its check because the selected model/provider failed. Retry the run or switch models."],
            }

        return {"clear": True, "questions": []}

    def audit(self, task: str) -> dict:
        raw = self.run(task, force_json=False)
        result = self.clean_json(raw)
        if result.get("parse_error"):
            return self._recover_audit_result(task, raw)
        clear = bool(result.get("clear", True))
        questions = result.get("questions", [])
        if not isinstance(questions, list):
            questions = [str(questions)]
        questions = [str(item).strip() for item in questions if str(item).strip()][:3]
        if clear:
            return {"clear": True, "questions": []}
        if questions:
            return {"clear": False, "questions": questions}
        return self._recover_audit_result(task, raw)


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
