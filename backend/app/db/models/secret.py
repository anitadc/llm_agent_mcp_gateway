import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Secret(Base):
    """Backing store for the Postgres SecretProvider (app/secrets/postgres_provider.py).
    `encrypted_value` is Fernet ciphertext, never plaintext -- see that module's
    docstring for the security tradeoff this backend makes. `tenant` is `""`
    (never NULL) for the default/shared namespace so the unique constraint below
    actually enforces one row per (tenant, secret_name); Postgres treats every
    NULL as distinct from every other NULL, so a nullable tenant column would let
    duplicate default-namespace secrets slip in.
    """

    __tablename__ = "secrets"
    __table_args__ = (UniqueConstraint("tenant", "secret_name", name="uq_secrets_tenant_secret_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant: Mapped[str] = mapped_column(String, nullable=False, default="")
    secret_name: Mapped[str] = mapped_column(String, nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
