import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.db.models.enums import AgentLifecycleStatus, AgentRiskClass
from app.repositories.agent_repo import AgentRepo
from app.services.agent_gateway.agent_registry_service import AgentRegistryService


def _agent_fields(**overrides) -> dict:
    defaults = dict(
        agent_key="pricing-agent",
        name="Pricing Agent",
        description="Calculates order pricing",
        capabilities=["pricing"],
        endpoint_url="http://pricing-agent.test/invoke",
    )
    defaults.update(overrides)
    return defaults


@pytest.mark.asyncio
async def test_register_creates_a_draft_agent(db_session: AsyncSession) -> None:
    registry = AgentRegistryService(AgentRepo(db_session))

    agent = await registry.register(**_agent_fields())
    await db_session.commit()

    assert agent.status == AgentLifecycleStatus.draft
    assert agent.agent_key == "pricing-agent"


@pytest.mark.asyncio
async def test_register_rejects_a_duplicate_agent_key(db_session: AsyncSession) -> None:
    registry = AgentRegistryService(AgentRepo(db_session))
    await registry.register(**_agent_fields())
    await db_session.commit()

    with pytest.raises(BadRequestError):
        await registry.register(**_agent_fields())


@pytest.mark.asyncio
async def test_update_is_allowed_while_draft(db_session: AsyncSession) -> None:
    registry = AgentRegistryService(AgentRepo(db_session))
    agent = await registry.register(**_agent_fields())
    await db_session.commit()

    updated = await registry.update(agent, name="Renamed Pricing Agent")

    assert updated.name == "Renamed Pricing Agent"


@pytest.mark.asyncio
async def test_update_is_rejected_once_under_review(db_session: AsyncSession) -> None:
    registry = AgentRegistryService(AgentRepo(db_session))
    agent = await registry.register(**_agent_fields())
    agent.status = AgentLifecycleStatus.under_review
    await db_session.commit()

    with pytest.raises(BadRequestError):
        await registry.update(agent, name="Should not work")


@pytest.mark.asyncio
async def test_publish_requires_approved_status(db_session: AsyncSession) -> None:
    registry = AgentRegistryService(AgentRepo(db_session))
    agent = await registry.register(**_agent_fields())
    await db_session.commit()

    with pytest.raises(BadRequestError):
        await registry.publish(agent)


@pytest.mark.asyncio
async def test_publish_succeeds_from_approved_and_moves_to_active(db_session: AsyncSession) -> None:
    registry = AgentRegistryService(AgentRepo(db_session))
    agent = await registry.register(**_agent_fields())
    agent.status = AgentLifecycleStatus.approved
    await db_session.commit()

    published = await registry.publish(agent)

    assert published.status == AgentLifecycleStatus.active


@pytest.mark.asyncio
async def test_publish_rejects_an_agent_missing_endpoint_url(db_session: AsyncSession) -> None:
    registry = AgentRegistryService(AgentRepo(db_session))
    agent = await registry.register(**_agent_fields(endpoint_url=None))
    agent.status = AgentLifecycleStatus.approved
    await db_session.commit()

    with pytest.raises(BadRequestError):
        await registry.publish(agent)


@pytest.mark.asyncio
async def test_suspend_then_reactivate_round_trip(db_session: AsyncSession) -> None:
    registry = AgentRegistryService(AgentRepo(db_session))
    agent = await registry.register(**_agent_fields())
    agent.status = AgentLifecycleStatus.active
    await db_session.commit()

    suspended = await registry.suspend(agent)
    assert suspended.status == AgentLifecycleStatus.suspended

    reactivated = await registry.reactivate(agent)
    assert reactivated.status == AgentLifecycleStatus.active


def test_build_agent_card_omits_auth_config() -> None:
    from app.db.models.agent import Agent

    agent = Agent(
        agent_key="pricing-agent",
        name="Pricing Agent",
        description="Calculates order pricing",
        capabilities=["pricing"],
        owner_team="finance",
        domain="finance",
        version="1.0.0",
        risk_class=AgentRiskClass.low,
        auth_config={"type": "bearer", "credential_ref": "PRICING_AGENT_TOKEN"},
        card={},
    )

    card = AgentRegistryService.build_agent_card(agent)

    assert "auth_config" not in card
    assert "credential_ref" not in str(card)
    assert card["capabilities"] == ["pricing"]
    assert card["provider"] == {"organization": "finance", "domain": "finance"}
