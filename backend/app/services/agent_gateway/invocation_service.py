from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger, log_method
from app.db.models.agent import Agent
from app.db.models.enums import AgentLifecycleStatus, RequestStatus
from app.repositories.agent_repo import AgentRepo
from app.secrets.service import SecretService
from app.services.policy_engine import PolicyEngine

logger = get_logger(__name__)


@dataclass
class AgentInvocationResult:
    agent: Agent | None
    authorization_decision: str
    status: RequestStatus
    result: Any | None
    error: str | None


class AgentInvocationService:
    """The governed invocation path: a consumer asks for a `capability`, never a
    specific agent or endpoint (per the spec's "consumer independence"
    principle). Only `active` agents are ever candidates, and the same
    PolicyEngine that gates MCP `tools/call` also gates this -- registration
    and approval only ever establish *eligibility*, never authorization.

    Only REMOTE_HTTP dispatch is implemented. Real A2A remote invocation and the
    LangGraph same-process Agent Boundary are both Future Capability (see
    docs/agent-gateway.md) -- this is the one execution mode that fits the
    existing architecture without a protocol library or framework integration,
    but the registry/approval/policy/audit pipeline in front of it is exactly
    what those modes would plug into later, unchanged.
    """

    def __init__(self, agent_repo: AgentRepo, secret_service: SecretService, settings: Settings) -> None:
        self.agent_repo = agent_repo
        self.secret_service = secret_service
        self.settings = settings

    @log_method(logger)
    async def invoke(
        self,
        *,
        capability: str,
        operation: str | None,
        payload: dict[str, Any],
        roles: list[str],
        identity_provider: str | None,
        policy_engine: PolicyEngine,
    ) -> AgentInvocationResult:
        candidates = await self.agent_repo.list_by_capability(capability, AgentLifecycleStatus.active)
        if not candidates:
            logger.warning("agent_invocation_no_active_agent", capability=capability)
            return AgentInvocationResult(
                agent=None,
                authorization_decision="no_active_agent",
                status=RequestStatus.error,
                result=None,
                error=f"No active agent serves capability '{capability}'",
            )

        for agent in candidates:
            decision = await policy_engine.evaluate(
                project_id=None, roles=roles, identity_provider=identity_provider, agent_key=agent.agent_key
            )
            if decision.allowed:
                return await self._dispatch(agent, operation, payload)

        logger.warning("agent_invocation_denied", capability=capability, roles=roles, identity_provider=identity_provider)
        return AgentInvocationResult(
            agent=None,
            authorization_decision="denied",
            status=RequestStatus.error,
            result=None,
            error="No access policy permits this role/identity provider for any agent serving this capability",
        )

    @log_method(logger)
    async def _dispatch(self, agent: Agent, operation: str | None, payload: dict[str, Any]) -> AgentInvocationResult:
        if not agent.endpoint_url:
            return AgentInvocationResult(
                agent=agent,
                authorization_decision="allowed",
                status=RequestStatus.error,
                result=None,
                error=f"Agent '{agent.agent_key}' has no endpoint_url configured",
            )

        headers = await self._resolve_auth_headers(agent)
        body = {"operation": operation, "payload": payload}
        try:
            async with httpx.AsyncClient(timeout=self.settings.agent_invocation_timeout_seconds) as client:
                response = await client.post(agent.endpoint_url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.exception("agent_invocation_request_failed", agent_key=agent.agent_key)
            return AgentInvocationResult(
                agent=agent,
                authorization_decision="allowed",
                status=RequestStatus.error,
                result=None,
                error=f"Agent '{agent.agent_key}' request failed: {exc}",
            )

        parsed = self._parse_body(response)
        # A non-2xx from the target agent is a completed invocation, not a
        # gateway failure -- same "is_error, don't raise" treatment RestExecutor
        # gives a REST-backed MCP tool's response.
        if response.status_code >= 400:
            logger.warning(
                "agent_invocation_error_response", agent_key=agent.agent_key, status_code=response.status_code
            )
            return AgentInvocationResult(
                agent=agent,
                authorization_decision="allowed",
                status=RequestStatus.error,
                result=parsed,
                error=f"Agent responded with HTTP {response.status_code}",
            )
        logger.info("agent_invocation_succeeded", agent_key=agent.agent_key, agent_version=agent.version)
        return AgentInvocationResult(
            agent=agent, authorization_decision="allowed", status=RequestStatus.success, result=parsed, error=None
        )

    @staticmethod
    @log_method(logger)
    def _parse_body(response: httpx.Response) -> Any:
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    @log_method(logger)
    async def _resolve_auth_headers(self, agent: Agent) -> dict[str, str]:
        config = agent.auth_config or {}
        auth_type = config.get("type", "none")
        if auth_type == "none":
            return {}
        credential_ref = config.get("credential_ref")
        value = await self.secret_service.get_secret(credential_ref) if credential_ref else None
        if not value:
            return {}
        if auth_type == "bearer":
            return {"Authorization": f"Bearer {value}"}
        if auth_type == "api_key":
            return {config.get("header_name", "X-API-Key"): value}
        return {}
