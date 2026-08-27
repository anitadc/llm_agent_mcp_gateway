# AI Gateway (LLM Gateway + MCP Gateway)

A self-hosted middleware layer that sits between your internal applications/agents and:

- **Multiple LLM providers** (OpenAI, Anthropic, AWS Bedrock) — via an OpenAI-compatible `/v1/chat/completions` and `/v1/embeddings` API, with auth, RBAC, rate limiting, guardrails, cost tracking, and automatic provider failover.
- **Multiple MCP (Model Context Protocol) servers** — via a single `POST /mcp` JSON-RPC endpoint, with a dynamic **MCP Server Registry**, tool discovery, health checking, session management, and per-tool authorization.
- **Enterprise REST APIs exposed as MCP tools** — the **API Registry** lets you register a plain REST API and its endpoints, each of which is instantly callable as an ordinary MCP tool through the same `POST /mcp` endpoint — no MCP server required, and agents can't tell (or need to tell) the difference.
- **Pluggable secret management** — provider API keys are never stored in this app's own config; they're resolved at call time through a swappable Secret Provider layer (Infisical by default, or AWS/GCP/Azure/Vault).
- **Pluggable identity providers** — human (dashboard/admin) authentication isn't tied to any one IdP; Keycloak is the default, with Microsoft Entra ID, Auth0, Okta, AWS IAM Identity Center, and Google Identity also supported, including per-tenant overrides.

This document is about *how to run and use* the application. For the internal architecture and conventions, see [CLAUDE.md](CLAUDE.md). For the secret provider layer specifically, see [docs/secret-management.md](docs/secret-management.md); for the identity provider layer, see [docs/identity-provider-architecture.md](docs/identity-provider-architecture.md); for exposing REST APIs as MCP tools, see [docs/api-registry.md](docs/api-registry.md); for the full system architecture, see [docs/architecture.md](docs/architecture.md). For architecture-review-grade design documents, see [doc/HLD.md](doc/HLD.md) (High Level Design) and [doc/LLD.md](doc/LLD.md) (Low Level Design); for customer-facing pitch material, see [doc/HPITCH.md](doc/HPITCH.md) and [doc/LPITCH.md](doc/LPITCH.md).

---

## 1. Architecture at a glance

```
                         ┌────────────────────────────┐
   Apps / Users ───────▶ │  Gateway Backend (FastAPI)  │
   AI Agents    ───────▶ │  /v1/chat/completions       │──▶ OpenAI / Anthropic / Bedrock
                         │  /v1/embeddings             │
                         │  /mcp  (JSON-RPC)           │──▶ Registered MCP servers, or
                         │  /mcp/servers, /mcp/tools    │      registered REST APIs (API Registry)
                         │  /mcp/api-services           │
                         └──────────┬──────────────────┘
                                    │
                 ┌──────────────────┼───────────────────┬───────────────┐
                 ▼                  ▼                    ▼               ▼
             PostgreSQL          Valkey (Redis)       Keycloak       Guardrails service
        (orgs/projects/keys/   (rate limits,      (human user auth,  (prompt/response
         routing/costs/logs/    response cache)     RBAC roles)        policy checks)
         MCP/API registries)
```

A React + Tailwind admin UI (`frontend/`) covers everything above: API keys, usage/cost, request logs, routing rules, budgets, provider configs, and the full MCP Gateway (server registry, API Registry for REST-backed tools, tools explorer, JSON-RPC playground, session viewer).

---

## 2. Prerequisites

- Docker + Docker Compose (recommended, fastest path)
- For local (non-Docker) development: Python 3.12+, Node.js 20+, and access to a Postgres 16 + Valkey/Redis instance

---

## 3. Quickstart — everything via Docker Compose

This brings up Postgres, Valkey, Keycloak (pre-seeded with a `gateway` realm), a mock Guardrails service, the backend, and the frontend.

```bash
docker compose up --build
```

Default ports (override via the env vars shown, e.g. in a root `.env` file):

| Service | Container port | Host port (default) | Env var to override |
|---|---|---|---|
| Postgres | 5432 | 5433 | `POSTGRES_HOST_PORT` |
| Valkey | 6379 | 6390 | `VALKEY_HOST_PORT` |
| Keycloak | 8080 | 8180 | `KEYCLOAK_HOST_PORT` |
| Guardrails mock | 9000 | 9100 | `GUARDRAILS_HOST_PORT` |
| Gateway backend | 8000 | 8010 | `BACKEND_HOST_PORT` |
| Gateway frontend | 5173 | 5173 | `FRONTEND_HOST_PORT` |

The backend container runs `alembic upgrade head` automatically before starting `uvicorn`, so the database schema is always up to date on boot.

Once healthy:

- **Frontend UI**: http://localhost:5173
- **Backend Swagger UI**: http://localhost:8010/docs
- **Backend health**: http://localhost:8010/health and http://localhost:8010/ready (checks DB, Valkey, Keycloak, Guardrails)
- **Keycloak admin console**: http://localhost:8180 (admin / admin)

Provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...) are **not** set as env vars on this stack — they're resolved at call time through the Secret Provider layer (Infisical by default). Point `SECRET_PROVIDER` and its provider-specific vars at your secret backend before `docker compose up` (or in a root `.env`) — see [docs/secret-management.md](docs/secret-management.md). `API_KEY_SECRET_PEPPER` (this gateway's own API-key hashing pepper, unrelated to LLM provider credentials) and `AWS_REGION_NAME` are still plain env vars.

To stop everything: `docker compose down` (add `-v` to also drop the Postgres volume).

---

## 4. Local development (hot reload)

Run infra in Docker, run backend/frontend directly on your machine for fast iteration:

```bash
docker compose up postgres valkey keycloak guardrails-mock
```

### Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env               # fill in provider keys, DB/Valkey/Keycloak URLs
alembic upgrade head                # apply migrations
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Point `.env`'s `DATABASE_URL` / `VALKEY_URL` / `KEYCLOAK_BASE_URL` / `GUARDRAILS_BASE_URL` at the Docker-Compose host ports above (e.g. `postgresql+asyncpg://gateway:gateway@localhost:5433/gateway`).

Swagger UI: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev      # Vite dev server on :5173, proxies /api -> localhost:8000
```

Create a `frontend/.env` with:

```
VITE_API_BASE=http://localhost:8000
VITE_KEYCLOAK_URL=http://localhost:8180
VITE_KEYCLOAK_REALM=gateway
VITE_KEYCLOAK_CLIENT_ID=gateway-frontend
```

### Tests

```bash
cd backend && pytest
```

Most tests spin up a real Postgres via `testcontainers`, so a running Docker daemon is required for the DB-backed suites (`test_routing.py`, `test_mcp_discovery.py`, `test_mcp_routing.py`, `test_mcp_session.py`, `test_mcp_health_checker.py`). The pure-unit suites (`test_auth.py`, `test_chat.py`, `test_guardrails.py`, `test_mcp_client.py`) run without Docker.

---

## 5. First-time setup

The UI ships with one seeded Keycloak admin user: **`admin@gateway.local` / `admin123`** (realm `gateway`). Sign in at http://localhost:5173 — you'll be redirected to Keycloak's hosted login page, then back to the dashboard.

Everything below can be done either from the UI or via the REST API. The REST walkthrough (useful for scripting/CI) is:

### 5.1 Get an admin bearer token

```bash
TOKEN=$(curl -s -X POST http://localhost:8180/realms/gateway/protocol/openid-connect/token \
  -d grant_type=password -d client_id=gateway-frontend \
  -d username=admin@gateway.local -d password=admin123 | jq -r .access_token)
```

### 5.2 Create an organization and project

```bash
ORG_ID=$(curl -s -X POST http://localhost:8010/v1/organizations \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Acme Corp"}' | jq -r .id)

PROJECT_ID=$(curl -s -X POST http://localhost:8010/v1/projects \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"organization_id\": \"$ORG_ID\", \"name\": \"Default Project\"}" | jq -r .id)
```

### 5.3 Issue an API key

API keys authenticate machine clients (apps, agents) for `/v1/chat/completions`, `/v1/embeddings`, and `/mcp`. Include `tool:read`/`tool:execute` in `scopes` if this key needs MCP access.

```bash
API_KEY=$(curl -s -X POST http://localhost:8010/v1/keys \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"name\": \"dev-key\", \"project_id\": \"$PROJECT_ID\", \"scopes\": [\"tool:read\", \"tool:execute\"]}" \
  | jq -r .raw_key)
```

> The raw key (`gw_...`) is only ever returned once, at creation time — store it now.

---

## 6. Using the LLM Gateway

Chat/embedding calls are routed by **model alias**, not by provider name directly — you first need a routing rule mapping an alias to one or more real provider/model targets (with a fallback order or strategy). Do this once per alias:

```bash
curl -X POST http://localhost:8010/v1/routing-rules \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "model_alias": "gateway-fast",
    "capability": "chat",
    "strategy": "priority",
    "targets": [{"provider": "openai", "model": "gpt-4o-mini", "weight": 1}],
    "priority": 100
  }'
```

(This requires `OPENAI_API_KEY` — or the corresponding provider key — to resolve successfully through the Secret Provider layer for the actual completion call to succeed; see [docs/secret-management.md](docs/secret-management.md). `GET /admin/secrets/status` and the **Secrets** admin page show whether each provider's credential currently resolves, without ever exposing the value.)

Then call it exactly like the OpenAI API, using your API key:

```bash
curl -X POST http://localhost:8010/v1/chat/completions \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{
    "model": "gateway-fast",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

Embeddings work the same way against `/v1/embeddings`, using a routing rule with `"capability": "embedding"`.

The UI's **Usage & Cost** and **Request Logs** pages show cost attribution and guardrail/cache/latency details for every call.

---

## 7. Using the MCP Gateway

Agents never call MCP servers directly — they only ever call this gateway's `POST /mcp`. The gateway owns discovery, routing, session continuity, and per-server auth.

### 7.1 Register an MCP server (registry)

```bash
curl -X POST http://localhost:8010/mcp/servers \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "threat-intel",
    "base_url": "http://threat-intel-mcp:9000/mcp",
    "auth_config": {"type": "none"}
  }'
```

For a server that needs outbound auth, set `auth_config` to `{"type": "bearer", "credential_ref": "MCP_THREAT_INTEL_TOKEN"}` (bearer token) or `{"type": "api_key", "credential_ref": "MCP_THREAT_INTEL_KEY", "header_name": "X-API-Key"}` — `credential_ref` names an **environment variable on the backend** holding the actual secret; the raw secret itself is never stored in the database.

### 7.2 Discover tools

```bash
curl -X POST http://localhost:8010/mcp/tools/sync -H "Authorization: Bearer $TOKEN"
```

This calls `initialize` + `tools/list` on every active, healthy server in the registry and rebuilds the central `tool_name → server` map. It also runs automatically on a timer (`MCP_DISCOVERY_REFRESH_SECONDS`, default 300s), alongside a faster liveness-only health-check loop (`MCP_HEALTH_CHECK_INTERVAL_SECONDS`, default 30s).

### 7.3 List available tools

```bash
curl http://localhost:8010/mcp/tools -H "Authorization: Bearer $API_KEY"
```

Only tools whose owning server is **active** (administratively enabled) and **healthy** (last probe succeeded) are returned — the same filter the gateway itself uses when routing a call.

### 7.4 Call a tool

```bash
curl -X POST http://localhost:8010/mcp \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "tools/call",
    "params": {"name": "get_top_threats", "arguments": {}}
  }'
```

Add an `Mcp-Session-Id` header (echoed back in the response headers) to keep a stateful session pinned to the same per-server session across calls. Calling `method: "initialize"` first broadcasts to every active server and returns a session id you can reuse.

### 7.5 From the UI

Under **MCP Servers** (admin): register/edit/delete servers, toggle active/inactive, trigger a manual health check, and open the **Server Health Monitor** (heartbeat, sync status, per-server usage/failure stats) for any server.

Under **MCP Tools**, **MCP Playground**, and **MCP Sessions**: search the discovered tool registry, send raw JSON-RPC requests interactively, and inspect live client↔server session mappings.

### 7.6 Expose a REST API as a tool (no MCP server required)

The **API Registry** turns a plain enterprise REST API into MCP tools, callable through the exact same `POST /mcp` as above. Full details: [docs/api-registry.md](docs/api-registry.md).

Register the REST backend once:

```bash
SERVICE_ID=$(curl -s -X POST http://localhost:8010/mcp/api-services \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "customer-service",
    "base_url": "https://customer.company.com",
    "authentication_type": "bearer",
    "auth_config": {"credential_ref": "CUSTOMER_SERVICE_TOKEN"}
  }' | jq -r .id)
```

`credential_ref` names a **secret resolved through the Secret Provider layer** (§8) — never a raw environment variable, unlike an MCP server's outbound auth above.

Register an endpoint under it — this immediately generates its MCP tool, no discovery/sync step needed:

```bash
curl -X POST http://localhost:8010/mcp/api-services/$SERVICE_ID/endpoints \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "tool_name": "get_customer",
    "description": "Retrieve customer information",
    "method": "GET",
    "path": "/customers/{id}",
    "parameters": {"id": {"type": "string", "required": true, "location": "path"}}
  }'
```

`get_customer` now shows up in `GET /mcp/tools` next to any MCP-server-backed tools, and is called exactly like the `tools/call` example in §7.4:

```bash
curl -X POST http://localhost:8010/mcp \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/call","params":{"name":"get_customer","arguments":{"id":"123"}}}'
```

A non-2xx response from the target API (e.g. customer not found) comes back as `{"content":[...], "isError": true}` — a normal tool result, not a gateway failure.

From the UI: **API Services (REST)** (admin-only) under the sidebar — register services, toggle active/inactive, and use the **REST Tool Builder** to add endpoints without touching curl.

---

## 8. Secret management

LLM provider credentials, MCP server credentials, and any other secret this gateway needs are resolved at call time through a pluggable **Secret Provider** layer — never a plain env var baked into `Settings`, and never stored in Postgres or Redis beyond a short-lived cache. Default backend: **Infisical**; also supported: AWS Secrets Manager, Google Secret Manager, Azure Key Vault, HashiCorp Vault. Full details, provider onboarding, security model, and rotation flow: [docs/secret-management.md](docs/secret-management.md).

Quick admin checks (Keycloak admin token, `$TOKEN` from §5.1):

```bash
# Which backend is active, and which others this deployment is configured for
curl http://localhost:8010/admin/secrets/providers -H "Authorization: Bearer $TOKEN"

# Per-provider credential status -- never the value itself
curl http://localhost:8010/admin/secrets/status -H "Authorization: Bearer $TOKEN"

# Force-refresh a credential (invalidates the cache, re-fetches from the backend)
curl -X POST http://localhost:8010/admin/secrets/rotate \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"secret_name": "OPENAI_API_KEY"}'
```

Or from the UI: **Secrets** (admin-only) under the sidebar.

---

## 9. Identity provider management

Human authentication goes through the same kind of pluggable abstraction as secrets — `IDENTITY_PROVIDER` selects Keycloak (default), Entra ID, Auth0, Okta, AWS IAM Identity Center, or Google Identity at startup, and `tenant_identity_config` lets different customers use different providers against the same running gateway. Full details: [docs/identity-provider-architecture.md](docs/identity-provider-architecture.md).

```bash
# Which IdP is active, and which others this deployment is configured for
curl http://localhost:8010/admin/identity/providers -H "Authorization: Bearer $TOKEN"

# Register a per-tenant IdP override (e.g. this customer authenticates via Entra)
curl -X POST http://localhost:8010/admin/identity/tenant-configs \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "customer-a",
    "provider": "entra",
    "issuer": "https://login.microsoftonline.com/<tenant-guid>/v2.0",
    "configuration": {"entra_tenant_id": "<tenant-guid>", "entra_client_id": "<app-id>"}
  }'

# RBAC/ABAC: only admins authenticated via Keycloak or Entra may use this project
curl -X POST http://localhost:8010/admin/identity/access-policies \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "finance-ai", "allowed_roles": ["admin"], "allowed_identity_providers": ["keycloak", "entra"]}'
```

Or from the UI: **Identity Providers** (admin-only) under the sidebar — shows the active provider, your own session's mapped identity (email/provider/tenant/roles/groups), tenant configs, and access policies.

---

## 10. Configuration reference

All backend runtime config lives in `backend/.env` (template: `backend/.env.example`). Key groups:

| Group | Variables |
|---|---|
| App | `APP_NAME`, `ENVIRONMENT`, `LOG_LEVEL` |
| Database | `DATABASE_URL` |
| Cache / rate limit | `VALKEY_URL`, `CACHE_TTL_SECONDS`, `RATE_LIMIT_WINDOW_SECONDS` |
| Auth (API keys) | `API_KEY_PREFIX`, `API_KEY_SECRET_PEPPER` |
| Guardrails | `GUARDRAILS_BASE_URL`, `GUARDRAILS_TIMEOUT_SECONDS` |
| Provider region (non-secret) | `AWS_REGION_NAME` |
| Secret Provider layer | `SECRET_PROVIDER`, `SECRET_CACHE_TTL_SECONDS`, plus the active provider's own vars (`INFISICAL_*`, `AWS_SECRETS_REGION`/`AWS_SECRET_NAME_PREFIX`, `GCP_PROJECT_ID`, `AZURE_KEYVAULT_NAME`, `VAULT_*`) — see [docs/secret-management.md](docs/secret-management.md) |
| Identity Provider layer | `IDENTITY_PROVIDER`, `KEYCLOAK_BASE_URL`/`KEYCLOAK_REALM`/`KEYCLOAK_CLIENT_ID`/`KEYCLOAK_AUDIENCE` (default provider), plus the active provider's own vars (`ENTRA_*`, `AUTH0_*`, `OKTA_*`, `AWS_SSO_*`, `GOOGLE_*`) — see [docs/identity-provider-architecture.md](docs/identity-provider-architecture.md) |
| MCP Gateway | `MCP_PROTOCOL_VERSION`, `MCP_CLIENT_TIMEOUT_SECONDS`, `MCP_DISCOVERY_REFRESH_SECONDS`, `MCP_HEALTH_CHECK_INTERVAL_SECONDS`, `MCP_DEFAULT_RATE_LIMIT_PER_WINDOW` |

Root-level `docker-compose.yml` also reads `POSTGRES_HOST_PORT`, `VALKEY_HOST_PORT`, `KEYCLOAK_HOST_PORT`, `GUARDRAILS_HOST_PORT`, `BACKEND_HOST_PORT`, `FRONTEND_HOST_PORT` for port overrides, plus the Secret Provider vars above.

The frontend reads `VITE_API_BASE`, `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_REALM`, `VITE_KEYCLOAK_CLIENT_ID` at build/dev time.

---

## 11. Project structure

```
backend/app/
  api/v1/          One router per domain (chat, embeddings, keys, mcp_gateway, mcp_servers, mcp_tools, mcp_sessions,
                     api_services, secrets, identity, ...)
  core/            Settings, security (API key hashing), exceptions
  db/models/        SQLAlchemy models, incl. api_service.py/api_endpoint.py (the API Registry)
  repositories/     Thin per-model DB-access classes
  identity/         IdentityProvider abstraction + 6 providers + shared JWT validator -- see docs/identity-provider-architecture.md
  secrets/          SecretProvider abstraction + 5 providers + SecretService (Redis cache/rotation) -- see docs/secret-management.md
  services/         routing/, guardrails/, mcp/ (mcp_client, discovery_service, health_checker, routing_engine, session_manager),
                     api_registry/ (schema_converter, rest_executor, api_registry_service -- see docs/api-registry.md),
                     policy_engine, cost/rate-limit/cache services
  middleware/       request_id, auth (Identity Provider Factory-driven), rate_limit
  alembic/versions/ One migration per schema change

frontend/src/
  pages/            Dashboard, ApiKeys, UsageCost, RequestLogs, RoutingRules, Budgets, Organizations, Projects, Users,
                     ProviderConfigs, ModelPricing, McpServers, McpServerHealth, ApiServices, McpTools, McpPlayground,
                     McpSessions, SecretSettings, IdentitySettings
  services/api.js    Centralized Axios client (every backend call)
  services/authService.js  keycloak-js adapter (the default provider's login flow; a deployment standardizing on another IdP swaps in that IdP's native SDK here)
```

See [CLAUDE.md](CLAUDE.md) for the full request lifecycle, conventions, and known deferred items (streaming, hard budget enforcement, encrypted-at-rest credentials, CI pipeline). See [docs/architecture.md](docs/architecture.md) for a diagram-level view of the whole system.

---

## 12. Architecture review summary

A full architecture review was performed against the actual codebase (source, migrations, config, middleware, tests) to produce [doc/HLD.md](doc/HLD.md) and [doc/LLD.md](doc/LLD.md). Findings below reflect that review; anything marked *Roadmap*/*Planned Enhancement*/*Future Capability* is not yet implemented.

### Architecture summary

A single FastAPI process governs two independent, implemented subsystems — the **LLM Gateway** (OpenAI-compatible chat/embeddings over an embedded LiteLLM router, OpenAI/Anthropic/Bedrock) and the **MCP Gateway** (registry, discovery, health-checked routing, per-tool auth), which itself now spans two execution paths: native MCP servers and the **API Registry** (enterprise REST APIs exposed as MCP tools — see [docs/api-registry.md](docs/api-registry.md)). Both top-level gateways sit behind a common middleware chain (`request_id → CORS → auth → rate_limit`) and are underpinned by two structurally identical pluggable abstractions: a 6-provider Identity layer and a 5-backend Secret layer. A **PolicyEngine** (RBAC/ABAC) exists but is wired into exactly one call site — MCP's `tools/call` (both MCP- and REST-backed tools), human callers only. The **Agent Gateway has zero implementation** — confirmed via a repo-wide grep — and exists only as documentation describing how an external agent already consumes the two real gateways today.

### Component inventory discovered

- 22 API routers, 21 SQLAlchemy models, 6 Alembic migrations
- LLM Gateway: `services/routing/{router,model_registry}`, `cache_service`, `cost_service`, `services/guardrails/*`
- MCP Gateway: `services/mcp/{discovery_service, health_checker, mcp_client, routing_engine, session_manager}`
- API Registry: `services/api_registry/{schema_converter, rest_executor, api_registry_service}` — REST endpoints auto-generate MCP tools, credentials resolved via the Secret Provider layer
- Identity: 6 providers + shared JWT validator + factory + multi-tenant resolver
- Secrets: 5 providers + cached `SecretService` + factory
- Cross-cutting: `PolicyEngine` (now tool-name-scoped via `allowed_tool_names`), `RBACService`, `RateLimitService`, custom `GatewayException` hierarchy with a single global handler
- Frontend: 17 admin pages over the same API surface, `keycloak-js`-driven auth

### Missing documentation / implementation areas

- **Observability**: no OpenTelemetry, no Prometheus, no distributed tracing — only structured (`structlog`) JSON logs plus DB-backed request/cost tables.
- **General admin audit trail**: only secret operations are audited; routing-rule/access-policy/user changes have no audit log.
- **Kubernetes/Helm/CI**: none exist; Docker Compose only.
- **Security and performance test suites**: absent — existing tests validate correct-path behavior only, no adversarial or load tests.
- `.env.example` doesn't document the Identity/Secret provider variable groups (documented only in `docs/*.md`, referenced above).

### Recommended improvements before production deployment

1. **Close the policy-enforcement gap** — decide whether `chat.py`/`embeddings.py` should also consult `PolicyEngine`, or document the API-key-scope-only model as a permanent, signed-off design choice.
2. **Add a general admin audit log** — extend the existing `secret_audit_log` pattern to routing rules, access policies, and user/role changes.
3. **Stand up adversarial and load test suites** — auth-bypass/IDOR-style tests and a basic load test (k6/locust) before any production sign-off.
4. **Author Kubernetes manifests/Helm chart and a CI pipeline** if cluster deployment is in scope for GA. *(Roadmap Item)*
5. **Wire real OpenTelemetry tracing** (or explicitly defer it) — the current `request_id`-correlated logs are a reasonable MVP substitute but don't give cross-service traces. *(Roadmap Item)*
6. **Enforce, not just record**, `Budget.limit_usd` and `AccessPolicy.max_tokens` — both are currently advisory-only. *(Planned Enhancement)*
7. **Agent Gateway** *(Future Capability)* — build the registry + agent-identity-as-principal + policy extension first (reusing the `mcp_servers`/`identity`/`PolicyEngine` patterns), before designing the actual agent-to-agent invocation protocol.

---

## 13. Troubleshooting

- **`docker compose up` hangs on `gateway-backend`**: check `docker compose logs gateway-backend` — usually Postgres/Keycloak aren't marked healthy yet; the compose file already waits on health checks, so give it another few seconds on first boot (Keycloak's first start is slow).
- **`/ready` returns 503**: it reports which dependency is down (`db`, `valkey`, `keycloak`, `guardrails`) in the JSON body.
- **Chat/embedding call fails with `provider_error`**: usually means no routing rule exists for that `model_alias`/capability, or the underlying provider credential doesn't resolve through the Secret Provider layer — check `GET /admin/secrets/status` or the **Secrets** admin page.
- **`GET /mcp/tools` returns fewer tools than expected**: for an MCP-backed tool, its owning server must be both `status: active` and `health_status: healthy` — check the MCP Servers page, or trigger a manual health check. For a REST-backed tool, its owning API service must be `status: active` — check the API Services (REST) page.
- **A REST-backed `tools/call` returns `{"isError": true}` instead of an HTTP error**: this is expected — a non-2xx response from the target REST API is a tool *result*, not a gateway failure. Check the response `content` for the actual body the target API returned.
- **401 on any endpoint**: API keys must be sent as `Authorization: Bearer gw_...`; Identity-Provider-authenticated users as `Authorization: Bearer <access_token>` from that provider's token endpoint.
- **Human login fails with a provider/tenant mismatch**: check `GET /admin/identity/providers` for the active default, and `GET /admin/identity/tenant-configs` for any per-tenant override whose `issuer` should match the token's `iss` claim — see [docs/identity-provider-architecture.md](docs/identity-provider-architecture.md#multi-tenant-identity-support).
