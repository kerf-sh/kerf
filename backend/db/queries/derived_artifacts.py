import uuid
from datetime import datetime
from typing import Optional, Dict, Any

import asyncpg


async def create_derived_artifact(
    conn: asyncpg.Connection,
    source_file_id: uuid.UUID,
    content_sha256: str,
    derived_kind: str,
    payload: bytes,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO derived_artifacts (source_file_id, content_sha256, derived_kind, payload, payload_size_bytes)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        source_file_id,
        content_sha256,
        derived_kind,
        payload,
        len(payload),
    )
    return dict(row)


async def get_derived_artifact(
    conn: asyncpg.Connection,
    source_file_id: uuid.UUID,
    content_sha256: str,
    derived_kind: str,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE derived_artifacts
        SET last_accessed_at = now()
        WHERE source_file_id = $1 AND content_sha256 = $2 AND derived_kind = $3
        RETURNING *
        """,
        source_file_id,
        content_sha256,
        derived_kind,
    )
    return dict(row) if row else None


async def touch_derived_artifact(
    conn: asyncpg.Connection,
    artifact_id: uuid.UUID,
) -> bool:
    result = await conn.execute(
        "UPDATE derived_artifacts SET last_accessed_at = now() WHERE id = $1",
        artifact_id,
    )
    return result == "UPDATE 1"


async def delete_derived_artifact(
    conn: asyncpg.Connection,
    artifact_id: uuid.UUID,
) -> bool:
    result = await conn.execute(
        "DELETE FROM derived_artifacts WHERE id = $1",
        artifact_id,
    )
    return result == "DELETE 1"


async def list_derived_artifacts(
    conn: asyncpg.Connection,
    source_file_id: Optional[uuid.UUID] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Dict[str, Any]]:
    query = "SELECT * FROM derived_artifacts"
    params = []
    param_idx = 1

    if source_file_id:
        query += f" WHERE source_file_id = ${param_idx}"
        params.append(source_file_id)
        param_idx += 1

    query += f" ORDER BY last_accessed_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
    params.extend([limit, offset])

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]
