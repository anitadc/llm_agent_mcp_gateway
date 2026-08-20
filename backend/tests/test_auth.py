from app.core.security import generate_api_key, hash_api_key, verify_api_key_hash


def test_hash_api_key_is_deterministic() -> None:
    raw_key = "gw_sometoken123"
    pepper = "pepper"
    assert hash_api_key(raw_key, pepper) == hash_api_key(raw_key, pepper)


def test_hash_api_key_differs_by_pepper() -> None:
    raw_key = "gw_sometoken123"
    assert hash_api_key(raw_key, "pepper-a") != hash_api_key(raw_key, "pepper-b")


def test_verify_api_key_hash_roundtrip() -> None:
    raw_key, prefix, hashed_key = generate_api_key("gw", "pepper")
    assert raw_key.startswith("gw_")
    assert prefix == raw_key[:12]
    assert verify_api_key_hash(raw_key, "pepper", hashed_key)
    assert not verify_api_key_hash("gw_wrong-key", "pepper", hashed_key)


def test_generate_api_key_is_unique() -> None:
    first, _, _ = generate_api_key("gw", "pepper")
    second, _, _ = generate_api_key("gw", "pepper")
    assert first != second
