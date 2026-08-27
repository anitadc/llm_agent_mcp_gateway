# Requirement Document — AI Gateway (LLM Gateway + MCP Gateway)

**Audience**: engineers joining this codebase. **Goal**: read this top to bottom and understand *what* the system must do and *why* it's shaped the way it is, before opening a single source file.

For *how the code is organized* and coding conventions, see [../CLAUDE.md](../CLAUDE.md). For *how to run it*, see [../README.md](../README.md). This document is the contract between those two — what must be true regardless of how it's implemented.

---

## 1. Purpose & Problem Statement

Internal applications and AI agents at the organization need to call LLMs (chat + embeddings) and MCP tool servers. Calling providers directly has problems:

- Every app re-implements auth, retries, rate limiting, and cost tracking.
- Provider API keys end up scattered across many codebases.
- There's no central place to see who is spending what, or to block/allow a model.
- Prompts and responses aren't screened for policy violations (PII, prohibited content) before/after they leave the organization's boundary.
- Agents that call MCP tool servers directly have no shared governance layer — no auth, no rate limits, no visibility into which tools exist or whether a server is even alive.

**This system is a single, self-hosted gateway that all of that traffic flows through instead.** It is a control-plane and policy-enforcement layer, not a product feature in itself — it does the same job for LLM calls and MCP tool calls that an API gateway does for microservices.

---

## 2. Actors

| Actor | What they do | How they authenticate |
|---|---|---|
| **AI Agent / backend service** | Calls `/v1/chat/completions`, `/v1/embeddings`, `POST /mcp` programmatically | API key (`Authorization: Bearer gw_...`) |
| **Admin** (human) | Manages organizations, projects, users, provider credentials, routing rules, budgets, MCP servers | Identity Provider login (Keycloak by default; Entra/Auth0/Okta/AWS Identity Center/Google also supported) |
| **Team Lead** (human) | Manages their own projects, budgets, project membership | Identity Provider login |
| **Developer** (human) | Views usage/logs/keys for their project(s) | Identity Provider login |
| **Viewer** (human) | Read-only access; for MCP specifically, can discover tools but not execute them | Identity Provider login |
| **MCP Server** | A third-party or internal service implementing the MCP protocol; the gateway calls it, it never calls the gateway | Receives a bearer/API-key token the gateway injects |

Organizations contain Projects; Projects contain API Keys and (via `project_users`) human members with a time-bounded membership window (`start_date`/`end_date`).

---

## 3. Glossary

| Term | Meaning |
|---|---|
| **Model alias** | A logical name (e.g. `gateway-fast`) that a caller requests. It is *never* a literal provider model name — it's resolved to one or more real provider/model targets via a **Routing Rule**. This is what makes provider failover and cost-based routing possible without client changes. |
| **Capability** | `chat` or `embedding`. Routing rules, provider pricing, and guardrail behavior all branch on this — chat and embedding traffic never cross-resolve against each other's rules. |
| **Routing Rule** | DB row mapping `(model_alias, capability, [project], [end user])` → an ordered list of `{provider, model}` targets plus a `strategy` (priority / cost / latency) for ordering them. |
| **Guardrail** | A pluggable policy check (PII, prohibited content, etc.) run on the prompt before the provider call, and on the response after it (chat only — embeddings have no text response to check). |
| **MCP (Model Context Protocol)** | JSON-RPC-based protocol by which an LLM/agent discovers and calls external "tools" hosted by an MCP server. |
| **MCP Server Registry** | The gateway's own table of known MCP servers, their transport/auth config, and their observed health/status. Nothing calls an MCP server unless it's in this registry. |
| **Tool Registry** | The gateway's cache of `tool_name → execution target` — either an owning MCP server (`source_type=mcp`) or a registered REST endpoint (`source_type=rest`), rebuilt by **Discovery** for the former and by direct registration for the latter. |
| **Discovery** | The act of calling `initialize` + `tools/list` on an MCP server and reconciling the Tool Registry from the result. Does not apply to REST-backed tools, which are explicitly registered instead (see the **API Registry**). |
| **Session (MCP)** | MCP servers can be stateful. The gateway maps one `client_session_id` to a per-server `server_session_id` so repeated calls from the same client land on the same server-side session. REST-backed tools have no session concept — every call is stateless. |
| **Scope** (`tool:read` / `tool:execute`) | MCP-specific authorization granularity, independent of the chat/embeddings RBAC roles. Applies identically to MCP- and REST-backed tools. |
| **API Registry** | The gateway's registry of enterprise REST APIs (`api_services`) and their individually registered endpoints (`api_endpoints`), each of which is exposed as an ordinary MCP tool. See §6.10. |

---

## 4. High-Level Architecture

```
                         ┌─────────────────────────────┐
   Apps / Agents ──────▶ │   Gateway Backend (FastAPI)  │
                         │                              │
                         │  /v1/chat/completions        │──▶ OpenAI / Anthropic / Bedrock
                         │  /v1/embeddings              │      (via an embedded LiteLLM Router)
                         │  /mcp            (JSON-RPC)  │──▶ Registered MCP servers (Streamable HTTP)
                         │  /mcp/servers, /mcp/tools     │      or registered REST APIs (API Registry)
                         │  /mcp/api-services            │
                         │  /v1/{orgs,projects,users,   │
                         │   keys,routing-rules,budgets, │
                         │   provider-configs,usage,logs}│
                         └───────────┬──────────────────┘
                                     │
             ┌───────────────────────┼───────────────────────┬────────────────────┐
             ▼                       ▼                       ▼                    ▼
        PostgreSQL               Valkey/Redis             Keycloak          Guardrails service
   (all persistent state:    (sliding-window rate     (human user auth,    (pluggable prompt /
    orgs/projects/keys/       limits, response cache,   RBAC roles via      response policy
    routing rules, cost       API-key lookup cache)      realm roles)        checks)
    ledger, request logs,
    MCP registry/tools/
    sessions/mcp logs)
```

**Request path, every request, in order:**

```
request_id middleware → CORS → auth middleware (API key OR Identity Provider token) → rate-limit middleware → router handler
```

A React + Tailwind admin UI (`frontend/`) is a thin client over this API — it has no business logic of its own; every decision (RBAC, routing, cost) is enforced server-side.

---

## 5. Functional Requirements — LLM Gateway

### 5.1 Authentication & Authorization

| ID | Requirement |
|---|---|
| REQ-AUTH-01 | Every request except `/health`, `/ready`, `/docs`, `/openapi.json`, `/redoc` must carry a `Bearer` token. |
| REQ-AUTH-02 | A token starting with the configured API-key prefix (`gw_` by default) is treated as an **API key**; anything else is treated as an **Identity Provider JWT** (Keycloak by default; see §8) and validated against that provider's JWKS (signature, issuer, audience, expiry). |
| REQ-AUTH-03 | API keys are stored **hashed** (HMAC-SHA256 keyed by a server-side pepper). The raw key is shown to the caller exactly once, at creation time, and is never recoverable or logged thereafter. |
| REQ-AUTH-04 | A verified API key's identity is cached in Valkey (keyed by hash) for the cache TTL, to avoid a DB round-trip on every request; revoking a key must invalidate this cache entry immediately. |
| REQ-AUTH-05 | A user's internal role is derived from whichever roles their Identity Provider's `UserIdentity.roles` carries (`admin` / `team_lead` / `developer` / `viewer`); first login auto-provisions a local `User` row keyed by `(identity_provider, external_sub)` (falling back to matching by email). |
| REQ-AUTH-06 | Admin-only management endpoints (organizations, users, provider configs, routing rules, model pricing) must reject any principal that isn't an Identity-Provider-authenticated user with the `admin` role — **API keys can never call these endpoints**, by design (Identity Providers are scoped to human auth only; see §12). |
| REQ-AUTH-07 | Team-lead-and-above endpoints (projects, project membership, budgets) accept `admin` or `team_lead`. |

### 5.2 Chat Completions — `POST /v1/chat/completions`

OpenAI-compatible request/response shape (`model`, `messages`, `temperature`, `max_tokens`, `top_p`, `user`).

| ID | Requirement |
|---|---|
| REQ-CHAT-01 | Resolve `api_key → project → organization` before doing anything else; a key whose project no longer exists must fail with 404, not silently proceed. |
| REQ-CHAT-02 | Run the **prompt guardrail check** (concatenated message contents) before any cache lookup or provider call. If blocked, return `422 guardrail_blocked` and log the request as `blocked` — no provider call is made. |
| REQ-CHAT-03 | Check the response cache (keyed by a hash of `model_alias` + normalized request body) **after** the prompt guardrail passes. A cache hit skips the provider call and routing entirely, costs `$0`, and is flagged `cache_hit: true`. |
| REQ-CHAT-04 | On a cache miss, resolve the `model_alias` to an ordered list of provider targets via the Routing Rules engine (§5.5) and call the first available one (with automatic fallback handled by the embedded LiteLLM Router). |
| REQ-CHAT-05 | Run the **response guardrail check** on the completion text. If blocked, return `422` and log as `blocked` (the response is never returned to the caller, even though a provider call already happened and must still be logged/costed as far as tokens spent). |
| REQ-CHAT-06 | If the guardrail masked part of the text (PII redaction), return the **masked** text to the caller, not the raw completion. |
| REQ-CHAT-07 | Compute cost from actual token usage (§5.7), cache the successful response, and write the response back with a `gateway_metadata` block: `request_id`, `resolved_provider`, `resolved_model`, `cache_hit`, `cost_usd`. |
| REQ-CHAT-08 | All logging/cost writes happen as a `BackgroundTask` **after** the response is already sent — they must never add latency to the caller. |

### 5.3 Embeddings — `POST /v1/embeddings`

| ID | Requirement |
|---|---|
| REQ-EMB-01 | Same lifecycle as chat (auth → prompt guardrail → cache → route → cost → log), resolved against routing rules tagged `capability: embedding` — **never** the `chat` rules, and vice versa. |
| REQ-EMB-02 | There is **no response-side guardrail check** — an embedding response is a vector, not text, so only the input is ever screened. |
| REQ-EMB-03 | Pricing entries for embedding models omit `completion_per_1k` (there is no completion side to price). |
| REQ-EMB-04 | Embeddings are a stateless proxy only — the gateway does not store, index, or search vectors; it has no vector-store responsibilities. |

### 5.4 Guardrails

| ID | Requirement |
|---|---|
| REQ-GRD-01 | Guardrail checks are implemented against an abstract `GuardrailsClient` interface (`check_prompt`, `check_response`), not a hardcoded HTTP call inline in the request handlers — so the real guardrails vendor/contract can be swapped without touching chat/embeddings code. |
| REQ-GRD-02 | The HTTP implementation retries once on a transient transport error before giving up. |
| REQ-GRD-03 | Every guardrail verdict (allowed/blocked, violation types, which direction) is persisted per request for audit, and surfaced in the Request Logs UI. |

### 5.5 Routing & Failover

| ID | Requirement |
|---|---|
| REQ-RTE-01 | A Routing Rule resolves by **specificity**: an end-user-specific + project-specific rule beats a project-only rule, which beats a global (no project, no user) rule; ties within the same specificity break by an explicit `priority` integer. |
| REQ-RTE-02 | Three ordering strategies must be supported for a rule's target list: **priority** (fixed weight order), **cost** (cheapest `model_pricing` entry first — unpriced models sort last, not first, so missing prices don't win by default), **latency** (fastest observed p50 first, over a rolling recent window; targets with fewer than the minimum sample count are treated as worst-case, not best-case, so a cold-start target doesn't win by looking artificially fast). |
| REQ-RTE-03 | No routing rule matching a requested `(model_alias, capability)` is a hard failure (`502 provider_error`), not a silent default — callers must not be routed to an arbitrary model. |
| REQ-RTE-04 | Provider calls go through an embedded LiteLLM `Router` (in-process, not a network sidecar) built per-request from the resolved target list, so automatic retry/fallback across targets is LiteLLM's responsibility, not hand-rolled here. |
| REQ-RTE-05 | Supported providers: OpenAI, Anthropic, AWS Bedrock. Provider credentials are read from server-side config only, never from the client request. |

### 5.6 Caching & Rate Limiting

| ID | Requirement |
|---|---|
| REQ-CACHE-01 | Successful, non-blocked responses are cached in Valkey keyed by a hash of the model alias and the semantically-relevant parts of the request; TTL is configurable. |
| REQ-RATE-01 | `/v1/chat/completions` and `/v1/embeddings` (and `/mcp`, see §6) are rate-limited per API key using a Valkey-backed sliding time window (atomic INCR+EXPIRE via a Lua script, to avoid a race between the check and the increment). Requests authenticated as an Identity-Provider-authenticated human user are not subject to this per-endpoint limiter. |

### 5.7 Cost Tracking & Budgets

| ID | Requirement |
|---|---|
| REQ-COST-01 | Cost is computed from actual `prompt_tokens`/`completion_tokens` returned by the provider, multiplied by admin-editable per-1k pricing (`model_pricing` table) — never hardcoded in code. A model with no pricing entry costs `$0`, not an error. |
| REQ-COST-02 | Every request writes one `cost_ledger` row (even `$0`), attributable to `project → organization` and, if known, the acting human `user`. |
| REQ-COST-03 | A Budget can be scoped to an organization, a project, or a user (at least one must be set) with a `daily` or `monthly` period and an `alert_threshold_pct`. Current spend and percent-used are computed live from `cost_ledger`, not a running counter that can drift. |
| REQ-COST-04 | **Budgets are advisory only in this version** — exceeding one does not block requests. Hard enforcement is an explicit deferred item (§13). |

### 5.8 Observability

| ID | Requirement |
|---|---|
| REQ-OBS-01 | Every chat/embedding request produces one `request_logs` row: identity, model alias, resolved provider/model, status (`success`/`error`/`blocked`/`rate_limited`), latency, token counts, cache-hit flag — queryable/paginated by org, project, status, model alias, and date range. |
| REQ-OBS-02 | A `/v1/usage/summary` endpoint aggregates total cost, request count, token counts, cache-hit rate, and a per-model-alias breakdown over a date range, scoped by org/project. |
| REQ-OBS-03 | `GET /health` is a liveness check (no dependency checks). `GET /ready` is a readiness check that individually reports the status of Postgres, Valkey, Keycloak, and the Guardrails service, and returns `503` if any is down. |

### 5.9 Administrative Management

Standard CRUD, all admin-gated (or admin/team-lead as noted), each its own router/tag: **Organizations**, **Projects** (+ **Project Users** membership with start/end dates), **Users**, **API Keys** (create/list/revoke — revoking invalidates the auth cache immediately), **Provider Configs** (which providers are enabled, credential *reference*, not the raw secret), **Model Pricing**, **Routing Rules**, **Budgets**.

---

## 6. Functional Requirements — MCP Gateway

**Core principle: agents never call an MCP server directly.** Every MCP interaction — discovery, tool listing, tool execution — goes through this gateway's `POST /mcp`, which resolves everything from the registry. There is no hardcoded server list anywhere in the code.

### 6.1 MCP Server Registry

| ID | Requirement |
|---|---|
| REQ-REG-01 | Each registered server stores: `name` (unique), `base_url`, `transport_type` (currently only `http` — Streamable HTTP; STDIO is explicitly out of scope), `auth_config`, operator-controlled `status` (`active`/`inactive`), observed `health_status` (`unknown`/`healthy`/`unhealthy`), `last_heartbeat`, discovery bookkeeping (`last_sync_status`/`error`/`at`/`latency_ms`, `protocol_version`), and free-form `metadata`. |
| REQ-REG-02 | `status` and `health_status` are **independent axes** — an operator can deactivate a perfectly healthy server, and a server can be administratively active but observed unhealthy. Both must be true for a server to be used (§6.4). |
| REQ-REG-03 | `auth_config` names an **environment variable** holding the outbound secret (`credential_ref`) — the raw secret is never stored in the database, logged, or returned partially decoded; only bearer-token and custom-header API-key auth styles are supported today. |
| REQ-REG-04 | Full CRUD (`GET/POST/PUT/DELETE /mcp/servers`), a manual health-check trigger (`POST /mcp/servers/{id}/health-check`), and a per-server usage/failure stats endpoint (`GET /mcp/servers/{id}/stats`, derived from the MCP request log, not a separate counter). All registry management is admin-only (Identity-Provider-authenticated human, same as Provider Configs). |

### 6.2 Tool Discovery

| ID | Requirement |
|---|---|
| REQ-DISC-01 | Discovering a server means: call `initialize` (also the liveness probe, §6.3), then `tools/list`, then reconcile the central **Tool Registry** (`tool_name → server_id`) — add tools the server newly advertises, remove rows for tools it no longer advertises. |
| REQ-DISC-02 | `tool_name` is **unique gateway-wide**. If two servers ever advertise the same tool name, the most recently synced server wins the mapping (last-write-wins) — there is no namespacing. |
| REQ-DISC-03 | Discovery is best-effort across servers: one server failing to sync (unreachable, protocol error) must not prevent any other server's sync from succeeding. |
| REQ-DISC-04 | Discovery runs automatically on a timer (default every 5 minutes) **and** on demand via `POST /mcp/tools/sync` (admin-only) — both use the exact same code path. Only administratively-`active` servers are ever discovered/synced. |

### 6.3 Health Checking

| ID | Requirement |
|---|---|
| REQ-HLT-01 | `initialize` doubles as the liveness probe — every MCP server must implement it, whereas a bespoke `/health` REST convention isn't part of the MCP protocol itself. |
| REQ-HLT-02 | A lighter, more frequent health-only sweep (default every 30s) runs independently of the heavier full-discovery sync, so an outage is reflected in `health_status` quickly without waiting for the next tool-list refresh. |
| REQ-HLT-03 | Liveness classification happens in exactly **one place** in the code, reused by the periodic sweep, the discovery flow, and live traffic (the `initialize`/`tools/call` paths through `POST /mcp` itself) — there must not be three different opinions about whether a server is healthy. |
| REQ-HLT-04 | A manual, on-demand health check (`POST /mcp/servers/{id}/health-check`) must be available for operators who don't want to wait for the next scheduled sweep. |

### 6.4 Request Routing — `POST /mcp`

The single entry point. Routing is decided **from the JSON-RPC request body**, never from the URL path.

| ID | Requirement |
|---|---|
| REQ-RPC-01 | `method: "initialize"` is broadcast to **every active server** (best-effort — one server's failure doesn't fail the call), a per-server session id is captured from each, and the aggregate result (protocol version, capabilities, gateway server info, plus any per-server warnings) is returned. |
| REQ-RPC-02 | `method: "tools/list"` is served **entirely from the cached Tool Registry** — no MCP server is called. It returns only tools whose owning server is both `active` and `healthy` right now (REQ-REG-02) — disabling or losing a server hides its tools immediately, without needing a re-sync. |
| REQ-RPC-03 | `method: "tools/call"` extracts `params.name`, looks it up in the Tool Registry to find the owning (and currently active+healthy) server, and forwards the call to it — resolving the tool's server at **call time**, not from a stale cache, so a server that went down after a successful sync is not used. |
| REQ-RPC-04 | Any other method, or a `tools/call` missing `params.name`, is rejected as a gateway-level bad request — it is not silently forwarded anywhere. |
| REQ-RPC-05 | Gateway-level rejections (missing scope, rate limited, unknown tool, malformed request) are ordinary HTTP errors, in the same error envelope as every other endpoint. Only once the gateway has agreed to forward a call does a downstream MCP server's own JSON-RPC `error` object get forwarded verbatim in the (still `200 OK`) response body — that's an application-level result, not a gateway rejection. |
| REQ-RPC-06 | Responses are fully buffered JSON, not a server-sent-events stream — the same "buffer the whole completion" tradeoff already made for chat, applied here to tool results (see §13, deferred streaming). |

### 6.5 Session Management

| ID | Requirement |
|---|---|
| REQ-SESS-01 | The gateway maintains `client_session_id → {server_id: server_session_id, ...}`, persisted in the database (not just in-process memory), so the mapping survives a gateway restart. |
| REQ-SESS-02 | The same `client_session_id` must always be routed to the same `server_session_id` for a given server across multiple calls. If no session exists yet for a server a call needs, the gateway transparently establishes one (via the same `initialize`-as-probe path) before forwarding. |
| REQ-SESS-03 | A client_session_id is carried via the `Mcp-Session-Id` header; if the client doesn't supply one, the gateway mints one and returns it in the response header for the client to reuse. |

### 6.6 Authentication & Authorization

| ID | Requirement |
|---|---|
| REQ-MCPAUTH-01 | Inbound auth reuses the exact same middleware as the rest of the gateway (API key or Identity Provider token) — there is no separate MCP auth mechanism. |
| REQ-MCPAUTH-02 | Two MCP-specific scopes gate the JSON-RPC methods: `tool:read` (required for `initialize`, `tools/list`) and `tool:execute` (required for `tools/call`). API keys must be issued with these scopes explicitly — pre-existing keys have neither by default. Identity-Provider-authenticated users get scopes implied by role: `viewer` gets `tool:read` only, every other role gets both. |
| REQ-MCPAUTH-03 | Outbound auth to each MCP server is injected by the gateway per REQ-REG-03 — the calling agent never sees or supplies the downstream server's credential. |

### 6.7 Rate Limiting

| ID | Requirement |
|---|---|
| REQ-MCPRATE-01 | `/mcp` is subject to the same coarse per-API-key endpoint limiter as chat/embeddings, **plus** a finer per-tool limit (`api_key/user × tool_name`) checked before a `tools/call` is forwarded — a caller hammering one tool can't starve the rest of their own quota against other tools, and vice versa. |

### 6.8 Observability

| ID | Requirement |
|---|---|
| REQ-MCPOBS-01 | Every `POST /mcp` call writes one MCP request log row: `request_id`, identity, `client_session_id`, `method`, `tool_name` (if applicable), `server_id` (if resolved), status, latency — same "background task after response sent" discipline as chat/embeddings logging. |
| REQ-MCPOBS-02 | Per-server usage is derived from that log (`GET /mcp/servers/{id}/stats`: request count, failure count, average latency over a window) rather than a separate running-counter table, so there's one source of truth. |

### 6.9 LLM Gateway ↔ MCP Gateway Integration

| ID | Requirement |
|---|---|
| REQ-INTEG-01 | The LLM Gateway (chat/embeddings) does **not** call MCP servers and does **not** read the MCP Server Registry directly. If an agent using the LLM Gateway needs tool access, it discovers/calls tools the same way any other client does: through `GET /mcp/tools` and `POST /mcp`. The two gateways are integrated only at the API-consumer level, not in-process. |

### 6.10 API Registry — REST APIs Exposed as MCP Tools

Every enterprise REST API can be exposed as an ordinary MCP tool without standing up an MCP server for it. Full detail: [api-registry.md](api-registry.md).

| ID | Requirement |
|---|---|
| REQ-API-01 | An `api_services` row registers one REST backend: `name` (unique), `base_url`, `authentication_type` (`none`/`api_key`/`bearer`/`basic`/`oauth2_client_credentials`) + `auth_config`, static `headers`, `timeout_seconds`, `retry_policy`, an optional `rate_limit_per_window`, and an operator-controlled `status` (`active`/`inactive`) — the REST analogue of `mcp_servers`. |
| REQ-API-02 | An `api_endpoints` row registers one REST endpoint under a service: `tool_name` (unique gateway-wide, same rule as `mcp_tools.name`), `method` (`GET`/`POST`/`PUT`/`DELETE`), `path` (with `{placeholder}` path parameters), and `parameters` (per-parameter `type`/`required`/`location`). |
| REQ-API-03 | Registering (or updating) an endpoint **immediately** creates (or resyncs) its paired `mcp_tools` row, with an auto-generated `inputSchema` derived from `parameters` — there is no separate discovery/sync step the way MCP servers need, because a REST endpoint isn't introspectable via `tools/list` the way an MCP server is. |
| REQ-API-04 | `mcp_tools` carries a `source_type` (`mcp`/`rest`) and points at exactly one of `server_id` or `api_endpoint_id`, enforced by a database CHECK constraint — `RoutingEngine.resolve_tool` and the Tool Registry's availability filter branch on this field so a single code path serves both tool kinds. A `tool_name` collision across an MCP-sourced and a REST-sourced registration is rejected outright (unlike two MCP servers advertising the same name, where the most recent sync wins — see REQ-DISC-02); cross-subsystem collisions are never silently resolved. |
| REQ-API-05 | A REST-backed tool is available for routing only while its owning `api_service.status == active` — REST services have no liveness/health concept the way MCP servers do (REQ-REG-02), since there is no `initialize`-style probe in plain REST. |
| REQ-API-06 | `tools/call` against a REST-backed tool: substitutes `{placeholder}` path parameters, buckets the remaining arguments into query/header/body per each parameter's `location`, injects credentials, and sends the HTTP request. `GET` requests get the same bounded transport-error retry MCP's `initialize`/`tools/list` get; `POST`/`PUT`/`DELETE` are never retried, for the same reason MCP's `tools/call` isn't (REQ-RPC-06's sibling: avoid double-executing a side-effecting call). |
| REQ-API-07 | A non-2xx HTTP response from the target REST API is **not** a gateway failure — it is returned as an ordinary `tools/call` result with `isError: true` and the response body as content, mirroring the MCP protocol's own `isError` convention. Only a connection/timeout failure, a missing required argument, or a credential that fails to resolve raises a gateway-level error. |
| REQ-API-08 | Every REST API service's credentials (API key, bearer token, basic auth, or OAuth2 client-credentials client id/secret) are resolved through the existing Secret Provider layer (§7) by name — never a raw environment variable, unlike the MCP Server Registry's own outbound auth (REQ-REG-03). An OAuth2 client-credentials token is cached (Valkey) until shortly before it expires, so a busy tool doesn't re-authenticate on every call. |
| REQ-API-09 | A REST-backed `tools/call` is additionally rate-limited per API service (`api_service.rate_limit_per_window`, falling back to the gateway default), on top of the existing per-tool limit (REQ-MCPRATE-01) — a caller hammering one REST-backed tool can't starve traffic to the rest of that same backend's endpoints. |
| REQ-API-10 | `mcp_request_logs` gains `execution_type`, `api_service_id`, `endpoint_path`, and `status_code`, populated only for REST-backed calls (`server_id` already covers MCP calls) — the same table as REQ-MCPOBS-01, not a parallel one. |
| REQ-API-11 | `access_policies.allowed_tool_names` gates which specific tool names (MCP- or REST-backed alike) a policy permits, evaluated by `PolicyEngine` identically regardless of tool kind — this is how "only `finance` roles may call `create_payment`" is expressed. Evaluation stops at the tool name; it does not inspect the call's actual arguments (see §13). |

---

## 7. Functional Requirements — Secret Provider Layer

Provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, and any MCP server's own outbound credential) are never plain env vars on `Settings` and never persisted in Postgres. They are resolved at call time through a pluggable **Secret Provider** abstraction (`backend/app/secrets/`). Full detail: [secret-management.md](secret-management.md).

| ID | Requirement |
|---|---|
| REQ-SEC-01 | A `SecretProvider` interface (`get_secret`/`set_secret`/`delete_secret`, each tenant-scopable) is implemented independently by five backends — Infisical (default), AWS Secrets Manager, Google Secret Manager, Azure Key Vault, HashiCorp Vault — selected at startup by `SECRET_PROVIDER`. No call site outside `app/secrets/` imports a concrete provider class or a provider SDK. |
| REQ-SEC-02 | `services/routing/model_registry.py` resolves every LiteLLM target's credentials through the Secret Provider layer at call time, never from `Settings`. |
| REQ-SEC-03 | A short-lived cache (`SecretService`, backed by Valkey, default TTL 300s, key `secret:{tenant}:{secret_name}`) sits in front of the provider so the hot chat/embedding path doesn't make an outbound call to the secret backend on every request. This is a deliberate, bounded-risk tradeoff, not an oversight — see the Security Model section of docs/secret-management.md. |
| REQ-SEC-04 | `POST /admin/secrets/rotate` invalidates the cache for a given secret (+ tenant) and force-refetches from the provider, so a credential rotated at the source takes effect without waiting out the cache TTL or restarting the gateway. |
| REQ-SEC-05 | No API response ever contains a secret value — only `{"provider": ..., "status": "configured"\|"not_configured"\|"error"}`. No secret value is ever logged. |
| REQ-SEC-06 | Every administrative secret operation (status check, rotate) writes a `secret_audit_log` row (tenant, operation, provider, secret name, acting user, status) — the table has no column that could ever hold a value. |
| REQ-SEC-07 | Every provider method accepts an optional `tenant` for multi-tenant secret isolation, mapped to that backend's own namespacing concept (Infisical secret path, AWS/Vault name prefix, GCP/Azure name suffix). Not yet wired through live chat/embeddings routing (`tenant` defaults to the shared namespace there) — see docs/secret-management.md's scope note. |

---

## 8. Functional Requirements — Identity Provider Layer

Human (dashboard/admin) authentication is never coupled to Keycloak specifically. A pluggable **Identity Provider** abstraction (`backend/app/identity/`) validates bearer tokens and maps them to a provider-agnostic `UserIdentity`. Full detail: [identity-provider-architecture.md](identity-provider-architecture.md).

| ID | Requirement |
|---|---|
| REQ-ID-01 | An `IdentityProvider` interface (`validate_token`/`get_user_info`/`get_roles`/`get_groups`, plus a concrete `get_user_identity` composition) is implemented independently by six backends — Keycloak (default), Microsoft Entra ID, Auth0, Okta Workforce Identity Cloud, AWS IAM Identity Center, Google Identity Platform — selected at startup by `IDENTITY_PROVIDER`. No call site outside `app/identity/` imports a concrete provider class. |
| REQ-ID-02 | JWT signature/issuer/audience/expiry validation (`validate_oidc_jwt`) is implemented exactly once and shared by all six providers — each provider supplies its own JWKS URL/issuer/audience, never its own copy of the validation logic. |
| REQ-ID-03 | Every provider maps its own role/group claim shape (Keycloak's `realm_access.roles`, Entra's `roles`, Auth0's namespaced custom claim, Okta's `groups`, ...) onto the identical `UserIdentity.roles`/`.groups` fields — callers outside `app/identity/` never see a provider-specific claim name. |
| REQ-ID-04 | `AuthMiddleware` resolves *which* provider to use per request: it peeks the token's unverified `iss` claim, checks `tenant_identity_config` for a matching tenant override, and falls back to the global `IDENTITY_PROVIDER` default if none matches — enabling different tenants to run different IdPs against one gateway process. |
| REQ-ID-05 | The internal `User` row is looked up by `(identity_provider, external_sub)`, not `external_sub` alone — a subject id is only unique within the provider that issued it. |
| REQ-ID-06 | `PolicyEngine` (RBAC/ABAC) evaluates `access_policies` (`allowed_roles`, `allowed_identity_providers`, `allowed_tool_names`, advisory-only `max_tokens`) generically over `UserIdentity.roles`/`.provider` and the tool being called, never a concrete `IdentityProvider` or tool implementation. No active policy for a project means unrestricted; any matching policy grants access. Wired into `POST /mcp`'s `tools/call` for IdP-authenticated human callers — `chat.py`/`embeddings.py` remain API-key-only by prior design and are not gated by it. See §6.10 for the tool-name-scoped extension. |
| REQ-ID-07 | No password is ever stored or forwarded by this layer; no raw token or its claims are ever logged. |

---

## 9. Data Model

| Table | Purpose | Key relationships |
|---|---|---|
| `organizations` | Top-level tenant | — |
| `projects` | Unit of billing/access under an org | → `organizations` |
| `users` | Human accounts, linked to whichever Identity Provider authenticated them | → `organizations` (nullable); natural key is `(identity_provider, external_sub)` |
| `project_users` | Time-bounded project membership | → `projects`, `users` |
| `api_keys` | Hashed machine credentials, scoped to a project, carry free-form `scopes` | → `projects` |
| `provider_configs` | Which LLM providers are enabled + credential reference | — |
| `model_pricing` | Admin-editable per-1k USD pricing per provider/model | — |
| `routing_rules` | `model_alias`/`capability` → ordered provider targets + strategy | → `projects` (nullable, for scoping) |
| `request_logs` | One row per chat/embedding request | → `api_keys`, `users`, `projects`, `organizations` |
| `guardrail_results` | One row per guardrail check (prompt or response direction) | → `request_logs` |
| `cost_ledger` | One row per request's computed USD cost | → `request_logs`, `projects`, `organizations`, `users` |
| `budgets` | Spend ceiling + alert threshold, scoped to org/project/user | → `organizations`/`projects`/`users` (at least one) |
| `mcp_servers` | The MCP Server Registry | — |
| `mcp_tools` | Tool Registry: `tool_name` (unique) → exactly one of `server_id` or `api_endpoint_id`, per `source_type` | → `mcp_servers`, `api_endpoints` |
| `mcp_sessions` | `client_session_id` → per-server session id map | → `projects`, `api_keys` (nullable) |
| `mcp_request_logs` | One row per `POST /mcp` call | → `api_keys`, `users`, `projects`, `mcp_servers`, `api_services` |
| `api_services` | The API (REST) Service Registry — see §6.10 | — |
| `api_endpoints` | One registered REST endpoint → its paired `mcp_tools` row | → `api_services` |
| `secret_audit_log` | Metadata-only audit trail for secret operations — **no column ever holds a secret value** | → `users` (nullable) |
| `tenant_identity_config` | Per-tenant Identity Provider override, resolved by matching a token's issuer | — |
| `access_policies` | RBAC/ABAC gate (`allowed_roles`, `allowed_identity_providers`, advisory `max_tokens`) | → `projects` (nullable = global policy) |

All schema changes go through Alembic migrations — there is no hand-edited DDL.

---

## 10. API Reference (summary)

| Domain | Endpoints | Auth |
|---|---|---|
| LLM traffic | `POST /v1/chat/completions`, `POST /v1/embeddings` | API key |
| Auth | `POST /v1/auth/token/exchange` | Identity-Provider-authenticated user |
| Keys | `GET/POST /v1/keys`, `DELETE /v1/keys/{id}` | Identity-Provider-authenticated user (delete: admin/team_lead) |
| Org/Project/User mgmt | `/v1/organizations`, `/v1/projects`, `/v1/users`, `/v1/project-users` | admin (projects/membership: admin or team_lead) |
| Provider/Pricing/Routing | `/v1/provider-configs`, `/v1/model-pricing`, `/v1/routing-rules` | admin |
| Budgets | `/v1/budgets` | admin or team_lead |
| Usage/Logs | `GET /v1/usage/summary`, `GET /v1/logs` | any authenticated user |
| Health | `GET /health`, `GET /ready` | none |
| MCP protocol | `POST /mcp` | API key or Identity-Provider-authenticated user, scope-gated per method |
| MCP registry | `GET/POST/PUT/DELETE /mcp/servers`, `POST /mcp/servers/{id}/health-check`, `GET /mcp/servers/{id}/stats` | admin |
| MCP tools | `GET /mcp/tools`, `POST /mcp/tools/sync` | scope `tool:read` (list) / admin (sync) |
| MCP sessions | `GET /mcp/sessions`, `GET /mcp/sessions/{client_session_id}` | any authenticated user |
| API Registry | `GET/POST /mcp/api-services`, `PUT/DELETE /mcp/api-services/{id}`, `GET/POST /mcp/api-services/{id}/endpoints`, `PUT/DELETE /mcp/api-services/{id}/endpoints/{endpoint_id}` | admin |
| Secrets | `GET /admin/secrets/providers`, `GET /admin/secrets/status`, `POST /admin/secrets/rotate`, `GET /admin/secrets/audit-log` | admin |
| Identity | `GET /admin/identity/providers`, `GET/POST/PUT/DELETE /admin/identity/tenant-configs`, `GET/POST/PATCH/DELETE /admin/identity/access-policies` | admin |

Full request/response schemas are in Swagger UI (`/docs`) at runtime — this table is for navigation, not a substitute for it.

---

## 11. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-SEC-01 | No raw provider credential or MCP server secret is ever persisted in Postgres, logged, or returned by any API. LLM provider credentials are resolved through the pluggable Secret Provider layer (§7); MCP server credentials store only an environment-variable *reference* (`credential_ref`), never the value. |
| NFR-SEC-02 | API keys are hashed at rest; only a short prefix is retained in plaintext for display/identification. |
| NFR-SEC-03 | All DB access goes through async SQLAlchemy sessions scoped to a request (via FastAPI `Depends`) — never a module-level global session. |
| NFR-PERF-01 | Logging and cost-ledger writes must never add latency to the client-visible response — they run as post-response background tasks. |
| NFR-PERF-02 | A successful, cacheable response must skip provider routing entirely on a cache hit. |
| NFR-REL-01 | A single failing MCP server must never prevent other servers from being discovered, health-checked, or used. |
| NFR-REL-02 | Every mutating admin action (schema change) goes through an Alembic migration, never a manual `ALTER TABLE`. |
| NFR-OBS-01 | Every request that reaches this gateway (LLM or MCP) is logged with enough detail (identity, resolved target, latency, status) to answer "who called what, when, and what happened" without external tooling. |

---

## 12. Key Architecture Decisions (and why — don't relitigate without re-reading this)

1. **LiteLLM is embedded in-process, not run as a network sidecar.** A routing rule's target list is turned into a LiteLLM `Router` per call; retries/fallback across targets are LiteLLM's job, not hand-rolled HTTP retry logic here.
2. **Identity Providers authenticate humans only; Keycloak is the default, not the only option.** Machine-to-machine traffic (agents, backend services) always uses API keys, never an Identity Provider token — this keeps the machine-auth path simple (hash comparison, no JWKS/network round-trip) and keeps RBAC roles meaningful only for people. Which concrete IdP validates a human's token is a pluggable, per-tenant decision (§8) — the rest of the app only ever depends on the resulting `UserIdentity`, never a specific provider.
3. **Guardrails are a pluggable adapter (`GuardrailsClient`), not an inline HTTP call.** The real guardrails vendor's contract is unconfirmed; the gateway is built against the interface so swapping the implementation later never touches `chat.py`/`embeddings.py`.
4. **Embeddings are a stateless proxy, not a vector store.** The gateway forwards `input → vector` and prices/logs it; it never persists or searches vectors.
5. **The MCP Gateway owns tool execution end to end; the LLM Gateway is not involved.** These are two independent capabilities of one backend that happen to share auth/logging/rate-limit infrastructure — an LLM chat call never triggers a tool call internally (there is no agent loop in this codebase; see §13).
6. **Health (`health_status`) and administrative status (`status`) are separate fields on `mcp_servers`.** Conflating "an operator turned this off" with "this server stopped responding" would make it impossible to distinguish planned maintenance from an outage in the registry UI, and would make re-enabling a server after maintenance silently depend on it happening to still be reachable.
7. **`tool_name` is unique gateway-wide**, not namespaced per server. Routing a `tools/call` purely from the JSON-RPC body (no server hint in the URL) requires an unambiguous name → server mapping; the tradeoff is documented in REQ-DISC-02 rather than hidden.
8. **REST APIs are exposed as MCP tools through the same Tool Registry and the same `POST /mcp` entry point, not a second execution path.** An agent calling `tools/call` never knows or needs to know whether `get_customer` runs against an MCP server or a REST API — auth, scopes, rate limiting, RBAC/ABAC, and observability are the exact same code paths for both, branching only on `mcp_tools.source_type` (§6.10). This is a deliberate extension of decision 5, not a parallel gateway.

---

## 13. Out of Scope / Deferred (do not silently "complete" these)

These are intentionally not implemented in the current version. If asked to add one, treat it as a deliberate scope decision requiring sign-off, not a bug fix:

- **True token streaming** with incremental guardrail scanning, for both chat completions and MCP tool responses — both currently buffer the full response before returning.
- **Hard budget enforcement** — budgets are visible/advisory only; nothing blocks a request for being over budget.
- **Encrypted-at-rest provider/MCP credentials** — today, only a reference (env var name) is stored in the DB; the actual secret lives in server environment config.
- **An agent loop** — this codebase does not decide *which* tool to call or orchestrate multi-step tool use. It routes and governs calls that something else (an external agent framework) decides to make.
- **MCP transports other than Streamable HTTP** — no STDIO, no SSE-only servers.
- **Kubernetes manifests / CI pipeline** — deployment today is Docker Compose only.
- **Argument-level (ABAC) policy evaluation** — `PolicyEngine`/`AccessPolicy.allowed_tool_names` (§6.10) gates on role, identity provider, and tool name, not on the actual call arguments (e.g. "block `create_payment` if `amount > $10,000`" is not possible today). A rule engine over tool arguments is a real feature, not a small addition.
- **OpenAPI/Swagger import for the API Registry** — REST endpoints are registered one at a time via the admin API/UI; there is no bulk import from an OpenAPI spec.
- **Per-endpoint (as opposed to per-service) rate limits or retry policy in the API Registry** — both are configured at the `api_services` level and apply to every endpoint registered under it.

---

## 14. Frontend Requirements (summary)

A React + Tailwind SPA, role-gated identically to the backend (a page hides itself if the logged-in user's role can't call its endpoints — this is convenience, not the security boundary, which is always server-side).

| Page | Purpose | Roles |
|---|---|---|
| Dashboard | Landing overview | any |
| API Keys | Issue/revoke keys, set scopes | any (revoke: admin/team_lead) |
| Usage & Cost | Cost/usage aggregates | any |
| Request Logs | Paginated LLM request history + guardrail detail | any |
| MCP Tools / Playground / Sessions | Browse the tool registry, hand-craft JSON-RPC calls, inspect session mappings | any |
| MCP Servers + Server Health Monitor | Registry CRUD, active/inactive toggle, manual health check, per-server usage stats | admin |
| API Services (REST) | API Registry CRUD (services + endpoints), the REST Tool Builder that generates each endpoint's MCP tool | admin |
| Routing Rules, Organizations, Users, Provider Configs, Model Pricing | Admin configuration | admin |
| Budgets, Projects | Team-level management | admin, team_lead |

There is no dedicated embeddings page — it's a machine-to-machine capability, surfaced only through the Usage/Logs capability filters.

---

## 15. How to Verify a Change Against This Document

Before merging anything non-trivial:

1. Which requirement ID(s) does this change affect? If none, it's probably a refactor — say so explicitly in the PR.
2. Does it cross a boundary listed in §12 (e.g. making the LLM Gateway call MCP directly)? That needs a conscious decision, not an incidental one.
3. Does it touch anything in §13? Confirm it's an intentional scope expansion before proceeding.
4. Did it add a new table/column? There must be a corresponding Alembic migration.
5. Did it add a new external call (provider, MCP server, guardrails)? Confirm it happens through the existing pluggable interface for that category, not a new one-off HTTP call.
