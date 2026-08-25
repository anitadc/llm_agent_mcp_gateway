import uuid
from datetime import datetime, timezone

from app.core.exceptions import BadRequestError
from app.core.logging import get_logger
from app.db.models.agent import Agent
from app.db.models.agent_approval_task import AgentApprovalTask
from app.db.models.enums import AgentApprovalDecision, AgentApprovalStage, AgentLifecycleStatus, AgentRiskClass
from app.repositories.agent_approval_task_repo import AgentApprovalTaskRepo
from app.repositories.agent_repo import AgentRepo
from app.services.agent_gateway import lifecycle
from app.services.agent_gateway.agent_registry_service import validate_agent_card

logger = get_logger(__name__)


class ApprovalService:
    """Approval-workflow orchestration: which review stages an agent needs
    (configuration-driven -- `Settings.agent_approval_stages`, plus `production`
    whenever risk_class is `high` -- never hard-coded per agent), and moving an
    agent to `approved`/`rejected` once every task for it has a decision.
    Registration alone never implies authorization: approval only ever changes
    `Agent.status`, which is an *eligibility* precondition the PolicyEngine gate
    is still evaluated on top of at invocation time (see invocation_service.py)."""

    def __init__(self, agent_repo: AgentRepo, task_repo: AgentApprovalTaskRepo, configured_stages: str) -> None:
        self.agent_repo = agent_repo
        self.task_repo = task_repo
        self._configured_stages = configured_stages

    def required_stages(self, agent: Agent) -> list[AgentApprovalStage]:
        stages = [AgentApprovalStage(s.strip()) for s in self._configured_stages.split(",") if s.strip()]
        if agent.risk_class == AgentRiskClass.high and AgentApprovalStage.production not in stages:
            stages.append(AgentApprovalStage.production)
        return stages

    async def submit_for_approval(self, agent: Agent) -> Agent:
        lifecycle.require_transition(agent.status, AgentLifecycleStatus.under_review)
        problems = validate_agent_card(agent)
        if problems:
            agent.status = AgentLifecycleStatus.rejected
            await self.agent_repo.db.flush()
            logger.warning("agent_card_validation_failed", agent_key=agent.agent_key, problems=problems)
            raise BadRequestError(f"Agent Card validation failed for '{agent.agent_key}': {'; '.join(problems)}")

        agent.status = AgentLifecycleStatus.under_review
        stages = self.required_stages(agent)
        for stage in stages:
            self.task_repo.db.add(AgentApprovalTask(agent_id=agent.id, stage=stage))
        await self.agent_repo.db.flush()
        logger.info(
            "agent_submitted_for_approval",
            agent_key=agent.agent_key,
            stages=[s.value for s in stages],
        )
        return agent

    async def decide(
        self, task: AgentApprovalTask, *, approved: bool, approver_user_id: uuid.UUID, reason: str | None
    ) -> AgentApprovalTask:
        if task.decision != AgentApprovalDecision.pending:
            raise BadRequestError(f"Approval task already decided ({task.decision.value})")

        task.decision = AgentApprovalDecision.approved if approved else AgentApprovalDecision.rejected
        task.approver_user_id = approver_user_id
        task.reason = reason
        task.decided_at = datetime.now(timezone.utc)
        await self.task_repo.db.flush()

        agent = task.agent
        logger.info(
            "agent_approval_task_decided",
            agent_key=agent.agent_key,
            stage=task.stage.value,
            approved=approved,
        )
        if not approved:
            # A single rejected stage rejects the whole registration -- the
            # spec's review sub-stages (SECURITY/TECHNICAL/BUSINESS/...) are
            # gates, not votes.
            agent.status = AgentLifecycleStatus.rejected
            await self.agent_repo.db.flush()
            logger.info("agent_rejected", agent_key=agent.agent_key, stage=task.stage.value)
            return task

        sibling_tasks = await self.task_repo.list_by_agent(agent.id)
        if all(t.decision == AgentApprovalDecision.approved for t in sibling_tasks):
            lifecycle.require_transition(agent.status, AgentLifecycleStatus.approved)
            agent.status = AgentLifecycleStatus.approved
            await self.agent_repo.db.flush()
            logger.info("agent_approved", agent_key=agent.agent_key)
        return task
