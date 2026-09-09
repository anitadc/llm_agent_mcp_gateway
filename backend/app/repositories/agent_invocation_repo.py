import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.db.models.agent_invocation import AgentInvocation
from app.db.models.enums import RequestStatus
from app.repositories.base import BaseRepository


class AgentInvocationRepo(BaseRepository[AgentInvocation]):
    model = AgentInvocation

    async def list_recent(self, limit: int = 100) -> list[AgentInvocation]:
        result = await self.db.execute(select(AgentInvocation).order_by(AgentInvocation.created_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def stats_for_agent(self, agent_id: uuid.UUID, window_minutes: int = 60) -> dict:
        """Per-agent usage/failure/cost counts, derived from agent_invocations
        rather than a separate counter table -- mirrors McpRequestLogRepo.stats_for_server."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        stmt = select(
            func.count(AgentInvocation.id),
            func.count(AgentInvocation.id).filter(AgentInvocation.status == RequestStatus.error),
            func.avg(AgentInvocation.latency_ms),
            func.sum(AgentInvocation.cost_usd),
        ).where(AgentInvocation.agent_id == agent_id, AgentInvocation.created_at >= cutoff)
        total, errors, avg_latency, total_cost = (await self.db.execute(stmt)).one()
        return {
            "request_count": total,
            "error_count": errors,
            "avg_latency_ms": float(avg_latency) if avg_latency is not None else None,
            "total_cost_usd": Decimal(total_cost) if total_cost is not None else None,
            "window_minutes": window_minutes,
        }
