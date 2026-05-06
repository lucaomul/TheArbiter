from types import SimpleNamespace

from fastapi.testclient import TestClient

from arbiter.api.main import create_app
from arbiter.models.result import ArbiterResult


def _client():
    return TestClient(create_app())


def test_health_route_returns_ok_and_rate_limit_headers(monkeypatch):
    monkeypatch.setenv("ARBITER_ENV", "development")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("ARBITER_RATE_LIMIT_LIMIT", "250")

    response = _client().get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-RateLimit-Limit"] == "250"
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


def test_models_route_returns_registry_payload(monkeypatch):
    monkeypatch.setenv("ARBITER_ENV", "development")
    monkeypatch.delenv("API_KEY", raising=False)

    fake_plugin = SimpleNamespace(
        model_id="demo-model",
        provider="groq",
        roles=["Architect"],
        quality_tier="high",
        cost=0.001,
        enabled=True,
        availability="available",
        source="curated",
        display_name="Demo Model",
    )

    class FakeRegistry:
        def all_model_ids(self):
            return ["demo-model"]

        def get(self, model_id):
            return fake_plugin if model_id == "demo-model" else None

    monkeypatch.setattr("arbiter.api.v1.routers.models.get_plugin_registry", lambda: FakeRegistry())

    response = _client().get("/api/v1/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["models"][0]["model_id"] == "demo-model"


def test_runs_route_uses_mocked_orchestrator(monkeypatch):
    monkeypatch.setenv("ARBITER_ENV", "development")
    monkeypatch.delenv("API_KEY", raising=False)

    class FakeOrchestrator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self, user_input, clarification="", manual_override=""):
            return ArbiterResult(
                best_solution=f"Processed: {user_input}",
                best_score=8.4,
                iteration_count=1,
                costs={"Total": 0.0021},
                iteration_history=[
                    {
                        "iter": 1,
                        "tech": 8,
                        "logic": 9,
                        "avg": 8.4,
                        "ship_readiness": "READY",
                        "verification_status": "VERIFIED",
                    }
                ],
                debug_info={"run_id": "api-test-run"},
            )

    monkeypatch.setattr("arbiter.api.v1.routers.runs.ArbiterOrchestrator", FakeOrchestrator)

    response = _client().post(
        "/api/v1/runs",
        json={
            "user_input": "Write a short memo",
            "task_mode": "Writing & Content",
            "max_iterations": 2,
            "target_score": 8.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "api-test-run"
    assert payload["best_score"] == 8.4
    assert payload["status"] == "completed"
    assert payload["iterations"][0]["verification_status"] == "VERIFIED"


def test_get_run_route_returns_persisted_payload(monkeypatch):
    monkeypatch.setenv("ARBITER_ENV", "development")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setattr("arbiter.api.v1.routers.runs.persistence_available", lambda: True)

    async def fake_get_run(run_id):
        return {
            "id": run_id,
            "best_score": 7.8,
            "best_solution": "Result body",
            "iteration_count": 2,
            "total_cost_usd": 0.003,
            "ship_readiness": "CLOSE",
            "run_metadata": {},
        }

    async def fake_get_run_iterations(run_id):
        return [
            {
                "iteration_number": 1,
                "tech_score": 7,
                "logic_score": 8,
                "avg_score": 7.5,
                "ship_readiness": "CLOSE",
                "verification_status": "CAUTION",
            }
        ]

    monkeypatch.setattr("arbiter.api.v1.routers.runs.db_get_run", fake_get_run)
    monkeypatch.setattr("arbiter.api.v1.routers.runs.db_get_run_iterations", fake_get_run_iterations)

    response = _client().get("/api/v1/runs/run-123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-123"
    assert payload["iterations"][0]["avg_score"] == 7.5


def test_production_routes_require_api_key(monkeypatch):
    monkeypatch.setenv("ARBITER_ENV", "production")
    monkeypatch.delenv("API_KEY", raising=False)

    response = _client().get("/api/v1/health")

    assert response.status_code == 401


def test_production_routes_allow_valid_api_key(monkeypatch):
    monkeypatch.setenv("ARBITER_ENV", "production")
    monkeypatch.setenv("API_KEY", "super-secret")

    response = _client().get("/api/v1/health", headers={"X-API-Key": "super-secret"})

    assert response.status_code == 200
