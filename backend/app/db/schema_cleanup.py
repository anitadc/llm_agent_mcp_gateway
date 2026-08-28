from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def drop_stale_updatedat_triggers(db: AsyncSession) -> None:
    """Remove legacy Postgres triggers that still reference the old `updatedAt` field.

    Older DBs can retain a trigger like:
        CREATE TRIGGER ... BEFORE UPDATE ON users FOR EACH ROW
        EXECUTE FUNCTION legacy_users_updatedAt_trigger();

    that assigns to NEW."updatedAt". The current schema uses `updated_at`, so the
    trigger raises `UndefinedColumnError` during any update.
    """
    await db.execute(
        text(
            """
            DO $$
            DECLARE
                trig record;
            BEGIN
                FOR trig IN
                    SELECT tgname, tgrelid::regclass::text AS table_name
                    FROM pg_trigger
                    WHERE tgname ILIKE '%updatedat%'
                       OR tgname ILIKE '%updated_at%'
                LOOP
                    EXECUTE format('DROP TRIGGER IF EXISTS %I ON %s', trig.tgname, trig.table_name);
                END LOOP;
            END $$;
            """
        )
    )

    await db.execute(
        text(
            """
            DO $$
            DECLARE
                fn record;
            BEGIN
                FOR fn IN
                    SELECT proname, oid::regprocedure::text AS proc_name
                    FROM pg_proc
                    WHERE proname ILIKE '%updatedat%'
                       OR proname ILIKE '%updated_at%'
                LOOP
                    EXECUTE format('DROP FUNCTION IF EXISTS %s', fn.proc_name);
                END LOOP;
            END $$;
            """
        )
    )
