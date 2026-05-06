from unittest.mock import patch

from arbiter.agents.base_agent import BaseAgent
from arbiter.infra.llm_client import LLMResult


def test_normalize_does_not_inflate_scores_from_risks():
    result = BaseAgent.normalize({"score": 4, "critique": "risk", "risks": ["possible issue"]})
    assert result["score"] == 4


def test_clean_json_handles_fenced_payload():
    raw = '```json\n{"score": 7, "critique": "ok", "fix_suggestion": "none"}\n```'
    parsed = BaseAgent.clean_json(raw)
    assert parsed["score"] == 7
    assert parsed["critique"] == "ok"


def test_clean_json_returns_parse_error_payload():
    parsed = BaseAgent.clean_json("not json at all")
    assert parsed["parse_error"] is True
    assert parsed["score"] == 1


def test_is_cacheable_response_rejects_provider_errors():
    payload = '{"score":1,"critique":"LLM call failed: boom","provider_error":true,"error_type":"rate_limit"}'
    assert BaseAgent.is_cacheable_response(payload) is False


def test_error_payload_detects_provider_failure():
    payload = '{"score":1,"critique":"Groq API error: no quota","provider_error":true,"error_type":"rate_limit"}'
    parsed = BaseAgent.error_payload(payload)
    assert parsed["provider_error"] is True
    assert parsed["error_type"] == "rate_limit"


def test_run_uses_cache_after_first_generation():
    agent = BaseAgent(name="Test", provider="openai", model="gpt-4o-mini", system_prompt="system")
    agent._cache.clear()
    llm_result = LLMResult(
        success=True,
        text="hello",
        error_type=None,
        provider="openai",
        model="gpt-4o-mini",
        retry_after_seconds=None,
    )
    with patch.object(agent._client, "generate_result", return_value=llm_result) as mocked_generate:
        first = agent.run("task")
        second = agent.run("task")
    assert first == "hello"
    assert second == "hello"
    assert mocked_generate.call_count == 1


def test_is_cacheable_response_rejects_failed_llm_result():
    llm_result = LLMResult(
        success=False,
        text='{"provider_error": true, "error_type": "rate_limit"}',
        error_type="rate_limit",
        provider="groq",
        model="demo",
        retry_after_seconds=1,
    )

    assert BaseAgent.is_cacheable_response(llm_result.text, llm_result=llm_result) is False
