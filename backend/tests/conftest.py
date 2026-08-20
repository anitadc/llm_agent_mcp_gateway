import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("VALKEY_URL", "redis://localhost:6379/1")
os.environ.setdefault("KEYCLOAK_BASE_URL", "http://localhost:8080")
os.environ.setdefault("KEYCLOAK_REALM", "gateway")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "gateway-frontend")
os.environ.setdefault("KEYCLOAK_AUDIENCE", "gateway-backend")
os.environ.setdefault("GUARDRAILS_BASE_URL", "http://localhost:9000")
os.environ.setdefault("API_KEY_SECRET_PEPPER", "test-pepper")

from app.db.base import Base  # noqa: E402
from app.db.models import *  # noqa: E402,F401,F403
from app.db.models.api_key import ApiKey  # noqa: E402
from app.db.models.organization import Organization  # noqa: E402
from app.db.models.project import Project  # noqa: E402
from app.core.security import generate_api_key  # noqa: E402


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest_asyncio.fixture
async def db_session(postgres_container: PostgresContainer) -> AsyncGenerator[AsyncSession, None]:
    url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_api_key(db_session: AsyncSession) -> tuple[ApiKey, str]:
    org = Organization(name=f"org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    project = Project(organization_id=org.id, name=f"project-{uuid.uuid4().hex[:8]}")
    db_session.add(project)
    await db_session.flush()

    raw_key, prefix, hashed_key = generate_api_key("gw", "test-pepper")
    api_key = ApiKey(project_id=project.id, hashed_key=hashed_key, prefix=prefix, name="test-key", scopes=[])
    db_session.add(api_key)
    await db_session.commit()
    await db_session.refresh(api_key)
    return api_key, raw_key
