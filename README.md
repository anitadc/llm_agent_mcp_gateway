# AI Gateway (LLM Gateway + MCP Gateway + Agent Gateway)

A self-hosted middleware layer that sits between your internal applications/agents and:

- **Multiple LLM providers** (OpenAI, Anthropic, AWS Bedrock) — via an OpenAI-compatible `/v1/chat/completions` and `/v1/embeddings` API, with auth, RBAC, rate limiting, guardrails, cost tracking, and automatic provider failover.
- **Multiple MCP (Model Context Protocol) servers** — via a single `POST /mcp` JSON-RPC endpoint, with a dynamic **MCP Server Registry**, tool discovery, health checking, session management, and per-tool authorization.
- **Enterprise REST APIs exposed as MCP tools** — the **API Registry** lets you register a plain REST API and its endpoints, each of which is instantly callable as an ordinary MCP tool through the same `POST /mcp` endpoint — no MCP server required, and agents can't tell (or need to tell) the difference.
- **A governed registry/marketplace of autonomous agents** — the **Agent Gateway** lets teams register their own agents behind an approval-gated lifecycle (multi-stage sign-off, SLA-tracked review, full audit trail), then exposes them to consumers as a discoverable capability-based marketplace (private/published visibility, per-project enablement, A2A-shaped Agent Cards) invoked through a single `POST /v1/agent-invocations` endpoint — the same "ask for a capability, not a specific agent" model the MCP Gateway uses for tools.
- **Pluggable secret management** — provider API keys are never stored in this app's own config; they're resolved at call time through a swappable Secret Provider layer (this app's own Postgres database, Fernet-encrypted at rest, by default — or AWS/GCP/Azure/Vault).
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
                         │  /v1/agents                  │──▶ Registered Agents (REMOTE_HTTP or A2A
                         │  /v1/agent-invocations       │      JSON-RPC over their own endpoint_url)
                         └──────────┬──────────────────┘
                                    │
                 ┌──────────────────┼───────────────────┬───────────────┐
                 ▼                  ▼                    ▼               ▼
             PostgreSQL          Valkey (Redis)       Keycloak       Guardrails service
        (orgs/projects/keys/   (rate limits,      (human user auth,  (prompt/response
         routing/costs/logs/    response cache,     RBAC roles)        policy checks)
         MCP/API/Agent          idempotency keys)
         registries)
```

A React + Tailwind admin UI (`frontend/`) covers everything above: API keys, usage/cost, request logs, routing rules, budgets, provider configs, the full MCP Gateway (server registry, API Registry for REST-backed tools, tools explorer, JSON-RPC playground, session viewer), and the full Agent Gateway (Agent Registry with its approval workflow, Agent Approvals queue, and a consumer-facing Agent Catalog).

The Agent Gateway's own dispatch path is a peer of the MCP Gateway's, not a wrapper around it — it never routes through `/mcp`, has its own registry/approval/invocation tables, and calls straight out to each agent's own `endpoint_url` (the same way the MCP Gateway calls out to each registered MCP server's `base_url`, and the API Registry calls out to each registered REST API's `base_url`).

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

Provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, ...) are **not** set as env vars on this stack — they're resolved at call time through the Secret Provider layer (this app's own Postgres database by default, via the **Secrets** admin page's "Set a Secret Value" form or `POST /admin/secrets`). Point `SECRET_PROVIDER` and its provider-specific vars at a different secret backend before `docker compose up` (or in a root `.env`) if you'd rather use AWS/GCP/Azure/Vault — see [docs/secret-management.md](docs/secret-management.md). `API_KEY_SECRET_PEPPER` (this gateway's own API-key hashing pepper, unrelated to LLM provider credentials) and `AWS_REGION_NAME` are still plain env vars.

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

`credential_ref` names a **secret resolved through the Secret Provider layer** (§9) — never a raw environment variable, unlike an MCP server's outbound auth above.

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

## 8. Using the Agent Gateway

The **Agent Gateway** is a governed registry and marketplace for autonomous agents — distinct from, and independent of, both the LLM Gateway and the MCP Gateway above. Where the LLM Gateway routes a chat/embedding call to a *model* and the MCP Gateway routes a `tools/call` to a *tool*, the Agent Gateway routes an invocation to an *agent* selected purely by the **capability** it advertises — callers never name a specific agent, endpoint, or protocol. Every agent goes through the same three layers before it can ever serve traffic:

1. **Registration** (`draft`) — an admin registers the agent's metadata; this alone grants no authorization.
2. **Approval** — a configurable, multi-stage human sign-off workflow (security/technical/business, plus an automatic extra `production` stage for high-risk agents) with SLA due-dates, reviewer assignment, evidence links, and a comment thread per stage.
3. **Publication** (`active`) — only now is the agent an eligible dispatch candidate, and even then every single invocation is separately re-evaluated by the same `PolicyEngine` (RBAC/ABAC) that gates MCP tool calls, and by the agent's marketplace **visibility**.

### 8.1 Register an agent

```bash
curl -X POST http://localhost:8010/v1/agents \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "agent_key": "invoice-reconciler",
    "name": "Invoice Reconciler",
    "description": "Matches incoming invoices against POs and flags mismatches",
    "owner_team": "finance-eng",
    "domain": "finance",
    "version": "1.0.0",
    "capabilities": ["invoice.reconcile"],
    "risk_class": "medium",
    "endpoint_url": "https://invoice-agent.internal:9443/invoke",
    "protocol": "remote_http",
    "auth_config": {"type": "bearer", "credential_ref": "INVOICE_AGENT_TOKEN"}
  }'
```

- `risk_class` (`low`/`medium`/`high`) and `trust_level` (`t0_unknown` … `t5_public_untrusted`) are inputs to the approval/routing decision, never a substitute for the PolicyEngine gate applied at invocation time.
- `protocol` (`remote_http`, the default, or `a2a`) selects the outbound wire format — see §8.7.
- `auth_config`'s `credential_ref` is resolved through the **Secret Provider** layer (§9) at dispatch time, exactly like an API Registry endpoint's credential — the raw secret is never stored on the agent row itself.
- An agent can only be edited (`PATCH /v1/agents/{id}`) while it's still `draft` or `rejected` — once it enters review it's immutable until a decision comes back.

### 8.2 Submit for multi-stage approval

```bash
curl -X POST http://localhost:8010/v1/agents/$AGENT_ID/submit -H "Authorization: Bearer $TOKEN"
```

This validates the Agent Card is structurally complete (`name`, at least one capability, `endpoint_url`), moves the agent to `under_review`, and creates one pending `AgentApprovalTask` per required stage — configured once for the whole deployment via `AGENT_APPROVAL_STAGES` (default `security,technical,business`), plus an automatic `production` stage whenever `risk_class` is `high`. Each task gets a `due_at` set `AGENT_APPROVAL_SLA_HOURS` (default 48) hours out.

### 8.3 Review, decide, and everything in between

```bash
# Pending queue across every agent (admin)
curl http://localhost:8010/v1/agent-approvals -H "Authorization: Bearer $TOKEN"

# Restrict who may decide this specific task (optional -- any admin can always decide, restricted or not)
curl -X POST http://localhost:8010/v1/agent-approvals/$TASK_ID/assign-reviewer \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"reviewer_user_id": "<user-uuid>"}'

# Attach supporting evidence (a pen-test report, a design doc, ...)
curl -X PATCH http://localhost:8010/v1/agent-approvals/$TASK_ID/evidence \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"evidence_links": ["https://wiki.internal/invoice-agent-security-review"]}'

# Discuss inline before deciding
curl -X POST http://localhost:8010/v1/agent-approvals/$TASK_ID/comments \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"body": "Confirmed rate limiting is in place on their side."}'
curl http://localhost:8010/v1/agent-approvals/$TASK_ID/comments -H "Authorization: Bearer $TOKEN"

# Decide
curl -X POST http://localhost:8010/v1/agent-approvals/$TASK_ID/approve \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"reason": "Looks good"}'
curl -X POST http://localhost:8010/v1/agent-approvals/$TASK_ID/reject \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"reason": "No auth on the callback endpoint"}'
```

- The agent as a whole moves to `approved` only once **every** stage for that submission round is approved; a **single** rejection immediately rejects the whole registration (the review stages are gates, not votes).
- A rejected agent can be edited and resubmitted (`current_submission_round` increments each time), and a new round's tasks are evaluated independently of a prior round's — an old rejected task never blocks a resubmission.
- An hourly sweep (`AGENT_APPROVAL_SLA_SWEEP_INTERVAL_SECONDS`, default 3600) marks any task still `pending` past its `due_at` as `escalated_at` and logs a warning — there's no email/Slack paging yet, so the **Agent Approvals** page's "overdue" badge (or the logs) is the operator-visible signal today.
- Every registration/submission/decision/lifecycle action is written to a per-agent **audit log** — see §8.9.

### 8.4 Publish and manage the lifecycle

```bash
curl -X POST http://localhost:8010/v1/agents/$AGENT_ID/publish   -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8010/v1/agents/$AGENT_ID/suspend   -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8010/v1/agents/$AGENT_ID/reactivate -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8010/v1/agents/$AGENT_ID/deprecate -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8010/v1/agents/$AGENT_ID/retire    -H "Authorization: Bearer $TOKEN"
```

The full state machine is `draft → under_review → approved → active → {suspended, deprecated} → retired`, plus `rejected` (from `under_review`, resubmittable back to `under_review`). Only `active` agents are ever dispatch candidates — a `suspended` or `deprecated` agent stops receiving new invocations immediately, without needing to be retired first. `deprecate` doesn't take a body today; set a human-readable `deprecation_notice` via `PATCH /v1/agents/{id}` while the agent is still editable (`draft`/`rejected`) if you want the catalog (§8.5) to show one.

### 8.5 Marketplace: visibility, project enablement, and the catalog

Every agent has a `visibility`: **`published`** (the default — every agent is invocable by any caller that clears the PolicyEngine gate, matching how the Agent Gateway behaved before this field existed) or **`private`** (invocable only by its owning project, or a project explicitly opted in):

```bash
# Register (or edit, while still draft) as private, scoped to a project
curl -X POST http://localhost:8010/v1/agents \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"agent_key": "internal-only-agent", "name": "...", "capabilities": ["..."], "visibility": "private", "project_id": "'"$PROJECT_ID"'"}'

# Opt a different project in to a private agent (a no-op, not an error, for a published one)
curl -X POST http://localhost:8010/v1/agents/$AGENT_ID/enable-project \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"project_id\": \"$OTHER_PROJECT_ID\"}"
curl -X POST http://localhost:8010/v1/agents/$AGENT_ID/disable-project \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"project_id\": \"$OTHER_PROJECT_ID\"}"

# Browse everything your project can currently invoke (any authenticated caller, not admin-only)
curl http://localhost:8010/v1/agents/catalog -H "Authorization: Bearer $API_KEY"
```

The catalog response is deliberately a stripped-down view (`AgentCatalogEntryOut`) — no `auth_config`, no approval/audit internals — safe to show to any consumer browsing for a capability to call.

### 8.6 Agent Card (A2A-shaped)

```bash
curl http://localhost:8010/v1/agents/$AGENT_ID/agent-card -H "Authorization: Bearer $TOKEN"
```

Returns a best-effort [A2A (Agent2Agent) protocol](https://github.com/a2aproject/A2A)-shaped **Agent Card** (`name`, `description`, `version`, `url`, `provider`, `capabilities`, `skills`, `defaultInputModes`/`defaultOutputModes`, plus a `deprecationNotice` when set) built from the registry row — a structural approximation for interoperability, not a certified implementation of the A2A JSON Schema.

### 8.7 Invoke an agent by capability

```bash
curl -X POST http://localhost:8010/v1/agent-invocations \
  -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" \
  -H "Idempotency-Key: reconcile-batch-2026-09-09-01" \
  -d '{
    "capability": "invoice.reconcile",
    "operation": "reconcile_batch",
    "payload": {"invoice_ids": ["INV-1001", "INV-1002"]}
  }'
```

- An API key needs the `agent:invoke` scope (the Agent Gateway analogue of `tool:execute`); an Identity-Provider-authenticated human is instead gated by the `PolicyEngine`'s `allowed_agent_keys`, exactly like MCP tools are gated by `allowed_tool_names`.
- Every `active` agent advertising the requested `capability` is a candidate, tried in ascending `priority` order. Each candidate is first checked against `visibility`/project-enablement (§8.5), then against the `PolicyEngine`; the first one that passes both is dispatched.
- A dispatch failure that's a transport error or a 5xx response is **retried against the next eligible candidate** automatically; a 4xx is treated as a definitive business rejection and returned immediately (another agent would most likely reject the same payload identically).
- The wire format sent to the agent's own `endpoint_url` depends on its `protocol`: **`remote_http`** (default) POSTs this app's own `{"operation", "payload"}` JSON; **`a2a`** wraps the same operation/payload into a best-effort A2A `message/send` JSON-RPC 2.0 envelope instead (not verified against a live A2A server).
- The optional `Idempotency-Key` header makes a repeat call from the same caller with the same key return the **first successful** attempt's response without re-invoking the agent — a failed attempt is never cached under the key, so a retry after a timeout/error always gets a fresh attempt. Cached for `AGENT_IDEMPOTENCY_TTL_SECONDS` (default 86400 — a full day, independent of the general response-cache TTL).
- `GET /v1/agent-invocations` lists your own recent invocation history (any authenticated caller, not admin-only — this is observability for your own traffic, same access level as `GET /v1/logs`).

### 8.8 Health checking

```bash
curl -X POST http://localhost:8010/v1/agents/$AGENT_ID/health-check -H "Authorization: Bearer $TOKEN"
```

Unlike an MCP server (which has `initialize` as a universal liveness probe), there's no protocol-guaranteed health check for an arbitrary REMOTE_HTTP/A2A agent — so the checker sends the same lightweight request shape a real invocation would use and treats **any** HTTP response, even a 4xx/5xx from the agent's own application logic, as proof the endpoint is alive and reachable (`health_status: healthy`). Only a transport-level failure (timeout, connection refused, DNS, TLS) counts as `unhealthy`. This also runs automatically on a timer against every active agent (`AGENT_HEALTH_CHECK_INTERVAL_SECONDS`, default 60s) — `health_status` is informational today (surfaced in the registry, approvals, and catalog views) and does not yet gate dispatch the way an MCP server's health does.

### 8.9 Cost tracking, stats, and the audit log

```bash
# Set (or update) what this agent costs per invocation -- omit entirely to leave it "unpriced"
curl -X PUT http://localhost:8010/v1/agents/$AGENT_ID/pricing \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"cost_per_invocation": "0.015"}'
curl http://localhost:8010/v1/agents/$AGENT_ID/pricing -H "Authorization: Bearer $TOKEN"

# Request/error/latency/cost aggregates over a rolling window (default 60 minutes)
curl "http://localhost:8010/v1/agents/$AGENT_ID/stats?window_minutes=60" -H "Authorization: Bearer $TOKEN"

# Full lifecycle/approval/audit history for this agent, paginated
curl "http://localhost:8010/v1/agents/$AGENT_ID/audit-log?page=1&page_size=25" -H "Authorization: Bearer $TOKEN"
```

`cost_usd` on an invocation (and `total_cost_usd` in `/stats`) is `null`, not `0`, whenever no `AgentPricing` row exists for that agent — deliberately distinct from a real, priced $0 call, so "unpriced" and "free" are never conflated in cost reporting.

### 8.10 From the UI

- **Agent Registry** (admin-only): register/edit agents, submit for approval, run the lifecycle actions (publish/suspend/reactivate/deprecate/retire), trigger a manual health check, set per-invocation pricing, enable/disable a private agent for other projects, and expand any row for its approval history, usage stats, cost, Agent Card, and recent audit log.
- **Agent Approvals** (admin-only): the cross-agent pending queue — assign a reviewer, attach evidence, hold a comment thread, and approve/reject each stage, with an overdue badge for anything past its SLA.
- **Agent Catalog** (any authenticated user): the consumer-facing marketplace view — search by name/capability/domain/owner team, see health/status at a glance, and read any deprecation notice.

---

## 9. Secret management

LLM provider credentials, MCP server credentials, and any other secret this gateway needs are resolved at call time through a pluggable **Secret Provider** layer — never a plain env var baked into `Settings`. Default backend: **this app's own Postgres database**, with values Fernet-encrypted at rest under `SECRET_STORAGE_ENCRYPTION_KEY`; also supported: AWS Secrets Manager, Google Secret Manager, Azure Key Vault, HashiCorp Vault. Resolved values are still cached briefly in Valkey regardless of backend. Full details, provider onboarding, security model, and rotation flow: [docs/secret-management.md](docs/secret-management.md).

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

## 10. Identity provider management

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

## 11. Configuration reference

All backend runtime config lives in `backend/.env` (template: `backend/.env.example`). Key groups:

| Group | Variables |
|---|---|
| App | `APP_NAME`, `ENVIRONMENT`, `LOG_LEVEL` |
| Database | `DATABASE_URL` |
| Cache / rate limit | `VALKEY_URL`, `CACHE_TTL_SECONDS`, `RATE_LIMIT_WINDOW_SECONDS` |
| Auth (API keys) | `API_KEY_PREFIX`, `API_KEY_SECRET_PEPPER` |
| Guardrails | `GUARDRAILS_BASE_URL`, `GUARDRAILS_TIMEOUT_SECONDS` |
| Provider region (non-secret) | `AWS_REGION_NAME` |
| Secret Provider layer | `SECRET_PROVIDER`, `SECRET_CACHE_TTL_SECONDS`, plus the active provider's own vars (`SECRET_STORAGE_ENCRYPTION_KEY` for the default Postgres backend, or `AWS_SECRETS_REGION`/`AWS_SECRET_NAME_PREFIX`, `GCP_PROJECT_ID`, `AZURE_KEYVAULT_NAME`, `VAULT_*`) — see [docs/secret-management.md](docs/secret-management.md) |
| Identity Provider layer | `IDENTITY_PROVIDER`, `KEYCLOAK_BASE_URL`/`KEYCLOAK_REALM`/`KEYCLOAK_CLIENT_ID`/`KEYCLOAK_AUDIENCE` (default provider), plus the active provider's own vars (`ENTRA_*`, `AUTH0_*`, `OKTA_*`, `AWS_SSO_*`, `GOOGLE_*`) — see [docs/identity-provider-architecture.md](docs/identity-provider-architecture.md) |
| MCP Gateway | `MCP_PROTOCOL_VERSION`, `MCP_CLIENT_TIMEOUT_SECONDS`, `MCP_DISCOVERY_REFRESH_SECONDS`, `MCP_HEALTH_CHECK_INTERVAL_SECONDS`, `MCP_DEFAULT_RATE_LIMIT_PER_WINDOW` |
| Agent Gateway | `AGENT_APPROVAL_STAGES` (default `security,technical,business`), `AGENT_INVOCATION_TIMEOUT_SECONDS`, `AGENT_DEFAULT_RATE_LIMIT_PER_WINDOW`, `AGENT_IDEMPOTENCY_TTL_SECONDS`, `AGENT_APPROVAL_SLA_HOURS`, `AGENT_APPROVAL_SLA_SWEEP_INTERVAL_SECONDS`, `AGENT_HEALTH_CHECK_INTERVAL_SECONDS` |

Root-level `docker-compose.yml` also reads `POSTGRES_HOST_PORT`, `VALKEY_HOST_PORT`, `KEYCLOAK_HOST_PORT`, `GUARDRAILS_HOST_PORT`, `BACKEND_HOST_PORT`, `FRONTEND_HOST_PORT` for port overrides, plus the Secret Provider vars above.

The frontend reads `VITE_API_BASE`, `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_REALM`, `VITE_KEYCLOAK_CLIENT_ID` at build/dev time.

---

## 12. Project structure

```
backend/app/
  api/v1/          One router per domain (chat, embeddings, keys, mcp_gateway, mcp_servers, mcp_tools, mcp_sessions,
                     api_services, secrets, identity, agents (Agent Registry + Approvals), agent_invocations, ...)
  core/            Settings, security (API key hashing), exceptions
  db/models/        SQLAlchemy models, incl. api_service.py/api_endpoint.py (the API Registry) and
                     agent.py/agent_approval_task.py/agent_approval_comment.py/agent_invocation.py/agent_pricing.py/
                     agent_project_enablement.py/agent_audit_log.py (the Agent Gateway)
  repositories/     Thin per-model DB-access classes
  identity/         IdentityProvider abstraction + 6 providers + shared JWT validator -- see docs/identity-provider-architecture.md
  secrets/          SecretProvider abstraction + 5 providers + SecretService (Redis cache/rotation) -- see docs/secret-management.md
  services/         routing/, guardrails/, mcp/ (mcp_client, discovery_service, health_checker, routing_engine, session_manager),
                     api_registry/ (schema_converter, rest_executor, api_registry_service -- see docs/api-registry.md),
                     agent_gateway/ (agent_registry_service, approval_service, invocation_service, health_checker, lifecycle),
                     policy_engine, cost/rate-limit/cache services
  middleware/       request_id, auth (Identity Provider Factory-driven), rate_limit
  alembic/versions/ One migration per schema change

frontend/src/
  pages/            Dashboard, ApiKeys, UsageCost, RequestLogs, RoutingRules, Budgets, Organizations, Projects, Users,
                     ProviderConfigs, ModelPricing, McpServers, McpServerHealth, ApiServices, McpTools, McpPlayground,
                     McpSessions, SecretSettings, IdentitySettings, Agents (Agent Registry), AgentApprovals, AgentCatalog
  services/api.js    Centralized Axios client (every backend call)
  services/authService.js  keycloak-js adapter (the default provider's login flow; a deployment standardizing on another IdP swaps in that IdP's native SDK here)
```

See [CLAUDE.md](CLAUDE.md) for the full request lifecycle, conventions, and known deferred items (streaming, hard budget enforcement, encrypted-at-rest credentials, CI pipeline). See [docs/architecture.md](docs/architecture.md) for a diagram-level view of the whole system.

---

## 13. Troubleshooting

- **`docker compose up` hangs on `gateway-backend`**: check `docker compose logs gateway-backend` — usually Postgres/Keycloak aren't marked healthy yet; the compose file already waits on health checks, so give it another few seconds on first boot (Keycloak's first start is slow).
- **`/ready` returns 503**: it reports which dependency is down (`db`, `valkey`, `keycloak`, `guardrails`) in the JSON body.
- **Chat/embedding call fails with `provider_error`**: usually means no routing rule exists for that `model_alias`/capability, or the underlying provider credential doesn't resolve through the Secret Provider layer — check `GET /admin/secrets/status` or the **Secrets** admin page.
- **`GET /mcp/tools` returns fewer tools than expected**: for an MCP-backed tool, its owning server must be both `status: active` and `health_status: healthy` — check the MCP Servers page, or trigger a manual health check. For a REST-backed tool, its owning API service must be `status: active` — check the API Services (REST) page.
- **A REST-backed `tools/call` returns `{"isError": true}` instead of an HTTP error**: this is expected — a non-2xx response from the target REST API is a tool *result*, not a gateway failure. Check the response `content` for the actual body the target API returned.
- **401 on any endpoint**: API keys must be sent as `Authorization: Bearer gw_...`; Identity-Provider-authenticated users as `Authorization: Bearer <access_token>` from that provider's token endpoint.
- **Human login fails with a provider/tenant mismatch**: check `GET /admin/identity/providers` for the active default, and `GET /admin/identity/tenant-configs` for any per-tenant override whose `issuer` should match the token's `iss` claim — see [docs/identity-provider-architecture.md](docs/identity-provider-architecture.md#multi-tenant-identity-support).
- **`POST /v1/agent-invocations` returns `"authorization_decision": "no_active_agent"`**: no agent with `status: active` currently advertises the requested `capability` — check the Agent Registry page, or that the agent actually made it through `publish` (§8.4).
- **... returns `"authorization_decision": "denied"`**: at least one active agent serves the capability, but the caller's role/identity-provider (or, for an API key, its missing `agent:invoke` scope) was rejected by every candidate's policy check — this is a completed authorization decision, not a bug.
- **A private agent doesn't show up in `GET /v1/agents/catalog` for a project that should see it**: confirm the caller is an API key (IdP-authenticated human callers have no project context for the catalog's visibility filter) and that its `project_id` either owns the agent or was explicitly enabled via `POST /v1/agents/{id}/enable-project` (§8.5).
- **An agent registration can't be edited (`PATCH /v1/agents/{id}` fails with `400`)**: it's only mutable while `draft` or `rejected` — once submitted it's immutable until a decision comes back; a rejected agent can be edited and resubmitted.
- **`due_at`/`escalated_at` never populate on approval tasks**: `AGENT_APPROVAL_SLA_HOURS` (or `AGENT_APPROVAL_SLA_SWEEP_INTERVAL_SECONDS`) may be set to `0`, which disables SLA tracking/the escalation sweep entirely — same on/off convention as the MCP background loops.
- **`Idempotency-Key` doesn't seem to prevent a duplicate call**: only a **successful** prior response is cached under that key — a failed attempt is deliberately never cached, so a retry after an error always dispatches fresh; also confirm the same caller (API key or user) and the same key string are being reused within `AGENT_IDEMPOTENCY_TTL_SECONDS`.
