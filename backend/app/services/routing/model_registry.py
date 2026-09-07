from typing import Any

import litellm

from app.core.config import Settings
from app.core.logging import get_logger, log_method
from app.secrets.service import SecretService

logger = get_logger(__name__)

# Which secret name(s) each provider needs, and which litellm_params key each
# resolved value fills in. Region is NOT a secret (see Settings.aws_region_name)
# so it's the only thing here that still comes from static config.
_SECRET_NAMES_FOR_PROVIDER: dict[str, dict[str, str]] = {
    "openai": {"api_key": "OPENAI_API_KEY"},
    "anthropic": {"api_key": "ANTHROPIC_API_KEY"},
    "bedrock": {"aws_access_key_id": "AWS_ACCESS_KEY_ID", "aws_secret_access_key": "AWS_SECRET_ACCESS_KEY"},
}


@log_method(logger)
async def _litellm_params_for(
    provider: str, model: str, settings: Settings, secret_service: SecretService
) -> dict[str, Any]:
    """Resolves this target's credentials through the pluggable Secret Provider
    layer (app/secrets/) at call time -- never from a static env var baked into
    Settings. See docs/secret-management.md.

    The model string is prefixed `provider/model` (e.g. "anthropic/claude-3-5-
    haiku-20241022") because LiteLLM can only auto-detect a bare model name's
    provider for a handful of well-known naming patterns (e.g. "gpt-*"); a bare
    Anthropic model name like "claude-3-5-haiku-20241022" raises
    BadRequestError("LLM Provider NOT provided") without it.
    """
    secret_names = _SECRET_NAMES_FOR_PROVIDER.get(provider)
    params: dict[str, Any] = {"model": f"{provider}/{model}" if secret_names is not None else model}
    for litellm_key, secret_name in (secret_names or {}).items():
        params[litellm_key] = await secret_service.get_secret(secret_name)
    if provider == "bedrock":
        params["aws_region_name"] = settings.aws_region_name
    return params


@log_method(logger)
async def build_router(
    model_alias: str, targets: list[dict[str, Any]], settings: Settings, secret_service: SecretService
) -> litellm.Router:
    model_list = []
    for target in targets:
        litellm_params = await _litellm_params_for(target["provider"], target["model"], settings, secret_service)
        model_list.append({"model_name": model_alias, "litellm_params": litellm_params})
    logger.info(
        "router_built",
        model_alias=model_alias,
        providers=[target["provider"] for target in targets],
    )
    return litellm.Router(model_list=model_list, routing_strategy="simple-shuffle", num_retries=1)
