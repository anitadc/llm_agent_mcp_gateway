from typing import Optional
import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import BudgetPeriod


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        CheckConstraint(
            "organization_id IS NOT NULL OR project_id IS NOT NULL OR user_id IS NOT NULL",
            name="chk_budget_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    period: Mapped[BudgetPeriod] = mapped_column(
        Enum(BudgetPeriod, name="budget_period", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=BudgetPeriod.monthly,
    )
    limit_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    alert_threshold_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
