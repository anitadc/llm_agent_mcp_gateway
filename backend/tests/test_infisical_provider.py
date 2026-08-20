from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.secrets.infisical_provider import InfisicalProvider


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
        secret_provider="infisical",
        infisical_client_id="test-client-id",
        infisical_client_secret="test-client-secret",
        infisical_project_id="test-project",
        infisical_environment="dev",
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.mark.asyncio
async def test_get_secret_returns_value_and_authenticates_only_once() -> None:
    with patch("infisical_sdk.InfisicalSDKClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.secrets.get_secret_by_name.return_value = MagicMock(secretValue="sk-test-123")
        provider = InfisicalProvider(_settings())

        first = await provider.get_secret("OPENAI_API_KEY")
        second = await provider.get_secret("OPENAI_API_KEY")

        assert first == "sk-test-123"
        assert second == "sk-test-123"
        mock_instance.auth.universal_auth.login.assert_called_once_with("test-client-id", "test-client-secret")


@pytest.mark.asyncio
async def test_get_secret_scopes_lookup_to_tenant_path() -> None:
    with patch("infisical_sdk.InfisicalSDKClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.secrets.get_secret_by_name.return_value = MagicMock(secretValue="val")
        provider = InfisicalProvider(_settings())

        await provider.get_secret("OPENAI_API_KEY", tenant="customer1")

        _, kwargs = mock_instance.secrets.get_secret_by_name.call_args
        assert kwargs["secret_path"] == "/customer1"
        assert kwargs["project_id"] == "test-project"
        assert kwargs["environment_slug"] == "dev"


@pytest.mark.asyncio
async def test_get_secret_returns_none_when_not_found() -> None:
    with patch("infisical_sdk.InfisicalSDKClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.secrets.get_secret_by_name.side_effect = Exception("Secret not found (404)")
        provider = InfisicalProvider(_settings())

        assert await provider.get_secret("MISSING_KEY") is None


@pytest.mark.asyncio
async def test_get_secret_raises_provider_error_on_real_failure() -> None:
    with patch("infisical_sdk.InfisicalSDKClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.secrets.get_secret_by_name.side_effect = Exception("connection refused")
        provider = InfisicalProvider(_settings())

        with pytest.raises(ProviderError):
            await provider.get_secret("OPENAI_API_KEY")


@pytest.mark.asyncio
async def test_set_secret_updates_existing_secret() -> None:
    with patch("infisical_sdk.InfisicalSDKClient") as MockClient:
        mock_instance = MockClient.return_value
        provider = InfisicalProvider(_settings())

        await provider.set_secret("OPENAI_API_KEY", "new-value")

        mock_instance.secrets.update_secret_by_name.assert_called_once()
        mock_instance.secrets.create_secret_by_name.assert_not_called()


@pytest.mark.asyncio
async def test_set_secret_creates_when_secret_does_not_exist_yet() -> None:
    with patch("infisical_sdk.InfisicalSDKClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.secrets.update_secret_by_name.side_effect = Exception("not found")
        provider = InfisicalProvider(_settings())

        await provider.set_secret("NEW_KEY", "value")

        mock_instance.secrets.create_secret_by_name.assert_called_once()


@pytest.mark.asyncio
async def test_delete_secret_calls_sdk_with_tenant_path() -> None:
    with patch("infisical_sdk.InfisicalSDKClient") as MockClient:
        mock_instance = MockClient.return_value
        provider = InfisicalProvider(_settings())

        await provider.delete_secret("OPENAI_API_KEY", tenant="customer1")

        _, kwargs = mock_instance.secrets.delete_secret_by_name.call_args
        assert kwargs["secret_path"] == "/customer1"


@pytest.mark.asyncio
async def test_missing_credentials_raises_provider_error_instead_of_calling_sdk() -> None:
    with patch("infisical_sdk.InfisicalSDKClient") as MockClient:
        mock_instance = MockClient.return_value
        provider = InfisicalProvider(_settings(infisical_client_id=None, infisical_client_secret=None))

        with pytest.raises(ProviderError):
            await provider.get_secret("OPENAI_API_KEY")

        mock_instance.auth.universal_auth.login.assert_not_called()
