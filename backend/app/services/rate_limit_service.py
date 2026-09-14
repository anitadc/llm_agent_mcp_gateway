import time

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.exceptions import RateLimitError
from app.core.logging import get_logger, log_method
from app.db.valkey import ValkeyUtil

logger = get_logger(__name__)

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
        self.client = client #or asyncio.get_event_loop().run_until_complete(ValkeyUtil.get_valkey())
        self.window_seconds = window_seconds if window_seconds is not None else get_settings().rate_limit_window_seconds
        # self._script = self.client.register_script(_INCR_AND_EXPIRE)

    @log_method(logger)
    async def check(self, key_id: str, limit_per_window: int = DEFAULT_REQUESTS_PER_WINDOW) -> None:
        window_start = int(time.time() // self.window_seconds)
        redis_key = f"ratelimit:{key_id}:{window_start}"
        try:
            if self.client is None:
                self.client = await ValkeyUtil.get_valkey()
            self._script = self.client.register_script(_INCR_AND_EXPIRE)
            count = await self._script(keys=[redis_key], args=[self.window_seconds * 1000]) if self._script else 0
        except redis.exceptions.RedisError:
            # Fail closed: the limiter backend being unreachable is treated as a hard
            # failure (surfaces as a 500 via the global handler), not as "no limit
            # applied" -- deliberate choice, not an accidental unhandled exception.
            logger.exception("rate_limit_backend_unavailable", key_id=key_id)
            raise
        if int(count) > limit_per_window:
            logger.warning("rate_limit_exceeded", key_id=key_id, count=int(count), limit=limit_per_window)
            raise RateLimitError("Too many requests")
