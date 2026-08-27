from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_mcp_session_repo
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.user import User
from app.repositories.mcp_session_repo import McpSessionRepo
from app.schemas.mcp import McpSessionOut

router = APIRouter(prefix="/mcp/sessions", tags=["mcp_sessions"])
logger = get_logger(__name__)


@router.get("", response_model=list[McpSessionOut])
async def list_mcp_sessions(
    user: User = Depends(get_current_user), repo: McpSessionRepo = Depends(get_mcp_session_repo)
) -> list[McpSessionOut]:
    sessions = await repo.list()
    logger.info("listing MCP sessions", user_id=user.id, count=len(sessions))
    return [McpSessionOut.model_validate(s) for s in sessions]


@router.get("/{client_session_id}", response_model=McpSessionOut)
async def get_mcp_session(
    client_session_id: str,
    user: User = Depends(get_current_user),
    repo: McpSessionRepo = Depends(get_mcp_session_repo),
) -> McpSessionOut:
    logger.info("fetching MCP session", user_id=user.id, client_session_id=client_session_id)
    session = await repo.get_by_client_session_id(client_session_id)
    if session is None:
        raise NotFoundError("MCP session not found")
    return McpSessionOut.model_validate(session)
