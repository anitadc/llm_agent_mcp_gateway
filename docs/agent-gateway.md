# Agent Gateway (MVP)

This document covers the Agent Gateway: a governed control plane for
agent-to-agent invocation, built to the same architectural discipline as the
LLM Gateway, MCP Gateway, and API Registry -- reusing the existing Identity,
Secret Provider, and Policy Engine layers rather than inventing parallel ones.

**Scope note up front:** the source specification this was built against
(`docs/agentgateway-req.md`) describes a full standalone, multi-language
platform -- a separate repository, a Rust data-plane, official A2A 1.0
protocol compliance, a Python SDK, a LangGraph integration package, and
Kubernetes/Helm manifests. This implementation is a deliberately scoped-down
**MVP core** living inside this repo's existing FastAPI + React monolith,
covering Agent Registry, Approval Workflow, Trust levels, RBAC/ABAC reuse, and
a governed HTTP-based invocation path. Everything else from the spec is
explicitly **Future Capability** -- see "What's NOT implemented" below.

## Why this exists

The same problem the MCP Gateway solves for tools exists one level up for
agents: once more than one internal or partner agent exists, someone needs a
single place to decide who is allowed to register one, whether it's actually
safe to call, and who's allowed to call it -- without every consumer having to
re-implement that governance itself.

## Architecture

```
Agent Registration (admin API, api/v1/agents.py) -- POST /v1/agents
        |
Approval Workflow (services/agent_gateway/approval_service.py) --
   POST /v1/agents/{id}/submit creates one AgentApprovalTask per configured
   stage (Settings.agent_approval_stages, plus "production" whenever
   risk_class is "high") -- never hard-coded per agent
        |
Human review -- POST /v1/agent-approvals/{task_id}/approve|reject
        |
Publish (services/agent_gateway/agent_registry_service.py) --
   POST /v1/agents/{id}/publish, only once every approval task is approved
        |
Governed Invocation (services/agent_gateway/invocation_service.py) --
   POST /v1/agent-invocations {capability, operation, payload}
      -> resolve active agents serving `capability`, lowest `priority` first
      -> PolicyEngine.evaluate(roles, identity_provider, agent_key=...)
      -> REMOTE_HTTP dispatch to the first agent that clears policy
```

A consumer never specifies a target agent, endpoint, or protocol -- it asks
for a `capability` (e.g. `"pricing"`) and the gateway resolves, authorizes,
and dispatches, exactly the same "consumer independence" principle the MCP
Gateway already applies to tool names.

## Data model

- **`agents`** -- the Agent Registry: `agent_key` (unique), `capabilities`
  (which `InvokeRequest.capability` values resolve to this agent),
  `priority` (lower wins, same ascending convention as `RoutingRule` target
  `weight`), `risk_class`, `trust_level` (T0-T5), `status` (the lifecycle
  state -- see below), `endpoint_url` + `auth_config` (REMOTE_HTTP dispatch
  target and its credentials), and a simplified `card` JSONB blob.
- **`agent_approval_tasks`** -- one row per required review stage
  (`security`/`technical`/`business`/`data_governance`/`production`) for one
  agent registration.
- **`agent_invocations`** -- observability/audit record for every governed
  invocation (capability, resolved agent, authorization decision, status,
  latency), the Agent Gateway analogue of `mcp_request_logs`.
- **`access_policies`** gained `allowed_agent_keys`, extending the existing
  `PolicyEngine` the exact same way `allowed_tool_names` already covers MCP
  and REST-backed tools -- a policy scoped to agents is independent of one
  scoped to tools, even if a name happens to collide between them.

## Lifecycle (MVP simplification)

The full spec's lifecycle is `draft -> submitted -> validating -> under_review
-> approved -> published -> active -> {suspended, deprecated} -> retired`
(plus `rejected`). This MVP treats `submitted`/`validating`/`published` as
instantaneous rather than independently persisted states: Agent Card
validation runs synchronously inside `submit_for_approval` (there is nothing
asynchronous to be "validating" against yet), and `publish` moves an agent
directly from `approved` to `active`. Those three enum values exist in the
schema for forward compatibility but no code path assigns them today -- see
`services/agent_gateway/lifecycle.py` for the full, explicit transition table.

**Registration never implies authorization.** `active` is only an
*eligibility* precondition for `invocation_service.py`'s capability
resolution -- every invocation is still separately gated by the same
`PolicyEngine` that gates MCP `tools/call`, evaluated over `agent_key`.

## Trust levels

`Agent.trust_level` captures T0 (unknown) through T5 (public/untrusted),
matching the spec's model. In this MVP pass, trust is stored and displayed
per agent but does not yet drive an independent routing/eligibility decision
beyond the `PolicyEngine` gate above -- deep trust-based route scoring (the
spec's P2 "Reputation" item) is a **Future Capability**, not silently faked.

## Invocation execution

Only `REMOTE_HTTP` dispatch is implemented: a plain `POST` to `Agent.
endpoint_url` with `{"operation": ..., "payload": ...}`, credentials resolved
through the Secret Provider layer (never a raw environment variable -- the
same choice already made for the API Registry's REST tool credentials). A
non-2xx response from the target agent is **not** a gateway failure -- it's a
completed invocation with `status: error` and the response body as `result`,
mirroring `RestExecutor`'s `is_error` treatment of REST-backed MCP tools.
Only a connection/timeout failure, a missing required field, or an unresolved
credential raises a gateway-level exception.

No retry, backoff, or circuit breaker is implemented for agent invocations --
the spec's P0 "Resilience" item is intentionally trimmed for this pass (see
below).

## What's NOT implemented (explicit scope boundaries, not oversights)

- **Real A2A protocol compliance** -- no official A2A Agent Card JSON Schema
  validation, no `/.well-known/agent-card.json` serving, no A2A task/message
  semantics, no protocol version negotiation. `AgentRegistryService.
  build_agent_card()` produces a simplified, human-readable JSON blob, not a
  standards-conformant Agent Card.
- **LangGraph same-process Agent Boundary** -- there is no framework
  interceptor; every invocation goes over `REMOTE_HTTP`, even for
  same-process scenarios a real deployment might want to keep in-process.
- **Python SDK / `integrations/langgraph` package** -- consumers call the
  REST API directly; no published client library exists.
- **A separate demo consumer repository** -- not applicable inside this
  monolith; there is no standalone order-agent/pricing-agent/risk-agent demo.
- **Rust data-plane, Kubernetes manifests, Helm charts** -- deployment is
  Docker Compose only, matching the rest of this platform.
- **Resilience beyond a per-call timeout** -- no retry/backoff, no circuit
  breaker, no idempotency-key handling, no dead-letter queue for async
  failures.
- **Argument-level (ABAC) policy evaluation** -- `PolicyEngine`/
  `AccessPolicy.allowed_agent_keys` gates on role, identity provider, and
  agent key, not on the actual invocation payload (see
  `docs/api-registry.md`'s identical scope note for REST-backed tools).
- **Federation, semantic (embedding-based) discovery, reputation scoring** --
  all explicitly P1/P2 in the source spec and untouched here.
- **mTLS, workload identity** -- authentication for human/API-key callers
  reuses the existing Identity Provider and API key layers; there is no
  separate workload-identity or mTLS adapter for agent-to-agent calls.

## Governance reuse (what was deliberately *not* rebuilt)

- **Authentication**: the same `AuthMiddleware`-resolved `Principal` (API key
  or Identity Provider user) gates every Agent Gateway call. API keys need an
  explicit `agent:invoke` scope to call `POST /v1/agent-invocations`, the
  same opt-in convention as MCP's `tool:execute`.
- **Authorization**: `PolicyEngine`, extended with `allowed_agent_keys`
  rather than a second policy engine.
- **Secrets**: `SecretService`, exactly as the API Registry uses it for REST
  tool credentials.
- **Observability**: `agent_invocations` follows the identical
  "`BackgroundTask` after the response is sent" discipline as
  `mcp_request_logs`/`request_logs`.

## Admin API surface

| Endpoint | Purpose |
|---|---|
| `GET/POST /v1/agents`, `GET/PATCH /v1/agents/{id}` | Registry CRUD (admin) |
| `GET /v1/agents/{id}/agent-card` | Simplified Agent Card |
| `POST /v1/agents/{id}/submit` | Validate + create approval tasks |
| `GET /v1/agents/{id}/approvals` | Approval tasks for one agent |
| `POST /v1/agents/{id}/publish` \| `/suspend` \| `/reactivate` \| `/deprecate` \| `/retire` | Lifecycle actions |
| `GET /v1/agent-approvals` | Pending tasks across all agents |
| `POST /v1/agent-approvals/{task_id}/approve` \| `/reject` | Approval decisions |
| `POST /v1/agent-invocations` | The consumer-facing governed invoke |
| `GET /v1/agent-invocations` | Invocation audit trail (any authenticated caller, like `GET /v1/logs`) |

## Admin UI

**Agent Registry** (`/agents`) -- register agents, inspect approval tasks and
the simplified Agent Card inline, and trigger the next available lifecycle
action for the agent's current status. **Agent Approvals** (`/agent-approvals`)
-- every pending review-stage task across all agents, with approve/reject and
an optional decision reason.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `AGENT_APPROVAL_STAGES` | `security,technical,business` | Comma-separated required stages; `production` is always added on top when `risk_class` is `high` |
| `AGENT_INVOCATION_TIMEOUT_SECONDS` | `10.0` | Per-call HTTP timeout for `REMOTE_HTTP` dispatch |
| `AGENT_DEFAULT_RATE_LIMIT_PER_WINDOW` | `60` | Per-`(caller, capability)` sliding-window limit on `POST /v1/agent-invocations`, same Valkey-backed `RateLimitService` the MCP Gateway uses |
