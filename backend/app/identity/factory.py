from typing import Any

import jwt

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.identity.base import IdentityProvider

logger = get_logger(__name__)

PROVIDER_NAMES = ["keycloak", "entra", "auth0", "okta", "aws_identity", "google"]


def _build_provider(name: str, settings: Settings) -> IdentityProvider:
    """The only place in the app that knows which concrete IdentityProvider
    class backs a given provider name. Every provider module is imported
    lazily, inside its own branch, mirroring app/secrets/factory.py."""
    if name == "keycloak":
        from app.identity.keycloak_provider import KeycloakProvider

        return KeycloakProvider(settings)
    if name == "entra":
        from app.identity.entra_provider import EntraProvider

        return EntraProvider(settings)
    if name == "auth0":
        from app.identity.auth0_provider import Auth0Provider

        return Auth0Provider(settings)
    if name == "okta":
        from app.identity.okta_provider import OktaProvider

        return OktaProvider(settings)
    if name == "aws_identity":
        from app.identity.aws_identity_provider import AWSIdentityProvider

        return AWSIdentityProvider(settings)
    if name == "google":
        from app.identity.google_identity_provider import GoogleIdentityProvider

        return GoogleIdentityProvider(settings)
    logger.error("unknown_identity_provider", provider=name)
    raise ValueError(f"Unknown IDENTITY_PROVIDER '{name}'")


def get_identity_provider(settings: Settings | None = None) -> IdentityProvider:
    """The default, single-tenant path: whichever provider IDENTITY_PROVIDER
    selects. See build_provider_from_tenant_config for the multi-tenant path."""
    settings = settings or get_settings()
    return _build_provider(settings.identity_provider, settings)


def build_provider_from_tenant_config(provider_name: str, configuration: dict[str, Any], settings: Settings) -> IdentityProvider:
    """Multi-tenant path (see docs/identity-provider-architecture.md): builds a
    one-off provider from a `tenant_identity_config` row's stored
    `configuration` instead of global Settings, by overlaying just that
    tenant's fields onto a copy of Settings. `configuration` keys are Settings
    field names (e.g. {"entra_tenant_id": "...", "entra_client_id": "..."}) --
    this is what lets Customer A authenticate via Entra and Customer B via
    Keycloak against the same running gateway process."""
    overridden = settings.model_copy(update=configuration)
    return _build_provider(provider_name, overridden)


def peek_unverified_issuer(token: str) -> str | None:
    """Reads the `iss` claim WITHOUT verifying the signature. Used only to
    decide which tenant's IdentityProvider should attempt real,
    signature-verified validation next -- never trusted for authentication or
    authorization by itself; the actual provider still fully validates the
    token afterwards."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False, "verify_aud": False, "verify_exp": False})
        return claims.get("iss")
    except jwt.PyJWTError as exc:
        logger.warning("issuer_peek_failed", reason=str(exc))
        return None


def is_provider_available(name: str, settings: Settings) -> bool:
    """Static config-presence check (NOT a live connectivity probe) -- just
    enough for the admin UI to show which providers this deployment is even
    configured for."""
    if name == "keycloak":
        return bool(settings.keycloak_base_url and settings.keycloak_realm and settings.keycloak_client_id)
    if name == "entra":
        return bool(settings.entra_tenant_id and settings.entra_client_id)
    if name == "auth0":
        return bool(settings.auth0_domain)
    if name == "okta":
        return bool(settings.okta_domain)
    if name == "aws_identity":
        return bool(settings.aws_sso_region)
    if name == "google":
        return bool(settings.google_client_id)
    return False


def list_provider_metadata(settings: Settings | None = None) -> list[dict]:
    settings = settings or get_settings()
    return [{"name": name, "available": is_provider_available(name, settings)} for name in PROVIDER_NAMES]
