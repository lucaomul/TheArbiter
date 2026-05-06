import asyncio
import time

import pytest
from fastapi import HTTPException

from arbiter.api.dependencies import require_api_key


def _run_require_api_key(**kwargs):
    return asyncio.run(require_api_key(**kwargs))


def test_require_api_key_allows_dev_without_configured_key(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("API_KEY_EXPIRES_AT", raising=False)
    monkeypatch.setenv("ARBITER_ENV", "development")

    assert _run_require_api_key(x_api_key=None, authorization=None) is None


def test_require_api_key_fails_closed_in_production_when_missing(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("API_KEY_EXPIRES_AT", raising=False)
    monkeypatch.setenv("ARBITER_ENV", "production")

    with pytest.raises(HTTPException) as exc:
        _run_require_api_key(x_api_key=None, authorization=None)

    assert exc.value.status_code == 401
    assert "required in production" in exc.value.detail.lower()


def test_require_api_key_accepts_valid_bearer_token(monkeypatch):
    monkeypatch.setenv("ARBITER_ENV", "production")
    monkeypatch.setenv("API_KEY", "secret-token")
    monkeypatch.delenv("API_KEY_EXPIRES_AT", raising=False)

    assert _run_require_api_key(x_api_key=None, authorization="Bearer secret-token") is None


def test_require_api_key_rejects_malformed_authorization_header(monkeypatch):
    monkeypatch.setenv("ARBITER_ENV", "production")
    monkeypatch.setenv("API_KEY", "secret-token")
    monkeypatch.delenv("API_KEY_EXPIRES_AT", raising=False)

    with pytest.raises(HTTPException) as exc:
        _run_require_api_key(x_api_key=None, authorization="Token secret-token")

    assert exc.value.status_code == 401
    assert "malformed" in exc.value.detail.lower()


def test_require_api_key_rejects_expired_configured_key(monkeypatch):
    monkeypatch.setenv("ARBITER_ENV", "production")
    monkeypatch.setenv("API_KEY", "secret-token")
    monkeypatch.setenv("API_KEY_EXPIRES_AT", str(time.time() - 60))

    with pytest.raises(HTTPException) as exc:
        _run_require_api_key(x_api_key="secret-token", authorization=None)

    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()
