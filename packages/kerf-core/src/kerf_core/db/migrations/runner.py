#!/usr/bin/env python3
"""Idempotent SQL migration runner.

Applied migrations are recorded in `schema_migrations`; each run executes
only files not yet recorded (each in its own transaction, then stamped).
Redeploys are safe — an already-applied migration is never re-run.

Pre-existing databases (migrated before this ledger existed) are
back-stamped: if `schema_migrations` is empty but core tables already
exist, every on-disk migration is recorded as applied without re-running
it, so the first idempotent run doesn't choke on "already exists".
"""
import asyncio
import sys
from pathlib import Path

import asyncpg

_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
)
"""


async def run_migrations(database_url: str):
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(_LEDGER_DDL)
        applied = {
            r["filename"]
            for r in await conn.fetch("SELECT filename FROM schema_migrations")
        }

        migrations_dir = Path(__file__).parent
        migration_files = sorted(migrations_dir.glob("*.sql"))

        # Back-stamp legacy DBs migrated before this ledger existed: if the
        # ledger is empty but the schema is clearly already populated,
        # record every file as applied instead of re-running it.
        if not applied:
            already_built = await conn.fetchval(
                "SELECT to_regclass('public.projects') IS NOT NULL"
            )
            if already_built:
                for migration_file in migration_files:
                    await conn.execute(
                        "INSERT INTO schema_migrations (filename) VALUES ($1) "
                        "ON CONFLICT DO NOTHING",
                        migration_file.name,
                    )
                print(
                    f"Existing schema detected — back-stamped "
                    f"{len(migration_files)} migrations as applied."
                )
                return

        ran = 0
        for migration_file in migration_files:
            name = migration_file.name
            if name in applied:
                print(f"  • {name} (already applied — skip)")
                continue
            print(f"Running migration: {name}")
            sql = migration_file.read_text()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)", name
                )
            print(f"  ✓ {name}")
            ran += 1

        print(f"\nMigrations up to date ({ran} applied this run).")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m kerf_core.db.migrations.runner <database_url>")
        sys.exit(1)
    asyncio.run(run_migrations(sys.argv[1]))
