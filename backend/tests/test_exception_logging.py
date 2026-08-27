import json

import pytest

from app.api.v1.health import get_readiness
from app.core.config import Settings
from app.core.logging import configure_logging, get_logger
from app.middleware.auth_middleware import AuthMiddleware


class _BrokenDb:
    async def execute(self, *args, **kwargs):
        raise RuntimeError("db down")


class _BrokenValkey:
    async def ping(self):
        raise RuntimeError("valkey down")


def test_structlog_configuration_handles_normal_info_events() -> None:
    configure_logging("INFO")
    logger = get_logger("test")
    logger.info("checking LLM secret status", admin_user_id="user-1", provider="infisical")


@pytest.mark.asyncio
async def test_readiness_logs_exception(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_exception(message: str, **kwargs):
        calls.append((message, kwargs))

    monkeypatch.setattr("app.api.v1.health.logger.exception", fake_exception)
    monkeypatch.setattr("app.api.v1.health.valkey_client", _BrokenValkey())

    response = await get_readiness(_BrokenDb(), Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        valkey_url="redis://localhost:6379/1",
        keycloak_base_url="http://localhost:8080",
        keycloak_realm="gateway",
        keycloak_client_id="gateway-frontend",
        keycloak_audience="gateway-backend",
        guardrails_base_url="http://localhost:9000",
        api_key_secret_pepper="pepper",
    ))

    assert response.status_code == 503
    assert any("db health check failed" in message for message, _ in calls)


@pytest.mark.asyncio
async def test_readiness_skips_unconfigured_infisical_provider(monkeypatch) -> None:
    class _HealthyDb:
        async def execute(self, *args, **kwargs):
            return None

    class _HealthyValkey:
        async def ping(self):
            return True

    class _FakeResponse:
        status_code = 200

    async def fake_get(self, url):
        return _FakeResponse()

    monkeypatch.setattr("app.api.v1.health.valkey_client", _HealthyValkey())
    monkeypatch.setattr("app.api.v1.health.httpx.AsyncClient.get", fake_get)

    response = await get_readiness(_HealthyDb(), Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        valkey_url="redis://localhost:6379/1",
        keycloak_base_url="http://localhost:8080",
        keycloak_realm="gateway",
        keycloak_client_id="gateway-frontend",
        keycloak_audience="gateway-backend",
        guardrails_base_url="http://localhost:9000",
        api_key_secret_pepper="pepper",
        secret_provider=None,
    ))

    payload = json.loads(response.body)
    assert payload["infisical"] == "skipped"
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_middleware_logs_unexpected_exception(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_exception(message: str, **kwargs):
        calls.append((message, kwargs))

    monkeypatch.setattr("app.middleware.auth_middleware.logger.exception", fake_exception)

    class _BrokenTokenProvider:
        async def get_user_identity(self, token: str):
            raise RuntimeError("broken identity provider")

    async def _resolve_provider(*args, **kwargs):
        return _BrokenTokenProvider()

    request = type("Request", (), {"url": type("Url", (), {"path": "/api/test"})(), "headers": {}, "state": type("State", (), {})()})()
    middleware = AuthMiddleware(app=None)
    middleware._resolve_provider = _resolve_provider

    response = await middleware.dispatch(request, lambda req: None)

    assert response.status_code == 401
    assert any("Unexpected auth failure" in message for message, _ in calls)
