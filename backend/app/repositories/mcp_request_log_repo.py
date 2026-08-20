import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.db.models.enums import RequestStatus
from app.db.models.mcp_request_log import McpRequestLog
from app.repositories.base import BaseRepository


class McpRequestLogRepo(BaseRepository[McpRequestLog]):
    model = McpRequestLog

    async def stats_for_server(self, server_id: uuid.UUID, window_minutes: int = 60) -> dict:
        """Per-server usage/failure counts for the Server Health Monitor page,
        derived from mcp_request_logs rather than a separate counter table."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        stmt = select(
            func.count(McpRequestLog.id),
            func.count(McpRequestLog.id).filter(McpRequestLog.status == RequestStatus.error),
            func.avg(McpRequestLog.latency_ms),
        ).where(McpRequestLog.server_id == server_id, McpRequestLog.created_at >= cutoff)
        total, errors, avg_latency = (await self.db.execute(stmt)).one()
        return {
            "request_count": total,
            "error_count": errors,
            "avg_latency_ms": float(avg_latency) if avg_latency is not None else None,
            "window_minutes": window_minutes,
        }
