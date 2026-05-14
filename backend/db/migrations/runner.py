#!/usr/bin/env python3
import asyncio
import asyncpg
import sys
from pathlib import Path


async def run_migrations(database_url: str):
    conn = await asyncpg.connect(database_url)

    migrations_dir = Path(__file__).parent / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    for migration_file in migration_files:
        print(f"Running migration: {migration_file.name}")
        sql = migration_file.read_text()
        try:
            await conn.execute(sql)
            print(f"  ✓ {migration_file.name}")
        except Exception as e:
            print(f"  ✗ {migration_file.name}: {e}")
            raise

    await conn.close()
    print("\nAll migrations completed successfully!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m db.migrations <database_url>")
        print("Example: python -m db.migrations postgres://postgres:postgres@localhost:5432/kerf")
        sys.exit(1)

    database_url = sys.argv[1]
    asyncio.run(run_migrations(database_url))
