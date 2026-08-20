from typing import Any

from pydantic import BaseModel, Field


class UserIdentity(BaseModel):
    """The provider-agnostic shape every IdentityProvider maps into. Whatever a
    given IdP calls its role claim (Keycloak's `realm_access.roles`, Entra's
    `roles`, Auth0's namespaced custom claim, Okta's `groups`, ...), callers
    outside app/identity/ only ever see `UserIdentity.roles`."""

    user_id: str
    email: str | None = None
    tenant_id: str | None = None
    provider: str
    roles: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
