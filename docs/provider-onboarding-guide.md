# Adding a New Identity Provider

Adding provider #7 requires exactly three things, and touches no other file
in the codebase:

1. A new provider class
2. Its configuration fields
3. Factory registration

Nothing in `middleware/auth_middleware.py`, `services/auth_service.py`,
`services/policy_engine.py`, or any API route needs to change -- they all
depend on `IdentityProvider`/`UserIdentity`, never a concrete class.

## Step by step

### 1. Add configuration fields (`backend/app/core/config.py`)

```python
newidp_domain: str | None = None
newidp_client_id: str | None = None
# ...whatever this IdP's discovery/JWKS/audience convention needs
```

If the tenant secret story matters (a confidential-client flow), don't add a
`newidp_client_secret` plain field -- resolve it via the Secret Provider layer
(`SecretService.get_secret("NEWIDP_CLIENT_SECRET")`) at the point you actually
need it, same as every other credential in this app.

### 2. Create the provider (`backend/app/identity/newidp_provider.py`)

```python
from typing import Any

from app.core.config import Settings
from app.identity.base import IdentityProvider, validate_oidc_jwt


class NewIdpProvider(IdentityProvider):
    name = "newidp"

    def __init__(self, settings: Settings) -> None:
        self._issuer = f"https://{settings.newidp_domain}/"
        self._jwks_url = f"{self._issuer}.well-known/jwks.json"
        self._audience = settings.newidp_client_id

    async def validate_token(self, token: str) -> dict[str, Any]:
        return validate_oidc_jwt(token, jwks_url=self._jwks_url, issuer=self._issuer, audience=self._audience)

    async def get_user_info(self, token: str) -> dict[str, Any]:
        claims = await self.validate_token(token)
        return {"user_id": claims["sub"], "email": claims.get("email"), "tenant_id": ..., "attributes": {}}

    async def get_roles(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        return list(claims.get("roles", []))

    async def get_groups(self, token: str) -> list[str]:
        claims = await self.validate_token(token)
        return list(claims.get("groups", []))
```

If this IdP isn't a standard OIDC/JWKS provider (unlikely for an enterprise
IdP, but possible), implement `validate_token` however is appropriate --
`validate_oidc_jwt` is a convenience for the common case, not a requirement of
the interface.

**Never import an SDK at module level if constructing its client makes a
network/credential-resolution call.** `GCPSecretProvider` in the Secret
Provider layer got this wrong once (fixed) -- see
[secret-management.md](secret-management.md)'s onboarding guide for the same
lesson applied there. If your new provider's SDK client construction is
similarly eager, defer it behind a lazily-initialized property.

### 3. Register it (`backend/app/identity/factory.py`)

```python
PROVIDER_NAMES = [..., "newidp"]

def _build_provider(name: str, settings: Settings) -> IdentityProvider:
    ...
    if name == "newidp":
        from app.identity.newidp_provider import NewIdpProvider
        return NewIdpProvider(settings)
    ...

def is_provider_available(name: str, settings: Settings) -> bool:
    ...
    if name == "newidp":
        return bool(settings.newidp_domain)
    ...
```

### 4. Update the `IdentityProviderName` enum and its Alembic migration

`users.identity_provider` and `tenant_identity_config.provider` are typed
Postgres enums (matching this codebase's convention for every other
categorical column). Add the new value to
`db/models/enums.py::IdentityProviderName` and ship an
`ALTER TYPE identity_provider_name ADD VALUE 'newidp'` migration. This is the
one piece of "just three things" that technically touches the database, but
it's additive and doesn't change any existing behavior.

### 5. Write tests (`tests/identity/test_newidp.py`)

Follow the existing pattern (`test_entra.py` is a good template): construct
the provider directly, mock `validate_token` with canned claims, assert
`get_user_info`/`get_roles`/`get_groups`/`get_user_identity` map correctly.
The shared JWT validation itself is already covered generically by
`test_jwt_validation.py` -- you don't need to re-test signature/issuer/
audience/expiry handling per provider.

### 6. Frontend

`PROVIDER_LABELS` in `frontend/src/pages/IdentitySettings.jsx` is the only
frontend change -- add a display label. The settings page itself (active
provider display, tenant configs, access policies, session display) needs no
other changes; it already renders whatever `GET /admin/identity/providers`
reports.

## What you do NOT need to touch

- `middleware/auth_middleware.py` -- already generic over any `IdentityProvider`.
- `services/auth_service.py` -- `sync_user_from_identity` already works off `UserIdentity`.
- `services/policy_engine.py` -- already generic over `UserIdentity.roles`/`.provider`.
- Any `api/v1/*.py` route -- none of them know or care which IdP authenticated the caller.
- The LLM Gateway routing engine or LiteLLM integration -- entirely unrelated to authentication.
