from typing import Any

from app.core.config import Settings
from app.core.logging import get_logger, log_method
from app.identity.base import IdentityProvider, validate_oidc_jwt

logger = get_logger(__name__)


class AWSIdentityProvider(IdentityProvider):
    """AWS IAM Identity Center (successor to AWS SSO), OIDC-flavored SSO tokens.

    Scope note: IAM Identity Center's authorization model (permission sets) is
    not carried inside the SSO token itself -- resolving "what can this user do
    in AWS" requires calling the Identity Store / SSO Admin API with the
    instance ARN, which this provider does not do. What IS implemented is the
    generically-useful slice: validating that an already-issued token is
    genuinely signed by this IAM Identity Center instance (JWKS-based, same as
    every other provider here) and extracting whatever roles/groups claims the
    customer's specific trust-broker configuration happens to inject. See
    docs/identity-provider-architecture.md for the full reasoning and the
    extension point for a deeper integration.
    """

    name = "aws_identity"

    def __init__(self, settings: Settings) -> None:
        self._instance_arn = settings.aws_sso_instance_arn
        self._issuer = f"https://oidc.{settings.aws_sso_region}.amazonaws.com"
        self._jwks_url = f"{self._issuer}/.well-known/jwks.json"
        # IAM Identity Center doesn't issue a fixed audience the way most OIDC
        # providers do; there is nothing generically correct to check here.
        self._audience = None

    @log_method(logger)
    async def validate_token(self, token: str) -> dict[str, Any]:
        return validate_oidc_jwt(token, jwks_url=self._jwks_url, issuer=self._issuer, audience=self._audience)

    @log_method(logger)
    async def get_user_info(self, token: str) -> dict[str, Any]:
        claims = await self.validate_token(token)
        return {
            "user_id": claims["sub"],
            "email": claims.get("email"),
            "tenant_id": self._instance_arn,
            "attributes": {},
        }

    @log_method(logger)
    async def get_roles(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        return list(claims.get("roles", []))

    @log_method(logger)
    async def get_groups(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        return list(claims.get("groups", []))
