import uuid

from app.core.config import Settings
from app.core.exceptions import AuthError
from app.core.logging import get_logger, log_method
from app.core.security import generate_api_key, hash_api_key
from app.db.models.api_key import ApiKey
from app.db.models.enums import IdentityProviderName, UserRole
from app.db.models.user import User
from app.identity.models import UserIdentity
from app.repositories.api_key_repo import ApiKeyRepo
from app.repositories.user_repo import UserRepo
from app.services.cache_service import CacheService

logger = get_logger(__name__)


class AuthService:
    def __init__(
        self,
        api_key_repo: ApiKeyRepo,
        user_repo: UserRepo,
        cache: CacheService,
        settings: Settings,
    ) -> None:
        self.api_key_repo = api_key_repo
        self.user_repo = user_repo
        self.cache = cache
        self.settings = settings

    @log_method(logger)
    async def issue_api_key(self, name: str, project_id: uuid.UUID, scopes: list[str]) -> tuple[ApiKey, str]:
        raw_key, prefix, hashed_key = generate_api_key(
            self.settings.api_key_prefix, self.settings.api_key_secret_pepper
        )
        api_key = await self.api_key_repo.add(
            ApiKey(project_id=project_id, hashed_key=hashed_key, prefix=prefix, name=name, scopes=scopes)
        )
        logger.info("api_key_issued", api_key_id=str(api_key.id), project_id=str(project_id), scope_count=len(scopes))
        return api_key, raw_key

    @log_method(logger)
    async def revoke_api_key(self, api_key: ApiKey) -> None:
        await self.api_key_repo.revoke(api_key)
        await self.cache.delete(f"apikey:{api_key.hashed_key}")
        logger.info("api_key_revoked", api_key_id=str(api_key.id))

    @log_method(logger)
    async def verify_api_key(self, raw_key: str) -> ApiKey:
        """A cache lookup/write failure degrades to `cached_id is None` (see
        CacheService) -- verification still succeeds via `get_by_hashed_key`, just
        without the cache short-circuit, so a Valkey outage costs latency, not
        availability."""
        hashed_key = hash_api_key(raw_key, self.settings.api_key_secret_pepper)
        cache_key = f"apikey:{hashed_key}"

        cached_id = await self.cache.get_raw(cache_key)
        if cached_id:
            api_key = await self.api_key_repo.get(uuid.UUID(cached_id))
            if api_key and api_key.is_active:
                return api_key

        api_key = await self.api_key_repo.get_by_hashed_key(hashed_key)
        if api_key is None:
            logger.warning("api_key_verification_failed", reason="not_found")
            raise AuthError("Invalid or missing API key")

        await self.cache.set_raw(cache_key, str(api_key.id))
        await self.api_key_repo.touch_last_used(api_key)
        return api_key

    @log_method(logger)
    async def sync_user_from_identity(self, identity: UserIdentity) -> User:
        """Find-or-create the internal User row for an already-validated
        UserIdentity, regardless of which IdentityProvider produced it --
        replaces the old Keycloak-only `authenticate_keycloak`. Role derivation
        (mapping the IdP's roles onto this app's UserRole) and upsert-by-subject
        are now identical for all six providers; a subject id is only looked up
        *within* its own provider (see User.__table_args__)."""
        provider = IdentityProviderName(identity.provider)
        role = next((r for r in UserRole if r.value in identity.roles), UserRole.viewer)

        user = await self.user_repo.get_by_external_sub(provider, identity.user_id)
        if user is not None:
            return user

        if identity.email:
            user = await self.user_repo.get_by_email(identity.email)
            if user is not None:
                user.identity_provider = provider
                user.external_sub = identity.user_id
                await self.user_repo.db.flush()
                logger.info("user_identity_linked", user_id=str(user.id), provider=provider.value)
                return user

        new_user = await self.user_repo.add(
            User(
                identity_provider=provider,
                external_sub=identity.user_id,
                email=identity.email or f"{identity.user_id}@unknown.local",
                role=role,
            )
        )
        logger.info("user_provisioned", user_id=str(new_user.id), provider=provider.value, role=role.value)
        return new_user
