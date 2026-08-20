import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import McpToolSourceType

if TYPE_CHECKING:
    from app.db.models.api_endpoint import ApiEndpoint
    from app.db.models.mcp_server import McpServer


class McpTool(Base):
    """Central tool registry: tool_name -> execution target. `name` is unique
    gateway-wide (TDD requires a single unambiguous tool_name -> target mapping for
    body-based routing). `source_type` discriminates the two kinds of target this
    row can point at:

    - mcp:  server_id is set, api_endpoint_id is null -- owning MCP server, built by
            DiscoveryService (see services/mcp/discovery_service.py). If two servers
            advertise the same tool name, the most recent sync wins the mapping and
            the previous owner's row is removed.
    - rest: api_endpoint_id is set, server_id is null -- a registered REST API
            endpoint, built by ApiRegistryService (see
            services/api_registry/api_registry_service.py) when that endpoint is
            registered/updated, never by background discovery.

    The CHECK constraint enforces exactly one target is set, matching source_type,
    at the database level -- the same "belt and suspenders" pattern as
    Budget.chk_budget_scope.
    """

    __tablename__ = "mcp_tools"
    __table_args__ = (
        CheckConstraint(
            "(source_type = 'mcp' AND server_id IS NOT NULL AND api_endpoint_id IS NULL) OR "
            "(source_type = 'rest' AND api_endpoint_id IS NOT NULL AND server_id IS NULL)",
            name="chk_mcp_tool_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_type: Mapped[McpToolSourceType] = mapped_column(
        Enum(McpToolSourceType, name="mcp_tool_source_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=McpToolSourceType.mcp,
    )
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=True
    )
    api_endpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_endpoints.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    server: Mapped["McpServer | None"] = relationship(back_populates="tools", lazy="raise_on_sql")
    api_endpoint: Mapped["ApiEndpoint | None"] = relationship(back_populates="mcp_tool", lazy="raise_on_sql")
