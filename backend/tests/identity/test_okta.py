from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.identity.okta_provider import OktaProvider


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
        okta_domain="dev-123.okta.com",
        okta_client_id="okta-client-1",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _provider_with_claims(claims: dict) -> OktaProvider:
    provider = OktaProvider(_settings())
    provider.validate_token = AsyncMock(return_value=claims)
    return provider


@pytest.mark.asyncio
async def test_get_user_info_uses_the_domain_as_tenant_id() -> None:
    provider = _provider_with_claims({"sub": "00u1", "email": "dave@example.com", "name": "Dave"})

    info = await provider.get_user_info("token")

    assert info["user_id"] == "00u1"
    assert info["tenant_id"] == "dev-123.okta.com"


@pytest.mark.asyncio
async def test_get_roles_prefers_an_explicit_roles_claim_when_present() -> None:
    provider = _provider_with_claims({"sub": "00u1", "groups": ["Engineering"], "roles": ["app-admin"]})

    assert await provider.get_roles("token") == ["app-admin"]


@pytest.mark.asyncio
async def test_get_roles_falls_back_to_groups_when_no_roles_claim_is_configured() -> None:
    """Okta Workforce Identity conventionally uses group membership itself as
    the RBAC signal -- most tenants never configure a distinct roles claim."""
    provider = _provider_with_claims({"sub": "00u2", "groups": ["Engineering", "Billing"]})

    assert await provider.get_roles("token") == ["Engineering", "Billing"]


@pytest.mark.asyncio
async def test_get_groups_reads_the_groups_claim() -> None:
    provider = _provider_with_claims({"sub": "00u1", "groups": ["Engineering"]})

    assert await provider.get_groups("token") == ["Engineering"]
