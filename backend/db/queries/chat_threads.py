import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import asyncpg


async def create_thread(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    title: str = "",
    file_id: Optional[uuid.UUID] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO chat_threads (project_id, file_id, title, model)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        project_id,
        file_id,
        title,
        model,
    )
    return dict(row)


async def get_thread(
    conn: asyncpg.Connection,
    thread_id: uuid.UUID,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM chat_threads WHERE id = $1",
        thread_id,
    )
    return dict(row) if row else None


async def list_threads(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    file_id: Optional[uuid.UUID] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    query = """
        SELECT * FROM chat_threads
        WHERE project_id = $1
    """
    params = [project_id]
    param_idx = 2

    if file_id is not None:
        query += f" AND file_id = ${param_idx}"
        params.append(file_id)
        param_idx += 1

    query += f" ORDER BY last_message_at DESC NULLS LAST, created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
    params.extend([limit, offset])

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def update_thread(
    conn: asyncpg.Connection,
    thread_id: uuid.UUID,
    title: Optional[str] = None,
    file_id: Optional[uuid.UUID] = None,
    is_starred: Optional[bool] = None,
    last_message_at: Optional[datetime] = None,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    updates = []
    params = [thread_id]
    param_idx = 2

    if title is not None:
        updates.append(f"title = ${param_idx}")
        params.append(title)
        param_idx += 1

    if file_id is not None:
        updates.append(f"file_id = ${param_idx}")
        params.append(file_id)
        param_idx += 1

    if is_starred is not None:
        updates.append(f"is_starred = ${param_idx}")
        params.append(is_starred)
        param_idx += 1

    if last_message_at is not None:
        updates.append(f"last_message_at = ${param_idx}")
        params.append(last_message_at)
        param_idx += 1

    if model is not None:
        updates.append(f"model = ${param_idx}")
        params.append(model)
        param_idx += 1

    if not updates:
        return await get_thread(conn, thread_id)

    updates.append("updated_at = now()")

    query = f"""
        UPDATE chat_threads
        SET {', '.join(updates)}
        WHERE id = $1
        RETURNING *
    """

    row = await conn.fetchrow(query, *params)
    return dict(row) if row else None


async def delete_thread(conn: asyncpg.Connection, thread_id: uuid.UUID) -> bool:
    result = await conn.execute(
        "DELETE FROM chat_threads WHERE id = $1",
        thread_id,
    )
    return result == "DELETE 1"


async def create_message(
    conn: asyncpg.Connection,
    thread_id: uuid.UUID,
    role: str,
    content: str,
    part_refs: Optional[List[Dict[str, Any]]] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    tool_call_id: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO chat_messages (thread_id, role, content, part_refs, tool_calls, tool_call_id, model)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        thread_id,
        role,
        content,
        part_refs or [],
        tool_calls or [],
        tool_call_id,
        model,
    )
    return dict(row)


async def get_messages(
    conn: asyncpg.Connection,
    thread_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT * FROM chat_messages
        WHERE thread_id = $1
        ORDER BY created_at ASC
        LIMIT $2 OFFSET $3
        """,
        thread_id,
        limit,
        offset,
    )
    return [dict(row) for row in rows]
