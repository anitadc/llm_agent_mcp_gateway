import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
import redis.asyncio as redis
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.exceptions import BadRequestError, ProviderError
from app.db.models.api_endpoint import ApiEndpoint
from app.db.models.api_service import ApiService
from app.db.models.enums import RestAuthType, RestHttpMethod
from app.db.valkey import valkey_client
from app.secrets.service import SecretService
from app.services.api_registry.schema_converter import rest_response_to_mcp_content

_DEFAULT_MAX_ATTEMPTS = 2
_DEFAULT_BACKOFF_MULTIPLIER = 0.2
_DEFAULT_BACKOFF_MAX = 2.0
_OAUTH2_TOKEN_CACHE_TTL_FALLBACK_SECONDS = 300
_OAUTH2_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 30


@dataclass
class RestExecutionResult:
    content: dict[str, Any]
    status_code: int
    is_error: bool


class RestExecutor:
    """Executes a registered REST endpoint on behalf of an MCP `tools/call`,
    injecting credentials resolved through the existing Secret Provider layer
    (never a raw env var -- unlike the MCP Server Registry's outbound auth in
    services/mcp/mcp_client.py, which is a documented asymmetry this layer
    deliberately does not repeat) and converting the HTTP response into the
    standard MCP tool-result content shape.

    A non-2xx HTTP response from the target API is NOT a gateway failure -- it's
    a tool *result* (a 404 "customer not found" is useful information for the
    calling agent, not a broken gateway), so it comes back as `is_error=True`
    with the response body as content, mirroring the MCP protocol's own
    `isError` convention for a tool that ran but failed. Only a connection/
    timeout failure, a missing required argument, or a credential that fails to
    resolve raises a gateway-level exception (ProviderError/BadRequestError).

    GET requests (idempotent) get the same bounded transport-error retry as
    MCP's `initialize`/`tools/list`; POST/PUT/DELETE (potentially
    side-effecting) are never retried, for the same reason MCP's `tools/call`
    isn't -- see services/mcp/mcp_client.py.
    """

    def __init__(self, secret_service: SecretService, cache_client: redis.Redis | None = None) -> None:
        self.secret_service = secret_service
        self.cache_client = cache_client or valkey_client

    async def execute(
        self, service: ApiService, endpoint: ApiEndpoint, arguments: dict[str, Any]
    ) -> RestExecutionResult:
        path, query, headers, body = self._split_arguments(endpoint, arguments)
        url = service.base_url.rstrip("/") + path
        request_headers = {**service.headers, **headers, **(await self._resolve_auth_headers(service))}
        request_kwargs: dict[str, Any] = {"params": query or None, "headers": request_headers}
        if body:
            request_kwargs["json"] = body

        try:
            response = await self._send(service, endpoint.method, url, request_kwargs)
        except Exception as exc:
            # Broad on purpose, matching services/mcp/mcp_client.py's convention:
            # a GET's exhausted tenacity retries surface as tenacity.RetryError,
            # not the original httpx.TransportError, so narrowing this to
            # TransportError would miss that case.
            raise ProviderError(f"REST API '{service.name}' call to '{endpoint.tool_name}' failed: {exc}") from exc

        content = rest_response_to_mcp_content(self._parse_body(response))
        return RestExecutionResult(
            content=content, status_code=response.status_code, is_error=response.status_code >= 400
        )

    @staticmethod
    def _parse_body(response: httpx.Response) -> Any:
        if not response.content:
            return {"status_code": response.status_code}
        try:
            return response.json()
        except ValueError:
            return response.text

    async def _send(
        self, service: ApiService, method: RestHttpMethod, url: str, request_kwargs: dict[str, Any]
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=service.timeout_seconds) as client:
            if method != RestHttpMethod.GET:
                return await client.request(method.value, url, **request_kwargs)

            max_attempts = service.retry_policy.get("max_attempts", _DEFAULT_MAX_ATTEMPTS)
            multiplier = service.retry_policy.get("backoff_multiplier", _DEFAULT_BACKOFF_MULTIPLIER)
            backoff_max = service.retry_policy.get("backoff_max", _DEFAULT_BACKOFF_MAX)

            @retry(
                retry=retry_if_exception_type(httpx.TransportError),
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=multiplier, max=backoff_max),
            )
            async def _get() -> httpx.Response:
                return await client.get(url, **request_kwargs)

            return await _get()

    @staticmethod
    def _split_arguments(
        endpoint: ApiEndpoint, arguments: dict[str, Any]
    ) -> tuple[str, dict[str, Any], dict[str, str], dict[str, Any]]:
        """Buckets caller-supplied arguments into path/query/header/body groups
        per each parameter's registered `location` (defaulting to "path" if the
        name appears as a `{placeholder}` in the endpoint path, else "query"),
        and substitutes path placeholders -- `/customer/{id}` + {"id": "123"} ->
        `/customer/123`. Raises BadRequestError for a missing required argument,
        the gateway-level validation step called out in the spec."""
        path_template = endpoint.path
        path_values: dict[str, Any] = {}
        query: dict[str, Any] = {}
        headers: dict[str, str] = {}
        body: dict[str, Any] = {}

        for name, spec in (endpoint.parameters or {}).items():
            location = spec.get("location") or ("path" if f"{{{name}}}" in path_template else "query")
            if name not in arguments:
                if spec.get("required"):
                    raise BadRequestError(f"Missing required parameter '{name}' for tool '{endpoint.tool_name}'")
                continue
            value = arguments[name]
            if location == "path":
                path_values[name] = value
            elif location == "header":
                headers[name] = str(value)
            elif location == "body":
                body[name] = value
            else:
                query[name] = value

        path = path_template
        for name, value in path_values.items():
            path = path.replace("{" + name + "}", quote(str(value), safe=""))
        return path, query, headers, body

    async def _resolve_auth_headers(self, service: ApiService) -> dict[str, str]:
        config = service.auth_config or {}
        auth_type = service.authentication_type

        if auth_type == RestAuthType.none:
            return {}
        if auth_type == RestAuthType.api_key:
            value = await self.secret_service.get_secret(config.get("credential_ref", ""))
            return {config.get("header_name", "X-API-Key"): value} if value else {}
        if auth_type == RestAuthType.bearer:
            value = await self.secret_service.get_secret(config.get("credential_ref", ""))
            return {"Authorization": f"Bearer {value}"} if value else {}
        if auth_type == RestAuthType.basic:
            username = await self.secret_service.get_secret(config.get("username_ref", ""))
            password = await self.secret_service.get_secret(config.get("password_ref", ""))
            if not username or not password:
                return {}
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {"Authorization": f"Basic {token}"}
        if auth_type == RestAuthType.oauth2_client_credentials:
            token = await self._get_oauth2_token(service, config)
            return {"Authorization": f"Bearer {token}"} if token else {}
        return {}

    async def _get_oauth2_token(self, service: ApiService, config: dict[str, Any]) -> str | None:
        """Client-credentials token exchange, cached in Valkey per service so a
        busy tool doesn't re-authenticate on every single call -- the same
        bounded-cache tradeoff SecretService makes for secret values."""
        cache_key = f"oauth2-token:{service.id}"
        cached = await self.cache_client.get(cache_key)
        if cached:
            return cached

        client_id = await self.secret_service.get_secret(config.get("client_id_ref", ""))
        client_secret = await self.secret_service.get_secret(config.get("client_secret_ref", ""))
        token_url = config.get("token_url")
        if not token_url or not client_id or not client_secret:
            return None

        form = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
        if config.get("scope"):
            form["scope"] = config["scope"]

        try:
            async with httpx.AsyncClient(timeout=service.timeout_seconds) as client:
                response = await client.post(token_url, data=form)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"OAuth2 client-credentials exchange for '{service.name}' failed: {exc}") from exc

        payload = response.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise ProviderError(f"OAuth2 client-credentials exchange for '{service.name}' returned no access_token")

        ttl = max(int(payload.get("expires_in", _OAUTH2_TOKEN_CACHE_TTL_FALLBACK_SECONDS)) - _OAUTH2_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS, 30)
        await self.cache_client.set(cache_key, access_token, ex=ttl)
        return access_token
