import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import ModelCapability, RequestStatus, RoutingStrategy
from app.db.models.organization import Organization
from app.db.models.project import Project
from app.db.models.request_log import RequestLog
from app.db.models.routing_rule import RoutingRule
from app.repositories.request_log_repo import RequestLogRepo
from app.repositories.routing_rule_repo import RoutingRuleRepo


async def _make_org_and_project(db_session: AsyncSession) -> tuple[Organization, Project]:
    org = Organization(name=f"org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()
    project = Project(organization_id=org.id, name=f"project-{uuid.uuid4().hex[:8]}")
    db_session.add(project)
    await db_session.flush()
    return org, project


@pytest.mark.asyncio
async def test_project_rule_beats_global_rule(db_session: AsyncSession, seeded_api_key) -> None:
    api_key, _ = seeded_api_key
    repo = RoutingRuleRepo(db_session)

    db_session.add(
        RoutingRule(
            model_alias="gateway-fast",
            project_id=None,
            strategy=RoutingStrategy.priority,
            capability=ModelCapability.chat,
            targets=[{"provider": "openai", "model": "gpt-4o-mini", "weight": 1}],
            priority=100,
        )
    )
    db_session.add(
        RoutingRule(
            model_alias="gateway-fast",
            project_id=api_key.project_id,
            strategy=RoutingStrategy.priority,
            capability=ModelCapability.chat,
            targets=[{"provider": "anthropic", "model": "claude-3-5-haiku-20241022", "weight": 1}],
            priority=200,
        )
    )
    await db_session.commit()

    match = await repo.find_best_match("gateway-fast", ModelCapability.chat, api_key.project_id)

    assert match is not None
    assert match.targets[0]["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_end_user_rule_beats_project_rule(db_session: AsyncSession, seeded_api_key) -> None:
    api_key, _ = seeded_api_key
    repo = RoutingRuleRepo(db_session)

    db_session.add(
        RoutingRule(
            model_alias="gateway-fast",
            project_id=api_key.project_id,
            strategy=RoutingStrategy.priority,
            capability=ModelCapability.chat,
            targets=[{"provider": "anthropic", "model": "claude-3-5-haiku-20241022", "weight": 1}],
            priority=200,
        )
    )
    db_session.add(
        RoutingRule(
            model_alias="gateway-fast",
            project_id=api_key.project_id,
            user_id="vip-customer-001",
            strategy=RoutingStrategy.priority,
            capability=ModelCapability.chat,
            targets=[{"provider": "anthropic", "model": "claude-3-5-sonnet-20241022", "weight": 1}],
            priority=300,
        )
    )
    await db_session.commit()

    match_for_vip = await repo.find_best_match(
        "gateway-fast", ModelCapability.chat, api_key.project_id, user_id="vip-customer-001"
    )
    match_for_others = await repo.find_best_match("gateway-fast", ModelCapability.chat, api_key.project_id)

    assert match_for_vip.targets[0]["model"] == "claude-3-5-sonnet-20241022"
    assert match_for_others.targets[0]["model"] == "claude-3-5-haiku-20241022"


@pytest.mark.asyncio
async def test_capability_never_cross_resolves(db_session: AsyncSession, seeded_api_key) -> None:
    api_key, _ = seeded_api_key
    repo = RoutingRuleRepo(db_session)

    db_session.add(
        RoutingRule(
            model_alias="gateway-embed",
            project_id=None,
            strategy=RoutingStrategy.priority,
            capability=ModelCapability.embedding,
            targets=[{"provider": "openai", "model": "text-embedding-3-small"}],
            priority=100,
        )
    )
    await db_session.commit()

    chat_match = await repo.find_best_match("gateway-embed", ModelCapability.chat, api_key.project_id)
    embedding_match = await repo.find_best_match("gateway-embed", ModelCapability.embedding, api_key.project_id)

    assert chat_match is None
    assert embedding_match is not None


@pytest.mark.asyncio
async def test_latency_p50_computed_from_recent_successful_requests(db_session: AsyncSession) -> None:
    org, project = await _make_org_and_project(db_session)

    for latency in [100, 200, 300, 400, 500]:
        db_session.add(
            RequestLog(
                request_id=uuid.uuid4(),
                project_id=project.id,
                organization_id=org.id,
                model_alias="gateway-realtime",
                resolved_provider="openai",
                resolved_model="gpt-4o-mini",
                status=RequestStatus.success,
                latency_ms=latency,
                prompt_tokens=10,
                completion_tokens=10,
            )
        )
    # a failed request with a huge latency must NOT skew the p50 -- only successes count
    db_session.add(
        RequestLog(
            request_id=uuid.uuid4(),
            project_id=project.id,
            organization_id=org.id,
            model_alias="gateway-realtime",
            resolved_provider="openai",
            resolved_model="gpt-4o-mini",
            status=RequestStatus.error,
            latency_ms=99999,
            prompt_tokens=0,
            completion_tokens=0,
        )
    )
    await db_session.commit()

    repo = RequestLogRepo(db_session)
    p50 = await repo.get_latency_p50_ms("openai", "gpt-4o-mini")

    assert p50 == 300.0


@pytest.mark.asyncio
async def test_latency_p50_none_when_insufficient_samples(db_session: AsyncSession) -> None:
    org, project = await _make_org_and_project(db_session)

    db_session.add(
        RequestLog(
            request_id=uuid.uuid4(),
            project_id=project.id,
            organization_id=org.id,
            model_alias="gateway-realtime",
            resolved_provider="anthropic",
            resolved_model="claude-3-5-haiku-20241022",
            status=RequestStatus.success,
            latency_ms=250,
            prompt_tokens=10,
            completion_tokens=10,
        )
    )
    await db_session.commit()

    repo = RequestLogRepo(db_session)
    # only 1 sample; default min_samples=3 means this is treated as cold-start, not real data
    p50 = await repo.get_latency_p50_ms("anthropic", "claude-3-5-haiku-20241022")

    assert p50 is None
