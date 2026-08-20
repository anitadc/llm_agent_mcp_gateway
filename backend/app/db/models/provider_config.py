import uuid

from sqlalchemy import Boolean, Enum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import ProviderNameEnum


class ProviderConfig(Base):
    __tablename__ = "provider_configs"
    __table_args__ = (UniqueConstraint("provider", "display_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[ProviderNameEnum] = mapped_column(
        Enum(ProviderNameEnum, name="provider_name", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    credential_ref: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
