import pytest

from app.core.config import Settings
from app.secrets.service import SecretService


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
        secret_cache_ttl_seconds=300,
    )
    defaults.update(overrides)
    return Settings(**defaults)


class _FakeRedis:
    """In-memory stand-in for the Valkey client -- just enough of the
    get/set/delete surface SecretService actually uses."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.store[key] = value
        self.set_calls.append((key, value, ex))

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


class _FakeProvider:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.get_calls = 0
        self.set_calls: list[tuple[str, str, str | None]] = []
        self.delete_calls: list[tuple[str, str | None]] = []

    async def get_secret(self, secret_name: str, tenant: str | None = None) -> str | None:
        self.get_calls += 1
        key = f"{tenant}:{secret_name}" if tenant else secret_name
        return self.values.get(key)

    async def set_secret(self, secret_name: str, value: str, tenant: str | None = None) -> None:
        self.set_calls.append((secret_name, value, tenant))

    async def delete_secret(self, secret_name: str, tenant: str | None = None) -> None:
        self.delete_calls.append((secret_name, tenant))


@pytest.mark.asyncio
async def test_cache_miss_falls_through_to_provider_and_populates_cache() -> None:
    provider = _FakeProvider({"OPENAI_API_KEY": "sk-1"})
    redis = _FakeRedis()
    service = SecretService(provider, "postgres", _settings(), client=redis)

    value = await service.get_secret("OPENAI_API_KEY")

    assert value == "sk-1"
    assert provider.get_calls == 1
    assert redis.store["secret:default:OPENAI_API_KEY"] == "sk-1"


@pytest.mark.asyncio
async def test_cache_hit_never_calls_the_provider() -> None:
    provider = _FakeProvider({"OPENAI_API_KEY": "sk-1"})
    redis = _FakeRedis()
    service = SecretService(provider, "postgres", _settings(), client=redis)

    await service.get_secret("OPENAI_API_KEY")  # warms cache
    provider.get_calls = 0  # reset counter
    value = await service.get_secret("OPENAI_API_KEY")

    assert value == "sk-1"
    assert provider.get_calls == 0


@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache_and_rewarms_it() -> None:
    provider = _FakeProvider({"OPENAI_API_KEY": "sk-rotated"})
    redis = _FakeRedis()
    redis.store["secret:default:OPENAI_API_KEY"] = "sk-stale"
    service = SecretService(provider, "postgres", _settings(), client=redis)

    value = await service.get_secret("OPENAI_API_KEY", force_refresh=True)

    assert value == "sk-rotated"
    assert provider.get_calls == 1
    assert redis.store["secret:default:OPENAI_API_KEY"] == "sk-rotated"


@pytest.mark.asyncio
async def test_tenant_scopes_the_cache_key() -> None:
    provider = _FakeProvider({"tenant-a:OPENAI_API_KEY": "sk-tenant-a"})
    redis = _FakeRedis()
    service = SecretService(provider, "postgres", _settings(), client=redis)

    value = await service.get_secret("OPENAI_API_KEY", tenant="tenant-a")

    assert value == "sk-tenant-a"
    assert "secret:tenant-a:OPENAI_API_KEY" in redis.store
    assert "secret:default:OPENAI_API_KEY" not in redis.store


@pytest.mark.asyncio
async def test_set_secret_invalidates_the_cache_instead_of_prewarming_it() -> None:
    provider = _FakeProvider({})
    redis = _FakeRedis()
    redis.store["secret:default:OPENAI_API_KEY"] = "sk-old"
    service = SecretService(provider, "postgres", _settings(), client=redis)

    await service.set_secret("OPENAI_API_KEY", "sk-new")

    assert provider.set_calls == [("OPENAI_API_KEY", "sk-new", None)]
    assert "secret:default:OPENAI_API_KEY" not in redis.store


@pytest.mark.asyncio
async def test_delete_secret_invalidates_the_cache() -> None:
    provider = _FakeProvider({})
    redis = _FakeRedis()
    redis.store["secret:default:OPENAI_API_KEY"] = "sk-old"
    service = SecretService(provider, "postgres", _settings(), client=redis)

    await service.delete_secret("OPENAI_API_KEY")

    assert provider.delete_calls == [("OPENAI_API_KEY", None)]
    assert "secret:default:OPENAI_API_KEY" not in redis.store


@pytest.mark.asyncio
async def test_missing_secret_is_not_cached() -> None:
    provider = _FakeProvider({})
    redis = _FakeRedis()
    service = SecretService(provider, "postgres", _settings(), client=redis)

    value = await service.get_secret("DOES_NOT_EXIST")

    assert value is None
    assert "secret:default:DOES_NOT_EXIST" not in redis.store
