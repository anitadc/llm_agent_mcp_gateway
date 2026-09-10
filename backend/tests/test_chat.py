from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.db.models.enums import RoutingStrategy
from app.db.models.routing_rule import RoutingRule
from app.services.cost_service import CostService
from app.services.routing.router import GatewayRouter


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        valkey_url="redis://localhost:6379/1",
        keycloak_base_url="http://localhost:8080",
        keycloak_realm="tcsaigateway",
        keycloak_client_id="tcsaigateway-frontend",
        keycloak_audience="tcsaigateway-backend",
        guardrails_base_url="http://localhost:9000",
        api_key_secret_pepper="pepper",
    )


@dataclass
class _FakePricingEntry:
    prompt_per_1k: Decimal
    completion_per_1k: Decimal | None = None


class _FakePricingRepo:
    """Stands in for ModelPricingRepo in unit tests that don't have a real DB --
    mirrors the same (provider, model) -> pricing lookup shape."""

    def __init__(self, prices: dict[tuple[str, str], _FakePricingEntry]) -> None:
        self._prices = prices

    async def get_by_provider_model(self, provider: str, model: str) -> _FakePricingEntry | None:
        return self._prices.get((provider, model))


PRICES = {
    ("openai", "gpt-4o-mini"): _FakePricingEntry(Decimal("0.00015"), Decimal("0.0006")),
    ("openai", "text-embedding-3-small"): _FakePricingEntry(Decimal("0.00002")),
    ("anthropic", "claude-3-5-sonnet-20241022"): _FakePricingEntry(Decimal("0.0030"), Decimal("0.0150")),
}


class _FakeRequestLogRepo:
    """Stands in for RequestLogRepo -- mirrors the (provider, model) -> rolling p50 lookup."""

    def __init__(self, latencies: dict[tuple[str, str], float | None]) -> None:
        self._latencies = latencies

    async def get_latency_p50_ms(self, provider: str, model: str) -> float | None:
        return self._latencies.get((provider, model))


@pytest.mark.asyncio
async def test_cost_calculation_includes_completion_cost() -> None:
    service = CostService(_FakePricingRepo(PRICES))
    cost = await service.calculate(1000, 1000, "openai", "gpt-4o-mini")
    assert cost == Decimal("0.00015") + Decimal("0.0006")


@pytest.mark.asyncio
async def test_cost_calculation_is_input_only_for_embeddings() -> None:
    service = CostService(_FakePricingRepo(PRICES))
    cost = await service.calculate(1000, 0, "openai", "text-embedding-3-small")
    assert cost == Decimal("0.00002")


@pytest.mark.asyncio
async def test_cost_calculation_unknown_model_is_zero() -> None:
    service = CostService(_FakePricingRepo(PRICES))
    assert await service.calculate(1000, 1000, "openai", "not-a-real-model") == Decimal("0")


@pytest.mark.asyncio
async def test_priority_strategy_orders_by_weight() -> None:
    router = GatewayRouter(rules_repo=None, pricing_repo=None, request_log_repo=None, settings=_settings(), secret_service=None)
    rule = RoutingRule(
        model_alias="gateway-fast",
        strategy=RoutingStrategy.priority,
        targets=[
            {"provider": "anthropic", "model": "claude-3-5-haiku-20241022", "weight": 2},
            {"provider": "openai", "model": "gpt-4o-mini", "weight": 1},
        ],
    )

    ordered = await router._order_targets(rule)

    assert [t["provider"] for t in ordered] == ["openai", "anthropic"]


@pytest.mark.asyncio
async def test_cost_strategy_orders_by_cheapest_first() -> None:
    router = GatewayRouter(
        rules_repo=None,
        pricing_repo=_FakePricingRepo(PRICES),
        request_log_repo=None,
        settings=_settings(),
        secret_service=None,
    )
    rule = RoutingRule(
        model_alias="gateway-cheap",
        strategy=RoutingStrategy.cost,
        targets=[
            {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
            {"provider": "openai", "model": "gpt-4o-mini"},
        ],
    )

    ordered = await router._order_targets(rule)

    assert ordered[0]["provider"] == "openai"


@pytest.mark.asyncio
async def test_latency_strategy_orders_by_fastest_first() -> None:
    latencies = {
        ("anthropic", "claude-3-5-haiku-20241022"): 800.0,
        ("openai", "gpt-4o-mini"): 250.0,
    }
    router = GatewayRouter(
        rules_repo=None,
        pricing_repo=None,
        request_log_repo=_FakeRequestLogRepo(latencies),
        settings=_settings(),
        secret_service=None,
    )
    rule = RoutingRule(
        model_alias="gateway-realtime",
        strategy=RoutingStrategy.latency,
        targets=[
            {"provider": "anthropic", "model": "claude-3-5-haiku-20241022"},
            {"provider": "openai", "model": "gpt-4o-mini"},
        ],
    )

    ordered = await router._order_targets(rule)

    assert [t["provider"] for t in ordered] == ["openai", "anthropic"]


@pytest.mark.asyncio
async def test_latency_strategy_treats_no_data_as_worst_case() -> None:
    # Only one target has recent data; the other (cold start / never seen) should
    # sort after it rather than winning by default.
    latencies = {("openai", "gpt-4o-mini"): 500.0}
    router = GatewayRouter(
        rules_repo=None,
        pricing_repo=None,
        request_log_repo=_FakeRequestLogRepo(latencies),
        settings=_settings(),
        secret_service=None,
    )
    rule = RoutingRule(
        model_alias="gateway-realtime",
        strategy=RoutingStrategy.latency,
        targets=[
            {"provider": "bedrock", "model": "never-called-before"},
            {"provider": "openai", "model": "gpt-4o-mini"},
        ],
    )

    ordered = await router._order_targets(rule)

    assert [t["provider"] for t in ordered] == ["openai", "bedrock"]
