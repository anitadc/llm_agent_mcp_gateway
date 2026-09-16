import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.schemas.user import UserCreate
from app.db.models.enums import UserRole

settings = get_settings()

KEYCLOAK_BASE_URL = "http://keycloak:8080"
# KEYCLOAK_BASE_URL = "http://localhost:8180"
KEYCLOAK_REALM = "tcsaigateway"
KEYCLOAK_CLIENT_ID = "tcsaigateway-frontend"
KEYCLOAK_ADMIN_USER = "admin@tcsaigateway.local"
KEYCLOAK_ADMIN_PASS = "admin123"

class Keycloak:
    async def get_keycloak_admin_token() -> str:
        """Authenticates with Keycloak using httpx to obtain an admin bearer token."""
        token_url = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
        payload = {
            "grant_type": "password",
            "client_id": KEYCLOAK_CLIENT_ID,
            "username": KEYCLOAK_ADMIN_USER,
            "password": KEYCLOAK_ADMIN_PASS,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=payload, timeout=10.0)
            response.raise_for_status()
            return response.json()["access_token"]


    async def create_keycloak_user(admin_token: str, body: UserCreate) -> None:
        """Provisions a new user in Keycloak asynchronously with payload details."""
        admin_url = f"{KEYCLOAK_BASE_URL}/admin/realms/{KEYCLOAK_REALM}/users"
        headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        }

        username = body.email.split("@")[0]
        # password_value = getattr(body, "password", username)

        keycloak_payload = {
            "username": username,
            "email": body.email,
            "enabled": True,
            "emailVerified": True,
            "attributes": {
                "locale": ["en"]
            },
            "credentials": [
                {
                    "type": "password",
                    "value": "defaultPassword123!",  # Default password; should be changed by user
                    "temporary": False,
                }
            ]
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(admin_url, json=keycloak_payload, headers=headers, timeout=10.0)
            response.raise_for_status()

    async def get_realm_roles(admin_token: str) -> list[dict]:
        """Retrieves all realm roles from Keycloak asynchronously."""
        roles_url = f"{KEYCLOAK_BASE_URL}/admin/realms/{KEYCLOAK_REALM}/roles"
        headers = {
            "Authorization": f"Bearer {admin_token}",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(roles_url, headers=headers, timeout=10.0)
            response.raise_for_status()
            return response.json()

    async def get_keycloak_user_by_username(admin_token: str, username: str) -> list[dict]:
        """Fetches user details from Keycloak by username using the Admin REST API."""
        admin_url = f"{KEYCLOAK_BASE_URL}/admin/realms/{KEYCLOAK_REALM}/users"
        headers = {
            "Authorization": f"Bearer {admin_token}",
        }
        params = {
            "username": username,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                admin_url, 
                headers=headers, 
                params=params, 
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()

    async def assign_realm_roles(admin_token: str, user_id: str, realm_roles: list[dict], assign_role:UserRole) -> None:
        """Assigns realm-level roles to a specific user in Keycloak."""
        role_mapping_url = f"{KEYCLOAK_BASE_URL}/admin/realms/{KEYCLOAK_REALM}/users/{user_id}/role-mappings/realm"
        headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            for role in realm_roles:
                if role["name"] == assign_role.value:
                    response = await client.post(role_mapping_url, json=[role], headers=headers, timeout=10.0)
                    response.raise_for_status()
