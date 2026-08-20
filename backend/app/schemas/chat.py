import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float = Field(default=1.0, ge=0, le=2)
    max_tokens: int | None = None
    top_p: float | None = None
    stream: bool = False
    user: str | None = None


class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: Literal["stop", "length", "content_filter"]


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class GatewayMetadata(BaseModel):
    request_id: uuid.UUID
    resolved_provider: str | None = None
    resolved_model: str | None = None
    cache_hit: bool = False
    cost_usd: float


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: Usage
    gateway_metadata: GatewayMetadata
