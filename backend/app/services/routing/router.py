import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import openai

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger, log_method
from app.db.models.enums import ModelCapability, RoutingStrategy
from app.db.models.routing_rule import RoutingRule
from app.repositories.model_pricing_repo import ModelPricingRepo
from app.repositories.request_log_repo import RequestLogRepo
from app.repositories.routing_rule_repo import RoutingRuleRepo
from app.secrets.service import SecretService
from app.services.routing.model_registry import build_router

logger = get_logger(__name__)

# Targets with no (or too little) recent latency data sort after every target that
# has real data, rather than winning by default -- same "unknown = worst" convention
# the cost strategy uses for models missing from model_pricing.
_UNKNOWN_LATENCY_MS = float("inf")


@dataclass
class RouteTarget:
    provider: str
    model: str
    weight: int | None = None


@dataclass
class ProviderResponse:
    raw: Any
    resolved_provider: str | None
    resolved_model: str | None


class GatewayRouter:
    def __init__(
        self,
        rules_repo: RoutingRuleRepo,
        pricing_repo: ModelPricingRepo,
        request_log_repo: RequestLogRepo,
        settings: Settings,
        secret_service: SecretService,
    ) -> None:
        self.rules_repo = rules_repo
        self.pricing_repo = pricing_repo
        self.request_log_repo = request_log_repo
        self.settings = settings
        self.secret_service = secret_service

    @log_method(logger)
    async def resolve(
        self,
        model_alias: str,
        project_id: uuid.UUID,
        user_id: str | None = None,
        capability: ModelCapability = ModelCapability.chat,
    ) -> tuple[RoutingRule, list[dict[str, Any]]]:
        rule = await self.rules_repo.find_best_match(model_alias, capability, project_id, user_id)
        if rule is None:
            logger.warning("no_routing_rule_matched", model_alias=model_alias, capability=capability.value)
            raise ProviderError(f"No active routing rule for alias '{model_alias}' ({capability.value})")
        return rule, await self._order_targets(rule)

    @log_method(logger)
    async def _order_targets(self, rule: RoutingRule) -> list[dict[str, Any]]:
        targets = list(rule.targets)
        if rule.strategy == RoutingStrategy.priority:
            return sorted(targets, key=lambda t: t.get("weight", 0))
        if rule.strategy == RoutingStrategy.cost:
            prices: dict[tuple[str, str], Decimal] = {}
            for target in targets:
                entry = await self.pricing_repo.get_by_provider_model(target["provider"], target["model"])
                prices[(target["provider"], target["model"])] = entry.prompt_per_1k if entry else Decimal("999999")
            return sorted(targets, key=lambda t: prices[(t["provider"], t["model"])])
        if rule.strategy == RoutingStrategy.latency:
            latencies: dict[tuple[str, str], float] = {}
            for target in targets:
                p50 = await self.request_log_repo.get_latency_p50_ms(target["provider"], target["model"])
                latencies[(target["provider"], target["model"])] = p50 if p50 is not None else _UNKNOWN_LATENCY_MS
            return sorted(targets, key=lambda t: latencies[(t["provider"], t["model"])])
        return targets

    @log_method(logger)
    async def complete(
        self,
        model_alias: str,
        messages: list[dict[str, str]],
        project_id: uuid.UUID,
        user_id: str | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        _, targets = await self.resolve(model_alias, project_id, user_id, ModelCapability.chat)
        router = await build_router(model_alias, targets, self.settings, self.secret_service)
        try:
            response = await router.acompletion(model=model_alias, messages=messages, **kwargs)
        except openai.APIError as exc:
            logger.exception(
                "provider_completion_failed",
                model_alias=model_alias,
                providers=[t["provider"] for t in targets],
            )
            raise ProviderError(str(exc)) from exc
        resolved_model = getattr(response, "model", None)
        resolved_provider = self._provider_for_model(targets, resolved_model)
        logger.info(
            "provider_completion_succeeded",
            model_alias=model_alias,
            resolved_provider=resolved_provider,
            resolved_model=resolved_model,
        )
        return ProviderResponse(response, resolved_provider, resolved_model)

    @log_method(logger)
    async def embed(
        self,
        model_alias: str,
        input: str | list[str],
        project_id: uuid.UUID,
        user_id: str | None = None,
    ) -> ProviderResponse:
        _, targets = await self.resolve(model_alias, project_id, user_id, ModelCapability.embedding)
        router = await build_router(model_alias, targets, self.settings, self.secret_service)
        try:
            response = await router.aembedding(model=model_alias, input=input)
        except openai.APIError as exc:
            logger.exception(
                "provider_embedding_failed",
                model_alias=model_alias,
                providers=[t["provider"] for t in targets],
            )
            raise ProviderError(str(exc)) from exc
        resolved_model = getattr(response, "model", None)
        resolved_provider = self._provider_for_model(targets, resolved_model)
        logger.info(
            "provider_embedding_succeeded",
            model_alias=model_alias,
            resolved_provider=resolved_provider,
            resolved_model=resolved_model,
        )
        return ProviderResponse(response, resolved_provider, resolved_model)

    @staticmethod
    @log_method(logger)
    def _provider_for_model(targets: list[dict[str, Any]], model: str | None) -> str | None:
        for target in targets:
            if target["model"] == model:
                return target["provider"]
        return targets[0]["provider"] if targets else None
