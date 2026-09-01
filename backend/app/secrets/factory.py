from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.secrets.base import SecretProvider

logger = get_logger(__name__)

PROVIDER_NAMES = ["postgres", "infisical", "aws", "gcp", "azure", "vault"]

class NullSecretProvider(SecretProvider):
    """Explicit no-op provider for deployments that intentionally do not
    configure a secret backend. It behaves like an always-empty secret store so
    the app can still boot and report "not configured" for secret lookups."""

    async def get_secret(self, secret_name: str, tenant: str | None = None) -> str | None:
        return None

    async def set_secret(self, secret_name: str, value: str, tenant: str | None = None) -> None:
        return None

    async def delete_secret(self, secret_name: str, tenant: str | None = None) -> None:
        return None


def get_secret_provider(settings: Settings | None = None) -> SecretProvider:
    """The only place in the app that knows which concrete SecretProvider class
    backs SECRET_PROVIDER. Every provider module is imported lazily, inside its
    own branch, so a deployment never pays for (or needs installed/configured)
    SDKs it isn't using."""
    settings = settings or get_settings()
    provider = settings.secret_provider

    if provider is None:
        return NullSecretProvider()
    if provider == "postgres":
        from app.secrets.postgres_provider import PostgresSecretProvider

        return PostgresSecretProvider(settings)
    if provider == "infisical":
        from app.secrets.infisical_provider import InfisicalProvider

        return InfisicalProvider(settings)
    if provider == "aws":
        from app.secrets.aws_provider import AWSSecretsProvider

        return AWSSecretsProvider(settings)
    if provider == "gcp":
        from app.secrets.gcp_provider import GCPSecretProvider

        return GCPSecretProvider(settings)
    if provider == "azure":
        from app.secrets.azure_provider import AzureKeyVaultProvider

        return AzureKeyVaultProvider(settings)
    if provider == "vault":
        from app.secrets.vault_provider import VaultProvider

        return VaultProvider(settings)

    logger.error("unknown_secret_provider", provider=provider)
    raise ValueError(f"Unknown SECRET_PROVIDER '{provider}'")


def is_provider_available(name: str, settings: Settings) -> bool:
    """Static config-presence check (NOT a live connectivity probe) -- just
    enough for the admin UI to show which providers this deployment is even
    configured for, without making an outbound call on every page load."""
    if name == "postgres":
        return bool(settings.secret_storage_encryption_key)
    if name == "infisical":
        return bool(settings.infisical_client_id and settings.infisical_client_secret and settings.infisical_project_id)
    if name == "aws":
        return bool(settings.aws_secrets_region)
    if name == "gcp":
        return bool(settings.gcp_project_id)
    if name == "azure":
        return bool(settings.azure_keyvault_name)
    if name == "vault":
        return bool(settings.vault_addr)
    return False


def list_provider_metadata(settings: Settings | None = None) -> list[dict]:
    settings = settings or get_settings()
    return [{"name": name, "available": is_provider_available(name, settings)} for name in PROVIDER_NAMES]
