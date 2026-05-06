from arbiter.config.settings import SETTINGS
from arbiter.infra.model_selector import ModelSelector
from arbiter.infra.plugin_registry import ModelPlugin


class FakeRegistry:
    def __init__(self, plugins):
        self._plugins = {plugin.model_id: plugin for plugin in plugins}

    def resolve_model_id(self, model_id: str) -> str:
        return model_id

    def is_selectable(self, model_id: str, agent: str) -> bool:
        plugin = self._plugins.get(model_id)
        return bool(plugin and plugin.enabled and agent in plugin.roles)

    def recommended_replacement(self, model_id: str, agent: str) -> str:
        for plugin in self.candidates_for_role(agent):
            if plugin.model_id != model_id:
                return plugin.model_id
        return ""

    def candidates_for_role(self, agent: str):
        return [plugin for plugin in self._plugins.values() if agent in plugin.roles]

    def cost_for(self, model_id: str) -> float:
        plugin = self._plugins.get(model_id)
        return float(plugin.cost if plugin else 0.0)


class FakePerf:
    def __init__(self, scores):
        self.scores = scores

    def average_score(self, agent: str, model: str) -> float:
        return float(self.scores.get((agent, model), 5.0))


def _selector():
    plugins = [
        ModelPlugin("model-high", "openai", 0.02, "high", ["Architect"]),
        ModelPlugin("model-mid", "openai", 0.01, "mid", ["Architect"]),
        ModelPlugin("model-groq", "groq", 0.005, "mid", ["Architect"]),
    ]
    selector = ModelSelector()
    selector._registry = FakeRegistry(plugins)
    selector._perf = FakePerf(
        {
            ("Architect", "model-high"): 8.5,
            ("Architect", "model-mid"): 7.0,
            ("Architect", "model-groq"): 6.5,
        }
    )
    selector._overrides = {}
    selector._cooldowns = {}
    selector._provider_lock = ""
    return selector


def test_choose_respects_manual_override():
    selector = _selector()
    selector.set_override("Architect", "model-mid")

    model_id, provider = selector.choose("Architect", context={})

    assert model_id == "model-mid"
    assert provider == "openai"


def test_choose_force_quality_prefers_high_tier():
    selector = _selector()

    model_id, provider = selector.choose("Architect", context={"force_quality": True, "stable_mode": False})

    assert model_id == "model-high"
    assert provider == "openai"


def test_choose_respects_provider_lock():
    selector = _selector()
    selector.set_provider_lock("groq")

    model_id, provider = selector.choose("Architect", context={})

    assert model_id == "model-groq"
    assert provider == "groq"


def test_choose_uses_exploration_when_enabled(monkeypatch):
    selector = _selector()
    monkeypatch.setattr("arbiter.infra.model_selector.random.random", lambda: 0.0)
    monkeypatch.setattr("arbiter.infra.model_selector.random.choice", lambda seq: seq[-1])
    monkeypatch.setattr(SETTINGS, "exploration_rate", 1.0)

    model_id, _provider = selector.choose("Architect", context={"stable_mode": False})

    assert model_id == "model-groq"


def test_fallback_models_skip_current_and_cooldown():
    selector = _selector()
    selector.mark_temporarily_unavailable("model-mid", seconds=60)

    fallbacks = selector.fallback_models("Architect", current_model="model-high")

    assert "model-high" not in fallbacks
    assert "model-mid" not in fallbacks
    assert fallbacks[0] == "model-groq"
