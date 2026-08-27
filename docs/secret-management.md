# Secret Management Layer

This document covers the pluggable Secret Provider layer that resolves LLM provider
credentials (and any other secret this gateway needs) at runtime. For the gateway's
overall architecture, see [architecture.md](architecture.md); for the broader
functional requirements, see [REQUIREMENT.md](REQUIREMENT.md).

## Why this exists

Before this layer, provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`) were plain environment variables read
directly off `Settings`. That meant:

- every deployment had to inject raw secrets as container env vars (visible in
  `docker inspect`, process environment dumps, CI logs if misconfigured),
- rotating a credential meant restarting the backend,
- there was no audit trail of who/what read or changed a credential,
- there was no way to give different tenants/customers their own provider keys.

The Secret Provider layer fixes all four without hardcoding this gateway to any one
secret backend.

## Architecture

```
backend/app/secrets/
  base.py               SecretProvider ABC -- get_secret / set_secret / delete_secret
  factory.py             get_secret_provider(settings) -> SecretProvider
  service.py             SecretService -- Redis cache + rotation in front of a provider
  infisical_provider.py  Default. Universal Auth (machine identity) + secret paths.
  aws_provider.py        AWS Secrets Manager.
  gcp_provider.py        Google Cloud Secret Manager.
  azure_provider.py      Azure Key Vault.
  vault_provider.py      HashiCorp Vault (KV v2).
```

```
services/routing/model_registry.py (_litellm_params_for, build_router)
        |
        v
  SecretService.get_secret("OPENAI_API_KEY")      <-- routing/chat/embeddings call this,
        |                                              never a concrete provider directly
        v
  Redis/Valkey cache (secret:{tenant}:{name}, TTL 300s)
        | (miss)
        v
  SecretProvider.get_secret(name, tenant)   <-- exactly one concrete class, chosen by
        |                                        SECRET_PROVIDER at startup
        v
  Infisical / AWS Secrets Manager / GCP Secret Manager / Azure Key Vault / Vault
```

Nothing outside `app/secrets/` imports a concrete provider class or a provider SDK
(`infisical_sdk`, `boto3`, `google.cloud.secretmanager`, `azure.keyvault.secrets`,
`hvac`). Every caller — the LiteLLM integration, the admin API — goes through
`get_secret_provider()` / `SecretService` instead, so swapping backends never
touches a call site.

**A second real consumer, beyond LLM routing:** the API Registry's
`RestExecutor` (`services/api_registry/rest_executor.py`) resolves every
credential for a registered REST API service — API key, bearer token, basic
auth username/password, OAuth2 client-credentials client ID/secret — through
this exact same `SecretService.get_secret()` call, never a raw environment
variable. This is a deliberate improvement over the MCP Server Registry's own
outbound auth (`services/mcp/mcp_client.py`'s `_resolve_auth_headers`, which
still reads a named env var directly) — see
[api-registry.md](api-registry.md) for the full picture.

### Why a `SecretService` on top of `SecretProvider`

`SecretProvider` implementations are deliberately dumb: read/write/delete against
one backend, nothing else. `SecretService` adds the two things every caller needs
regardless of backend:

1. A short-lived cache (see "Caching" below), so the hot LLM-routing path doesn't
   make a network call to the secret backend on every single request.
2. A place to hang cache invalidation (`invalidate`) and forced refresh
   (`force_refresh=True`) for rotation, without every provider having to
   reimplement that.

## Provider onboarding guide

To add a new secret backend:

1. Create `app/secrets/<name>_provider.py` implementing `SecretProvider`
   (`get_secret`, `set_secret`, `delete_secret`, each accepting an optional
   `tenant: str | None`).
2. Import the SDK **lazily**, inside `__init__` (or lazily behind a property, if
   constructing the SDK client itself makes a network/credential-resolution call
   -- see `GCPSecretProvider._resolved_client` for why `google-cloud-secret-manager`
   specifically needs this).
3. Add the branch to `app/secrets/factory.py::get_secret_provider` and a name to
   `PROVIDER_NAMES`.
4. Add an `is_provider_available()` branch (a cheap "is this deployment even
   configured for it" check for the admin UI — not a live connectivity probe).
5. Add the new provider's config fields to `Settings` (`core/config.py`).
6. Write `tests/test_<name>_provider.py` (or add cases to
   `tests/test_secret_providers.py`) mocking the SDK the same way the existing
   providers' tests do.

None of steps 1-6 touch `model_registry.py`, `router.py`, or `api/v1/secrets.py` --
that's the point of the abstraction.

### Currently supported providers

| Provider | `SECRET_PROVIDER` | Auth | Namespacing (tenant) |
|---|---|---|---|
| Infisical (default) | `infisical` | Universal Auth (machine identity client id/secret) | Secret path/folder: `/{tenant}` |
| AWS Secrets Manager | `aws` | boto3 default credential chain (env/instance role/~/.aws) | Name prefix: `{prefix}/{tenant}/{name}` |
| Google Secret Manager | `gcp` | Application Default Credentials | Secret ID: `{tenant}__{name}` |
| Azure Key Vault | `azure` | `DefaultAzureCredential` (managed identity/CLI/env) | Secret name: `{tenant}-{name}` (`_` normalized to `-`) |
| HashiCorp Vault | `vault` | Static token (`VAULT_TOKEN`) against a KV v2 mount | Path: `{tenant}/{name}` |

`tenant=None` (the default, and the only namespace a single-tenant deployment ever
needs) maps to each provider's root path/prefix.

## Configuration

All of this lives in `backend/.env` (the settings live in `core/config.py`; they
could not be added to `backend/.env.example` in this pass due to a local
permission restriction on that file -- add them there manually):

```
SECRET_PROVIDER=infisical          # infisical | aws | gcp | azure | vault
SECRET_CACHE_TTL_SECONDS=300

# Infisical (default)
INFISICAL_SITE_URL=http://localhost:8081
INFISICAL_CLIENT_ID=
INFISICAL_CLIENT_SECRET=
INFISICAL_PROJECT_ID=
INFISICAL_ENVIRONMENT=prod          # dev | staging | prod

# AWS Secrets Manager
AWS_SECRETS_REGION=
AWS_SECRET_NAME_PREFIX=llm-gateway

# Google Secret Manager
GCP_PROJECT_ID=

# Azure Key Vault
AZURE_KEYVAULT_NAME=

# HashiCorp Vault
VAULT_ADDR=
VAULT_TOKEN=
VAULT_MOUNT_POINT=secret
```

Only the config for the active `SECRET_PROVIDER` needs to be filled in — the other
four providers' modules are never imported if they're not selected.

### Secret names this gateway looks up

| Secret name | Used for |
|---|---|
| `OPENAI_API_KEY` | OpenAI chat/embeddings |
| `ANTHROPIC_API_KEY` | Anthropic chat |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Bedrock (region itself is *not* a secret — see `Settings.aws_region_name`) |
| `GOOGLE_API_KEY` | Reserved for a future Google Gemini routing target |
| `AZURE_OPENAI_KEY` | Reserved for a future Azure OpenAI routing target |

Under Infisical's default project/environment, these live at
`LLM_GATEWAY/{secret_name}` (project `llm-gateway`, environment DEV/STAGING/PROD)
as specified — the gateway itself only needs `INFISICAL_PROJECT_ID`/
`INFISICAL_ENVIRONMENT` pointed at that project+environment; it does not hardcode
the `LLM_GATEWAY/` path prefix (that's an Infisical *folder* naming convention on
the secrets themselves, not something the client needs to know).

## Security model

- **Values never reach Postgres.** `secret_audit_log` records *who did what to
  which secret name*, never a value. `SecretAuditLog` has no column that could
  hold one.
- **Values are never returned by any API.** `GET /admin/secrets/status` returns
  `{"provider": "OPENAI", "status": "configured"}`, never the key itself.
- **Values are never logged.** No `logger.info(f"...{value}...")` exists anywhere
  in this layer; errors are raised with the secret *name*, never the value.
- **Values ARE cached in Redis/Valkey, for up to `SECRET_CACHE_TTL_SECONDS`
  (default 300s).** This is a deliberate, bounded-risk tradeoff, not an oversight:
  without it, every single `/v1/chat/completions` or `/v1/embeddings` call would
  make an outbound network call to Infisical/AWS/GCP/Azure/Vault just to fetch a
  credential it already resolved five seconds ago — real added latency and real
  load on the secret backend, on every request. A 5-minute TTL cache bounds the
  blast radius of "value sitting in Redis" to a short, known window, and
  `POST /admin/secrets/rotate` invalidates it immediately on demand.
  **If your threat model doesn't tolerate a secret value ever touching Redis**
  (e.g. Redis isn't fully within your trust boundary), the fix is local:
  `SecretService` takes any object exposing `get`/`set`/`delete` as its `client`
  — swap in an in-process (per-worker, non-shared) cache instead of the shared
  Valkey client, at the cost of a cache miss (and a real provider round trip) on
  every worker's first request for each secret after a restart.
- **Outbound authentication to each backend never uses a credential this
  gateway's own config stores directly** — Infisical uses its own machine
  identity; AWS/GCP/Azure use their respective standard credential chains
  (IAM role, ADC, managed identity); only Vault's static token is genuinely
  "a credential in our config," which is inherent to how Vault token auth works
  (a real deployment would typically swap this for AppRole or a Kubernetes auth
  method instead of a static root/period token).

## Rotation

`POST /admin/secrets/rotate` (admin-only):

```json
{"secret_name": "OPENAI_API_KEY", "tenant": null}
```

1. Invalidates the Redis cache entry for `{tenant}:{secret_name}`.
2. Re-fetches from the provider with `force_refresh=True` (bypasses cache, then
   re-populates it with whatever the provider returns now).
3. Records a `secret_audit_log` row (`operation=rotate`, success/error).
4. Returns `{"secret_name": ..., "provider": ..., "status": "rotated"|"error"}` --
   never the value.

This covers "provider refresh" and "cache invalidation" as one action: the actual
*generation* of a new credential value happens in the secret backend itself
(Infisical/AWS/.../Vault's own rotation feature or an operator manually updating
it there) — this endpoint's job is making sure the gateway stops using its stale
cached copy the moment that happens, without waiting out the TTL.

## Multi-tenant secret isolation

Every `SecretProvider` method accepts `tenant: str | None`. `None` (the default)
is the shared/default namespace every single-tenant deployment uses. When a
tenant is given, each provider maps it to that backend's own namespacing concept
(see the table above) — so e.g. tenant `customer1` and tenant `customer2` can
each have their own `OPENAI_API_KEY` without colliding, whether that's two
folders in one Infisical project, two prefixes in one AWS account, or (for a
harder isolation requirement) tenant `customer1` pointed at an entirely separate
Infisical *project* by giving that tenant its own `SecretProvider` instance
configured with a different `infisical_project_id`.

**Scope note:** this pass wires the full tenant-parameterized capability through
`SecretProvider`/`SecretService` and covers it with tests, but does **not** thread
a real `tenant_id` (e.g. `organization_id`) through `GatewayRouter`/`build_router`
for actual chat/embeddings calls yet — today's LLM routing always resolves
credentials in the default namespace, matching the fact that `provider_configs`
(which providers are enabled) isn't tenant-scoped today either. Wiring
`organization_id` through as `tenant` on every `GatewayRouter.complete()`/`embed()`
call is the natural next step if/when per-tenant BYO-provider-keys becomes a real
product requirement — the secret layer itself is already ready for it.

## Audit logging

Every **administrative** secret operation writes a `secret_audit_log` row via
`services/logging_service.record_secret_audit` (same "BackgroundTask after the
response is sent" discipline as request/MCP logging — never adds latency):

- `GET /admin/secrets/status` — one `get` row per underlying secret name checked.
- `POST /admin/secrets/rotate` — one `rotate` row.

**Scope note:** the routing hot path (`model_registry._litellm_params_for`,
called on every chat/embedding request) does **not** write an audit row per
credential read. Doing so would mean one or more audit-log INSERTs on every
single LLM call — the same volume as `request_logs`, for a signal `request_logs`
already carries indirectly (which provider/model resolved). If a stricter
"literally every read is audited" posture becomes a requirement, the extension
point is `SecretService.get_secret`, not the routing code that calls it.

## Deployment patterns

- **Docker Compose (dev/small deployments):** point `SECRET_PROVIDER=infisical`
  at Infisical Cloud (`INFISICAL_SITE_URL=http://localhost:8081`) or a
  self-hosted Infisical instance's URL — this repo does not bundle a self-hosted
  Infisical stack; see `docker-compose.yml`'s `gateway-backend` environment block
  for the full variable list.
- **AWS deployments:** set `SECRET_PROVIDER=aws`, `AWS_SECRETS_REGION`, and rely on
  the task/instance's IAM role for credentials (no static AWS keys in this
  gateway's own config).
- **GCP deployments:** set `SECRET_PROVIDER=gcp`, `GCP_PROJECT_ID`, and run on a
  service account with Secret Manager access (Application Default Credentials).
- **Azure deployments:** set `SECRET_PROVIDER=azure`, `AZURE_KEYVAULT_NAME`, and
  run under a managed identity with Key Vault Secrets User access.
- **On-prem / air-gapped:** `SECRET_PROVIDER=vault` against an internal Vault
  cluster; swap the static `VAULT_TOKEN` for a short-lived one from your own
  auth method in front of this config.
