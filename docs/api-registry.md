# API Registry — Exposing Enterprise REST APIs as MCP Tools

This document covers the API Registry (`backend/app/api_registry`-equivalent
code lives under `services/api_registry/`, `db/models/api_service.py` +
`api_endpoint.py`, `api/v1/api_services.py`): the extension that lets
enterprise REST APIs be invoked through the MCP Gateway as ordinary MCP tools,
alongside native MCP-server tools. For the MCP Gateway's overall architecture
see [architecture.md](architecture.md); for the RBAC/ABAC policy layer this
reuses see [identity-provider-architecture.md](identity-provider-architecture.md).

## Why this exists

Before this extension, the only way to expose a capability to an agent through
this gateway was to stand up (or already have) an actual MCP server. Most
enterprise capabilities live behind a plain REST API, not an MCP server. The
API Registry closes that gap without creating a second, parallel execution
path: a registered REST endpoint becomes a row in the exact same `mcp_tools`
table an MCP server's tools live in, discovered and invoked through the exact
same `POST /mcp` JSON-RPC endpoint. An agent never knows or cares whether
`get_customer` is backed by an MCP server or a REST call — it calls
`tools/call` either way.

## Architecture

```
Application/agent
      |
POST /mcp {method: "tools/call", params: {name, arguments}}
      |
mcp_gateway.py -- resolves tool via RoutingEngine (unchanged entry point)
      |
      +-- source_type=mcp  --> existing MCP server dispatch (unchanged)
      |
      +-- source_type=rest --> ApiRegistryService.execute()
                                     |
                               RestExecutor
                                     |
                          Enterprise REST API (base_url)
```

- **`api_services`** — the REST API Service Registry: one row per enterprise
  REST backend (`base_url`, `authentication_type`/`auth_config`, static
  `headers`, `timeout_seconds`, `retry_policy`, `rate_limit_per_window`,
  `status`). Mirrors `mcp_servers` on purpose.
- **`api_endpoints`** — one registered REST endpoint per row (`method`, `path`,
  `parameters`). `tool_name` is unique gateway-wide, same rule as
  `mcp_tools.name`. Registering an endpoint (`POST
  /mcp/api-services/{id}/endpoints`) immediately creates its paired `mcp_tools`
  row — there is no separate discovery/sync step, unlike MCP servers, because
  REST endpoints are explicitly declared by an admin, not introspectable the
  way `tools/list` is for an MCP server.
- **`mcp_tools`** now carries a `source_type` (`mcp` | `rest`) and points at
  exactly one of `server_id` or `api_endpoint_id`, enforced by a CHECK
  constraint (`chk_mcp_tool_source`). `RoutingEngine.resolve_tool` and
  `McpToolRepo.search`'s availability filter both branch on this field so a
  single code path serves both tool kinds.
- **`RestExecutor`** (`services/api_registry/rest_executor.py`) builds the
  actual HTTP request: substitutes `{placeholder}` path parameters, buckets
  the remaining arguments into query/header/body per each parameter's
  registered `location`, injects credentials, and converts the HTTP response
  into the standard MCP `{"content": [{"type": "text", "text": ...}]}` shape
  via `schema_converter.rest_response_to_mcp_content`.
- **`ApiRegistryService`** (`services/api_registry/api_registry_service.py`)
  is the facade: registers/updates/deletes endpoints (keeping each one's
  paired `mcp_tools` row in sync), and dispatches `execute()` to
  `RestExecutor`.

## Credential handling

REST API credentials are resolved through the existing **Secret Provider
layer** (`SecretService.get_secret`), never a plain environment variable —
`auth_config` only ever stores a secret *name* (`credential_ref`,
`username_ref`/`password_ref`, `client_id_ref`/`client_secret_ref`), exactly
like `ProviderConfig.credential_ref`. This is a deliberate improvement over
the MCP Server Registry's outbound auth (`mcp_client.py`'s
`_resolve_auth_headers`, which reads a raw environment variable directly) —
the spec for this feature required secret-management-backed storage, so the
REST path does not repeat that older asymmetry.

Four authentication types are supported: `none`, `api_key`, `bearer`, `basic`,
and `oauth2_client_credentials` (client-credentials token exchange, with the
resulting bearer token cached in Valkey per service until it's close to
expiring).

## Tool execution result semantics

A non-2xx HTTP response from the target REST API is **not** treated as a
gateway failure — it comes back as a normal `tools/call` result with
`isError: true` and the response body as content (mirroring the MCP
protocol's own `isError` convention for a tool that ran but failed). A 404
"customer not found" is useful information for the calling agent, not a
broken gateway. Only a connection/timeout failure, a missing required
argument, or a credential that fails to resolve raises a gateway-level
`ProviderError`/`BadRequestError`.

GET requests get the same bounded transport-error retry MCP's
`initialize`/`tools/list` calls get; POST/PUT/DELETE are never retried, for
the same reason MCP's `tools/call` isn't — see
[architecture.md](architecture.md)'s request-lifecycle notes.

## Governance reuse

Nothing about auth, rate limiting, or policy enforcement was rebuilt for REST
tools — the exact same mechanisms MCP tools already go through are reused:

- **Authentication**: the same `AuthMiddleware`-resolved `Principal` (API key
  or Identity Provider user) gates every `tools/call`, REST-backed or not.
- **Authorization**: the same `tool:read`/`tool:execute` scopes.
- **RBAC/ABAC**: `PolicyEngine`/`AccessPolicy` now also carries
  `allowed_tool_names` — a policy can scope itself to specific tool names
  (e.g. "only `finance` roles may call `create_payment`"), evaluated
  identically regardless of whether that tool is MCP- or REST-backed. This
  extends the existing single wiring point (MCP `tools/call` for
  Identity-Provider-authenticated human callers) rather than adding a second one.
- **Rate limiting**: the existing per-tool key (`mcp-tool:{caller}:{tool_name}`)
  still applies; a second, REST-specific key
  (`mcp-restapi:{api_service.name}`) additionally caps traffic to the whole
  REST backend, using `ApiService.rate_limit_per_window` or the gateway
  default.
- **Observability**: `mcp_request_logs` gained `execution_type`,
  `api_service_id`, `endpoint_path`, and `status_code` columns, populated
  only for REST-backed calls (`server_id` already covers MCP calls) — the
  same table, not a parallel one.

## What's NOT implemented (explicit scope boundaries)

- **Argument-level (ABAC) policy evaluation** — e.g. "block `create_payment`
  if `amount > $10,000`" is not implemented. `PolicyEngine` gates on role,
  identity provider, and tool name, not on the actual call arguments. A rule
  engine over tool arguments is a real feature, not a small addition — this is
  a **Future Capability**, not a silent gap.
- **OpenAPI/Swagger import** — endpoints are registered one at a time via the
  admin API/UI; there is no bulk import from an OpenAPI spec. **Future
  Capability.**
- **Streaming REST responses** — like every other response path in this
  gateway, a REST call's response is fully buffered before being returned.
- **Per-endpoint (as opposed to per-service) rate limits or retry policy** —
  both are configured at the `ApiService` level and apply to every endpoint
  registered under it.
