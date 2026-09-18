# FAQ

Operational questions that come up running this stack locally (Docker Compose). See
`README.md` for the base setup flow and `doc/HLD.md`/`doc/LLD.md` for architecture.

---

### The Identity Providers / Secret Providers admin pages show most backends as "down" — what does that mean?

It's not a live health/connectivity check — it's a **static config-presence check**
(`is_provider_available` in `app/identity/factory.py` and `app/secrets/factory.py`).
"Down"/"not configured" just means the required settings for that backend are empty,
which is the default in `docker-compose.yml` for everything except the one active
default (Keycloak for identity, Postgres for secrets).

**To activate another Identity Provider:**

| Provider | Required setting(s) |
|---|---|
| Microsoft Entra ID | `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` |
| Auth0 | `AUTH0_DOMAIN` (+ `AUTH0_AUDIENCE`/`AUTH0_CLIENT_ID` for real validation) |
| Okta Workforce Identity Cloud | `OKTA_DOMAIN` |
| AWS IAM Identity Center | `AWS_SSO_REGION` (+ `AWS_SSO_INSTANCE_ARN`) |
| Google Identity | `GOOGLE_CLIENT_ID` (+ optional `GOOGLE_WORKSPACE_DOMAIN`) |

Two ways to actually use one, after filling in its settings and redeploying:

1. **Replace the global default** — set `IDENTITY_PROVIDER` (in `docker-compose.yml`'s
   `tcsaigateway-backend` environment) to `entra`/`auth0`/`okta`/`aws_identity`/`google`. Only
   one provider can be the global default at a time.
2. **Run it alongside Keycloak** — leave `IDENTITY_PROVIDER=keycloak` and add a row under
   **Tenant identity configs** on the same page (`{tenant_id, provider, issuer,
   configuration}`). The gateway routes each incoming token to a provider by matching its
   (unverified) `iss` claim, so multiple providers can be active simultaneously, each
   scoped to different tenants.

**Caveat that applies either way**: these providers only *validate* a token already
issued elsewhere (JWKS signature/issuer/audience check) — the frontend only has login UI
wired for Keycloak (`keycloak-js`). Activating another provider means either an external
client obtains its own token from that IdP and sends it as `Authorization: Bearer
<token>`, or the frontend gains that provider's login flow (not built yet).

**Secret Providers** work the same way: `postgres` (the default) is "active" because
`SECRET_STORAGE_ENCRYPTION_KEY` is set; `aws`/`gcp`/`azure`/`vault` show unavailable
until their settings (`AWS_SECRETS_REGION`, `GCP_PROJECT_ID`, `AZURE_KEYVAULT_NAME`,
`VAULT_ADDR`, respectively) are filled in and `SECRET_PROVIDER` is switched + redeployed.

---

### What is "Multi-Tenant Identity Configs" on the Identity Providers page, and how do I configure one?

By default, **one** Identity Provider (`IDENTITY_PROVIDER`, Keycloak here) validates
every login for the whole gateway. Multi-Tenant Identity Configs override that **per
tenant**, so different customers/tenants can authenticate through different IdPs against
the same running gateway — e.g. Customer A logs in via their own Microsoft Entra ID
tenant, Customer B still uses the default Keycloak, both hitting the same backend. This
is purely additive: it never replaces the global default, it only carves out exceptions.

Mechanically: on each request, `auth_middleware.py` reads the (unverified) `iss` claim
off the incoming JWT and looks it up in the `tenant_identity_config` table. If a row's
`issuer` matches, that row's `provider` + `configuration` build a one-off
`IdentityProvider` instance for validating *that* request; otherwise it falls back to the
global default.

**To configure one**, click **Add tenant config** and fill in:

| Field | What it is | Example |
|---|---|---|
| Tenant id | Your own internal label for this tenant | `customer-a` |
| Provider | Which `IdentityProvider` implementation to use | `Microsoft Entra ID` |
| Issuer | The exact `iss` value that provider's tokens carry — the lookup key | `https://login.microsoftonline.com/{tenant-guid}/v2.0` |
| Configuration | JSON overriding that provider's `Settings` fields | `{"entra_tenant_id": "...", "entra_client_id": "..."}` |

`configuration` keys must match the `Settings` field names that provider's constructor
actually reads (see the settings table above — Entra needs `entra_tenant_id` +
`entra_client_id`, Okta needs `okta_domain`, etc.). No client secret is ever needed here:
every built-in provider only does JWKS signature/issuer/audience validation on a token
already issued elsewhere, not an OAuth flow initiated by this app.

One practical wrinkle: you need the **issuer** value up front, which usually means an
app/client is already registered with that IdP outside this gateway (e.g. an Entra App
Registration) so you know its tenant/client id and can construct the issuer URL — this
form doesn't create anything on the IdP side, it only tells the gateway how to validate
tokens that IdP already issues.

---

### What is "Access Policies (RBAC / ABAC)" on the Identity Providers page, and how do I configure one?

Access Policies are the RBAC/ABAC gate that controls **who can invoke which MCP tool or
Agent Gateway agent** — a separate, additive authorization layer on top of
authentication. **They are not enforced on plain `/v1/chat/completions` or
`/v1/embeddings` calls** — those only go through Guardrails content-safety checks, not
this gate, despite what the `AccessPolicy` model's docstring implies. Enforcement
(`PolicyEngine.evaluate`) is only wired into `mcp_gateway.py`'s `tools/call` and the
Agent Gateway's `invocation_service.py`.

**Semantics**:
- **No active policy at all for a project → unrestricted.** A fresh deployment with zero
  policies isn't locked out.
- Once at least one policy exists for that project (or globally, `project_id=None`),
  access is granted if it matches **any** policy (OR across policies).
- Within one policy, an **empty** list on `allowed_roles` / `allowed_identity_providers`
  / `allowed_tool_names` / `allowed_agent_keys` means unrestricted on that dimension —
  only non-empty lists actually constrain anything.

Example: "only `finance`-role users may invoke the `create_payment` tool" = a policy
with `allowed_roles: ["finance"]`, `allowed_tool_names: ["create_payment"]`, everything
else left empty.

**To configure one (UI)** — click **Add policy**:

| Field | Meaning |
|---|---|
| Name | Label for the policy |
| Project id | Blank = applies globally; a project id scopes it to that project |
| Allowed roles | Comma-separated (blank = any role) |
| Allowed identity providers | Comma-separated (blank = any provider) |
| Max tokens | Stored but **not enforced yet** (same advisory-only status as Budgets) |

**Gap in the current UI**: `allowed_tool_names` and `allowed_agent_keys` — the fields
that actually restrict *which* tool/agent the policy applies to — aren't exposed in this
form; it only sends role/provider/max_tokens. Set those via the API directly:

```bash
curl -X POST http://localhost:8010/admin/identity/access-policies \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"finance-only","allowed_roles":["finance"],"allowed_tool_names":["create_payment"]}'
```

---

### How do Multi-Tenant Identity Configs and Access Policies (RBAC/ABAC) relate, and how do I set up a full RBAC/ABAC policy?

They're two **independent** features that happen to live on the same Identity Providers
page — not one nested inside the other:

- **Multi-Tenant Identity Configs** decide *which IdentityProvider validates a token*
  (per tenant, by issuer).
- **Access Policies (RBAC/ABAC)** decide *what an already-authenticated caller is
  allowed to do* (which MCP tool/agent).

**The connection point**: every Access Policy has an `allowed_identity_providers`
field, and `PolicyEngine` checks it against `principal.identity.provider` — the same
provider-name string (`"entra"`, `"keycloak"`, etc.) that a Multi-Tenant Identity Config
maps a tenant's issuer to. So once a tenant is set up to authenticate via, say, Entra,
you can write an Access Policy that applies *specifically to Entra-authenticated
callers*, independent of their role.

**Worked example** — "Customer A (authenticated via their own Entra tenant) may only
call the `read_only_report` tool, regardless of their role":

1. **Multi-Tenant Identity Configs** → Add tenant config: `tenant_id=customer-a`,
   `provider=Microsoft Entra ID`, `issuer=https://login.microsoftonline.com/{their-tenant-guid}/v2.0`,
   `configuration={"entra_tenant_id":"...","entra_client_id":"..."}` (see the entry
   above for details).
2. **Access Policies** → since the UI form doesn't expose `allowed_tool_names`, create
   it via the API:
   ```bash
   curl -X POST http://localhost:8010/admin/identity/access-policies \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"name":"customer-a-readonly","allowed_identity_providers":["entra"],"allowed_tool_names":["read_only_report"]}'
   ```

Now any user whose token validated via Entra is restricted to that one tool, while
everyone else (Keycloak-authenticated, or any tenant without a matching policy) is
unaffected — remember, **no active policy for a project means unrestricted**, and it's
OR-across-policies, so this only *adds* a constraint for Entra callers if no broader
policy already covers them.

**Where it's enforced (reminder)**: only `mcp_gateway.py`'s `tools/call` and the Agent
Gateway's `invocation_service.py` call `PolicyEngine.evaluate()` — not plain
`/v1/chat/completions` or `/v1/embeddings`. It only applies to **human/IdP callers**
(`principal.kind == "user"`) — API-key callers already carry their own scopes and are
exempt from this check entirely.

---

### How do I get an API key to invoke the gateway?

API keys are scoped to a **Project**, which belongs to an **Organization** — create both
once, then create the key:

1. Log in at http://localhost:5173.
2. **Organizations** page → create one.
3. **Projects** page → create one under it.
4. **API Keys** page → create a key scoped to that project. The raw key (`gw_...`) is
   shown **once**, at creation — copy it immediately; it can't be retrieved again
   afterward (only revoked).

See `README.md` for the equivalent curl sequence.

---

### What are the steps to configure and use the MCP Gateway?

**Concept**: register external MCP tool servers → the gateway discovers their tools into
a local registry → callers (API keys or logged-in users) invoke any of those tools
through **one** endpoint, `POST /mcp`, with auth/rate-limiting/RBAC enforced centrally
instead of per-server.

**1. Register an MCP server** — **MCP Servers** page → **Add server** (or `POST
/mcp/servers`): name, base URL, description, auth type (`none`/`bearer`/`api_key`),
and for the latter two, a credential ref (+ header name for `api_key`).

**Important caveat**: unlike every other credential in this app, MCP outbound auth is
**not** resolved through the Secret Provider — `credential_ref` names a plain **OS
environment variable on the backend container** (`os.environ.get(credential_ref)` in
`mcp_client.py`), a documented asymmetry, not an oversight. To use `bearer`/`api_key`
auth you must add that env var to `docker-compose.yml`'s `tcsaigateway-backend` block and
redeploy; setting it via the Secrets page does nothing for this.

**2. Health-check it** — a background loop probes every active server every
`MCP_HEALTH_CHECK_INTERVAL_SECONDS` (default 30s), or trigger it manually via the
**Health check** button (`POST /mcp/servers/{id}/health-check`). Status shows on the
**MCP Server Health** page.

**3. Discover its tools** — **MCP Tools** page → **Sync** (`POST /mcp/tools/sync`) runs
`initialize` + `tools/list` against every active server and reconciles the registry.
Also runs automatically every `MCP_DISCOVERY_REFRESH_SECONDS` (default 300s). `GET
/mcp/tools` (Tools Explorer) shows what's callable right now — a tool only appears if
its owning server is active *and* healthy.

**4. Grant the caller MCP scopes** — the part most often missed:
- **API key**: scopes are **opt-in** — a key has no MCP access unless `tool:read`/
  `tool:execute` were included in its `scopes` list *at creation time*.
- **Logged-in user (Keycloak/IdP)**: automatic by role — `viewer` gets `tool:read` only;
  every other role gets `tool:read` + `tool:execute`.

**5. (Optional) Restrict by role/tool** — for human/IdP callers only (API keys already
have scopes), an Access Policy with `allowed_tool_names` further restricts which roles
may call which tool (see the Access Policies entry above).

**6. Call it** — one endpoint, same Bearer auth as everything else:

```bash
curl -X POST http://localhost:8010/mcp -H "Authorization: Bearer gw_..." -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/call","params":{"name":"<tool_name>","arguments":{}}}'
```

No need to call `initialize` first — `tools/call` lazily establishes a per-server
session if one doesn't exist. Reuse the `Mcp-Session-Id` response header on subsequent
calls to skip the repeated handshake. Rate limiting is per `(caller, tool)` pair
(`MCP_DEFAULT_RATE_LIMIT_PER_WINDOW`, default 60/window).

**7. Test it in the UI** — **MCP Playground** page: pick
`initialize`/`tools/list`/`tools/call`, edit the JSON params, Send; it tracks the
returned session id automatically across calls.

---

### What is an "MCP Session" in this application?

It's the gateway's own bookkeeping for something the MCP protocol requires: a stateful
handshake between a client and a server. It solves a specific problem — the gateway
sits between *your* application and potentially *many* different MCP servers, so it
needs to track, per client, which underlying per-server session it's already
established, instead of re-handshaking with every server on every call.

**The data model (`mcp_sessions` table)** — each row is:

| Field | What it holds |
|---|---|
| `client_session_id` | The session id **your app** sees, passed via the `Mcp-Session-Id` header |
| `server_sessions` | A dict `{server_id: server_session_id}` — the *real* session id each individual MCP server handed back when the gateway called that server's own `initialize` |
| `project_id` / `api_key_id` | Which project/key this session belongs to (nullable, for audit/ownership) |
| `last_used_at` | Auto-updated on every use |

So one client session id can map to **several** different server-side session ids
simultaneously — one per MCP server you've talked to during that session.

**Why it exists / how it's used**:
1. First call (no `Mcp-Session-Id` header): the gateway generates a new
   `client_session_id`, creates a row, and returns it in the response header.
2. When a `tools/call` targets a specific MCP server for the first time in that client
   session, the gateway calls that server's own `initialize`, gets back a
   server-issued session id, and stores it in `server_sessions[server_id]`.
3. On a later call reusing the same `Mcp-Session-Id` header against the *same* server,
   the gateway reuses the already-established server session instead of
   re-initializing — cheaper, and preserves whatever stateful context that server
   itself keeps tied to its session (e.g. pagination cursors).
4. It's **persisted in Postgres, not in-memory** — deliberately, so the mapping
   survives a gateway restart rather than forcing every client to re-handshake.

You don't have to manage this yourself: if you never send `Mcp-Session-Id`, the
gateway still works correctly, just without reuse — it creates a fresh session each
call.

**Where you see it**: the **MCP Sessions** page (and `GET /mcp/sessions`) is
**read-only** — just a live viewer into these client↔server mappings for debugging
("why is this call slow / which server session is this tied to"). There's no
create/delete UI, because sessions are entirely a byproduct of `initialize`/
`tools/call` traffic, not something you configure ahead of time.

---

### How do I invoke MCP tools from an external application?

There's no special SDK — any language with an HTTP client works, since it's plain
HTTP + JSON-RPC 2.0. Here's the full integration path:

**1. Get credentials with MCP access.** Scopes are **opt-in per key** — a key created
without them has zero MCP access, even for an admin:

```bash
curl -X POST http://localhost:8010/v1/keys \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"my-app","project_id":"<project-id>","scopes":["tool:read","tool:execute"]}'
```

Store the returned `raw_key` (`gw_...`) in your app's config — it's shown once.

**2. Discover what tools exist:**

```bash
curl http://localhost:8010/mcp/tools -H "Authorization: Bearer gw_..."
```

Each entry returns `name`, `description`, and `input_schema` (a JSON Schema) — build
your `arguments` object to match that schema. Only tools whose owning server/API
service is active *and* healthy show up here.

**3. (Optional but recommended) Start a session** if your app will make several calls
in one workflow, instead of paying the handshake cost every time:

```bash
curl -i -X POST http://localhost:8010/mcp -H "Authorization: Bearer gw_..." -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{}}'
```

Capture the `Mcp-Session-Id` response header and pass it back on every subsequent call
in that workflow.

**4. Call a tool:**

```bash
curl -X POST http://localhost:8010/mcp \
  -H "Authorization: Bearer gw_..." -H "Content-Type: application/json" -H "Mcp-Session-Id: <from step 3>" \
  -d '{"jsonrpc":"2.0","id":"2","method":"tools/call","params":{"name":"<tool_name>","arguments":{...}}}'
```

**5. Handle the response correctly — this is the part people get wrong.** There are
three distinct outcomes, and your app needs to branch on all three, not just HTTP
status:

| Outcome | HTTP status | Shape |
|---|---|---|
| Gateway rejected the request before forwarding it (bad scope, rate limited, unknown tool, bad JSON) | 4xx/5xx | `{"error":{"code":...,"message":...,"request_id":...}}` |
| Gateway forwarded it; the downstream MCP server itself returned a JSON-RPC error | **200** | `{"jsonrpc":"2.0","id":...,"error":{"code":...,"message":...}}` |
| Success, or a REST-backed tool's target API returned a non-2xx | **200** | `{"jsonrpc":"2.0","id":...,"result":{...}}` — for a REST-backed tool, check `result.isError`, since a failed target-API call still comes back as a *result*, not an error |

So: check HTTP status first; if 200, check for a top-level `"error"` key before
assuming success; if the tool is REST-backed, also check `result.isError`.

**A minimal example** (Python, but the same shape applies in any language):

```python
import requests

API_KEY = "gw_..."
BASE = "http://localhost:8010"
headers = {"Authorization": f"Bearer {API_KEY}"}

init = requests.post(f"{BASE}/mcp", headers=headers, json={"jsonrpc": "2.0", "id": "1", "method": "initialize", "params": {}})
session_id = init.headers.get("Mcp-Session-Id")
if session_id:
    headers["Mcp-Session-Id"] = session_id

resp = requests.post(f"{BASE}/mcp", headers=headers, json={
    "jsonrpc": "2.0", "id": "2", "method": "tools/call",
    "params": {"name": "get_customer", "arguments": {"id": "123"}},
})
body = resp.json()
if resp.status_code >= 400:
    raise RuntimeError(f"gateway rejected: {body['error']['message']}")
if "error" in body:
    raise RuntimeError(f"tool call failed: {body['error']['message']}")
result = body["result"]
if result.get("isError"):
    raise RuntimeError(f"target API error: {result}")
print(result)
```

---

### How does `invocation_service.py` work, and what does `_resolve_auth_headers` do inside it?

`AgentInvocationService` (`app/services/agent_gateway/invocation_service.py`) is the
**governed invocation path** for the Agent Gateway — a consumer asks for a
**capability** (e.g. `"pricing"`), never a specific agent or endpoint directly, and the
service decides which registered agent actually handles it. It mirrors the same
governed-call pattern MCP `tools/call` uses (candidate lookup → policy gate → dispatch
→ never raise on a downstream failure), just applied to agents instead of tools.

**`invoke()` — picking which agent handles the request:**

1. **Find candidates**: `AgentRepo.list_by_capability()` returns every `active` agent
   whose `capabilities` list includes the requested one, **ordered by `priority`
   ascending** — the same "lower number wins" convention as a Routing Rule target's
   `weight`. Only `active` agents are ever candidates; registering or approving an
   agent never by itself makes it eligible to be invoked.
2. **No candidates at all** → returns immediately with
   `authorization_decision="no_active_agent"` and an error — nothing to gate.
3. **Policy gate, first-match-wins**: for each candidate *in priority order*, it calls
   the same `PolicyEngine.evaluate()` used by MCP `tools/call`, this time checking the
   `agent_key` dimension (via `allowed_agent_keys`) instead of `tool_name`. The **first**
   candidate that passes is dispatched to immediately — this is not "try all, pick the
   best," it's "take the highest-priority agent this caller is actually allowed to
   use." If every candidate is rejected by policy, it returns
   `authorization_decision="denied"` only after the loop exhausts every candidate.

**`_dispatch()` — actually calling the agent:**

- If the winning agent has no `endpoint_url` configured, that's an immediate error
  result — but note `authorization_decision` is still `"allowed"`, because the policy
  check already passed; this is a *configuration* problem, not an *authorization* one.
- Resolves outbound auth headers (see below), then `POST`s
  `{"operation": ..., "payload": ...}` to `agent.endpoint_url` with a
  `httpx.AsyncClient` bounded by `agent_invocation_timeout_seconds`.
- A transport-level failure (`httpx.HTTPError` — connection refused, timeout, DNS,
  etc.) is caught and logged, and returns a normal error *result* — it never raises up
  to the caller.
- A non-2xx HTTP response **from the agent itself** is treated as a **completed
  invocation** with `status=error` (not a gateway failure) — the exact same
  "`isError`, don't raise" treatment `RestExecutor` gives a REST-backed MCP tool's
  non-2xx response. Only `REMOTE_HTTP` dispatch exists today; real A2A remote
  invocation and an in-process LangGraph boundary are both still Future Capability.

**`_resolve_auth_headers()` — how the agent's own credential gets attached:**

```python
async def _resolve_auth_headers(self, agent: Agent) -> dict[str, str]:
    config = agent.auth_config or {}
    auth_type = config.get("type", "none")
    if auth_type == "none":
        return {}
    credential_ref = config.get("credential_ref")
    value = await self.secret_service.get_secret(credential_ref) if credential_ref else None
    if not value:
        return {}
    if auth_type == "bearer":
        return {"Authorization": f"Bearer {value}"}
    if auth_type == "api_key":
        return {config.get("header_name", "X-API-Key"): value}
    return {}
```

It reads the agent's own `auth_config` field (`{"type": "none"|"bearer"|"api_key",
"credential_ref": ..., "header_name": ...}` — the same shape as an MCP server's or a
REST API service's `auth_config`) and builds the header the gateway will send when
**it** calls out to the agent's endpoint:
- `none` → no auth header at all.
- `bearer` → `Authorization: Bearer <value>`.
- `api_key` → a header named by `header_name` (default `X-API-Key`) carrying `<value>`.

**The one detail worth remembering**: `credential_ref` here is resolved through the
**Secret Provider layer** (`self.secret_service.get_secret(...)`) — a real secret
lookup, Fernet-encrypted at rest by default. This is different from an MCP server's
outbound auth (`mcp_client.py`'s own `_resolve_auth_headers`), which resolves
`credential_ref` from a **plain OS environment variable** instead — see the MCP
Gateway entry above for that asymmetry. Agents and REST API services (API Registry)
both go through the proper Secret Provider; MCP servers are the one documented
exception.

---

### Request numbers are increasing but cost isn't changing — how does budget/cost tracking work?

`CostService.calculate()` (called from `chat.py`/`embeddings.py` after every completion)
looks up the **`model_pricing`** table by an *exact* match on `(resolved_provider,
resolved_model)` — the real provider/model your routing rule resolved to, not the alias
you sent as `"model"`. It multiplies prompt/completion tokens by that row's
`prompt_per_1k`/`completion_per_1k`. The result is written to **`cost_ledger`** (one row
per request, linked to `request_logs`) on *every* request — even the `$0` ones.

**Budgets have no separate running counter** — `GET /v1/budgets` computes
`current_spend_usd` live, by summing `cost_ledger` rows scoped to that org/project/user
since the period start. And budgets are **advisory only**: nothing in the request path
checks a budget or blocks a request for exceeding it.

**Two things independently produce `cost_usd = 0`**, while `request_logs` keeps
incrementing normally either way:

1. **Cache hits.** Repeating the same `model` + `messages` + `temperature` +
   `max_tokens` combination serves the cached response from Valkey and is deliberately
   costed at `$0` (no real provider call happened, so there's nothing to charge for).
   Check the response's `gateway_metadata.cache_hit` field.
2. **No `model_pricing` row for that provider/model.** If `model_pricing` has no entry
   matching the *resolved* provider+model, cost silently returns `$0` (logged as a
   `model_pricing_not_found` warning). This table isn't seeded by default, so on a fresh
   deployment it's empty until you add rows yourself.

**Fix for #2** — Model Pricing page, or:

```bash
curl -X POST http://localhost:8010/v1/model-pricing \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"provider":"openai","model":"gpt-4o-mini","prompt_per_1k":0.00015,"completion_per_1k":0.0006}'
```

`provider`/`model` here must match your **routing rule's target**, not the alias.

---

### Routing Rules explained simply — what is a Model Alias, Capability, Strategy, Target, and Priority, and how do I set one up?

Think of a **Routing Rule** as a phone directory entry. Your application never dials a
real AI provider directly — it just asks the gateway for a *name* (like `"gpt-4o-mini"`
or `"fast-chat"`), and a Routing Rule tells the gateway what that name actually means:
which real AI service to call, in what order, and how to pick between them if you've
listed more than one. Without a rule for that exact name, the gateway has nowhere to
send the request — which is why you get the `"No active routing rule"` error below if
one is missing.

Here's every field on the "New rule" form, in plain terms:

**Model alias** — the nickname your application uses. This is just a label *you*
invent; it doesn't have to match any real provider's model name (though it's simplest
if it does, e.g. calling it `"gpt-4o-mini"` when it actually points at OpenAI's
`gpt-4o-mini`). Whatever you type here must match exactly what your app sends as
`"model"` in its request.

**Capability** — what *kind* of AI task this rule is for: `chat` (having a conversation
/ generating text) or `embedding` (turning text into a list of numbers used for search
and similarity matching). A rule only ever applies to requests of its own capability —
a `chat` rule is invisible to an embedding request for the same alias, and vice versa.

**Targets** — the actual list of real AI backends this alias is allowed to use. Each
target is three things:
- **Provider**: which AI company — `openai`, `anthropic`, or `bedrock` (AWS) today.
- **Model**: that company's exact model name (e.g. `gpt-4o-mini`, `claude-3-5-haiku-20241022`).
- **Weight**: a small number used to break ties between targets (see Strategy below).

You can list more than one target as a **fallback chain** — if the first one fails
(the provider is down, the credential is wrong, etc.), the gateway automatically tries
the next one. Your application never needs to know which target actually answered.

**Strategy** — *how* to order multiple targets when you've listed more than one:
- **`priority`** — always try them in a fixed order you control via each target's
  **Weight** (the lower the weight number, the sooner it's tried — weight `1` before
  weight `2`). Simplest option, good for "always prefer X, fall back to Y."
- **`cost`** — automatically try the cheapest target first, based on what you've entered
  on the Model Pricing page. A target with no pricing entered is treated as the most
  expensive, so it's tried last.
- **`latency`** — automatically try whichever target has been responding fastest
  recently, based on real request history. A target with no history yet is tried last.

If you only have one target, Strategy doesn't matter — there's nothing to order.

**Priority (the number field)** — easy to confuse with the `priority` Strategy option
above, but it does something completely different: it decides which **rule** wins when
you've created more than one rule for the *same* alias + capability (say, two separate
global rules both named `"gpt-4o-mini"` for `chat`). Whichever of those competing rules
has the **higher** Priority number is used, and the other is ignored *completely* — this
is not a fallback chain like Targets are, it's winner-take-all between rules. If you
only ever create one rule per alias+capability, you can safely leave this at its
default and never think about it again. (For the full technical tie-breaking order,
including project/user-scoped rules beating global ones, see the entry further below.)

**Active** — a simple on/off switch. An inactive rule is invisible to the gateway, as if
it didn't exist.

**A complete worked example**: "My app should call the alias `quick-helper` for chat,
preferring OpenAI but falling back to Anthropic if OpenAI is ever down."

| Field | Value |
|---|---|
| Model alias | `quick-helper` |
| Capability | `chat` |
| Strategy | `priority` |
| Targets | 1: provider `openai`, model `gpt-4o-mini`, weight `1` — 2: provider `anthropic`, model `claude-3-5-haiku-20241022`, weight `2` |
| Priority | `100` (default is fine — no competing rule exists yet) |
| Active | ✅ |

With this saved, sending `{"model": "quick-helper", ...}` to `/v1/chat/completions`
tries OpenAI's `gpt-4o-mini` first; if that call fails for any reason, the gateway
automatically retries the exact same request against Anthropic's
`claude-3-5-haiku-20241022` instead — no code change or retry logic needed on your
side.

**Step by step, in the UI**:
1. Go to the **Routing Rules** page → **New rule**.
2. Type your **Model alias** (whatever string your app will send as `"model"`).
3. Pick the **Capability** (`chat` or `embedding`).
4. Pick a **Strategy** — `priority` is the easiest to reason about when starting out.
5. Add one or more **Targets**: pick a **Provider**, type its exact **Model** name, and
   set a **Weight** if you're using more than one target with the `priority` strategy.
6. Leave **Priority** at its default unless you already know you'll have competing
   rules for the same alias.
7. Check **Active** and save.
8. Before testing: make sure that provider's real credential is set on the **Secrets**
   page (see below), and add a row on the **Model Pricing** page for the same
   provider/model if you want accurate cost tracking (see the cost-tracking entry
   above) — a routing rule alone doesn't handle either of those.

A rule created via the UI form is always **global** (it applies to every project/API
key) — there's no project/user scoping exposed there today, only via the API.

---

### I called `/v1/chat/completions` and got `"No active routing rule for alias 'X'"` — what do I do?

Create a **Routing Rule** (Routing Rules page) with:

- **Model alias**: exactly the string you send as `"model"` in the request (e.g.
  `gpt-4o-mini`)
- **Capability**: `chat` (or `embedding`)
- **Strategy**: `priority` is fine for a single target
- **Targets**: at least one `{provider, model, weight}` — e.g. provider `openai`, model
  `gpt-4o-mini`
- **Active**: checked

A rule created via the UI is global (no project/user scoping), so it matches any
project/API key. `ProviderNameEnum` only supports `openai`, `anthropic`, `bedrock` today.

---

### In Routing Rules, there's a "priority" option in the Strategy dropdown, and also a separate Priority number field — how do these work, and what's the difference?

They control two completely different things, despite sharing a name.

**Strategy + target weight — orders the *targets within one rule*** (its fallback
chain — the UI labels that section "Targets (tried in order)"). `GatewayRouter.
_order_targets()` sorts them before building the LLM router:

- **`priority`** — sorts by each target's own **weight**, ascending — **lower weight is
  tried first** (weight `1` beats weight `2`).
- **`cost`** — sorts by that target's `model_pricing.prompt_per_1k`; a target with no
  pricing row sorts *last* (treated as maximally expensive).
- **`latency`** — sorts by the target's recent p50 latency from `request_logs`; a target
  with no data sorts last.

Whichever order results, that's the sequence litellm's Router tries — first entry
first, falling back to the next target on failure.

**The top-level Priority number — resolves competing *rules***, not targets. If
several **active** rules match the same `model_alias` + `capability` (e.g. two global
rules both for `gpt-4o-mini`/`chat`), `RoutingRuleRepo.find_best_match()` picks exactly
one:

1. **Specificity wins first** — a rule scoped to project+user beats project-only, which
   beats a global rule.
2. **Among rules tied on specificity, the higher Priority number wins.** This is
   **winner-take-all**, not a fallback chain — the losing rule's targets are never
   tried at all.

**The gotcha**: these two sort in **opposite directions**. Target weight is ascending
(lowest number tried first); the rule-level Priority field is descending (highest
number wins). They share a name but don't behave the same way.

---

### How do I set an LLM provider's credential (e.g. `OPENAI_API_KEY`)?

Use the **Secret Management** page's "Set a Secret Value" form (or `POST
/admin/secrets`, admin-only). This writes through to the active Secret Provider
(Postgres by default, Fernet-encrypted at rest) and is never shown again after saving.

Recognized names: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AWS_ACCESS_KEY_ID` +
`AWS_SECRET_ACCESS_KEY` (Bedrock). Note: LLM provider credentials are **never** read
from `.env`/environment variables, by design — only from the Secret Provider,
regardless of restart or redeploy.

---

### There's a "Rotate" button next to every secret on the Secrets page — how does it work, and where is it used?

It does **not** generate or let you type a new value — it forces a fresh read from the
underlying Secret Provider, bypassing the cache, and re-caches whatever it finds:

```python
# app/secrets/service.py — SecretService.get_secret(..., force_refresh=True)
value = await self.provider.get_secret(secret_name, tenant=tenant)   # skips the cache check
await self._cache_write(cache_key, value)                            # re-caches it
```

Clicking it loops over every secret name that LLM provider actually needs (e.g. AWS
Bedrock rotates *two* — `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` — in sequence),
calling `POST /admin/secrets/rotate` (`{"secret_name": ..., "tenant": ...}`) once per
name. Each call is audit-logged (`operation: rotate`, success/error) into
`secret_audit_log`, visible in the "Recent Secret Operations" table below.

**What it's for**: resolved secret values are cached in Valkey for
`secret_cache_ttl_seconds` (default 300s) so the hot LLM-routing path doesn't hit the
Secret Provider on every request. Rotate exists to bust that cache when a credential's
real value changed **outside this app** — e.g. you rotated the actual key in the AWS
Secrets Manager console, or updated it directly in Vault — so the gateway doesn't keep
serving the old cached value for up to 5 minutes.

**It's not needed after using "Set a Secret Value"** — that form's `set_secret` already
invalidates the cache entry as its last step, so the very next request re-fetches the
fresh value automatically. Rotate only matters when the write happened somewhere
`SecretService` doesn't already know about.

---

### There's a "Recent Secret Operations" table on the Secrets page — why are these records being inserted, and what's the purpose?

Each row is a fire-and-forget audit record written by `record_secret_audit()`
(`app/services/logging_service.py`), which runs as a background task after the response
is already sent — it never blocks or slows down the actual secret operation. Its
signature deliberately has **no `value` parameter at all**: nothing that could hold a
secret value ever reaches this function, let alone gets written to the row. Each row
only records:

- **who** (`user_id`)
- **what operation** (`get` / `set` / `rotate` / `delete`)
- **which secret, by name only** (`secret_name` — never its value)
- **against which provider/tenant** (`provider`, `tenant_id`)
- **whether it succeeded** (`status`: success/error)

**What actually triggers a row** — three endpoints in `app/api/v1/secrets.py` write one:

1. **Just loading/refreshing the Secrets page** — `GET /admin/secrets/status` runs a
   `get` check for every recognized LLM credential name (`OPENAI_API_KEY`,
   `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS` both `AWS_ACCESS_KEY_ID`/
   `AWS_SECRET_ACCESS_KEY`, `AZURE_OPENAI_KEY` — 6 checks across 5 providers) and logs
   one audit row per check. This is why the log can grow fast even without clicking
   anything — simply opening the page does this every time.
2. **Rotate** — one `rotate` row per secret name rotated.
3. **Set a Secret Value** — one `set` row per save.

**Purpose**: a compliance/security trail specific to the Secret Provider layer, proving
*who touched which credential and when*, without the trail itself ever becoming a way
to leak a secret value. This is currently the **only** general-purpose audit trail in
the app — routing rule changes, org/project edits, etc. aren't logged this way; secrets
got this treatment because credential access is the highest-sensitivity operation in
the system.

---

### I get `401 {"code":"unauthorized","message":"Invalid or missing API key"}` — what's wrong?

The API key you sent doesn't hash-match any row in the `api_keys` table. Common causes:

- No API key has actually been created yet in this database (see "How do I get an API
  key" above) — this is the normal state right after a fresh deploy or a Postgres volume
  reset.
- You're using a stale key from a database that's since been recreated (e.g. after
  `docker compose down -v`, or a Docker Desktop reset — named volumes normally survive a
  plain `docker compose down`, but not a volume wipe).
- A copy/paste issue (extra whitespace, truncated value).

---

### I edited `backend/.env` and nothing changed after redeploying — why?

`docker-compose.yml` sets every backend setting explicitly in its own `environment:`
block for `tcsaigateway-backend`, and real Docker environment variables always win over
`backend/.env` for the same key. So editing `backend/.env` only has an effect for a
setting that **isn't** already listed in `docker-compose.yml`. To change one that is,
edit `docker-compose.yml` directly, or use a **root-level** `.env` (next to
`docker-compose.yml`), which Compose itself reads for its `${VAR:-default}`
substitutions — that's a different mechanism from `backend/.env`.

---

### We're storing secrets in Postgres now; we plan to move to Infisical (or another backend) later — is that a sound approach?

Yes — the `SecretProvider` abstraction (`app/secrets/base.py`) exists exactly for this.
Every caller goes through `SecretService`/`get_secret_provider()`, never a concrete
provider, so switching `SECRET_PROVIDER` later touches zero call sites. Two things worth
planning for before that cutover:

1. **No migration tooling exists** — switching means a one-time script that reads every
   secret via the current provider and re-writes it via the new one; `SECRET_PROVIDER`
   is a single global setting with no dual-write/parallel-run support.
2. **Decide what happens to the leftover encrypted rows in Postgres** after cutover
   (wipe them, or leave them dormant) rather than letting stale ciphertext linger.

---

### How do I run the deploy/curl commands from Windows `cmd.exe` instead of bash?

`cmd.exe` doesn't support bash's `$(...)` command substitution or `\` line-continuation.
For a single curl call, put everything on one line and escape JSON quotes as `\"`:

```
curl -X POST http://localhost:8010/v1/chat/completions -H "Authorization: Bearer gw_xxxxxxxxxxxx" -H "Content-Type: application/json" -d "{\"model\":\"gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}"
```

For a multi-step flow (token → org → project → key) where each step needs the previous
step's output, chaining `for /f` loops on one raw cmd line is unreliable (cmd's
delayed-expansion quirk). Shell out to PowerShell instead — `Invoke-RestMethod` parses
JSON natively:

```
powershell -NoProfile -Command "$t=(Invoke-RestMethod -Method Post -Uri http://localhost:8180/realms/gateway/protocol/openid-connect/token -Body @{client_id='tcsaigateway-frontend';grant_type='password';username='admin@gateway.local';password='admin123'}).access_token; ..."
```

Multi-Tenant Identity Configs
Purpose
By default, one Identity Provider (IDENTITY_PROVIDER, Keycloak here) validates every login for the whole gateway. Multi-Tenant Identity Configs let you override that per tenant, so different customers/tenants can authenticate through different IdPs against the same running gateway — e.g. Customer A logs in via their own Microsoft Entra ID tenant, Customer B still uses the default Keycloak, both hitting the same backend.

Mechanically: when a request comes in, auth_middleware.py reads the (unverified) iss claim off the incoming JWT and looks it up in the tenant_identity_config table. If a row's issuer matches, that row's provider + configuration build a one-off IdentityProvider instance for validating that request; otherwise it falls back to the global IDENTITY_PROVIDER default. So this is purely additive — it never replaces the default, it just carves out exceptions per tenant.

How to configure it
On the Identity Providers page, click Add tenant config and fill in:

Field	What it is	Example
Tenant id	Your own internal label for this tenant	customer-a
Provider	Which IdentityProvider implementation to use	Microsoft Entra ID
Issuer	The exact iss value that provider's tokens carry — this is the lookup key	https://login.microsoftonline.com/{tenant-guid}/v2.0
Configuration	JSON overriding that provider's Settings fields	{"entra_tenant_id": "...", "entra_client_id": "..."}
The configuration keys must match the Settings field names that provider's constructor actually reads (see the table in the FAQ's identity-provider entry — e.g. Entra needs entra_tenant_id + entra_client_id, Okta needs okta_domain, etc.). All of the built-in providers only do JWKS signature/issuer/audience validation — no client secret is ever needed here, since there's no OAuth flow being initiated by this app, only an already-issued token being checked.

One practical wrinkle: you need the issuer value up front, which usually means you've already registered an app/client with that IdP outside this gateway (e.g. an Entra App Registration) so you know its tenant/client id and can construct the issuer URL — this form doesn't create anything on the IdP side, it only tells the gateway how to validate tokens that IdP already issues.

---

### When an agent makes multiple LLM calls and MCP tool calls, how does that actually flow through the gateway?

The most important framing first: **the gateway does not run the agent's loop.** There's no
orchestrator in this codebase that decides "call the LLM, then call a tool, then call the LLM
again." That reasoning loop lives entirely in the agent's own code (a LangChain/LangGraph app, a
custom script, whatever). The gateway's job is to be the single governed front door the agent
calls into, once per LLM completion and once per tool invocation. Each of those is its own
independent HTTP request/response cycle. The two paths are separate endpoints with separate
pipelines, and it's worth being precise about what state (if any) carries over between calls.

**The shared entry pipeline**

Every request — chat or MCP — passes through the same middleware stack first, in this order
(outermost/first-to-run listed first), per the comment and registration order in `main.py`:

`RequestIDMiddleware -> CORSMiddleware -> AuthMiddleware -> RateLimitMiddleware -> route handler`

- `RequestIDMiddleware` stamps a fresh `request_id` (UUID) onto `request.state` for *this single
  call* — it does not span multiple calls, so if you want to correlate an agent's whole
  multi-call session in logs, that has to happen on the agent's side (its own trace/correlation
  id passed in a custom header or in the request body — nothing here generates one).
- `AuthMiddleware` resolves the caller into a `Principal` — either an API key (`gw_...` bearer
  token) or an Identity-Provider-authenticated human — and populates `request.state.principal`.
- `RateLimitMiddleware` applies one coarse, per-API-key limit to `/v1/chat/completions`,
  `/v1/embeddings`, and `/mcp` as a whole (`RATE_LIMITED_PATHS` in `rate_limit_middleware.py`) —
  this is on top of anything the MCP path does internally (see below).

An agent making many LLM calls and many tool calls in the same "session" typically reuses the
**same API key** for both — there's no shared session object at the gateway level tying them
together, just the same bearer token on every request.

**Path 1 — each LLM call (`POST /v1/chat/completions`)**

Walking `chat.py` top to bottom, every single completion the agent asks for goes through this
pipeline **independently**:

1. **Project lookup** from the API key.
2. **Prompt guardrail check** — the concatenated message content is sent to the Guardrails
   service; a violation raises `GuardrailBlockedError` and the call never reaches a provider.
3. **Cache lookup** — a cache key is built from `model` + the exact `messages`/`temperature`/
   `max_tokens`. If the agent sends the identical prompt twice, the second call short-circuits
   here and never touches a provider at all — this is the only thing that makes two calls "aware"
   of each other, and only when they're byte-for-byte identical.
4. **Routing resolution** — `GatewayRouter.resolve()` looks up the `RoutingRule` matching the
   requested `model_alias`, then orders its provider targets by the rule's strategy — `priority`
   (static weight), `cost` (cheapest `model_pricing` row first), or `latency` (lowest recent p50
   first, recomputed from `request_log` each call). Two calls to the same alias can therefore
   resolve to a *different* concrete provider/model if the strategy is `latency` or `cost` and
   the underlying data shifted between calls.
5. **Dispatch** — a `litellm.Router` is built from the ordered targets and `Router.acompletion()`
   is called. Provider failover across the target list (e.g. OpenAI down -> fall back to the next
   target) happens *inside this one call*, handled by litellm itself (`num_retries=1`) — it is
   not something that spans separate agent-initiated calls.
6. **Response guardrail check** on the completion text, same block-or-continue semantics as the
   prompt check.
7. **Cost calculation**, cache write, and a `background_tasks.add_task(record_request, ...)` call
   that writes the usage/cost/log row *after* the response is already returned to the agent — so
   logging latency never adds to the agent's perceived response time.

If the agent fires off five LLM calls, that's five completely separate trips through steps 1-7,
each with its own `request_id`, each independently cached/routed/costed/guardrailed. Nothing here
batches or pipelines them — if the agent wants them concurrent, it's the agent issuing five
concurrent HTTP requests itself.

**Path 2 — each MCP tool call (`POST /mcp`)**

This one is body-routed, not path-routed: every MCP interaction — `initialize`, `tools/list`,
`tools/call` — hits the same `/mcp` endpoint, and the JSON-RPC `method` field decides what
happens.

Before the first tool call, a well-behaved agent sends `initialize` once. That handler broadcasts
`initialize` to every *registry-active* MCP server (never a hardcoded list), records a per-server
session id for each one, and returns a single `client_session_id` the agent must echo back on
every subsequent call via the `Mcp-Session-Id` header. This is the one piece of real cross-call
state in the whole gateway: a JSONB map of `{server_id: server_session_id}` hanging off the
client's session row (`SessionManager` in `session_manager.py`).

For each `tools/call` the agent then makes:

1. **Scope check** — the API key needs `tool:execute` (or, for a human Identity-Provider caller
   with no scopes, the request instead goes through `PolicyEngine.evaluate()` — RBAC/ABAC over
   role/identity-provider/tool_name).
2. **Rate limit, per tool** — `mcp-tool:{caller}:{tool_name}` — this is *in addition* to the
   coarse per-key limit the middleware already applied, so a chatty agent hammering one specific
   tool gets throttled on that tool specifically, separate from its overall request budget.
3. **Tool resolution** — `RoutingEngine.resolve_tool(tool_name)` looks the tool up purely by name
   in the tool registry (never by which server the agent thinks it's on) and checks it's both
   `enabled` and currently routable (server healthy, or REST service active). This is resolved
   fresh on *every single call* — if an admin disables a tool between two of the agent's calls,
   the second one fails immediately.
4. **Dispatch, branching on the tool's source**:
   - **REST-backed** (API Registry): its own per-service rate limit, then
     `ApiRegistryService.execute()` translates the call into a plain HTTP request to the
     registered REST API. Stateless — no session involved.
   - **MCP-server-backed**: looks up the session's already-recorded server-session-id for *that
     specific server*; if none exists yet (e.g. the agent skipped `initialize`, or this is the
     first call touching a server it hadn't used before), it lazily probes/initializes that one
     server on the spot. Then `McpClient.call_tool()` sends the actual JSON-RPC request to the
     real MCP server over HTTP.
5. A downstream **JSON-RPC `error`** from the MCP server is forwarded back verbatim as a normal
   200 response (it's an application-level result, not a gateway failure) — only gateway-level
   rejections (bad scope, rate limited, unknown tool) come back as HTTP errors.
6. Same as chat: a `background_tasks.add_task(record_mcp_request, ...)` fires after the response
   is sent, logging method/tool/server/status/latency for cost/usage rollups.

So if the agent calls three different tools that happen to live on three different MCP servers,
you get three independent lookups and three independent (lazily-established, then reused)
per-server sessions, all hanging off the one `client_session_id` the agent keeps sending.

**Putting "multiple LLM calls + multiple tool calls" together**

For a typical agent turn — say, `tools/call` -> `tools/call` -> `chat/completions` ->
`tools/call` — what actually happens is four unrelated HTTP requests to the gateway, hitting two
different endpoints, each independently authenticated, guardrailed/authorized, rate-limited, and
logged. The only continuity across them is:

- the same API key (or IdP token) on every request,
- the same `Mcp-Session-Id` header the agent must carry across its MCP calls so the gateway
  doesn't re-`initialize` every server on every tool call,
- and, downstream, the same `project_id`/`organization_id` that every one of those
  background-logged rows carries — which is what lets the Usage & Cost and Request Logs pages
  roll all of that agent's LLM spend and tool traffic up into one place, even though the gateway
  itself never tracked them as "one agent's session."

One naming note since it's easy to conflate given this codebase: this is entirely separate from
the **Agent Gateway**'s own `POST /v1/agent-invocations` — that's for invoking a *registered
agent* (a third-party autonomous service) by capability, not for an agent making LLM/MCP calls
through the gateway. The flow described above is "an agent using the gateway as its LLM+tools
access layer"; the Agent Gateway is "the gateway routing to an agent as the callee." Same
gateway, two unrelated call directions.

---

### If one agent invokes another agent — internal or external — should that go through the Agent Gateway?

**Yes — always route it through the Agent Gateway, whether the target is internal or external.**
The gateway is designed as the only sanctioned path to any registered agent. There's no code path
in this app for "in-process" or "direct" agent-to-agent calls today — every invocation, internal
or external, goes out over HTTP through `AgentInvocationService`. Bypassing the gateway isn't a
shortcut to the same destination with less overhead; it's a different, ungoverned path that skips
every control this system exists to provide.

**What "internal" vs "external" actually means in this codebase**

Two fields on the `Agent` model already model this distinction, though they mean different
things — worth being precise:

- `trust_level` (`t0_unknown` … `t1_registered_internal` … `t4_approved_external_partner` …
  `t5_public_untrusted`) is the field that literally encodes "is this an internal service or an
  external partner/public agent." Caveat: as of the current code, this is descriptive metadata
  only — it's stored and returned in `AgentOut`, but nothing in `PolicyEngine` or
  `AgentInvocationService` actually branches on it yet. It doesn't yet gate or restrict anything
  by itself.
- `visibility` (`private`/`published`) + `project_id` + `AgentProjectEnablement` is the field
  that's *actually enforced* today — a `private` agent is only reachable by its owning project or
  a project explicitly opted in; `published` (the default) is reachable by anyone who clears the
  `PolicyEngine` gate. This is the practical "internal-only" vs "open to everyone" boundary right
  now, independent of whether the agent's *real* endpoint happens to sit inside or outside your
  network.

So: register an agent that's genuinely internal (say, a finance-team agent only your own team
should call) as `private`, scoped to your project. Register one meant to be broadly usable —
whether it's your own service or a genuine third-party SaaS agent — as `published`. Either way,
the registration record and the invocation path are identical; only the visibility gate differs.

**The recommended step-by-step flow: Agent A invoking Agent B through the gateway**

1. Agent B must already be a registered, `active` agent — it went through registration
   (`draft`) → multi-stage approval (`under_review` → `approved`) → `publish` (`active`), the
   same governance flow documented earlier in this FAQ and in the README's Agent Gateway section.
   If B doesn't exist yet as a gateway-registered agent, it has to go through that onboarding
   first — there's no ad-hoc/unregistered invocation.
2. Whatever runtime executes Agent A's logic must hold a gateway API key with the `agent:invoke`
   scope (or be an Identity-Provider-authenticated human/service, gated instead by
   `PolicyEngine`). This is the one nuance worth being very clear about: **the gateway has no
   concept of "Agent A" as a caller identity.** Agent A isn't itself a first-class principal —
   it's whatever process is running its code, and that process needs its own API key (issued the
   normal way, via `POST /v1/keys`) to be allowed to call the gateway at all. There's no
   "agent-to-agent" credential type distinct from any other caller.
3. Agent A calls `POST /v1/agent-invocations` with `{"capability": "...", "operation": "...",
   "payload": {...}}` — asking for a *capability*, never naming Agent B directly, even if A knows
   exactly which agent it wants. This indirection is the whole point: it's what lets B be
   swapped, scaled, or replaced without A's code changing.
4. Inside the gateway, per request (`AgentInvocationService.invoke()`):
   - Every `active` agent advertising that capability is a candidate, tried in ascending
     `priority` order (so if B has competitors registered for the same capability, the
     lowest-priority-number one is tried first).
   - Each candidate is checked against **visibility/project-enablement** first (is A's project
     allowed to reach this specific candidate if it's `private`?), then against the
     **`PolicyEngine`** (RBAC/ABAC over role/identity-provider/`agent_key`, via
     `allowed_agent_keys`) — API-key callers instead rely on their `agent:invoke` scope and skip
     this second check.
   - The first candidate that passes both gates is dispatched to.
5. Dispatch — the gateway `POST`s to B's registered `endpoint_url`, either as its own
   `{"operation","payload"}` JSON (`protocol: remote_http`, the default) or as a best-effort A2A
   JSON-RPC envelope (`protocol: a2a`), attaching whatever outbound auth B's `auth_config`
   specifies, resolved through the **Secret Provider** — so A never needs to know or hold B's
   credential.
6. On failure, a transport error or a 5xx from B automatically retries the *next* eligible
   candidate for that capability (not B specifically retried, a different agent entirely) — so
   this only helps if more than one agent serves the capability. A 4xx is treated as final.
7. Result comes back to A as an `InvokeResponse` — `status`, `result`, `cost_usd` (priced via
   `AgentPricing` if set), and B's identity/version. If A sent an `Idempotency-Key` header, a
   repeat of that exact key/caller pair replays the first *successful* response instead of
   re-invoking B.
8. Every call is logged — an `AgentInvocation` row records the capability, resolved agent,
   latency, status, and cost, all attributed to A's project — this is what makes the Usage & Cost
   / audit views possible at all.

**What you'd lose if Agent A called Agent B's endpoint directly (bypassing the gateway)**

Concretely, all of the following disappear the moment A calls B's `endpoint_url` itself instead
of going through `POST /v1/agent-invocations`:

- No authorization gate at all — `visibility`/project-enablement and the `PolicyEngine` check
  both live inside the gateway; a direct call skips both entirely.
- No audit trail — nothing gets written to `AgentInvocation` or `AgentAuditLog`; the call is
  invisible to the Usage & Cost, Request Logs, and Agent Registry pages.
- No cost attribution — the `AgentPricing` lookup only happens in `_price()`, inside the gateway
  path.
- No candidate failover — direct calls have exactly one destination; there's no "try the next
  eligible agent for this capability" behavior outside `invoke()`.
- No rate limiting — the per-capability `RateLimitService` check in `agent_invocations.py` never
  runs.
- No idempotency protection — the `Idempotency-Key` cache is entirely inside this one endpoint.
- No indirection — A would have to hardcode B's endpoint/protocol/auth details itself, defeating
  the entire "ask for a capability, not an agent" model this gateway (and the MCP Gateway, and
  the LLM Gateway's routing rules) are all built around.

**Two honesty caveats worth knowing before relying on this for genuine multi-hop agent chains**

- No first-class chaining/tracing today: `InvokeRequest` has a `correlation_id` field, but it's
  currently dead — declared in the schema, never read or forwarded anywhere in
  `invocation_service.py` or the logging path. If you need to trace "A called B called C" across
  multiple gateway invocations, that has to be threaded through your own `payload` and correlated
  on your own side for now; the gateway won't do it for you yet.
- No network-boundary enforcement on `endpoint_url`: registering an agent accepts any reachable
  URL, internal or public internet, with no SSRF-style allowlist — same as MCP servers and REST
  API services elsewhere in this codebase. "Internal" vs "external" is a registration-time label
  (`trust_level`, `visibility`) for your own governance process, not something the gateway itself
  firewalls at the network layer.


