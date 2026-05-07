import os
import json
import re
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib import error, request

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency in test/minimal environments
    def load_dotenv(*_args, **_kwargs):
        return False

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency in test/minimal environments
    OpenAI = None

from arbiter.config.settings import PRICES, estimate_token_cost_usd
from arbiter.infra.structured_logging import get_logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
logger = get_logger(__name__)


@dataclass
class LLMResult:
    success: bool
    text: str
    error_type: Optional[str]
    provider: str
    model: str
    retry_after_seconds: Optional[int] = None


class LLMClient:
    """
    Unified interface for calling multiple LLM providers.
    Normalizes responses to plain strings.
    """

    def __init__(self):
        self._openai_client = None
        self._groq_client   = None
        self._ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        self._last_call_metadata = {}
        self._metadata_lock = threading.RLock()
        self._last_result = None
        self._session_stats = {
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "total_calls": 0,
            "calls_by_agent": {},
            "latency_total_ms": 0.0,
        }

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
        retry_after_seconds: int = None,
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
        retry_after_seconds = retry_after_seconds or self._extract_retry_after_seconds(message)
        if retry_after_seconds is not None:
            payload["retry_after_seconds"] = retry_after_seconds
        return json.dumps(payload)

    @staticmethod
    def estimate_text_tokens(text: str) -> int:
        text = str(text or "").strip()
        if not text:
            return 0
        return max(1, int(round(len(text) / 4.0)))

    def _build_usage_metadata(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        output_text: str,
        usage: dict = None,
        latency_ms: float = None,
        cost_method: str = "provider_usage",
        cached: bool = False,
        agent_name: str = "",
    ) -> dict:
        usage = usage or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)

        if prompt_tokens <= 0:
            prompt_tokens = self.estimate_text_tokens(f"{system_prompt}\n{user_prompt}")
        if completion_tokens <= 0:
            completion_tokens = self.estimate_text_tokens(output_text)

        estimated_cost = estimate_token_cost_usd(
            model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        resolved_cost_method = cost_method
        if estimated_cost is None:
            estimated_cost = round(float(PRICES.get(model, 0.0) or 0.0), 8)
            if cached:
                estimated_cost = 0.0
                resolved_cost_method = "cache_hit"
            else:
                resolved_cost_method = "flat_model_estimate"
        elif cached:
            estimated_cost = 0.0
            resolved_cost_method = "cache_hit"
        elif cost_method != "provider_usage":
            resolved_cost_method = cost_method

        return {
            "provider": provider,
            "model": model,
            "agent_name": agent_name,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": max(0, prompt_tokens + completion_tokens),
            "estimated_cost_usd": round(float(estimated_cost or 0.0), 8),
            "cost_method": resolved_cost_method,
            "cached": bool(cached),
            "latency_ms": latency_ms,
        }

    def _set_last_call_metadata(self, metadata: dict):
        with self._metadata_lock:
            self._last_call_metadata = dict(metadata or {})
            self._record_session_call(self._last_call_metadata)

    def get_last_call_metadata(self) -> dict:
        with self._metadata_lock:
            return dict(self._last_call_metadata or {})

    def get_last_result(self) -> Optional[LLMResult]:
        with self._metadata_lock:
            if self._last_result is None:
                return None
            return LLMResult(**self._last_result.__dict__)

    def _record_session_call(self, metadata: dict):
        if not metadata:
            return
        total_tokens = int(metadata.get("total_tokens", 0) or 0)
        cost = float(metadata.get("estimated_cost_usd", 0.0) or 0.0)
        latency_ms = float(metadata.get("latency_ms", 0.0) or 0.0)
        agent_name = str(metadata.get("agent_name", "") or "unknown")
        self._session_stats["total_tokens"] += total_tokens
        self._session_stats["total_cost_usd"] = round(self._session_stats["total_cost_usd"] + cost, 8)
        self._session_stats["total_calls"] += 1
        self._session_stats["latency_total_ms"] += latency_ms

        agent_bucket = self._session_stats["calls_by_agent"].setdefault(
            agent_name,
            {"tokens": 0, "cost": 0.0, "calls": 0},
        )
        agent_bucket["tokens"] += total_tokens
        agent_bucket["cost"] = round(float(agent_bucket["cost"]) + cost, 8)
        agent_bucket["calls"] += 1

    def get_session_stats(self) -> dict:
        with self._metadata_lock:
            total_calls = int(self._session_stats.get("total_calls", 0) or 0)
            avg_latency_ms = round(
                (float(self._session_stats.get("latency_total_ms", 0.0) or 0.0) / total_calls),
                2,
            ) if total_calls else 0.0
            calls_by_agent = {}
            for agent_name, bucket in dict(self._session_stats.get("calls_by_agent", {})).items():
                calls_by_agent[agent_name] = {
                    "tokens": int(bucket.get("tokens", 0) or 0),
                    "cost": round(float(bucket.get("cost", 0.0) or 0.0), 8),
                    "calls": int(bucket.get("calls", 0) or 0),
                }
            return {
                "total_tokens": int(self._session_stats.get("total_tokens", 0) or 0),
                "total_cost_usd": round(float(self._session_stats.get("total_cost_usd", 0.0) or 0.0), 8),
                "total_calls": total_calls,
                "calls_by_agent": calls_by_agent,
                "avg_latency_ms": avg_latency_ms,
            }

    @staticmethod
    def _response_error_type(response: str):
        text = str(response or "").strip()
        if not text.startswith("{"):
            return None
        try:
            payload = json.loads(text)
        except Exception:
            return None
        if payload.get("provider_error") or payload.get("error_type"):
            return str(payload.get("error_type") or "provider_error")
        return None

    @staticmethod
    def _response_error_payload(response: str) -> Optional[dict]:
        text = str(response or "").strip()
        if not text.startswith("{"):
            return None
        try:
            payload = json.loads(text)
        except Exception:
            return None
        if payload.get("provider_error") or payload.get("error_type"):
            return payload
        return None

    @staticmethod
    def _infer_error_type(message: str) -> str:
        lowered = str(message or "").lower()
        if "rate limit" in lowered or "rate_limit" in lowered or "quota" in lowered:
            return "rate_limit"
        if "decommissioned" in lowered or "model_decommissioned" in lowered:
            return "model_decommissioned"
        if "not found" in lowered and "model" in lowered:
            return "model_missing"
        return "provider_error"

    def _result_from_response(self, provider: str, model: str, response: str) -> LLMResult:
        payload = self._response_error_payload(response)
        if payload:
            retry_after_seconds = payload.get("retry_after_seconds")
            try:
                retry_after_seconds = int(retry_after_seconds) if retry_after_seconds is not None else None
            except Exception:
                retry_after_seconds = None
            return LLMResult(
                success=False,
                text=str(response or ""),
                error_type=str(payload.get("error_type") or "provider_error"),
                provider=provider,
                model=model,
                retry_after_seconds=retry_after_seconds,
            )
        return LLMResult(
            success=True,
            text=str(response or ""),
            error_type=None,
            provider=provider,
            model=model,
            retry_after_seconds=None,
        )

    def _result_from_exception(
        self,
        provider: str,
        model: str,
        message: str,
        critique_prefix: str,
        fix_suggestion: str,
    ) -> LLMResult:
        error_type = self._infer_error_type(message)
        retry_after_seconds = self._extract_retry_after_seconds(message)
        return LLMResult(
            success=False,
            text=self._error_payload(
                provider,
                model,
                message,
                critique_prefix,
                fix_suggestion,
                error_type=error_type,
                retry_after_seconds=retry_after_seconds,
            ),
            error_type=error_type,
            provider=provider,
            model=model,
            retry_after_seconds=retry_after_seconds,
        )

    @staticmethod
    def _require_openai_sdk(provider_label: str):
        if OpenAI is None:
            raise RuntimeError(
                f"The `openai` package is not installed, so the {provider_label} client cannot be created."
            )

    # ── Provider clients (lazy init) ──────────────────────────
    def _get_openai(self):
        self._require_openai_sdk("OpenAI")
        if self._openai_client is None:
            self._openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return self._openai_client

    def _get_groq(self):
        self._require_openai_sdk("Groq")
        if self._groq_client is None:
            self._groq_client = OpenAI(
                api_key=os.getenv("GROQ_API_KEY"),
                base_url="https://api.groq.com/openai/v1",
            )
        return self._groq_client

    # ── Main entry point ──────────────────────────────────────
    def generate_result(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        force_json: bool = False,
        temperature: float = 0.7,
        agent_name: str = "",
        max_retries: int = 2,
        max_retry_sleep_seconds: Optional[int] = None,
        request_timeout_seconds: Optional[int] = None,
    ) -> LLMResult:
        self._set_last_call_metadata({})
        self._last_result = None
        retry_limit = max(0, int(max_retries or 0))
        attempt = 0

        while True:
            start_time = time.perf_counter()
            logger.debug(
                "llm_call_start",
                extra={
                    "provider": provider,
                    "model": model,
                    "force_json": force_json,
                    "agent_name": agent_name,
                    "attempt": attempt + 1,
                },
            )
            usage = {}
            try:
                if provider == "openai":
                    response, usage = self._call_openai(
                        model,
                        system_prompt,
                        user_prompt,
                        force_json,
                        temperature,
                        request_timeout_seconds=request_timeout_seconds,
                    )
                elif provider == "groq":
                    response, usage = self._call_groq(
                        model,
                        system_prompt,
                        user_prompt,
                        temperature,
                        request_timeout_seconds=request_timeout_seconds,
                    )
                elif provider == "gemini":
                    response, usage = self._call_gemini(
                        model,
                        system_prompt,
                        user_prompt,
                        temperature,
                        request_timeout_seconds=request_timeout_seconds,
                    )
                elif provider == "ollama":
                    response, usage = self._call_ollama(
                        model,
                        system_prompt,
                        user_prompt,
                        temperature,
                        request_timeout_seconds=request_timeout_seconds,
                    )
                elif provider == "anthropic":
                    response, usage = self._call_anthropic(
                        model,
                        system_prompt,
                        user_prompt,
                        temperature,
                        request_timeout_seconds=request_timeout_seconds,
                    )
                else:
                    raise ValueError(f"Unknown provider: {provider}")
                result = self._result_from_response(provider, model, response)
            except Exception as exc:
                message = str(exc)
                fix = "Check API key and network."
                if self._infer_error_type(message) == "rate_limit":
                    fix = "This model hit a quota or rate limit. Retry later or fall back to a cheaper/local model."
                result = self._result_from_exception(
                    provider,
                    model,
                    message,
                    "LLM call failed",
                    fix,
                )

            latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            if result.success:
                metadata = self._build_usage_metadata(
                    provider=provider,
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    output_text=result.text,
                    usage=usage,
                    latency_ms=latency_ms,
                    cost_method="provider_usage" if usage else "heuristic_tokens",
                    agent_name=agent_name,
                )
                self._set_last_call_metadata(metadata)
                self._last_result = result
                logger.debug(
                    "llm_call_success",
                    extra={
                        "provider": provider,
                        "model": model,
                        "agent_name": agent_name,
                        "latency_ms": latency_ms,
                        "estimated_cost_usd": metadata.get("estimated_cost_usd", 0.0),
                        "cost_method": metadata.get("cost_method", ""),
                        "attempt": attempt + 1,
                    },
                )
                return result

            if result.error_type == "rate_limit" and attempt < retry_limit:
                backoff_seconds = max(1, int(result.retry_after_seconds or (2 ** attempt)))
                if max_retry_sleep_seconds is not None:
                    try:
                        backoff_seconds = min(backoff_seconds, max(0, int(max_retry_sleep_seconds)))
                    except Exception:
                        pass
                logger.warning(
                    "llm_call_retry_scheduled",
                    extra={
                        "provider": provider,
                        "model": model,
                        "agent_name": agent_name,
                        "attempt": attempt + 1,
                        "backoff_seconds": backoff_seconds,
                        "error_type": result.error_type,
                    },
                )
                if backoff_seconds > 0:
                    time.sleep(backoff_seconds)
                attempt += 1
                continue

            metadata = {
                "provider": provider,
                "model": model,
                "agent_name": agent_name,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "cost_method": "provider_error",
                "cached": False,
                "latency_ms": latency_ms,
                "error_type": result.error_type or "provider_error",
            }
            self._set_last_call_metadata(metadata)
            self._last_result = result
            logger.warning(
                "llm_call_failed",
                extra={
                    "provider": provider,
                    "model": model,
                    "agent_name": agent_name,
                    "latency_ms": latency_ms,
                    "error_type": result.error_type or "provider_error",
                    "attempt": attempt + 1,
                },
            )
            return result

    def generate(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        force_json: bool = False,
        temperature: float = 0.7,
        agent_name: str = "",
        max_retries: int = 2,
        max_retry_sleep_seconds: Optional[int] = None,
        request_timeout_seconds: Optional[int] = None,
    ) -> str:
        return self.generate_result(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            force_json=force_json,
            temperature=temperature,
            agent_name=agent_name,
            max_retries=max_retries,
            max_retry_sleep_seconds=max_retry_sleep_seconds,
            request_timeout_seconds=request_timeout_seconds,
        ).text

    # ── OpenAI ────────────────────────────────────────────────
    def _call_openai(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        force_json: bool,
        temperature: float,
        request_timeout_seconds: Optional[int] = None,
    ) -> tuple[str, dict]:
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
        if request_timeout_seconds is not None:
            params["timeout"] = max(1, int(request_timeout_seconds))
        response = client.chat.completions.create(**params)
        usage_obj = getattr(response, "usage", None)
        usage = {
            "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) if usage_obj else 0,
            "completion_tokens": getattr(usage_obj, "completion_tokens", 0) if usage_obj else 0,
        }
        return response.choices[0].message.content, usage

    # ── Groq ──────────────────────────────────────────────────
    def _call_groq(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        request_timeout_seconds: Optional[int] = None,
    ) -> tuple[str, dict]:
        client = self._get_groq()
        try:
            params = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                "temperature": temperature,
            }
            if request_timeout_seconds is not None:
                params["timeout"] = max(1, int(request_timeout_seconds))
            response = client.chat.completions.create(
                **params,
            )
            usage_obj = getattr(response, "usage", None)
            usage = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) if usage_obj else 0,
                "completion_tokens": getattr(usage_obj, "completion_tokens", 0) if usage_obj else 0,
            }
            return response.choices[0].message.content, usage
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
            return self._error_payload("groq", model, message, "Groq API error", fix, error_type=error_type), {}

    # ── Gemini ────────────────────────────────────────────────
    def _call_gemini(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        request_timeout_seconds: Optional[int] = None,
    ) -> tuple[str, dict]:
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
            with request.urlopen(req, timeout=max(1, int(request_timeout_seconds or 45))) as response:
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
            return self._error_payload("gemini", model, error_msg, "Gemini API error", fix, error_type=error_type), {}
        except Exception as exc:
            return self._error_payload(
                "gemini",
                model,
                str(exc),
                "Gemini API error",
                "Check Gemini API key, network, or runtime environment.",
                error_type="provider_error",
            ), {}

        usage_metadata = res_json.get("usageMetadata", {}) or {}
        usage = {
            "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
            "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
        }
        return res_json["candidates"][0]["content"]["parts"][0]["text"], usage

    # ── Ollama ───────────────────────────────────────────────
    def _call_anthropic(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        request_timeout_seconds: Optional[int] = None,
    ) -> tuple[str, dict]:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return self._error_payload(
                "anthropic",
                model,
                "ANTHROPIC_API_KEY is not set.",
                "Anthropic API error",
                "Add ANTHROPIC_API_KEY to your .env before using Claude models.",
                error_type="provider_error",
            ), {}

        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": model,
            "max_tokens": 2048,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt}
            ],
        }
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=max(1, int(request_timeout_seconds or 60))) as response:
                res_json = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                res_json = json.loads(body)
            except json.JSONDecodeError:
                res_json = {}
            error_info = res_json.get("error", {})
            error_msg = error_info.get("message", body or "Unknown Anthropic error")
            error_type = "provider_error"
            lower = error_msg.lower()
            if "rate limit" in lower or "quota" in lower:
                error_type = "rate_limit"
            fix = (
                "Anthropic rate limit reached. Retry later or switch to another preset/provider."
                if error_type == "rate_limit"
                else "Check ANTHROPIC_API_KEY and Anthropic request format."
            )
            return self._error_payload("anthropic", model, error_msg, "Anthropic API error", fix, error_type=error_type), {}
        except Exception as exc:
            return self._error_payload(
                "anthropic",
                model,
                str(exc),
                "Anthropic API error",
                "Check ANTHROPIC_API_KEY, network, or Anthropic runtime availability.",
                error_type="provider_error",
            ), {}

        parts = res_json.get("content", [])
        text_parts = [
            str(part.get("text", "")).strip()
            for part in parts
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        if text_parts:
            usage_obj = res_json.get("usage", {}) or {}
            usage = {
                "prompt_tokens": usage_obj.get("input_tokens", 0),
                "completion_tokens": usage_obj.get("output_tokens", 0),
            }
            return "\n".join(part for part in text_parts if part), usage
        return self._error_payload(
            "anthropic",
            model,
            json.dumps(res_json),
            "Anthropic API error",
            "Anthropic returned an unexpected response payload.",
            error_type="provider_error",
        ), {}

    # ── Ollama ───────────────────────────────────────────────
    def _call_ollama(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        request_timeout_seconds: Optional[int] = None,
    ) -> tuple[str, dict]:
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
            with request.urlopen(req, timeout=max(1, int(request_timeout_seconds or 120))) as response:
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
            ), {}
        except Exception as exc:
            return self._error_payload(
                "ollama",
                model,
                str(exc),
                "Ollama API error",
                "Make sure the Ollama app/server is running locally on http://127.0.0.1:11434.",
                error_type="provider_error",
            ), {}

        if "response" in res_json:
            usage = {
                "prompt_tokens": res_json.get("prompt_eval_count", 0),
                "completion_tokens": res_json.get("eval_count", 0),
            }
            return res_json["response"], usage
        return self._error_payload(
            "ollama",
            model,
            json.dumps(res_json),
            "Ollama API error",
            "Ollama returned an unexpected response payload.",
            error_type="provider_error",
        ), {}


# Singleton
_client = LLMClient()


def get_llm_client() -> LLMClient:
    return _client
