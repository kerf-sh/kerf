import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import asyncpg


async def create_project(
    conn: asyncpg.Connection,
    workspace_id: uuid.UUID,
    name: str,
    description: str = "",
    visibility: str = "private",
    tags: Optional[List[str]] = None,
    created_by: Optional[uuid.UUID] = None,
) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        INSERT INTO projects (workspace_id, name, description, visibility, tags, created_by)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
        """,
        workspace_id,
        name,
        description,
        visibility,
        tags or [],
        created_by,
    )
    return dict(row)


async def get_project(conn: asyncpg.Connection, project_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM projects WHERE id = $1",
        project_id,
    )
    return dict(row) if row else None


async def list_projects(
    conn: asyncpg.Connection,
    workspace_id: uuid.UUID,
    tags: Optional[List[str]] = None,
    visibility: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    conditions = ["workspace_id = $1"]
    params = [workspace_id]
    param_idx = 2

    if tags:
        for tag in tags:
            conditions.append(f"${param_idx} = ANY(tags)")
            params.append(tag)
            param_idx += 1

    if visibility:
        conditions.append(f"visibility = ${param_idx}")
        params.append(visibility)
        param_idx += 1

    query = f"""
        SELECT * FROM projects
        WHERE {' AND '.join(conditions)}
        ORDER BY updated_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    params.extend([limit, offset])

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def update_project(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    name: Optional[str] = None,
    description: Optional[str] = None,
    visibility: Optional[str] = None,
    tags: Optional[List[str]] = None,
    thumbnail_storage_key: Optional[str] = None,
    readme: Optional[str] = None,
    cover_storage_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    updates = []
    params = [project_id]
    param_idx = 2

    if name is not None:
        updates.append(f"name = ${param_idx}")
        params.append(name)
        param_idx += 1

    if description is not None:
        updates.append(f"description = ${param_idx}")
        params.append(description)
        param_idx += 1

    if visibility is not None:
        updates.append(f"visibility = ${param_idx}")
        params.append(visibility)
        param_idx += 1

    if tags is not None:
        updates.append(f"tags = ${param_idx}")
        params.append(tags)
        param_idx += 1

    if thumbnail_storage_key is not None:
        updates.append(f"thumbnail_storage_key = ${param_idx}")
        params.append(thumbnail_storage_key)
        param_idx += 1
        updates.append("thumbnail_updated_at = now()")

    if readme is not None:
        updates.append(f"readme = ${param_idx}")
        params.append(readme)
        param_idx += 1
        updates.append("readme_generated_at = now()")

    if cover_storage_key is not None:
        updates.append(f"cover_storage_key = ${param_idx}")
        params.append(cover_storage_key)
        param_idx += 1
        updates.append("cover_generated_at = now()")

    if not updates:
        return await get_project(conn, project_id)

    updates.append("updated_at = now()")

    query = f"""
        UPDATE projects
        SET {', '.join(updates)}
        WHERE id = $1
        RETURNING *
    """

    row = await conn.fetchrow(query, *params)
    return dict(row) if row else None


async def delete_project(conn: asyncpg.Connection, project_id: uuid.UUID) -> bool:
    result = await conn.execute(
        "DELETE FROM projects WHERE id = $1",
        project_id,
    )
    return result == "DELETE 1"


async def list_public_projects(
    conn: asyncpg.Connection,
    tags: Optional[List[str]] = None,
    sort: str = "newest",
    limit: int = 20,
    offset: int = 0,
    viewer_user_id: Optional[uuid.UUID] = None,
) -> List[Dict[str, Any]]:
    """List public projects for the Workshop gallery.

    Returns rows enriched with:
      - workspace_slug, workspace_name (from workspaces table)
      - author_name (from users table via workspace.created_by)
      - likes_count
      - liked_by_me (always False when viewer_user_id is None)
    """
    conditions = ["p.visibility = 'public'"]
    params: List[Any] = []
    param_idx = 1

    if tags:
        for tag in tags:
            conditions.append(f"${param_idx} = ANY(p.tags)")
            params.append(tag)
            param_idx += 1

    where_clause = "WHERE " + " AND ".join(conditions)

    if sort == "popular":
        order_clause = "ORDER BY likes_count DESC, p.updated_at DESC"
    else:
        order_clause = "ORDER BY p.updated_at DESC"

    # viewer_user_id param placeholders
    if viewer_user_id is not None:
        liked_expr = f"EXISTS(SELECT 1 FROM workshop_likes wl WHERE wl.project_id = p.id AND wl.user_id = ${param_idx})"
        params.append(viewer_user_id)
        param_idx += 1
    else:
        liked_expr = "FALSE"

    limit_placeholder = f"${param_idx}"
    offset_placeholder = f"${param_idx + 1}"
    params.extend([limit, offset])

    query = f"""
        SELECT
            p.*,
            w.slug  AS workspace_slug,
            w.name  AS workspace_name,
            u.name  AS author_name,
            COALESCE(lc.likes_count, 0) AS likes_count,
            COALESCE(fk.forks_count, 0) AS forks_count,
            {liked_expr} AS liked_by_me
        FROM projects p
        JOIN workspaces w ON w.id = p.workspace_id
        JOIN users u ON u.id = w.created_by
        LEFT JOIN (
            SELECT project_id, COUNT(*) AS likes_count
            FROM workshop_likes
            GROUP BY project_id
        ) lc ON lc.project_id = p.id
        LEFT JOIN (
            SELECT forked_from_project_id AS project_id, COUNT(*) AS forks_count
            FROM projects
            WHERE forked_from_project_id IS NOT NULL
            GROUP BY forked_from_project_id
        ) fk ON fk.project_id = p.id
        {where_clause}
        {order_clause}
        LIMIT {limit_placeholder} OFFSET {offset_placeholder}
    """

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]


async def get_public_project(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    viewer_user_id: Optional[uuid.UUID] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch a single public project with workspace + author + like data."""
    if viewer_user_id is not None:
        liked_expr = "EXISTS(SELECT 1 FROM workshop_likes wl WHERE wl.project_id = p.id AND wl.user_id = $2)"
        row = await conn.fetchrow(
            f"""
            SELECT
                p.*,
                w.slug  AS workspace_slug,
                w.name  AS workspace_name,
                u.name  AS author_name,
                COALESCE(lc.likes_count, 0) AS likes_count,
                COALESCE(fk.forks_count, 0) AS forks_count,
                {liked_expr} AS liked_by_me
            FROM projects p
            JOIN workspaces w ON w.id = p.workspace_id
            JOIN users u ON u.id = w.created_by
            LEFT JOIN (
                SELECT project_id, COUNT(*) AS likes_count
                FROM workshop_likes
                GROUP BY project_id
            ) lc ON lc.project_id = p.id
            LEFT JOIN (
                SELECT forked_from_project_id AS project_id, COUNT(*) AS forks_count
                FROM projects
                WHERE forked_from_project_id IS NOT NULL
                GROUP BY forked_from_project_id
            ) fk ON fk.project_id = p.id
            WHERE p.id = $1 AND p.visibility = 'public'
            """,
            project_id,
            viewer_user_id,
        )
    else:
        row = await conn.fetchrow(
            """
            SELECT
                p.*,
                w.slug  AS workspace_slug,
                w.name  AS workspace_name,
                u.name  AS author_name,
                COALESCE(lc.likes_count, 0) AS likes_count,
                COALESCE(fk.forks_count, 0) AS forks_count,
                FALSE AS liked_by_me
            FROM projects p
            JOIN workspaces w ON w.id = p.workspace_id
            JOIN users u ON u.id = w.created_by
            LEFT JOIN (
                SELECT project_id, COUNT(*) AS likes_count
                FROM workshop_likes
                GROUP BY project_id
            ) lc ON lc.project_id = p.id
            LEFT JOIN (
                SELECT forked_from_project_id AS project_id, COUNT(*) AS forks_count
                FROM projects
                WHERE forked_from_project_id IS NOT NULL
                GROUP BY forked_from_project_id
            ) fk ON fk.project_id = p.id
            WHERE p.id = $1 AND p.visibility = 'public'
            """,
            project_id,
        )
    return dict(row) if row else None
