import uuid
from datetime import datetime, timedelta, timezone

from app.core.exceptions import BadRequestError, ForbiddenError
from app.core.logging import get_logger, log_method
from app.db.models.agent import Agent
from app.db.models.agent_approval_comment import AgentApprovalComment
from app.db.models.agent_approval_task import AgentApprovalTask
from app.db.models.enums import AgentApprovalDecision, AgentApprovalStage, AgentLifecycleStatus, AgentRiskClass, UserRole
from app.db.models.user import User
from app.repositories.agent_approval_comment_repo import AgentApprovalCommentRepo
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

    def __init__(
        self,
        agent_repo: AgentRepo,
        task_repo: AgentApprovalTaskRepo,
        configured_stages: str,
        comment_repo: AgentApprovalCommentRepo | None = None,
        sla_hours: int = 48,
    ) -> None:
        self.agent_repo = agent_repo
        self.task_repo = task_repo
        self._configured_stages = configured_stages
        self.comment_repo = comment_repo
        self._sla_hours = sla_hours

    @log_method(logger)
    def required_stages(self, agent: Agent) -> list[AgentApprovalStage]:
        stages = [AgentApprovalStage(s.strip()) for s in self._configured_stages.split(",") if s.strip()]
        if agent.risk_class == AgentRiskClass.high and AgentApprovalStage.production not in stages:
            stages.append(AgentApprovalStage.production)
        return stages

    @log_method(logger)
    async def submit_for_approval(self, agent: Agent) -> Agent:
        lifecycle.require_transition(agent.status, AgentLifecycleStatus.under_review)
        problems = validate_agent_card(agent)
        if problems:
            agent.status = AgentLifecycleStatus.rejected
            await self.agent_repo.db.flush()
            logger.warning("agent_card_validation_failed", agent_key=agent.agent_key, problems=problems)
            raise BadRequestError(f"Agent Card validation failed for '{agent.agent_key}': {'; '.join(problems)}")

        agent.status = AgentLifecycleStatus.under_review
        agent.current_submission_round += 1
        due_at = datetime.now(timezone.utc) + timedelta(hours=self._sla_hours) if self._sla_hours > 0 else None
        stages = self.required_stages(agent)
        for stage in stages:
            self.task_repo.db.add(
                AgentApprovalTask(
                    agent_id=agent.id,
                    stage=stage,
                    submission_round=agent.current_submission_round,
                    due_at=due_at,
                )
            )
        await self.agent_repo.db.flush()
        logger.info(
            "agent_submitted_for_approval",
            agent_key=agent.agent_key,
            stages=[s.value for s in stages],
            submission_round=agent.current_submission_round,
        )
        return agent

    @log_method(logger)
    async def decide(
        self, task: AgentApprovalTask, *, approved: bool, approver: User, reason: str | None
    ) -> AgentApprovalTask:
        if task.decision != AgentApprovalDecision.pending:
            raise BadRequestError(f"Approval task already decided ({task.decision.value})")
        # An assigned reviewer restricts who may decide -- but never below the
        # baseline every task already had before this field existed: any admin.
        if (
            task.assigned_reviewer_user_id is not None
            and task.assigned_reviewer_user_id != approver.id
            and approver.role != UserRole.admin
        ):
            logger.warning(
                "agent_approval_wrong_reviewer",
                task_id=str(task.id),
                assigned_reviewer_user_id=str(task.assigned_reviewer_user_id),
                attempted_by=str(approver.id),
            )
            raise ForbiddenError("This approval task is assigned to a different reviewer")

        task.decision = AgentApprovalDecision.approved if approved else AgentApprovalDecision.rejected
        task.approver_user_id = approver.id
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

        sibling_tasks = [t for t in await self.task_repo.list_by_agent(agent.id) if t.submission_round == task.submission_round]
        if all(t.decision == AgentApprovalDecision.approved for t in sibling_tasks):
            lifecycle.require_transition(agent.status, AgentLifecycleStatus.approved)
            agent.status = AgentLifecycleStatus.approved
            await self.agent_repo.db.flush()
            logger.info("agent_approved", agent_key=agent.agent_key)
        return task

	@log_method(logger)
    async def assign_reviewer(self, task: AgentApprovalTask, reviewer_user_id: uuid.UUID | None) -> AgentApprovalTask:
        task.assigned_reviewer_user_id = reviewer_user_id
        await self.task_repo.db.flush()
        logger.info(
            "agent_approval_reviewer_assigned",
            task_id=str(task.id),
            reviewer_user_id=str(reviewer_user_id) if reviewer_user_id else None,
        )
        return task

	@log_method(logger)
    async def add_evidence_links(self, task: AgentApprovalTask, links: list[str]) -> AgentApprovalTask:
        task.evidence_links = [*task.evidence_links, *links]
        await self.task_repo.db.flush()
        logger.info("agent_approval_evidence_added", task_id=str(task.id), link_count=len(links))
        return task

	@log_method(logger)
    async def add_comment(self, task: AgentApprovalTask, author_user_id: uuid.UUID | None, body: str) -> AgentApprovalComment:
        if self.comment_repo is None:
            raise BadRequestError("Approval comments are not available on this ApprovalService instance")
        comment = await self.comment_repo.add(
            AgentApprovalComment(task_id=task.id, author_user_id=author_user_id, body=body)
        )
        logger.info("agent_approval_comment_added", task_id=str(task.id))
        return comment

	@log_method(logger)
    async def escalate_overdue(self) -> list[AgentApprovalTask]:
        """The SLA sweep's core: find every pending task past its due_at that
        hasn't been flagged yet, mark it escalated, and log it -- there's no
        email/Slack integration to page anyone yet, so `escalated_at` plus this
        log line is the visible signal an operator watching the Agent Approvals
        page (or logs) needs to notice and act on."""
        overdue = await self.task_repo.list_overdue(datetime.now(timezone.utc))
        for task in overdue:
            task.escalated_at = datetime.now(timezone.utc)
            logger.warning(
                "agent_approval_overdue",
                task_id=str(task.id),
                agent_key=task.agent.agent_key,
                stage=task.stage.value,
                due_at=task.due_at.isoformat() if task.due_at else None,
            )
        if overdue:
            await self.task_repo.db.flush()
        return overdue
