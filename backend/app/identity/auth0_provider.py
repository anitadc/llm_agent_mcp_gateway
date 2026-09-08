from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger, log_method
from app.identity.base import IdentityProvider, validate_oidc_jwt

logger = get_logger(__name__)


class Auth0Provider(IdentityProvider):
    """Auth0. Domain-based issuer/JWKS discovery. Auth0 has no standard
    roles/groups claim -- RBAC is conventionally surfaced via a namespaced
    custom claim the tenant configures in an Auth0 Action/Rule, so the claim
    names themselves are configurable (AUTH0_ROLES_CLAIM/AUTH0_GROUPS_CLAIM)
    rather than fixed like Entra's `roles`."""

    name = "auth0"

    def __init__(self, settings: Settings) -> None:
        self._domain = settings.auth0_domain
        self._issuer = f"https://{self._domain}/"
        self._jwks_url = f"https://{self._domain}/.well-known/jwks.json"
        self._audience = settings.auth0_audience or settings.auth0_client_id
        self._roles_claim = settings.auth0_roles_claim
        self._groups_claim = settings.auth0_groups_claim

    @log_method(logger)
    async def validate_token(self, token: str) -> dict[str, Any]:
        return validate_oidc_jwt(token, jwks_url=self._jwks_url, issuer=self._issuer, audience=self._audience)

    @log_method(logger)
    async def get_user_info(self, token: str) -> dict[str, Any]:
        claims = await self.validate_token(token)
        return {
            "user_id": claims["sub"],
            "email": claims.get("email"),
            # Auth0's tenant boundary IS the domain (one tenant per Auth0
            # "domain"), unlike Entra where tenant is a claim inside one shared issuer.
            "tenant_id": self._domain,
            "attributes": {"nickname": claims.get("nickname")},
        }

    @log_method(logger)
    async def get_roles(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        return list(claims.get(self._roles_claim, []))

    @log_method(logger)
    async def get_groups(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        return list(claims.get(self._groups_claim, []))
