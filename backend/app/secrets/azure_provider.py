import asyncio

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.secrets.base import SecretProvider

logger = get_logger(__name__)


class AzureKeyVaultProvider(SecretProvider):
    """Azure Key Vault. Key Vault secret names may only contain alphanumerics and
    hyphens, so `_` is translated to `-` and `tenant`/`secret_name` are joined with
    `-` (e.g. tenant "customer1" + "OPENAI_API_KEY" -> "customer1-OPENAI-API-KEY").
    Authenticates via DefaultAzureCredential (managed identity, env vars, Azure CLI
    login, ...) -- never a credential stored in this app's own config."""

    def __init__(self, settings: Settings) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        vault_url = f"https://{settings.azure_keyvault_name}.vault.azure.net"
        self._client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())

    @staticmethod
    def _normalize(name: str) -> str:
        return name.replace("_", "-")

    def _secret_name(self, secret_name: str, tenant: str | None) -> str:
        combined = f"{tenant}-{secret_name}" if tenant else secret_name
        return self._normalize(combined)

    async def get_secret(self, secret_name: str, tenant: str | None = None) -> str | None:
        from azure.core.exceptions import AzureError, ResourceNotFoundError

        try:
            result = await asyncio.to_thread(self._client.get_secret, self._secret_name(secret_name, tenant))
        except ResourceNotFoundError:
            return None
        except AzureError as exc:
            logger.exception("azure_keyvault_get_failed", secret_name=secret_name, tenant=tenant)
            raise ProviderError(f"Azure Key Vault get_secret failed: {exc}") from exc
        return result.value

    async def set_secret(self, secret_name: str, value: str, tenant: str | None = None) -> None:
        from azure.core.exceptions import AzureError

        try:
            # set_secret is an upsert in Key Vault -- no separate create/update path needed.
            await asyncio.to_thread(self._client.set_secret, self._secret_name(secret_name, tenant), value)
        except AzureError as exc:
            logger.exception("azure_keyvault_set_failed", secret_name=secret_name, tenant=tenant)
            raise ProviderError(f"Azure Key Vault set_secret failed: {exc}") from exc

    async def delete_secret(self, secret_name: str, tenant: str | None = None) -> None:
        from azure.core.exceptions import AzureError, ResourceNotFoundError

        try:
            poller = await asyncio.to_thread(self._client.begin_delete_secret, self._secret_name(secret_name, tenant))
            await asyncio.to_thread(poller.result)
        except ResourceNotFoundError:
            pass
        except AzureError as exc:
            logger.exception("azure_keyvault_delete_failed", secret_name=secret_name, tenant=tenant)
            raise ProviderError(f"Azure Key Vault delete_secret failed: {exc}") from exc
