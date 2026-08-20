import json
import uuid

import httpx
import pytest
import respx

from app.core.exceptions import BadRequestError, ProviderError
from app.db.models.api_endpoint import ApiEndpoint
from app.db.models.api_service import ApiService
from app.db.models.enums import RestAuthType, RestHttpMethod
from app.services.api_registry.rest_executor import RestExecutor


class _FakeSecretService:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    async def get_secret(self, secret_name: str, tenant: str | None = None, force_refresh: bool = False) -> str | None:
        return self.values.get(secret_name)


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.store[key] = value


def _service(**overrides) -> ApiService:
    defaults = dict(
        id=uuid.uuid4(),
        name="customer-service",
        base_url="http://api.test",
        authentication_type=RestAuthType.none,
        auth_config={},
        headers={},
        timeout_seconds=5.0,
        retry_policy={},
    )
    defaults.update(overrides)
    return ApiService(**defaults)


def _endpoint(**overrides) -> ApiEndpoint:
    defaults = dict(
        id=uuid.uuid4(),
        tool_name="get_customer",
        method=RestHttpMethod.GET,
        path="/customers/{id}",
        parameters={"id": {"type": "string", "required": True, "location": "path"}},
    )
    defaults.update(overrides)
    return ApiEndpoint(**defaults)


@pytest.mark.asyncio
@respx.mock
async def test_get_request_substitutes_path_parameter() -> None:
    route = respx.get("http://api.test/customers/123").mock(return_value=httpx.Response(200, json={"id": 123}))
    executor = RestExecutor(_FakeSecretService({}))

    result = await executor.execute(_service(), _endpoint(), {"id": "123"})

    assert route.called
    assert json.loads(result.content["content"][0]["text"]) == {"id": 123}
    assert result.status_code == 200
    assert result.is_error is False


@pytest.mark.asyncio
@respx.mock
async def test_missing_required_parameter_raises_bad_request_error() -> None:
    executor = RestExecutor(_FakeSecretService({}))

    with pytest.raises(BadRequestError):
        await executor.execute(_service(), _endpoint(), {})


@pytest.mark.asyncio
@respx.mock
async def test_query_parameters_are_forwarded() -> None:
    route = respx.get("http://api.test/customers/123").mock(return_value=httpx.Response(200, json={}))
    endpoint = _endpoint(
        parameters={
            "id": {"type": "string", "required": True, "location": "path"},
            "page": {"type": "integer", "required": False, "location": "query"},
        }
    )
    executor = RestExecutor(_FakeSecretService({}))

    await executor.execute(_service(), endpoint, {"id": "123", "page": 2})

    assert route.calls[0].request.url.params["page"] == "2"


@pytest.mark.asyncio
@respx.mock
async def test_header_parameter_is_forwarded() -> None:
    route = respx.get("http://api.test/customers/123").mock(return_value=httpx.Response(200, json={}))
    endpoint = _endpoint(
        parameters={
            "id": {"type": "string", "required": True, "location": "path"},
            "x-trace-id": {"type": "string", "location": "header"},
        }
    )
    executor = RestExecutor(_FakeSecretService({}))

    await executor.execute(_service(), endpoint, {"id": "123", "x-trace-id": "abc"})

    assert route.calls[0].request.headers["x-trace-id"] == "abc"


@pytest.mark.asyncio
@respx.mock
async def test_body_parameters_are_sent_as_json_for_post() -> None:
    route = respx.post("http://api.test/tickets").mock(return_value=httpx.Response(201, json={"id": 1}))
    endpoint = _endpoint(
        tool_name="create_ticket",
        method=RestHttpMethod.POST,
        path="/tickets",
        parameters={"title": {"type": "string", "required": True, "location": "body"}},
    )
    executor = RestExecutor(_FakeSecretService({}))

    result = await executor.execute(_service(), endpoint, {"title": "Something broke"})

    assert json.loads(route.calls[0].request.content) == {"title": "Something broke"}
    assert result.status_code == 201


@pytest.mark.asyncio
@respx.mock
async def test_non_2xx_response_is_a_tool_error_not_a_raised_exception() -> None:
    respx.get("http://api.test/customers/999").mock(return_value=httpx.Response(404, json={"error": "not found"}))
    executor = RestExecutor(_FakeSecretService({}))

    result = await executor.execute(_service(), _endpoint(), {"id": "999"})

    assert result.is_error is True
    assert result.status_code == 404
    assert json.loads(result.content["content"][0]["text"]) == {"error": "not found"}


@pytest.mark.asyncio
@respx.mock
async def test_connection_error_raises_provider_error() -> None:
    respx.get("http://api.test/customers/123").mock(side_effect=httpx.ConnectError("boom"))
    executor = RestExecutor(_FakeSecretService({}))

    with pytest.raises(ProviderError):
        await executor.execute(_service(), _endpoint(), {"id": "123"})


@pytest.mark.asyncio
@respx.mock
async def test_get_retries_on_transient_transport_error() -> None:
    route = respx.get("http://api.test/customers/123")
    route.side_effect = [httpx.ConnectError("boom"), httpx.Response(200, json={"id": 123})]
    executor = RestExecutor(_FakeSecretService({}))

    result = await executor.execute(_service(), _endpoint(), {"id": "123"})

    assert result.status_code == 200
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_post_does_not_retry_on_transport_error() -> None:
    route = respx.post("http://api.test/tickets").mock(side_effect=httpx.ConnectError("boom"))
    endpoint = _endpoint(tool_name="create_ticket", method=RestHttpMethod.POST, path="/tickets", parameters={})
    executor = RestExecutor(_FakeSecretService({}))

    with pytest.raises(ProviderError):
        await executor.execute(_service(), endpoint, {})

    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_api_key_auth_injects_configured_header() -> None:
    route = respx.get("http://api.test/customers/123").mock(return_value=httpx.Response(200, json={}))
    service = _service(
        authentication_type=RestAuthType.api_key,
        auth_config={"credential_ref": "CUSTOMER_API_KEY", "header_name": "X-Api-Key"},
    )
    executor = RestExecutor(_FakeSecretService({"CUSTOMER_API_KEY": "k3y"}))

    await executor.execute(service, _endpoint(), {"id": "123"})

    assert route.calls[0].request.headers["X-Api-Key"] == "k3y"


@pytest.mark.asyncio
@respx.mock
async def test_bearer_auth_injects_authorization_header() -> None:
    route = respx.get("http://api.test/customers/123").mock(return_value=httpx.Response(200, json={}))
    service = _service(authentication_type=RestAuthType.bearer, auth_config={"credential_ref": "CUSTOMER_TOKEN"})
    executor = RestExecutor(_FakeSecretService({"CUSTOMER_TOKEN": "tok123"}))

    await executor.execute(service, _endpoint(), {"id": "123"})

    assert route.calls[0].request.headers["Authorization"] == "Bearer tok123"


@pytest.mark.asyncio
@respx.mock
async def test_basic_auth_injects_base64_credentials() -> None:
    import base64

    route = respx.get("http://api.test/customers/123").mock(return_value=httpx.Response(200, json={}))
    service = _service(
        authentication_type=RestAuthType.basic,
        auth_config={"username_ref": "CUSTOMER_USER", "password_ref": "CUSTOMER_PASS"},
    )
    executor = RestExecutor(_FakeSecretService({"CUSTOMER_USER": "alice", "CUSTOMER_PASS": "s3cret"}))

    await executor.execute(service, _endpoint(), {"id": "123"})

    expected = "Basic " + base64.b64encode(b"alice:s3cret").decode()
    assert route.calls[0].request.headers["Authorization"] == expected


@pytest.mark.asyncio
@respx.mock
async def test_oauth2_client_credentials_fetches_and_caches_token() -> None:
    token_route = respx.post("http://auth.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "oauth-tok", "expires_in": 3600})
    )
    api_route = respx.get("http://api.test/customers/123").mock(return_value=httpx.Response(200, json={}))
    service = _service(
        authentication_type=RestAuthType.oauth2_client_credentials,
        auth_config={"token_url": "http://auth.test/token", "client_id_ref": "CID", "client_secret_ref": "CSECRET"},
    )
    redis = _FakeRedis()
    executor = RestExecutor(_FakeSecretService({"CID": "client-id", "CSECRET": "client-secret"}), cache_client=redis)

    await executor.execute(service, _endpoint(), {"id": "123"})
    await executor.execute(service, _endpoint(), {"id": "123"})

    assert token_route.call_count == 1  # second call served from cache
    assert api_route.calls[0].request.headers["Authorization"] == "Bearer oauth-tok"
    assert api_route.calls[1].request.headers["Authorization"] == "Bearer oauth-tok"
