import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.api.deps import get_agent_invocation_repo, get_agent_invocation_service, get_current_principal, get_policy_engine
from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenError
from app.core.logging import get_logger, log_method
from app.middleware.auth_middleware import Principal
from app.repositories.agent_invocation_repo import AgentInvocationRepo
from app.schemas.agent import AgentInvocationOut, InvokeRequest, InvokeResponse
from app.services.agent_gateway.invocation_service import AgentInvocationService
from app.services.logging_service import record_agent_invocation
from app.services.policy_engine import PolicyEngine
from app.services.rate_limit_service import RateLimitService

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/agent-invocations", tags=["agent_gateway"])


def _identity(principal: Principal) -> tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None]:
    if principal.kind == "api_key":
        return principal.api_key.project_id, principal.api_key.id, None
    return None, None, principal.user.id


@router.post("", response_model=InvokeResponse)
@log_method(logger)
async def invoke_agent(
    body: InvokeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(get_current_principal),
    invocation_service: AgentInvocationService = Depends(get_agent_invocation_service),
    policy_engine: PolicyEngine = Depends(get_policy_engine),
    settings: Settings = Depends(get_settings),
) -> InvokeResponse:
    """The consumer-facing invocation contract: callers ask for a `capability`,
    never a target agent/endpoint/protocol -- the gateway resolves, authorizes,
    and dispatches. Mirrors mcp_gateway.py's `tools/call` handling: API keys
    carry their own scope (`agent:invoke`) and are never subject to the
    PolicyEngine; Identity-Provider-authenticated humans are gated by it,
    evaluated over `agent_key` exactly like MCP tools are over `tool_name`."""
    request_id = request.state.request_id
    start = time.perf_counter()
    project_id, api_key_id, user_id = _identity(principal)
    logger.info("invoking agent", request_id=request_id, capability=body.capability, operation=body.operation, api_key_id=api_key_id, user_id=user_id)

    if principal.kind == "api_key":
        if "agent:invoke" not in (principal.api_key.scopes or []):
            logger.warning("agent_invocation_forbidden", request_id=str(request_id), capability=body.capability)
            raise ForbiddenError("Missing required scope 'agent:invoke'")
        roles: list[str] = []
        identity_provider = None
    else:
        roles = principal.identity.roles if principal.identity else []
        identity_provider = principal.identity.provider if principal.identity else None

    rate_limit_key = f"agent-invoke:{api_key_id or user_id}:{body.capability}"
    await RateLimitService().check(rate_limit_key, settings.agent_default_rate_limit_per_window)

    result = await invocation_service.invoke(
        capability=body.capability,
        operation=body.operation,
        payload=body.payload,
        roles=roles,
        identity_provider=identity_provider,
        policy_engine=policy_engine,
    )

    background_tasks.add_task(
        record_agent_invocation,
        request_id=request_id,
        api_key_id=api_key_id,
        user_id=user_id,
        project_id=project_id,
        capability=body.capability,
        operation=body.operation,
        agent_id=result.agent.id if result.agent else None,
        authorization_decision=result.authorization_decision,
        status=result.status,
        latency_ms=int((time.perf_counter() - start) * 1000),
    )

    logger.info(
        "agent_invocation_completed",
        request_id=str(request_id),
        target_agent_key=result.agent.agent_key if result.agent else None,
        status=result.status.value,
        authorization_decision=result.authorization_decision,
        latency_ms=int((time.perf_counter() - start) * 1000),
    )

    return InvokeResponse(
        invocation_id=request_id,
        status=result.status.value,
        target_agent_key=result.agent.agent_key if result.agent else None,
        target_agent_version=result.agent.version if result.agent else None,
        protocol="REMOTE_HTTP",
        authorization_decision=result.authorization_decision,
        latency_ms=int((time.perf_counter() - start) * 1000),
        result=result.result,
        error=result.error,
    )


@router.get("", response_model=list[AgentInvocationOut])
@log_method(logger)
async def list_agent_invocations(
    principal: Principal = Depends(get_current_principal),
    repo: AgentInvocationRepo = Depends(get_agent_invocation_repo),
) -> list[AgentInvocationOut]:
    """Same access level as GET /v1/logs -- any authenticated caller, not
    admin-only, since this is observability for a caller's own traffic, not a
    registry-management action."""
    invocations = await repo.list_recent()
    logger.info("listing agent invocations", principal_kind=principal.kind, count=len(invocations))
    return [AgentInvocationOut.model_validate(inv) for inv in invocations]
