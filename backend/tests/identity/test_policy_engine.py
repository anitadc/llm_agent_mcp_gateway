import pytest

from app.db.models.access_policy import AccessPolicy
from app.services.policy_engine import PolicyEngine


class _FakeAccessPolicyRepo:
    def __init__(self, policies: list[AccessPolicy]) -> None:
        self.policies = policies

    async def list_active_for_project(self, project_id):
        return self.policies


def _policy(**overrides) -> AccessPolicy:
    defaults = dict(
        name="test-policy",
        project_id=None,
        allowed_roles=[],
        allowed_identity_providers=[],
        allowed_tool_names=[],
        allowed_agent_keys=[],
        is_active=True,
    )
    defaults.update(overrides)
    return AccessPolicy(**defaults)


@pytest.mark.asyncio
async def test_no_policies_configured_means_unrestricted() -> None:
    engine = PolicyEngine(_FakeAccessPolicyRepo([]))

    decision = await engine.evaluate(project_id=None, roles=["viewer"], identity_provider="keycloak")

    assert decision.allowed is True


@pytest.mark.asyncio
async def test_policy_denies_a_role_not_in_allowed_roles() -> None:
    engine = PolicyEngine(_FakeAccessPolicyRepo([_policy(allowed_roles=["admin"])]))

    decision = await engine.evaluate(project_id=None, roles=["viewer"], identity_provider="keycloak")

    assert decision.allowed is False
    assert decision.reason


@pytest.mark.asyncio
async def test_policy_allows_a_matching_role() -> None:
    engine = PolicyEngine(_FakeAccessPolicyRepo([_policy(allowed_roles=["admin", "team_lead"])]))

    decision = await engine.evaluate(project_id=None, roles=["team_lead"], identity_provider="keycloak")

    assert decision.allowed is True


@pytest.mark.asyncio
async def test_policy_denies_a_disallowed_identity_provider() -> None:
    engine = PolicyEngine(_FakeAccessPolicyRepo([_policy(allowed_identity_providers=["entra"])]))

    decision = await engine.evaluate(project_id=None, roles=["admin"], identity_provider="keycloak")

    assert decision.allowed is False


@pytest.mark.asyncio
async def test_empty_allowed_lists_mean_unrestricted_on_that_dimension() -> None:
    engine = PolicyEngine(_FakeAccessPolicyRepo([_policy(allowed_roles=["admin"], allowed_identity_providers=[])]))

    decision = await engine.evaluate(project_id=None, roles=["admin"], identity_provider="anything-at-all")

    assert decision.allowed is True


@pytest.mark.asyncio
async def test_any_matching_policy_grants_access_when_multiple_exist() -> None:
    engine = PolicyEngine(
        _FakeAccessPolicyRepo([_policy(name="admins-only", allowed_roles=["admin"]), _policy(name="viewers-too", allowed_roles=["viewer"])])
    )

    decision = await engine.evaluate(project_id=None, roles=["viewer"], identity_provider="keycloak")

    assert decision.allowed is True


@pytest.mark.asyncio
async def test_policy_denies_a_tool_not_in_allowed_tool_names() -> None:
    """Expresses "only finance agents can execute payment APIs"."""
    engine = PolicyEngine(
        _FakeAccessPolicyRepo([_policy(allowed_roles=["finance"], allowed_tool_names=["create_payment"])])
    )

    decision = await engine.evaluate(
        project_id=None, roles=["finance"], identity_provider="keycloak", tool_name="get_customer"
    )

    assert decision.allowed is False


@pytest.mark.asyncio
async def test_policy_allows_a_matching_tool_name() -> None:
    engine = PolicyEngine(
        _FakeAccessPolicyRepo([_policy(allowed_roles=["finance"], allowed_tool_names=["create_payment"])])
    )

    decision = await engine.evaluate(
        project_id=None, roles=["finance"], identity_provider="keycloak", tool_name="create_payment"
    )

    assert decision.allowed is True


@pytest.mark.asyncio
async def test_empty_allowed_tool_names_means_unrestricted_on_that_dimension() -> None:
    engine = PolicyEngine(_FakeAccessPolicyRepo([_policy(allowed_roles=["admin"], allowed_tool_names=[])]))

    decision = await engine.evaluate(
        project_id=None, roles=["admin"], identity_provider="keycloak", tool_name="anything_at_all"
    )

    assert decision.allowed is True


@pytest.mark.asyncio
async def test_tool_name_defaults_to_none_for_non_tool_evaluations() -> None:
    """Callers that don't pass tool_name (none exist yet, but the parameter is
    optional for forward-compatibility) still get correctly gated on roles/idp."""
    engine = PolicyEngine(_FakeAccessPolicyRepo([_policy(allowed_roles=["admin"])]))

    decision = await engine.evaluate(project_id=None, roles=["admin"], identity_provider="keycloak")

    assert decision.allowed is True


@pytest.mark.asyncio
async def test_policy_denies_an_agent_key_not_in_allowed_agent_keys() -> None:
    engine = PolicyEngine(
        _FakeAccessPolicyRepo([_policy(allowed_roles=["finance"], allowed_agent_keys=["pricing-agent"])])
    )

    decision = await engine.evaluate(
        project_id=None, roles=["finance"], identity_provider="keycloak", agent_key="risk-agent"
    )

    assert decision.allowed is False


@pytest.mark.asyncio
async def test_policy_allows_a_matching_agent_key() -> None:
    engine = PolicyEngine(
        _FakeAccessPolicyRepo([_policy(allowed_roles=["finance"], allowed_agent_keys=["pricing-agent"])])
    )

    decision = await engine.evaluate(
        project_id=None, roles=["finance"], identity_provider="keycloak", agent_key="pricing-agent"
    )

    assert decision.allowed is True


@pytest.mark.asyncio
async def test_allowed_tool_names_and_allowed_agent_keys_are_independent_dimensions() -> None:
    """A policy scoped to a tool name must not accidentally also gate (or pass)
    an agent invocation sharing the same string, and vice versa."""
    engine = PolicyEngine(_FakeAccessPolicyRepo([_policy(allowed_tool_names=["shared-name"])]))

    decision = await engine.evaluate(project_id=None, roles=[], identity_provider="keycloak", agent_key="shared-name")

    assert decision.allowed is False


@pytest.mark.asyncio
async def test_empty_allowed_agent_keys_means_unrestricted_on_that_dimension() -> None:
    engine = PolicyEngine(_FakeAccessPolicyRepo([_policy(allowed_roles=["admin"], allowed_agent_keys=[])]))

    decision = await engine.evaluate(
        project_id=None, roles=["admin"], identity_provider="keycloak", agent_key="anything_at_all"
    )

    assert decision.allowed is True
