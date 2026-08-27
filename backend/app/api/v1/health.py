import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.valkey import valkey_client

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health")
async def get_health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def get_readiness(
    db: AsyncSession = Depends(get_db), settings: Settings = Depends(get_settings)
) -> JSONResponse:
    statuses = {
        "db": "down",
        "valkey": "down",
        "keycloak": "down",
        "guardrails": "down",
        "infisical": "down",
    }

    try:
        await db.execute(text("SELECT 1"))
        statuses["db"] = "ok"
    except Exception:
        logger.exception("database health check failed")

    try:
        await valkey_client.ping()
        statuses["valkey"] = "ok"
    except Exception:
        logger.exception("valkey health check failed")

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
        except Exception:
            logger.exception("keycloak health check failed", jwks_url=settings.keycloak_jwks_url)

        try:
            resp = await client.get(f"{settings.guardrails_base_url}/health")
            statuses["guardrails"] = "ok" if resp.status_code < 500 else "down"
        except Exception:
            logger.exception("guardrails health check failed", guardrails_base_url=settings.guardrails_base_url)

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
