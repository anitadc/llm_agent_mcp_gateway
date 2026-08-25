import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response

from app.api.deps import (
    get_api_registry_service,
    get_current_principal,
    get_health_checker,
    get_mcp_client,
    get_mcp_server_repo,
    get_mcp_tool_repo,
    get_policy_engine,
    get_routing_engine,
    get_session_manager,
    mcp_scopes_for,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import BadRequestError, ForbiddenError, GatewayException
from app.core.logging import get_logger
from app.db.models.enums import McpToolSourceType, RequestStatus
from app.db.models.mcp_session import McpSession
from app.db.models.mcp_tool import McpTool
from app.middleware.auth_middleware import Principal
from app.repositories.mcp_server_repo import McpServerRepo
from app.repositories.mcp_tool_repo import McpToolRepo
from app.schemas.mcp import JsonRpcErrorObject, JsonRpcRequest, JsonRpcResponse
from app.services.api_registry.api_registry_service import ApiRegistryService
from app.services.logging_service import record_mcp_request
from app.services.mcp.health_checker import HealthChecker
from app.services.mcp.mcp_client import MCP_SESSION_HEADER, McpClient
from app.services.mcp.routing_engine import RoutingEngine
from app.services.mcp.session_manager import SessionManager
from app.services.policy_engine import PolicyEngine
from app.services.rate_limit_service import RateLimitService

logger = get_logger(__name__)

router = APIRouter(tags=["mcp_gateway"])


def _identity(principal: Principal) -> tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None]:
    """Returns (project_id, api_key_id, user_id) for whichever principal kind
    authenticated this request."""
    if principal.kind == "api_key":
        return principal.api_key.project_id, principal.api_key.id, None
    return None, None, principal.user.id


def _require_scope(principal: Principal, scope: str) -> None:
    if scope not in mcp_scopes_for(principal):
        raise ForbiddenError(f"Missing required MCP scope '{scope}'")


@router.post("/mcp", response_model=JsonRpcResponse, response_model_exclude_none=True)
async def mcp_gateway(
    body: JsonRpcRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
    server_repo: McpServerRepo = Depends(get_mcp_server_repo),
    tool_repo: McpToolRepo = Depends(get_mcp_tool_repo),
    routing_engine: RoutingEngine = Depends(get_routing_engine),
    session_manager: SessionManager = Depends(get_session_manager),
    mcp_client: McpClient = Depends(get_mcp_client),
    health_checker: HealthChecker = Depends(get_health_checker),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
    api_registry_service: ApiRegistryService = Depends(get_api_registry_service),
) -> JsonRpcResponse:
    """Single entry point for every MCP JSON-RPC call. Routing is entirely
    body-driven (never path-driven): the `method` (and, for tools/call, the
    `params.name` tool name) decide where the request goes -- see TDD/PRD for why
    this must not become per-tool or per-server sub-routes.

    Rejections that are the GATEWAY's decision (missing scope, rate limited) are
    raised as ordinary GatewayExceptions and come back as HTTP-level errors, exactly
    like every other endpoint in this app. Only once the gateway has agreed to
    forward the call does a downstream failure surface -- and even then, a
    same-shape JSON-RPC `error` object returned by the MCP server is forwarded
    verbatim in the 200 response body, since that's an application-level result,
    not a gateway rejection.
    """
    request_id = request.state.request_id
    start = time.perf_counter()
    project_id, api_key_id, user_id = _identity(principal)
    client_session_id = request.headers.get(MCP_SESSION_HEADER)

    status = RequestStatus.success
    tool_name: str | None = None
    server_id: uuid.UUID | None = None
    execution_type: McpToolSourceType | None = None
    api_service_id: uuid.UUID | None = None
    endpoint_path: str | None = None
    status_code: int | None = None

    try:
        if body.method == "initialize":
            _require_scope(principal, "tool:read")
            result, client_session_id = await _handle_initialize(
                client_session_id, project_id, api_key_id, settings, server_repo, session_manager, health_checker
            )

        elif body.method == "tools/list":
            _require_scope(principal, "tool:read")
            result = await _handle_tools_list(tool_repo)

        elif body.method == "tools/call":
            _require_scope(principal, "tool:execute")

            params = body.params or {}
            tool_name = params.get("name")
            if not tool_name:
                raise BadRequestError("params.name is required for tools/call")

            # Scopes (tool:execute) gate the machine credential; AccessPolicy is
            # the RBAC/ABAC gate for *human* (Identity Provider) callers, evaluated
            # generically over UserIdentity.roles/.provider/tool_name -- it never
            # inspects which concrete IdentityProvider authenticated them, or
            # whether the tool is MCP- or REST-backed. API-key callers already
            # have their own adequate authorization (scopes) and carry no
            # IdP-sourced roles, so they aren't subject to this check.
            if principal.kind == "user" and principal.identity is not None:
                decision = await policy_engine.evaluate(
                    project_id=None,
                    roles=principal.identity.roles,
                    identity_provider=principal.identity.provider,
                    tool_name=tool_name,
                )
                if not decision.allowed:
                    raise ForbiddenError(decision.reason or "Access policy denied this request")

            rate_limit_key = f"mcp-tool:{api_key_id or user_id}:{tool_name}"
            await RateLimitService().check(rate_limit_key, settings.mcp_default_rate_limit_per_window)

            tool = await routing_engine.resolve_tool(tool_name)
            execution_type = tool.source_type
            arguments = params.get("arguments") or {}

            if tool.source_type == McpToolSourceType.rest:
                result, status_code, api_service_id, endpoint_path = await _handle_rest_tools_call(
                    tool, arguments, api_registry_service, settings
                )
                if status_code is not None and status_code >= 400:
                    status = RequestStatus.error
            else:
                server_id = tool.server_id
                session, _ = await session_manager.get_or_create(client_session_id, project_id, api_key_id)
                client_session_id = session.client_session_id
                result, rpc_error = await _handle_tools_call(
                    tool, session, session_manager, mcp_client, health_checker, body.id, arguments
                )
                if rpc_error is not None:
                    status = RequestStatus.error
                    response.headers[MCP_SESSION_HEADER] = client_session_id
                    return JsonRpcResponse(id=body.id, error=rpc_error)

        else:
            raise BadRequestError(f"Unsupported MCP method '{body.method}'")

        if client_session_id:
            response.headers[MCP_SESSION_HEADER] = client_session_id
        return JsonRpcResponse(id=body.id, result=result)
    except Exception as exc:
        # Broad on purpose: this must catch both expected GatewayExceptions (bad
        # request, forbidden, unavailable tool, ...) and genuine bugs so `status`
        # is always correct for record_mcp_request below. Severity of the log
        # reflects which kind actually happened.
        if status == RequestStatus.success:
            status = RequestStatus.error
        if isinstance(exc, GatewayException) and exc.status_code < 500:
            logger.warning(
                "mcp_gateway_request_rejected",
                method=body.method,
                tool_name=tool_name,
                error_code=exc.code,
            )
        else:
            logger.exception(
                "mcp_gateway_request_failed",
                method=body.method,
                tool_name=tool_name,
                server_id=str(server_id) if server_id else None,
            )
        raise
    finally:
        background_tasks.add_task(
            record_mcp_request,
            request_id=request_id,
            api_key_id=api_key_id,
            user_id=user_id,
            project_id=project_id,
            client_session_id=client_session_id,
            method=body.method,
            tool_name=tool_name,
            server_id=server_id,
            status=status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            execution_type=execution_type,
            api_service_id=api_service_id,
            endpoint_path=endpoint_path,
            status_code=status_code,
        )


async def _handle_initialize(
    client_session_id: str | None,
    project_id: uuid.UUID | None,
    api_key_id: uuid.UUID | None,
    settings: Settings,
    server_repo: McpServerRepo,
    session_manager: SessionManager,
    health_checker: HealthChecker,
) -> tuple[dict, str]:
    """Broadcasts `initialize` to every administratively-active MCP server (via the
    registry, never a hardcoded list) and records each per-server session id
    against this one client session. Best-effort: a server that fails to
    initialize is reported back but doesn't fail the whole call; the same probe
    also refreshes that server's health_status in the registry."""
    session, _ = await session_manager.get_or_create(client_session_id, project_id, api_key_id)

    warnings: dict[str, str] = {}
    for server in await server_repo.list_active():
        init_result = await health_checker.probe(server)
        if init_result is None:
            warnings[server.name] = "Server failed its liveness probe"
            continue
        await session_manager.record_server_session(session, server.id, init_result.session_id)

    result = {
        "protocolVersion": settings.mcp_protocol_version,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "llm-gateway-mcp-gateway", "version": "1.0.0"},
    }
    if warnings:
        result["_gatewayWarnings"] = warnings
    return result, session.client_session_id


async def _handle_tools_list(tool_repo: McpToolRepo) -> dict:
    """Served entirely from the cached registry -- no MCP server is called. Only
    tools whose owning server is registry-active + healthy are returned, so
    disabling or losing a server immediately hides its tools here."""
    tools = await tool_repo.search(None, only_available=True)
    return {"tools": [{"name": t.name, "description": t.description, "inputSchema": t.input_schema} for t in tools]}


async def _handle_rest_tools_call(
    tool: McpTool,
    arguments: dict,
    api_registry_service: ApiRegistryService,
    settings: Settings,
) -> tuple[dict, int, uuid.UUID, str]:
    """REST-backed tools/call dispatch: enforces the REST API's own rate limit
    (in addition to the per-tool limit already checked by the caller) then
    executes via RestExecutor. Unlike an MCP server call, there's no session to
    establish -- REST endpoints are stateless from the gateway's perspective."""
    api_service = tool.api_endpoint.api_service
    await RateLimitService().check(
        f"mcp-restapi:{api_service.name}", api_service.rate_limit_per_window or settings.mcp_default_rate_limit_per_window
    )
    exec_result = await api_registry_service.execute(tool, arguments)
    result = {**exec_result.content, "isError": exec_result.is_error}
    return result, exec_result.status_code, api_service.id, tool.api_endpoint.path


async def _handle_tools_call(
    tool: McpTool,
    session: McpSession,
    session_manager: SessionManager,
    mcp_client: McpClient,
    health_checker: HealthChecker,
    request_id: str | int | None,
    arguments: dict,
) -> tuple[dict | None, JsonRpcErrorObject | None]:
    server_session_id = session_manager.get_server_session_id(session, tool.server_id)
    if server_session_id is None:
        init_result = await health_checker.probe(tool.server)
        if init_result is None:
            return None, JsonRpcErrorObject(code=-32000, message=f"MCP server '{tool.server.name}' is unreachable")
        server_session_id = init_result.session_id
        await session_manager.record_server_session(session, tool.server_id, server_session_id)

    rpc_result = await mcp_client.call_tool(
        tool.server, server_session_id, request_id if request_id is not None else str(uuid.uuid4()), tool.name, arguments
    )
    payload = rpc_result.payload
    if "error" in payload:
        return None, JsonRpcErrorObject.model_validate(payload["error"])
    return payload.get("result"), None
