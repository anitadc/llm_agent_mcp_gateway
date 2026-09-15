import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import RequestStatus

if TYPE_CHECKING:
    from app.db.models.agent import Agent


class AgentInvocation(Base):
    """Observability/audit record for one governed agent invocation -- the Agent
    Gateway analogue of McpRequestLog. `authorization_decision` records the
    PolicyEngine's allow/deny reason so "why did/didn't this route" never
    requires reconstructing the decision from application logs."""

    __tablename__ = "agent_invocations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    api_key_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    capability: Mapped[str] = mapped_column(String, nullable=False)
    operation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    authorization_decision: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="request_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # NULL means "no AgentPricing row for this agent" -- deliberately distinct
    # from Decimal("0") (an agent explicitly priced at zero). Mirrors the LLM
    # Gateway's cost_ledger.cost_usd except for this one distinction, which that
    # table doesn't make -- see app/services/agent_gateway/invocation_service.py.
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    agent: Mapped[Optional["Agent"]] = relationship(back_populates="invocations", lazy="raise_on_sql")
