from app.core.logging import get_logger
import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()

if settings.valkey_url:
    connection_url = settings.valkey_url
else:
    auth_part = ""
    if settings.valkey_user and settings.valkey_password:
        auth_part = f"{settings.valkey_user}:{settings.valkey_password}@"
    elif settings.valkey_user:
        auth_part = f"{settings.valkey_user}@"
    elif settings.valkey_password:
        auth_part = f":{settings.valkey_password}@"

    connection_url = f"redis://{auth_part}{settings.valkey_host}:{settings.valkey_port}/{settings.valkey_db}"

logger = get_logger(__name__)
logger.info(f"Connecting to Valkey Redis at {connection_url}")
valkey_client: redis.Redis = redis.from_url(connection_url, decode_responses=True)


async def get_valkey() -> redis.Redis:
    return valkey_client
