import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()

valkey_client: redis.Redis = redis.from_url(settings.valkey_url, decode_responses=True)


async def get_valkey() -> redis.Redis:
    return valkey_client
