from datetime import datetime, timezone

from app.db.models.enums import McpHealthStatus, McpServerStatus
from app.db.models.mcp_server import McpServer
from app.repositories.mcp_server_repo import McpServerRepo
from app.services.mcp.mcp_client import McpClient, McpRpcResult


class HealthChecker:
    """Owns liveness for the MCP Server Registry: `initialize` is the one call
    every MCP server must support, so it doubles as the health probe -- a bespoke
    REST /health convention isn't part of the MCP protocol and would need its own
    per-server config just to be optional, which isn't worth the complexity here.
    Both the periodic health-check loop and DiscoveryService (which needs a live
    session before it can call tools/list) share this single probe implementation,
    so "is this server healthy" is decided in exactly one place."""

    def __init__(self, server_repo: McpServerRepo, client: McpClient) -> None:
        self.server_repo = server_repo
        self.client = client

    async def probe(self, server: McpServer) -> McpRpcResult | None:
        """Updates server.health_status/last_heartbeat in place and returns the
        initialize result on success (so callers can reuse its session id), or
        None on failure."""
        try:
            result = await self.client.initialize(server)
            server.health_status = McpHealthStatus.healthy
            return result
        except Exception:
            server.health_status = McpHealthStatus.unhealthy
            return None
        finally:
            server.last_heartbeat = datetime.now(timezone.utc)
            await self.server_repo.db.flush()

    async def check_all(self) -> list[McpServer]:
        """Best-effort across every administratively-active server -- one server
        being down must not stop the others from being probed."""
        servers = await self.server_repo.list_active()
        for server in servers:
            await self.probe(server)
        return servers

    @staticmethod
    def is_routable(server: McpServer) -> bool:
        return server.status == McpServerStatus.active and server.health_status == McpHealthStatus.healthy
