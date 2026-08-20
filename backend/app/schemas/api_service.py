import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.db.models.api_endpoint import ApiEndpoint
from app.db.models.api_service import ApiService
from app.db.models.enums import ApiServiceStatus, RestAuthType, RestHttpMethod


class ApiServiceCreate(BaseModel):
    name: str
    description: str | None = None
    base_url: str
    authentication_type: RestAuthType = RestAuthType.none
    # See ApiService.auth_config docstring for the shape per authentication_type.
    auth_config: dict[str, Any] = {}
    headers: dict[str, str] = {}
    timeout_seconds: float = 10.0
    retry_policy: dict[str, Any] = {}
    rate_limit_per_window: int | None = None
    status: ApiServiceStatus = ApiServiceStatus.active
    metadata: dict[str, Any] = {}


class ApiServiceUpdate(BaseModel):
    description: str | None = None
    base_url: str | None = None
    authentication_type: RestAuthType | None = None
    auth_config: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    timeout_seconds: float | None = None
    retry_policy: dict[str, Any] | None = None
    rate_limit_per_window: int | None = None
    status: ApiServiceStatus | None = None
    metadata: dict[str, Any] | None = None


class ApiServiceOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    base_url: str
    authentication_type: RestAuthType
    auth_config: dict[str, Any]
    headers: dict[str, str]
    timeout_seconds: float
    retry_policy: dict[str, Any]
    rate_limit_per_window: int | None = None
    status: ApiServiceStatus
    metadata: dict[str, Any]
    created_at: datetime
    endpoint_count: int = 0

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, service: ApiService, endpoint_count: int = 0) -> "ApiServiceOut":
        return cls(
            id=service.id,
            name=service.name,
            description=service.description,
            base_url=service.base_url,
            authentication_type=service.authentication_type,
            auth_config=service.auth_config,
            headers=service.headers,
            timeout_seconds=service.timeout_seconds,
            retry_policy=service.retry_policy,
            rate_limit_per_window=service.rate_limit_per_window,
            status=service.status,
            metadata=service.extra_metadata,
            created_at=service.created_at,
            endpoint_count=endpoint_count,
        )


class ApiEndpointParameter(BaseModel):
    type: str = "string"
    required: bool = False
    location: str = "query"
    description: str | None = None


class ApiEndpointCreate(BaseModel):
    tool_name: str
    description: str | None = None
    method: RestHttpMethod
    path: str
    # keyed by parameter name, e.g. {"id": {"type": "string", "required": true, "location": "path"}}
    parameters: dict[str, ApiEndpointParameter] = {}
    enabled: bool = True


class ApiEndpointUpdate(BaseModel):
    description: str | None = None
    method: RestHttpMethod | None = None
    path: str | None = None
    parameters: dict[str, ApiEndpointParameter] | None = None
    enabled: bool | None = None


class ApiEndpointOut(BaseModel):
    id: uuid.UUID
    api_service_id: uuid.UUID
    api_service_name: str
    tool_name: str
    description: str | None = None
    method: RestHttpMethod
    path: str
    parameters: dict[str, Any]
    enabled: bool
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, endpoint: ApiEndpoint) -> "ApiEndpointOut":
        return cls(
            id=endpoint.id,
            api_service_id=endpoint.api_service_id,
            api_service_name=endpoint.api_service.name,
            tool_name=endpoint.tool_name,
            description=endpoint.description,
            method=endpoint.method,
            path=endpoint.path,
            parameters=endpoint.parameters,
            enabled=endpoint.enabled,
            updated_at=endpoint.updated_at,
        )
