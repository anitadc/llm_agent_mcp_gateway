from collections.abc import AsyncGenerator, Callable

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthError, ForbiddenError
from app.core.logging import get_logger, log_method
from app.db.models.api_key import ApiKey
from app.db.models.enums import UserRole
from app.db.models.user import User
from app.db.session import get_db
from app.db.valkey import valkey_client
from app.middleware.auth_middleware import Principal
from app.repositories.agent_approval_task_repo import AgentApprovalTaskRepo
from app.repositories.agent_invocation_repo import AgentInvocationRepo
from app.repositories.agent_repo import AgentRepo
from app.repositories.api_endpoint_repo import ApiEndpointRepo
from app.repositories.api_key_repo import ApiKeyRepo
from app.repositories.api_service_repo import ApiServiceRepo
from app.repositories.budget_repo import BudgetRepo
from app.repositories.cost_ledger_repo import CostLedgerRepo
from app.repositories.mcp_request_log_repo import McpRequestLogRepo
from app.repositories.mcp_server_repo import McpServerRepo
from app.repositories.mcp_session_repo import McpSessionRepo
from app.repositories.mcp_tool_repo import McpToolRepo
from app.repositories.model_pricing_repo import ModelPricingRepo
from app.repositories.organization_repo import OrganizationRepo
from app.repositories.project_repo import ProjectRepo
from app.repositories.project_user_repo import ProjectUserRepo
from app.repositories.provider_config_repo import ProviderConfigRepo
from app.repositories.request_log_repo import RequestLogRepo
from app.repositories.routing_rule_repo import RoutingRuleRepo
from app.repositories.access_policy_repo import AccessPolicyRepo
from app.repositories.secret_audit_log_repo import SecretAuditLogRepo
from app.repositories.tenant_identity_config_repo import TenantIdentityConfigRepo
from app.repositories.user_repo import UserRepo
from app.identity.models import UserIdentity
from app.secrets.factory import get_secret_provider
from app.secrets.service import SecretService
from app.services.agent_gateway.agent_registry_service import AgentRegistryService
from app.services.agent_gateway.approval_service import ApprovalService
from app.services.agent_gateway.invocation_service import AgentInvocationService
from app.services.api_registry.api_registry_service import ApiRegistryService
from app.services.api_registry.rest_executor import RestExecutor
from app.services.cache_service import CacheService
from app.services.cost_service import CostService
from app.services.guardrails.base import GuardrailsClient
from app.services.guardrails.http_client import HttpGuardrailsClient
from app.services.mcp.discovery_service import DiscoveryService
from app.services.mcp.health_checker import HealthChecker
from app.services.mcp.mcp_client import McpClient
from app.services.mcp.routing_engine import RoutingEngine
from app.services.mcp.session_manager import SessionManager
from app.services.policy_engine import PolicyEngine
from app.services.routing.router import GatewayRouter

logger = get_logger(__name__)

__all__ = ["get_db"]

# Viewers may discover tools but not execute them; every other role gets both.
_VIEWER_MCP_SCOPES = {"tool:read"}
_FULL_MCP_SCOPES = {"tool:read", "tool:execute"}

@log_method(logger)
def get_current_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        logger.warning("auth_missing_principal", path=request.url.path)
        raise AuthError("Missing or invalid credentials")
    return principal

@log_method(logger)
def get_current_api_key(principal: Principal = Depends(get_current_principal)) -> ApiKey:
    if principal.kind != "api_key" or principal.api_key is None:
        logger.warning("auth_wrong_principal_kind", expected="api_key", actual=principal.kind)
        raise AuthError("This endpoint requires an API key, not a user session")
    return principal.api_key

@log_method(logger)
def get_current_user(principal: Principal = Depends(get_current_principal)) -> User:
    if principal.kind != "user" or principal.user is None:
        logger.warning("auth_wrong_principal_kind", expected="user", actual=principal.kind)
        raise AuthError("This endpoint requires an Identity-Provider-authenticated user session")
    return principal.user


def get_current_identity(principal: Principal = Depends(get_current_principal)) -> UserIdentity:
    if principal.kind != "user" or principal.identity is None:
        logger.warning("auth_wrong_principal_kind", expected="user_identity", actual=principal.kind)
        raise AuthError("This endpoint requires an Identity-Provider-authenticated user session")
    return principal.identity


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    def _dependency(user: User = Depends(get_current_user)) -> User:
        from app.services.rbac_service import RBACService

        RBACService.require_role(user, *roles)
        return user

    return _dependency


def mcp_scopes_for(principal: Principal) -> set[str]:
    """API keys must carry MCP scopes explicitly (opt-in, so pre-existing keys issued
    before MCP shipped have no MCP access until re-issued with it); Keycloak users are
    granted scopes by role, since human accounts don't carry a `scopes` list."""
    if principal.kind == "api_key":
        return set(principal.api_key.scopes or [])
    return _VIEWER_MCP_SCOPES if principal.user.role == UserRole.viewer else _FULL_MCP_SCOPES


def require_mcp_scope(scope: str) -> Callable[[Principal], Principal]:
    def _dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if scope not in mcp_scopes_for(principal):
            logger.warning("mcp_scope_denied", scope=scope, principal_kind=principal.kind)
            raise ForbiddenError(f"Missing required MCP scope '{scope}'")
        return principal

    return _dependency


async def get_cache_service() -> AsyncGenerator[CacheService, None]:
    yield CacheService(valkey_client)


def get_guardrails_client(settings: Settings = Depends(get_settings)) -> GuardrailsClient:
    return HttpGuardrailsClient(settings)


def get_model_pricing_repo(db: AsyncSession = Depends(get_db)) -> ModelPricingRepo:
    return ModelPricingRepo(db)


def get_cost_service(pricing_repo: ModelPricingRepo = Depends(get_model_pricing_repo)) -> CostService:
    return CostService(pricing_repo)


def get_secret_service(settings: Settings = Depends(get_settings)) -> SecretService:
    return SecretService(get_secret_provider(settings), settings.secret_provider, settings)


def get_secret_audit_log_repo(db: AsyncSession = Depends(get_db)) -> SecretAuditLogRepo:
    return SecretAuditLogRepo(db)


def get_gateway_router(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    secret_service: SecretService = Depends(get_secret_service),
) -> GatewayRouter:
    return GatewayRouter(RoutingRuleRepo(db), ModelPricingRepo(db), RequestLogRepo(db), settings, secret_service)


def get_organization_repo(db: AsyncSession = Depends(get_db)) -> OrganizationRepo:
    return OrganizationRepo(db)


def get_project_repo(db: AsyncSession = Depends(get_db)) -> ProjectRepo:
    return ProjectRepo(db)


def get_user_repo(db: AsyncSession = Depends(get_db)) -> UserRepo:
    return UserRepo(db)


def get_project_user_repo(db: AsyncSession = Depends(get_db)) -> ProjectUserRepo:
    return ProjectUserRepo(db)


def get_api_key_repo(db: AsyncSession = Depends(get_db)) -> ApiKeyRepo:
    return ApiKeyRepo(db)


def get_provider_config_repo(db: AsyncSession = Depends(get_db)) -> ProviderConfigRepo:
    return ProviderConfigRepo(db)


def get_routing_rule_repo(db: AsyncSession = Depends(get_db)) -> RoutingRuleRepo:
    return RoutingRuleRepo(db)


def get_request_log_repo(db: AsyncSession = Depends(get_db)) -> RequestLogRepo:
    return RequestLogRepo(db)


def get_cost_ledger_repo(db: AsyncSession = Depends(get_db)) -> CostLedgerRepo:
    return CostLedgerRepo(db)


def get_budget_repo(db: AsyncSession = Depends(get_db)) -> BudgetRepo:
    return BudgetRepo(db)


def get_mcp_server_repo(db: AsyncSession = Depends(get_db)) -> McpServerRepo:
    return McpServerRepo(db)


def get_mcp_tool_repo(db: AsyncSession = Depends(get_db)) -> McpToolRepo:
    return McpToolRepo(db)


def get_mcp_session_repo(db: AsyncSession = Depends(get_db)) -> McpSessionRepo:
    return McpSessionRepo(db)


def get_mcp_request_log_repo(db: AsyncSession = Depends(get_db)) -> McpRequestLogRepo:
    return McpRequestLogRepo(db)


def get_mcp_client(settings: Settings = Depends(get_settings)) -> McpClient:
    return McpClient(settings)


def get_health_checker(
    server_repo: McpServerRepo = Depends(get_mcp_server_repo), client: McpClient = Depends(get_mcp_client)
) -> HealthChecker:
    return HealthChecker(server_repo, client)


def get_discovery_service(
    server_repo: McpServerRepo = Depends(get_mcp_server_repo),
    tool_repo: McpToolRepo = Depends(get_mcp_tool_repo),
    client: McpClient = Depends(get_mcp_client),
    health_checker: HealthChecker = Depends(get_health_checker),
) -> DiscoveryService:
    return DiscoveryService(server_repo, tool_repo, client, health_checker)


def get_routing_engine(tool_repo: McpToolRepo = Depends(get_mcp_tool_repo)) -> RoutingEngine:
    return RoutingEngine(tool_repo)


def get_session_manager(session_repo: McpSessionRepo = Depends(get_mcp_session_repo)) -> SessionManager:
    return SessionManager(session_repo)


def get_tenant_identity_config_repo(db: AsyncSession = Depends(get_db)) -> TenantIdentityConfigRepo:
    return TenantIdentityConfigRepo(db)


def get_access_policy_repo(db: AsyncSession = Depends(get_db)) -> AccessPolicyRepo:
    return AccessPolicyRepo(db)


def get_policy_engine(repo: AccessPolicyRepo = Depends(get_access_policy_repo)) -> PolicyEngine:
    return PolicyEngine(repo)


def get_api_service_repo(db: AsyncSession = Depends(get_db)) -> ApiServiceRepo:
    return ApiServiceRepo(db)


def get_api_endpoint_repo(db: AsyncSession = Depends(get_db)) -> ApiEndpointRepo:
    return ApiEndpointRepo(db)


def get_rest_executor(secret_service: SecretService = Depends(get_secret_service)) -> RestExecutor:
    return RestExecutor(secret_service)


def get_api_registry_service(
    service_repo: ApiServiceRepo = Depends(get_api_service_repo),
    endpoint_repo: ApiEndpointRepo = Depends(get_api_endpoint_repo),
    tool_repo: McpToolRepo = Depends(get_mcp_tool_repo),
    executor: RestExecutor = Depends(get_rest_executor),
) -> ApiRegistryService:
    return ApiRegistryService(service_repo, endpoint_repo, tool_repo, executor)


def get_agent_repo(db: AsyncSession = Depends(get_db)) -> AgentRepo:
    return AgentRepo(db)


def get_agent_approval_task_repo(db: AsyncSession = Depends(get_db)) -> AgentApprovalTaskRepo:
    return AgentApprovalTaskRepo(db)


def get_agent_invocation_repo(db: AsyncSession = Depends(get_db)) -> AgentInvocationRepo:
    return AgentInvocationRepo(db)


def get_agent_registry_service(agent_repo: AgentRepo = Depends(get_agent_repo)) -> AgentRegistryService:
    return AgentRegistryService(agent_repo)


def get_approval_service(
    agent_repo: AgentRepo = Depends(get_agent_repo),
    task_repo: AgentApprovalTaskRepo = Depends(get_agent_approval_task_repo),
    settings: Settings = Depends(get_settings),
) -> ApprovalService:
    return ApprovalService(agent_repo, task_repo, settings.agent_approval_stages)


def get_agent_invocation_service(
    agent_repo: AgentRepo = Depends(get_agent_repo),
    secret_service: SecretService = Depends(get_secret_service),
    settings: Settings = Depends(get_settings),
) -> AgentInvocationService:
    return AgentInvocationService(agent_repo, secret_service, settings)
