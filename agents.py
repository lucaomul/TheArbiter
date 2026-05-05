import os
import json
import re
import requests
from openai import OpenAI
from dotenv import load_dotenv

try:
    from langchain.memory import ConversationBufferWindowMemory
except Exception:
    ConversationBufferWindowMemory = None

load_dotenv()


class IterationMemory:
    def __init__(self, k: int = 6, seed=None):
        self.k = k
        self.entries = []
        self.backend = None

        if ConversationBufferWindowMemory is not None:
            self.backend = ConversationBufferWindowMemory(
                k=k,
                memory_key="history",
                input_key="input",
                output_key="output",
                return_messages=False,
            )

        for item in seed or []:
            self.add(item.get("input", ""), item.get("output", ""))

    def add(self, user_input: str, assistant_output: str):
        record = {
            "input": str(user_input).strip(),
            "output": str(assistant_output).strip(),
        }
        self.entries.append(record)
        self.entries = self.entries[-self.k:]

        if self.backend is not None:
            self.backend.save_context(
                {"input": record["input"]},
                {"output": record["output"]},
            )

    def context(self) -> str:
        if self.backend is not None:
            return self.backend.load_memory_variables({}).get("history", "").strip()

        parts = []
        for item in self.entries[-self.k:]:
            parts.append(
                f"User/Input: {item['input']}\nAssistant/Output: {item['output']}"
            )
        return "\n\n".join(parts).strip()

    def dump(self):
        return self.entries[-self.k:]


class AIAgent:
    def __init__(self, name: str, provider: str, model_name: str, system_instruction: str):
        self.name             = name
        self.provider         = provider
        self.model_name       = model_name
        self.system_instruction = system_instruction

        if provider == "openai":
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        elif provider == "groq":
            self.client = OpenAI(
                api_key=os.getenv("GROQ_API_KEY"),
                base_url="https://api.groq.com/openai/v1",
            )
        elif provider == "gemini":
            self.api_key = os.getenv("GEMINI_API_KEY")

    # ── Main call ───────────────────────────────────────────
    def ask(self, prompt: str, history: str = "") -> str:
        """
        Send a prompt to the agent.
        history: structured string of previous critique/iteration context.
        """
        if history:
            full_context = (
                f"=== PREVIOUS ITERATION CONTEXT ===\n{history}\n\n"
                f"=== CURRENT TASK ===\n{prompt}"
            )
        else:
            full_context = prompt

        try:
            if self.provider in ("openai", "groq"):
                return self._call_openai_compatible(full_context)
            elif self.provider == "gemini":
                return self._call_gemini(full_context)
        except Exception as e:
            return json.dumps({
                "error": str(e),
                "score": 1,
                "critique": f"API call failed: {e}",
                "fix_suggestion": "Check API key and network.",
                "clear": False,
                "questions": [],
            })

    def ask_json(self, prompt: str, history: str = "", max_retries: int = 2, repair_agent=None) -> dict:
        retry_instruction = (
            "\n\nIMPORTANT: Return exactly one valid JSON object. "
            "No markdown, no code fences, no commentary."
        )

        current_prompt = prompt
        last_parsed = None

        for _ in range(max_retries + 1):
            raw = self.ask(current_prompt, history=history)
            parsed = self.clean_json(raw)
            parsed.setdefault("raw_output", raw)

            if not parsed.get("parse_error"):
                return parsed

            repaired = self.repair_json(raw, repair_agent)
            if repaired is not None:
                repaired.setdefault("raw_output", raw)
                repaired["repaired"] = True
                return repaired

            last_parsed = parsed
            current_prompt = prompt + retry_instruction

        return last_parsed or {
            "parse_error": True,
            "raw_output": "",
            "score": 1,
            "critique": "Critic response was not valid JSON.",
            "fix_suggestion": "Retry with stricter JSON formatting.",
        }

    # ── OpenAI / Groq ────────────────────────────────────────
    def _call_openai_compatible(self, full_context: str) -> str:
        # Critics and Auditor → force JSON mode
        # Architect → plain text (code blocks don't parse as JSON)
        is_json_agent = self.name != "Architect"

        params = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": self.system_instruction},
                {"role": "user",   "content": full_context},
            ],
        }
        if is_json_agent and self.provider == "openai":
            params["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**params)
        return response.choices[0].message.content

    # ── Gemini ───────────────────────────────────────────────
    def _call_gemini(self, full_context: str) -> str:
        clean_model = self.model_name.split("/")[-1]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{clean_model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{
                "parts": [{
                    "text": (
                        f"INSTRUCTION: {self.system_instruction}\n\n"
                        f"{full_context}\n\n"
                        f"Return ONLY valid JSON if you are a Critic or Auditor."
                    )
                }]
            }],
            "generationConfig": {
                "temperature": 0.3,   # lower = more consistent scores
                "maxOutputTokens": 2048,
            },
        }

        response = requests.post(url, json=payload, timeout=45)
        res_json = response.json()

        if response.status_code != 200:
            error_msg = res_json.get("error", {}).get("message", "Unknown Gemini error")
            return json.dumps({
                "error": error_msg,
                "score": 1,
                "critique": f"Gemini API error: {error_msg}",
                "fix_suggestion": "Check Gemini API key or quota.",
            })

        return res_json["candidates"][0]["content"]["parts"][0]["text"]

    # ── JSON cleaner ─────────────────────────────────────────
    @staticmethod
    def clean_json(raw_data: str) -> dict:
        """
        Robustly extract a JSON object from any string.
        Handles markdown fences, extra text, and malformed output.
        """
        raw_str = str(raw_data).strip()

        # Try the raw response first.
        try:
            return json.loads(raw_str)
        except Exception:
            pass

        # Try common fenced JSON layouts.
        fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", raw_str, re.DOTALL | re.IGNORECASE)
        for block in fenced_blocks:
            block = block.strip()
            if not block:
                continue
            try:
                return json.loads(block)
            except Exception:
                continue

        # As a final recovery step, scan for the first decodable JSON object.
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

        # Graceful fallback — surface the real failure instead of a fake review.
        return {
            "parse_error":    True,
            "raw_output":     raw_str,
            "score":          1,
            "critique":       "Critic response was not valid JSON.",
            "fix_suggestion": "Inspect the raw model output and retry with stricter JSON formatting.",
            "clear":          False,
            "questions":      [],
        }

    @staticmethod
    def repair_json(raw_output: str, repair_agent) -> dict | None:
        if repair_agent is None or not str(raw_output).strip():
            return None

        repaired_raw = repair_agent.ask(
            "Repair this malformed critic output into valid JSON with the keys "
            "score, critique, and fix_suggestion.\n\n"
            f"RAW OUTPUT:\n{raw_output}"
        )
        repaired = AIAgent.clean_json(repaired_raw)
        if repaired.get("parse_error"):
            return None
        return repaired

    @staticmethod
    def normalize_json_result(data: dict, default_score: int = 1) -> dict:
        normalized = dict(data or {})

        try:
            score = int(normalized.get("score", default_score))
        except Exception:
            score = default_score

        normalized["score"] = max(1, min(10, score))
        normalized["critique"] = str(normalized.get("critique", "")).strip() or "No critique returned."
        normalized["fix_suggestion"] = str(normalized.get("fix_suggestion", "")).strip() or "No fix suggestion returned."
        normalized.setdefault("raw_output", "")

        return normalized
