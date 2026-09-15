import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccessPolicy(Base):
    """RBAC/ABAC gate evaluated before an LLM call is routed, and before an MCP
    `tools/call` is forwarded (see services/policy_engine.py). `project_id=None`
    means a global policy that applies regardless of project. `max_tokens` is
    stored and returned by the admin API but -- like Budget's spend ceiling -- is
    advisory only in this version; it is not yet enforced against the actual
    request. `allowed_tool_names` is the MCP/REST-tool-execution analogue of
    `allowed_roles`: an empty list means unrestricted (any tool), a non-empty list
    restricts this policy to only those tool names -- this is how "only finance
    agents can execute payment APIs" is expressed (allowed_roles=["finance"],
    allowed_tool_names=["create_payment", "process_refund"]). `allowed_agent_keys`
    is the identical pattern applied to Agent Gateway invocations (empty list =
    unrestricted; see services/agent_gateway/invocation_service.py) -- registering
    an agent never implies authorization to invoke it, this is that separate gate.
    See docs/identity-provider-architecture.md's RBAC/ABAC section."""

    __tablename__ = "access_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    allowed_roles: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    allowed_identity_providers: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    allowed_tool_names: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    allowed_agent_keys: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
