from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "llm-gateway"
    environment: Literal["local", "staging", "prod"] = "local"
    log_level: str = "INFO"

    database_url: str

    valkey_url: str
    cache_ttl_seconds: int = 300
    rate_limit_window_seconds: int = 60

    # --- Identity Provider layer (app/identity/) ---
    # Keycloak remains the default; its own settings below double as
    # KeycloakProvider's config (kept under their existing names/env vars --
    # KEYCLOAK_BASE_URL, not the prompt's KEYCLOAK_URL -- to avoid a breaking
    # rename of already-deployed config). *_client_secret fields are reserved for
    # future confidential-client flows (introspection, client-credentials) --
    # today's validation is JWKS-only and doesn't need them -- and are resolved
    # via the Secret Provider layer (`{PROVIDER}_CLIENT_SECRET`), never a plain
    # env var here, mirroring every other credential in this app. See
    # docs/identity-provider-architecture.md.
    identity_provider: Literal["keycloak", "entra", "auth0", "okta", "aws_identity", "google"] = "keycloak"

    keycloak_base_url: str
    keycloak_realm: str
    keycloak_client_id: str
    keycloak_jwks_url: str = ""
    keycloak_audience: str

    entra_tenant_id: str | None = None
    entra_client_id: str | None = None

    auth0_domain: str | None = None
    auth0_client_id: str | None = None
    auth0_audience: str | None = None
    # Auth0 has no standard roles/groups claim -- RBAC rules typically inject
    # them into a namespaced custom claim the tenant configures themselves.
    auth0_roles_claim: str = "https://llm-gateway/roles"
    auth0_groups_claim: str = "https://llm-gateway/groups"

    okta_domain: str | None = None
    okta_client_id: str | None = None
    okta_audience: str = "api://default"

    # A distinct setting from aws_region_name (Bedrock) / aws_secrets_region
    # (Secrets Manager) -- a real deployment may run IAM Identity Center in a
    # different region than either.
    aws_sso_region: str | None = None
    aws_sso_instance_arn: str | None = None

    google_client_id: str | None = None
    # Restricts sign-in to a single Google Workspace domain (the `hd` claim) --
    # unset means any Google Account is accepted.
    google_workspace_domain: str | None = None

    guardrails_base_url: str
    guardrails_timeout_seconds: float = 5.0

    # Non-secret provider config (region isn't a credential); the credentials
    # themselves (OPENAI_API_KEY, ANTHROPIC_API_KEY, AWS_ACCESS_KEY_ID/SECRET_ACCESS_KEY,
    # ...) are never read from env/Settings -- they're always resolved at call time
    # through the pluggable Secret Provider layer (app/secrets/). See
    # docs/secret-management.md.
    aws_region_name: str | None = None

    api_key_prefix: str = "gw"
    api_key_secret_pepper: str

    # --- Secret Provider layer (app/secrets/) ---
    secret_provider: Literal["postgres", "aws", "gcp", "azure", "vault"] = "postgres"
    # Redis/Valkey cache TTL for resolved secret values -- bounds how long a
    # provider outage or a rotated-but-not-yet-invalidated value can linger.
    secret_cache_ttl_seconds: int = 300

    # Fernet key (Fernet.generate_key()) encrypting values stored by
    # PostgresSecretProvider -- required only when secret_provider="postgres".
    # Never derived from another secret here: rotating this key independently
    # of everything else is exactly the point.
    secret_storage_encryption_key: str | None = None

    aws_secrets_region: str | None = None
    aws_secret_name_prefix: str = "llm-gateway"

    gcp_project_id: str | None = None

    azure_keyvault_name: str | None = None

    vault_addr: str | None = None
    vault_token: str | None = None
    vault_mount_point: str = "secret"

    mcp_protocol_version: str = "2025-06-18"
    mcp_client_timeout_seconds: float = 10.0
    # 0 disables the periodic background refresh; discovery is still available on-demand
    # via the manual sync API either way.
    mcp_discovery_refresh_seconds: int = 300
    # Health checks are cheap (just `initialize`), so they run far more often than a
    # full tool-discovery sync. 0 disables the periodic loop; POST
    # /mcp/servers/{id}/health-check is still available on-demand either way.
    mcp_health_check_interval_seconds: int = 30
    mcp_default_rate_limit_per_window: int = 60

    # Agent Gateway (MVP) -- comma-separated stage names, evaluated against
    # AgentApprovalStage; "production" is additionally always required whenever
    # an agent's risk_class is "high", regardless of this list -- see
    # services/agent_gateway/approval_service.py. Configuration-driven per
    # docs/agent-gateway.md, never hard-coded per agent.
    agent_approval_stages: str = "security,technical,business"
    agent_invocation_timeout_seconds: float = 10.0
    agent_default_rate_limit_per_window: int = 60
    # How long a caller-supplied Idempotency-Key on POST /v1/agent-invocations is
    # remembered before a repeat with the same key is treated as a fresh call.
    agent_idempotency_ttl_seconds: int = 86400
    # SLA deadline stamped on every AgentApprovalTask at creation, and how often the
    # background sweep checks for overdue ones. Either set to 0 disables the sweep
    # loop entirely -- same on/off convention as the MCP background loops below.
    agent_approval_sla_hours: int = 48
    agent_approval_sla_sweep_interval_seconds: int = 3600
    # 0 disables the periodic liveness loop; POST /v1/agents/{id}/health-check is
    # still available on-demand either way -- mirrors mcp_health_check_interval_seconds.
    agent_health_check_interval_seconds: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def derive_jwks_url(self) -> "Settings":
        if not self.keycloak_jwks_url:
            self.keycloak_jwks_url = (
                f"{self.keycloak_base_url}/realms/{self.keycloak_realm}"
                "/protocol/openid-connect/certs"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
