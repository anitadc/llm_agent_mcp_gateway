import asyncio

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.secrets.base import SecretProvider

logger = get_logger(__name__)


class AWSSecretsProvider(SecretProvider):
    """AWS Secrets Manager. Secret names are namespaced as
    `{prefix}/{tenant}/{secret_name}` (or `{prefix}/{secret_name}` with no tenant) --
    AWS secret names natively allow `/`, so this reads as a normal path hierarchy in
    the console. Credentials for AWS itself come from boto3's standard credential
    chain (env vars, instance/task role, ~/.aws/config, ...), never from this app's
    own config -- that's exactly the kind of hardcoded credential this layer exists
    to avoid.
    """

    def __init__(self, settings: Settings) -> None:
        import boto3

        self._client = boto3.client("secretsmanager", region_name=settings.aws_secrets_region)
        self._prefix = settings.aws_secret_name_prefix

    def _full_name(self, secret_name: str, tenant: str | None) -> str:
        parts = [p for p in (self._prefix, tenant, secret_name) if p]
        return "/".join(parts)

    @staticmethod
    def _is_not_found(exc: Exception) -> bool:
        return getattr(exc, "response", {}).get("Error", {}).get("Code") == "ResourceNotFoundException"

    async def get_secret(self, secret_name: str, tenant: str | None = None) -> str | None:
        import botocore.exceptions

        try:
            response = await asyncio.to_thread(self._client.get_secret_value, SecretId=self._full_name(secret_name, tenant))
        except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as exc:
            if self._is_not_found(exc):
                return None
            logger.exception("aws_secrets_get_failed", secret_name=secret_name, tenant=tenant)
            raise ProviderError(f"AWS Secrets Manager get_secret failed: {exc}") from exc
        return response.get("SecretString")

    async def set_secret(self, secret_name: str, value: str, tenant: str | None = None) -> None:
        import botocore.exceptions

        name = self._full_name(secret_name, tenant)
        try:
            await asyncio.to_thread(self._client.put_secret_value, SecretId=name, SecretString=value)
        except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as exc:
            if not self._is_not_found(exc):
                logger.exception("aws_secrets_set_failed", secret_name=secret_name, tenant=tenant)
                raise ProviderError(f"AWS Secrets Manager set_secret failed: {exc}") from exc
            try:
                await asyncio.to_thread(self._client.create_secret, Name=name, SecretString=value)
            except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as create_exc:
                logger.exception("aws_secrets_create_failed", secret_name=secret_name, tenant=tenant)
                raise ProviderError(f"AWS Secrets Manager create_secret failed: {create_exc}") from create_exc

    async def delete_secret(self, secret_name: str, tenant: str | None = None) -> None:
        import botocore.exceptions

        name = self._full_name(secret_name, tenant)
        try:
            # No ForceDeleteWithoutRecovery: AWS's default recovery window (7-30
            # days) protects against an accidental/malicious delete being permanent.
            await asyncio.to_thread(self._client.delete_secret, SecretId=name)
        except (botocore.exceptions.ClientError, botocore.exceptions.BotoCoreError) as exc:
            if not self._is_not_found(exc):
                logger.exception("aws_secrets_delete_failed", secret_name=secret_name, tenant=tenant)
                raise ProviderError(f"AWS Secrets Manager delete_secret failed: {exc}") from exc
