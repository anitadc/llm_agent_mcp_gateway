from app.core.config import get_settings
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    # __table_args__ = {"schema": get_settings().database_schema}
    # metadata.schema = get_settings().database_schema
    # metadata = DeclarativeBase.metadata(schema=get_settings().database_schema)
    pass