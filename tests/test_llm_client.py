from arbiter.infra.llm_client import LLMClient


def test_generate_result_retries_rate_limit_then_succeeds(monkeypatch):
    client = LLMClient()
    attempts = {"count": 0}
    sleeps = []

    def fake_call(model, system_prompt, user_prompt, temperature):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return (
                client._error_payload(
                    "gemini",
                    model,
                    "Rate limit reached, try again in 1s",
                    "Gemini API error",
                    "Retry later.",
                    error_type="rate_limit",
                    retry_after_seconds=1,
                ),
                {},
            )
        return "Recovered response", {"prompt_tokens": 10, "completion_tokens": 5}

    monkeypatch.setattr(client, "_call_gemini", fake_call)
    monkeypatch.setattr("arbiter.infra.llm_client.time.sleep", lambda seconds: sleeps.append(seconds))

    result = client.generate_result(
        provider="gemini",
        model="gemini-2.5-flash",
        system_prompt="system",
        user_prompt="user",
        agent_name="Test Agent",
    )

    assert result.success is True
    assert result.text == "Recovered response"
    assert attempts["count"] == 2
    assert sleeps == [1]


def test_generate_result_stops_after_max_rate_limit_retries(monkeypatch):
    client = LLMClient()
    attempts = {"count": 0}
    sleeps = []

    def fake_call(model, system_prompt, user_prompt, temperature):
        attempts["count"] += 1
        return (
            client._error_payload(
                "anthropic",
                model,
                "Rate limit reached",
                "Anthropic API error",
                "Retry later.",
                error_type="rate_limit",
            ),
            {},
        )

    monkeypatch.setattr(client, "_call_anthropic", fake_call)
    monkeypatch.setattr("arbiter.infra.llm_client.time.sleep", lambda seconds: sleeps.append(seconds))

    result = client.generate_result(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        system_prompt="system",
        user_prompt="user",
        agent_name="Test Agent",
    )

    assert result.success is False
    assert result.error_type == "rate_limit"
    assert attempts["count"] == 3
    assert sleeps == [1, 2]
