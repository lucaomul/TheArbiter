from arbiter.core.agent_runner import AgentRunner


class _Registry:
    def get(self, _role):
        return "system prompt"


def test_run_auditor_falls_back_after_provider_limit(monkeypatch):
    runner = AgentRunner(_Registry())
    monkeypatch.setattr(
        runner,
        "_auditor_candidate_models",
        lambda context=None: ["llama-3.3-70b-versatile", "gemini-2.5-flash"],
    )

    outcomes = {
        "llama-3.3-70b-versatile": {
            "clear": True,
            "questions": [],
            "provider_error": True,
            "provider_limited": True,
            "warning": "Groq rate limit",
            "error_type": "rate_limit",
            "retry_after_seconds": 400,
        },
        "gemini-2.5-flash": {
            "clear": True,
            "questions": [],
        },
    }

    def fake_audit(self, task, llm_options=None):
        assert llm_options == {"max_retries": 0, "request_timeout_seconds": 12}
        return dict(outcomes[self.model])

    cooled_models = []

    monkeypatch.setattr("arbiter.core.agent_runner.AuditorAgent.audit", fake_audit)
    monkeypatch.setattr(runner, "_handle_provider_error", lambda model, result: cooled_models.append(model))

    result, model = runner.run_auditor("Design an API")

    assert model == "gemini-2.5-flash"
    assert result["clear"] is True
    assert result["fallback_used"] is True
    assert result["attempted_models"] == ["llama-3.3-70b-versatile", "gemini-2.5-flash"]
    assert cooled_models == ["llama-3.3-70b-versatile"]
    assert "switched to `gemini-2.5-flash`" in result["warning"]


def test_run_auditor_degrades_gracefully_when_all_candidates_fail(monkeypatch):
    runner = AgentRunner(_Registry())
    monkeypatch.setattr(
        runner,
        "_auditor_candidate_models",
        lambda context=None: ["llama-3.3-70b-versatile", "claude-3-5-haiku-latest"],
    )

    def fake_audit(self, task, llm_options=None):
        return {
            "clear": True,
            "questions": [],
            "provider_error": True,
            "provider_limited": True,
            "warning": "Provider limited",
            "error_type": "rate_limit",
            "retry_after_seconds": 90,
        }

    monkeypatch.setattr("arbiter.core.agent_runner.AuditorAgent.audit", fake_audit)
    monkeypatch.setattr(runner, "_handle_provider_error", lambda model, result: None)

    result, model = runner.run_auditor("Design an API")

    assert model == "claude-3-5-haiku-latest"
    assert result["clear"] is True
    assert result["questions"] == []
    assert result["provider_error"] is True
    assert result["provider_limited"] is True
    assert result["fallback_used"] is True
    assert result["attempted_models"] == ["llama-3.3-70b-versatile", "claude-3-5-haiku-latest"]
    assert "case can still proceed" in result["warning"].lower()
