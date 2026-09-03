import os
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger, log_method
from app.db.models.mcp_server import McpServer

logger = get_logger(__name__)

MCP_SESSION_HEADER = "Mcp-Session-Id"


@dataclass
class McpRpcResult:
    payload: dict[str, Any]
    session_id: str | None


def _resolve_auth_headers(server: McpServer) -> dict[str, str]:
    """Outbound service-to-service auth, driven by the registry's auth_config:
    {"type": "none" | "bearer" | "api_key", "credential_ref": "ENV_VAR_NAME",
    "header_name": "X-API-Key"}. credential_ref names an env var -- the raw secret
    is resolved at call time and never stored on the model or logged, mirroring
    ProviderConfig.credential_ref."""
    config = server.auth_config or {}
    auth_type = config.get("type", "none")
    if auth_type == "none":
        return {}
    credential_ref = config.get("credential_ref")
    token = os.environ.get(credential_ref) if credential_ref else None
    if not token:
        if credential_ref:
            logger.warning(
                "mcp_server_credential_missing",
                server_name=server.name,
                credential_ref=credential_ref,
            )
        return {}
    if auth_type == "bearer":
        return {"Authorization": f"Bearer {token}"}
    if auth_type == "api_key":
        return {config.get("header_name", "X-API-Key"): token}
    return {}


class McpClient:
    """Async Streamable HTTP transport for the MCP JSON-RPC protocol. Responses are
    read as a single buffered JSON body, not an SSE stream -- the same "buffer the
    full completion" tradeoff the chat path already makes (see CLAUDE.md's deferred
    streaming item), applied here to tool-call responses."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @log_method(logger)
    def _headers(self, server: McpServer, session_id: str | None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "MCP-Protocol-Version": server.protocol_version or self._settings.mcp_protocol_version,
        }
        if session_id:
            headers[MCP_SESSION_HEADER] = session_id
        headers.update(_resolve_auth_headers(server))
        return headers

    @log_method(logger)
    async def _post_raw(self, server: McpServer, body: dict[str, Any], session_id: str | None) -> McpRpcResult:
        async with httpx.AsyncClient(timeout=self._settings.mcp_client_timeout_seconds) as client:
            response = await client.post(server.base_url, json=body, headers=self._headers(server, session_id))
        response.raise_for_status()
        return McpRpcResult(payload=response.json(), session_id=response.headers.get(MCP_SESSION_HEADER))

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=0.2, max=2),
        # without this, an exhausted retry raises tenacity.RetryError instead of the
        # underlying httpx exception, which callers' `except httpx.HTTPError` would miss.
        reraise=True,
    )
    @log_method(logger)
    async def _post_idempotent(self, server: McpServer, body: dict[str, Any], session_id: str | None) -> McpRpcResult:
        return await self._post_raw(server, body, session_id)

    @log_method(logger)
    async def initialize(self, server: McpServer) -> McpRpcResult:
        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": self._settings.mcp_protocol_version,
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "llm-gateway-mcp", "version": "1.0.0"},
            },
        }
        try:
            return await self._post_idempotent(server, body, session_id=None)
        except httpx.HTTPError as exc:
            logger.exception(
                "mcp_server_initialize_failed",
                server_name=server.name,
                server_url=server.base_url,
            )
            raise ProviderError(f"MCP server '{server.name}' initialize failed: {exc}") from exc

    @log_method(logger)
    async def list_tools(self, server: McpServer, session_id: str | None) -> list[dict[str, Any]]:
        body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "tools/list", "params": {}}
        try:
            result = await self._post_idempotent(server, body, session_id)
        except httpx.HTTPError as exc:
            logger.exception(
                "mcp_server_tools_list_failed",
                server_name=server.name,
                server_url=server.base_url,
            )
            raise ProviderError(f"MCP server '{server.name}' tools/list failed: {exc}") from exc
        if "error" in result.payload:
            raise ProviderError(f"MCP server '{server.name}' tools/list error: {result.payload['error']}")
        return result.payload.get("result", {}).get("tools", [])

    @log_method(logger)
    async def call_tool(
        self,
        server: McpServer,
        session_id: str | None,
        request_id: str | int,
        name: str,
        arguments: dict[str, Any],
    ) -> McpRpcResult:
        """No automatic retry -- unlike initialize/tools/list this call may have side
        effects on the remote server, so a transport hiccup surfaces as an error
        instead of silently risking a duplicate tool execution."""
        body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        try:
            return await self._post_raw(server, body, session_id)
        except httpx.HTTPError as exc:
            logger.exception(
                "mcp_server_tools_call_failed",
                server_name=server.name,
                server_url=server.base_url,
                tool_name=name,
            )
            raise ProviderError(f"MCP server '{server.name}' tools/call failed: {exc}") from exc
