import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ARRAY, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import (
    AgentHealthStatus,
    AgentLifecycleStatus,
    AgentProtocol,
    AgentRiskClass,
    AgentTrustLevel,
    AgentVisibility,
)

if TYPE_CHECKING:
    from app.db.models.agent_approval_task import AgentApprovalTask
    from app.db.models.agent_invocation import AgentInvocation


class Agent(Base):
    """The Agent Registry's row shape: one registered agent, its (simplified,
    non-A2A-schema-validated -- see services/agent_gateway/agent_registry_service.py)
    Agent Card, and the governance state (lifecycle/risk/trust) that decides
    whether it's eligible to be routed to. Registration alone never implies
    authorization -- see `services/policy_engine.py` for the separate RBAC/ABAC
    gate every invocation still passes through."""

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_team: Mapped[str | None] = mapped_column(String, nullable=True)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[str] = mapped_column(String, nullable=False, default="1.0.0")

    # Which capability keys a consumer's InvokeRequest.capability can resolve to
    # this agent for -- the "consumer asks for capability, not endpoint" principle.
    # Multiple agents may serve the same capability; `priority` (lower = preferred,
    # same ascending convention as RoutingRule target `weight`) breaks the tie.
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    risk_class: Mapped[AgentRiskClass] = mapped_column(
        Enum(AgentRiskClass, name="agent_risk_class", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AgentRiskClass.low,
    )
    trust_level: Mapped[AgentTrustLevel] = mapped_column(
        Enum(AgentTrustLevel, name="agent_trust_level", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AgentTrustLevel.t1_registered_internal,
    )
    status: Mapped[AgentLifecycleStatus] = mapped_column(
        Enum(AgentLifecycleStatus, name="agent_lifecycle_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AgentLifecycleStatus.draft,
    )

    # REMOTE_HTTP invocation target. `protocol` selects the wire format
    # AgentInvocationService._dispatch uses against it -- `remote_http` (default,
    # every pre-existing agent) sends this app's own {"operation","payload"} JSON;
    # `a2a` sends an Agent2Agent-protocol JSON-RPC 2.0 envelope instead. Real A2A
    # remote invocation via that mode and the LangGraph same-process boundary are
    # otherwise still evolving (see docs/agent-gateway.md). endpoint_url is
    # required before an agent can publish either way.
    endpoint_url: Mapped[str | None] = mapped_column(String, nullable=True)
    protocol: Mapped[AgentProtocol] = mapped_column(
        Enum(AgentProtocol, name="agent_protocol", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AgentProtocol.remote_http,
    )
    # {"type": "none"|"bearer"|"api_key", "credential_ref": "SECRET_NAME", "header_name": "X-API-Key"}
    # credential_ref is resolved through the Secret Provider layer at invocation
    # time, never stored here -- mirrors ApiService.auth_config.
    auth_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Simplified Agent Card (NOT validated against the official A2A JSON schema --
    # see docs/agent-gateway.md's scope notes): free-form provider/skills/modality
    # metadata surfaced via GET /v1/agents/{id}/agent-card.
    card: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Marketplace visibility. `published` is the default so every agent that
    # existed before this field was added keeps its exact current behavior
    # (invocable by any caller that clears PolicyEngine, from anywhere). `private`
    # additionally requires project_id and an agent_project_enablements row for
    # the caller's project -- see AgentRepo.list_by_capability.
    visibility: Mapped[AgentVisibility] = mapped_column(
        Enum(AgentVisibility, name="agent_visibility", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AgentVisibility.published,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    # Surfaced to consumers of the catalog once status == deprecated; purely
    # informational, never enforced.
    deprecation_notice: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Liveness as observed by the last probe (see
    # services/agent_gateway/health_checker.py) -- unknown until the first probe.
    health_status: Mapped[AgentHealthStatus] = mapped_column(
        Enum(AgentHealthStatus, name="agent_health_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AgentHealthStatus.unknown,
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Incremented once per submit_for_approval call and stamped onto every
    # AgentApprovalTask it creates, so a rejected-then-resubmitted agent's review
    # history groups cleanly into rounds instead of one flat undifferentiated list.
    current_submission_round: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    approval_tasks: Mapped[list["AgentApprovalTask"]] = relationship(back_populates="agent", lazy="raise_on_sql")
    invocations: Mapped[list["AgentInvocation"]] = relationship(back_populates="agent", lazy="raise_on_sql")
