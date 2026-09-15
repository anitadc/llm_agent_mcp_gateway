from typing import Optional
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import ProviderNameEnum


class ModelPricing(Base):
    __tablename__ = "model_pricing"
    __table_args__ = (UniqueConstraint("provider", "model"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[ProviderNameEnum] = mapped_column(
        Enum(ProviderNameEnum, name="provider_name", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_per_1k: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    completion_per_1k: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
