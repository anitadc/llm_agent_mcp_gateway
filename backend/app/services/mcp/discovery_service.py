import time
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.db.models.enums import McpSyncStatus
from app.db.models.mcp_server import McpServer
from app.db.models.mcp_tool import McpTool
from app.repositories.mcp_server_repo import McpServerRepo
from app.repositories.mcp_tool_repo import McpToolRepo
from app.services.mcp.health_checker import HealthChecker
from app.services.mcp.mcp_client import McpClient

logger = get_logger(__name__)


class DiscoveryService:
    """Builds and maintains the central tool_name -> server registry (mcp_tools) by
    calling `initialize` then `tools/list` against each registered, active MCP
    server. Liveness (health_status/last_heartbeat) is delegated entirely to
    HealthChecker.probe so a server's health is decided in exactly one place,
    whether it was observed via a sync, a periodic health check, or live traffic."""

    def __init__(
        self, server_repo: McpServerRepo, tool_repo: McpToolRepo, client: McpClient, health_checker: HealthChecker
    ) -> None:
        self.server_repo = server_repo
        self.tool_repo = tool_repo
        self.client = client
        self.health_checker = health_checker

    async def sync_server(self, server: McpServer) -> McpServer:
        start = time.perf_counter()
        try:
            init_result = await self.health_checker.probe(server)
            if init_result is None:
                server.last_sync_status = McpSyncStatus.error
                server.last_sync_error = f"Server '{server.name}' failed its liveness probe; tools/list skipped"
                logger.warning(
                    "mcp_server_sync_skipped",
                    server_id=str(server.id),
                    server_name=server.name,
                    reason="liveness_probe_failed",
                )
                return server

            server.protocol_version = (
                init_result.payload.get("result", {}).get("protocolVersion") or server.protocol_version
            )
            tools = await self.client.list_tools(server, init_result.session_id)
            await self._reconcile_tools(server, tools)
            server.last_sync_status = McpSyncStatus.success
            server.last_sync_error = None
            logger.info(
                "mcp_server_synced",
                server_id=str(server.id),
                server_name=server.name,
                tool_count=len(tools),
            )
        except Exception as exc:
            server.last_sync_status = McpSyncStatus.error
            server.last_sync_error = str(exc)[:2000]
            logger.exception(
                "mcp_server_sync_failed",
                server_id=str(server.id),
                server_name=server.name,
            )
        finally:
            server.last_sync_at = datetime.now(timezone.utc)
            server.last_sync_latency_ms = int((time.perf_counter() - start) * 1000)
            await self.server_repo.db.flush()
        return server

    async def _reconcile_tools(self, server: McpServer, tools: list[dict]) -> None:
        existing_for_server = {t.name: t for t in await self.tool_repo.list_by_server(server.id)}
        seen_names: set[str] = set()

        for tool in tools:
            name = tool["name"]
            seen_names.add(name)
            row = existing_for_server.get(name)
            if row is None:
                # tool_name is unique gateway-wide -- if another server previously
                # owned this name, the most recent sync reassigns ownership to it.
                row = await self.tool_repo.get_by_name(name)
            if row is None:
                row = McpTool(server_id=server.id, name=name, input_schema={})
                self.tool_repo.db.add(row)
            row.server_id = server.id
            row.description = tool.get("description")
            row.input_schema = tool.get("inputSchema", {})
            row.enabled = True

        # tools the server no longer advertises are removed from the registry
        for name, row in existing_for_server.items():
            if name not in seen_names:
                await self.tool_repo.delete(row)

    async def sync_all(self) -> list[McpServer]:
        """Best-effort across all active servers -- one server failing to sync
        must not prevent the others from refreshing."""
        return [await self.sync_server(server) for server in await self.server_repo.list_active()]
