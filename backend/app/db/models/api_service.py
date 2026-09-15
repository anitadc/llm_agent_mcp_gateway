import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import ApiServiceStatus, RestAuthType

if TYPE_CHECKING:
    from app.db.models.api_endpoint import ApiEndpoint


class ApiService(Base):
    """The API Service Registry's row shape: one enterprise REST backend,
    reachable at `base_url`, plus the auth/timeout/retry config every endpoint
    registered under it inherits. Mirrors McpServer on purpose -- REST APIs and
    MCP servers are both "a thing tools execute against", registered and
    governed the same way."""

    __tablename__ = "api_services"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_url: Mapped[str] = mapped_column(String, nullable=False)

    authentication_type: Mapped[RestAuthType] = mapped_column(
        Enum(RestAuthType, name="rest_auth_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RestAuthType.none,
    )
    # Shape depends on authentication_type -- every *_ref field names a secret
    # resolved through the existing Secret Provider layer at execution time, the
    # raw value is never stored here:
    #   api_key:    {"credential_ref": "SECRET_NAME", "header_name": "X-API-Key"}
    #   bearer:     {"credential_ref": "SECRET_NAME"}
    #   basic:      {"username_ref": "SECRET_NAME", "password_ref": "SECRET_NAME"}
    #   oauth2_client_credentials:
    #               {"token_url": "...", "client_id_ref": "SECRET_NAME",
    #                "client_secret_ref": "SECRET_NAME", "scope": "..."}
    auth_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Static headers merged into every request to this service (e.g. "Accept").
    headers: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    # {"max_attempts": 2, "backoff_multiplier": 0.2, "backoff_max": 2.0}
    retry_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Per-service request budget for the rate limiter; None falls back to the
    # gateway's mcp_default_rate_limit_per_window, same convention as tools.
    rate_limit_per_window: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[ApiServiceStatus] = mapped_column(
        Enum(ApiServiceStatus, name="api_service_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ApiServiceStatus.active,
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    endpoints: Mapped[list["ApiEndpoint"]] = relationship(back_populates="api_service", lazy="raise_on_sql")
