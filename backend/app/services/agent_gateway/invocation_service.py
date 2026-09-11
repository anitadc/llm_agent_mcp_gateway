import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger, log_method
from app.db.models.agent import Agent
from app.db.models.enums import AgentLifecycleStatus, AgentProtocol, AgentVisibility, RequestStatus
from app.repositories.agent_pricing_repo import AgentPricingRepo
from app.repositories.agent_project_enablement_repo import AgentProjectEnablementRepo
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
    cost_usd: Decimal | None = None
    # Internal to this module: whether a dispatch failure is worth retrying
    # against the next eligible candidate (a transport error or a 5xx from the
    # agent) versus a definitive business rejection (a 4xx) that would likely
    # fail identically anywhere else. Never surfaced in the API response.
    retryable: bool = field(default=False, repr=False)


class AgentInvocationService:
    """The governed invocation path: a consumer asks for a `capability`, never a
    specific agent or endpoint (per the spec's "consumer independence"
    principle). Only `active` agents are ever candidates, tried in `priority`
    order; a `private`-visibility agent is additionally gated by
    AgentProjectEnablement before the same PolicyEngine that gates MCP
    `tools/call` is applied -- registration and approval only ever establish
    *eligibility*, never authorization. A retryable dispatch failure (a
    transport error or a 5xx) falls through to the next eligible candidate; a
    4xx from the agent is treated as a definitive rejection and returned as-is.

    Two dispatch wire formats exist per-agent (`Agent.protocol`):
    `remote_http` (default, this app's own {"operation","payload"} JSON -- every
    agent registered before this field existed keeps using it unchanged) and
    `a2a` (a best-effort Agent2Agent protocol JSON-RPC 2.0 envelope, not
    verified against a live A2A server). The LangGraph same-process Agent
    Boundary is still Future Capability (see docs/agent-gateway.md) -- the
    registry/approval/policy/audit pipeline in front of dispatch is exactly
    what that mode would plug into later, unchanged.
    """

    def __init__(
        self,
        agent_repo: AgentRepo,
        secret_service: SecretService,
        settings: Settings,
        enablement_repo: AgentProjectEnablementRepo | None = None,
        pricing_repo: AgentPricingRepo | None = None,
    ) -> None:
        self.agent_repo = agent_repo
        self.secret_service = secret_service
        self.settings = settings
        self.enablement_repo = enablement_repo
        self.pricing_repo = pricing_repo

    @log_method(logger)
    async def _is_reachable(self, agent: Agent, project_id: uuid.UUID | None) -> bool:
        """The marketplace visibility gate -- independent of, and evaluated
        before, the PolicyEngine's role/identity-provider gate below. A
        `published` agent (every agent registered before AgentVisibility
        existed, since that's its default) is reachable by anyone, exactly as
        today. A `private` agent is reachable only by its owning project or a
        project explicitly enabled for it."""
        if agent.visibility != AgentVisibility.private:
            return True
        if project_id is not None and agent.project_id == project_id:
            return True
        if project_id is None or self.enablement_repo is None:
            return False
        return await self.enablement_repo.is_enabled(agent.id, project_id)

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
        project_id: uuid.UUID | None = None,
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

        attempted: list[str] = []
        last_result: AgentInvocationResult | None = None
        for agent in candidates:
            if not await self._is_reachable(agent, project_id):
                continue
            decision = await policy_engine.evaluate(
                project_id=None, roles=roles, identity_provider=identity_provider, agent_key=agent.agent_key
            )
            if not decision.allowed:
                continue
            attempted.append(agent.agent_key)
            result = await self._dispatch(agent, operation, payload)
            if result.status == RequestStatus.success or not result.retryable:
                return await self._price(result)
            # A retryable failure (transport error / 5xx) falls through to the
            # next eligible candidate instead of giving up immediately -- a
            # non-retryable one (a 4xx business rejection) is returned as-is,
            # since another agent implementation would most likely reject the
            # same payload the same way.
            logger.warning("agent_invocation_retrying_next_candidate", failed_agent_key=agent.agent_key, capability=capability)
            last_result = result

        if attempted:
            # Every eligible candidate was tried and every one failed retryably.
            if last_result is not None:
                return await self._price(last_result)
            return AgentInvocationResult(
                agent=None,
                authorization_decision="allowed",
                status=RequestStatus.error,
                result=None,
                error=f"All {len(attempted)} eligible agent(s) for capability '{capability}' failed",
            )

        logger.warning("agent_invocation_denied", capability=capability, roles=roles, identity_provider=identity_provider)
        return AgentInvocationResult(
            agent=None,
            authorization_decision="denied",
            status=RequestStatus.error,
            result=None,
            error="No access policy permits this role/identity provider for any agent serving this capability",
        )

    @log_method(logger)
    async def _price(self, result: AgentInvocationResult) -> AgentInvocationResult:
        """Computes cost_usd for a completed dispatch attempt. Deliberately
        leaves it None (not 0) when no AgentPricing row exists for the agent --
        see AgentInvocation.cost_usd's docstring for why that distinction
        matters; this mirrors the LLM Gateway's CostService.calculate() except
        for that one difference."""
        if result.agent is None or self.pricing_repo is None:
            return result
        pricing = await self.pricing_repo.get_by_agent(result.agent.id)
        if pricing is None:
            logger.warning("agent_pricing_not_found", agent_key=result.agent.agent_key)
            return result
        result.cost_usd = pricing.cost_per_invocation
        return result

	@log_method(logger)
    async def _dispatch(self, agent: Agent, operation: str | None, payload: dict[str, Any]) -> AgentInvocationResult:
        if not agent.endpoint_url:
            return AgentInvocationResult(
                agent=agent,
                authorization_decision="allowed",
                status=RequestStatus.error,
                result=None,
                error=f"Agent '{agent.agent_key}' has no endpoint_url configured",
                retryable=False,
            )

        headers = await self._resolve_auth_headers(agent)
        try:
            async with httpx.AsyncClient(timeout=self.settings.agent_invocation_timeout_seconds) as client:
                if agent.protocol == AgentProtocol.a2a:
                    response = await client.post(agent.endpoint_url, json=self._a2a_envelope(operation, payload), headers=headers)
                else:
                    response = await client.post(
                        agent.endpoint_url, json={"operation": operation, "payload": payload}, headers=headers
                    )
        except httpx.HTTPError as exc:
            logger.exception("agent_invocation_request_failed", agent_key=agent.agent_key)
            return AgentInvocationResult(
                agent=agent,
                authorization_decision="allowed",
                status=RequestStatus.error,
                result=None,
                error=f"Agent '{agent.agent_key}' request failed: {exc}",
                retryable=True,
            )

        parsed = self._parse_body(response)
        if agent.protocol == AgentProtocol.a2a and isinstance(parsed, dict) and parsed.get("error"):
            # A JSON-RPC-level error in an otherwise-200 A2A response -- the
            # Agent2Agent analogue of mcp_gateway.py treating a JSON-RPC `error`
            # key as a completed-but-failed call, not a transport failure.
            logger.warning("agent_invocation_a2a_error", agent_key=agent.agent_key, error=parsed["error"])
            return AgentInvocationResult(
                agent=agent,
                authorization_decision="allowed",
                status=RequestStatus.error,
                result=parsed,
                error=f"Agent returned a JSON-RPC error: {parsed['error']}",
                retryable=False,
            )
        # A non-2xx from the target agent is a completed invocation, not a
        # gateway failure -- same "is_error, don't raise" treatment RestExecutor
        # gives a REST-backed MCP tool's response. Only a 5xx is retried against
        # another candidate; a 4xx is treated as a definitive business rejection.
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
                retryable=response.status_code >= 500,
            )
        logger.info("agent_invocation_succeeded", agent_key=agent.agent_key, agent_version=agent.version)
        return AgentInvocationResult(
            agent=agent, authorization_decision="allowed", status=RequestStatus.success, result=parsed, error=None
        )

    @staticmethod
	@log_method(logger)
    def _a2a_envelope(operation: str | None, payload: dict[str, Any]) -> dict[str, Any]:
        """A best-effort Agent2Agent (A2A) protocol `message/send` JSON-RPC 2.0
        envelope -- NOT verified against a live A2A server (Future Capability,
        see docs/agent-gateway.md); the operation/payload this app's own callers
        already send is serialized into the message's single text part so a
        real A2A agent still receives the caller's intent even though the
        wire shape around it is A2A-flavored rather than this app's ad-hoc one."""
        text = json.dumps({"operation": operation, "payload": payload})
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": {"message": {"role": "user", "messageId": str(uuid.uuid4()), "parts": [{"kind": "text", "text": text}]}},
        }

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
