import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.db.models.enums import GuardrailDirection, ModelCapability, RequestStatus


class GuardrailResultOut(BaseModel):
    direction: GuardrailDirection
    allowed: bool
    violations: list[dict[str, Any]]

    model_config = {"from_attributes": True}


class RequestLogOut(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    api_key_id: uuid.UUID | None = None
    project_id: uuid.UUID
    organization_id: uuid.UUID
    model_alias: str
    capability: ModelCapability
    resolved_provider: str | None = None
    resolved_model: str | None = None
    status: RequestStatus
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    cache_hit: bool
    created_at: datetime
    guardrail_results: list[GuardrailResultOut] = []

    model_config = {"from_attributes": True}


class PaginatedRequestLogs(BaseModel):
    items: list[RequestLogOut]
    page: int
    page_size: int
    total: int
