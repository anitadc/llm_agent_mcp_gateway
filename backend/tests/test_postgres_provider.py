import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.db.base import Base
from app.db.models.secret import Secret
from app.secrets.postgres_provider import PostgresSecretProvider

# A syntactically valid (though not secret) Fernet key -- good enough for tests,
# never used against a real deployment.
_TEST_FERNET_KEY = "ZkcyJKfplZZRbdiUXnsC15rHoufpJvBoThi14IV8tiQ="


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
        secret_storage_encryption_key=_TEST_FERNET_KEY,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest_asyncio.fixture
async def session_factory(postgres_container: PostgresContainer):
    """PostgresSecretProvider opens its own sessions rather than sharing the
    request's, so tests hand it a sessionmaker (not a single session) bound to
    the same test container the rest of the suite uses."""
    url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_set_then_get_roundtrips_the_value(session_factory) -> None:
    provider = PostgresSecretProvider(_settings(), session_factory=session_factory)

    await provider.set_secret("OPENAI_API_KEY", "sk-test-123")
    value = await provider.get_secret("OPENAI_API_KEY")

    assert value == "sk-test-123"


@pytest.mark.asyncio
async def test_get_returns_none_when_not_found(session_factory) -> None:
    provider = PostgresSecretProvider(_settings(), session_factory=session_factory)

    assert await provider.get_secret("MISSING_KEY") is None


@pytest.mark.asyncio
async def test_set_secret_upserts_an_existing_value(session_factory) -> None:
    provider = PostgresSecretProvider(_settings(), session_factory=session_factory)

    await provider.set_secret("OPENAI_API_KEY", "sk-old")
    await provider.set_secret("OPENAI_API_KEY", "sk-new")

    assert await provider.get_secret("OPENAI_API_KEY") == "sk-new"


@pytest.mark.asyncio
async def test_tenant_scopes_secrets_independently(session_factory) -> None:
    provider = PostgresSecretProvider(_settings(), session_factory=session_factory)

    await provider.set_secret("OPENAI_API_KEY", "sk-tenant-a", tenant="tenant-a")
    await provider.set_secret("OPENAI_API_KEY", "sk-tenant-b", tenant="tenant-b")

    assert await provider.get_secret("OPENAI_API_KEY", tenant="tenant-a") == "sk-tenant-a"
    assert await provider.get_secret("OPENAI_API_KEY", tenant="tenant-b") == "sk-tenant-b"
    assert await provider.get_secret("OPENAI_API_KEY") is None


@pytest.mark.asyncio
async def test_values_are_encrypted_at_rest(session_factory) -> None:
    provider = PostgresSecretProvider(_settings(), session_factory=session_factory)
    await provider.set_secret("OPENAI_API_KEY", "sk-plaintext-marker")

    async with session_factory() as session:
        row = await session.scalar(select(Secret).where(Secret.secret_name == "OPENAI_API_KEY"))

    assert row is not None
    assert "sk-plaintext-marker" not in row.encrypted_value


@pytest.mark.asyncio
async def test_delete_secret_removes_the_row(session_factory) -> None:
    provider = PostgresSecretProvider(_settings(), session_factory=session_factory)
    await provider.set_secret("OPENAI_API_KEY", "sk-test")

    await provider.delete_secret("OPENAI_API_KEY")

    assert await provider.get_secret("OPENAI_API_KEY") is None


@pytest.mark.asyncio
async def test_delete_missing_secret_is_a_no_op(session_factory) -> None:
    provider = PostgresSecretProvider(_settings(), session_factory=session_factory)

    await provider.delete_secret("DOES_NOT_EXIST")  # must not raise


def test_missing_encryption_key_raises_provider_error() -> None:
    with pytest.raises(ProviderError):
        PostgresSecretProvider(_settings(secret_storage_encryption_key=None))


def test_malformed_encryption_key_raises_provider_error() -> None:
    with pytest.raises(ProviderError):
        PostgresSecretProvider(_settings(secret_storage_encryption_key="not-a-valid-fernet-key"))
