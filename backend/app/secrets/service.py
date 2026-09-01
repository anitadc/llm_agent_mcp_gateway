import redis.asyncio as redis

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.valkey import valkey_client
from app.secrets.base import SecretProvider

logger = get_logger(__name__)


class SecretService:
    """Adds a short-lived Redis/Valkey cache in front of a SecretProvider, so the
    hot LLM-routing path doesn't make an outbound call to Postgres/Infisical/AWS/GCP/Azure/
    Vault on every single request -- only on a cache miss (first use, or after the
    TTL/an explicit rotation expires it).

    Security note: this caches the secret VALUE itself, in Redis, for up to
    `secret_cache_ttl_seconds` (default 300s). That's a deliberate, bounded-risk
    performance tradeoff -- the alternative is an external network round trip to
    the secret backend on every LLM call -- not an oversight; see
    docs/secret-management.md's "Security Model" section for the full reasoning
    and how to run with a stricter (in-process-only, no Redis) cache instead.

    This class never logs a secret value and never writes one to Postgres --
    only cache keys/metadata (never values) and audit *metadata* (never values)
    exist outside of Redis's short-lived cache and the provider's own store.
    """

    def __init__(self, provider: SecretProvider, provider_name: str, settings: Settings, client: redis.Redis | None = None) -> None:
        self.provider = provider
        self.provider_name = provider_name
        self.cache_ttl_seconds = settings.secret_cache_ttl_seconds
        self.client = client or valkey_client

    @staticmethod
    def _cache_key(secret_name: str, tenant: str | None) -> str:
        return f"secret:{tenant or 'default'}:{secret_name}"

    async def _cache_get(self, cache_key: str) -> str | None:
        """A Valkey/Redis outage degrades to a cache-miss rather than failing the
        caller -- the cache is a latency optimization in front of the real secret
        provider, not the source of truth."""
        try:
            return await self.client.get(cache_key)
        except redis.exceptions.RedisError as exc:
            logger.warning("secret_cache_unavailable", operation="get", error=str(exc))
            return None

    async def _cache_write(self, cache_key: str, value: str | None) -> None:
        """Best-effort: a failed cache write/invalidation must not fail the
        surrounding secret operation, since the provider call has already
        succeeded (or is a read) by the time this runs -- it only risks a stale
        cached value for up to `cache_ttl_seconds`, an already-accepted tradeoff
        (see class docstring)."""
        try:
            if value is None:
                await self.client.delete(cache_key)
            else:
                await self.client.set(cache_key, value, ex=self.cache_ttl_seconds)
        except redis.exceptions.RedisError as exc:
            logger.warning("secret_cache_unavailable", operation="delete" if value is None else "set", error=str(exc))

    async def get_secret(self, secret_name: str, tenant: str | None = None, force_refresh: bool = False) -> str | None:
        cache_key = self._cache_key(secret_name, tenant)
        if not force_refresh:
            cached = await self._cache_get(cache_key)
            if cached is not None:
                return cached

        value = await self.provider.get_secret(secret_name, tenant=tenant)
        await self._cache_write(cache_key, value)
        return value

    async def set_secret(self, secret_name: str, value: str, tenant: str | None = None) -> None:
        await self.provider.set_secret(secret_name, value, tenant=tenant)
        # Invalidate rather than pre-warm: the next get_secret re-reads from the
        # provider, so a set immediately followed by a get can never observe a
        # stale cached value from before the write.
        await self._cache_write(self._cache_key(secret_name, tenant), None)

    async def delete_secret(self, secret_name: str, tenant: str | None = None) -> None:
        await self.provider.delete_secret(secret_name, tenant=tenant)
        await self._cache_write(self._cache_key(secret_name, tenant), None)

    async def invalidate(self, secret_name: str, tenant: str | None = None) -> None:
        await self._cache_write(self._cache_key(secret_name, tenant), None)
