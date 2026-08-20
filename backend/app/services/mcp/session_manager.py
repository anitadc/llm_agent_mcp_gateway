import uuid

from app.db.models.mcp_session import McpSession
from app.repositories.mcp_session_repo import McpSessionRepo


class SessionManager:
    """Maintains client_session_id -> {server_id: server_session_id}, so a given
    client session is always routed back to the same server-side session on every
    subsequent call to a stateful MCP server."""

    def __init__(self, session_repo: McpSessionRepo) -> None:
        self.session_repo = session_repo

    async def get_or_create(
        self,
        client_session_id: str | None,
        project_id: uuid.UUID | None,
        api_key_id: uuid.UUID | None,
    ) -> tuple[McpSession, bool]:
        if client_session_id:
            existing = await self.session_repo.get_by_client_session_id(client_session_id)
            if existing is not None:
                return existing, False
        session = McpSession(
            client_session_id=client_session_id or str(uuid.uuid4()),
            project_id=project_id,
            api_key_id=api_key_id,
            server_sessions={},
        )
        return await self.session_repo.add(session), True

    async def get(self, client_session_id: str) -> McpSession | None:
        return await self.session_repo.get_by_client_session_id(client_session_id)

    @staticmethod
    def get_server_session_id(session: McpSession, server_id: uuid.UUID) -> str | None:
        return session.server_sessions.get(str(server_id))

    async def record_server_session(
        self, session: McpSession, server_id: uuid.UUID, server_session_id: str | None
    ) -> None:
        if server_session_id is None or session.server_sessions.get(str(server_id)) == server_session_id:
            return
        # Reassign (not mutate-in-place) so SQLAlchemy's change tracking sees a new
        # dict object on this plain JSONB column.
        session.server_sessions = {**session.server_sessions, str(server_id): server_session_id}
        await self.session_repo.db.flush()
