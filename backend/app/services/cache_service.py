import hashlib
import json
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.valkey import valkey_client

logger = get_logger(__name__)


class CacheService:
    def __init__(self, client: redis.Redis | None = None, ttl_seconds: int | None = None) -> None:
        self.client = client or valkey_client
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else get_settings().cache_ttl_seconds

    @staticmethod
    def build_key(model_alias: str, payload: dict[str, Any]) -> str:
        normalized = json.dumps(payload, sort_keys=True, default=str)
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        return f"cache:{model_alias}:{digest}"

    async def get(self, key: str) -> dict[str, Any] | None:
        """A Valkey/Redis outage degrades to a cache-miss (returns None) rather than
        failing the caller -- the cache is a performance optimization, not a source
        of truth, so callers should fall through to their own lookup."""
        try:
            raw = await self.client.get(key)
        except redis.exceptions.RedisError as exc:
            logger.warning("cache_backend_unavailable", operation="get", error=str(exc))
            return None
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: dict[str, Any]) -> None:
        try:
            await self.client.set(key, json.dumps(value, default=str), ex=self.ttl_seconds)
        except redis.exceptions.RedisError as exc:
            logger.warning("cache_backend_unavailable", operation="set", error=str(exc))

    async def get_raw(self, key: str) -> str | None:
        """Same degrade-to-miss behavior as `get`, for callers storing plain string
        values (e.g. an id) rather than a JSON payload."""
        try:
            return await self.client.get(key)
        except redis.exceptions.RedisError as exc:
            logger.warning("cache_backend_unavailable", operation="get_raw", error=str(exc))
            return None

    async def set_raw(self, key: str, value: str) -> None:
        try:
            await self.client.set(key, value, ex=self.ttl_seconds)
        except redis.exceptions.RedisError as exc:
            logger.warning("cache_backend_unavailable", operation="set_raw", error=str(exc))

    async def delete(self, key: str) -> None:
        try:
            await self.client.delete(key)
        except redis.exceptions.RedisError as exc:
            logger.warning("cache_backend_unavailable", operation="delete", error=str(exc))
