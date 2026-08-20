import asyncio

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.secrets.base import SecretProvider


class InfisicalProvider(SecretProvider):
    """Default secret provider. Secrets live under a single Infisical project
    (`infisical_project_id`) and environment (DEV/STAGING/PROD, `infisical_environment`);
    `tenant` maps to a secret path/folder within that project+environment, e.g.
    tenant "customer1" -> path "/customer1", so multiple tenants can share one
    Infisical project without colliding on secret names.

    Authenticates once (Universal Auth / machine identity) and reuses the access
    token for subsequent calls; the SDK is synchronous, so every call is run in a
    worker thread to avoid blocking the event loop.
    """

    def __init__(self, settings: Settings) -> None:
        from infisical_sdk import InfisicalSDKClient

        self._client = InfisicalSDKClient(host=settings.infisical_site_url)
        self._client_id = settings.infisical_client_id
        self._client_secret = settings.infisical_client_secret
        self._project_id = settings.infisical_project_id
        self._environment = settings.infisical_environment
        self._authenticated = False
        self._auth_lock = asyncio.Lock()

    async def _ensure_authenticated(self) -> None:
        if self._authenticated:
            return
        async with self._auth_lock:
            if self._authenticated:
                return
            if not self._client_id or not self._client_secret:
                raise ProviderError("Infisical is not configured: missing client id/secret")
            await asyncio.to_thread(self._client.auth.universal_auth.login, self._client_id, self._client_secret)
            self._authenticated = True

    @staticmethod
    def _secret_path(tenant: str | None) -> str:
        return f"/{tenant}" if tenant else "/"

    @staticmethod
    def _is_not_found(exc: Exception) -> bool:
        # The SDK raises a generic InfisicalError without a structured status code;
        # fall back to matching the message it surfaces from the Infisical API.
        message = str(exc).lower()
        return "404" in message or "not found" in message or "secretnotfound" in message

    async def get_secret(self, secret_name: str, tenant: str | None = None) -> str | None:
        await self._ensure_authenticated()
        try:
            result = await asyncio.to_thread(
                self._client.secrets.get_secret_by_name,
                secret_name=secret_name,
                project_id=self._project_id,
                environment_slug=self._environment,
                secret_path=self._secret_path(tenant),
            )
        except Exception as exc:
            if self._is_not_found(exc):
                return None
            raise ProviderError(f"Infisical get_secret failed: {exc}") from exc
        return result.secretValue

    async def set_secret(self, secret_name: str, value: str, tenant: str | None = None) -> None:
        await self._ensure_authenticated()
        path = self._secret_path(tenant)
        try:
            await asyncio.to_thread(
                self._client.secrets.update_secret_by_name,
                current_secret_name=secret_name,
                project_id=self._project_id,
                secret_path=path,
                environment_slug=self._environment,
                secret_value=value,
            )
        except Exception as exc:
            if not self._is_not_found(exc):
                raise ProviderError(f"Infisical set_secret failed: {exc}") from exc
            try:
                await asyncio.to_thread(
                    self._client.secrets.create_secret_by_name,
                    secret_name=secret_name,
                    project_id=self._project_id,
                    secret_path=path,
                    environment_slug=self._environment,
                    secret_value=value,
                )
            except Exception as create_exc:
                raise ProviderError(f"Infisical create_secret failed: {create_exc}") from create_exc

    async def delete_secret(self, secret_name: str, tenant: str | None = None) -> None:
        await self._ensure_authenticated()
        try:
            await asyncio.to_thread(
                self._client.secrets.delete_secret_by_name,
                secret_name=secret_name,
                project_id=self._project_id,
                secret_path=self._secret_path(tenant),
                environment_slug=self._environment,
            )
        except Exception as exc:
            if not self._is_not_found(exc):
                raise ProviderError(f"Infisical delete_secret failed: {exc}") from exc
