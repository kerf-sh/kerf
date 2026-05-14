import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import asyncpg

_UNSET = object()


async def create_file(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    name: str,
    kind: str = "file",
    parent_id: Optional[uuid.UUID] = None,
    content: str = "",
    storage_key: Optional[str] = None,
    mime_type: Optional[str] = None,
    size: Optional[int] = None,
    extension: Optional[str] = None,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO files (project_id, parent_id, name, kind, content, storage_key, mime_type, size, extension)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING *
        """,
        project_id,
        parent_id,
        name,
        kind,
        content,
        storage_key,
        mime_type,
        size,
        extension,
    )
    return dict(row)


async def get_file(conn: asyncpg.Connection, file_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM files WHERE id = $1 AND deleted_at IS NULL",
        file_id,
    )
    return dict(row) if row else None


async def list_files(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    parent_id: Optional[uuid.UUID] = None,
    include_deleted: bool = False,
) -> List[Dict[str, Any]]:
    if include_deleted:
        query = "SELECT * FROM files WHERE project_id = $1"
        params = [project_id]
        if parent_id is not None:
            query += " AND parent_id = $2"
            params.append(parent_id)
        else:
            query += " AND parent_id IS NULL"
    else:
        query = "SELECT * FROM files WHERE project_id = $1 AND deleted_at IS NULL"
        params = [project_id]
        if parent_id is not None:
            query += " AND parent_id = $2"
            params.append(parent_id)
        else:
            query += " AND parent_id IS NULL"

    query += " ORDER BY name ASC"
    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def update_file(
    conn: asyncpg.Connection,
    file_id: uuid.UUID,
    name: Optional[str] = None,
    content: Optional[str] = None,
    parent_id: Any = _UNSET,
    storage_key: Optional[str] = None,
    mesh_storage_key: Optional[str] = None,
    deleted_at: Optional[datetime] = None,
    extension: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    updates = []
    params = [file_id]
    param_idx = 2

    if name is not None:
        updates.append(f"name = ${param_idx}")
        params.append(name)
        param_idx += 1

    if content is not None:
        updates.append(f"content = ${param_idx}")
        params.append(content)
        param_idx += 1

    if parent_id is not _UNSET:
        updates.append(f"parent_id = ${param_idx}")
        params.append(parent_id)
        param_idx += 1

    if storage_key is not None:
        updates.append(f"storage_key = ${param_idx}")
        params.append(storage_key)
        param_idx += 1

    if mesh_storage_key is not None:
        updates.append(f"mesh_storage_key = ${param_idx}")
        params.append(mesh_storage_key)
        param_idx += 1

    if deleted_at is not None:
        updates.append(f"deleted_at = ${param_idx}")
        params.append(deleted_at)
        param_idx += 1

    if extension is not None:
        updates.append(f"extension = ${param_idx}")
        params.append(extension)
        param_idx += 1

    if not updates:
        return await get_file(conn, file_id)

    updates.append("updated_at = now()")

    query = f"""
        UPDATE files
        SET {', '.join(updates)}
        WHERE id = $1 AND deleted_at IS NULL
        RETURNING *
    """

    row = await conn.fetchrow(query, *params)
    return dict(row) if row else None


async def delete_file(
    conn: asyncpg.Connection,
    file_id: uuid.UUID,
    soft: bool = True,
) -> bool:
    if soft:
        result = await conn.execute(
            "UPDATE files SET deleted_at = now(), updated_at = now() WHERE id = $1 AND deleted_at IS NULL",
            file_id,
        )
        return result == "UPDATE 1"
    else:
        result = await conn.execute(
            "DELETE FROM files WHERE id = $1",
            file_id,
        )
        return result == "DELETE 1"


async def get_file_revisions(
    conn: asyncpg.Connection,
    file_id: uuid.UUID,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT * FROM file_revisions
        WHERE file_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        file_id,
        limit,
    )
    return [dict(row) for row in rows]


async def create_file_revision(
    conn: asyncpg.Connection,
    file_id: uuid.UUID,
    content: str,
    source: str,
    user_id: Optional[uuid.UUID] = None,
    content_sha256: Optional[str] = None,
    kind: str = "base",
    content_gz: Optional[bytes] = None,
    parent_revision_id: Optional[uuid.UUID] = None,
    content_preview: Optional[str] = None,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO file_revisions
        (file_id, content, source, user_id, content_sha256, kind, content_gz, parent_revision_id, content_preview)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING *
        """,
        file_id,
        content,
        source,
        user_id,
        content_sha256,
        kind,
        content_gz,
        parent_revision_id,
        content_preview,
    )
    return dict(row)
