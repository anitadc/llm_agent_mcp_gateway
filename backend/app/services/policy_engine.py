import uuid
from dataclasses import dataclass

from app.core.logging import get_logger
from app.db.models.access_policy import AccessPolicy
from app.repositories.access_policy_repo import AccessPolicyRepo

logger = get_logger(__name__)


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str | None = None


class PolicyEngine:
    """RBAC/ABAC gate, evaluated generically over UserIdentity.roles/.provider and
    (for MCP tool calls) the tool name being invoked -- it never looks at a
    concrete IdentityProvider or a concrete tool implementation, only the
    mapped-to fields every provider/tool produces, so it evaluates identically
    regardless of which IdP authenticated the caller or whether the tool is
    MCP- or REST-backed.

    Semantics: no active policy at all for a project means unrestricted (so a
    deployment that hasn't configured any policies isn't suddenly locked out).
    Once at least one policy exists, access is granted if ANY policy matches
    (an OR across policies); within one policy, an empty allowed_roles,
    allowed_identity_providers, or allowed_tool_names list means "unrestricted
    on that dimension" -- it only constrains what's actually listed. This is
    how "only finance agents can execute payment APIs" is expressed: a policy
    with allowed_roles=["finance"] and allowed_tool_names=["create_payment"].

    Arbitrary request-argument evaluation (e.g. "block if amount > $10,000") is
    NOT implemented -- see docs/api-registry.md's scope notes; a rule engine over
    tool arguments is a real feature, not a small addition, and is called out
    there as a Future Capability rather than silently half-built here.

    `agent_key` is the Agent Gateway analogue of `tool_name`, checked against its
    own `allowed_agent_keys` column rather than being conflated with
    `allowed_tool_names` -- a policy scoped to MCP tools should not accidentally
    also gate (or fail to gate) agent invocations just because both happen to be
    named the same string. See services/agent_gateway/invocation_service.py.
    """

    def __init__(self, repo: AccessPolicyRepo) -> None:
        self.repo = repo

    async def evaluate(
        self,
        project_id: uuid.UUID | None,
        roles: list[str],
        identity_provider: str | None,
        tool_name: str | None = None,
        agent_key: str | None = None,
    ) -> PolicyDecision:
        policies = await self.repo.list_active_for_project(project_id)
        if not policies:
            return PolicyDecision(allowed=True)

        if any(self._matches(policy, roles, identity_provider, tool_name, agent_key) for policy in policies):
            return PolicyDecision(allowed=True)
        logger.warning(
            "policy_denied",
            project_id=str(project_id) if project_id else None,
            roles=roles,
            identity_provider=identity_provider,
            tool_name=tool_name,
            agent_key=agent_key,
        )
        return PolicyDecision(
            allowed=False, reason="No access policy permits this role / identity provider / tool / agent combination"
        )

    @staticmethod
    def _matches(
        policy: AccessPolicy,
        roles: list[str],
        identity_provider: str | None,
        tool_name: str | None,
        agent_key: str | None,
    ) -> bool:
        if policy.allowed_identity_providers and identity_provider not in policy.allowed_identity_providers:
            return False
        if policy.allowed_roles and not (set(roles) & set(policy.allowed_roles)):
            return False
        if policy.allowed_tool_names and tool_name not in policy.allowed_tool_names:
            return False
        if policy.allowed_agent_keys and agent_key not in policy.allowed_agent_keys:
            return False
        return True
