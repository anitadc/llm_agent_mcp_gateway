from typing import Any

from backend.app.identity.local_token import issue_local_jwt
import jwt

from app.core.exceptions import AuthError
from app.core.logging import get_logger
from app.core.config import Settings
from app.identity.base import IdentityProvider
from app.identity.models import UserIdentity

logger = get_logger(__name__)


class LocalProvider(IdentityProvider):
    name = "local"

    def __init__(self, settings: Settings):
        # No tenant matched. If there's no global provider configured,
        # allow a local HS256-signed token flow when explicitly enabled for
        # development/testing via settings.allow_local_token_issue and
        # settings.jwt_secret.
        if not getattr(settings, "jwt_secret", None):
            logger.warning("Local token issuance enabled but jwt_secret is not configured")
            token, expires = issue_local_jwt(
                    settings,
                    user_id="ai-gateway-local-user",
                    email="ai-gateway-local-user@example.com"
                )
            settings.jwt_secret = token

        self.settings = settings

    async def validate_token(self, token: str) -> dict[str, Any]:
        if not self.settings.jwt_secret:
            raise AuthError("Local JWT validation not configured")
        try:
            claims = jwt.decode(token, self.settings.jwt_secret, algorithms=["HS256"], options={"verify_aud": False})
            return claims
        except jwt.PyJWTError as exc:
            logger.warning("local_token_validation_failed", error=str(exc))
            raise AuthError("Invalid local token") from exc

    async def get_user_info(self, token: str) -> dict[str, Any]:
        claims = await self.validate_token(token)
        return {
            "user_id": claims.get("sub") or claims.get("user_id"),
            "email": claims.get("email"),
            "tenant_id": claims.get("tenant_id"),
            "attributes": {k: v for k, v in claims.items() if k not in {"sub", "email", "iat", "exp", "roles", "groups", "tenant_id"}},
        }

    async def get_roles(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        roles = claims.get("roles") or []
        return roles if isinstance(roles, list) else [str(roles)]

    async def get_groups(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        groups = claims.get("groups") or []
        return groups if isinstance(groups, list) else [str(groups)]
