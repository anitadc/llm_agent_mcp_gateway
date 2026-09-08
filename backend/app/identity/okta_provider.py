from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger, log_method
from app.identity.base import IdentityProvider, validate_oidc_jwt

logger = get_logger(__name__)


class OktaProvider(IdentityProvider):
    """Okta Workforce Identity Cloud, default Authorization Server. Workforce
    Identity conventionally uses group membership itself as the RBAC signal --
    the same `groups` claim backs both `.roles` and `.groups` here unless the
    tenant's Authorization Server is configured with a distinct `roles` claim."""

    name = "okta"

    def __init__(self, settings: Settings) -> None:
        self._domain = settings.okta_domain
        self._issuer = f"https://{self._domain}/oauth2/default"
        self._jwks_url = f"{self._issuer}/v1/keys"
        self._audience = settings.okta_audience

    @log_method(logger)
    async def validate_token(self, token: str) -> dict[str, Any]:
        return validate_oidc_jwt(token, jwks_url=self._jwks_url, issuer=self._issuer, audience=self._audience)

    @log_method(logger)
    async def get_user_info(self, token: str) -> dict[str, Any]:
        claims = await self.validate_token(token)
        return {
            "user_id": claims["sub"],
            "email": claims.get("email"),
            "tenant_id": self._domain,
            "attributes": {"name": claims.get("name")},
        }

    @log_method(logger)
    async def get_roles(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        return list(claims.get("roles", claims.get("groups", [])))

    @log_method(logger)
    async def get_groups(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        return list(claims.get("groups", []))
