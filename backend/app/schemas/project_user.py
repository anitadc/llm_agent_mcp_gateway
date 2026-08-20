import uuid
from datetime import date, datetime

from pydantic import BaseModel


class ProjectUserCreate(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID
    start_date: date | None = None


class ProjectUserUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None


class ProjectUserOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    start_date: date
    end_date: date | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
