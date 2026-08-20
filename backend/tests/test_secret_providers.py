from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.secrets.aws_provider import AWSSecretsProvider
from app.secrets.azure_provider import AzureKeyVaultProvider
from app.secrets.gcp_provider import GCPSecretProvider
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


# --- AWS Secrets Manager -----------------------------------------------------


@pytest.mark.asyncio
async def test_aws_get_secret_uses_prefix_and_tenant_namespaced_name() -> None:
    with patch("boto3.client") as mock_client_factory:
        mock_client = mock_client_factory.return_value
        mock_client.get_secret_value.return_value = {"SecretString": "sk-aws"}
        provider = AWSSecretsProvider(_settings(aws_secrets_region="us-east-1", aws_secret_name_prefix="llm-gateway"))

        value = await provider.get_secret("OPENAI_API_KEY", tenant="tenant-a")

        assert value == "sk-aws"
        mock_client.get_secret_value.assert_called_once_with(SecretId="llm-gateway/tenant-a/OPENAI_API_KEY")


@pytest.mark.asyncio
async def test_aws_set_secret_falls_back_to_create_when_missing() -> None:
    class _NotFound(Exception):
        response = {"Error": {"Code": "ResourceNotFoundException"}}

    with patch("boto3.client") as mock_client_factory:
        mock_client = mock_client_factory.return_value
        mock_client.put_secret_value.side_effect = _NotFound()
        provider = AWSSecretsProvider(_settings(aws_secrets_region="us-east-1"))

        await provider.set_secret("OPENAI_API_KEY", "value")

        mock_client.create_secret.assert_called_once()


# --- GCP Secret Manager -------------------------------------------------------


@pytest.mark.asyncio
async def test_gcp_get_secret_namespaces_by_tenant_and_decodes_payload() -> None:
    with patch("google.cloud.secretmanager.SecretManagerServiceClient") as MockClient:
        mock_client = MockClient.return_value
        mock_client.access_secret_version.return_value = MagicMock(payload=MagicMock(data=b"sk-gcp"))
        provider = GCPSecretProvider(_settings(gcp_project_id="my-project"))

        value = await provider.get_secret("OPENAI_API_KEY", tenant="tenant-a")

        assert value == "sk-gcp"
        _, kwargs = mock_client.access_secret_version.call_args
        assert kwargs["request"]["name"] == "projects/my-project/secrets/tenant-a__OPENAI_API_KEY/versions/latest"


@pytest.mark.asyncio
async def test_gcp_client_is_not_constructed_until_first_use() -> None:
    with patch("google.cloud.secretmanager.SecretManagerServiceClient") as MockClient:
        GCPSecretProvider(_settings(gcp_project_id="my-project"))
        MockClient.assert_not_called()


# --- Azure Key Vault -----------------------------------------------------------


@pytest.mark.asyncio
async def test_azure_get_secret_normalizes_underscores_to_hyphens() -> None:
    with patch("azure.identity.DefaultAzureCredential"), patch("azure.keyvault.secrets.SecretClient") as MockClient:
        mock_client = MockClient.return_value
        mock_client.get_secret.return_value = MagicMock(value="sk-azure")
        provider = AzureKeyVaultProvider(_settings(azure_keyvault_name="my-vault"))

        value = await provider.get_secret("OPENAI_API_KEY", tenant="tenant-a")

        assert value == "sk-azure"
        mock_client.get_secret.assert_called_once_with("tenant-a-OPENAI-API-KEY")


@pytest.mark.asyncio
async def test_azure_set_secret_is_a_plain_upsert() -> None:
    with patch("azure.identity.DefaultAzureCredential"), patch("azure.keyvault.secrets.SecretClient") as MockClient:
        mock_client = MockClient.return_value
        provider = AzureKeyVaultProvider(_settings(azure_keyvault_name="my-vault"))

        await provider.set_secret("OPENAI_API_KEY", "value")

        mock_client.set_secret.assert_called_once_with("OPENAI-API-KEY", "value")


# --- HashiCorp Vault -----------------------------------------------------------


@pytest.mark.asyncio
async def test_vault_get_secret_reads_from_kv_v2_at_tenant_path() -> None:
    with patch("hvac.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_client.secrets.kv.v2.read_secret_version.return_value = {"data": {"data": {"value": "sk-vault"}}}
        provider = VaultProvider(_settings(vault_addr="http://localhost:8200", vault_token="root", vault_mount_point="secret"))

        value = await provider.get_secret("OPENAI_API_KEY", tenant="tenant-a")

        assert value == "sk-vault"
        _, kwargs = mock_client.secrets.kv.v2.read_secret_version.call_args
        assert kwargs["path"] == "tenant-a/OPENAI_API_KEY"
        assert kwargs["mount_point"] == "secret"


@pytest.mark.asyncio
async def test_vault_get_secret_defaults_to_default_namespace_without_tenant() -> None:
    with patch("hvac.Client") as MockClient:
        mock_client = MockClient.return_value
        mock_client.secrets.kv.v2.read_secret_version.return_value = {"data": {"data": {"value": "sk-vault"}}}
        provider = VaultProvider(_settings(vault_addr="http://localhost:8200", vault_token="root"))

        await provider.get_secret("OPENAI_API_KEY")

        _, kwargs = mock_client.secrets.kv.v2.read_secret_version.call_args
        assert kwargs["path"] == "default/OPENAI_API_KEY"
