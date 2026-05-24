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


# ---------------------------------------------------------------------------
# S3 multipart state helpers (DB-backed, safe under horizontal scale)
# ---------------------------------------------------------------------------

async def init_s3_multipart(
    conn: asyncpg.Connection,
    session_id: uuid.UUID,
    s3_upload_id: str,
    s3_temp_key: str,
) -> None:
    """Record the S3 multipart upload_id and temp key against an upload session."""
    await conn.execute(
        """
        UPDATE upload_sessions
        SET s3_upload_id = $2, s3_temp_key = $3, s3_parts = '[]'::jsonb
        WHERE id = $1
        """,
        session_id, s3_upload_id, s3_temp_key,
    )


async def append_s3_part(
    conn: asyncpg.Connection,
    session_id: uuid.UUID,
    part_number: int,
    etag: str,
) -> None:
    """Append a completed part record to the session's s3_parts array."""
    await conn.execute(
        """
        UPDATE upload_sessions
        SET s3_parts = s3_parts || jsonb_build_object('PartNumber', $2, 'ETag', $3)::jsonb
        WHERE id = $1
        """,
        session_id, part_number, etag,
    )


async def get_s3_multipart_state(
    conn: asyncpg.Connection,
    session_id: uuid.UUID,
) -> Optional[Dict[str, Any]]:
    """Return {'upload_id': str, 'temp_key': str, 'parts': list} or None."""
    row = await conn.fetchrow(
        "SELECT s3_upload_id, s3_temp_key, s3_parts FROM upload_sessions WHERE id = $1",
        session_id,
    )
    if not row or not row["s3_upload_id"]:
        return None
    import json as _json
    parts_raw = row["s3_parts"]
    parts = _json.loads(parts_raw) if isinstance(parts_raw, (str, bytes)) else (parts_raw or [])
    return {
        "upload_id": row["s3_upload_id"],
        "temp_key": row["s3_temp_key"],
        "parts": parts,
    }
