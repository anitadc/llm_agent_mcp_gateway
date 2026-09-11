import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentPricing(Base):
    """Per-agent flat cost-per-invocation, admin-editable, mirroring
    ModelPricing's role for the LLM Gateway. A flat per-call price (rather than
    token-based pricing) since an agent invocation isn't necessarily
    token-metered the way an LLM completion is. No row for an agent means its
    invocations are unpriced -- see AgentInvocation.cost_usd for why that's
    NULL, not zero."""

    __tablename__ = "agent_pricing"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    cost_per_invocation: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
