import hashlib
import hmac
import secrets


def generate_api_key(prefix: str, pepper: str) -> tuple[str, str, str]:
    """Returns (raw_key, prefix, hashed_key). raw_key = '{prefix}_<random>'."""
    raw_key = f"{prefix}_{secrets.token_urlsafe(32)}"
    key_prefix = raw_key[:12]
    hashed_key = hash_api_key(raw_key, pepper)
    return raw_key, key_prefix, hashed_key


def hash_api_key(raw_key: str, pepper: str) -> str:
    """HMAC-SHA256 keyed by the pepper: deterministic (so it supports an equality
    lookup by hash, unlike a salted algorithm such as argon2/bcrypt) yet irreversible
    without the pepper. Appropriate here because the input is already a 256-bit random
    token, not a low-entropy password that needs deliberate slow-hashing."""
    return hmac.new(pepper.encode(), raw_key.encode(), hashlib.sha256).hexdigest()


def verify_api_key_hash(raw_key: str, pepper: str, hashed_key: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key, pepper), hashed_key)
