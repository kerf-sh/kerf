import uuid
from typing import Dict, Any

import asyncpg


async def toggle_like(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> Dict[str, Any]:
    """Toggle a like on a project. Returns {liked_by_me, likes_count}."""
    # Check current state
    existing = await conn.fetchval(
        "SELECT 1 FROM workshop_likes WHERE user_id = $1 AND project_id = $2",
        user_id,
        project_id,
    )

    if existing:
        await conn.execute(
            "DELETE FROM workshop_likes WHERE user_id = $1 AND project_id = $2",
            user_id,
            project_id,
        )
        liked = False
    else:
        await conn.execute(
            "INSERT INTO workshop_likes (user_id, project_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            user_id,
            project_id,
        )
        liked = True

    count = await conn.fetchval(
        "SELECT COUNT(*) FROM workshop_likes WHERE project_id = $1",
        project_id,
    )

    return {"liked_by_me": liked, "likes_count": int(count or 0)}
