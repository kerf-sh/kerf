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
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO usage_events
        (user_id, project_id, kind, model, input_tokens, output_tokens, bytes_delta, usd_cost)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
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
    )
    return dict(row)


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
