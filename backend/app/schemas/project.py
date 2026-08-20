import uuid
from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    organization_id: uuid.UUID
    name: str


class ProjectUpdate(BaseModel):
    name: str


class ProjectOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}
