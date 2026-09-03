import httpx
import redis.exceptions
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import Settings, get_settings
from app.core.logging import get_logger, log_method
from app.db.valkey import valkey_client

logger = get_logger(__name__)

router = APIRouter(tags=["health"])

@router.get("/provider_info")
@log_method(logger)
async def get_provider_info() -> dict:
    """Public info about which identity provider the backend is configured to use.

    This is intentionally non-sensitive and helps frontends adapt their
    login flow (Keycloak redirect vs. a dev local token form).
    """
    return {
        "identity_provider": "local" #if get_settings().identity_provider is None else get_settings().identity_provider,
        }


@router.get("/health")
@log_method(logger)
async def get_health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
@log_method(logger)
async def get_readiness(
    db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings)
) -> JSONResponse:
    statuses = {"db": "down", "valkey": "down", "keycloak": "down", "guardrails": "down","infisical": "down"}

    try:
        await db.execute(text("SELECT 1"))
        statuses["db"] = "ok"
    except SQLAlchemyError as exc:
        logger.warning("readiness_check_failed", dependency="db", error=str(exc))

    try:
        await valkey_client.ping()
        statuses["valkey"] = "ok"
    except redis.exceptions.RedisError as exc:
        logger.warning("readiness_check_failed", dependency="valkey", error=str(exc))

    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            # keycloak_jwks_url (not keycloak_base_url) on purpose: base_url must
            # match the issuer string embedded in browser-obtained tokens, which
            # in a Docker Compose deployment is the externally-published host, not
            # necessarily one this container can reach itself. jwks_url is always
            # a real network-reachable endpoint, since token validation depends on
            # actually fetching it -- see identity/base.py::validate_oidc_jwt.
            resp = await client.get(settings.keycloak_jwks_url)
            statuses["keycloak"] = "ok" if resp.status_code < 500 else "down"
        except httpx.HTTPError as exc:
            logger.warning("readiness_check_failed", dependency="keycloak", error=str(exc))
        try:
            resp = await client.get(f"{settings.guardrails_base_url}/health")
            statuses["guardrails"] = "ok" if resp.status_code < 500 else "down"
        except httpx.HTTPError as exc:
            logger.warning("readiness_check_failed", dependency="guardrails", error=str(exc))

        if settings.secret_provider != "infisical":
            statuses["infisical"] = "skipped"
        else:
            infisical_url = settings.infisical_site_url.rstrip("/") + "/health"
            try:
                resp = await client.get(infisical_url)
                statuses["infisical"] = "ok" if resp.status_code < 500 else "down"
            except Exception:
                logger.exception("infisical health check failed", infisical_url=infisical_url)

    status_code = 200 if all(v in {"ok", "skipped"} for v in statuses.values()) else 503
    return JSONResponse(status_code=status_code, content=statuses)
