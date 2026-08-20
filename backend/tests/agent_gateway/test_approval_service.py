import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.db.models.enums import AgentApprovalDecision, AgentLifecycleStatus, AgentRiskClass
from app.repositories.agent_approval_task_repo import AgentApprovalTaskRepo
from app.repositories.agent_repo import AgentRepo
from app.services.agent_gateway.agent_registry_service import AgentRegistryService
from app.services.agent_gateway.approval_service import ApprovalService


def _agent_fields(**overrides) -> dict:
    defaults = dict(
        agent_key="pricing-agent",
        name="Pricing Agent",
        description="Calculates order pricing",
        capabilities=["pricing"],
        endpoint_url="http://pricing-agent.test/invoke",
        risk_class=AgentRiskClass.low,
    )
    defaults.update(overrides)
    return defaults


async def _make(db_session: AsyncSession, stages: str = "security,technical,business", **agent_overrides):
    agent_repo = AgentRepo(db_session)
    task_repo = AgentApprovalTaskRepo(db_session)
    registry = AgentRegistryService(agent_repo)
    approval = ApprovalService(agent_repo, task_repo, stages)
    agent = await registry.register(**_agent_fields(**agent_overrides))
    await db_session.commit()
    return approval, task_repo, agent


@pytest.mark.asyncio
async def test_submit_creates_one_task_per_configured_stage(db_session: AsyncSession) -> None:
    approval, task_repo, agent = await _make(db_session)

    await approval.submit_for_approval(agent)
    await db_session.commit()

    tasks = await task_repo.list_by_agent(agent.id)
    assert {t.stage.value for t in tasks} == {"security", "technical", "business"}
    assert agent.status == AgentLifecycleStatus.under_review


@pytest.mark.asyncio
async def test_high_risk_agent_gets_an_additional_production_stage(db_session: AsyncSession) -> None:
    approval, task_repo, agent = await _make(db_session, risk_class=AgentRiskClass.high)

    await approval.submit_for_approval(agent)
    await db_session.commit()

    tasks = await task_repo.list_by_agent(agent.id)
    assert "production" in {t.stage.value for t in tasks}


@pytest.mark.asyncio
async def test_submit_rejects_an_agent_missing_endpoint_url(db_session: AsyncSession) -> None:
    approval, task_repo, agent = await _make(db_session, endpoint_url=None)

    with pytest.raises(BadRequestError):
        await approval.submit_for_approval(agent)

    assert agent.status == AgentLifecycleStatus.rejected
    assert await task_repo.list_by_agent(agent.id) == []


@pytest.mark.asyncio
async def test_agent_reaches_approved_only_once_every_task_is_approved(db_session: AsyncSession) -> None:
    approval, task_repo, agent = await _make(db_session, stages="security,technical")
    await approval.submit_for_approval(agent)
    await db_session.commit()
    tasks = await task_repo.list_by_agent(agent.id)

    await approval.decide(tasks[0], approved=True, approver_user_id=uuid.uuid4(), reason="looks fine")
    assert agent.status == AgentLifecycleStatus.under_review  # one stage still pending

    await approval.decide(tasks[1], approved=True, approver_user_id=uuid.uuid4(), reason="looks fine")
    assert agent.status == AgentLifecycleStatus.approved


@pytest.mark.asyncio
async def test_a_single_rejection_rejects_the_whole_agent(db_session: AsyncSession) -> None:
    approval, task_repo, agent = await _make(db_session, stages="security,technical")
    await approval.submit_for_approval(agent)
    await db_session.commit()
    tasks = await task_repo.list_by_agent(agent.id)

    await approval.decide(tasks[0], approved=False, approver_user_id=uuid.uuid4(), reason="fails security review")

    assert agent.status == AgentLifecycleStatus.rejected
    # The still-pending sibling task is left as-is -- rejection short-circuits
    # the agent, it doesn't force a decision on tasks nobody has reviewed yet.
    assert tasks[1].decision == AgentApprovalDecision.pending


@pytest.mark.asyncio
async def test_deciding_an_already_decided_task_raises(db_session: AsyncSession) -> None:
    approval, task_repo, agent = await _make(db_session, stages="security")
    await approval.submit_for_approval(agent)
    await db_session.commit()
    task = (await task_repo.list_by_agent(agent.id))[0]

    await approval.decide(task, approved=True, approver_user_id=uuid.uuid4(), reason=None)

    with pytest.raises(BadRequestError):
        await approval.decide(task, approved=True, approver_user_id=uuid.uuid4(), reason=None)
