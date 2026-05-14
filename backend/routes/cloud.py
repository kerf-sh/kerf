import asyncio
import base64
import json
import os
import re
import secrets
import tempfile
from datetime import datetime
from typing import Optional

import asyncpg
import httpx
import pygit2
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from config import get_settings
from db.connection import get_pool_required
from dependencies import require_auth
from storage import get_storage_required
from storage.s3 import S3Storage
from storage.git_storer import S3GitStorer
from utils.encrypt import encrypt_secret, decrypt_secret

router = APIRouter()
settings = get_settings()

github_oauth_router = APIRouter()


class InitResponse(BaseModel):
    project_id: str
    default_branch: str
    head_sha: str


class ImportRequest(BaseModel):
    github_url: str
    branch: Optional[str] = None


class ConnectRequest(BaseModel):
    github_owner: str
    github_repo: str


class CreateBranchRequest(BaseModel):
    name: str
    from_sha: Optional[str] = None


class CheckoutRequest(BaseModel):
    branch: str
    force: bool = False


class CommitRequest(BaseModel):
    message: str
    branch: Optional[str] = None


class MergeRequest(BaseModel):
    from_branch: str
    into_branch: str


class PullRequest(BaseModel):
    branch: Optional[str] = None


async def require_role(request: Request, project_id: str, uid: str) -> tuple[str, str]:
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT owner_id FROM projects WHERE id = $1",
            project_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="project not found")

        if str(row["owner_id"]) == uid:
            return uid, "owner"

        member_row = await conn.fetchrow(
            "SELECT role FROM project_members WHERE project_id = $1 AND user_id = $2",
            project_id, uid,
        )
        if not member_row:
            raise HTTPException(status_code=404, detail="project not found")
        return uid, member_row["role"]


async def require_editor(request: Request, project_id: str, uid: str) -> str:
    uid, role = await require_role(request, project_id, uid)
    if role not in ("owner", "editor"):
        raise HTTPException(status_code=403, detail="editor or owner role required")
    return uid


async def project_name(ctx, project_id: str) -> str:
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name FROM projects WHERE id = $1",
            project_id,
        )
        return row["name"] if row else ""


@router.post("/projects/{pid}/git/init")
async def git_init(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    uid = await require_editor(request, pid, user_id)

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM cloud_git_repos WHERE project_id = $1",
            pid,
        )
        if existing:
            return {
                "project_id": pid,
                "default_branch": existing["default_branch"],
                "head_sha": existing.get("head_sha", ""),
            }

        await conn.execute(
            """
            INSERT INTO cloud_git_repos (project_id, default_branch, head_sha)
            VALUES ($1, 'main', '')
            """,
            pid,
        )

    return {
        "project_id": pid,
        "default_branch": "main",
        "head_sha": "",
    }


@router.post("/projects/{pid}/git/import")
async def git_import(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    uid = await require_editor(request, pid, user_id)

    body = await request.json()
    github_url = body.get("github_url", "").strip()
    if not github_url:
        raise HTTPException(status_code=400, detail="github_url is required")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM cloud_git_repos WHERE project_id = $1",
            pid,
        )
        if existing:
            raise HTTPException(status_code=409, detail="git already enabled for this project")

        default_branch = body.get("branch") or "main"

        await conn.execute(
            """
            INSERT INTO cloud_git_repos (project_id, default_branch, github_remote_url)
            VALUES ($1, $2, $3)
            """,
            pid, default_branch, github_url,
        )

    return {
        "project_id": pid,
        "default_branch": default_branch,
        "head_sha": "",
    }


@router.post("/projects/{pid}/git/connect")
async def git_connect(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    uid = await require_editor(request, pid, user_id)

    body = await request.json()
    github_owner = body.get("github_owner", "").strip()
    github_repo = body.get("github_repo", "").strip()
    if not github_owner or not github_repo:
        raise HTTPException(status_code=400, detail="github_owner and github_repo are required")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE cloud_git_repos
            SET github_owner = $2, github_repo = $3
            WHERE project_id = $1
            """,
            pid, github_owner, github_repo,
        )

    return {
        "github_owner": github_owner,
        "github_repo": github_repo,
    }


@router.get("/projects/{pid}/git/log")
async def git_log(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    await require_role(request, pid, user_id)

    branch = request.query_params.get("branch")
    limit = int(request.query_params.get("limit", 50))

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT sha, message, author_name, author_email, created_at
            FROM cloud_git_commits
            WHERE project_id = $1 AND ($2::text IS NULL OR branch = $2)
            ORDER BY created_at DESC
            LIMIT $3
            """,
            pid, branch, limit,
        )
        return [
            {
                "sha": str(row["sha"]),
                "message": row["message"],
                "author_name": row["author_name"],
                "author_email": row["author_email"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]


@router.get("/projects/{pid}/git/branches")
async def git_branches(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    await require_role(request, pid, user_id)

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT name, head_sha, is_default
            FROM cloud_git_branches
            WHERE project_id = $1
            ORDER BY name
            """,
            pid,
        )
        return [
            {
                "name": row["name"],
                "head_sha": str(row["head_sha"]) if row["head_sha"] else "",
                "is_default": row["is_default"],
            }
            for row in rows
        ]


@router.post("/projects/{pid}/git/branches")
async def git_create_branch(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    await require_editor(request, pid, user_id)

    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    from_sha = body.get("from_sha")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cloud_git_branches (project_id, name, head_sha)
            VALUES ($1, $2, $3)
            """,
            pid, name, from_sha or "",
        )

    return {
        "name": name,
        "head_sha": from_sha or "",
    }


@router.post("/projects/{pid}/git/checkout")
async def git_checkout(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    await require_editor(request, pid, user_id)

    body = await request.json()
    branch = body.get("branch", "").strip()
    if not branch:
        raise HTTPException(status_code=400, detail="branch is required")

    force = body.get("force", False)

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT head_sha FROM cloud_git_branches WHERE project_id = $1 AND name = $2",
            pid, branch,
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"branch {branch} not found")

        head_sha = str(row["head_sha"]) if row["head_sha"] else ""

    return {
        "branch": branch,
        "head_sha": head_sha,
    }


@router.post("/projects/{pid}/git/commit")
async def git_commit(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    uid = await require_editor(request, pid, user_id)

    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    branch = body.get("branch", "").strip()

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT name, email FROM users WHERE id = $1",
            uid,
        )
        if not user_row:
            raise HTTPException(status_code=400, detail="user not found")

        sha = secrets.token_hex(20)

        await conn.execute(
            """
            INSERT INTO cloud_git_commits (project_id, sha, message, author_name, author_email, branch)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            pid, sha, message, user_row["name"], user_row["email"], branch or "main",
        )

        if branch:
            await conn.execute(
                """
                UPDATE cloud_git_branches SET head_sha = $3 WHERE project_id = $1 AND name = $2
                """,
                pid, branch, sha,
            )

    return {
        "sha": sha,
        "branch": branch or "main",
    }


@router.post("/projects/{pid}/git/merge")
async def git_merge(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    uid = await require_editor(request, pid, user_id)

    body = await request.json()
    from_branch = body.get("from_branch", "").strip()
    into_branch = body.get("into_branch", "").strip()
    if not from_branch or not into_branch:
        raise HTTPException(status_code=400, detail="from_branch and into_branch are required")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        from_row = await conn.fetchrow(
            "SELECT head_sha FROM cloud_git_branches WHERE project_id = $1 AND name = $2",
            pid, from_branch,
        )
        if not from_row:
            raise HTTPException(status_code=404, detail=f"branch {from_branch} not found")

        sha = secrets.token_hex(20)

        await conn.execute(
            """
            INSERT INTO cloud_git_commits (project_id, sha, message, author_name, author_email, branch)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            pid, sha, f"Merge {from_branch} into {into_branch}", "system", "system@kerf", into_branch,
        )

        await conn.execute(
            """
            UPDATE cloud_git_branches SET head_sha = $3 WHERE project_id = $1 AND name = $2
            """,
            pid, into_branch, sha,
        )

    return {
        "sha": sha,
        "fast_forward": False,
        "into_branch": into_branch,
    }


@router.post("/projects/{pid}/git/push")
async def git_push(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    await require_editor(request, pid, user_id)

    storage_inst = get_storage_required()
    if not isinstance(storage_inst, S3Storage):
        raise HTTPException(status_code=503, detail='git push requires S3 storage backend')
    prefix = f'workspaces/{pid}/git'
    storer = S3GitStorer(storage_inst, storage_inst.bucket, prefix)
    body = await request.json() if (await request.body()) else {}
    local_dir = body.get('local_dir', '').strip()
    if not local_dir:
        raise HTTPException(status_code=400, detail='local_dir is required (path to local bare repo on this server)')
    if not os.path.isdir(local_dir):
        raise HTTPException(status_code=404, detail=f'local repo not found: {local_dir}')
    try:
        await asyncio.get_event_loop().run_in_executor(None, storer.push_from_local, local_dir)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE cloud_git_repos SET last_pushed_at = now() WHERE project_id = $1
            """,
            pid,
        )

    return {"status": "pushed", "prefix": prefix}


@router.post("/projects/{pid}/git/pull")
async def git_pull(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    await require_editor(request, pid, user_id)

    body = await request.json() if (await request.body()) else {}
    branch = body.get("branch", "").strip()

    storage_inst = get_storage_required()
    if not isinstance(storage_inst, S3Storage):
        raise HTTPException(status_code=503, detail='git pull requires S3 storage backend')
    prefix = f'workspaces/{pid}/git'
    storer = S3GitStorer(storage_inst, storage_inst.bucket, prefix)
    local_dir = body.get('local_dir', '').strip() or tempfile.mkdtemp(prefix='kerf-git-')
    try:
        await asyncio.get_event_loop().run_in_executor(None, storer.clone_to_local, local_dir)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        if not branch:
            row = await conn.fetchrow(
                "SELECT default_branch FROM cloud_git_repos WHERE project_id = $1",
                pid,
            )
            branch = row["default_branch"] if row else "main"

        await conn.execute(
            """
            UPDATE cloud_git_repos SET last_fetched_at = now() WHERE project_id = $1
            """,
            pid,
        )

    return {"status": "pulled", "local_dir": local_dir, "branch": branch}


@router.get("/projects/{pid}/git/diff/{sha}")
async def git_diff(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
    sha: Optional[str] = None,
):
    user_id = payload.get("sub")
    await require_role(request, pid, user_id)

    return f"diff for {sha}"


@router.delete("/projects/{pid}/git/repo")
async def git_delete_repo(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    user_id = payload.get("sub")
    uid, role = await require_role(request, pid, user_id)
    if role != "owner":
        raise HTTPException(status_code=403, detail="only the project owner can delete the git repo")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM cloud_git_repos WHERE project_id = $1",
            pid,
        )

    return Response(status_code=204)


@github_oauth_router.get("/github/start")
async def github_auth_start(
    request: Request,
    payload: dict = Depends(require_auth),
):
    if not settings.cloud_github_client_id or not settings.cloud_github_client_secret:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")

    user_id = payload["sub"]
    redirect_query_param = request.query_params.get("redirect", "")

    nonce = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
    state_data = {"n": nonce, "u": user_id, "r": redirect_query_param}
    state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode().rstrip("=")

    response = Response(status_code=302)
    response.headers["Location"] = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={settings.cloud_github_client_id}"
        f"&redirect_uri={settings.cloud_github_redirect_url}"
        "&scope=repo"
        f"&state={state}"
        "&response_type=code"
    )
    response.set_cookie(
        key="kerf_github_oauth_state",
        value=state,
        httponly=True,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return response


@github_oauth_router.get("/github/callback")
async def github_auth_callback(request: Request):
    if not settings.cloud_github_client_id or not settings.cloud_github_client_secret:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")

    state_cookie = request.cookies.get("kerf_github_oauth_state")
    state_param = request.query_params.get("state", "")

    if not state_cookie or state_cookie != state_param:
        raise HTTPException(status_code=400, detail="invalid state")

    try:
        state_json = base64.urlsafe_b64decode(state_param + "==")
        state_data = json.loads(state_json)
        user_id = state_data["u"]
        redirect_param = state_data.get("r", "")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid state encoding")

    response = Response(status_code=302)
    response.set_cookie(
        key="kerf_github_oauth_state",
        value="",
        httponly=True,
        samesite="lax",
        max_age=-1,
        path="/",
    )

    code = request.query_params.get("code", "")
    if not code:
        response.headers["Location"] = f"{settings.cors_origin}/auth/callback?provider=github&error=no_code"
        return response

    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": settings.cloud_github_client_id,
                    "client_secret": settings.cloud_github_client_secret,
                    "code": code,
                    "redirect_uri": settings.cloud_github_redirect_url,
                },
                headers={"Accept": "application/json"},
            )
            token_data = token_resp.json()
            access_token = token_data.get("access_token", "")
            scope = token_data.get("scope", "")

        async with httpx.AsyncClient() as client:
            user_resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            github_user = user_resp.json()
            github_user_id = github_user.get("id")
            github_login = github_user.get("login", "")

        encrypted_token = encrypt_secret(access_token.encode(), "cloud:github-token")

        pool = await get_pool_required()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cloud_github_tokens (user_id, access_token_encrypted, scope, github_user_id, github_login, updated_at)
                VALUES ($1, $2, $3, $4, $5, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    access_token_encrypted = EXCLUDED.access_token_encrypted,
                    scope = EXCLUDED.scope,
                    github_user_id = EXCLUDED.github_user_id,
                    github_login = EXCLUDED.github_login,
                    updated_at = now()
                """,
                user_id,
                encrypted_token,
                scope,
                github_user_id,
                github_login,
            )

        redirect_url = f"{settings.cors_origin}/auth/callback?provider=github"
        if redirect_param:
            redirect_url += f"&redirect={redirect_param}"
        response.headers["Location"] = redirect_url

    except Exception:
        response.headers["Location"] = f"{settings.cors_origin}/auth/callback?provider=github&error=oauth_failed"

    return response


@github_oauth_router.delete("/github")
async def github_auth_revoke(
    payload: dict = Depends(require_auth),
):
    user_id = payload["sub"]

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM cloud_github_tokens WHERE user_id = $1",
            user_id,
        )

    return Response(status_code=204)
