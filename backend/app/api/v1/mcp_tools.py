from fastapi import APIRouter, Depends

from app.api.deps import get_discovery_service, get_mcp_tool_repo, require_mcp_scope, require_roles
from app.core.logging import get_logger
from app.db.models.enums import McpSyncStatus, UserRole
from app.db.models.user import User
from app.middleware.auth_middleware import Principal
from app.repositories.mcp_tool_repo import McpToolRepo
from app.schemas.mcp import McpServerOut, McpToolOut
from app.services.mcp.discovery_service import DiscoveryService

logger = get_logger(__name__)

router = APIRouter(prefix="/mcp/tools", tags=["mcp_tools"])


@router.get("", response_model=list[McpToolOut])
async def list_tools(
    q: str | None = None,
    include_unavailable: bool = False,
    principal: Principal = Depends(require_mcp_scope("tool:read")),
    repo: McpToolRepo = Depends(get_mcp_tool_repo),
) -> list[McpToolOut]:
    """Served entirely from the cached registry (mcp_tools) -- no MCP server is
    called for a plain listing/search; use POST /mcp/tools/sync to refresh it.

    By default this returns exactly what a caller could route to right now (tool
    enabled, owning server active + healthy) -- the same view the LLM Gateway sees
    when it calls this endpoint. Pass include_unavailable=true (the Tools Explorer
    UI does, for admins) to also see tools hidden by a disabled or unhealthy server.
    """
    tools = await repo.search(q, only_available=not include_unavailable)
    logger.info("listing MCP tools", principal_kind=principal.kind, query=q, include_unavailable=include_unavailable, count=len(tools))
    return [McpToolOut.from_model(t) for t in tools]


@router.post("/sync", response_model=list[McpServerOut])
async def sync_tools(
    user: User = Depends(require_roles(UserRole.admin)),
    discovery: DiscoveryService = Depends(get_discovery_service),
) -> list[McpServerOut]:
    """Manual sync: re-runs initialize + tools/list against every enabled MCP
    server and reconciles the registry (adds new tools, drops removed ones)."""
    logger.info("syncing MCP tools", user_id=user.id)
    servers = await discovery.sync_all()
    failed = [s.name for s in servers if s.last_sync_status != McpSyncStatus.success]
    logger.info(
        "mcp_tools_sync_triggered",
        user_id=str(user.id),
        server_count=len(servers),
        failed_servers=failed,
    )
    return [McpServerOut.from_model(s) for s in servers]
