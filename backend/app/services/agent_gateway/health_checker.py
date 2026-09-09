from datetime import datetime, timezone

import httpx

from app.core.logging import get_logger
from app.db.models.agent import Agent
from app.db.models.enums import AgentHealthStatus
from app.repositories.agent_repo import AgentRepo

logger = get_logger(__name__)


class AgentHealthChecker:
    """Owns liveness for the Agent Registry. Unlike MCP servers, arbitrary
    REMOTE_HTTP/A2A agent endpoints have no single universal probe method the
    protocol guarantees (MCP's `initialize` fills that role for MCP servers;
    nothing analogous is guaranteed here) -- so this sends the same lightweight
    request shape AgentInvocationService would use and treats any HTTP response
    at all (even a 4xx/5xx from the agent's own application logic) as proof the
    endpoint is alive and reachable. Only a transport-level failure (timeout,
    connection refused, DNS, TLS) counts as unhealthy."""

    def __init__(self, agent_repo: AgentRepo, timeout_seconds: float) -> None:
        self.agent_repo = agent_repo
        self.timeout_seconds = timeout_seconds

    async def probe(self, agent: Agent) -> bool:
        """Updates agent.health_status/last_heartbeat in place; returns whether
        the probe considered it healthy."""
        if not agent.endpoint_url:
            agent.health_status = AgentHealthStatus.unknown
            await self.agent_repo.db.flush()
            await self.agent_repo.db.refresh(agent)
            return False
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                await client.post(agent.endpoint_url, json={"operation": None, "payload": {}})
            agent.health_status = AgentHealthStatus.healthy
            healthy = True
        except httpx.HTTPError as exc:
            agent.health_status = AgentHealthStatus.unhealthy
            logger.warning("agent_unhealthy", agent_id=str(agent.id), agent_key=agent.agent_key, error=str(exc))
            healthy = False
        finally:
            agent.last_heartbeat = datetime.now(timezone.utc)
            await self.agent_repo.db.flush()
            await self.agent_repo.db.refresh(agent)
        return healthy

    async def check_all(self) -> list[Agent]:
        """Best-effort across every active agent -- one agent being down must
        not stop the others from being probed."""
        agents = await self.agent_repo.list_active()
        for agent in agents:
            await self.probe(agent)
        return agents
