# FAQ — Agents, Tool Calling, and the LLM/MCP Gateways

This FAQ answers the questions that come up most when a team member is trying to understand how an AI agent actually invokes tools through this system. For the formal requirements, see [REQUIREMENT.md](REQUIREMENT.md); for setup/usage, see [../README.md](../README.md).

---

## Q1. If an AI agent wants to invoke a tool, what are the steps inside the gateway?

Tracing a single `tools/call` request through [`mcp_gateway.py`](../backend/app/api/v1/mcp_gateway.py):

### Prerequisite (one-time, before any agent calls anything)

The tool must already exist in the registry, via one of two paths:

- **MCP-backed**: an admin registered the MCP server (`POST /mcp/servers`) and a discovery sync ran (`POST /mcp/tools/sync`, or the periodic background loop), populating `mcp_tools` with `tool_name → server_id`.
- **REST-backed**: an admin registered a REST API service (`POST /mcp/api-services`) and one of its endpoints (`POST /mcp/api-services/{id}/endpoints`) — this immediately creates the paired `mcp_tools` row (`tool_name → api_endpoint_id`), no separate sync step. See [api-registry.md](api-registry.md).

An agent never needs to know or care which path a given tool came from — both show up identically in `tools/list`/`GET /mcp/tools` and are invoked the same way in step 2 below.

### 1. Transport & identity — middleware (runs before the handler)

`request_id` → CORS → **auth middleware** (validates the API key hash or Keycloak JWT, attaches a `Principal`) → **rate-limit middleware** (coarse per-API-key limit on the `/mcp` path).

### 2. Agent sends the call

```
POST /mcp
Authorization: Bearer gw_...
Mcp-Session-Id: <optional, from a prior call>

{"jsonrpc":"2.0","id":"1","method":"tools/call","params":{"name":"get_top_threats","arguments":{...}}}
```

### 3. Inside the handler, in order

| Step | What happens | Fails as |
|---|---|---|
| 3a. Scope check | `_require_scope(principal, "tool:execute")` — API key must have been issued with this scope; Keycloak users get it by role | `403 Forbidden` |
| 3b. Extract tool name | `params.name` must be present | `400 Bad Request` |
| 3c. Per-tool rate limit | `RateLimitService.check("mcp-tool:{caller}:{tool_name}", ...)` — a Valkey sliding window, separate from the coarse endpoint limit | `429 Rate Limited` |
| 3d. Registry lookup + gate | `routing_engine.resolve_tool(tool_name)` — looks up the tool's `source_type` and target, requiring `tool.enabled` **and**, for an MCP-backed tool, `server.status == active` **and** `server.health_status == healthy`, or, for a REST-backed tool, `api_service.status == active` | `404 Not Found` |
| 3e (MCP only). Session resolution | `session_manager.get_or_create(client_session_id, ...)` — finds/creates the client↔server session mapping row | — |
| 3f (MCP only). Ensure a live server session | If no `server_session_id` recorded yet for this server, `health_checker.probe(server)` runs `initialize` (this doubles as the liveness check) and the new session id is persisted | JSON-RPC `error` (still HTTP 200) if unreachable |
| 3g. Forward the call | **MCP-backed**: `mcp_client.call_tool(server, session_id, request_id, tool_name, arguments)` — injects the server's outbound auth header (resolved from `auth_config.credential_ref` → env var), POSTs to `server.base_url`, **no retry**. **REST-backed**: a per-API-service rate limit is checked, then `RestExecutor.execute(service, endpoint, arguments)` — substitutes path params, buckets the rest into query/header/body, injects credentials resolved through the Secret Provider layer, sends the HTTP call (GET retries transient transport errors, POST/PUT/DELETE don't) — either way, avoids double-executing a side-effecting tool | `502` on transport failure |
| 3h. Return | **MCP-backed**: if the server's own response has a JSON-RPC `error`, it's forwarded verbatim (still HTTP 200) — that's the *tool's* failure, not the gateway's. **REST-backed**: a non-2xx HTTP response comes back the same way, as `{"content": [...], "isError": true}` — a 404 is useful information for the agent, not a broken gateway. Otherwise the `result` is returned. `Mcp-Session-Id` is echoed in the response header either way | — |

### 4. Logging (after the response is already sent)

A `BackgroundTask` writes one row to `mcp_request_logs` (`tool_name`, `execution_type`, `server_id` or `api_service_id`/`endpoint_path`/`status_code`, `client_session_id`, `status`, `latency_ms`) — never adds latency to the caller.

**Key design point:** steps 3a–3d are *gateway* decisions and always surface as plain HTTP errors, same as every other endpoint. Only once the gateway has agreed to forward the call (past 3d) does anything from the downstream MCP server itself get embedded in the JSON-RPC response body.

If the agent hasn't called `initialize` first, it doesn't need to — step 3f transparently establishes the server session on the first `tools/call` that needs it.

---

## Q2. How does the agent decide *which* tool to invoke — is there an LLM Gateway call involved?

**Short answer: no.** There is no LLM Gateway call in this codebase that decides which tool to invoke — that decision is deliberately kept **outside** both gateways, in whatever external agent/orchestration layer is calling them. This was an explicit constraint when the MCP Gateway was built (no agent loop; see `REQ-INTEG-01` in [REQUIREMENT.md](REQUIREMENT.md)): the LLM Gateway and MCP Gateway are integrated only at the **API-consumer level**, never in-process.

A concrete detail that makes this unambiguous: [`ChatCompletionRequest`](../backend/app/schemas/chat.py#L12-L19) has **no `tools`/`functions` field** at all — just `model`, `messages`, `temperature`, `max_tokens`, `top_p`, `stream`, `user`. So `POST /v1/chat/completions` currently has no built-in bridge to MCP tool schemas; you can't pass MCP tool definitions into a chat call and get back a structured "call this tool" response the way OpenAI's native function-calling works.

What actually happens today is entirely the calling application's job:

```
┌─────────────────────────────────────────────────────────────┐
│  External Agent / Orchestrator  (NOT in this codebase)       │
│                                                                │
│  1. POST /mcp {method:"tools/list"}   ──▶ MCP Gateway         │
│         (discover available tools + their inputSchema)        │
│                                                                │
│  2. Decide what to do next — via its own logic, or by         │
│     calling POST /v1/chat/completions ──▶ LLM Gateway         │
│     (e.g. stuff the tool list into the prompt/system message  │
│     and ask the model to pick one + produce arguments, then   │
│     parse that out of the plain-text completion itself)       │
│                                                                │
│  3. POST /mcp {method:"tools/call"}   ──▶ MCP Gateway         │
│         (execute the tool the agent decided on)                │
└─────────────────────────────────────────────────────────────┘
```

Steps 1 and 3 both go through this gateway (governed, logged, rate-limited). Step 2 — the actual reasoning about *which* tool and *what arguments* — is either:

- a call to `/v1/chat/completions` where the agent manually embeds the tool catalog as text and parses the model's reply itself (works today, but clunky — no structured tool-call output), or
- entirely outside this gateway (a LangChain/custom agent framework calling a provider's native function-calling API directly, then routing only the actual tool execution through `POST /mcp`).

**If you want native OpenAI-style structured tool-calling** (`tools`/`tool_choice` in the request, `finish_reason: "tool_calls"` in the response) wired through the LLM Gateway, that's a real, currently-unimplemented feature — it would mean extending `ChatCompletionRequest`/`ChatCompletionResponse` and `GatewayRouter.complete()` to pass `tools` through to LiteLLM and surface the model's tool-call intent back to the caller, who would then still call `POST /mcp` themselves to execute it. This is a legitimate future scope item, not something already wired up.

---

## Q3. If an agent needs multiple tool calls to accomplish a task, what's the end-to-end flow?

For a task needing several tool calls in sequence, **the orchestration loop lives entirely in the external agent process** — it alternates between the two gateways, call by call. Neither gateway calls the other, and neither gateway "remembers" the task between calls; the agent is the only thing holding state across the loop.

```
Agent process
  │
  ├─ 1. POST /mcp  {method:"tools/list"}         ──▶ MCP Gateway   (discover catalog, once per task/session)
  │
  ├─ 2. POST /mcp  {method:"initialize"}         ──▶ MCP Gateway   (get a Mcp-Session-Id to reuse for this whole task)
  │
  ├─ 3. POST /v1/chat/completions                ──▶ LLM Gateway  (planning turn 1)
  │
  │     ┌── loop until the model stops requesting tools ──┐
  ├─ 4. │ parse completion → "call tool X with {args}"     │  (agent's own logic — see Q2 caveat)
  ├─ 5. │ POST /mcp {method:"tools/call", name:X, args}    ──▶ MCP Gateway   (Mcp-Session-Id header reused)
  ├─ 6. │ append {"role":"tool","content":<result>} to msgs │
  ├─ 7. │ POST /v1/chat/completions with full history      ──▶ LLM Gateway  (planning turn 2, 3, ...)
  │     └───────────────────────────────────────────────────┘
  │
  └─ 8. model returns a final natural-language answer, no further tool request → return to caller
```

### Step-by-step detail

**1. Discover tools** — `POST /mcp` `{"method":"tools/list"}` (or `GET /mcp/tools`), needs `tool:read` scope. Cache the catalog + `inputSchema` for the duration of the task rather than re-fetching per turn.

**2. Establish one session for the whole task** — `POST /mcp` `{"method":"initialize"}`. The gateway broadcasts to every active MCP server, and the response carries an `Mcp-Session-Id` header. **Capture it and send it on every subsequent `tools/call` in this task** — that's what makes step 5's server-side session continuity work (see [session_manager.py](../backend/app/services/mcp/session_manager.py)); skip this and the gateway will silently establish a session on the first `tools/call` anyway, but you lose the ability to pin the whole multi-step task to one deliberate session.

**3/7. Ask the LLM what to do next** — `POST /v1/chat/completions`. Same caveat as Q2: no `tools`/`tool_choice` field exists on this request today, so the agent must:
- embed the tool catalog (names + `inputSchema`) as text in the system/user prompt,
- pick its own convention for the model's reply (e.g. `respond with {"tool": "...", "arguments": {...}}` or `FINAL_ANSWER: ...`),
- parse that convention out of the plain completion text itself.

The schema does already support feeding a tool's result back in as `{"role": "tool", "content": "..."}` — `tool` is a valid `ChatMessage.role` value — but there's no `tool_call_id` linkage the way OpenAI's wire format has one, so if multiple tool calls are in flight, correlating them is the agent's responsibility, not something the API shape carries for you.

**4. Parse the model's decision** — entirely agent-side logic, not gateway logic.

**5. Execute the chosen tool** — `POST /mcp` `{"method":"tools/call", "params":{"name":..., "arguments":...}}` with `Mcp-Session-Id` from step 2, needs `tool:execute` scope. Internally this goes through everything in Q1: scope check → per-tool rate limit → registry active+healthy gate → session resolution → forward → log.

**6. Feed the result back** — append it as a new message, growing the conversation history the same way any ReAct-style loop does.

**8. Terminate** — when the model's reply doesn't request another tool, return it as the final answer. Nothing in either gateway decides this for you.

### What this means practically

- **N tool calls ⇒ roughly N+1 chat-completion calls** in a typical plan→act→observe loop — each is a full round trip, each is separately rate-limited/logged/costed.
- **Every tool call in the loop should carry the same `Mcp-Session-Id`** if the MCP servers are stateful, or you lose session continuity between calls.
- **No expiry on `mcp_sessions` rows currently exists** — worth flagging as a gap if agents run long-lived tasks; rows persist indefinitely unless something is added to clean them up.
- If you want the model itself to emit structured tool calls (rather than the agent hand-parsing text), that requires extending `ChatCompletionRequest`/`Response` and `GatewayRouter.complete()` to pass `tools` through to LiteLLM — a real, currently-unimplemented enhancement, not something already wired up.

---

## Q4. Can I expose a plain REST API as a tool without standing up an MCP server?

**Yes** — this is what the API Registry is for (`backend/app/db/models/api_service.py`/`api_endpoint.py`, `services/api_registry/`). An admin registers the REST backend once (`POST /mcp/api-services` — base URL, auth type, timeout, retry policy) and then registers each endpoint they want callable (`POST /mcp/api-services/{id}/endpoints` — method, path, parameters). Registering an endpoint **immediately** creates its paired `mcp_tools` row — there is no separate discovery/sync step the way MCP servers need, because a REST endpoint isn't something the gateway can introspect the way `tools/list` lets it for an MCP server.

From the agent's side, nothing changes: the tool shows up in `tools/list`/`GET /mcp/tools` next to every MCP-backed tool, with an auto-generated `inputSchema`, and is invoked with the exact same `POST /mcp {method:"tools/call"}` shape. The agent has no way to tell — and no reason to care — whether `get_customer` runs against an MCP server or a REST API; that's the entire point of the abstraction. See [api-registry.md](api-registry.md) for the full design, including how credentials are resolved (through the Secret Provider layer, never a raw env var) and why a non-2xx REST response comes back as a tool result (`isError: true`) rather than a gateway failure.

## Q5. Does RBAC/ABAC (AccessPolicy) apply to REST-backed tools the same way it does to MCP tools?

Yes, identically — `PolicyEngine.evaluate()` is passed the `tool_name` regardless of which kind of tool it is, and `AccessPolicy.allowed_tool_names` (if set) restricts a policy to specific tool names without needing to know whether that name resolves to an MCP server or a REST endpoint. The one thing this does **not** do is inspect the call's actual arguments — a policy can say "only `finance` roles may call `create_payment`" but not "...and only if `amount < 10000`"; that's a documented **Future Capability**, not a silent gap (see [api-registry.md](api-registry.md)'s scope notes).
