from typing import Optional


async def list_credentials(conn) -> list[dict]:
    rows = await conn.fetch(
        """
        select name, enabled, rate_limit_per_minute, last_used_at, updated_at,
               (length(secret_encrypted) > 0) as has_secret
        from distributor_credentials
        order by name
        """
    )
    return [dict(row) for row in rows]


async def get_credential_by_name(conn, name: str) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        select name, enabled, rate_limit_per_minute, last_used_at, updated_at,
               (length(secret_encrypted) > 0) as has_secret
        from distributor_credentials
        where name = $1
        """,
        name,
    )
    return dict(row) if row else None


async def upsert_credential(
    conn, name: str, enabled: bool, secret_encrypted: bytes, rate_limit_per_minute: int
) -> dict:
    row = await conn.fetchrow(
        """
        insert into distributor_credentials (name, enabled, secret_encrypted, rate_limit_per_minute)
        values ($1, $2, $3, $4)
        on conflict (name) do update set
            enabled = excluded.enabled,
            secret_encrypted = excluded.secret_encrypted,
            rate_limit_per_minute = excluded.rate_limit_per_minute,
            updated_at = now()
        returning updated_at, last_used_at
        """,
        name,
        enabled,
        secret_encrypted,
        rate_limit_per_minute,
    )
    return dict(row) if row else {}


async def delete_credential(conn, name: str) -> None:
    await conn.execute("delete from distributor_credentials where name = $1", name)
