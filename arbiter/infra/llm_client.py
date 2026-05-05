import os
import json
import re
from pathlib import Path
from urllib import error, request
from openai import OpenAI
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class LLMClient:
    """
    Unified interface for calling multiple LLM providers.
    Normalizes responses to plain strings.
    """

    def __init__(self):
        self._openai_client = None
        self._groq_client   = None
        self._ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

    @staticmethod
    def _extract_retry_after_seconds(message: str):
        text = str(message or "")
        match = re.search(r"try again in\s+(\d+)m([\d.]+)s", text, re.IGNORECASE)
        if match:
            minutes = int(match.group(1))
            seconds = float(match.group(2))
            return int(minutes * 60 + seconds)
        match = re.search(r"try again in\s+([\d.]+)s", text, re.IGNORECASE)
        if match:
            return int(float(match.group(1)))
        return None

    def _error_payload(
        self,
        provider: str,
        model: str,
        message: str,
        critique_prefix: str,
        fix_suggestion: str,
        error_type: str = "provider_error",
    ) -> str:
        payload = {
            "error": message,
            "score": 1,
            "critique": f"{critique_prefix}: {message}",
            "fix_suggestion": fix_suggestion,
            "provider_error": True,
            "provider": provider,
            "model": model,
            "error_type": error_type,
        }
        retry_after_seconds = self._extract_retry_after_seconds(message)
        if retry_after_seconds is not None:
            payload["retry_after_seconds"] = retry_after_seconds
        return json.dumps(payload)

    # ── Provider clients (lazy init) ──────────────────────────
    def _get_openai(self) -> OpenAI:
        if self._openai_client is None:
            self._openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return self._openai_client

    def _get_groq(self) -> OpenAI:
        if self._groq_client is None:
            self._groq_client = OpenAI(
                api_key=os.getenv("GROQ_API_KEY"),
                base_url="https://api.groq.com/openai/v1",
            )
        return self._groq_client

    # ── Main entry point ──────────────────────────────────────
    def generate(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        force_json: bool = False,
        temperature: float = 0.7,
    ) -> str:
        try:
            if provider == "openai":
                return self._call_openai(model, system_prompt, user_prompt, force_json, temperature)
            elif provider == "groq":
                return self._call_groq(model, system_prompt, user_prompt, temperature)
            elif provider == "gemini":
                return self._call_gemini(model, system_prompt, user_prompt, temperature)
            elif provider == "ollama":
                return self._call_ollama(model, system_prompt, user_prompt, temperature)
            else:
                raise ValueError(f"Unknown provider: {provider}")
        except Exception as e:
            message = str(e)
            error_type = "provider_error"
            fix = "Check API key and network."
            if "rate limit" in message.lower() or "rate_limit" in message.lower():
                error_type = "rate_limit"
                fix = "This model hit a quota or rate limit. Retry later or fall back to a cheaper/local model."
            return self._error_payload(provider, model, message, "LLM call failed", fix, error_type=error_type)

    # ── OpenAI ────────────────────────────────────────────────
    def _call_openai(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        force_json: bool,
        temperature: float,
    ) -> str:
        client = self._get_openai()
        params = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if force_json:
            params["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**params)
        return response.choices[0].message.content

    # ── Groq ──────────────────────────────────────────────────
    def _call_groq(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        client = self._get_groq()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception as exc:
            message = str(exc)
            fix = "Check Groq API key and runtime environment."
            error_type = "provider_error"
            lower = message.lower()
            if "rate limit" in lower or "rate_limit" in lower:
                error_type = "rate_limit"
                fix = "Groq rate limit reached for this model. Retry later or fall back to a cheaper/local Groq model."
            if "model_decommissioned" in message or "decommissioned" in message.lower():
                error_type = "model_decommissioned"
                fix = "Replace the deprecated Groq model with a currently supported one, such as llama-3.3-70b-versatile."
            return self._error_payload("groq", model, message, "Groq API error", fix, error_type=error_type)

    # ── Gemini ────────────────────────────────────────────────
    def _call_gemini(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        clean_model = model.split("/")[-1]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{clean_model}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"INSTRUCTION: {system_prompt}\n\n{user_prompt}"
                }]
            }],
            "generationConfig": {
                "temperature":    temperature,
                "maxOutputTokens": 2048,
            },
        }
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=45) as response:
                res_json = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                res_json = json.loads(body)
            except json.JSONDecodeError:
                res_json = {}
            error_msg = res_json.get("error", {}).get("message", body or "Unknown Gemini error")
            error_type = "rate_limit" if ("rate limit" in error_msg.lower() or "quota" in error_msg.lower()) else "provider_error"
            fix = "Check Gemini API key or quota." if error_type == "rate_limit" else "Check Gemini API key or request format."
            return self._error_payload("gemini", model, error_msg, "Gemini API error", fix, error_type=error_type)
        except Exception as exc:
            return self._error_payload(
                "gemini",
                model,
                str(exc),
                "Gemini API error",
                "Check Gemini API key, network, or runtime environment.",
                error_type="provider_error",
            )

        return res_json["candidates"][0]["content"]["parts"][0]["text"]

    # ── Ollama ───────────────────────────────────────────────
    def _call_ollama(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        clean_model = model.split("ollama:", 1)[-1] if model.startswith("ollama:") else model
        url = f"{self._ollama_base_url}/api/generate"
        payload = {
            "model": clean_model,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                res_json = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                res_json = json.loads(body)
            except json.JSONDecodeError:
                res_json = {}
            error_msg = res_json.get("error", body or "Unknown Ollama error")
            error_type = "provider_error"
            if "not found" in error_msg.lower() or "pull" in error_msg.lower():
                error_type = "model_missing"
            return self._error_payload(
                "ollama",
                model,
                error_msg,
                "Ollama API error",
                "Make sure `ollama serve` is running and the selected model is pulled locally.",
                error_type=error_type,
            )
        except Exception as exc:
            return self._error_payload(
                "ollama",
                model,
                str(exc),
                "Ollama API error",
                "Make sure the Ollama app/server is running locally on http://127.0.0.1:11434.",
                error_type="provider_error",
            )

        if "response" in res_json:
            return res_json["response"]
        return self._error_payload(
            "ollama",
            model,
            json.dumps(res_json),
            "Ollama API error",
            "Ollama returned an unexpected response payload.",
            error_type="provider_error",
        )


# Singleton
_client = LLMClient()


def get_llm_client() -> LLMClient:
    return _client
