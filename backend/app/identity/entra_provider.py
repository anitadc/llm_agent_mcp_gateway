from typing import Any

from app.core.config import Settings
from app.identity.base import IdentityProvider, validate_oidc_jwt


class EntraProvider(IdentityProvider):
    """Microsoft Entra ID (Azure AD), v2.0 endpoint. Tenant-scoped issuer/JWKS."""

    name = "entra"

    def __init__(self, settings: Settings) -> None:
        tenant_id = settings.entra_tenant_id
        self._tenant_id = tenant_id
        self._jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        self._issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        self._audience = settings.entra_client_id

    async def validate_token(self, token: str) -> dict[str, Any]:
        return validate_oidc_jwt(token, jwks_url=self._jwks_url, issuer=self._issuer, audience=self._audience)

    async def get_user_info(self, token: str) -> dict[str, Any]:
        claims = await self.validate_token(token)
        return {
            # `oid` is stable per user across app registrations; `sub` is
            # per-application and would silently change if the App
            # Registration is ever recreated, so prefer `oid` when present.
            "user_id": claims.get("oid") or claims["sub"],
            "email": claims.get("preferred_username") or claims.get("email"),
            "tenant_id": claims.get("tid", self._tenant_id),
            "attributes": {"name": claims.get("name")},
        }

    async def get_roles(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        # App roles assigned to the user/group in the App Registration's manifest.
        return list(claims.get("roles", []))

    async def get_groups(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        # A user in more group memberships than Entra's inline-claim limit
        # triggers a "groups overage" (`_claim_names`/`hasgroups` instead of a
        # populated `groups` array), which requires a follow-up Microsoft Graph
        # call this provider does not make -- see
        # docs/identity-provider-architecture.md.
        return list(claims.get("groups", []))
