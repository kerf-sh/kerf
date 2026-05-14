import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import asyncpg


async def create_upload_session(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    filename: str,
    size: int,
    sha256: str,
    storage_key: str,
    mime: Optional[str] = None,
    chunk_size: int = 5242880,
    total_chunks: int = 1,
    expires_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    if expires_at is None:
        expires_at = datetime.utcnow() + timedelta(hours=24)

    row = await conn.fetchrow(
        """
        INSERT INTO upload_sessions
        (project_id, user_id, filename, size, mime, sha256, storage_key, chunk_size, total_chunks, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING *
        """,
        project_id,
        user_id,
        filename,
        size,
        mime,
        sha256,
        storage_key,
        chunk_size,
        total_chunks,
        expires_at,
    )
    return dict(row)


async def get_upload_session(
    conn: asyncpg.Connection,
    session_id: uuid.UUID,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM upload_sessions WHERE id = $1",
        session_id,
    )
    return dict(row) if row else None


async def get_upload_session_by_sha256(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    sha256: str,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        SELECT * FROM upload_sessions
        WHERE project_id = $1 AND sha256 = $2 AND complete = false AND expires_at > now()
        """,
        project_id,
        sha256,
    )
    return dict(row) if row else None


async def update_upload_session(
    conn: asyncpg.Connection,
    session_id: uuid.UUID,
    received_chunks: List[int],
    bytes_received: int,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE upload_sessions
        SET received_chunks = $2, bytes_received = $3
        WHERE id = $1
        RETURNING *
        """,
        session_id,
        received_chunks,
        bytes_received,
    )
    return dict(row) if row else None


async def complete_upload_session(
    conn: asyncpg.Connection,
    session_id: uuid.UUID,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE upload_sessions
        SET complete = true
        WHERE id = $1
        RETURNING *
        """,
        session_id,
    )
    return dict(row) if row else None


async def delete_upload_session(
    conn: asyncpg.Connection,
    session_id: uuid.UUID,
) -> bool:
    result = await conn.execute(
        "DELETE FROM upload_sessions WHERE id = $1",
        session_id,
    )
    return result == "DELETE 1"


async def cleanup_expired_upload_sessions(
    conn: asyncpg.Connection,
) -> int:
    result = await conn.execute(
        "DELETE FROM upload_sessions WHERE expires_at < now() AND complete = false"
    )
    count = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
    return count
