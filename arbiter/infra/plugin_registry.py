"""
Plugin-based model registry.
Adding a new model requires zero code changes — only a config entry here.
"""

from dataclasses import dataclass, field
from typing import Optional


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
        self._plugins = {p.model_id: p for p in (plugins or _REGISTRY)}

    def get(self, model_id: str) -> Optional[ModelPlugin]:
        return self._plugins.get(model_id)

    def provider_for(self, model_id: str, fallback: str = "openai") -> str:
        model_name = str(model_id or "").strip()
        if model_name.startswith("ollama:"):
            return "ollama"
        plugin = self._plugins.get(model_name)
        return plugin.provider if plugin else fallback

    def cost_for(self, model_id: str) -> float:
        plugin = self._plugins.get(model_id)
        return plugin.cost if plugin else 0.001

    def candidates_for_role(self, role: str, enabled_only: bool = True) -> list[ModelPlugin]:
        return [
            p for p in self._plugins.values()
            if role in p.roles and (not enabled_only or p.enabled)
        ]

    def all_model_ids(self) -> list[str]:
        return list(self._plugins.keys())

    def register(self, plugin: ModelPlugin):
        self._plugins[plugin.model_id] = plugin

    def disable(self, model_id: str):
        if model_id in self._plugins:
            self._plugins[model_id].enabled = False

    def enable(self, model_id: str):
        if model_id in self._plugins:
            self._plugins[model_id].enabled = True


_registry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    return _registry


def provider_for_model(model_id: str, fallback: str = "openai") -> str:
    return _registry.provider_for(model_id, fallback)
