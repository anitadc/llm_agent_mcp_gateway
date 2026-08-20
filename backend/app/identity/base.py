from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

import jwt

from app.core.exceptions import AuthError
from app.identity.models import UserIdentity


@lru_cache(maxsize=32)
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url)


def validate_oidc_jwt(token: str, *, jwks_url: str, issuer: str | None, audience: str | None) -> dict[str, Any]:
    """Shared signature/issuer/audience/expiry validation for every OIDC-based
    provider (Keycloak, Entra ID, Auth0, Okta, Google, and AWS IAM Identity
    Center's OIDC-flavored SSO tokens) -- the one piece of genuinely
    provider-agnostic logic among them, implemented exactly once instead of
    once per provider. JWKS signing keys are cached per URL (same convention the
    pre-abstraction Keycloak-only validator already used), so repeated
    validation only costs a JWKS network fetch once per key set, not per call.
    """
    try:
        client = _jwks_client(jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={
                "verify_exp": True,
                "verify_aud": audience is not None,
                "verify_iss": issuer is not None,
            },
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"Token validation failed: {exc}") from exc


class IdentityProvider(ABC):
    """Every enterprise IdP (Keycloak, Entra ID, Auth0, Okta, AWS IAM Identity
    Center, Google Identity) implements this contract. Nothing outside
    app/identity/ imports a concrete provider class -- callers always go
    through get_identity_provider() (factory.py) and, from there, only
    get_user_identity(), never the four primitives directly."""

    name: str = "unknown"

    @abstractmethod
    async def validate_token(self, token: str) -> dict[str, Any]:
        """Returns the verified JWT claims. Raises AuthError on any failure
        (bad signature, expired, wrong issuer/audience)."""
        ...

    @abstractmethod
    async def get_user_info(self, token: str) -> dict[str, Any]:
        """Returns at least {"user_id": ..., "email": ..., "tenant_id": ...};
        may include "attributes" (dict) for anything provider-specific."""
        ...

    @abstractmethod
    async def get_roles(self, token: str) -> list[str]:
        ...

    @abstractmethod
    async def get_groups(self, token: str) -> list[str]:
        ...

    async def get_user_identity(self, token: str) -> UserIdentity:
        """Composes the four provider-specific primitives above into the
        provider-agnostic UserIdentity. Concrete, not abstract -- every
        provider gets this for free; there is exactly one place that knows how
        to assemble it, so a new provider only ever has to implement the four
        primitives, never this composition."""
        user_info = await self.get_user_info(token)
        roles = await self.get_roles(token)
        groups = await self.get_groups(token)
        return UserIdentity(
            user_id=user_info["user_id"],
            email=user_info.get("email"),
            tenant_id=user_info.get("tenant_id"),
            provider=self.name,
            roles=roles,
            groups=groups,
            attributes=user_info.get("attributes", {}),
        )
