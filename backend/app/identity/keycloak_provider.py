from typing import Any

from app.core.config import Settings
from app.identity.base import IdentityProvider, validate_oidc_jwt


class KeycloakProvider(IdentityProvider):
    """Default provider. OpenID Connect via JWKS discovery, realm-scoped.
    Client roles (per-application, under `resource_access.{client_id}.roles`)
    are unioned with realm roles (`realm_access.roles`) -- an enterprise realm
    often grants app-specific roles at the client level rather than realm-wide."""

    name = "keycloak"

    def __init__(self, settings: Settings) -> None:
        self._realm = settings.keycloak_realm
        self._client_id = settings.keycloak_client_id
        self._jwks_url = settings.keycloak_jwks_url
        self._issuer = f"{settings.keycloak_base_url}/realms/{settings.keycloak_realm}"
        self._audience = settings.keycloak_audience

    async def validate_token(self, token: str) -> dict[str, Any]:
        return validate_oidc_jwt(token, jwks_url=self._jwks_url, issuer=self._issuer, audience=self._audience)

    async def get_user_info(self, token: str) -> dict[str, Any]:
        claims = await self.validate_token(token)
        return {
            "user_id": claims["sub"],
            "email": claims.get("email"),
            "tenant_id": self._realm,
            "attributes": {"preferred_username": claims.get("preferred_username")},
        }

    async def get_roles(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        realm_roles = set(claims.get("realm_access", {}).get("roles", []))
        client_roles = set(claims.get("resource_access", {}).get(self._client_id, {}).get("roles", []))
        return sorted(realm_roles | client_roles)

    async def get_groups(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        return list(claims.get("groups", []))
