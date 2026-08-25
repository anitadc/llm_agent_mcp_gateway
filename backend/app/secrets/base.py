from abc import ABC, abstractmethod


class SecretProvider(ABC):
    """Every secret backend (this app's own Postgres database, AWS Secrets
    Manager, GCP Secret Manager, Azure Key Vault, HashiCorp Vault, ...)
    implements this interface. Nothing outside app/secrets/ imports a provider
    module directly or a provider SDK -- every caller goes through
    get_secret_provider()/SecretService instead, so swapping backends never
    touches call sites (routing, admin API, tests).

    `tenant` is an optional namespace for multi-tenant secret isolation: each
    provider maps it to its own native namespacing concept (a Postgres/AWS/Vault
    row or path prefix, a GCP/Azure name prefix). `None` means the
    default/shared namespace -- the only namespace a single-tenant deployment
    ever needs.
    """

    @abstractmethod
    async def get_secret(self, secret_name: str, tenant: str | None = None) -> str | None:
        """Returns the secret's current value, or None if it doesn't exist."""
        ...

    @abstractmethod
    async def set_secret(self, secret_name: str, value: str, tenant: str | None = None) -> None:
        """Creates the secret if it doesn't exist yet, otherwise updates it."""
        ...

    @abstractmethod
    async def delete_secret(self, secret_name: str, tenant: str | None = None) -> None:
        ...
