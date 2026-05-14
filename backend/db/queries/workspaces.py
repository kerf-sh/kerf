import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import asyncpg


async def create_workspace(
    conn: asyncpg.Connection,
    slug: str,
    name: str,
    created_by: uuid.UUID,
    avatar_storage_key: Optional[str] = None,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO workspaces (slug, name, created_by, avatar_storage_key)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        slug,
        name,
        created_by,
        avatar_storage_key,
    )
    return dict(row)


async def get_workspace(conn: asyncpg.Connection, workspace_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM workspaces WHERE id = $1",
        workspace_id,
    )
    return dict(row) if row else None


async def get_workspace_by_slug(conn: asyncpg.Connection, slug: str) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM workspaces WHERE slug = $1",
        slug,
    )
    return dict(row) if row else None


async def update_workspace(
    conn: asyncpg.Connection,
    workspace_id: uuid.UUID,
    name: Optional[str] = None,
    slug: Optional[str] = None,
    avatar_storage_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    updates = []
    params = [workspace_id]
    param_idx = 2

    if name is not None:
        updates.append(f"name = ${param_idx}")
        params.append(name)
        param_idx += 1

    if slug is not None:
        updates.append(f"slug = ${param_idx}")
        params.append(slug)
        param_idx += 1

    if avatar_storage_key is not None:
        updates.append(f"avatar_storage_key = ${param_idx}")
        params.append(avatar_storage_key)
        param_idx += 1

    if not updates:
        return await get_workspace(conn, workspace_id)

    updates.append("updated_at = now()")

    query = f"""
        UPDATE workspaces
        SET {', '.join(updates)}
        WHERE id = $1
        RETURNING *
    """

    row = await conn.fetchrow(query, *params)
    return dict(row) if row else None


async def delete_workspace(conn: asyncpg.Connection, workspace_id: uuid.UUID) -> bool:
    result = await conn.execute(
        "DELETE FROM workspaces WHERE id = $1",
        workspace_id,
    )
    return result == "DELETE 1"


async def list_workspace_members(
    conn: asyncpg.Connection,
    workspace_id: uuid.UUID,
) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT wm.*, u.email, u.name, u.avatar_url
        FROM workspace_members wm
        JOIN users u ON wm.user_id = u.id
        WHERE wm.workspace_id = $1
        ORDER BY wm.created_at ASC
        """,
        workspace_id,
    )
    return [dict(row) for row in rows]


async def add_workspace_member(
    conn: asyncpg.Connection,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO workspace_members (workspace_id, user_id, role)
        VALUES ($1, $2, $3)
        ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = EXCLUDED.role
        RETURNING *
        """,
        workspace_id,
        user_id,
        role,
    )
    return dict(row)


async def remove_workspace_member(
    conn: asyncpg.Connection,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    result = await conn.execute(
        "DELETE FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id,
        user_id,
    )
    return result == "DELETE 1"


async def get_workspace_member(
    conn: asyncpg.Connection,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id,
        user_id,
    )
    return dict(row) if row else None


async def create_workspace_invite(
    conn: asyncpg.Connection,
    workspace_id: uuid.UUID,
    email: str,
    role: str,
    token: str,
    created_by: uuid.UUID,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO workspace_invites (workspace_id, email, role, token, created_by)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        workspace_id,
        email,
        role,
        token,
        created_by,
    )
    return dict(row)


async def get_workspace_invite_by_token(
    conn: asyncpg.Connection,
    token: str,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM workspace_invites WHERE token = $1",
        token,
    )
    return dict(row) if row else None


async def delete_workspace_invite(
    conn: asyncpg.Connection,
    invite_id: uuid.UUID,
) -> bool:
    result = await conn.execute(
        "DELETE FROM workspace_invites WHERE id = $1",
        invite_id,
    )
    return result == "DELETE 1"
