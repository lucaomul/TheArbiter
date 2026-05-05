import hashlib
import json
from typing import Optional


class ResponseCache:
    """
    In-memory cache for LLM responses.
    Avoids duplicate API calls for identical prompts.
    """

    def __init__(self):
        self._store: dict[str, str] = {}

    def _make_key(self, provider: str, model: str, prompt: str) -> str:
        raw = json.dumps({"provider": provider, "model": model, "prompt": prompt}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, provider: str, model: str, prompt: str) -> Optional[str]:
        key = self._make_key(provider, model, prompt)
        return self._store.get(key)

    def set(self, provider: str, model: str, prompt: str, response: str):
        key = self._make_key(provider, model, prompt)
        self._store[key] = response

    def clear(self):
        self._store.clear()

    def size(self) -> int:
        return len(self._store)


# Singleton instance shared across the app session
_cache = ResponseCache()


def get_cache() -> ResponseCache:
    return _cache
