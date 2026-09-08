import time
from typing import Any

import jwt

from app.core.config import Settings
from app.core.logging import get_logger, log_method

logger = get_logger(__name__)


@log_method(logger)
def issue_local_jwt(settings: Settings, *, user_id: str, email: str, roles: list[str] | None = None, groups: list[str] | None = None, tenant_id: str | None = None, expires_seconds: int = 3600) -> tuple[str, int]:
    """Issues a HS256-signed JWT using `settings.jwt_secret`.

    Returns (token, expires_in_seconds).
    """
    if not settings.jwt_secret:
        raise RuntimeError("Local JWT issuance is not configured (missing jwt_secret)")

    now = int(time.time())
    exp = now + expires_seconds
    claims: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": exp,
    }
    if tenant_id is not None:
        claims["tenant_id"] = tenant_id
    if roles:
        claims["roles"] = roles
    if groups:
        claims["groups"] = groups

    token = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    return token, expires_seconds
