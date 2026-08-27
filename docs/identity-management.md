# Identity Management — Overview

A short index for the Identity Provider layer. For depth, follow the links --
this page is deliberately just a map.

## What it is

A pluggable abstraction (`backend/app/identity/`) that authenticates human
(dashboard/admin) users against any of six enterprise Identity Providers --
Keycloak (default), Microsoft Entra ID, Auth0, Okta Workforce Identity Cloud,
AWS IAM Identity Center, or Google Identity Platform/Workspace -- without any
provider-specific logic in API routes, the routing engine, the policy engine,
or the LiteLLM integration. It mirrors the [Secret Provider layer](secret-management.md)'s
shape on purpose: same `base.py` + `factory.py` structure, same "lazy import,
never a hardcoded dependency" discipline.

## Read next

| Question | Document |
|---|---|
| How is it built, and why these design choices? | [identity-provider-architecture.md](identity-provider-architecture.md) |
| How do I add IdP #7? | [provider-onboarding-guide.md](provider-onboarding-guide.md) |
| What security guarantees does it make? | [security-model.md](security-model.md) |
| Where does this fit in the whole system? | [architecture.md](architecture.md) |
| What are the formal requirements? | [REQUIREMENT.md](REQUIREMENT.md) §5.1, §7 |
| How do I configure/run it? | [../README.md](../README.md) |

## At a glance

- **Default provider**: Keycloak, unchanged from before this layer existed --
  existing deployments need zero configuration changes.
- **Switch providers**: `IDENTITY_PROVIDER=entra|auth0|okta|aws_identity|google`
  + that provider's own env vars, then restart.
- **Multi-tenant**: `tenant_identity_config` lets different customers run
  different IdPs against the same gateway process, resolved by token issuer.
- **RBAC/ABAC**: `access_policies`, evaluated generically over
  `UserIdentity.roles`/`.provider` -- never a concrete provider. Also carries
  `allowed_tool_names`, gating which MCP tools -- server-backed or REST-backed
  (see [api-registry.md](api-registry.md)) -- a policy permits, evaluated the
  same way regardless of tool kind.
- **Admin UI**: Settings → Identity Providers (active provider status, tenant
  configs, access policies, your current session's mapped identity).
- **What's NOT built**: enforcement of `AccessPolicy.max_tokens`; a frontend
  SDK swap per provider (MSAL.js for Entra, etc. -- the backend abstraction
  doesn't require one, but a deployment standardizing on a non-Keycloak IdP
  would still want its native login SDK in the browser); full AWS IAM
  Identity Center permission-set resolution; Google Workspace Admin SDK
  Directory API calls for real role/group data. All stated explicitly, not
  silently absent -- see the scope notes in
  [identity-provider-architecture.md](identity-provider-architecture.md).
