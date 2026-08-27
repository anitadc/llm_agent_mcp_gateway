import asyncio

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.secrets.base import SecretProvider


class VaultProvider(SecretProvider):
    """HashiCorp Vault, KV v2 secrets engine. Path is `{tenant}/{secret_name}`
    (or `default/{secret_name}` with no tenant) under the configured mount point.
    Each secret is stored as a single-key KV document `{"value": <secret>}` since
    this provider's contract is one string value per secret_name, not an arbitrary
    document."""

    def __init__(self, settings: Settings) -> None:
        import hvac

        self._client = hvac.Client(url=settings.vault_addr, token=settings.vault_token)
        self._mount_point = settings.vault_mount_point

    @staticmethod
    def _path(secret_name: str, tenant: str | None) -> str:
        return f"{tenant or 'default'}/{secret_name}"

    async def get_secret(self, secret_name: str, tenant: str | None = None) -> str | None:
        import hvac.exceptions

        try:
            response = await asyncio.to_thread(
                self._client.secrets.kv.v2.read_secret_version,
                path=self._path(secret_name, tenant),
                mount_point=self._mount_point,
                raise_on_deleted_version=True,
            )
        except hvac.exceptions.InvalidPath:
            return None
        except Exception as exc:
            raise ProviderError(f"Vault get_secret failed: {exc}") from exc
        return response["data"]["data"].get("value")

    async def set_secret(self, secret_name: str, value: str, tenant: str | None = None) -> None:
        try:
            await asyncio.to_thread(
                self._client.secrets.kv.v2.create_or_update_secret,
                path=self._path(secret_name, tenant),
                secret={"value": value},
                mount_point=self._mount_point,
            )
        except Exception as exc:
            raise ProviderError(f"Vault set_secret failed: {exc}") from exc

    async def delete_secret(self, secret_name: str, tenant: str | None = None) -> None:
        import hvac.exceptions

        try:
            await asyncio.to_thread(
                self._client.secrets.kv.v2.delete_metadata_and_all_versions,
                path=self._path(secret_name, tenant),
                mount_point=self._mount_point,
            )
        except hvac.exceptions.InvalidPath:
            pass
        except Exception as exc:
            raise ProviderError(f"Vault delete_secret failed: {exc}") from exc
