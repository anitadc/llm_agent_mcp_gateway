import uuid

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_agent_approval_task_repo,
    get_agent_registry_service,
    get_agent_repo,
    get_approval_service,
    require_roles,
)
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.enums import UserRole
from app.db.models.user import User
from app.repositories.agent_approval_task_repo import AgentApprovalTaskRepo
from app.repositories.agent_repo import AgentRepo
from app.schemas.agent import AgentApprovalTaskOut, AgentCreate, AgentOut, AgentUpdate, ApprovalDecisionRequest
from app.services.agent_gateway.agent_registry_service import AgentRegistryService
from app.services.agent_gateway.approval_service import ApprovalService

router = APIRouter(prefix="/v1/agents", tags=["agent_gateway"])
logger = get_logger(__name__)


@router.get("", response_model=list[AgentOut])
async def list_agents(
    user: User = Depends(require_roles(UserRole.admin)), repo: AgentRepo = Depends(get_agent_repo)
) -> list[AgentOut]:
    agents = await repo.list()
    logger.info("listing agents", user_id=user.id, count=len(agents))
    return [AgentOut.from_model(a) for a in agents]


@router.post("", response_model=AgentOut, status_code=201)
async def register_agent(
    body: AgentCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    logger.info("registering agent", user_id=user.id, agent_key=body.agent_key, name=body.name)
    agent = await registry.register(submitted_by=user.id, **body.model_dump())
    return AgentOut.from_model(agent)


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
) -> AgentOut:
    logger.info("fetching agent", user_id=user.id, agent_id=str(agent_id))
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    return AgentOut.from_model(agent)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    logger.info("updating agent", user_id=user.id, agent_id=str(agent_id), fields=list(body.model_dump(exclude_none=True)))
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.update(agent, **body.model_dump())
    return AgentOut.from_model(agent)


@router.get("/{agent_id}/agent-card")
async def get_agent_card(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
) -> dict:
    logger.info("fetching agent card", user_id=user.id, agent_id=str(agent_id))
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    return AgentRegistryService.build_agent_card(agent)


@router.post("/{agent_id}/submit", response_model=list[AgentApprovalTaskOut])
async def submit_agent_for_approval(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    agent_repo: AgentRepo = Depends(get_agent_repo),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
    approval: ApprovalService = Depends(get_approval_service),
) -> list[AgentApprovalTaskOut]:
    logger.info("submitting agent for approval", user_id=user.id, agent_id=str(agent_id))
    agent = await agent_repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    await approval.submit_for_approval(agent)
    tasks = await task_repo.list_by_agent(agent.id)
    return [AgentApprovalTaskOut.from_model(t) for t in tasks]


@router.get("/{agent_id}/approvals", response_model=list[AgentApprovalTaskOut])
async def list_agent_approvals(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
) -> list[AgentApprovalTaskOut]:
    tasks = await task_repo.list_by_agent(agent_id)
    logger.info("listing agent approvals", user_id=user.id, agent_id=str(agent_id), count=len(tasks))
    return [AgentApprovalTaskOut.from_model(t) for t in tasks]


@router.post("/{agent_id}/publish", response_model=AgentOut)
async def publish_agent(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    logger.info("publishing agent", user_id=user.id, agent_id=str(agent_id))
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.publish(agent)
    return AgentOut.from_model(agent)


@router.post("/{agent_id}/suspend", response_model=AgentOut)
async def suspend_agent(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    logger.info("suspending agent", user_id=user.id, agent_id=str(agent_id))
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.suspend(agent)
    return AgentOut.from_model(agent)


@router.post("/{agent_id}/reactivate", response_model=AgentOut)
async def reactivate_agent(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    logger.info("reactivating agent", user_id=user.id, agent_id=str(agent_id))
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.reactivate(agent)
    return AgentOut.from_model(agent)


@router.post("/{agent_id}/deprecate", response_model=AgentOut)
async def deprecate_agent(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    logger.info("deprecating agent", user_id=user.id, agent_id=str(agent_id))
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.deprecate(agent)
    return AgentOut.from_model(agent)


@router.post("/{agent_id}/retire", response_model=AgentOut)
async def retire_agent(
    agent_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AgentRepo = Depends(get_agent_repo),
    registry: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentOut:
    logger.info("retiring agent", user_id=user.id, agent_id=str(agent_id))
    agent = await repo.get(agent_id)
    if agent is None:
        raise NotFoundError("Agent not found")
    agent = await registry.retire(agent)
    return AgentOut.from_model(agent)


approvals_router = APIRouter(prefix="/v1/agent-approvals", tags=["agent_gateway"])


@approvals_router.get("", response_model=list[AgentApprovalTaskOut])
async def list_pending_approvals(
    user: User = Depends(require_roles(UserRole.admin)),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
) -> list[AgentApprovalTaskOut]:
    tasks = await task_repo.list_pending()
    logger.info("listing pending approvals", user_id=user.id, count=len(tasks))
    return [AgentApprovalTaskOut.from_model(t) for t in tasks]


@approvals_router.post("/{task_id}/approve", response_model=AgentApprovalTaskOut)
async def approve_task(
    task_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    user: User = Depends(require_roles(UserRole.admin)),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
    approval: ApprovalService = Depends(get_approval_service),
) -> AgentApprovalTaskOut:
    logger.info("approving agent task", user_id=user.id, task_id=str(task_id), approved=True)
    task = await task_repo.get(task_id)
    if task is None:
        raise NotFoundError("Approval task not found")
    task = await approval.decide(task, approved=True, approver_user_id=user.id, reason=body.reason)
    return AgentApprovalTaskOut.from_model(task)


@approvals_router.post("/{task_id}/reject", response_model=AgentApprovalTaskOut)
async def reject_task(
    task_id: uuid.UUID,
    body: ApprovalDecisionRequest,
    user: User = Depends(require_roles(UserRole.admin)),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
    approval: ApprovalService = Depends(get_approval_service),
) -> AgentApprovalTaskOut:
    logger.info("rejecting agent task", user_id=user.id, task_id=str(task_id), approved=False)
    task = await task_repo.get(task_id)
    if task is None:
        raise NotFoundError("Approval task not found")
    task = await approval.decide(task, approved=False, approver_user_id=user.id, reason=body.reason)
    return AgentApprovalTaskOut.from_model(task)
