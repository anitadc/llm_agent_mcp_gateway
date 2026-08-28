import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key, hash_api_key, verify_api_key_hash
from app.db.schema_cleanup import drop_stale_updatedat_triggers


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


@pytest.mark.asyncio
async def test_drop_stale_updatedat_triggers_removes_legacy_trigger(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION legacy_users_updatedAt_trigger() RETURNS trigger AS $$
            BEGIN
                NEW."updatedAt" = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    await db_session.execute(
        text(
            "CREATE TRIGGER legacy_users_updatedAt_trigger BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION legacy_users_updatedAt_trigger();"
        )
    )
    await db_session.commit()

    await drop_stale_updatedat_triggers(db_session)
    await db_session.commit()

    result = await db_session.execute(
        text("SELECT COUNT(*) FROM pg_trigger WHERE tgname = 'legacy_users_updatedAt_trigger'")
    )
    assert result.scalar_one() == 0
