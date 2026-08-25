from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.db.models.secret import Secret
from app.db.session import async_session_factory
from app.secrets.base import SecretProvider

logger = get_logger(__name__)


class PostgresSecretProvider(SecretProvider):
    """Stores secret values directly in this app's own Postgres database,
    encrypted at rest with Fernet (SECRET_STORAGE_ENCRYPTION_KEY) -- the
    zero-external-dependency option for a deployment that doesn't want to run a
    separate secret manager. Security tradeoff: the encryption key itself lives
    in this app's own config/env, so anyone with access to both the database and
    that config can decrypt every stored secret -- a dedicated secrets manager
    (Vault, AWS/GCP/Azure) keeps the encryption key and the ciphertext in
    separate systems, which this backend does not. Choose this only when that
    tradeoff is acceptable for the deployment.

    Opens its own short-lived session per call via `async_session_factory`
    rather than participating in the current request's session/transaction --
    the same pattern CacheService/RateLimitService use for their own storage
    backends, and it lets a secret read/write commit independently of whatever
    else the request is doing.
    """

    def __init__(self, settings: Settings, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        if not settings.secret_storage_encryption_key:
            raise ProviderError("Postgres secret storage is not configured: missing SECRET_STORAGE_ENCRYPTION_KEY")
        from cryptography.fernet import Fernet, InvalidToken

        self._invalid_token = InvalidToken
        try:
            self._fernet = Fernet(settings.secret_storage_encryption_key.encode())
        except ValueError as exc:
            raise ProviderError(f"SECRET_STORAGE_ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc
        self._session_factory = session_factory or async_session_factory

    @staticmethod
    def _tenant_key(tenant: str | None) -> str:
        return tenant or ""

    async def get_secret(self, secret_name: str, tenant: str | None = None) -> str | None:
        try:
            async with self._session_factory() as session:
                row = await session.scalar(
                    select(Secret).where(Secret.tenant == self._tenant_key(tenant), Secret.secret_name == secret_name)
                )
        except SQLAlchemyError as exc:
            logger.exception("postgres_secrets_get_failed", secret_name=secret_name, tenant=tenant)
            raise ProviderError(f"Postgres secret storage get_secret failed: {exc}") from exc
        if row is None:
            return None
        try:
            return self._fernet.decrypt(row.encrypted_value.encode()).decode()
        except self._invalid_token as exc:
            logger.exception("postgres_secrets_decrypt_failed", secret_name=secret_name, tenant=tenant)
            raise ProviderError(f"Postgres secret storage failed to decrypt secret '{secret_name}': {exc}") from exc

    async def set_secret(self, secret_name: str, value: str, tenant: str | None = None) -> None:
        ciphertext = self._fernet.encrypt(value.encode()).decode()
        tenant_key = self._tenant_key(tenant)
        stmt = pg_insert(Secret).values(tenant=tenant_key, secret_name=secret_name, encrypted_value=ciphertext)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Secret.tenant, Secret.secret_name],
            set_={"encrypted_value": stmt.excluded.encrypted_value, "updated_at": func.now()},
        )
        try:
            async with self._session_factory() as session:
                await session.execute(stmt)
                await session.commit()
        except SQLAlchemyError as exc:
            logger.exception("postgres_secrets_set_failed", secret_name=secret_name, tenant=tenant)
            raise ProviderError(f"Postgres secret storage set_secret failed: {exc}") from exc

    async def delete_secret(self, secret_name: str, tenant: str | None = None) -> None:
        tenant_key = self._tenant_key(tenant)
        try:
            async with self._session_factory() as session:
                row = await session.scalar(
                    select(Secret).where(Secret.tenant == tenant_key, Secret.secret_name == secret_name)
                )
                if row is not None:
                    await session.delete(row)
                    await session.commit()
        except SQLAlchemyError as exc:
            logger.exception("postgres_secrets_delete_failed", secret_name=secret_name, tenant=tenant)
            raise ProviderError(f"Postgres secret storage delete_secret failed: {exc}") from exc
