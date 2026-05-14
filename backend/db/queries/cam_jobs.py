import uuid
from typing import Optional, Dict, Any

import asyncpg


async def create_cam_job(
    conn: asyncpg.Connection,
    file_id: uuid.UUID,
    project_id: uuid.UUID,
    input_spec: Dict[str, Any],
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO cam_jobs (file_id, project_id, input_spec)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        file_id,
        project_id,
        input_spec,
    )
    return dict(row)


async def get_cam_job(conn: asyncpg.Connection, job_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM cam_jobs WHERE id = $1",
        job_id,
    )
    return dict(row) if row else None


async def claim_cam_job(conn: asyncpg.Connection) -> Optional[Dict[str, Any]]:
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT * FROM cam_jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """,
        )
        if not row:
            return None

        result = await conn.execute(
            "UPDATE cam_jobs SET status = 'running', started_at = now() WHERE id = $1",
            row["id"],
        )
        if result == "UPDATE 1":
            return dict(row)
        return None


async def complete_cam_job(
    conn: asyncpg.Connection,
    job_id: uuid.UUID,
    result_json: Dict[str, Any],
    output_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE cam_jobs
        SET status = 'done', result_json = $2, output_key = $3, finished_at = now()
        WHERE id = $1
        RETURNING *
        """,
        job_id,
        result_json,
        output_key,
    )
    return dict(row) if row else None


async def fail_cam_job(
    conn: asyncpg.Connection,
    job_id: uuid.UUID,
    error: str,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE cam_jobs
        SET status = 'error', error = $2, finished_at = now()
        WHERE id = $1
        RETURNING *
        """,
        job_id,
        error,
    )
    return dict(row) if row else None
