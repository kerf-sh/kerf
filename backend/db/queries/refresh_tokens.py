import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import asyncpg


async def create_refresh_token(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    token_hash: str,
    expires_at: datetime,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        user_id,
        token_hash,
        expires_at,
    )
    return dict(row)


async def get_refresh_token(
    conn: asyncpg.Connection,
    token_hash: str,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT * FROM refresh_tokens
        WHERE token_hash = $1
          AND revoked_at IS NULL
          AND expires_at > now()
        """,
        token_hash,
    )
    return dict(row) if row else None


async def revoke_refresh_token(
    conn: asyncpg.Connection,
    token_hash: str,
) -> bool:
    result = await conn.execute(
        "UPDATE refresh_tokens SET revoked_at = now() WHERE token_hash = $1",
        token_hash,
    )
    return result == "UPDATE 1"


async def revoke_all_user_refresh_tokens(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
) -> int:
    result = await conn.execute(
        "UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = $1 AND revoked_at IS NULL",
        user_id,
    )
    count = int(result.split(" ")[1]) if result.startswith("UPDATE ") else 0
    return count
