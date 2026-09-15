from typing import Optional
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentProjectEnablement(Base):
    """One row = one project has opted in to a `private`-visibility agent.
    `published` agents never need a row here -- they're invocable everywhere,
    same as every agent was before AgentVisibility existed; this table only
    ever narrows access, it never grants anything a published agent wouldn't
    already have. See AgentRepo.list_by_capability."""

    __tablename__ = "agent_project_enablements"
    __table_args__ = (UniqueConstraint("agent_id", "project_id", name="uq_agent_project_enablement"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    enabled_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
