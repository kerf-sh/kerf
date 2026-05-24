import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import asyncpg


async def create_usage_event(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    kind: str,
    project_id: Optional[uuid.UUID] = None,
    model: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    bytes_delta: int = 0,
    usd_cost: float = 0.0,
    payer: str = "kerf_paid",
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO usage_events
        (user_id, project_id, kind, model, input_tokens, output_tokens, bytes_delta, usd_cost, payer)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING *
        """,
        user_id,
        project_id,
        kind,
        model,
        input_tokens,
        output_tokens,
        bytes_delta,
        usd_cost,
        payer,
    )
    return dict(row)


async def record_storage(
    conn: asyncpg.Connection,
    user_id: str,
    project_id: str,
    bytes_delta: int,
) -> Dict[str, Any]:
    """Emit a kind='storage' usage_event for a file upload or deletion.

    Parameters
    ----------
    conn:
        An open asyncpg connection (typically acquired from a pool).
    user_id:
        UUID string of the authenticated user who triggered the storage change.
    project_id:
        UUID string of the project that owns the uploaded/deleted file.
    bytes_delta:
        Signed byte count: positive for uploads, negative for deletions.
        Zero values are accepted but produce a no-op row (bytes_delta=0).

    Returns
    -------
    dict — the inserted usage_events row.
    """
    return await create_usage_event(
        conn,
        user_id=uuid.UUID(user_id),
        kind="storage",
        project_id=uuid.UUID(project_id),
        bytes_delta=bytes_delta,
    )


async def list_usage_events(
    conn: asyncpg.Connection,
    user_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    kind: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    conditions = []
    params = []
    param_idx = 1

    if user_id:
        conditions.append(f"user_id = ${param_idx}")
        params.append(user_id)
        param_idx += 1

    if project_id:
        conditions.append(f"project_id = ${param_idx}")
        params.append(project_id)
        param_idx += 1

    if kind:
        conditions.append(f"kind = ${param_idx}")
        params.append(kind)
        param_idx += 1

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT * FROM usage_events
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([limit, offset])

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]
