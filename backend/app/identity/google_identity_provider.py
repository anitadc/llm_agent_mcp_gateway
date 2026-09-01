from typing import Any

from app.core.config import Settings
from app.core.exceptions import AuthError
from app.core.logging import get_logger
from app.identity.base import IdentityProvider, validate_oidc_jwt

logger = get_logger(__name__)


class GoogleIdentityProvider(IdentityProvider):
    """Google Identity Platform / Google Workspace sign-in. `google_workspace_domain`,
    if set, enforces the `hd` (hosted domain) claim so only accounts in that
    Workspace are accepted -- unset accepts any Google Account."""

    name = "google"

    def __init__(self, settings: Settings) -> None:
        self._issuer = "https://accounts.google.com"
        self._jwks_url = "https://www.googleapis.com/oauth2/v3/certs"
        self._audience = settings.google_client_id
        self._workspace_domain = settings.google_workspace_domain

    async def validate_token(self, token: str) -> dict[str, Any]:
        claims = validate_oidc_jwt(token, jwks_url=self._jwks_url, issuer=self._issuer, audience=self._audience)
        if self._workspace_domain and claims.get("hd") != self._workspace_domain:
            logger.warning(
                "google_workspace_domain_mismatch",
                required_domain=self._workspace_domain,
                actual_domain=claims.get("hd"),
            )
            raise AuthError(f"Google account is not a member of the required workspace domain '{self._workspace_domain}'")
        return claims

    async def get_user_info(self, token: str) -> dict[str, Any]:
        claims = await self.validate_token(token)
        return {
            "user_id": claims["sub"],
            "email": claims.get("email"),
            "tenant_id": claims.get("hd"),
            "attributes": {"name": claims.get("name")},
        }

    async def get_roles(self, token: str) -> list[str]:
        # A plain Google ID token carries no roles claim -- Workspace role/org
        # unit assignment lives behind the Admin SDK Directory API, which this
        # provider does not call. See docs/identity-provider-architecture.md.
        await self.validate_token(token)
        return []

    async def get_groups(self, token: str) -> list[str]:
        # Same reasoning as get_roles: Workspace group membership requires an
        # Admin SDK Directory API call, not carried in the ID token itself.
        await self.validate_token(token)
        return []
