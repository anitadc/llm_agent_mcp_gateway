# Architecture

This is the system-level architecture reference. For the full functional
requirements see [REQUIREMENT.md](REQUIREMENT.md); for coding conventions
see [../CLAUDE.md](../CLAUDE.md); for the secret layer specifically see
[secret-management.md](secret-management.md); for the identity layer see
[identity-provider-architecture.md](identity-provider-architecture.md); for
exposing REST APIs as MCP tools see [api-registry.md](api-registry.md); for
the Agent Gateway (agent registry, approvals, governed invocation) see
[agent-gateway.md](agent-gateway.md).

## System overview

```
                              ┌──────────────────────────────┐
   Apps / Human users ──────▶ │                              │
   AI Agents          ──────▶ │   Gateway Backend (FastAPI)   │
                              │                              │
                              │  /v1/chat/completions        │──▶ OpenAI / Anthropic / Bedrock
                              │  /v1/embeddings               │      (embedded LiteLLM Router)
                              │  /mcp              (JSON-RPC) │──▶ Registered MCP servers
                              │  /mcp/servers, /mcp/tools      │      (Streamable HTTP), or
                              │  /mcp/api-services              │      registered REST APIs
                              │  /admin/secrets/*              │──▶ Infisical / AWS / GCP /
                              │  /admin/identity/*             │      Azure / Vault
                              │  /v1/{orgs,projects,users,     │──▶ Keycloak / Entra / Auth0 /
                              │   keys,routing-rules,budgets,  │      Okta / AWS Identity Center /
                              │   provider-configs,usage,logs} │      Google (whichever is active)
                              └───────────────┬───────────────┘
                                              │
              ┌────────────────┬──────────────┼──────────────┬───────────────────┐
              ▼                ▼              ▼              ▼                   ▼
         PostgreSQL      Valkey/Redis   Identity backend  Guardrails         Secret backend
    (all persistent    (rate limits,   (Keycloak default,   service          (Infisical/AWS/GCP/
     state EXCEPT       response       or Entra/Auth0/     (prompt/          Azure/Vault --
     secret values --    cache,        Okta/AWS Identity    response         see below)
     see below)          secret cache)  Center/Google)       policy checks)
```

A React + Tailwind admin UI (`frontend/`) is a thin client over this API — every
decision (RBAC, routing, cost, secret access) is enforced server-side, never in
the browser.

## Request lifecycle

Every request, regardless of endpoint:

```
request_id middleware → CORS → auth middleware (API key OR Identity Provider
    token -- resolved by the Identity Provider Factory, see below)
    → rate-limit middleware → router handler → (BackgroundTask: logging/cost, after response sent)
```

### Chat / Embeddings

```
auth → prompt guardrail check → cache lookup (hit? return, $0, no routing) →
resolve model_alias -> provider targets (routing_rules) → build a LiteLLM Router,
resolving each target's credentials through the Secret Provider layer →
provider call → response guardrail check (chat only) → cost calc → cache write →
BackgroundTask: request_logs + cost_ledger + guardrail_results
```

### MCP (`POST /mcp`)

```
auth → scope check (tool:read / tool:execute) → [tools/call only] policy check
(role/idp/tool_name) → per-tool rate limit → resolve tool via the Tool Registry
(source_type: mcp | rest) →
  mcp:  gated on the owning server being administratively active AND currently
        healthy → resolve/establish a per-server session → forward to the MCP
        server (outbound auth via an env var named by its registry entry)
  rest: gated on the owning API service being administratively active →
        per-API-service rate limit → RestExecutor builds and sends the HTTP
        call (outbound auth resolved through the Secret Provider layer) →
        response converted to MCP content, non-2xx returned as isError=true,
        not a gateway failure
→ BackgroundTask: mcp_request_logs
```

See [api-registry.md](api-registry.md) for the REST-backed path in full.

### Secret resolution (used inside both of the above)

```
SecretService.get_secret(name) → Redis cache hit? return → miss: SecretProvider
(whichever one SECRET_PROVIDER selects) → cache the result (TTL) → return
```

See [secret-management.md](secret-management.md) for the full picture.

### Identity resolution (the auth middleware step above, expanded)

```
Bearer token → peek unverified `iss` claim → tenant_identity_config match?
  yes: build a provider from that tenant's stored config
  no:  use the global IDENTITY_PROVIDER default
→ selected IdentityProvider.get_user_identity(token) (JWKS-validated) →
UserIdentity → AuthService.sync_user_from_identity → internal User row →
Principal(kind="user", user=User, identity=UserIdentity)
```

See [identity-provider-architecture.md](identity-provider-architecture.md) for the full picture.

## The five governed subsystems

| Subsystem | Owns | Does NOT own |
|---|---|---|
| **LLM Gateway** (`api/v1/chat.py`, `embeddings.py`, `services/routing/`) | Provider routing/failover, guardrails, cost, caching | Which credential a provider target uses (delegates to the Secret Provider layer); tool execution |
| **MCP Gateway** (`api/v1/mcp_*.py`, `api/v1/api_services.py`, `services/mcp/`, `services/api_registry/`) | The MCP Server Registry AND the API (REST) Service Registry, tool discovery/registration, health, sessions, per-tool auth/rate-limits, REST execution | *Deciding* which tool to call (that's an external agent's job — see below); credential storage for MCP servers' own outbound auth (delegates to the Secret Provider layer, unlike REST tool credentials which already do) |
| **Agent Gateway (MVP)** (`api/v1/agents.py`, `api/v1/agent_invocations.py`, `services/agent_gateway/`) | Agent Registry, approval workflow, trust levels, and governed `REMOTE_HTTP` invocation dispatched by capability — see [agent-gateway.md](agent-gateway.md) | Real A2A protocol compliance, the LangGraph same-process boundary, and a Python SDK — all documented Future Capability |
| **Secret Provider layer** (`app/secrets/`) | Resolving a named secret's current value, from exactly one pluggable backend | Any opinion about what a secret is *for* — it doesn't know "OPENAI_API_KEY" is special, callers just ask for it by name |
| **Identity Provider layer** (`app/identity/`) | Validating a bearer token and mapping it to a provider-agnostic `UserIdentity` (roles/groups/tenant), from exactly one pluggable IdP per tenant | Machine-to-machine auth (API keys are a separate, deliberately simpler mechanism); *what* a role/group is allowed to do (that's `services/policy_engine.py`'s job, which consumes `UserIdentity` but is itself IdP-agnostic) |

### Why the LLM Gateway, MCP Gateway, and Agent Gateway don't call each other

There is no in-process orchestration loop in this codebase. An AI agent that
needs several tool calls to accomplish a task alternates between the gateways
itself, one HTTP call at a time — `POST /mcp {method:"tools/list"}` to
discover, `POST /v1/chat/completions` to decide what to do next, `POST /mcp
{method:"tools/call"}` to execute, repeat. The Agent Gateway follows the same
rule: `POST /v1/agent-invocations` is a governed dispatch a caller invokes
explicitly by capability, not a mechanism this platform uses to autonomously
chain calls across the other two gateways. None of the three is aware the
others exist. This is a deliberate boundary, not a missing feature — see
[FAQ.md](FAQ.md) for the full walkthrough of the LLM/MCP flow, and
[agent-gateway.md](agent-gateway.md) for the Agent Gateway's own scope
boundaries.

## Data model (by subsystem)

| Subsystem | Tables |
|---|---|
| Tenancy / access | `organizations`, `projects`, `users`, `project_users`, `api_keys` |
| LLM routing/cost | `provider_configs`, `model_pricing`, `routing_rules`, `request_logs`, `guardrail_results`, `cost_ledger`, `budgets` |
| MCP | `mcp_servers`, `mcp_tools`, `mcp_sessions`, `mcp_request_logs` |
| API Registry (REST-as-MCP) | `api_services`, `api_endpoints` -- see [api-registry.md](api-registry.md) |
| Agent Gateway (MVP) | `agents`, `agent_approval_tasks`, `agent_invocations` -- see [agent-gateway.md](agent-gateway.md) |
| Secrets | `secret_audit_log` (metadata only — **no table anywhere in this schema stores a secret value**) |
| Identity | `tenant_identity_config` (per-tenant IdP selection), `access_policies` (RBAC/ABAC gate) |

Every schema change ships as an Alembic migration (`backend/alembic/versions/`) —
never a hand-edited `ALTER TABLE`.

## Deployment

- **Local/dev:** `docker compose up --build` brings up Postgres, Valkey, Keycloak
  (pre-seeded realm), a mock Guardrails service, the backend, and the frontend.
  See [../README.md](../README.md) for the full walkthrough.
- **Secret backend:** configured independently of the app stack via
  `SECRET_PROVIDER` + that provider's own env vars — see
  [secret-management.md](secret-management.md#deployment-patterns) for
  per-provider notes (AWS IAM roles, GCP ADC, Azure managed identity, Vault auth
  methods).
- **Identity backend:** configured independently via `IDENTITY_PROVIDER` +
  that provider's own env vars — Keycloak (bundled in `docker-compose.yml` for
  local dev) is the default; see
  [identity-provider-architecture.md](identity-provider-architecture.md#configuration)
  for the other five.
- **Not yet included:** Kubernetes manifests, a CI pipeline, a self-hosted
  Infisical stack (this repo assumes Infisical Cloud or an already-running
  self-hosted instance, referenced only by URL).

## Known architectural boundaries (see REQUIREMENT.md §11 for the full list)

- No true token streaming (chat completions or MCP tool responses both buffer
  the full response).
- No hard budget enforcement — budgets are visible/advisory only.
- No encrypted-at-rest secret values in this app's own database — there are none;
  values live only in the configured secret backend and a short-lived Redis
  cache (see [secret-management.md](secret-management.md#security-model)).
- Tenant-scoped LLM routing credentials (per-tenant BYO provider keys) are
  supported by the Secret Provider layer's `tenant` parameter but not yet wired
  through `GatewayRouter` for live chat/embeddings traffic.
- `AccessPolicy.max_tokens` is stored/returned by the admin API but not yet
  enforced against an actual request (see
  [identity-provider-architecture.md](identity-provider-architecture.md)'s
  RBAC/ABAC section) — same advisory-only treatment as `Budget`.
- Policy enforcement (RBAC/ABAC) is wired into `POST /mcp`'s `tools/call` path
  for IdP-authenticated human callers only — `chat.py`/`embeddings.py` remain
  API-key-only by prior deliberate design and are not gated by `AccessPolicy`.
  `AccessPolicy.allowed_tool_names` extends this to gate specific tools (MCP-
  or REST-backed alike), but evaluation stops at the tool name — it does not
  inspect the call's actual arguments (see [api-registry.md](api-registry.md)'s
  scope notes).
