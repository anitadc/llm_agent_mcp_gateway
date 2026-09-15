import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import IdentityProviderName, UserRole


class User(Base):
    __tablename__ = "users"
    # A subject id is only unique *within* one identity provider -- two
    # different IdPs could theoretically mint the same string, so the natural
    # key is the (provider, external_sub) pair, not external_sub alone.
    __table_args__ = (UniqueConstraint("identity_provider", "external_sub"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identity_provider: Mapped[IdentityProviderName] = mapped_column(
        Enum(IdentityProviderName, name="identity_provider_name", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=IdentityProviderName.keycloak,
    )
    external_sub: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserRole.developer,
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
