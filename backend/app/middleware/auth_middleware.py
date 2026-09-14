from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.exceptions import AuthError, GatewayException
from app.core.logging import get_logger
from app.db.models.api_key import ApiKey
from app.db.models.user import User
from app.db.session import async_session_factory
from app.identity.factory import build_provider_from_tenant_config, get_identity_provider, peek_unverified_issuer
from app.identity.models import UserIdentity
from app.repositories.api_key_repo import ApiKeyRepo
from app.repositories.tenant_identity_config_repo import TenantIdentityConfigRepo
from app.repositories.user_repo import UserRepo
from app.services.auth_service import AuthService
from app.services.cache_service import CacheService

logger = get_logger(__name__)

UNAUTHENTICATED_PATHS = {"/health", "/ready", "/docs", "/openapi.json", "/redoc", "/v1/auth/provider", "/v1/auth/local/issue"}


@dataclass
class Principal:
    kind: str  # "api_key" | "user"
    api_key: ApiKey | None = None
    user: User | None = None
    identity: UserIdentity | None = None  # only set for kind == "user"


class AuthMiddleware(BaseHTTPMiddleware):
    """Request -> Identity Provider Factory -> selected IdentityProvider -> JWT
    validation -> UserIdentity -> User sync. No provider-specific logic lives
    here: the factory decides *which* IdentityProvider to ask (the tenant whose
    tenant_identity_config.issuer matches this token's issuer, or the global
    IDENTITY_PROVIDER default), and every provider answers the exact same
    get_user_identity(token) contract. See docs/identity-provider-architecture.md."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in UNAUTHENTICATED_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return _error_response(request, AuthError("Missing bearer token"))
        token = auth_header[len("bearer ") :].strip()

        settings = get_settings()
        async with async_session_factory() as session:
            auth_service = AuthService(ApiKeyRepo(session), UserRepo(session), CacheService(None, ttl_seconds=settings.cache_ttl_seconds), settings)
            try:
                if token.startswith(f"{settings.api_key_prefix}_"):
                    api_key = await auth_service.verify_api_key(token)
                    request.state.principal = Principal(kind="api_key", api_key=api_key)
                else:
                    provider = await self._resolve_provider(token, session, settings)
                    identity = await provider.get_user_identity(token)
                    user = await auth_service.sync_user_from_identity(identity)
                    request.state.principal = Principal(kind="user", user=user, identity=identity)
                await session.commit()
            except GatewayException as exc:
                logger.warning("auth_failed", path=request.url.path, code=exc.code, message=exc.message)
                return _error_response(request, exc)
            except Exception as exc:
                logger.exception("auth_failed_unexpected", path=request.url.path, error_type=type(exc).__name__)
                return _error_response(request, AuthError("Invalid or expired credentials"))

        return await call_next(request)

    @staticmethod
    async def _resolve_provider(token: str, session, settings):
        """Multi-tenant resolution: peek the token's (still-unverified) issuer,
        see if a tenant has registered that issuer via tenant_identity_config,
        and if so build a provider from *that tenant's* configuration instead of
        the process-wide default. Falls back to the global IDENTITY_PROVIDER
        when there's no match -- the only path a single-tenant deployment ever
        takes."""
        issuer = peek_unverified_issuer(token)
        if issuer:
            tenant_config = await TenantIdentityConfigRepo(session).get_by_issuer(issuer)
            if tenant_config is not None:
                return build_provider_from_tenant_config(tenant_config.provider.value, tenant_config.configuration, settings)
        return get_identity_provider(settings)


def _error_response(request: Request, exc: GatewayException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "request_id": str(request_id) if request_id else None}},
    )
