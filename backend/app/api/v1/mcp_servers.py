import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_health_checker, get_mcp_request_log_repo, get_mcp_server_repo, require_roles
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.enums import UserRole
from app.db.models.mcp_server import McpServer
from app.db.models.user import User
from app.repositories.mcp_request_log_repo import McpRequestLogRepo
from app.repositories.mcp_server_repo import McpServerRepo
from app.schemas.mcp import McpServerCreate, McpServerOut, McpServerStatsOut, McpServerUpdate
from app.services.mcp.health_checker import HealthChecker

logger = get_logger(__name__)

router = APIRouter(prefix="/mcp/servers", tags=["mcp_servers"])


@router.get("", response_model=list[McpServerOut])
async def list_mcp_servers(
    user: User = Depends(require_roles(UserRole.admin)), repo: McpServerRepo = Depends(get_mcp_server_repo)
) -> list[McpServerOut]:
    servers = await repo.list_with_tool_counts()
    logger.info("listing MCP servers", user_id=user.id, count=len(servers))
    return [McpServerOut.from_model(server, tool_count) for server, tool_count in servers]


@router.post("", response_model=McpServerOut, status_code=201)
async def create_mcp_server(
    body: McpServerCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: McpServerRepo = Depends(get_mcp_server_repo),
) -> McpServerOut:
    logger.info("creating MCP server", user_id=user.id, name=body.name, base_url=body.base_url)
    server = await repo.add(
        McpServer(
            name=body.name,
            base_url=body.base_url,
            transport_type=body.transport_type,
            description=body.description,
            auth_config=body.auth_config,
            status=body.status,
            extra_metadata=body.metadata,
        )
    )
    logger.info(
        "mcp_server_created",
        server_id=str(server.id),
        server_name=server.name,
        base_url=server.base_url,
        user_id=str(user.id),
    )
    return McpServerOut.from_model(server)


@router.put("/{server_id}", response_model=McpServerOut)
async def update_mcp_server(
    server_id: uuid.UUID,
    body: McpServerUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: McpServerRepo = Depends(get_mcp_server_repo),
) -> McpServerOut:
    logger.info("updating MCP server", user_id=user.id, server_id=str(server_id), fields=list(body.model_dump(exclude_none=True).keys()))
    server = await repo.get(server_id)
    if server is None:
        raise NotFoundError("MCP server not found")
    if body.base_url is not None:
        server.base_url = body.base_url
    if body.description is not None:
        server.description = body.description
    if body.auth_config is not None:
        server.auth_config = body.auth_config
    if body.status is not None:
        server.status = body.status
    if body.metadata is not None:
        server.extra_metadata = body.metadata
    await repo.db.flush()
    await repo.db.refresh(server)
    logger.info(
        "mcp_server_updated",
        server_id=str(server.id),
        server_name=server.name,
        user_id=str(user.id),
    )
    return McpServerOut.from_model(server)


@router.delete("/{server_id}", status_code=204)
async def delete_mcp_server(
    server_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: McpServerRepo = Depends(get_mcp_server_repo),
) -> None:
    logger.info("deleting MCP server", user_id=user.id, server_id=str(server_id))
    server = await repo.get(server_id)
    if server is None:
        raise NotFoundError("MCP server not found")
    logger.info("mcp_server_deleted", server_id=str(server.id), server_name=server.name, user_id=str(user.id))
    await repo.delete(server)


@router.post("/{server_id}/health-check", response_model=McpServerOut)
async def trigger_health_check(
    server_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: McpServerRepo = Depends(get_mcp_server_repo),
    health_checker: HealthChecker = Depends(get_health_checker),
) -> McpServerOut:
    logger.info("checking MCP server health", user_id=user.id, server_id=str(server_id))
    server = await repo.get(server_id)
    if server is None:
        raise NotFoundError("MCP server not found")
    await health_checker.probe(server)
    logger.info(
        "mcp_server_health_check_triggered",
        server_id=str(server.id),
        server_name=server.name,
        health_status=str(server.health_status),
        user_id=str(user.id),
    )
    return McpServerOut.from_model(server)


@router.get("/{server_id}/stats", response_model=McpServerStatsOut)
async def get_mcp_server_stats(
    server_id: uuid.UUID,
    window_minutes: int = 60,
    user: User = Depends(require_roles(UserRole.admin)),
    server_repo: McpServerRepo = Depends(get_mcp_server_repo),
    log_repo: McpRequestLogRepo = Depends(get_mcp_request_log_repo),
) -> McpServerStatsOut:
    logger.info("loading MCP server stats", user_id=user.id, server_id=str(server_id), window_minutes=window_minutes)
    server = await server_repo.get(server_id)
    if server is None:
        raise NotFoundError("MCP server not found")
    stats = await log_repo.stats_for_server(server_id, window_minutes)
    return McpServerStatsOut(server_id=server_id, **stats)
