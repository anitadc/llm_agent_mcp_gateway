import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.db.models.enums import McpHealthStatus, McpServerStatus, McpSyncStatus, McpToolSourceType, McpTransportType
from app.db.models.mcp_server import McpServer
from app.db.models.mcp_tool import McpTool


class JsonRpcRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] | None = None


class JsonRpcErrorObject(BaseModel):
    code: int
    message: str
    data: Any | None = None


class JsonRpcResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    result: Any | None = None
    error: JsonRpcErrorObject | None = None


class McpServerCreate(BaseModel):
    name: str
    base_url: str
    transport_type: McpTransportType = McpTransportType.http
    description: str | None = None
    # {"type": "none" | "bearer" | "api_key", "credential_ref": "ENV_VAR_NAME", "header_name": "X-API-Key"}
    auth_config: dict[str, Any] = {}
    status: McpServerStatus = McpServerStatus.active
    metadata: dict[str, Any] = {}


class McpServerUpdate(BaseModel):
    base_url: str | None = None
    description: str | None = None
    auth_config: dict[str, Any] | None = None
    status: McpServerStatus | None = None
    metadata: dict[str, Any] | None = None


class McpServerOut(BaseModel):
    id: uuid.UUID
    name: str
    base_url: str
    transport_type: McpTransportType
    description: str | None = None
    auth_config: dict[str, Any]
    status: McpServerStatus
    health_status: McpHealthStatus
    last_heartbeat: datetime | None = None
    protocol_version: str | None = None
    last_sync_status: McpSyncStatus | None = None
    last_sync_error: str | None = None
    last_sync_at: datetime | None = None
    last_sync_latency_ms: int | None = None
    metadata: dict[str, Any]
    created_at: datetime
    tool_count: int = 0

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, server: McpServer, tool_count: int = 0) -> "McpServerOut":
        return cls(
            id=server.id,
            name=server.name,
            base_url=server.base_url,
            transport_type=server.transport_type,
            description=server.description,
            auth_config=server.auth_config,
            status=server.status,
            health_status=server.health_status,
            last_heartbeat=server.last_heartbeat,
            protocol_version=server.protocol_version,
            last_sync_status=server.last_sync_status,
            last_sync_error=server.last_sync_error,
            last_sync_at=server.last_sync_at,
            last_sync_latency_ms=server.last_sync_latency_ms,
            metadata=server.extra_metadata,
            created_at=server.created_at,
            tool_count=tool_count,
        )


class McpServerStatsOut(BaseModel):
    server_id: uuid.UUID
    window_minutes: int
    request_count: int
    error_count: int
    avg_latency_ms: float | None = None


class McpToolOut(BaseModel):
    id: uuid.UUID
    source_type: McpToolSourceType
    # Unified "what does this tool execute against" view -- populated from
    # server.name for source_type=mcp, or api_endpoint.api_service.name for
    # source_type=rest, so the frontend's Unified Tool Explorer can render a
    # single "Target" column regardless of tool kind.
    target: str
    server_id: uuid.UUID | None = None
    name: str
    description: str | None = None
    input_schema: dict[str, Any]
    enabled: bool
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, tool: McpTool) -> "McpToolOut":
        target = tool.server.name if tool.source_type == McpToolSourceType.mcp else tool.api_endpoint.api_service.name
        return cls(
            id=tool.id,
            source_type=tool.source_type,
            target=target,
            server_id=tool.server_id,
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            enabled=tool.enabled,
            updated_at=tool.updated_at,
        )


class McpSessionOut(BaseModel):
    id: uuid.UUID
    client_session_id: str
    project_id: uuid.UUID | None = None
    api_key_id: uuid.UUID | None = None
    server_sessions: dict[str, str]
    created_at: datetime
    last_used_at: datetime

    model_config = {"from_attributes": True}
