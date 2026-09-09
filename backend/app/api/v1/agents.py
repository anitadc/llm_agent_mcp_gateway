import uuid

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.deps import (
    get_agent_approval_comment_repo,
    get_agent_approval_task_repo,
    get_agent_audit_log_repo,
    get_agent_health_checker,
    get_agent_invocation_repo,
    get_agent_pricing_repo,
    get_agent_project_enablement_repo,
    get_agent_registry_service,
    get_agent_repo,
    get_approval_service,
    get_current_principal,
    require_roles,
)
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.agent_pricing import AgentPricing
from app.db.models.enums import AgentVisibility, UserRole
from app.db.models.user import User
from app.middleware.auth_middleware import Principal
from app.repositories.agent_approval_comment_repo import AgentApprovalCommentRepo
from app.repositories.agent_approval_task_repo import AgentApprovalTaskRepo
from app.repositories.agent_audit_log_repo import AgentAuditLogRepo
from app.repositories.agent_invocation_repo import AgentInvocationRepo
from app.repositories.agent_pricing_repo import AgentPricingRepo
from app.repositories.agent_project_enablement_repo import AgentProjectEnablementRepo
from app.repositories.agent_repo import AgentRepo
from app.schemas.agent import (
    AgentApprovalTaskOut,
    AgentCatalogEntryOut,
    AgentCreate,
    AgentEnablementRequest,
    AgentOut,
    AgentPricingOut,
    AgentPricingSet,
    AgentStatsOut,
    AgentUpdate,
    ApprovalCommentCreate,
    ApprovalCommentOut,
    ApprovalDecisionRequest,
    ApprovalEvidenceRequest,
    ApprovalReviewerAssignRequest,
    PaginatedAgentAuditLog,
)
from app.services.agent_gateway.agent_registry_service import AgentRegistryService
from app.services.agent_gateway.approval_service import ApprovalService
from app.services.agent_gateway.health_checker import AgentHealthChecker
from app.services.logging_service import record_agent_audit

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/agents", tags=["agent_gateway"])


@router.get("", response_model=list[AgentOut])
async def list_agents(
    user: User = Depends(require_roles(UserRole.admin)), repo: AgentRepo = Depends(get_agent_repo)
) -> list[AgentOut]:
    return [AgentOut.from_model(a) for a in await repo.list()]


@router.get("/catalog", response_model=list[AgentCatalogEntryOut])
async def browse_agent_catalog(
    principal: Principal = Depends(get_current_principal),
    repo: AgentRepo = Depends(get_agent_repo),
    enablement_repo: AgentProjectEnablementRepo = Depends(get_agent_project_enablement_repo),
) -> list[AgentCatalogEntryOut]:
    """The marketplace browsing view -- any authenticated caller (API key or
    IdP user), not admin-only, since this is discovery, not registry
    management -- same access level as GET /v1/agent-invocations. Shows every
    `published` agent plus any `private` one the caller's own project (API-key
    callers only; IdP users have no project context) has been enabled for."""
    project_id = principal.api_key.project_id if principal.kind == "api_key" and principal.api_key else None
    agents = await repo.list_for_catalog()
    visible = []
    for agent in agents:
        if agent.visibility != AgentVisibility.private:
            visible.append(agent)
        elif project_id is not None and (
            agent.project_id == project_id or await enablement_repo.is_enabled(agent.id, project_id)
        ):
            visible.append(agent)
    return [AgentCatalogEntryOut.from_model(a) for a in visible]


@router.post("", response_model=AgentOut, status_code=201)
async def register_agent(
    body: AgentCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    agent = await registry.register(submitted_by=user.id, **body.model_dump())
    background_tasks.add_task(
        record_agent_audit, agent_id=agent.id, action="registered", actor_user_id=user.id, details={"agent_key": agent.agent_key}
    )
    return AgentOut.from_model(agent)


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
) -> AgentOut:
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    return AgentOut.from_model(agent)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdate,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.update(agent, **body.model_dump())
    background_tasks.add_task(record_agent_audit, agent_id=agent.id, action="updated", actor_user_id=user.id)
    return AgentOut.from_model(agent)


@router.get("/{agent_id}/agent-card")
async def get_agent_card(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
) -> dict:
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    return AgentRegistryService.build_agent_card(agent)


@router.post("/{agent_id}/submit", response_model=list[AgentApprovalTaskOut])
async def submit_agent_for_approval(
    agent_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    agent_repo: AgentRepo = Depends(get_agent_repo),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
    approval: ApprovalService = Depends(get_approval_service),
) -> list[AgentApprovalTaskOut]:
    agent = await agent_repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    await approval.submit_for_approval(agent)
    background_tasks.add_task(
        record_agent_audit,
        agent_id=agent.id,
        action="submitted",
        actor_user_id=user.id,
        details={"submission_round": agent.current_submission_round},
    )
    tasks = await task_repo.list_by_agent(agent.id)
    return [AgentApprovalTaskOut.from_model(t) for t in tasks]


@router.get("/{agent_id}/approvals", response_model=list[AgentApprovalTaskOut])
async def list_agent_approvals(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
) -> list[AgentApprovalTaskOut]:
    return [AgentApprovalTaskOut.from_model(t) for t in await task_repo.list_by_agent(agent_id)]


@router.get("/{agent_id}/audit-log", response_model=PaginatedAgentAuditLog)
async def get_agent_audit_log(
    agent_id: uuid.UUID,
    page: int = 1,
    page_size: int = 25,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentAuditLogRepo = Depends(get_agent_audit_log_repo),
) -> PaginatedAgentAuditLog:
    items, total = await repo.list_paginated(agent_id=agent_id, page=page, page_size=min(page_size, 100))
    return PaginatedAgentAuditLog(items=items, page=page, page_size=page_size, total=total)


@router.get("/{agent_id}/stats", response_model=AgentStatsOut)
async def get_agent_stats(
    agent_id: uuid.UUID,
    window_minutes: int = 60,
    user: User = Depends(require_roles(UserRole.admin)),
    agent_repo: AgentRepo = Depends(get_agent_repo),
    invocation_repo: AgentInvocationRepo = Depends(get_agent_invocation_repo),
) -> AgentStatsOut:
    agent = await agent_repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    stats = await invocation_repo.stats_for_agent(agent_id, window_minutes)
    return AgentStatsOut(agent_id=agent_id, **stats)


@router.get("/{agent_id}/pricing", response_model=AgentPricingOut)
async def get_agent_pricing(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentPricingRepo = Depends(get_agent_pricing_repo),
) -> AgentPricingOut:
    pricing = await repo.get_by_agent(agent_id)
    if pricing is None:
        raise NotFoundError("No pricing set for this agent")
    return AgentPricingOut.model_validate(pricing)


@router.put("/{agent_id}/pricing", response_model=AgentPricingOut)
async def set_agent_pricing(
    agent_id: uuid.UUID,
    body: AgentPricingSet,
    user: User = Depends(require_roles(UserRole.admin)),
    agent_repo: AgentRepo = Depends(get_agent_repo),
    repo: AgentPricingRepo = Depends(get_agent_pricing_repo),
) -> AgentPricingOut:
    if await agent_repo.get(agent_id) is None:
        raise NotFoundError("Agent not found")
    existing = await repo.get_by_agent(agent_id)
    if existing is None:
        existing = await repo.add(AgentPricing(agent_id=agent_id, cost_per_invocation=body.cost_per_invocation))
    else:
        existing.cost_per_invocation = body.cost_per_invocation
        await repo.db.flush()
        await repo.db.refresh(existing)
    logger.info("agent_pricing_set", agent_id=str(agent_id), cost_per_invocation=str(body.cost_per_invocation))
    return AgentPricingOut.model_validate(existing)


@router.post("/{agent_id}/health-check", response_model=AgentOut)
async def trigger_agent_health_check(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    health_checker: AgentHealthChecker = Depends(get_agent_health_checker),
) -> AgentOut:
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    await health_checker.probe(agent)
    return AgentOut.from_model(agent)


@router.post("/{agent_id}/enable-project", status_code=204)
async def enable_agent_for_project(
    agent_id: uuid.UUID,
    body: AgentEnablementRequest,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> None:
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    await registry.enable_for_project(agent, body.project_id, enabled_by_user_id=user.id)


@router.post("/{agent_id}/disable-project", status_code=204)
async def disable_agent_for_project(
    agent_id: uuid.UUID,
    body: AgentEnablementRequest,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> None:
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    await registry.disable_for_project(agent, body.project_id)


@router.post("/{agent_id}/publish", response_model=AgentOut)
async def publish_agent(
    agent_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.publish(agent)
    background_tasks.add_task(record_agent_audit, agent_id=agent.id, action="published", actor_user_id=user.id)
    return AgentOut.from_model(agent)


@router.post("/{agent_id}/suspend", response_model=AgentOut)
async def suspend_agent(
    agent_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.suspend(agent)
    background_tasks.add_task(record_agent_audit, agent_id=agent.id, action="suspended", actor_user_id=user.id)
    return AgentOut.from_model(agent)


@router.post("/{agent_id}/reactivate", response_model=AgentOut)
async def reactivate_agent(
    agent_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.reactivate(agent)
    background_tasks.add_task(record_agent_audit, agent_id=agent.id, action="reactivated", actor_user_id=user.id)
    return AgentOut.from_model(agent)


@router.post("/{agent_id}/deprecate", response_model=AgentOut)
async def deprecate_agent(
    agent_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.deprecate(agent)
    background_tasks.add_task(record_agent_audit, agent_id=agent.id, action="deprecated", actor_user_id=user.id)
    return AgentOut.from_model(agent)


@router.post("/{agent_id}/retire", response_model=AgentOut)
async def retire_agent(
    agent_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.retire(agent)
    background_tasks.add_task(record_agent_audit, agent_id=agent.id, action="retired", actor_user_id=user.id)
    return AgentOut.from_model(agent)


approvals_router = APIRouter(prefix="/v1/agent-approvals", tags=["agent_gateway"])


@approvals_router.get("", response_model=list[AgentApprovalTaskOut])
async def list_pending_approvals(
    user: User = Depends(require_roles(UserRole.admin)),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
) -> list[AgentApprovalTaskOut]:
    return [AgentApprovalTaskOut.from_model(t) for t in await task_repo.list_pending()]


@approvals_router.post("/{task_id}/approve", response_model=AgentApprovalTaskOut)
async def approve_task(
    task_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
    approval: ApprovalService = Depends(get_approval_service),
) -> AgentApprovalTaskOut:
    task = await task_repo.get(task_id)
    if task is None:
        raise NotFoundError("Approval task not found")
    task = await approval.decide(task, approved=True, approver=user, reason=body.reason)
    background_tasks.add_task(
        record_agent_audit,
        agent_id=task.agent_id,
        action="approved_stage",
        actor_user_id=user.id,
        details={"stage": task.stage.value, "task_id": str(task.id)},
    )
    return AgentApprovalTaskOut.from_model(task)


@approvals_router.post("/{task_id}/reject", response_model=AgentApprovalTaskOut)
async def reject_task(
    task_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
    approval: ApprovalService = Depends(get_approval_service),
) -> AgentApprovalTaskOut:
    task = await task_repo.get(task_id)
    if task is None:
        raise NotFoundError("Approval task not found")
    task = await approval.decide(task, approved=False, approver=user, reason=body.reason)
    background_tasks.add_task(
        record_agent_audit,
        agent_id=task.agent_id,
        action="rejected_stage",
        actor_user_id=user.id,
        details={"stage": task.stage.value, "task_id": str(task.id)},
    )
    return AgentApprovalTaskOut.from_model(task)


@approvals_router.post("/{task_id}/assign-reviewer", response_model=AgentApprovalTaskOut)
async def assign_approval_reviewer(
    task_id: uuid.UUID,
    body: ApprovalReviewerAssignRequest,
    user: User = Depends(require_roles(UserRole.admin)),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
    approval: ApprovalService = Depends(get_approval_service),
) -> AgentApprovalTaskOut:
    task = await task_repo.get(task_id)
    if task is None:
        raise NotFoundError("Approval task not found")
    task = await approval.assign_reviewer(task, body.reviewer_user_id)
    return AgentApprovalTaskOut.from_model(task)


@approvals_router.patch("/{task_id}/evidence", response_model=AgentApprovalTaskOut)
async def add_approval_evidence(
    task_id: uuid.UUID,
    body: ApprovalEvidenceRequest,
    user: User = Depends(require_roles(UserRole.admin)),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
    approval: ApprovalService = Depends(get_approval_service),
) -> AgentApprovalTaskOut:
    task = await task_repo.get(task_id)
    if task is None:
        raise NotFoundError("Approval task not found")
    task = await approval.add_evidence_links(task, body.evidence_links)
    return AgentApprovalTaskOut.from_model(task)


@approvals_router.get("/{task_id}/comments", response_model=list[ApprovalCommentOut])
async def list_approval_comments(
    task_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    comment_repo: AgentApprovalCommentRepo = Depends(get_agent_approval_comment_repo),
) -> list[ApprovalCommentOut]:
    return [ApprovalCommentOut.from_model(c) for c in await comment_repo.list_by_task(task_id)]


@approvals_router.post("/{task_id}/comments", response_model=ApprovalCommentOut, status_code=201)
async def add_approval_comment(
    task_id: uuid.UUID,
    body: ApprovalCommentCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
    approval: ApprovalService = Depends(get_approval_service),
) -> ApprovalCommentOut:
    task = await task_repo.get(task_id)
    if task is None:
        raise NotFoundError("Approval task not found")
    comment = await approval.add_comment(task, author_user_id=user.id, body=body.body)
    return ApprovalCommentOut.from_model(comment)
