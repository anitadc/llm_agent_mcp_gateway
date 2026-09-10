from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.identity.auth0_provider import Auth0Provider


def _settings(**overrides) -> Settings:
    defaults = dict(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        valkey_url="redis://localhost:6379/1",
        keycloak_base_url="http://localhost:8080",
        keycloak_realm="tcsaigateway",
        keycloak_client_id="tcsaigateway-frontend",
        keycloak_audience="tcsaigateway-backend",
        guardrails_base_url="http://localhost:9000",
        api_key_secret_pepper="pepper",
        auth0_domain="tenant.auth0.com",
        auth0_client_id="auth0-client-1",
        auth0_roles_claim="https://llm-gateway/roles",
        auth0_groups_claim="https://llm-gateway/groups",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _provider_with_claims(claims: dict, **settings_overrides) -> Auth0Provider:
    provider = Auth0Provider(_settings(**settings_overrides))
    provider.validate_token = AsyncMock(return_value=claims)
    return provider


@pytest.mark.asyncio
async def test_get_user_info_uses_the_domain_as_tenant_id() -> None:
    provider = _provider_with_claims({"sub": "auth0|123", "email": "carol@example.com", "nickname": "carol"})

    info = await provider.get_user_info("token")

    assert info["user_id"] == "auth0|123"
    assert info["email"] == "carol@example.com"
    assert info["tenant_id"] == "tenant.auth0.com"


@pytest.mark.asyncio
async def test_get_roles_reads_the_configured_namespaced_claim() -> None:
    provider = _provider_with_claims(
        {"sub": "auth0|123", "https://llm-gateway/roles": ["viewer"], "https://llm-gateway/groups": ["eng"]}
    )

    assert await provider.get_roles("token") == ["viewer"]
    assert await provider.get_groups("token") == ["eng"]


@pytest.mark.asyncio
async def test_missing_custom_claims_default_to_empty() -> None:
    provider = _provider_with_claims({"sub": "auth0|123", "email": "carol@example.com"})

    assert await provider.get_roles("token") == []
    assert await provider.get_groups("token") == []


@pytest.mark.asyncio
async def test_respects_a_differently_configured_claim_namespace() -> None:
    provider = _provider_with_claims(
        {"sub": "auth0|123", "https://custom/roles": ["billing-admin"]},
        auth0_roles_claim="https://custom/roles",
    )

    assert await provider.get_roles("token") == ["billing-admin"]
