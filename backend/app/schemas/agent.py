import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.db.models.agent import Agent
from app.db.models.agent_approval_task import AgentApprovalTask
from app.db.models.enums import AgentApprovalDecision, AgentApprovalStage, AgentLifecycleStatus, AgentRiskClass, AgentTrustLevel


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
    auth_config: dict[str, Any] = {}
    card: dict[str, Any] = {}


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
    auth_config: dict[str, Any] | None = None
    card: dict[str, Any] | None = None


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
    auth_config: dict[str, Any]
    card: dict[str, Any]
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
            auth_config=agent.auth_config,
            card=agent.card,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )


class AgentApprovalTaskOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_key: str
    stage: AgentApprovalStage
    decision: AgentApprovalDecision
    approver_user_id: uuid.UUID | None = None
    reason: str | None = None
    decided_at: datetime | None = None
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
            created_at=task.created_at,
        )


class ApprovalDecisionRequest(BaseModel):
    reason: str | None = None


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


class AgentInvocationOut(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    capability: str
    operation: str | None = None
    agent_id: uuid.UUID | None = None
    authorization_decision: str
    status: str
    latency_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}
