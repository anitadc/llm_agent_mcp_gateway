import asyncio

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.secrets.base import SecretProvider


class GCPSecretProvider(SecretProvider):
    """Google Cloud Secret Manager. Secret IDs are namespaced as
    `{tenant}__{secret_name}` (GCP secret IDs allow letters, digits, hyphens and
    underscores but not `/`, so `__` stands in for a path separator) or bare
    `secret_name` with no tenant. Always reads the `latest` version."""

    def __init__(self, settings: Settings) -> None:
        self._project_id = settings.gcp_project_id
        self._client = None

    @property
    def _resolved_client(self):
        # Constructing SecretManagerServiceClient() resolves Application Default
        # Credentials immediately (a real network/filesystem lookup) -- deferred
        # until first actual use so simply instantiating this provider (e.g. once
        # per request via the DI factory) never pays that cost when GCP isn't the
        # active provider, and an ADC failure surfaces as a get/set/delete error
        # rather than at construction time.
        if self._client is None:
            from google.cloud import secretmanager

            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    def _secret_id(self, secret_name: str, tenant: str | None) -> str:
        return f"{tenant}__{secret_name}" if tenant else secret_name

    def _secret_resource(self, secret_name: str, tenant: str | None) -> str:
        return f"projects/{self._project_id}/secrets/{self._secret_id(secret_name, tenant)}"

    async def get_secret(self, secret_name: str, tenant: str | None = None) -> str | None:
        from google.api_core.exceptions import NotFound

        try:
            response = await asyncio.to_thread(
                self._resolved_client.access_secret_version,
                request={"name": f"{self._secret_resource(secret_name, tenant)}/versions/latest"},
            )
        except NotFound:
            return None
        except Exception as exc:
            raise ProviderError(f"GCP Secret Manager get_secret failed: {exc}") from exc
        return response.payload.data.decode("utf-8")

    async def set_secret(self, secret_name: str, value: str, tenant: str | None = None) -> None:
        from google.api_core.exceptions import AlreadyExists, NotFound

        resource = self._secret_resource(secret_name, tenant)
        try:
            await asyncio.to_thread(self._resolved_client.get_secret, request={"name": resource})
        except NotFound:
            try:
                await asyncio.to_thread(
                    self._resolved_client.create_secret,
                    request={
                        "parent": f"projects/{self._project_id}",
                        "secret_id": self._secret_id(secret_name, tenant),
                        "secret": {"replication": {"automatic": {}}},
                    },
                )
            except AlreadyExists:
                pass
            except Exception as exc:
                raise ProviderError(f"GCP Secret Manager create_secret failed: {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"GCP Secret Manager get_secret (pre-check) failed: {exc}") from exc

        try:
            await asyncio.to_thread(
                self._resolved_client.add_secret_version,
                request={"parent": resource, "payload": {"data": value.encode("utf-8")}},
            )
        except Exception as exc:
            raise ProviderError(f"GCP Secret Manager add_secret_version failed: {exc}") from exc

    async def delete_secret(self, secret_name: str, tenant: str | None = None) -> None:
        from google.api_core.exceptions import NotFound

        try:
            await asyncio.to_thread(
                self._resolved_client.delete_secret, request={"name": self._secret_resource(secret_name, tenant)}
            )
        except NotFound:
            pass
        except Exception as exc:
            raise ProviderError(f"GCP Secret Manager delete_secret failed: {exc}") from exc
