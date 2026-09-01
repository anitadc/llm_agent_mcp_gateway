import uuid
from decimal import Decimal

from app.core.logging import get_logger
from app.db.models.cost_ledger import CostLedger
from app.db.models.enums import (
    GuardrailDirection,
    McpToolSourceType,
    ModelCapability,
    RequestStatus,
    SecretAuditStatus,
    SecretOperation,
)
from app.db.models.agent_invocation import AgentInvocation
from app.db.models.guardrail_result import GuardrailResult
from app.db.models.mcp_request_log import McpRequestLog
from app.db.models.request_log import RequestLog
from app.db.models.secret_audit_log import SecretAuditLog
from app.db.session import async_session_factory
from app.services.guardrails.base import GuardrailVerdict

logger = get_logger(__name__)


async def record_request(
    *,
    request_id: uuid.UUID,
    api_key_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
    model_alias: str,
    capability: ModelCapability,
    resolved_provider: str | None,
    resolved_model: str | None,
    status: RequestStatus,
    latency_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
    cache_hit: bool,
    cost_usd: Decimal | None,
    guardrail_verdicts: list[tuple[GuardrailDirection, GuardrailVerdict]],
) -> None:
    """Runs as a FastAPI BackgroundTask, after the response has already been sent.
    Opens its own DB session rather than reusing the request's, so it never depends
    on exactly when the request-scoped session dependency tears down."""
    async with async_session_factory() as session:
        try:
            log = RequestLog(
                request_id=request_id,
                api_key_id=api_key_id,
                user_id=user_id,
                project_id=project_id,
                organization_id=organization_id,
                model_alias=model_alias,
                capability=capability,
                resolved_provider=resolved_provider,
                resolved_model=resolved_model,
                status=status,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cache_hit=cache_hit,
            )
            session.add(log)
            await session.flush()

            if cost_usd is not None:
                session.add(
                    CostLedger(
                        request_log_id=log.id,
                        project_id=project_id,
                        organization_id=organization_id,
                        user_id=user_id,
                        cost_usd=cost_usd,
                    )
                )

            for direction, verdict in guardrail_verdicts:
                session.add(
                    GuardrailResult(
                        request_log_id=log.id,
                        direction=direction,
                        allowed=verdict.allowed,
                        violations=verdict.violations,
                    )
                )

            await session.commit()
        except Exception:
            # This runs as a BackgroundTask after the response is already sent, so
            # there is no caller left to observe a failure here -- without logging
            # it, a broken request_log/cost_ledger write would be invisible.
            logger.exception("record_request_failed", request_id=str(request_id), status=status.value)
            raise


async def record_mcp_request(
    *,
    request_id: uuid.UUID,
    api_key_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    client_session_id: str | None,
    method: str,
    tool_name: str | None,
    server_id: uuid.UUID | None,
    status: RequestStatus,
    latency_ms: int,
    execution_type: McpToolSourceType | None = None,
    api_service_id: uuid.UUID | None = None,
    endpoint_path: str | None = None,
    status_code: int | None = None,
) -> None:
    """Runs as a FastAPI BackgroundTask, same convention as record_request: its own
    DB session, after the response has already been sent to the client.
    execution_type/api_service_id/endpoint_path/status_code are only meaningful
    for a tools/call against a REST-backed tool -- see McpRequestLog's docstring."""
    async with async_session_factory() as session:
        try:
            session.add(
                McpRequestLog(
                    request_id=request_id,
                    api_key_id=api_key_id,
                    user_id=user_id,
                    project_id=project_id,
                    client_session_id=client_session_id,
                    method=method,
                    tool_name=tool_name,
                    server_id=server_id,
                    execution_type=execution_type,
                    api_service_id=api_service_id,
                    endpoint_path=endpoint_path,
                    status_code=status_code,
                    status=status,
                    latency_ms=latency_ms,
                )
            )
            await session.commit()
        except Exception:
            logger.exception("record_mcp_request_failed", request_id=str(request_id), status=status.value)
            raise


async def record_agent_invocation(
    *,
    request_id: uuid.UUID,
    api_key_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    capability: str,
    operation: str | None,
    agent_id: uuid.UUID | None,
    authorization_decision: str,
    status: RequestStatus,
    latency_ms: int,
) -> None:
    """Runs as a FastAPI BackgroundTask -- same convention as record_mcp_request:
    its own DB session, after the response has already been sent."""
    async with async_session_factory() as session:
        try:
            session.add(
                AgentInvocation(
                    request_id=request_id,
                    api_key_id=api_key_id,
                    user_id=user_id,
                    project_id=project_id,
                    capability=capability,
                    operation=operation,
                    agent_id=agent_id,
                    authorization_decision=authorization_decision,
                    status=status,
                    latency_ms=latency_ms,
                )
            )
            await session.commit()
        except Exception:
            logger.exception("record_agent_invocation_failed", request_id=str(request_id), status=status.value)
            raise


async def record_secret_audit(
    *,
    tenant_id: str | None,
    operation: SecretOperation,
    provider: str,
    secret_name: str,
    user_id: uuid.UUID | None,
    status: SecretAuditStatus,
) -> None:
    """Runs as a FastAPI BackgroundTask -- same convention as record_request/
    record_mcp_request. Deliberately takes no `value` parameter: nothing that
    could hold a secret ever reaches this function, let alone the DB row it writes."""
    async with async_session_factory() as session:
        try:
            session.add(
                SecretAuditLog(
                    tenant_id=tenant_id,
                    operation=operation,
                    provider=provider,
                    secret_name=secret_name,
                    user_id=user_id,
                    status=status,
                )
            )
            await session.commit()
        except Exception:
            # secret_name is an identifier/label (e.g. a key alias), never the secret
            # value itself -- see the docstring above -- so it is safe to log.
            logger.exception(
                "record_secret_audit_failed", operation=operation.value, provider=provider, secret_name=secret_name
            )
            raise
