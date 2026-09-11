import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.db.models.agent import Agent
from app.db.models.agent_approval_comment import AgentApprovalComment
from app.db.models.agent_approval_task import AgentApprovalTask
from app.db.models.enums import (
    AgentApprovalDecision,
    AgentApprovalStage,
    AgentHealthStatus,
    AgentLifecycleStatus,
    AgentProtocol,
    AgentRiskClass,
    AgentTrustLevel,
    AgentVisibility,
)


class AgentCreate(BaseModel):
    agent_key: str
    name: str
    description: str | None = None
    owner_team: str | None = None
    domain: str | None = None
    version: str = "1.0.0"
    capabilities: list[str] = []
    priority: int = 100
    risk_class: AgentRiskClass = AgentRiskClass.low
    trust_level: AgentTrustLevel = AgentTrustLevel.t1_registered_internal
    endpoint_url: str | None = None
    protocol: AgentProtocol = AgentProtocol.remote_http
    auth_config: dict[str, Any] = {}
    card: dict[str, Any] = {}
    visibility: AgentVisibility = AgentVisibility.published
    project_id: uuid.UUID | None = None


class AgentUpdate(BaseModel):
    """Only mutable while the agent hasn't reached `active` -- see
    services/agent_gateway/agent_registry_service.py."""

    name: str | None = None
    description: str | None = None
    owner_team: str | None = None
    domain: str | None = None
    capabilities: list[str] | None = None
    priority: int | None = None
    risk_class: AgentRiskClass | None = None
    trust_level: AgentTrustLevel | None = None
    endpoint_url: str | None = None
    protocol: AgentProtocol | None = None
    auth_config: dict[str, Any] | None = None
    card: dict[str, Any] | None = None
    visibility: AgentVisibility | None = None
    project_id: uuid.UUID | None = None
    deprecation_notice: str | None = None


class AgentOut(BaseModel):
    id: uuid.UUID
    agent_key: str
    name: str
    description: str | None = None
    owner_team: str | None = None
    domain: str | None = None
    version: str
    capabilities: list[str]
    priority: int
    risk_class: AgentRiskClass
    trust_level: AgentTrustLevel
    status: AgentLifecycleStatus
    endpoint_url: str | None = None
    protocol: AgentProtocol
    auth_config: dict[str, Any]
    card: dict[str, Any]
    visibility: AgentVisibility
    project_id: uuid.UUID | None = None
    deprecation_notice: str | None = None
    health_status: AgentHealthStatus
    last_heartbeat: datetime | None = None
    current_submission_round: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, agent: Agent) -> "AgentOut":
        return cls(
            id=agent.id,
            agent_key=agent.agent_key,
            name=agent.name,
            description=agent.description,
            owner_team=agent.owner_team,
            domain=agent.domain,
            version=agent.version,
            capabilities=agent.capabilities,
            priority=agent.priority,
            risk_class=agent.risk_class,
            trust_level=agent.trust_level,
            status=agent.status,
            endpoint_url=agent.endpoint_url,
            protocol=agent.protocol,
            auth_config=agent.auth_config,
            card=agent.card,
            visibility=agent.visibility,
            project_id=agent.project_id,
            deprecation_notice=agent.deprecation_notice,
            health_status=agent.health_status,
            last_heartbeat=agent.last_heartbeat,
            current_submission_round=agent.current_submission_round,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )


class AgentCatalogEntryOut(BaseModel):
    """The consumer-facing catalog view -- deliberately excludes auth_config
    (which may reference a credential name) and any admin-only governance
    fields; see GET /v1/agents/catalog."""

    id: uuid.UUID
    agent_key: str
    name: str
    description: str | None = None
    owner_team: str | None = None
    domain: str | None = None
    version: str
    capabilities: list[str]
    status: AgentLifecycleStatus
    deprecation_notice: str | None = None
    health_status: AgentHealthStatus

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, agent: Agent) -> "AgentCatalogEntryOut":
        return cls(
            id=agent.id,
            agent_key=agent.agent_key,
            name=agent.name,
            description=agent.description,
            owner_team=agent.owner_team,
            domain=agent.domain,
            version=agent.version,
            capabilities=agent.capabilities,
            status=agent.status,
            deprecation_notice=agent.deprecation_notice,
            health_status=agent.health_status,
        )


class AgentEnablementRequest(BaseModel):
    project_id: uuid.UUID


class AgentStatsOut(BaseModel):
    agent_id: uuid.UUID
    window_minutes: int
    request_count: int
    error_count: int
    avg_latency_ms: float | None = None
    total_cost_usd: Decimal | None = None


class AgentPricingSet(BaseModel):
    cost_per_invocation: Decimal


class AgentPricingOut(BaseModel):
    agent_id: uuid.UUID
    cost_per_invocation: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentApprovalTaskOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_key: str
    stage: AgentApprovalStage
    decision: AgentApprovalDecision
    approver_user_id: uuid.UUID | None = None
    reason: str | None = None
    decided_at: datetime | None = None
    assigned_reviewer_user_id: uuid.UUID | None = None
    due_at: datetime | None = None
    escalated_at: datetime | None = None
    evidence_links: list[str]
    submission_round: int
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, task: AgentApprovalTask) -> "AgentApprovalTaskOut":
        return cls(
            id=task.id,
            agent_id=task.agent_id,
            agent_key=task.agent.agent_key,
            stage=task.stage,
            decision=task.decision,
            approver_user_id=task.approver_user_id,
            reason=task.reason,
            decided_at=task.decided_at,
            assigned_reviewer_user_id=task.assigned_reviewer_user_id,
            due_at=task.due_at,
            escalated_at=task.escalated_at,
            evidence_links=task.evidence_links,
            submission_round=task.submission_round,
            created_at=task.created_at,
        )


class ApprovalDecisionRequest(BaseModel):
    reason: str | None = None


class ApprovalReviewerAssignRequest(BaseModel):
    reviewer_user_id: uuid.UUID | None = None


class ApprovalEvidenceRequest(BaseModel):
    evidence_links: list[str]


class ApprovalCommentCreate(BaseModel):
    body: str


class ApprovalCommentOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    author_user_id: uuid.UUID | None = None
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, comment: AgentApprovalComment) -> "ApprovalCommentOut":
        return cls(
            id=comment.id,
            task_id=comment.task_id,
            author_user_id=comment.author_user_id,
            body=comment.body,
            created_at=comment.created_at,
        )


class AgentAuditLogOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID | None = None
    action: str
    actor_user_id: uuid.UUID | None = None
    details: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedAgentAuditLog(BaseModel):
    items: list[AgentAuditLogOut]
    page: int
    page_size: int
    total: int


class InvokeRequest(BaseModel):
    capability: str
    operation: str | None = None
    payload: dict[str, Any] = {}
    correlation_id: str | None = None


class InvokeResponse(BaseModel):
    invocation_id: uuid.UUID
    status: str
    target_agent_key: str | None = None
    target_agent_version: str | None = None
    protocol: str
    authorization_decision: str
    latency_ms: int
    result: Any | None = None
    error: str | None = None
    cost_usd: Decimal | None = None


class AgentInvocationOut(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    capability: str
    operation: str | None = None
    agent_id: uuid.UUID | None = None
    authorization_decision: str
    status: str
    latency_ms: int
    cost_usd: Decimal | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
