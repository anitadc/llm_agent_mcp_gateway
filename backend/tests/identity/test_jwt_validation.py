import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.exceptions import AuthError
from app.identity.base import validate_oidc_jwt


def _keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _sign(private_key, **claim_overrides) -> str:
    now = int(time.time())
    claims = {"sub": "user-1", "iss": "https://issuer.test", "aud": "my-audience", "iat": now, "exp": now + 300}
    claims.update(claim_overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


def _patched_jwks(public_key):
    client = MagicMock()
    client.get_signing_key_from_jwt.return_value = MagicMock(key=public_key)
    return patch("app.identity.base._jwks_client", return_value=client)


def test_accepts_a_correctly_signed_token() -> None:
    private_key, public_key = _keypair()
    token = _sign(private_key)

    with _patched_jwks(public_key):
        claims = validate_oidc_jwt(token, jwks_url="https://issuer.test/jwks", issuer="https://issuer.test", audience="my-audience")

    assert claims["sub"] == "user-1"


def test_rejects_an_expired_token() -> None:
    private_key, public_key = _keypair()
    now = int(time.time())
    token = _sign(private_key, iat=now - 1000, exp=now - 500)

    with _patched_jwks(public_key), pytest.raises(AuthError):
        validate_oidc_jwt(token, jwks_url="https://issuer.test/jwks", issuer="https://issuer.test", audience="my-audience")


def test_rejects_the_wrong_audience() -> None:
    private_key, public_key = _keypair()
    token = _sign(private_key, aud="someone-elses-audience")

    with _patched_jwks(public_key), pytest.raises(AuthError):
        validate_oidc_jwt(token, jwks_url="https://issuer.test/jwks", issuer="https://issuer.test", audience="my-audience")


def test_rejects_the_wrong_issuer() -> None:
    private_key, public_key = _keypair()
    token = _sign(private_key, iss="https://not-the-expected-issuer.test")

    with _patched_jwks(public_key), pytest.raises(AuthError):
        validate_oidc_jwt(token, jwks_url="https://issuer.test/jwks", issuer="https://issuer.test", audience="my-audience")


def test_rejects_a_token_signed_by_a_different_key() -> None:
    _, public_key = _keypair()
    other_private_key, _ = _keypair()
    token = _sign(other_private_key)  # signed by a key whose public half we don't trust

    with _patched_jwks(public_key), pytest.raises(AuthError):
        validate_oidc_jwt(token, jwks_url="https://issuer.test/jwks", issuer="https://issuer.test", audience="my-audience")


def test_audience_none_skips_audience_verification() -> None:
    """AWSIdentityProvider passes audience=None since IAM Identity Center has no
    fixed audience convention -- the token here has no `aud` claim at all, and
    validation must still succeed."""
    private_key, public_key = _keypair()
    now = int(time.time())
    token = jwt.encode({"sub": "user-1", "iss": "https://issuer.test", "iat": now, "exp": now + 300}, private_key, algorithm="RS256")

    with _patched_jwks(public_key):
        claims = validate_oidc_jwt(token, jwks_url="https://issuer.test/jwks", issuer="https://issuer.test", audience=None)

    assert claims["sub"] == "user-1"
