import pytest

from app.core.config import Settings
from app.secrets.aws_provider import AWSSecretsProvider
from app.secrets.azure_provider import AzureKeyVaultProvider
from app.secrets.factory import get_secret_provider, is_provider_available, list_provider_metadata
from app.secrets.gcp_provider import GCPSecretProvider
from app.secrets.infisical_provider import InfisicalProvider
from app.secrets.vault_provider import VaultProvider


def _settings(**overrides) -> Settings:
    defaults = dict(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        valkey_url="redis://localhost:6379/1",
        keycloak_base_url="http://localhost:8080",
        keycloak_realm="gateway",
        keycloak_client_id="gateway-frontend",
        keycloak_audience="gateway-backend",
        guardrails_base_url="http://localhost:9000",
        api_key_secret_pepper="pepper",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_factory_returns_infisical_provider_by_default() -> None:
    settings = _settings(
        secret_provider="infisical", infisical_client_id="id", infisical_client_secret="secret", infisical_project_id="proj"
    )
    assert isinstance(get_secret_provider(settings), InfisicalProvider)


def test_factory_returns_aws_provider() -> None:
    settings = _settings(secret_provider="aws", aws_secrets_region="us-east-1")
    assert isinstance(get_secret_provider(settings), AWSSecretsProvider)


def test_factory_returns_gcp_provider() -> None:
    settings = _settings(secret_provider="gcp", gcp_project_id="my-project")
    assert isinstance(get_secret_provider(settings), GCPSecretProvider)


def test_factory_returns_azure_provider() -> None:
    settings = _settings(secret_provider="azure", azure_keyvault_name="my-vault")
    assert isinstance(get_secret_provider(settings), AzureKeyVaultProvider)


def test_factory_returns_vault_provider() -> None:
    settings = _settings(secret_provider="vault", vault_addr="http://localhost:8200", vault_token="root")
    assert isinstance(get_secret_provider(settings), VaultProvider)


def test_factory_rejects_unknown_provider() -> None:
    settings = _settings()
    settings.secret_provider = "unknown-provider"
    with pytest.raises(ValueError):
        get_secret_provider(settings)


def test_list_provider_metadata_reports_all_five() -> None:
    settings = _settings(secret_provider="infisical")
    metadata = list_provider_metadata(settings)
    assert {m["name"] for m in metadata} == {"infisical", "aws", "gcp", "azure", "vault"}


def test_is_provider_available_reflects_config_presence() -> None:
    unconfigured = _settings()
    assert is_provider_available("infisical", unconfigured) is False
    assert is_provider_available("aws", unconfigured) is False

    configured = _settings(infisical_client_id="id", infisical_client_secret="secret", infisical_project_id="proj")
    assert is_provider_available("infisical", configured) is True
