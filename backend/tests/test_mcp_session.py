import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.mcp_session_repo import McpSessionRepo
from app.services.mcp.session_manager import SessionManager


@pytest.mark.asyncio
async def test_get_or_create_mints_a_new_session_when_none_given(db_session: AsyncSession) -> None:
    manager = SessionManager(McpSessionRepo(db_session))

    session, created = await manager.get_or_create(None, project_id=None, api_key_id=None)
    await db_session.commit()

    assert created is True
    assert session.client_session_id


@pytest.mark.asyncio
async def test_same_client_session_id_always_returns_same_session(db_session: AsyncSession) -> None:
    manager = SessionManager(McpSessionRepo(db_session))
    first, created_first = await manager.get_or_create(None, project_id=None, api_key_id=None)
    await db_session.commit()

    second, created_second = await manager.get_or_create(first.client_session_id, project_id=None, api_key_id=None)

    assert created_second is False
    assert second.id == first.id


@pytest.mark.asyncio
async def test_server_session_mapping_is_consistent_across_calls(db_session: AsyncSession) -> None:
    manager = SessionManager(McpSessionRepo(db_session))
    session, _ = await manager.get_or_create(None, project_id=None, api_key_id=None)
    await db_session.commit()
    server_a = uuid.uuid4()
    server_b = uuid.uuid4()

    await manager.record_server_session(session, server_a, "session-for-a")
    await manager.record_server_session(session, server_b, "session-for-b")
    await db_session.commit()

    reloaded = await manager.get(session.client_session_id)

    assert manager.get_server_session_id(reloaded, server_a) == "session-for-a"
    assert manager.get_server_session_id(reloaded, server_b) == "session-for-b"


@pytest.mark.asyncio
async def test_unknown_server_has_no_recorded_session(db_session: AsyncSession) -> None:
    manager = SessionManager(McpSessionRepo(db_session))
    session, _ = await manager.get_or_create(None, project_id=None, api_key_id=None)
    await db_session.commit()

    assert manager.get_server_session_id(session, uuid.uuid4()) is None
