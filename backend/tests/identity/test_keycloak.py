from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.identity.keycloak_provider import KeycloakProvider

CLAIMS = {
    "sub": "abc-123",
    "email": "alice@example.com",
    "preferred_username": "alice",
    "realm_access": {"roles": ["admin", "offline_access"]},
    "resource_access": {"gateway-frontend": {"roles": ["finance-user"]}},
    "groups": ["/finance", "/finance/reporting"],
}


def _settings(**overrides) -> Settings:
    defaults = dict(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        valkey_url="redis://localhost:6379/1",
        keycloak_base_url="https://kc.test",
        keycloak_realm="gateway",
        keycloak_client_id="gateway-frontend",
        keycloak_audience="gateway-backend",
        guardrails_base_url="http://localhost:9000",
        api_key_secret_pepper="pepper",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _provider_with_claims(claims: dict) -> KeycloakProvider:
    provider = KeycloakProvider(_settings())
    provider.validate_token = AsyncMock(return_value=claims)
    return provider


@pytest.mark.asyncio
async def test_get_user_info_maps_sub_email_and_realm_as_tenant() -> None:
    provider = _provider_with_claims(CLAIMS)

    info = await provider.get_user_info("token")

    assert info["user_id"] == "abc-123"
    assert info["email"] == "alice@example.com"
    assert info["tenant_id"] == "gateway"


@pytest.mark.asyncio
async def test_get_roles_unions_realm_and_client_roles() -> None:
    provider = _provider_with_claims(CLAIMS)

    roles = await provider.get_roles("token")

    assert set(roles) == {"admin", "offline_access", "finance-user"}


@pytest.mark.asyncio
async def test_get_groups_reads_groups_claim() -> None:
    provider = _provider_with_claims(CLAIMS)

    groups = await provider.get_groups("token")

    assert groups == ["/finance", "/finance/reporting"]


@pytest.mark.asyncio
async def test_get_user_identity_composes_the_full_identity() -> None:
    provider = _provider_with_claims(CLAIMS)

    identity = await provider.get_user_identity("token")

    assert identity.user_id == "abc-123"
    assert identity.provider == "keycloak"
    assert identity.tenant_id == "gateway"
    assert set(identity.roles) == {"admin", "offline_access", "finance-user"}
    assert identity.groups == ["/finance", "/finance/reporting"]


@pytest.mark.asyncio
async def test_missing_groups_and_client_roles_default_to_empty() -> None:
    provider = _provider_with_claims({"sub": "x", "email": "x@example.com", "realm_access": {"roles": []}})

    assert await provider.get_roles("token") == []
    assert await provider.get_groups("token") == []
