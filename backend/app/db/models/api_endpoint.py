import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import RestHttpMethod

if TYPE_CHECKING:
    from app.db.models.api_service import ApiService
    from app.db.models.mcp_tool import McpTool


class ApiEndpoint(Base):
    """One registered REST endpoint under an ApiService. `tool_name` is unique
    gateway-wide (same rule as McpTool.name) since it becomes the MCP tool name
    a caller invokes via `tools/call`. Every ApiEndpoint has exactly one McpTool
    row pointing back at it (source_type=rest) -- see
    services/api_registry/api_registry_service.py, which is the only code path
    allowed to create/update/delete that paired McpTool row."""

    __tablename__ = "api_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_services.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[RestHttpMethod] = mapped_column(
        Enum(RestHttpMethod, name="rest_http_method", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    # e.g. "/customers/{id}" -- {name} placeholders are substituted from arguments
    # whose parameter entry has location="path" (see rest_executor.py::_split_arguments).
    path: Mapped[str] = mapped_column(String, nullable=False)
    # {"<param_name>": {"type": "string", "required": true, "location": "path"|"query"|"header"|"body"}}
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    api_service: Mapped["ApiService"] = relationship(back_populates="endpoints", lazy="raise_on_sql")
    mcp_tool: Mapped["McpTool | None"] = relationship(back_populates="api_endpoint", lazy="raise_on_sql")
