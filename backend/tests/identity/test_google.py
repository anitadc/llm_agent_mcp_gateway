from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.core.exceptions import AuthError
from app.identity.google_identity_provider import GoogleIdentityProvider


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
        google_client_id="google-client-1",
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.mark.asyncio
async def test_get_user_info_uses_hd_claim_as_tenant_id() -> None:
    provider = GoogleIdentityProvider(_settings())
    with patch("app.identity.google_identity_provider.validate_oidc_jwt", return_value={"sub": "g-1", "email": "frank@example.com", "hd": "example.com", "name": "Frank"}):
        info = await provider.get_user_info("token")

    assert info["user_id"] == "g-1"
    assert info["tenant_id"] == "example.com"


@pytest.mark.asyncio
async def test_roles_and_groups_are_empty_by_design() -> None:
    """A plain Google ID token carries no roles/groups -- Workspace RBAC
    requires an Admin SDK Directory API call this provider does not make."""
    provider = GoogleIdentityProvider(_settings())
    with patch("app.identity.google_identity_provider.validate_oidc_jwt", return_value={"sub": "g-1", "email": "frank@example.com"}):
        assert await provider.get_roles("token") == []
        assert await provider.get_groups("token") == []


@pytest.mark.asyncio
async def test_workspace_domain_restriction_accepts_matching_domain() -> None:
    provider = GoogleIdentityProvider(_settings(google_workspace_domain="example.com"))
    with patch("app.identity.google_identity_provider.validate_oidc_jwt", return_value={"sub": "g-1", "hd": "example.com"}):
        claims = await provider.validate_token("token")
    assert claims["sub"] == "g-1"


@pytest.mark.asyncio
async def test_workspace_domain_restriction_rejects_a_different_domain() -> None:
    provider = GoogleIdentityProvider(_settings(google_workspace_domain="example.com"))
    with patch("app.identity.google_identity_provider.validate_oidc_jwt", return_value={"sub": "g-1", "hd": "other.com"}):
        with pytest.raises(AuthError):
            await provider.validate_token("token")
