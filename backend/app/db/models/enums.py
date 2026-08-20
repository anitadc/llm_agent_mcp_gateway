import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    team_lead = "team_lead"
    developer = "developer"
    viewer = "viewer"


class ProviderNameEnum(str, enum.Enum):
    openai = "openai"
    anthropic = "anthropic"
    bedrock = "bedrock"


class RoutingStrategy(str, enum.Enum):
    priority = "priority"
    cost = "cost"
    latency = "latency"


class ModelCapability(str, enum.Enum):
    chat = "chat"
    embedding = "embedding"


class RequestStatus(str, enum.Enum):
    success = "success"
    error = "error"
    blocked = "blocked"
    rate_limited = "rate_limited"


class BudgetPeriod(str, enum.Enum):
    daily = "daily"
    monthly = "monthly"


class GuardrailDirection(str, enum.Enum):
    prompt = "prompt"
    response = "response"


class McpSyncStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    error = "error"


class McpTransportType(str, enum.Enum):
    http = "http"


class McpServerStatus(str, enum.Enum):
    """Administrative on/off switch, set by an operator -- independent of
    health_status, which reflects whether the server is actually reachable."""

    active = "active"
    inactive = "inactive"


class McpHealthStatus(str, enum.Enum):
    """Liveness as observed by the last probe (HealthChecker.probe) -- unknown until
    the first probe has run."""

    unknown = "unknown"
    healthy = "healthy"
    unhealthy = "unhealthy"


class SecretOperation(str, enum.Enum):
    get = "get"
    set = "set"
    delete = "delete"
    rotate = "rotate"


class SecretAuditStatus(str, enum.Enum):
    success = "success"
    error = "error"


class IdentityProviderName(str, enum.Enum):
    keycloak = "keycloak"
    entra = "entra"
    auth0 = "auth0"
    okta = "okta"
    aws_identity = "aws_identity"
    google = "google"


class McpToolSourceType(str, enum.Enum):
    """Discriminates what a mcp_tools row actually executes against -- an MCP
    server (the original registry) or a registered REST API endpoint (the API
    Registry). RoutingEngine and mcp_gateway.py branch on this to decide which
    executor handles a `tools/call`."""

    mcp = "mcp"
    rest = "rest"


class ApiServiceStatus(str, enum.Enum):
    """Administrative on/off switch for a registered REST API, mirroring
    McpServerStatus -- independent of any liveness concept (REST services have
    no MCP-style `initialize` probe, so there is no health_status axis here)."""

    active = "active"
    inactive = "inactive"


class RestAuthType(str, enum.Enum):
    none = "none"
    api_key = "api_key"
    bearer = "bearer"
    basic = "basic"
    oauth2_client_credentials = "oauth2_client_credentials"


class RestHttpMethod(str, enum.Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class AgentLifecycleStatus(str, enum.Enum):
    """Agent Gateway registration lifecycle (see services/agent_gateway/lifecycle.py
    for the allowed transition table). Registration alone never implies
    authorization -- only `active` agents are ever routable, and even then every
    invocation is separately gated by the PolicyEngine, same as MCP tools."""

    draft = "draft"
    submitted = "submitted"
    validating = "validating"
    under_review = "under_review"
    approved = "approved"
    published = "published"
    active = "active"
    suspended = "suspended"
    deprecated = "deprecated"
    retired = "retired"
    rejected = "rejected"


class AgentRiskClass(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class AgentTrustLevel(str, enum.Enum):
    """T0-T5 from the Agent Gateway trust model. Trust is an input to
    authorization/route eligibility, never a substitute for it -- the
    PolicyEngine gate still applies regardless of trust level."""

    t0_unknown = "t0_unknown"
    t1_registered_internal = "t1_registered_internal"
    t2_enterprise_trusted = "t2_enterprise_trusted"
    t3_privileged = "t3_privileged"
    t4_approved_external_partner = "t4_approved_external_partner"
    t5_public_untrusted = "t5_public_untrusted"


class AgentApprovalStage(str, enum.Enum):
    security = "security"
    technical = "technical"
    business = "business"
    data_governance = "data_governance"
    production = "production"


class AgentApprovalDecision(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
