from typing import Any

from app.core.exceptions import BadRequestError
from app.core.logging import get_logger, log_method
from app.db.models.agent import Agent
from app.db.models.enums import AgentLifecycleStatus
from app.repositories.agent_repo import AgentRepo
from app.services.agent_gateway import lifecycle

logger = get_logger(__name__)


@log_method(logger)
def validate_agent_card(agent: Agent) -> list[str]:
    """Lightweight structural validation only -- NOT validation against the
    official A2A Agent Card JSON Schema. Real A2A schema/version/interface
    compliance is a documented Future Capability (see docs/agent-gateway.md);
    this is deliberately just enough to catch an obviously incomplete
    registration before it consumes a human reviewer's time."""
    problems: list[str] = []
    if not agent.name:
        problems.append("name is required")
    if not agent.capabilities:
        problems.append("at least one capability is required")
    if not agent.endpoint_url:
        problems.append("endpoint_url is required")
    return problems


class AgentRegistryService:
    """Facade for the Agent Registry: registration, editing while still in
    draft/rejected, and the terminal lifecycle actions (publish/suspend/
    deprecate/retire). Approval-stage orchestration itself lives in
    ApprovalService -- kept separate so "what is an agent" and "how does an
    agent get approved" don't end up in one file, mirroring how DiscoveryService
    and ApiRegistryService are split from the MCP/API Registry proper."""

    def __init__(self, agent_repo: AgentRepo) -> None:
        self.agent_repo = agent_repo

    @log_method(logger)
    async def register(self, **fields: Any) -> Agent:
        if await self.agent_repo.get_by_key(fields["agent_key"]) is not None:
            raise BadRequestError(f"Agent key '{fields['agent_key']}' is already registered")
        agent = await self.agent_repo.add(Agent(status=AgentLifecycleStatus.draft, **fields))
        logger.info("agent_registered", agent_key=agent.agent_key, agent_id=str(agent.id))
        return agent

    @log_method(logger)
    async def update(self, agent: Agent, **fields: Any) -> Agent:
        if agent.status not in (AgentLifecycleStatus.draft, AgentLifecycleStatus.rejected):
            raise BadRequestError(f"Agent '{agent.agent_key}' cannot be edited while '{agent.status.value}'")
        for key, value in fields.items():
            if value is not None:
                setattr(agent, key, value)
        await self.agent_repo.db.flush()
        await self.agent_repo.db.refresh(agent)
        return agent

    @log_method(logger)
    async def publish(self, agent: Agent) -> Agent:
        lifecycle.require_transition(agent.status, AgentLifecycleStatus.active)
        problems = validate_agent_card(agent)
        if problems:
            logger.warning("agent_publish_rejected", agent_key=agent.agent_key, problems=problems)
            raise BadRequestError(f"Cannot publish '{agent.agent_key}': {'; '.join(problems)}")
        agent.status = AgentLifecycleStatus.active
        await self.agent_repo.db.flush()
        await self.agent_repo.db.refresh(agent)
        logger.info("agent_published", agent_key=agent.agent_key)
        return agent

    @log_method(logger)
    async def suspend(self, agent: Agent) -> Agent:
        lifecycle.require_transition(agent.status, AgentLifecycleStatus.suspended)
        agent.status = AgentLifecycleStatus.suspended
        await self.agent_repo.db.flush()
        await self.agent_repo.db.refresh(agent)
        logger.info("agent_suspended", agent_key=agent.agent_key)
        return agent

    @log_method(logger)
    async def reactivate(self, agent: Agent) -> Agent:
        lifecycle.require_transition(agent.status, AgentLifecycleStatus.active)
        agent.status = AgentLifecycleStatus.active
        await self.agent_repo.db.flush()
        await self.agent_repo.db.refresh(agent)
        logger.info("agent_reactivated", agent_key=agent.agent_key)
        return agent

    @log_method(logger)
    async def deprecate(self, agent: Agent) -> Agent:
        lifecycle.require_transition(agent.status, AgentLifecycleStatus.deprecated)
        agent.status = AgentLifecycleStatus.deprecated
        await self.agent_repo.db.flush()
        await self.agent_repo.db.refresh(agent)
        logger.info("agent_deprecated", agent_key=agent.agent_key)
        return agent

    @log_method(logger)
    async def retire(self, agent: Agent) -> Agent:
        lifecycle.require_transition(agent.status, AgentLifecycleStatus.retired)
        agent.status = AgentLifecycleStatus.retired
        await self.agent_repo.db.flush()
        await self.agent_repo.db.refresh(agent)
        logger.info("agent_retired", agent_key=agent.agent_key)
        return agent

    @staticmethod
    @log_method(logger)
    def build_agent_card(agent: Agent) -> dict[str, Any]:
        """A simplified Agent Card -- NOT the official A2A schema (Future
        Capability). Governed fields always win over whatever a registrant put
        in the free-form `card` JSON, and auth_config/credential_ref is never
        included -- an Agent Card must never expose a secret reference."""
        return {
            **agent.card,
            "name": agent.name,
            "description": agent.description,
            "version": agent.version,
            "capabilities": agent.capabilities,
            "provider": {"organization": agent.owner_team, "domain": agent.domain},
        }
