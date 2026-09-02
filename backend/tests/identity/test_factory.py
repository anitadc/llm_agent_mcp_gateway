import jwt
import pytest

from app.core.config import Settings
from app.identity.auth0_provider import Auth0Provider
from app.identity.aws_identity_provider import AWSIdentityProvider
from app.identity.entra_provider import EntraProvider
from app.identity.factory import (
    build_provider_from_tenant_config,
    get_identity_provider,
    is_provider_available,
    list_provider_metadata,
    peek_unverified_issuer,
)
from app.identity.google_identity_provider import GoogleIdentityProvider
from app.identity.keycloak_provider import KeycloakProvider
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
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.mark.parametrize(
    ("provider_name", "expected_type", "overrides"),
    [
        ("keycloak", KeycloakProvider, {}),
        ("entra", EntraProvider, {"entra_tenant_id": "t1", "entra_client_id": "c1"}),
        ("auth0", Auth0Provider, {"auth0_domain": "tenant.auth0.com"}),
        ("okta", OktaProvider, {"okta_domain": "dev-1.okta.com"}),
        ("aws_identity", AWSIdentityProvider, {"aws_sso_region": "us-east-1"}),
        ("google", GoogleIdentityProvider, {"google_client_id": "g1"}),
    ],
)
def test_factory_returns_the_configured_provider_type(provider_name, expected_type, overrides) -> None:
    settings = _settings(identity_provider=provider_name, **overrides)
    assert isinstance(get_identity_provider(settings), expected_type)


def test_factory_accepts_none_as_an_explicitly_disabled_provider() -> None:
    settings = _settings(identity_provider=None)
    assert settings.identity_provider is None
    with pytest.raises(ValueError, match="IDENTITY_PROVIDER.*configured"):
        get_identity_provider(settings)
def test_factory_falls_back_to_the_first_configured_provider_when_identity_provider_is_blank() -> None:
    settings = _settings(identity_provider=None)
    assert settings.identity_provider is None
    assert isinstance(get_identity_provider(settings), KeycloakProvider)


def test_factory_rejects_an_unknown_provider() -> None:
    settings = _settings()
    settings.identity_provider = "unknown-provider"
    with pytest.raises(ValueError):
        get_identity_provider(settings)


def test_list_provider_metadata_reports_all_six() -> None:
    metadata = list_provider_metadata(_settings())
    assert {m["name"] for m in metadata} == {"keycloak", "entra", "auth0", "okta", "aws_identity", "google"}


def test_is_provider_available_reflects_config_presence() -> None:
    settings = _settings()
    assert is_provider_available("entra", settings) is False
    assert is_provider_available("keycloak", settings) is True  # keycloak_* are required fields, always present

    configured = _settings(entra_tenant_id="t1", entra_client_id="c1")
    assert is_provider_available("entra", configured) is True


def test_peek_unverified_issuer_reads_iss_without_verifying_signature() -> None:
    token = jwt.encode({"iss": "https://issuer.example.com", "sub": "x"}, "irrelevant-key", algorithm="HS256")
    assert peek_unverified_issuer(token) == "https://issuer.example.com"


def test_peek_unverified_issuer_returns_none_for_garbage_input() -> None:
    assert peek_unverified_issuer("not-a-jwt-at-all") is None


def test_build_provider_from_tenant_config_overlays_settings_for_that_tenant() -> None:
    base = _settings(identity_provider="keycloak")

    provider = build_provider_from_tenant_config(
        "entra", {"entra_tenant_id": "tenant-x", "entra_client_id": "client-x"}, base
    )

    assert isinstance(provider, EntraProvider)
    assert provider._tenant_id == "tenant-x"


def test_build_provider_from_tenant_config_does_not_mutate_the_base_settings() -> None:
    base = _settings(identity_provider="keycloak")

    build_provider_from_tenant_config("entra", {"entra_tenant_id": "tenant-x", "entra_client_id": "client-x"}, base)

    assert base.identity_provider == "keycloak"
    assert base.entra_tenant_id is None
