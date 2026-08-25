import asyncio
import contextlib

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import (
    agent_invocations,
    agents,
    api_services,
    auth,
    budgets,
    chat,
    embeddings,
    health,
    identity,
    keys,
    logs,
    mcp_gateway,
    mcp_servers,
    mcp_sessions,
    mcp_tools,
    model_pricing,
    organizations,
    project_users,
    projects,
    provider_configs,
    routing_rules,
    secrets,
    usage,
    users,
)
from app.core.config import get_settings
from app.core.exceptions import GatewayException
from app.core.logging import configure_logging, get_logger
from app.db.session import async_session_factory
from app.middleware.auth_middleware import AuthMiddleware
from app.middleware.rate_limit_middleware import RateLimitMiddleware
from app.middleware.request_id_middleware import RequestIDMiddleware
from app.repositories.mcp_server_repo import McpServerRepo
from app.repositories.mcp_tool_repo import McpToolRepo
from app.services.mcp.discovery_service import DiscoveryService
from app.services.mcp.health_checker import HealthChecker
from app.services.mcp.mcp_client import McpClient

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)

app = FastAPI(title="Custom LLM Gateway", version="1.0.0")

# Middleware is added innermost-first: Starlette executes the LAST-added middleware
# FIRST, so this order yields request_id -> CORS -> auth -> rate_limit -> route,
# matching TDD.md §3.5 exactly.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)

_discovery_refresh_task: asyncio.Task | None = None
_health_check_task: asyncio.Task | None = None


async def _discovery_refresh_loop() -> None:
    """Periodic tool-registry refresh, in addition to the manual POST
    /mcp/tools/sync API -- keeps mcp_tools in sync with servers that add or
    remove tools without an operator triggering a sync by hand."""
    while True:
        await asyncio.sleep(settings.mcp_discovery_refresh_seconds)
        # Broad catch is deliberate: this loop must survive one bad sync cycle and
        # keep running on the next interval rather than dying silently forever.
        try:
            async with async_session_factory() as session:
                health_checker = HealthChecker(McpServerRepo(session), McpClient(settings))
                discovery = DiscoveryService(McpServerRepo(session), McpToolRepo(session), McpClient(settings), health_checker)
                await discovery.sync_all()
                await session.commit()
        except Exception as exc:
            logger.exception("discovery_refresh_loop_failed", error=str(exc))


async def _health_check_loop() -> None:
    """Lighter, more frequent liveness sweep than the full discovery sync -- just
    `initialize` against every active registry entry, so an outage is reflected in
    health_status (and therefore in routing/tools-list filtering) quickly."""
    while True:
        await asyncio.sleep(settings.mcp_health_check_interval_seconds)
        # Broad catch is deliberate: this loop must survive one bad health-check cycle
        # and keep running on the next interval rather than dying silently forever.
        try:
            async with async_session_factory() as session:
                health_checker = HealthChecker(McpServerRepo(session), McpClient(settings))
                await health_checker.check_all()
                await session.commit()
        except Exception as exc:
            logger.exception("health_check_loop_failed", error=str(exc))


async def _cancel_task(task: asyncio.Task | None) -> None:
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@app.on_event("startup")
async def _start_background_tasks() -> None:
    global _discovery_refresh_task, _health_check_task
    if settings.mcp_discovery_refresh_seconds > 0:
        _discovery_refresh_task = asyncio.create_task(_discovery_refresh_loop())
    if settings.mcp_health_check_interval_seconds > 0:
        _health_check_task = asyncio.create_task(_health_check_loop())


@app.on_event("shutdown")
async def _stop_background_tasks() -> None:
    await _cancel_task(_discovery_refresh_task)
    await _cancel_task(_health_check_task)


@app.exception_handler(GatewayException)
async def gateway_exception_handler(request: Request, exc: GatewayException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": str(request_id) if request_id else None,
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        request_id=str(request_id) if request_id else None,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "request_id": str(request_id) if request_id else None,
            }
        },
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(embeddings.router)
app.include_router(keys.router)
app.include_router(organizations.router)
app.include_router(projects.router)
app.include_router(users.router)
app.include_router(project_users.router)
app.include_router(provider_configs.router)
app.include_router(usage.router)
app.include_router(logs.router)
app.include_router(routing_rules.router)
app.include_router(budgets.router)
app.include_router(model_pricing.router)
app.include_router(mcp_gateway.router)
app.include_router(mcp_servers.router)
app.include_router(mcp_tools.router)
app.include_router(mcp_sessions.router)
app.include_router(api_services.router)
app.include_router(agents.router)
app.include_router(agents.approvals_router)
app.include_router(agent_invocations.router)
app.include_router(secrets.router)
app.include_router(identity.router)
