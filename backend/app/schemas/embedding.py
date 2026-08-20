from typing import Literal

from pydantic import BaseModel

from app.schemas.chat import GatewayMetadata


class EmbeddingRequest(BaseModel):
    model: str
    input: str | list[str]
    encoding_format: Literal["float", "base64"] = "float"
    user: str | None = None


class EmbeddingData(BaseModel):
    index: int
    embedding: list[float]


class EmbeddingUsage(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    object: Literal["list"] = "list"
    model: str
    data: list[EmbeddingData]
    usage: EmbeddingUsage
    gateway_metadata: GatewayMetadata
