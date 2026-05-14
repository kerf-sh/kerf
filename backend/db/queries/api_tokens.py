import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import asyncpg


async def create_api_token(
    conn: asyncpg.Connection,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    token_hash: str,
    name: str,
    scopes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO api_tokens (workspace_id, user_id, token_hash, name, scopes)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        workspace_id,
        user_id,
        token_hash,
        name,
        scopes or ["workspace:member-role"],
    )
    return dict(row)


async def get_api_token(conn: asyncpg.Connection, token_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM api_tokens WHERE id = $1",
        token_id,
    )
    return dict(row) if row else None


async def get_api_token_by_hash(
    conn: asyncpg.Connection,
    token_hash: str,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE api_tokens
        SET last_used_at = now()
        WHERE token_hash = $1 AND revoked_at IS NULL
        RETURNING *
        """,
        token_hash,
    )
    return dict(row) if row else None


async def revoke_api_token(
    conn: asyncpg.Connection,
    token_id: uuid.UUID,
) -> bool:
    result = await conn.execute(
        "UPDATE api_tokens SET revoked_at = now() WHERE id = $1",
        token_id,
    )
    return result == "UPDATE 1"


async def list_api_tokens(
    conn: asyncpg.Connection,
    workspace_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    include_revoked: bool = False,
) -> List[Dict[str, Any]]:
    conditions = []
    params = []
    param_idx = 1

    if workspace_id:
        conditions.append(f"workspace_id = ${param_idx}")
        params.append(workspace_id)
        param_idx += 1

    if user_id:
        conditions.append(f"user_id = ${param_idx}")
        params.append(user_id)
        param_idx += 1

    if not include_revoked:
        conditions.append("revoked_at IS NULL")

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT * FROM api_tokens
        {where_clause}
        ORDER BY created_at DESC
    """

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]
