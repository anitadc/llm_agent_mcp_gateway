import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.agent_approval_task import AgentApprovalTask


class AgentApprovalComment(Base):
    """A discussion thread on one approval task -- reviewers can leave context
    (why they're waiting, what they need clarified) without that context being
    lost the way a bare approve/reject `reason` field would lose it."""

    __tablename__ = "agent_approval_comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_approval_tasks.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["AgentApprovalTask"] = relationship(back_populates="comments", lazy="raise_on_sql")
