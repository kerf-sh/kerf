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

from kerf_core.config import get_settings
from kerf_core.db.connection import get_pool_required
from kerf_core.dependencies import require_auth
from kerf_core.storage import get_storage_required
from kerf_core.storage.s3 import S3Storage
from kerf_core.storage.git_storer import (
    S3GitStorer,
    StorerConcurrencyError,
    resolve_project_repo,
)
from kerf_core.storage.materialize import FileEntry, materialize_and_commit
from kerf_core.utils.encrypt import encrypt_secret, decrypt_secret
from kerf_cloud.github_app import app_jwt as _gh_app_jwt, installation_token as _gh_installation_token, install_url as _gh_install_url

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


async def _project_workspace_id(conn, project_id) -> Optional[str]:
    """The owning workspace id (recorded as first-uploader for dedup billing)."""
    return await conn.fetchval(
        "SELECT workspace_id FROM projects WHERE id = $1",
        project_id,
    )


async def _collect_file_entries(conn, project_id) -> list[FileEntry]:
    """Materialize the project's current file tree into ``FileEntry`` list.

    Repo-relative POSIX paths are reconstructed by walking ``parent_id`` so
    nested folders survive into the git tree. ``content`` is the file's exact
    bytes: from the inline ``content`` column, or (when offloaded) fetched
    once from the object store so ``materialize_and_commit`` can re-classify
    and re-key it content-addressed (no duplication — same oid → same key).
    """
    rows = await conn.fetch(
        "SELECT id, parent_id, name, kind, content, storage_key "
        "FROM files WHERE project_id = $1 AND deleted_at IS NULL",
        project_id,
    )
    by_id = {r["id"]: r for r in rows}

    def _full_path(row) -> str:
        segs = [row["name"]]
        seen = set()
        cur = row["parent_id"]
        while cur is not None and cur not in seen:
            seen.add(cur)
            parent = by_id.get(cur)
            if parent is None:
                break
            segs.append(parent["name"])
            cur = parent["parent_id"]
        return "/".join(reversed(segs))

    storage = get_storage_required()
    entries: list[FileEntry] = []
    for r in rows:
        if r["kind"] == "folder":
            continue
        if r["storage_key"]:
            stream, _ct = await storage.get(r["storage_key"])
            try:
                content = stream.read()
            finally:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
        else:
            content = (r["content"] or "").encode("utf-8")
        entries.append(FileEntry(path=_full_path(r), content=content))
    return entries


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
            SELECT sha, message, author_name, author_email, created_at, parent_shas
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
                "parent_shas": list(row["parent_shas"]) if row["parent_shas"] else [],
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

    branch = (body.get("branch", "") or "").strip() or "main"

    storage_inst = get_storage_required()
    loc = resolve_project_repo(pid, storage_inst)

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT name, email FROM users WHERE id = $1",
            uid,
        )
        if not user_row:
            raise HTTPException(status_code=400, detail="user not found")

        ws_id = await _project_workspace_id(conn, pid)
        entries = await _collect_file_entries(conn, pid)

        # If the canonical repo lives in S3, hydrate the server-local working
        # copy first so the new commit chains onto existing history. (Local
        # backend: the repo dir IS canonical — nothing to clone.)
        if loc.s3_prefix is not None:
            if not isinstance(storage_inst, S3Storage):
                raise HTTPException(
                    status_code=503,
                    detail="git commit requires S3 storage backend for this project",
                )
            storer = S3GitStorer(storage_inst, storage_inst.bucket, loc.s3_prefix)
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, storer.clone_to_local, loc.repo_dir
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        # ── Ordering: git + blob ledger FIRST, cloud_git_commits LAST ──
        # materialize_and_commit writes the content-addressed blobs, the
        # blob_objects/blob_refs ledger, then the real git commit. Only after
        # that durable commit succeeds do we append the cloud_git_commits
        # row. A crash between the two can at worst leave a real commit with
        # no cloud_git_commits row (re-derivable from refs / a retry) — it can
        # NEVER leave cloud_git_commits pointing at a sha that does not exist
        # in the repo. The ledger is therefore never ahead of git.
        try:
            mat = await materialize_and_commit(
                repo_dir=loc.repo_dir,
                files=entries,
                project_id=pid,
                workspace_id=ws_id,
                storage=storage_inst,
                db_conn=conn,
                message=message,
                author_name=user_row["name"] or "Kerf",
                author_email=user_row["email"] or "noreply@kerf.dev",
                branch=branch,
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"commit failed: {e}")

        sha = mat.commit_sha

        # Push the working copy back to the canonical S3 store (refs LAST).
        if loc.s3_prefix is not None:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, storer.push_from_local, loc.repo_dir
                )
            except StorerConcurrencyError as e:
                raise HTTPException(status_code=409, detail=str(e))
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        await conn.execute(
            """
            INSERT INTO cloud_git_commits (project_id, sha, message, author_name, author_email, branch, parent_shas)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            pid, sha, message, user_row["name"], user_row["email"], branch, mat.parent_shas,
        )

        await conn.execute(
            """
            UPDATE cloud_git_branches SET head_sha = $3 WHERE project_id = $1 AND name = $2
            """,
            pid, branch, sha,
        )
        await conn.execute(
            """
            UPDATE cloud_git_repos SET head_sha = $2 WHERE project_id = $1
            """,
            pid, sha,
        )

    return {
        "sha": sha,
        "branch": branch,
        "tree_sha": mat.tree_sha,
        "blobs": mat.blobs,
        "inlined": mat.inlined,
    }


@router.post("/projects/{pid}/git/fork")
async def git_fork(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    """Cheap-fork the project's git repo into ``target_project_id``.

    The fork gets its OWN bare repo (its own refs/objects, independent
    history) but every offloaded large file is shared by reference: the
    object store is content-addressed (``blobs/<oid>``), so we copy NO blob
    bytes — we only add ``blob_refs`` rows for the fork pointing at the same
    oids the source already wrote. Near-zero marginal storage for the Nth
    fork of a STEP-heavy project, which is the commercial point of T-125.

    Ordering note: the git object copy happens before the blob_refs inserts;
    a crash mid-way leaves only extra/absent ref rows (idempotent on retry,
    GC-safe) and never a ref to a missing object.
    """
    user_id = payload.get("sub")
    await require_editor(request, pid, user_id)

    body = await request.json()
    target_project_id = (body.get("target_project_id", "") or "").strip()
    if not target_project_id:
        raise HTTPException(status_code=400, detail="target_project_id is required")

    # Caller must also be able to write the fork target.
    await require_editor(request, target_project_id, user_id)

    storage_inst = get_storage_required()
    src_loc = resolve_project_repo(pid, storage_inst)
    dst_loc = resolve_project_repo(target_project_id, storage_inst)

    def _copy_repo(src_dir: str, dst_dir: str) -> None:
        # A bare repo is a self-contained directory tree. Copying it gives
        # the fork its own refs/objects; the LFS pointers inside the tree
        # still resolve to the SAME content-addressed object-store keys, so
        # no blob bytes are duplicated.
        import shutil

        if not os.path.isdir(src_dir):
            raise FileNotFoundError(f"source repo not found: {src_dir}")
        if os.path.isdir(dst_dir):
            shutil.rmtree(dst_dir)
        shutil.copytree(src_dir, dst_dir)

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        # Hydrate the source working copy from S3 if that is canonical.
        if src_loc.s3_prefix is not None:
            if not isinstance(storage_inst, S3Storage):
                raise HTTPException(
                    status_code=503,
                    detail="git fork requires S3 storage backend for this project",
                )
            src_storer = S3GitStorer(
                storage_inst, storage_inst.bucket, src_loc.s3_prefix
            )
            await asyncio.get_event_loop().run_in_executor(
                None, src_storer.clone_to_local, src_loc.repo_dir
            )

        try:
            await asyncio.get_event_loop().run_in_executor(
                None, _copy_repo, src_loc.repo_dir, dst_loc.repo_dir
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        # Share objects by reference: add a blob_refs row for the fork at
        # every (oid, path) the source already references. No storage.put,
        # no second byte-copy. Idempotent via ON CONFLICT.
        src_refs = await conn.fetch(
            "SELECT oid, path FROM blob_refs WHERE project_id = $1", pid
        )
        for r in src_refs:
            await conn.execute(
                """
                INSERT INTO blob_refs (oid, project_id, path)
                VALUES ($1, $2, $3)
                ON CONFLICT (oid, project_id, path) DO NOTHING
                """,
                r["oid"], target_project_id, r["path"],
            )

        # Push the fork's own repo to its canonical S3 prefix.
        if dst_loc.s3_prefix is not None:
            dst_storer = S3GitStorer(
                storage_inst, storage_inst.bucket, dst_loc.s3_prefix
            )
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, dst_storer.push_from_local, dst_loc.repo_dir
                )
            except StorerConcurrencyError as e:
                raise HTTPException(status_code=409, detail=str(e))
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    return {
        "source_project_id": pid,
        "target_project_id": target_project_id,
        "shared_objects": len(src_refs),
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
    except StorerConcurrencyError as e:
        raise HTTPException(status_code=409, detail=str(e))
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
    """Redirect the authenticated user to the GitHub App installation page.

    The user selects repos to grant access to. GitHub redirects back to
    /github/callback with installation_id (and setup_action=install or
    setup_action=update).

    Falls back gracefully when the GitHub App is not configured (503).
    """
    if not settings.cloud_github_app_id or not settings.github_private_key_pem:
        raise HTTPException(status_code=503, detail="GitHub App not configured")
    if not settings.cloud_github_app_slug:
        raise HTTPException(status_code=503, detail="GitHub App slug not configured")

    user_id = payload["sub"]
    redirect_query_param = request.query_params.get("redirect", "")

    nonce = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()
    state_data = {"n": nonce, "u": user_id, "r": redirect_query_param}
    state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode().rstrip("=")

    location = _gh_install_url(settings.cloud_github_app_slug, state)

    response = Response(status_code=302)
    response.headers["Location"] = location
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
    """Handle GitHub App installation callback.

    GitHub redirects here after the user installs (or updates) the App,
    sending ?installation_id=<id>&setup_action=install&state=<state>.

    We persist the installation_id against the user row in
    cloud_github_tokens. The actual short-lived installation access token is
    NEVER stored — it is minted on demand via github_app.installation_token().
    """
    if not settings.cloud_github_app_id or not settings.github_private_key_pem:
        raise HTTPException(status_code=503, detail="GitHub App not configured")

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

    installation_id_str = request.query_params.get("installation_id", "")
    if not installation_id_str:
        response.headers["Location"] = f"{settings.cors_origin}/auth/callback?provider=github&error=no_installation"
        return response

    try:
        installation_id = int(installation_id_str)
    except ValueError:
        response.headers["Location"] = f"{settings.cors_origin}/auth/callback?provider=github&error=bad_installation_id"
        return response

    try:
        # Mint a token to confirm the installation is valid and fetch the
        # GitHub user/login associated with this installation.
        inst_token = await _gh_installation_token(
            installation_id,
            settings.cloud_github_app_id,
            settings.github_private_key_pem,
        )

        async with httpx.AsyncClient() as client:
            user_resp = await client.get(
                "https://api.github.com/installation/token",
                headers={"Authorization": f"Bearer {inst_token}", "Accept": "application/vnd.github+json"},
            )
            # Fall back gracefully if this endpoint isn't accessible
            github_user_id = None
            github_login = ""
            if user_resp.status_code < 400:
                gh_data = user_resp.json()
                github_login = gh_data.get("login", "")

        pool = await get_pool_required()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cloud_github_tokens (
                    user_id, access_token_encrypted, scope,
                    github_user_id, github_login, github_installation_id, updated_at
                )
                VALUES ($1, $2, '', $3, $4, $5, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    github_installation_id = EXCLUDED.github_installation_id,
                    github_login = COALESCE(NULLIF(EXCLUDED.github_login, ''), cloud_github_tokens.github_login),
                    updated_at = now()
                """,
                user_id,
                # Placeholder encrypted blob — the OAuth token is no longer used;
                # we store a zero-length encrypted sentinel so the NOT NULL
                # constraint is satisfied on new rows.
                encrypt_secret(b"", "cloud:github-token"),
                github_user_id,
                github_login,
                installation_id,
            )

        redirect_url = f"{settings.cors_origin}/auth/callback?provider=github"
        if redirect_param:
            redirect_url += f"&redirect={redirect_param}"
        response.headers["Location"] = redirect_url

    except Exception:
        response.headers["Location"] = f"{settings.cors_origin}/auth/callback?provider=github&error=install_failed"

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


# ---------------------------------------------------------------------------
# Git provider settings endpoints (T-146)
# ---------------------------------------------------------------------------

_KERF_GIT_NOTE = (
    "Kerf's hosted git is always retained as the system of record. "
    "This only configures an optional additional external mirror."
)


def _provider_registry():
    """Return the default ProviderRegistry built from current settings."""
    from kerf_cloud.git_providers.registry import _build_default_registry
    return _build_default_registry(settings)


@router.get("/git/providers")
async def list_git_providers(
    payload: dict = Depends(require_auth),
):
    """List all git providers that are configured (env-gated).

    Only providers whose app credentials are present in the server environment
    are returned. Unconfigured providers are never exposed.
    """
    registry = _provider_registry()
    names = registry.available_names()
    return {
        "providers": names,
        "note": _KERF_GIT_NOTE,
    }


class ProviderConnectRequest(BaseModel):
    provider: str
    github_owner: Optional[str] = None
    github_repo: Optional[str] = None


@router.post("/projects/{pid}/git/provider/connect")
async def git_provider_connect(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    """Connect a project's optional external mirror to a configured provider.

    The caller must be an editor or owner of the project. Only providers
    reported by GET /git/providers (i.e. env-configured) may be used.
    Kerf's hosted git is always retained regardless of this setting.
    """
    user_id = payload.get("sub")
    await require_editor(request, pid, user_id)

    body = await request.json()
    provider_name = (body.get("provider") or "").strip()
    if not provider_name:
        raise HTTPException(status_code=400, detail="provider is required")

    pool = await get_pool_required()
    registry = _provider_registry()
    provider = registry.get(provider_name, pool=pool)
    if provider is None:
        raise HTTPException(
            status_code=404,
            detail=f"provider '{provider_name}' is not available (not configured or unknown)",
        )

    kwargs = {k: v for k, v in body.items() if k != "provider"}
    try:
        result = await provider.connect(pid, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        **result,
        "kerf_git_retained": True,
        "note": _KERF_GIT_NOTE,
    }


@router.post("/projects/{pid}/git/provider/disconnect")
async def git_provider_disconnect(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    """Disconnect a project's optional external mirror.

    Kerf's hosted git is always retained — this only removes the mirror link.
    """
    user_id = payload.get("sub")
    await require_editor(request, pid, user_id)

    body = await request.json() if (await request.body()) else {}
    provider_name = (body.get("provider") or "").strip()
    if not provider_name:
        raise HTTPException(status_code=400, detail="provider is required")

    pool = await get_pool_required()
    registry = _provider_registry()
    provider = registry.get(provider_name, pool=pool)
    if provider is None:
        raise HTTPException(
            status_code=404,
            detail=f"provider '{provider_name}' is not available (not configured or unknown)",
        )

    kwargs = {k: v for k, v in body.items() if k != "provider"}
    try:
        await provider.disconnect(pid, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "provider": provider_name,
        "project_id": pid,
        "disconnected": True,
        "kerf_git_retained": True,
        "note": _KERF_GIT_NOTE,
    }


@router.get("/projects/{pid}/git/provider/status")
async def git_provider_status(
    request: Request,
    payload: dict = Depends(require_auth),
    pid: Optional[str] = None,
):
    """Return connection and last-sync status for all configured providers.

    Any project member (not just editors) may query status. The response
    always includes a note confirming Kerf's hosted git is retained.
    """
    user_id = payload.get("sub")
    await require_role(request, pid, user_id)

    pool = await get_pool_required()
    registry = _provider_registry()

    statuses = []
    for provider in registry.configured_providers(pool=pool):
        try:
            pstatus = await provider.status(pid, user_id=user_id)
        except Exception:
            pstatus = {"provider": provider.name, "connected": False, "error": "status_unavailable"}
        statuses.append(pstatus)

    return {
        "project_id": pid,
        "providers": statuses,
        "kerf_git_retained": True,
        "note": _KERF_GIT_NOTE,
    }
