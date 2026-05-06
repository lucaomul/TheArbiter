import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib import error, parse, request

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency in test/minimal environments
    def load_dotenv(*_args, **_kwargs):
        return False


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = PROJECT_ROOT / ".arbiter_memory"
CATALOG_PATH = CATALOG_DIR / "model_catalog.json"
logger = logging.getLogger(__name__)
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _looks_like_text_model(provider: str, model_id: str) -> bool:
    model = str(model_id or "").strip().lower()
    if not model:
        return False

    blocked_fragments = [
        "embedding",
        "image",
        "tts",
        "transcribe",
        "whisper",
        "audio",
        "moderation",
        "safeguard",
        "guard",
    ]
    if any(fragment in model for fragment in blocked_fragments):
        return False

    if provider == "openai":
        if model.startswith("ft:"):
            return False
        if "realtime" in model:
            return False
    if provider == "gemini":
        if "native-audio" in model or "live" in model:
            return False
    return True


def infer_quality_tier(provider: str, model_id: str) -> str:
    model = str(model_id or "").lower()
    if any(token in model for token in ("opus", "sonnet", "70b", "120b", "gpt-5", "gpt-4o", "2.5-pro", "3-pro")):
        return "high"
    if any(token in model for token in ("flash", "mini", "haiku", "8b", "20b", "lite")):
        return "mid"
    if provider == "groq" and "llama" in model:
        return "mid"
    return "mid"


def infer_roles(provider: str, model_id: str) -> list[str]:
    model = str(model_id or "").lower()

    if provider == "gemini":
        roles = ["Auditor", "Tech Critic", "Logic Critic"]
        if "pro" in model:
            roles.append("Architect")
        return roles
    if provider == "openai":
        roles = ["Architect", "Auditor", "Tech Critic", "Logic Critic", "Repair"]
        if "mini" in model:
            roles.append("Janitor")
        return roles
    if provider == "anthropic":
        return ["Architect", "Auditor", "Tech Critic", "Logic Critic", "Janitor", "Repair"]
    if provider == "groq":
        return ["Architect", "Auditor", "Tech Critic", "Logic Critic", "Janitor", "Repair"]
    if provider == "ollama":
        return ["Architect", "Auditor", "Tech Critic", "Logic Critic", "Janitor", "Repair"]
    return ["Architect", "Auditor", "Tech Critic", "Logic Critic"]


def infer_tags(provider: str, model_id: str) -> list[str]:
    model = str(model_id or "").lower()
    tags = [provider]
    if any(token in model for token in ("mini", "flash", "haiku", "instant", "8b", "lite")):
        tags.append("fast")
    if any(token in model for token in ("pro", "sonnet", "opus", "70b", "120b")):
        tags.append("strong")
    if "preview" in model or "exp" in model or "experimental" in model:
        tags.append("preview")
    return sorted(set(tags))


def _is_auto_enabled(provider: str, model_id: str) -> bool:
    model = str(model_id or "").lower()
    if not _looks_like_text_model(provider, model):
        return False
    if "preview" in model or "experimental" in model or model.endswith("-exp"):
        return False
    return True


class ModelCatalog:
    def __init__(self, path: Path = None):
        self.path = path or CATALOG_PATH
        self.refresh_hours = max(1, int(float(os.getenv("ARBITER_MODEL_SYNC_HOURS", "12"))))
        self.request_timeout = max(2, int(float(os.getenv("ARBITER_MODEL_SYNC_TIMEOUT_SECONDS", "6"))))
        self.enabled = str(os.getenv("ARBITER_ENABLE_MODEL_SYNC", "1")).strip().lower() not in {
            "0", "false", "no", "off"
        }
        self._fallback_catalog = self._default_catalog()
        self._storage_warning_emitted = False

    def _default_catalog(self) -> dict:
        return {
            "updated_at": "",
            "providers": {},
        }

    def _ensure_storage(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                self.path.write_text(json.dumps(self._default_catalog(), indent=2), encoding="utf-8")
            return True
        except Exception:
            if not self._storage_warning_emitted:
                logger.warning("model_catalog_storage_unavailable")
                self._storage_warning_emitted = True
            return False

    def load(self) -> dict:
        if not self._ensure_storage():
            return dict(self._fallback_catalog)
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                return self._default_catalog()
            data = json.loads(raw)
            if isinstance(data, dict):
                data.setdefault("providers", {})
                data.setdefault("updated_at", "")
                self._fallback_catalog = dict(data)
                return data
        except Exception:
            logger.warning("model_catalog_load_failed")
        return dict(self._fallback_catalog)

    def save(self, catalog: dict):
        self._fallback_catalog = dict(catalog or self._default_catalog())
        if not self._ensure_storage():
            return
        try:
            self.path.write_text(json.dumps(catalog, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            logger.warning("model_catalog_save_failed")

    def is_stale(self, catalog: dict) -> bool:
        updated_at = _parse_timestamp(catalog.get("updated_at", ""))
        if updated_at is None:
            return True
        return datetime.utcnow() - updated_at >= timedelta(hours=self.refresh_hours)

    def sync_if_needed(self, force: bool = False) -> dict:
        catalog = self.load()
        if not self.enabled and not force:
            return catalog
        if force or self.is_stale(catalog):
            return self.sync_all()
        return catalog

    def sync_all(self, providers: list[str] = None) -> dict:
        catalog = self.load()
        sync_providers = providers or ["openai", "anthropic", "gemini", "groq", "ollama"]
        for provider in sync_providers:
            catalog["providers"][provider] = self._sync_provider(provider)
        catalog["updated_at"] = _utc_now_iso()
        self.save(catalog)
        return catalog

    def _sync_provider(self, provider: str) -> dict:
        discoverer = getattr(self, f"_discover_{provider}", None)
        if discoverer is None:
            return {
                "status": "unsupported",
                "updated_at": _utc_now_iso(),
                "models": [],
                "error": f"No discoverer implemented for provider `{provider}`.",
            }
        try:
            models = discoverer()
            return {
                "status": "ok",
                "updated_at": _utc_now_iso(),
                "models": models,
                "error": "",
            }
        except RuntimeError as exc:
            return {
                "status": "skipped",
                "updated_at": _utc_now_iso(),
                "models": [],
                "error": str(exc),
            }
        except error.URLError as exc:
            return {
                "status": "error",
                "updated_at": _utc_now_iso(),
                "models": [],
                "error": str(exc),
            }
        except Exception as exc:
            logger.warning("model_catalog_provider_sync_failed")
            return {
                "status": "error",
                "updated_at": _utc_now_iso(),
                "models": [],
                "error": str(exc),
            }

    @staticmethod
    def _http_json(url: str, headers: dict = None, timeout: int = 6) -> dict:
        req = request.Request(url, headers=headers or {}, method="GET")
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _normalize_model(self, provider: str, model_id: str, display_name: str = "", metadata: dict = None) -> dict:
        return {
            "id": model_id,
            "display_name": display_name or model_id,
            "provider": provider,
            "quality_tier": infer_quality_tier(provider, model_id),
            "roles": infer_roles(provider, model_id),
            "tags": infer_tags(provider, model_id),
            "enabled": _is_auto_enabled(provider, model_id),
            "availability": "available",
            "metadata": metadata or {},
        }

    def _discover_openai(self) -> list[dict]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        payload = self._http_json(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=self.request_timeout,
        )
        models = []
        for item in payload.get("data", []):
            model_id = str(item.get("id", "")).strip()
            if not _looks_like_text_model("openai", model_id):
                continue
            models.append(self._normalize_model("openai", model_id))
        return sorted(models, key=lambda item: item["id"])

    def _discover_groq(self) -> list[dict]:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set.")
        payload = self._http_json(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=self.request_timeout,
        )
        models = []
        for item in payload.get("data", []):
            model_id = str(item.get("id", "")).strip()
            if not _looks_like_text_model("groq", model_id):
                continue
            models.append(self._normalize_model("groq", model_id))
        return sorted(models, key=lambda item: item["id"])

    def _discover_anthropic(self) -> list[dict]:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        payload = self._http_json(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=self.request_timeout,
        )
        models = []
        for item in payload.get("data", []):
            model_id = str(item.get("id", "")).strip()
            if not _looks_like_text_model("anthropic", model_id):
                continue
            models.append(
                self._normalize_model(
                    "anthropic",
                    model_id,
                    display_name=str(item.get("display_name", "")).strip() or model_id,
                )
            )
        return sorted(models, key=lambda item: item["id"])

    def _discover_gemini(self) -> list[dict]:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")
        query = parse.urlencode({"key": api_key})
        payload = self._http_json(
            f"https://generativelanguage.googleapis.com/v1beta/models?{query}",
            timeout=self.request_timeout,
        )
        models = []
        for item in payload.get("models", []):
            name = str(item.get("name", "")).strip()
            model_id = name.split("/", 1)[-1] if "/" in name else name
            methods = item.get("supportedGenerationMethods", []) or []
            if "generateContent" not in methods:
                continue
            if not _looks_like_text_model("gemini", model_id):
                continue
            models.append(
                self._normalize_model(
                    "gemini",
                    model_id,
                    display_name=str(item.get("displayName", "")).strip() or model_id,
                    metadata={"supported_generation_methods": methods},
                )
            )
        return sorted(models, key=lambda item: item["id"])

    def _discover_ollama(self) -> list[dict]:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        payload = self._http_json(f"{base_url}/api/tags", timeout=self.request_timeout)
        models = []
        for item in payload.get("models", []):
            model_id = str(item.get("name", "")).strip()
            if not _looks_like_text_model("ollama", model_id):
                continue
            models.append(self._normalize_model("ollama", f"ollama:{model_id}", display_name=model_id))
        return sorted(models, key=lambda item: item["id"])


_catalog = ModelCatalog()


def get_model_catalog() -> ModelCatalog:
    return _catalog
