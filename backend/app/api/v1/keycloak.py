import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.schemas.user import UserCreate

settings = get_settings()

KEYCLOAK_BASE_URL = "http://keycloak:8080"
KEYCLOAK_REALM = "gateway"
KEYCLOAK_CLIENT_ID = "gateway-frontend"
KEYCLOAK_ADMIN_USER = "admin@gateway.local"
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
        password_value = getattr(body, "password", username)

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
                    "value": password_value,
                    "temporary": False,
                }
            ]
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(admin_url, json=keycloak_payload, headers=headers, timeout=10.0)
            response.raise_for_status()