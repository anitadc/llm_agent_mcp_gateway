import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import McpHealthStatus, McpServerStatus, McpSyncStatus, McpTransportType

if TYPE_CHECKING:
    from app.db.models.mcp_tool import McpTool


class McpServer(Base):
    """The MCP Server Registry's row shape: one registered MCP server, its
    transport/auth config, and the liveness/discovery state the gateway needs to
    decide whether it's safe to route to."""

    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    transport_type: Mapped[McpTransportType] = mapped_column(
        Enum(McpTransportType, name="mcp_transport_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=McpTransportType.http,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # {"type": "none" | "bearer" | "api_key", "credential_ref": "ENV_VAR_NAME", "header_name": "X-API-Key"}
    # credential_ref names an env var -- the raw secret is never stored here or
    # anywhere else on this row, mirroring ProviderConfig.credential_ref.
    auth_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Administrative on/off switch (operator-controlled).
    status: Mapped[McpServerStatus] = mapped_column(
        Enum(McpServerStatus, name="mcp_server_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=McpServerStatus.active,
    )
    # Liveness as observed by the last probe (see services/mcp/health_checker.py).
    health_status: Mapped[McpHealthStatus] = mapped_column(
        Enum(McpHealthStatus, name="mcp_health_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=McpHealthStatus.unknown,
    )
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    protocol_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_sync_status: Mapped[Optional[McpSyncStatus]] = mapped_column(
        Enum(McpSyncStatus, name="mcp_sync_status", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Free-form operator metadata (owning team, environment, tags, ...). Named
    # extra_metadata on the Python side because `metadata` is reserved by
    # DeclarativeBase; the DB column itself is still named "metadata".
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tools: Mapped[list["McpTool"]] = relationship(back_populates="server", lazy="raise_on_sql")
