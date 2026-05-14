import uuid
from datetime import datetime
from typing import Optional, Dict, Any

import asyncpg


async def create_share_link(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    token: str,
    role: str,
    created_by: uuid.UUID,
    expires_at: Optional[datetime] = None,
    max_uses: Optional[int] = None,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO share_links (project_id, token, role, created_by, expires_at, max_uses)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
        """,
        project_id,
        token,
        role,
        created_by,
        expires_at,
        max_uses,
    )
    return dict(row)


async def get_share_link(
    conn: asyncpg.Connection,
    link_id: uuid.UUID,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM share_links WHERE id = $1",
        link_id,
    )
    return dict(row) if row else None


async def get_share_link_by_token(
    conn: asyncpg.Connection,
    token: str,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE share_links
        SET uses = uses + 1
        WHERE token = $1
          AND revoked_at IS NULL
          AND (expires_at IS NULL OR expires_at > now())
          AND (max_uses IS NULL OR uses < max_uses)
        RETURNING *
        """,
        token,
    )
    return dict(row) if row else None


async def revoke_share_link(
    conn: asyncpg.Connection,
    link_id: uuid.UUID,
) -> bool:
    result = await conn.execute(
        "UPDATE share_links SET revoked_at = now() WHERE id = $1",
        link_id,
    )
    return result == "UPDATE 1"


async def list_share_links(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
) -> list[Dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT * FROM share_links WHERE project_id = $1 ORDER BY created_at DESC",
        project_id,
    )
    return [dict(row) for row in rows]
