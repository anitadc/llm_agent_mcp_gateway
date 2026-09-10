import json

import httpx
import pytest
import respx

from app.core.config import Settings
from app.services.guardrails.http_client import HttpGuardrailsClient


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        valkey_url="redis://localhost:6379/1",
        keycloak_base_url="http://localhost:8080",
        keycloak_realm="tcsaigateway",
        keycloak_client_id="tcsaigateway-frontend",
        keycloak_audience="tcsaigateway-backend",
        guardrails_base_url="http://guardrails.test",
        api_key_secret_pepper="pepper",
    )


@pytest.mark.asyncio
@respx.mock
async def test_check_prompt_sends_expected_payload() -> None:
    route = respx.post("http://guardrails.test/v1/guardrails/check").mock(
        return_value=httpx.Response(200, json={"allowed": True, "masked_text": "hello", "violations": []})
    )
    client = HttpGuardrailsClient(_settings())

    verdict = await client.check_prompt("hello", {"project_id": "p1", "request_id": "r1"})

    assert verdict.allowed is True
    assert verdict.masked_text == "hello"
    sent_payload = json.loads(route.calls[0].request.content)
    assert sent_payload["direction"] == "prompt"
    assert sent_payload["text"] == "hello"


@pytest.mark.asyncio
@respx.mock
async def test_check_response_reports_violations() -> None:
    respx.post("http://guardrails.test/v1/guardrails/check").mock(
        return_value=httpx.Response(
            200,
            json={"allowed": False, "masked_text": "[redacted]", "violations": [{"type": "pii_detected", "detail": "email"}]},
        )
    )
    client = HttpGuardrailsClient(_settings())

    verdict = await client.check_response("my email is a@b.com", {"project_id": "p1", "request_id": "r1"})

    assert verdict.allowed is False
    assert verdict.violations[0]["type"] == "pii_detected"


@pytest.mark.asyncio
@respx.mock
async def test_transient_error_is_retried() -> None:
    route = respx.post("http://guardrails.test/v1/guardrails/check")
    route.side_effect = [
        httpx.ConnectError("boom"),
        httpx.Response(200, json={"allowed": True, "masked_text": "hi", "violations": []}),
    ]
    client = HttpGuardrailsClient(_settings())

    verdict = await client.check_prompt("hi", {"project_id": "p1", "request_id": "r1"})

    assert verdict.allowed is True
    assert route.call_count == 2
