import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.access_policy import AccessPolicy
from app.db.models.agent import Agent
from app.db.models.enums import AgentLifecycleStatus
from app.repositories.agent_repo import AgentRepo
from app.services.agent_gateway.invocation_service import AgentInvocationService
from app.services.policy_engine import PolicyEngine


class _FakeSecretService:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    async def get_secret(self, secret_name: str, tenant: str | None = None, force_refresh: bool = False) -> str | None:
        return self.values.get(secret_name)


class _FakeAccessPolicyRepo:
    def __init__(self, policies: list[AccessPolicy]) -> None:
        self.policies = policies

    async def list_active_for_project(self, project_id):
        return self.policies


class _FakeSettings:
    agent_invocation_timeout_seconds = 5.0


def _unrestricted_policy_engine() -> PolicyEngine:
    return PolicyEngine(_FakeAccessPolicyRepo([]))


async def _seed_agent(db_session: AsyncSession, **overrides) -> Agent:
    defaults = dict(
        agent_key="pricing-agent",
        name="Pricing Agent",
        capabilities=["pricing"],
        endpoint_url="http://pricing-agent.test/invoke",
        status=AgentLifecycleStatus.active,
    )
    defaults.update(overrides)
    agent = Agent(**defaults)
    db_session.add(agent)
    await db_session.commit()
    return agent


@pytest.mark.asyncio
@respx.mock
async def test_invoke_dispatches_to_the_active_agent_serving_the_capability(db_session: AsyncSession) -> None:
    await _seed_agent(db_session)
    route = respx.post("http://pricing-agent.test/invoke").mock(return_value=httpx.Response(200, json={"price": 42}))
    service = AgentInvocationService(AgentRepo(db_session), _FakeSecretService({}), _FakeSettings())

    result = await service.invoke(
        capability="pricing",
        operation="calculate-price",
        payload={"sku": "abc"},
        roles=["developer"],
        identity_provider="keycloak",
        policy_engine=_unrestricted_policy_engine(),
    )

    assert route.called
    assert result.status.value == "success"
    assert result.result == {"price": 42}
    assert result.agent.agent_key == "pricing-agent"


@pytest.mark.asyncio
async def test_invoke_returns_error_when_no_active_agent_serves_the_capability(db_session: AsyncSession) -> None:
    service = AgentInvocationService(AgentRepo(db_session), _FakeSecretService({}), _FakeSettings())

    result = await service.invoke(
        capability="unknown-capability",
        operation=None,
        payload={},
        roles=["developer"],
        identity_provider="keycloak",
        policy_engine=_unrestricted_policy_engine(),
    )

    assert result.agent is None
    assert result.status.value == "error"
    assert result.authorization_decision == "no_active_agent"


@pytest.mark.asyncio
async def test_invoke_ignores_a_draft_agent_serving_the_same_capability(db_session: AsyncSession) -> None:
    await _seed_agent(db_session, agent_key="draft-pricing", status=AgentLifecycleStatus.draft)
    service = AgentInvocationService(AgentRepo(db_session), _FakeSecretService({}), _FakeSettings())

    result = await service.invoke(
        capability="pricing",
        operation=None,
        payload={},
        roles=["developer"],
        identity_provider="keycloak",
        policy_engine=_unrestricted_policy_engine(),
    )

    assert result.agent is None
    assert result.authorization_decision == "no_active_agent"


@pytest.mark.asyncio
async def test_invoke_denies_when_policy_engine_rejects_every_candidate(db_session: AsyncSession) -> None:
    await _seed_agent(db_session)
    policy = AccessPolicy(
        name="finance-only",
        allowed_roles=["finance"],
        allowed_agent_keys=[],
        allowed_identity_providers=[],
        allowed_tool_names=[],
        is_active=True,
    )
    engine = PolicyEngine(_FakeAccessPolicyRepo([policy]))
    service = AgentInvocationService(AgentRepo(db_session), _FakeSecretService({}), _FakeSettings())

    result = await service.invoke(
        capability="pricing", operation=None, payload={}, roles=["developer"], identity_provider="keycloak", policy_engine=engine
    )

    assert result.agent is None
    assert result.authorization_decision == "denied"


@pytest.mark.asyncio
@respx.mock
async def test_invoke_treats_non_2xx_response_as_a_completed_invocation_not_a_raised_exception(
    db_session: AsyncSession,
) -> None:
    await _seed_agent(db_session)
    respx.post("http://pricing-agent.test/invoke").mock(return_value=httpx.Response(422, json={"error": "bad sku"}))
    service = AgentInvocationService(AgentRepo(db_session), _FakeSecretService({}), _FakeSettings())

    result = await service.invoke(
        capability="pricing",
        operation=None,
        payload={},
        roles=["developer"],
        identity_provider="keycloak",
        policy_engine=_unrestricted_policy_engine(),
    )

    assert result.status.value == "error"
    assert result.authorization_decision == "allowed"
    assert result.result == {"error": "bad sku"}


@pytest.mark.asyncio
@respx.mock
async def test_invoke_returns_error_result_on_connection_failure_not_a_raised_exception(db_session: AsyncSession) -> None:
    await _seed_agent(db_session)
    respx.post("http://pricing-agent.test/invoke").mock(side_effect=httpx.ConnectError("boom"))
    service = AgentInvocationService(AgentRepo(db_session), _FakeSecretService({}), _FakeSettings())

    result = await service.invoke(
        capability="pricing",
        operation=None,
        payload={},
        roles=["developer"],
        identity_provider="keycloak",
        policy_engine=_unrestricted_policy_engine(),
    )

    assert result.status.value == "error"
    assert result.authorization_decision == "allowed"
    assert "failed" in result.error


@pytest.mark.asyncio
@respx.mock
async def test_invoke_injects_bearer_auth_resolved_via_secret_service(db_session: AsyncSession) -> None:
    await _seed_agent(db_session, auth_config={"type": "bearer", "credential_ref": "PRICING_AGENT_TOKEN"})
    route = respx.post("http://pricing-agent.test/invoke").mock(return_value=httpx.Response(200, json={}))
    service = AgentInvocationService(
        AgentRepo(db_session), _FakeSecretService({"PRICING_AGENT_TOKEN": "s3cr3t"}), _FakeSettings()
    )

    await service.invoke(
        capability="pricing",
        operation=None,
        payload={},
        roles=["developer"],
        identity_provider="keycloak",
        policy_engine=_unrestricted_policy_engine(),
    )

    assert route.calls[0].request.headers["Authorization"] == "Bearer s3cr3t"


@pytest.mark.asyncio
@respx.mock
async def test_invoke_prefers_the_lower_priority_number_among_multiple_candidates(db_session: AsyncSession) -> None:
    """Lower `priority` wins -- same ascending convention as RoutingRule target `weight`."""
    await _seed_agent(db_session, agent_key="low-priority-agent", priority=200, endpoint_url="http://low.test/invoke")
    await _seed_agent(db_session, agent_key="high-priority-agent", priority=10, endpoint_url="http://high.test/invoke")
    respx.post("http://low.test/invoke").mock(return_value=httpx.Response(200, json={"from": "low"}))
    high_route = respx.post("http://high.test/invoke").mock(return_value=httpx.Response(200, json={"from": "high"}))
    service = AgentInvocationService(AgentRepo(db_session), _FakeSecretService({}), _FakeSettings())

    result = await service.invoke(
        capability="pricing",
        operation=None,
        payload={},
        roles=["developer"],
        identity_provider="keycloak",
        policy_engine=_unrestricted_policy_engine(),
    )

    assert high_route.called
    assert result.result == {"from": "high"}
