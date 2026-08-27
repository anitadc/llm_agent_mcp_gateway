# Identity Layer Security Model

## JWT signature validation

Every token is validated against the RS256 public key published by its
issuer's JWKS endpoint (`identity/base.py::validate_oidc_jwt`) -- never a
shared secret, never `alg: none`, and the algorithm list passed to
`jwt.decode` is hardcoded to `["RS256"]` so a token can't downgrade the
algorithm itself. A token signed by a key this gateway doesn't recognize (or
signed with a different key than the one its `kid` claims) is rejected; this
is covered directly by
`tests/identity/test_jwt_validation.py::test_rejects_a_token_signed_by_a_different_key`.

## JWKS caching

Signing keys are cached per JWKS URL (`functools.lru_cache` on
`_jwks_client`), so a validated provider doesn't re-fetch its issuer's JWKS on
every single request -- only on first use per URL (and whenever `PyJWKClient`
itself decides a key rotation requires a refresh, which it detects via the
token's `kid` header not matching any cached key).

## Token expiration validation

`verify_exp: True` is always passed to `jwt.decode` -- an expired token is
rejected regardless of everything else being valid. There is no grace period.

## Issuer validation

`verify_iss` is enabled whenever an `issuer` is supplied (every provider
except AWS IAM Identity Center's audience-less case still supplies an issuer)
-- a token whose `iss` claim doesn't match rejects, even if signed by a key
that happens to be in the right JWKS set (relevant for providers where
multiple tenants could theoretically share infrastructure).

## Audience validation

`verify_aud` is enabled whenever an `audience` is configured. AWS IAM
Identity Center is the one provider that passes `audience=None` (see
[identity-provider-architecture.md](identity-provider-architecture.md)'s scope
note on why IAM Identity Center has no fixed audience convention) --
everywhere else, a token issued for a different application is rejected.

## No password storage

This layer never sees, stores, or forwards a password. It only ever validates
an already-issued bearer token; the actual login (redirect, credential entry,
MFA) happens entirely at the IdP, outside this gateway. `keycloak-js` (or
whatever SDK a deployment's frontend uses for its chosen IdP) never sends a
password to this backend.

## No token logging

No log statement, exception message, or audit row anywhere in `app/identity/`
includes a raw token or its claims verbatim. `AuthError` messages describe
*why* validation failed (expired, wrong issuer, wrong audience, bad
signature) without echoing the token itself. `secret_audit_log` (the adjacent
Secret Provider layer's audit trail) has the same property for credential
values -- see [secret-management.md](secret-management.md)'s security model.

## Secure session handling

- The frontend never persists a token to `localStorage`/`sessionStorage`
  itself -- `keycloak-js` (or the equivalent SDK for a swapped-in IdP) manages
  token storage and silent refresh internally, via `authService.getToken()`'s
  `updateToken(30)` call before every request.
- The backend is stateless with respect to sessions: every request
  independently re-validates its bearer token; there is no server-side
  session store to fixate or hijack.
- `Principal` (the auth middleware's per-request result) lives only in
  `request.state` for the duration of one request -- it is never persisted,
  cached across requests, or shared between requests.
- Internal `User` rows are looked up by `(identity_provider, external_sub)` --
  a subject id is only meaningful *within* the provider that issued it, so two
  different IdPs minting the same string (astronomically unlikely, but not
  impossible by construction) can never be confused for the same person. See
  `User.__table_args__`.

## What this layer deliberately does NOT do

- It does not perform the OAuth2 authorization-code flow itself (no
  `authlib`, despite being a common choice for that) -- the frontend/IdP SDK
  already handles obtaining a token; this backend only ever validates one
  that already exists. Adding an authorization-code flow here would be new
  scope, not a gap in what exists today.
- It does not introspect tokens via each provider's token-introspection
  endpoint -- JWKS-based local validation is faster (no network call per
  request beyond the cached JWKS fetch) and is the standard pattern for a
  resource server validating tokens issued by a third-party IdP.
- It does not enforce `AccessPolicy.max_tokens` yet (see
  [identity-provider-architecture.md](identity-provider-architecture.md)'s RBAC/ABAC
  section) -- stored and returned by the admin API, not yet applied to a
  request, exactly like `Budget`'s spend ceiling.
