from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.identity.entra_provider import EntraProvider

CLAIMS = {
    "oid": "entra-oid-1",
    "sub": "app-specific-sub",
    "preferred_username": "bob@contoso.com",
    "tid": "tenant-guid-123",
    "roles": ["finance-admin"],
    "groups": ["group-guid-1"],
    "name": "Bob Smith",
}


def _settings(**overrides) -> Settings:
    defaults = dict(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        valkey_url="redis://localhost:6379/1",
        keycloak_base_url="http://localhost:8080",
        keycloak_realm="gateway",
        keycloak_client_id="gateway-frontend",
        keycloak_audience="gateway-backend",
        guardrails_base_url="http://localhost:9000",
        api_key_secret_pepper="pepper",
        entra_tenant_id="default-tenant",
        entra_client_id="entra-client-1",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _provider_with_claims(claims: dict, **settings_overrides) -> EntraProvider:
    provider = EntraProvider(_settings(**settings_overrides))
    provider.validate_token = AsyncMock(return_value=claims)
    return provider


@pytest.mark.asyncio
async def test_get_user_info_prefers_oid_over_sub_and_reads_tid_as_tenant() -> None:
    provider = _provider_with_claims(CLAIMS)

    info = await provider.get_user_info("token")

    assert info["user_id"] == "entra-oid-1"
    assert info["email"] == "bob@contoso.com"
    assert info["tenant_id"] == "tenant-guid-123"


@pytest.mark.asyncio
async def test_get_roles_reads_the_app_roles_claim() -> None:
    provider = _provider_with_claims(CLAIMS)

    assert await provider.get_roles("token") == ["finance-admin"]


@pytest.mark.asyncio
async def test_get_groups_reads_the_groups_claim() -> None:
    provider = _provider_with_claims(CLAIMS)

    assert await provider.get_groups("token") == ["group-guid-1"]


@pytest.mark.asyncio
async def test_falls_back_to_configured_tenant_id_when_tid_claim_is_missing() -> None:
    provider = _provider_with_claims({"sub": "s1", "email": "x@contoso.com"}, entra_tenant_id="fallback-tenant")

    info = await provider.get_user_info("token")

    assert info["tenant_id"] == "fallback-tenant"


@pytest.mark.asyncio
async def test_falls_back_to_sub_when_oid_is_missing() -> None:
    provider = _provider_with_claims({"sub": "s1", "email": "x@contoso.com"})

    info = await provider.get_user_info("token")

    assert info["user_id"] == "s1"
