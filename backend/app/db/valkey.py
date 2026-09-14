from app.core.logging import get_logger
import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()

logger = get_logger(__name__)

class ValkeyUtil:
    __valkey_client: redis.Redis | object = None

    @staticmethod
    async def get_valkey() -> redis.Redis | object:
        if ValkeyUtil.__valkey_client is not None:
            return ValkeyUtil.__valkey_client
        
        if not settings.valkey_enabled:
            logger.info("Valkey/Redis disabled by configuration (VALKEY_ENABLED=false)")
            valkey_client = ValkeyUtil._make_disabled_client()
        else:
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

            logger.info(f"Connecting to Valkey Redis at {connection_url}")
            valkey_client = redis.Redis.from_url(
                connection_url,
                decode_responses=True,
                socket_keepalive=True,
            )

        ValkeyUtil.__valkey_client = valkey_client

        return valkey_client

    @staticmethod
    def _make_disabled_client() -> object:
        class _DisabledValkey:
            async def get(self, *args, **kwargs):
                return None
                # raise redis.exceptions.RedisError("valkey disabled")

            async def set(self, *args, **kwargs):
                return None
                # raise redis.exceptions.RedisError("valkey disabled")

            async def delete(self, *args, **kwargs):
                return None
                # raise redis.exceptions.RedisError("valkey disabled")

            async def ping(self):
                return None
                # raise redis.exceptions.RedisError("valkey disabled")

            register_script = lambda self, *args, **kwargs: lambda *a, **k: None

        return _DisabledValkey()