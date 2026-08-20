import pytest

from app.core.config import Settings
from app.services.routing.model_registry import _litellm_params_for, build_router


def _settings(**overrides) -> Settings:
    defaults = dict(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        valkey_url="redis://localhost:6379/1",
        keycloak_base_url="http://localhost:8080",
        keycloak_realm="gateway",
        keycloak_client_id="gateway-frontend",
        keycloak_audience="gateway-backend",
        guardrails_base_url="http://localhost:9000",
        api_key_secret_pepper="pepper",
        aws_region_name="us-east-1",
    )
    defaults.update(overrides)
    return Settings(**defaults)


class _StubSecretService:
    """Fakes SecretService without touching Redis or a real provider -- these
    tests are about whether model_registry asks the secret layer for
    credentials at all, not about caching behavior (that's SecretService's own
    responsibility, exercised elsewhere)."""

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.requested: list[str] = []

    async def get_secret(self, secret_name: str, tenant: str | None = None, force_refresh: bool = False) -> str | None:
        self.requested.append(secret_name)
        return self.values.get(secret_name)


@pytest.mark.asyncio
async def test_openai_params_resolve_api_key_via_secret_service() -> None:
    secret_service = _StubSecretService({"OPENAI_API_KEY": "sk-resolved-via-secret-layer"})

    params = await _litellm_params_for("openai", "gpt-4o-mini", _settings(), secret_service)

    # model is prefixed provider/model -- LiteLLM can't reliably auto-detect the
    # provider from a bare model name for every provider (see build_router test).
    assert params == {"model": "openai/gpt-4o-mini", "api_key": "sk-resolved-via-secret-layer"}
    assert secret_service.requested == ["OPENAI_API_KEY"]


@pytest.mark.asyncio
async def test_anthropic_params_resolve_api_key_via_secret_service() -> None:
    secret_service = _StubSecretService({"ANTHROPIC_API_KEY": "anthropic-key"})

    params = await _litellm_params_for("anthropic", "claude-3-5-sonnet-20241022", _settings(), secret_service)

    assert params["model"] == "anthropic/claude-3-5-sonnet-20241022"
    assert params["api_key"] == "anthropic-key"
    assert secret_service.requested == ["ANTHROPIC_API_KEY"]


@pytest.mark.asyncio
async def test_bedrock_params_resolve_both_aws_credentials_and_keep_static_region() -> None:
    secret_service = _StubSecretService({"AWS_ACCESS_KEY_ID": "AKIA...", "AWS_SECRET_ACCESS_KEY": "secret-key"})

    params = await _litellm_params_for(
        "bedrock", "anthropic.claude-3-haiku-20240307-v1:0", _settings(aws_region_name="eu-west-1"), secret_service
    )

    assert params["model"] == "bedrock/anthropic.claude-3-haiku-20240307-v1:0"
    assert params["aws_access_key_id"] == "AKIA..."
    assert params["aws_secret_access_key"] == "secret-key"
    assert params["aws_region_name"] == "eu-west-1"
    assert set(secret_service.requested) == {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}


@pytest.mark.asyncio
async def test_no_secret_lookup_or_prefix_for_unknown_provider() -> None:
    secret_service = _StubSecretService({})

    params = await _litellm_params_for("some-future-provider", "some-model", _settings(), secret_service)

    assert params == {"model": "some-model"}
    assert secret_service.requested == []


@pytest.mark.asyncio
async def test_build_router_resolves_credentials_for_every_target() -> None:
    """Also guards against the LiteLLM "LLM Provider NOT provided" failure a bare,
    non-prefixed Anthropic model name triggers -- this test constructs a real
    litellm.Router, so it would fail loudly if the provider/model prefixing in
    _litellm_params_for regressed."""
    secret_service = _StubSecretService({"OPENAI_API_KEY": "sk-a", "ANTHROPIC_API_KEY": "sk-b"})
    targets = [
        {"provider": "openai", "model": "gpt-4o-mini", "weight": 1},
        {"provider": "anthropic", "model": "claude-3-5-haiku-20241022", "weight": 2},
    ]

    router = await build_router("gateway-fast", targets, _settings(), secret_service)

    model_list = router.model_list
    assert len(model_list) == 2
    api_keys = {entry["litellm_params"]["api_key"] for entry in model_list}
    assert api_keys == {"sk-a", "sk-b"}
    assert set(secret_service.requested) == {"OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
