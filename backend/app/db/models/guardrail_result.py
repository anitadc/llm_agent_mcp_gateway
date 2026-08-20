import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import GuardrailDirection

if TYPE_CHECKING:
    from app.db.models.request_log import RequestLog


class GuardrailResult(Base):
    __tablename__ = "guardrail_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("request_logs.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[GuardrailDirection] = mapped_column(
        Enum(GuardrailDirection, name="guardrail_direction", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    violations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    request_log: Mapped["RequestLog"] = relationship(back_populates="guardrail_results")
