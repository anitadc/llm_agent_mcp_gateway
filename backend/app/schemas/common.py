import uuid

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: uuid.UUID | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
