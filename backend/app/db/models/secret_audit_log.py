import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import SecretAuditStatus, SecretOperation


class SecretAuditLog(Base):
    """Audit trail for the Secret Provider layer. Deliberately has no column that
    could ever hold a secret value -- only who did what, to which secret NAME,
    against which provider/tenant, and whether it succeeded."""

    __tablename__ = "secret_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    operation: Mapped[SecretOperation] = mapped_column(
        Enum(SecretOperation, name="secret_operation", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    secret_name: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[SecretAuditStatus] = mapped_column(
        Enum(SecretAuditStatus, name="secret_audit_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
