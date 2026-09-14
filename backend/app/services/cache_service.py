import hashlib
import json
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.logging import get_logger, log_method
from app.db.valkey import ValkeyUtil

logger = get_logger(__name__)


class CacheService:
    def __init__(self, client: redis.Redis | None = None, ttl_seconds: int | None = None) -> None:
        self.client = client #or asyncio.get_event_loop().run_until_complete(ValkeyUtil.get_valkey())
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else get_settings().cache_ttl_seconds

    @staticmethod
    @log_method(logger)
    def build_key(model_alias: str, payload: dict[str, Any]) -> str:
        normalized = json.dumps(payload, sort_keys=True, default=str)
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        return f"cache:{model_alias}:{digest}"

    @log_method(logger)
    async def get(self, key: str) -> dict[str, Any] | None:
        """A Valkey/Redis outage degrades to a cache-miss (returns None) rather than
        failing the caller -- the cache is a performance optimization, not a source
        of truth, so callers should fall through to their own lookup."""
        try:
            if self.client is None:
                self.client = await ValkeyUtil.get_valkey()
            raw = await self.client.get(key)
        except redis.exceptions.RedisError as exc:
            logger.warning("cache_backend_unavailable", operation="get", error=str(exc))
            return None
        return json.loads(raw) if raw else None

    @log_method(logger)
    async def set(self, key: str, value: dict[str, Any]) -> None:
        try:
            if self.client is None:
                self.client = await ValkeyUtil.get_valkey()
            await self.client.set(key, json.dumps(value, default=str), ex=self.ttl_seconds)
        except redis.exceptions.RedisError as exc:
            logger.warning("cache_backend_unavailable", operation="set", error=str(exc))

    @log_method(logger)
    async def get_raw(self, key: str) -> str | None:
        """Same degrade-to-miss behavior as `get`, for callers storing plain string
        values (e.g. an id) rather than a JSON payload."""
        try:
            if self.client is None:
                self.client = await ValkeyUtil.get_valkey()
            return await self.client.get(key)
        except redis.exceptions.RedisError as exc:
            logger.warning("cache_backend_unavailable", operation="get_raw", error=str(exc))
            return None

    @log_method(logger)
    async def set_raw(self, key: str, value: str) -> None:
        try:
            if self.client is None:
                self.client = await ValkeyUtil.get_valkey()
            await self.client.set(key, value, ex=self.ttl_seconds)
        except redis.exceptions.RedisError as exc:
            logger.warning("cache_backend_unavailable", operation="set_raw", error=str(exc))

    @log_method(logger)
    async def delete(self, key: str) -> None:
        try:
            if self.client is None:
                self.client = await ValkeyUtil.get_valkey()
            await self.client.delete(key)
        except redis.exceptions.RedisError as exc:
            logger.warning("cache_backend_unavailable", operation="delete", error=str(exc))
