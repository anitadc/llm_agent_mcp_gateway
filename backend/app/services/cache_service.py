import hashlib
import json
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings
from app.db.valkey import valkey_client


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
        raw = await self.client.get(key)
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: dict[str, Any]) -> None:
        await self.client.set(key, json.dumps(value, default=str), ex=self.ttl_seconds)
