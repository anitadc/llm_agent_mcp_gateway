import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import AgentApprovalDecision, AgentApprovalStage

if TYPE_CHECKING:
    from app.db.models.agent import Agent


class AgentApprovalTask(Base):
    """One review-stage instance for one agent registration. Stages required for
    a given agent are decided by configuration (`Settings.agent_approval_stages`,
    plus the `production` stage whenever `Agent.risk_class == high`) -- never
    hard-coded per agent. An agent reaches `approved` only once every task for it
    has `decision == approved`; see services/agent_gateway/approval_service.py."""

    __tablename__ = "agent_approval_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[AgentApprovalStage] = mapped_column(
        Enum(AgentApprovalStage, name="agent_approval_stage", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    decision: Mapped[AgentApprovalDecision] = mapped_column(
        Enum(AgentApprovalDecision, name="agent_approval_decision", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AgentApprovalDecision.pending,
    )
    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    agent: Mapped["Agent"] = relationship(back_populates="approval_tasks", lazy="raise_on_sql")
