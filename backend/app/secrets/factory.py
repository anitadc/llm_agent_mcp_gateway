from app.core.config import Settings, get_settings
from app.secrets.base import SecretProvider

PROVIDER_NAMES = ["infisical", "aws", "gcp", "azure", "vault"]


def get_secret_provider(settings: Settings | None = None) -> SecretProvider:
    """The only place in the app that knows which concrete SecretProvider class
    backs SECRET_PROVIDER. Every provider module is imported lazily, inside its
    own branch, so a deployment never pays for (or needs installed/configured)
    SDKs it isn't using."""
    settings = settings or get_settings()
    provider = settings.secret_provider

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

    raise ValueError(f"Unknown SECRET_PROVIDER '{provider}'")


def is_provider_available(name: str, settings: Settings) -> bool:
    """Static config-presence check (NOT a live connectivity probe) -- just
    enough for the admin UI to show which providers this deployment is even
    configured for, without making an outbound call on every page load."""
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
