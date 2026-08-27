# Identity Provider Abstraction Layer

This document covers the pluggable Identity Provider layer that authenticates
human (dashboard/admin) users. For the LLM Gateway's overall architecture, see
[architecture.md](architecture.md); for machine-to-machine auth (API keys,
which this layer does not touch), see [REQUIREMENT.md](REQUIREMENT.md) §5.1.
For the analogous credential-abstraction layer this design deliberately
mirrors, see [secret-management.md](secret-management.md) -- the two share the
same shape (base interface, factory, pluggable backends, "no hardcoded
provider logic in call sites") on purpose.

## Why this exists

Before this layer, `AuthMiddleware` called Keycloak-specific JWKS/JWT
validation directly. That meant:

- an enterprise customer already standardized on Entra ID, Auth0, Okta, AWS
  IAM Identity Center, or Google Workspace couldn't use this gateway without
  running a second identity system (Keycloak) just for it,
- there was no consistent shape for "this user's roles/groups" across
  providers -- each one exposes RBAC differently,
- supporting a second customer on a *different* IdP than the first would have
  meant branching logic throughout the auth path.

## Architecture

```
backend/app/identity/
  base.py                  IdentityProvider ABC + validate_oidc_jwt() (shared JWKS/JWT validation)
  models.py                 UserIdentity -- the provider-agnostic shape every provider maps into
  factory.py                 get_identity_provider() / build_provider_from_tenant_config() / peek_unverified_issuer()
  keycloak_provider.py      Default.
  entra_provider.py         Microsoft Entra ID (Azure AD).
  auth0_provider.py         Auth0.
  okta_provider.py          Okta Workforce Identity Cloud.
  aws_identity_provider.py  AWS IAM Identity Center.
  google_identity_provider.py  Google Identity Platform / Workspace.
```

```
Application
     |
POST /v1/... (Bearer <token>)
     |
AuthMiddleware
     |
Identity Provider Factory  <-- resolves WHICH provider: tenant_identity_config
     |                          match on the token's issuer, else the global
     |                          IDENTITY_PROVIDER default
Selected IdentityProvider
     |
validate_token()  --(JWKS)-->  Keycloak | Entra | Auth0 | Okta | AWS Identity Center | Google
     |
get_user_identity()  -->  UserIdentity (user_id, email, tenant_id, provider, roles, groups, attributes)
     |
AuthService.sync_user_from_identity()  -->  internal User row (find-or-create)
     |
Principal(kind="user", user=User, identity=UserIdentity)
     |
   Policy Engine (RBAC/ABAC, see below) -- evaluated at specific call sites, not globally
     |
Request handler
```

Nothing outside `app/identity/` imports a concrete provider class or a
provider SDK. Every caller goes through `get_identity_provider()` /
`AuthMiddleware`, and from there only ever touches `UserIdentity` -- never a
provider-specific claim shape.

### Why an ABC with exactly four methods, plus one concrete one

`validate_token`, `get_user_info`, `get_roles`, `get_groups` are the four
primitives every IdP implements differently (that's genuinely where the
provider-specific logic lives -- different claim names, different tenant
concepts, different RBAC conventions). `get_user_identity()` (concrete, not
abstract, defined once on `IdentityProvider` itself) composes those four into
the `UserIdentity` every caller actually uses. A new provider only ever
implements the four primitives; it gets the composition for free.

### The shared JWT validator

All six providers (yes, including AWS IAM Identity Center -- its SSO token is
OIDC-flavored too) are validated by the exact same mechanism: fetch JWKS,
verify RS256 signature, verify issuer, verify audience, verify expiry. That
mechanism (`validate_oidc_jwt` in `base.py`) is implemented **once**, not once
per provider -- each provider's `validate_token()` is a thin wrapper supplying
its own `jwks_url`/`issuer`/`audience`. JWKS signing keys are cached per URL
(`functools.lru_cache`), so repeated validation only costs a network fetch
once per key set, not per request.

## Per-provider mapping (where "Group/Role mapping" actually differs)

| Provider | Roles claim | Groups claim | Tenant concept |
|---|---|---|---|
| Keycloak | `realm_access.roles` ∪ `resource_access.{client_id}.roles` | `groups` | Realm name |
| Entra ID | `roles` (App Roles) | `groups` (subject to "groups overage" -- see below) | `tid` (tenant GUID) |
| Auth0 | Configurable namespaced claim (`AUTH0_ROLES_CLAIM`) | Configurable namespaced claim (`AUTH0_GROUPS_CLAIM`) | The Auth0 domain itself |
| Okta | `roles` if configured, else falls back to `groups` | `groups` | The Okta domain |
| AWS IAM Identity Center | Whatever the trust broker injects (see scope note) | Same | The SSO instance ARN |
| Google | None (empty by design) | None (empty by design) | `hd` (Workspace hosted domain) |

**Scope notes, stated plainly rather than silently glossed over:**

- **Entra groups overage**: a user in more groups than fit inline triggers
  `_claim_names`/`hasgroups` instead of a populated `groups` array; resolving
  the full list requires a follow-up Microsoft Graph call this provider does
  not make.
- **Google Workspace roles/groups**: a plain Google ID token carries neither;
  both require an Admin SDK Directory API call, out of scope for pure
  ID-token validation. `google_workspace_domain` (the `hd` claim check) is the
  one piece of Workspace-specific behavior implemented.
- **AWS IAM Identity Center permission sets**: not carried in the SSO token
  itself; resolving "what can this user do in AWS" requires calling the
  Identity Store / SSO Admin API with the instance ARN. What's implemented is
  the generically useful slice -- validating that a token was genuinely issued
  by this instance and extracting whatever roles/groups claims a specific
  trust-broker configuration happens to inject.

## Multi-tenant identity support

`tenant_identity_config` (id, tenant_id, provider, **issuer**, configuration,
created_at) lets Customer A authenticate via Entra and Customer B via
Keycloak against the same running gateway process:

1. `AuthMiddleware` reads the token's `iss` claim **without verifying the
   signature yet** (`peek_unverified_issuer` -- never trusted for
   authorization, only for routing to the right provider).
2. Looks up `tenant_identity_config` by that issuer (a plain indexed string
   match -- `issuer` is denormalized specifically so this lookup doesn't need
   to inspect an arbitrary JSONB `configuration` blob).
3. If found, builds a one-off `IdentityProvider` from that tenant's
   `configuration` (Settings-field-name overrides layered onto a copy of the
   global config) via `build_provider_from_tenant_config`.
4. If not found, falls back to the global `IDENTITY_PROVIDER` default -- the
   only path a single-tenant deployment ever takes.
5. **Only then** is the token's signature actually verified, by whichever
   provider was selected.

`configuration` never holds a raw client secret -- a `*_client_secret_ref`
key inside it would name a Secret Provider entry instead (see
[secret-management.md](secret-management.md)), mirroring `McpServer.auth_config`
and `ProviderConfig.credential_ref` exactly. In practice today's providers
don't need a client secret for pure JWKS validation at all (see the
"reserved for future use" note in `core/config.py`), so this is currently an
unused-but-ready extension point, not a live code path.

## RBAC / ABAC integration

`services/policy_engine.py`'s `PolicyEngine.evaluate(project_id, roles,
identity_provider)` is a generic RBAC/ABAC gate: it never inspects which
concrete `IdentityProvider` authenticated the caller, only the
`UserIdentity.roles`/`.provider` fields every provider produces identically.

- No active `access_policies` row for a project means **unrestricted** (a
  deployment that hasn't configured any policy isn't suddenly locked out).
- Once at least one policy exists, access is granted if **any** policy
  matches (an OR across policies).
- Within one policy, an empty `allowed_roles` or `allowed_identity_providers`
  list means unrestricted on that dimension -- a policy can constrain just one
  axis without having to enumerate the other.
- `max_tokens` is stored and returned by the admin API but -- like `Budget`'s
  spend ceiling -- is **advisory only** in this version; it is not enforced
  against the actual request yet.

**Scope note on where this is wired in:** `chat.py`/`embeddings.py` are
deliberately API-key-only (see [REQUIREMENT.md](REQUIREMENT.md) §11 point
2 -- "Keycloak authenticates humans only"), so they never carry a
`UserIdentity` to evaluate a policy against; API keys are governed by their
own `scopes` mechanism instead, which is a different, already-adequate
authorization path for machine credentials. `PolicyEngine` is wired into
`POST /mcp`'s `tools/call` handling, and only for `user`-kind principals (MCP
already accepts both API keys and Keycloak/IdP-authenticated humans) --
API-key callers there are unaffected, exactly as before. Extending policy
enforcement to a human-authenticated LLM-calling path is a natural follow-up
if that access pattern becomes a real requirement; it isn't one the current
codebase's auth model supports today without a larger change.

## Configuration

```
IDENTITY_PROVIDER=keycloak   # keycloak | entra | auth0 | okta | aws_identity | google

# Keycloak (default) -- reuses the existing KEYCLOAK_* settings this app
# already had (KEYCLOAK_BASE_URL, not the shorter KEYCLOAK_URL some docs use,
# to avoid a breaking rename of already-deployed config)
KEYCLOAK_BASE_URL=
KEYCLOAK_REALM=
KEYCLOAK_CLIENT_ID=
KEYCLOAK_AUDIENCE=

# Microsoft Entra ID
ENTRA_TENANT_ID=
ENTRA_CLIENT_ID=

# Auth0
AUTH0_DOMAIN=
AUTH0_CLIENT_ID=
AUTH0_AUDIENCE=
AUTH0_ROLES_CLAIM=https://llm-gateway/roles
AUTH0_GROUPS_CLAIM=https://llm-gateway/groups

# Okta Workforce Identity Cloud
OKTA_DOMAIN=
OKTA_CLIENT_ID=

# AWS IAM Identity Center -- a distinct region setting from aws_region_name
# (Bedrock) / aws_secrets_region (Secrets Manager); a real deployment may run
# IAM Identity Center in a different region than either.
AWS_SSO_REGION=
AWS_SSO_INSTANCE_ARN=

# Google Identity Platform / Workspace
GOOGLE_CLIENT_ID=
GOOGLE_WORKSPACE_DOMAIN=
```

`*_CLIENT_SECRET` variables named in some IdP setup guides are deliberately
**not** plain env vars here -- they'd be resolved via the Secret Provider
layer (`{PROVIDER}_CLIENT_SECRET`) like every other credential in this app, if
and when a confidential-client flow (token introspection, client-credentials)
actually needs one. Today's validation is JWKS-only and doesn't.

See [../docs/secret-management.md](secret-management.md) for that layer, and
[provider-onboarding-guide.md](provider-onboarding-guide.md) for adding a
7th provider.
