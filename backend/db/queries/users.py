import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import asyncpg


async def create_user(
    conn: asyncpg.Connection,
    email: str,
    name: str = "",
    password_hash: Optional[str] = None,
    google_id: Optional[str] = None,
    avatar_url: str = "",
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO users (email, name, password_hash, google_id, avatar_url)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        email,
        name,
        password_hash,
        google_id,
        avatar_url,
    )
    return dict(row)


async def get_user(conn: asyncpg.Connection, user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM users WHERE id = $1",
        user_id,
    )
    return dict(row) if row else None


async def get_user_by_email(conn: asyncpg.Connection, email: str) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM users WHERE email = $1",
        email,
    )
    return dict(row) if row else None


async def get_user_by_google_id(conn: asyncpg.Connection, google_id: str) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM users WHERE google_id = $1",
        google_id,
    )
    return dict(row) if row else None


async def update_user(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    name: Optional[str] = None,
    email: Optional[str] = None,
    password_hash: Optional[str] = None,
    avatar_url: Optional[str] = None,
    avatar_storage_key: Optional[str] = None,
    preferences: Optional[Dict[str, Any]] = None,
    is_verified_publisher: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    updates = []
    params = [user_id]
    param_idx = 2

    if name is not None:
        updates.append(f"name = ${param_idx}")
        params.append(name)
        param_idx += 1

    if email is not None:
        updates.append(f"email = ${param_idx}")
        params.append(email)
        param_idx += 1

    if password_hash is not None:
        updates.append(f"password_hash = ${param_idx}")
        params.append(password_hash)
        param_idx += 1

    if avatar_url is not None:
        updates.append(f"avatar_url = ${param_idx}")
        params.append(avatar_url)
        param_idx += 1

    if avatar_storage_key is not None:
        updates.append(f"avatar_storage_key = ${param_idx}")
        params.append(avatar_storage_key)
        param_idx += 1

    if avatar_storage_key is not None:
        updates.append(f"avatar_updated_at = now()")
        param_idx += 1

    if preferences is not None:
        updates.append(f"preferences = ${param_idx}")
        params.append(preferences)
        param_idx += 1

    if is_verified_publisher is not None:
        updates.append(f"is_verified_publisher = ${param_idx}")
        params.append(is_verified_publisher)
        param_idx += 1

    if not updates:
        return await get_user(conn, user_id)

    query = f"""
        UPDATE users
        SET {', '.join(updates)}
        WHERE id = $1
        RETURNING *
    """

    row = await conn.fetchrow(query, *params)
    return dict(row) if row else None


async def delete_user(conn: asyncpg.Connection, user_id: uuid.UUID) -> bool:
    result = await conn.execute(
        "DELETE FROM users WHERE id = $1",
        user_id,
    )
    return result == "DELETE 1"


async def list_users(conn: asyncpg.Connection, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2",
        limit,
        offset,
    )
    return [dict(row) for row in rows]
