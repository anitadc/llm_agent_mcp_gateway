from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.identity.aws_identity_provider import AWSIdentityProvider


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
        aws_sso_region="us-east-1",
        aws_sso_instance_arn="arn:aws:sso:::instance/ssoins-123",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _provider_with_claims(claims: dict) -> AWSIdentityProvider:
    provider = AWSIdentityProvider(_settings())
    provider.validate_token = AsyncMock(return_value=claims)
    return provider


@pytest.mark.asyncio
async def test_get_user_info_uses_instance_arn_as_tenant_id() -> None:
    provider = _provider_with_claims({"sub": "aws-user-1", "email": "grace@example.com"})

    info = await provider.get_user_info("token")

    assert info["user_id"] == "aws-user-1"
    assert info["tenant_id"] == "arn:aws:sso:::instance/ssoins-123"


@pytest.mark.asyncio
async def test_get_roles_and_groups_read_whatever_claims_the_trust_broker_injects() -> None:
    provider = _provider_with_claims({"sub": "aws-user-1", "roles": ["ReadOnlyAccess"], "groups": ["finance-team"]})

    assert await provider.get_roles("token") == ["ReadOnlyAccess"]
    assert await provider.get_groups("token") == ["finance-team"]


@pytest.mark.asyncio
async def test_missing_role_and_group_claims_default_to_empty() -> None:
    """Permission sets aren't carried in the SSO token itself -- see the
    provider's own docstring and docs/identity-provider-architecture.md."""
    provider = _provider_with_claims({"sub": "aws-user-1"})

    assert await provider.get_roles("token") == []
    assert await provider.get_groups("token") == []
