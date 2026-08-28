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
   `gateway-backend` environment) to `entra`/`auth0`/`okta`/`aws_identity`/`google`. Only
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
auth you must add that env var to `docker-compose.yml`'s `gateway-backend` block and
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

### How do I set an LLM provider's credential (e.g. `OPENAI_API_KEY`)?

Use the **Secret Management** page's "Set a Secret Value" form (or `POST
/admin/secrets`, admin-only). This writes through to the active Secret Provider
(Postgres by default, Fernet-encrypted at rest) and is never shown again after saving.

Recognized names: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AWS_ACCESS_KEY_ID` +
`AWS_SECRET_ACCESS_KEY` (Bedrock). Note: LLM provider credentials are **never** read
from `.env`/environment variables, by design — only from the Secret Provider,
regardless of restart or redeploy.

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
block for `gateway-backend`, and real Docker environment variables always win over
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
powershell -NoProfile -Command "$t=(Invoke-RestMethod -Method Post -Uri http://localhost:8180/realms/gateway/protocol/openid-connect/token -Body @{client_id='gateway-frontend';grant_type='password';username='admin@gateway.local';password='admin123'}).access_token; ..."
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


