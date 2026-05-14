import uuid
from datetime import datetime
from typing import Optional, Dict, Any

import asyncpg


async def create_fem_job(
    conn: asyncpg.Connection,
    file_id: uuid.UUID,
    project_id: uuid.UUID,
    input_spec: Dict[str, Any],
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO fem_jobs (file_id, project_id, input_spec)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        file_id,
        project_id,
        input_spec,
    )
    return dict(row)


async def get_fem_job(conn: asyncpg.Connection, job_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM fem_jobs WHERE id = $1",
        job_id,
    )
    return dict(row) if row else None


async def claim_fem_job(
    conn: asyncpg.Connection,
    timeout_seconds: int = 30,
) -> Optional[Dict[str, Any]]:
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT * FROM fem_jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """,
        )
        if not row:
            return None

        result = await conn.execute(
            "UPDATE fem_jobs SET status = 'running', started_at = now() WHERE id = $1",
            row["id"],
        )
        if result == "UPDATE 1":
            return dict(row)
        return None


async def complete_fem_job(
    conn: asyncpg.Connection,
    job_id: uuid.UUID,
    result_json: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE fem_jobs
        SET status = 'done', result_json = $2, finished_at = now()
        WHERE id = $1
        RETURNING *
        """,
        job_id,
        result_json,
    )
    return dict(row) if row else None


async def fail_fem_job(
    conn: asyncpg.Connection,
    job_id: uuid.UUID,
    error: str,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE fem_jobs
        SET status = 'error', error = $2, finished_at = now()
        WHERE id = $1
        RETURNING *
        """,
        job_id,
        error,
    )
    return dict(row) if row else None


async def create_sim_job(
    conn: asyncpg.Connection,
    file_id: uuid.UUID,
    project_id: uuid.UUID,
    input_spec: Dict[str, Any],
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO sim_jobs (file_id, project_id, input_spec)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        file_id,
        project_id,
        input_spec,
    )
    return dict(row)


async def get_sim_job(conn: asyncpg.Connection, job_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM sim_jobs WHERE id = $1",
        job_id,
    )
    return dict(row) if row else None


async def claim_sim_job(
    conn: asyncpg.Connection,
    timeout_seconds: int = 30,
) -> Optional[Dict[str, Any]]:
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT * FROM sim_jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """,
        )
        if not row:
            return None

        result = await conn.execute(
            "UPDATE sim_jobs SET status = 'running', started_at = now() WHERE id = $1",
            row["id"],
        )
        if result == "UPDATE 1":
            return dict(row)
        return None


async def complete_sim_job(
    conn: asyncpg.Connection,
    job_id: uuid.UUID,
    result_json: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE sim_jobs
        SET status = 'done', result_json = $2, finished_at = now()
        WHERE id = $1
        RETURNING *
        """,
        job_id,
        result_json,
    )
    return dict(row) if row else None


async def fail_sim_job(
    conn: asyncpg.Connection,
    job_id: uuid.UUID,
    error: str,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE sim_jobs
        SET status = 'error', error = $2, finished_at = now()
        WHERE id = $1
        RETURNING *
        """,
        job_id,
        error,
    )
    return dict(row) if row else None


async def create_step_tessellation_job(
    conn: asyncpg.Connection,
    file_id: uuid.UUID,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO step_tessellation_jobs (file_id)
        VALUES ($1)
        ON CONFLICT (file_id) DO UPDATE SET status = 'queued'
        RETURNING *
        """,
        file_id,
    )
    return dict(row)


async def get_step_tessellation_job(
    conn: asyncpg.Connection,
    job_id: uuid.UUID,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM step_tessellation_jobs WHERE id = $1",
        job_id,
    )
    return dict(row) if row else None


async def complete_step_tessellation_job(
    conn: asyncpg.Connection,
    job_id: uuid.UUID,
    mesh_storage_key: str,
) -> Optional[Dict[str, Any]]:
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            UPDATE step_tessellation_jobs
            SET status = 'done', mesh_storage_key = $2, finished_at = now()
            WHERE id = $1
            RETURNING *
            """,
            job_id,
            mesh_storage_key,
        )
        if not row:
            return None

        await conn.execute(
            "UPDATE files SET mesh_storage_key = $2 WHERE id = $1",
            row["file_id"],
            mesh_storage_key,
        )
        return dict(row)


async def fail_step_tessellation_job(
    conn: asyncpg.Connection,
    job_id: uuid.UUID,
    error: str,
) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        """
        UPDATE step_tessellation_jobs
        SET status = 'error', error = $2, finished_at = now()
        WHERE id = $1
        RETURNING *
        """,
        job_id,
        error,
    )
    return dict(row) if row else None
