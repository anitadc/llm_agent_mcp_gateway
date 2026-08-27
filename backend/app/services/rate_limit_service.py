import time

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.exceptions import RateLimitError
from app.db.valkey import valkey_client

_INCR_AND_EXPIRE = """
local current = redis.call('INCR', KEYS[1])
if tonumber(current) == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
return current
"""

DEFAULT_REQUESTS_PER_WINDOW = 60


class RateLimitService:
    def __init__(self, client: redis.Redis | None = None, window_seconds: int | None = None) -> None:
        self.client = client or valkey_client
        self.window_seconds = window_seconds if window_seconds is not None else get_settings().rate_limit_window_seconds
        self._script = self.client.register_script(_INCR_AND_EXPIRE)

    async def check(self, key_id: str, limit_per_window: int = DEFAULT_REQUESTS_PER_WINDOW) -> None:
        window_start = int(time.time() // self.window_seconds)
        redis_key = f"ratelimit:{key_id}:{window_start}"
        count = await self._script(keys=[redis_key], args=[self.window_seconds * 1000])
        if int(count) > limit_per_window:
            raise RateLimitError("Too many requests")
