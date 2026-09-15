import uuid
from datetime import datetime
from typing import Any, List, Dict, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import ModelCapability, RoutingStrategy


class RoutingRule(Base):
    __tablename__ = "routing_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_alias: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    # Opaque end-user id from ChatCompletionRequest.user / EmbeddingRequest.user.
    # Deliberately NOT a foreign key: this never joins to `users` (see TDD.md §3.2.4).
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    capability: Mapped[ModelCapability] = mapped_column(
        Enum(ModelCapability, name="model_capability", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ModelCapability.chat,
    )
    strategy: Mapped[RoutingStrategy] = mapped_column(
        Enum(RoutingStrategy, name="routing_strategy", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RoutingStrategy.priority,
    )
    targets: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
