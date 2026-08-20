import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import IdentityProviderName


class TenantIdentityConfig(Base):
    """Multi-tenant identity support: lets Customer A authenticate via Entra and
    Customer B via Keycloak against the same running gateway process. `issuer`
    is denormalized (not derived from `configuration` at query time) so the
    auth middleware can resolve which tenant a token belongs to with a single
    indexed lookup on the token's unverified `iss` claim, before it knows
    anything else about the request. `configuration` holds Settings-field-name
    overrides for that provider (e.g. {"entra_tenant_id": ..., "entra_client_id":
    ...}) -- never a raw client secret; a `*_client_secret_ref` key inside it
    names a Secret Provider entry instead, mirroring McpServer.auth_config and
    ProviderConfig.credential_ref."""

    __tablename__ = "tenant_identity_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    provider: Mapped[IdentityProviderName] = mapped_column(
        Enum(IdentityProviderName, name="identity_provider_name", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    issuer: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
