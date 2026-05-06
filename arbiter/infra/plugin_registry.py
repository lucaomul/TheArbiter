"""
Plugin-based model registry with live catalog overlay.

Curated models remain the trusted defaults. A cached live catalog can:
- mark deprecated models unavailable
- surface newly discovered models
- resolve stable aliases to the best currently available model
"""

from dataclasses import dataclass, field
from typing import Optional

from arbiter.config.settings import PRICES
from arbiter.infra.model_catalog import get_model_catalog


DEFAULT_MODEL_ALIASES = {
    "openai_primary": {
        "provider": "openai",
        "preferred": "gpt-4o",
        "quality_tier": "high",
    },
    "openai_fast": {
        "provider": "openai",
        "preferred": "gpt-4o-mini",
        "quality_tier": "mid",
    },
    "anthropic_primary": {
        "provider": "anthropic",
        "preferred": "claude-sonnet-4-20250514",
        "quality_tier": "high",
    },
    "anthropic_fast": {
        "provider": "anthropic",
        "preferred": "claude-3-5-haiku-latest",
        "quality_tier": "mid",
    },
    "gemini_primary": {
        "provider": "gemini",
        "preferred": "gemini-2.5-pro",
        "quality_tier": "high",
    },
    "gemini_fast": {
        "provider": "gemini",
        "preferred": "gemini-2.5-flash",
        "quality_tier": "mid",
    },
    "groq_primary": {
        "provider": "groq",
        "preferred": "llama-3.3-70b-versatile",
        "quality_tier": "high",
    },
    "groq_fast": {
        "provider": "groq",
        "preferred": "llama-3.1-8b-instant",
        "quality_tier": "mid",
    },
    "ollama_primary": {
        "provider": "ollama",
        "preferred": "",
        "quality_tier": "high",
    },
}


@dataclass
class ModelPlugin:
    model_id: str
    provider: str
    cost: float
    quality_tier: str
    roles: list[str]
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    display_name: Optional[str] = None
    source: str = "curated"
    discovered: bool = False
    availability: str = "unknown"
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.display_name is None:
            self.display_name = self.model_id


_REGISTRY: list[ModelPlugin] = [
    ModelPlugin(
        model_id="gpt-4o",
        provider="openai",
        cost=0.015,
        quality_tier="high",
        roles=["Architect", "Repair"],
        tags=["strong", "expensive"],
    ),
    ModelPlugin(
        model_id="gpt-4o-mini",
        provider="openai",
        cost=0.0006,
        quality_tier="mid",
        roles=["Architect", "Repair", "Auditor"],
        tags=["cheap", "fast"],
    ),
    ModelPlugin(
        model_id="claude-sonnet-4-20250514",
        provider="anthropic",
        cost=0.003,
        quality_tier="high",
        roles=["Architect", "Auditor", "Tech Critic", "Logic Critic", "Repair"],
        tags=["strong", "reasoning", "premium"],
    ),
    ModelPlugin(
        model_id="claude-3-5-haiku-latest",
        provider="anthropic",
        cost=0.0008,
        quality_tier="mid",
        roles=["Auditor", "Tech Critic", "Logic Critic", "Janitor", "Repair"],
        tags=["fast", "balanced"],
    ),
    ModelPlugin(
        model_id="gemini-2.5-pro",
        provider="gemini",
        cost=0.003,
        quality_tier="high",
        roles=["Tech Critic", "Auditor"],
        tags=["strong"],
    ),
    ModelPlugin(
        model_id="gemini-2.5-flash",
        provider="gemini",
        cost=0.0001,
        quality_tier="mid",
        roles=["Tech Critic", "Auditor", "Logic Critic"],
        tags=["cheap", "fast"],
    ),
    ModelPlugin(
        model_id="gemini-1.5-pro",
        provider="gemini",
        cost=0.003,
        quality_tier="mid",
        roles=["Tech Critic", "Auditor"],
        enabled=False,
        tags=["stable"],
    ),
    ModelPlugin(
        model_id="gemini-1.5-flash",
        provider="gemini",
        cost=0.0001,
        quality_tier="low",
        roles=["Tech Critic", "Auditor"],
        enabled=False,
        tags=["cheap", "fast"],
    ),
    ModelPlugin(
        model_id="llama-3.3-70b-versatile",
        provider="groq",
        cost=0.000001,
        quality_tier="high",
        roles=["Logic Critic", "Architect", "Auditor", "Repair", "Janitor", "Tech Critic"],
        tags=["cheap", "fast", "strong"],
    ),
    ModelPlugin(
        model_id="llama-3.1-8b-instant",
        provider="groq",
        cost=0.000001,
        quality_tier="low",
        roles=["Repair", "Janitor", "Architect", "Auditor", "Tech Critic", "Logic Critic"],
        tags=["cheap", "fast"],
    ),
]


class PluginRegistry:
    def __init__(self, plugins: list[ModelPlugin] = None):
        base_plugins = plugins or _REGISTRY
        self._base_plugins = {plugin.model_id: self._clone_plugin(plugin) for plugin in base_plugins}
        self._plugins: dict[str, ModelPlugin] = {}
        self._aliases = {}
        self._provider_states = {}
        self._catalog = {}
        self._catalog_store = get_model_catalog()
        self._rebuild_registry()
        self.refresh_from_catalog(self._catalog_store.load())

    @staticmethod
    def _clone_plugin(plugin: ModelPlugin) -> ModelPlugin:
        return ModelPlugin(
            model_id=plugin.model_id,
            provider=plugin.provider,
            cost=float(plugin.cost),
            quality_tier=plugin.quality_tier,
            roles=list(plugin.roles or []),
            enabled=bool(plugin.enabled),
            tags=list(plugin.tags or []),
            display_name=plugin.display_name,
            source=plugin.source,
            discovered=bool(plugin.discovered),
            availability=plugin.availability,
            metadata=dict(plugin.metadata or {}),
        )

    def _rebuild_registry(self):
        self._plugins = {
            model_id: self._clone_plugin(plugin)
            for model_id, plugin in self._base_plugins.items()
        }
        self._aliases = {
            alias: config.get("preferred", "")
            for alias, config in DEFAULT_MODEL_ALIASES.items()
        }

    def sync_catalog_if_needed(self, force: bool = False) -> dict:
        catalog = self._catalog_store.sync_if_needed(force=force)
        self.refresh_from_catalog(catalog)
        return catalog

    def sync_catalog(self, force: bool = False) -> dict:
        catalog = self._catalog_store.sync_all() if force else self._catalog_store.sync_if_needed()
        self.refresh_from_catalog(catalog)
        return catalog

    def refresh_from_catalog(self, catalog: dict = None):
        self._rebuild_registry()
        self._catalog = catalog or {"providers": {}, "updated_at": ""}
        self._provider_states = dict((self._catalog.get("providers") or {}))

        for provider, state in self._provider_states.items():
            models = list(state.get("models", []) or [])
            discovered_ids = {str(item.get("id", "")).strip() for item in models if str(item.get("id", "")).strip()}
            status_ok = state.get("status") == "ok"

            if status_ok:
                for plugin in self._plugins.values():
                    if plugin.provider != provider:
                        continue
                    if plugin.model_id.startswith("ollama:"):
                        continue
                    if plugin.model_id not in discovered_ids:
                        plugin.enabled = False
                        plugin.availability = "deprecated"
                        plugin.metadata["catalog_note"] = "Missing from the latest provider catalog."
                    else:
                        plugin.availability = "available"
                        plugin.metadata["catalog_note"] = ""

            for item in models:
                model_id = str(item.get("id", "")).strip()
                if not model_id:
                    continue
                existing = self._plugins.get(model_id)
                if existing:
                    existing.availability = str(item.get("availability", existing.availability or "available"))
                    existing.metadata.update(dict(item.get("metadata", {}) or {}))
                    existing.metadata["discovered_by_catalog"] = True
                    existing.display_name = item.get("display_name") or existing.display_name
                    continue

                plugin = ModelPlugin(
                    model_id=model_id,
                    provider=provider,
                    cost=float(PRICES.get(model_id, 0.001)),
                    quality_tier=str(item.get("quality_tier", "mid")),
                    roles=list(item.get("roles", [])),
                    enabled=bool(item.get("enabled", False)),
                    tags=list(item.get("tags", [])),
                    display_name=item.get("display_name") or model_id,
                    source="discovered",
                    discovered=True,
                    availability=str(item.get("availability", "available")),
                    metadata=dict(item.get("metadata", {}) or {}),
                )
                self._plugins[model_id] = plugin

        self._refresh_alias_targets()

    def _refresh_alias_targets(self):
        for alias, config in DEFAULT_MODEL_ALIASES.items():
            preferred = str(config.get("preferred", "")).strip()
            provider = str(config.get("provider", "")).strip()
            quality_tier = str(config.get("quality_tier", "mid")).strip()
            selected = ""
            if preferred and self.is_model_available(preferred):
                selected = preferred
            else:
                selected = self._best_provider_candidate(
                    provider=provider,
                    quality_tier=quality_tier,
                )
            self._aliases[alias] = selected or preferred

    def _best_provider_candidate(self, provider: str, quality_tier: str = "", role: str = "") -> str:
        candidates = []
        for plugin in self._plugins.values():
            if provider and plugin.provider != provider:
                continue
            if role and role not in plugin.roles:
                continue
            if not self.is_model_available(plugin.model_id):
                continue
            candidates.append(plugin)

        quality_order = {"high": 0, "mid": 1, "low": 2}

        def sort_key(plugin: ModelPlugin):
            target_quality = quality_order.get(quality_tier or plugin.quality_tier, 1)
            return (
                abs(quality_order.get(plugin.quality_tier, 1) - target_quality),
                0 if plugin.source == "curated" else 1,
                plugin.cost,
                plugin.model_id,
            )

        ordered = sorted(candidates, key=sort_key)
        return ordered[0].model_id if ordered else ""

    @staticmethod
    def _family_hint(model_id: str) -> str:
        model = str(model_id or "").lower()
        for token in (
            "sonnet",
            "haiku",
            "opus",
            "flash",
            "pro",
            "mini",
            "instant",
            "llama",
            "gpt-oss",
            "gpt-4o",
            "gpt-5",
        ):
            if token in model:
                return token
        if "/" in model:
            return model.split("/", 1)[0]
        return model.split("-", 1)[0]

    def resolve_model_id(self, model_id: str) -> str:
        value = str(model_id or "").strip()
        if not value:
            return value
        if value.startswith("alias:"):
            return str(self._aliases.get(value.split(":", 1)[-1], "")).strip() or value
        return str(self._aliases.get(value, value)).strip()

    def get(self, model_id: str) -> Optional[ModelPlugin]:
        return self._plugins.get(self.resolve_model_id(model_id))

    def provider_for(self, model_id: str, fallback: str = "openai") -> str:
        model_name = self.resolve_model_id(model_id)
        if model_name.startswith("ollama:"):
            return "ollama"
        plugin = self._plugins.get(model_name)
        return plugin.provider if plugin else fallback

    def cost_for(self, model_id: str) -> float:
        plugin = self.get(model_id)
        return plugin.cost if plugin else 0.001

    def provider_state(self, provider: str) -> dict:
        return dict(self._provider_states.get(str(provider or "").strip(), {}))

    def aliases(self) -> dict:
        return dict(self._aliases)

    def is_model_available(self, model_id: str) -> bool:
        plugin = self.get(model_id)
        if plugin is None:
            return False
        if not plugin.enabled:
            return False
        if str(plugin.availability or "").lower() in {"deprecated", "unavailable"}:
            return False
        return True

    def is_selectable(self, model_id: str, role: str = "") -> bool:
        plugin = self.get(model_id)
        if plugin is None:
            return False
        if role and role not in plugin.roles:
            return False
        return self.is_model_available(plugin.model_id)

    def recommended_replacement(self, model_id: str, role: str = "") -> str:
        resolved = self.resolve_model_id(model_id)
        plugin = self.get(resolved)
        provider = plugin.provider if plugin else self.provider_for(resolved, "")
        quality_tier = plugin.quality_tier if plugin else "mid"
        family = self._family_hint(resolved)

        candidates = []
        for candidate in self._plugins.values():
            if provider and candidate.provider != provider:
                continue
            if role and role not in candidate.roles:
                continue
            if not self.is_model_available(candidate.model_id):
                continue
            if candidate.model_id == resolved:
                continue
            candidates.append(candidate)

        quality_order = {"high": 0, "mid": 1, "low": 2}

        def sort_key(candidate: ModelPlugin):
            return (
                0 if self._family_hint(candidate.model_id) == family else 1,
                abs(quality_order.get(candidate.quality_tier, 1) - quality_order.get(quality_tier, 1)),
                0 if candidate.source == "curated" else 1,
                candidate.cost,
                candidate.model_id,
            )

        ordered = sorted(candidates, key=sort_key)
        return ordered[0].model_id if ordered else ""

    def candidates_for_role(self, role: str, enabled_only: bool = True) -> list[ModelPlugin]:
        candidates = [
            plugin for plugin in self._plugins.values()
            if role in plugin.roles
        ]
        if enabled_only:
            candidates = [plugin for plugin in candidates if self.is_model_available(plugin.model_id)]
        return sorted(candidates, key=lambda plugin: (plugin.provider, plugin.cost, plugin.model_id))

    def discovered_models(self, provider: str = "") -> list[ModelPlugin]:
        discovered = [plugin for plugin in self._plugins.values() if plugin.discovered]
        if provider:
            discovered = [plugin for plugin in discovered if plugin.provider == provider]
        return list(discovered)

    def all_model_ids(self) -> list[str]:
        return sorted(self._plugins.keys())

    def register(self, plugin: ModelPlugin):
        cloned = self._clone_plugin(plugin)
        self._base_plugins[cloned.model_id] = cloned
        self._plugins[cloned.model_id] = self._clone_plugin(cloned)

    def register_alias(self, alias: str, model_id: str):
        self._aliases[str(alias or "").strip()] = self.resolve_model_id(model_id)

    def disable(self, model_id: str):
        resolved = self.resolve_model_id(model_id)
        if resolved in self._plugins:
            self._plugins[resolved].enabled = False
        if resolved in self._base_plugins:
            self._base_plugins[resolved].enabled = False

    def enable(self, model_id: str):
        resolved = self.resolve_model_id(model_id)
        if resolved in self._plugins:
            self._plugins[resolved].enabled = True
        if resolved in self._base_plugins:
            self._base_plugins[resolved].enabled = True


_registry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    return _registry


def provider_for_model(model_id: str, fallback: str = "openai") -> str:
    return _registry.provider_for(model_id, fallback)
