import time
from collections.abc import Iterable
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.api.deps import (
    get_cache_service,
    get_cost_service,
    get_current_api_key,
    get_gateway_router,
    get_guardrails_client,
    get_project_repo,
)
from app.core.exceptions import GuardrailBlockedError, NotFoundError
from app.core.logging import get_logger, log_method
from app.db.models.api_key import ApiKey
from app.db.models.enums import GuardrailDirection, ModelCapability, RequestStatus
from app.repositories.project_repo import ProjectRepo
from app.schemas.chat import GatewayMetadata
from app.schemas.embedding import EmbeddingData, EmbeddingRequest, EmbeddingResponse, EmbeddingUsage
from app.services.cache_service import CacheService
from app.services.cost_service import CostService
from app.services.guardrails.base import GuardrailsClient, GuardrailVerdict
from app.services.logging_service import record_request
from app.services.routing.router import GatewayRouter

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["embeddings"])


@router.post("/embeddings", response_model=EmbeddingResponse)
@log_method(logger)
async def create_embedding(
    body: EmbeddingRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    api_key: ApiKey = Depends(get_current_api_key),
    gateway_router: GatewayRouter = Depends(get_gateway_router),
    guardrails: GuardrailsClient = Depends(get_guardrails_client),
    cache: CacheService = Depends(get_cache_service),
    project_repo: ProjectRepo = Depends(get_project_repo),
    cost_service: CostService = Depends(get_cost_service),
) -> EmbeddingResponse:
    request_id = request.state.request_id
    start = time.perf_counter()
    logger.info("embedding request received", request_id=request_id, model=body.model, api_key_id=api_key.id, project_id=str(api_key.project_id))

    project = await project_repo.get(api_key.project_id)
    if project is None:
        raise NotFoundError("Project not found for this API key")

    context = {"project_id": str(api_key.project_id), "request_id": str(request_id)}
    inputs = body.input if isinstance(body.input, list) else [body.input]

    def log(
        *,
        status: RequestStatus,
        resolved_provider: str | None = None,
        resolved_model: str | None = None,
        prompt_tokens: int = 0,
        cache_hit: bool = False,
        cost_usd: Decimal | None = None,
        guardrail_verdicts: Iterable[tuple[GuardrailDirection, GuardrailVerdict]] = (),
    ) -> None:
        background_tasks.add_task(
            record_request,
            request_id=request_id,
            api_key_id=api_key.id,
            user_id=None,
            project_id=project.id,
            organization_id=project.organization_id,
            model_alias=body.model,
            capability=ModelCapability.embedding,
            resolved_provider=resolved_provider,
            resolved_model=resolved_model,
            status=status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            cache_hit=cache_hit,
            cost_usd=cost_usd,
            guardrail_verdicts=list(guardrail_verdicts),
        )

    prompt_text = "\n".join(inputs)
    prompt_verdict = await guardrails.check_prompt(prompt_text, context)
    if not prompt_verdict.allowed:
        log(status=RequestStatus.blocked, guardrail_verdicts=[(GuardrailDirection.prompt, prompt_verdict)])
        logger.warning("guardrail_blocked", request_id=str(request_id), direction="prompt", model=body.model)
        raise GuardrailBlockedError("Input violates policy")
    # No response-side guardrail check here: an embedding is a vector, not text (TDD.md §3.3/§6.4).

    cache_key = CacheService.build_key(body.model, {"input": inputs})
    cached = await cache.get(cache_key)
    if cached:
        cached_metadata = cached["gateway_metadata"]
        log(
            status=RequestStatus.success,
            resolved_provider=cached_metadata["resolved_provider"],
            resolved_model=cached_metadata["resolved_model"],
            prompt_tokens=cached["usage"]["prompt_tokens"],
            cache_hit=True,
            cost_usd=Decimal("0"),
            guardrail_verdicts=[(GuardrailDirection.prompt, prompt_verdict)],
        )
        cached_metadata["request_id"] = str(request_id)
        cached_metadata["cache_hit"] = True
        return EmbeddingResponse.model_validate(cached)

    provider_response = await gateway_router.embed(
        model_alias=body.model, input=inputs, project_id=api_key.project_id, user_id=body.user
    )
    raw = provider_response.raw
    usage = raw.usage

    cost = await cost_service.calculate(
        usage.prompt_tokens, 0, provider_response.resolved_provider, provider_response.resolved_model
    )

    result = EmbeddingResponse(
        model=body.model,
        data=[
            EmbeddingData(index=i, embedding=item["embedding"] if isinstance(item, dict) else item.embedding)
            for i, item in enumerate(raw.data)
        ],
        usage=EmbeddingUsage(prompt_tokens=usage.prompt_tokens, total_tokens=usage.total_tokens),
        gateway_metadata=GatewayMetadata(
            request_id=request_id,
            resolved_provider=provider_response.resolved_provider,
            resolved_model=provider_response.resolved_model,
            cache_hit=False,
            cost_usd=float(cost),
        ),
    )

    await cache.set(cache_key, result.model_dump(mode="json"))
    log(
        status=RequestStatus.success,
        resolved_provider=provider_response.resolved_provider,
        resolved_model=provider_response.resolved_model,
        prompt_tokens=usage.prompt_tokens,
        cache_hit=False,
        cost_usd=cost,
        guardrail_verdicts=[(GuardrailDirection.prompt, prompt_verdict)],
    )
    logger.info(
        "embedding_completed",
        request_id=str(request_id),
        resolved_provider=provider_response.resolved_provider,
        resolved_model=provider_response.resolved_model,
        cache_hit=False,
        prompt_tokens=usage.prompt_tokens,
        latency_ms=int((time.perf_counter() - start) * 1000),
    )
    return result
