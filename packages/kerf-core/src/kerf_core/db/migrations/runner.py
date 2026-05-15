#!/usr/bin/env python3
"""Idempotent SQL migration runner.

Applied `*.sql` files are recorded in `kerf_migrations_ledger` (a
filename-keyed table — deliberately NOT `schema_migrations`, which some
legacy/ORM tooling already owns with a different schema).

Each unseen migration is applied in its own transaction then stamped.
For databases that were already built by an earlier (non-idempotent)
run, re-applying a migration raises a duplicate-object error — that's
treated as "already applied": the error is swallowed and the file is
stamped, so genuinely-new migrations still run while old ones don't
re-execute. Real (non-duplicate) errors still abort the deploy.
"""
import asyncio
import sys
from pathlib import Path

import asyncpg

_LEDGER = "kerf_migrations_ledger"
_LEDGER_DDL = f"""
CREATE TABLE IF NOT EXISTS {_LEDGER} (
    filename    text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
)
"""

# asyncpg duplicate-object exceptions → migration already applied to a
# DB that predates this ledger; stamp it instead of failing.
_ALREADY_APPLIED = (
    asyncpg.exceptions.DuplicateColumnError,
    asyncpg.exceptions.DuplicateTableError,
    asyncpg.exceptions.DuplicateObjectError,
    asyncpg.exceptions.DuplicateFunctionError,
    asyncpg.exceptions.DuplicateSchemaError,
)


async def run_migrations(database_url: str):
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(_LEDGER_DDL)
        applied = {
            r["filename"]
            for r in await conn.fetch(f"SELECT filename FROM {_LEDGER}")
        }

        migrations_dir = Path(__file__).parent
        migration_files = sorted(migrations_dir.glob("*.sql"))

        ran = 0
        stamped = 0
        for migration_file in migration_files:
            name = migration_file.name
            if name in applied:
                continue
            sql = migration_file.read_text()
            try:
                async with conn.transaction():
                    await conn.execute(sql)
                await conn.execute(
                    f"INSERT INTO {_LEDGER} (filename) VALUES ($1) "
                    "ON CONFLICT DO NOTHING",
                    name,
                )
                print(f"  ✓ {name}")
                ran += 1
            except _ALREADY_APPLIED as exc:
                # Pre-existing schema from a legacy/non-idempotent run.
                await conn.execute(
                    f"INSERT INTO {_LEDGER} (filename) VALUES ($1) "
                    "ON CONFLICT DO NOTHING",
                    name,
                )
                print(f"  • {name} (already present — stamped: {type(exc).__name__})")
                stamped += 1

        print(
            f"\nMigrations up to date ({ran} applied, "
            f"{stamped} back-stamped this run)."
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m kerf_core.db.migrations.runner <database_url>")
        sys.exit(1)
    asyncio.run(run_migrations(sys.argv[1]))
