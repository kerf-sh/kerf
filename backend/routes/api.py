import re
import secrets
import hashlib
import hmac
import base64
import json
import logging
import os
import asyncio
import time
import uuid
import io
import zipfile
from datetime import datetime, timedelta
from typing import Optional, Any

import asyncpg
import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Cookie, UploadFile, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from urllib.parse import urlencode

from config import get_settings
from db.connection import get_pool_required
from db.queries import users as users_queries
from db.queries import workspaces as workspaces_queries
from db.queries import projects as projects_queries
from db.queries import files as files_queries
from db.queries import api_tokens as api_tokens_queries
from db.queries import refresh_tokens as rt_queries
from db.queries import chat_threads as threads_queries
from db.queries import share_links as share_links_queries
from db.queries import derived_artifacts as da_queries
from db.queries import jobs as jobs_queries
from db.queries import usage_events as usage_queries
from db.queries import upload_sessions as uploads_queries
from db.queries import library as library_queries
from db.queries import workshop_likes as workshop_likes_queries
from dependencies import require_auth, optional_auth
from storage import get_storage_required
import llm as llm_module
from tools.executor import execute as tools_execute, specs as tools_specs
from tools.context import ProjectCtx
from workers.auto_tess_worker import notify_step_uploaded

router = APIRouter()
LARGE_STEP_THRESHOLD = 5 * 1024 * 1024
settings = get_settings()

slug_re = re.compile(r'^[a-z0-9](?:[a-z0-9-]{1,30}[a-z0-9])?$')


def slug_from_name(name: str) -> str:
    lower = name.strip().lower()
    b = []
    prev_dash = False
    for r in lower:
        if r.isalnum():
            b.append(r)
            prev_dash = False
        elif r in ' _-':
            if not prev_dash and b:
                b.append('-')
                prev_dash = True
    out = ''.join(b).strip('-')
    if len(out) > 32:
        out = out[:32]
    if len(out) < 3:
        out = out + 'x' * (3 - len(out))
    return out


def hash_password(password: str) -> str:
    pepper = settings.password_pepper.encode()
    salted = pepper + password.encode()
    return hashlib.sha256(salted).hexdigest()


def check_password(stored_hash: str, password: str) -> bool:
    return hmac.compare_digest(stored_hash, hash_password(password))


def generate_access_token(user_id: str) -> tuple[str, datetime]:
    exp = datetime.utcnow() + timedelta(minutes=settings.jwt_access_ttl_minutes)
    payload = {"sub": user_id, "exp": exp, "iat": datetime.utcnow()}
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, exp


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def random_nonce() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(16)).decode().rstrip('=')


def generate_id() -> str:
    return secrets.token_hex(16)


def require_member(request: Request, pid: str, uid: str) -> Optional[str]:
    pool = get_pool_required()
    return "member"


def require_project_owner(request: Request, pid: str, uid: str) -> bool:
    return True


async def workspace_role_by_id(workspace_id: str, user_id: str) -> tuple[Optional[str], bool]:
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT role FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
            workspace_id, user_id
        )
        if row:
            return row['role'], True
        return None, True


async def get_user_workspace_role(conn: asyncpg.Connection, workspace_id: str, user_id: str) -> Optional[str]:
    row = await conn.fetchrow(
        "SELECT role FROM workspace_members WHERE workspace_id = $1 AND user_id = $2",
        workspace_id, user_id
    )
    return row['role'] if row else None


async def project_workspace_id(pid: str) -> Optional[str]:
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT workspace_id FROM projects WHERE id = $1",
            pid
        )
        return str(row['workspace_id']) if row else None


async def get_workspace_by_slug(slug: str) -> Optional[dict]:
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        return await workspaces_queries.get_workspace_by_slug(conn, slug)


async def create_personal_workspace(conn: asyncpg.Connection, user_id: str, display_name: str) -> Optional[dict]:
    slug = f"personal-{user_id[:8]}-{secrets.token_hex(4)}"
    slug = slug.lower()
    try:
        workspace = await workspaces_queries.create_workspace(conn, slug, display_name, user_id)
        await workspaces_queries.add_workspace_member(conn, workspace['id'], user_id, "owner")
        return workspace
    except Exception:
        return None


async def get_default_workspace(conn: asyncpg.Connection, user_id: str) -> tuple[Optional[dict], bool]:
    row = await conn.fetchrow(
        """
        SELECT w.* FROM workspaces w
        JOIN workspace_members wm ON w.id = wm.workspace_id
        WHERE wm.user_id = $1 AND wm.role = 'owner'
        ORDER BY w.created_at ASC
        LIMIT 1
        """,
        user_id,
    )
    if row:
        return dict(row), True
    return None, False


async def issue_tokens(conn: asyncpg.Connection, user_id: str) -> tuple[str, str]:
    access_token, _ = generate_access_token(user_id)
    refresh_token = generate_refresh_token()
    refresh_hash = hash_token(refresh_token)
    expires_at = datetime.utcnow() + timedelta(days=settings.jwt_refresh_ttl_days)
    await rt_queries.create_refresh_token(conn, user_id, refresh_hash, expires_at)
    return access_token, refresh_token


def user_to_response(user: dict) -> dict:
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "avatar_url": user.get("avatar_url") or "",
        "account_role": user["account_role"],
        "is_system": user["is_system"],
        "created_at": user["created_at"].isoformat() if isinstance(user["created_at"], datetime) else user["created_at"],
    }


def workspace_to_response(ws: dict) -> dict:
    return {
        "id": str(ws["id"]),
        "slug": ws["slug"],
        "name": ws["name"],
        "avatar_url": ws.get("avatar_url"),
        "created_at": ws["created_at"].isoformat() if isinstance(ws["created_at"], datetime) else ws["created_at"],
        "my_role": ws.get("my_role"),
        "member_count": ws.get("member_count"),
        "project_count": ws.get("project_count"),
    }


class MeResponse(BaseModel):
    id: str
    email: str
    name: str
    avatar_url: str
    account_role: str
    is_system: bool
    created_at: str
    default_workspace: Optional[dict] = None


@router.get("/me")
async def me(payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, name, avatar_url, account_role, is_system, created_at FROM users WHERE id = $1",
            user_id,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

        user = dict(row)
        default_ws, _ = await get_default_workspace(conn, str(user["id"]))

        return {
            **user_to_response(user),
            "default_workspace": workspace_to_response(default_ws) if default_ws else None,
        }


class UpdateMeRequest(BaseModel):
    name: Optional[str] = None


@router.patch("/me")
async def update_me(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        if req.name is not None:
            name = req.name.strip()
            row = await conn.fetchrow(
                """
                UPDATE users SET name = $2 WHERE id = $1
                RETURNING id, email, name, avatar_url, account_role, is_system, created_at
                """,
                user_id, name,
            )
        else:
            row = await conn.fetchrow(
                "SELECT id, email, name, avatar_url, account_role, is_system, created_at FROM users WHERE id = $1",
                user_id,
            )

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

        return user_to_response(dict(row))


@router.get("/models")
async def list_models():
    return {
        "models": [
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
            {"id": "claude-opus-4-20250514", "name": "Claude Opus 4"},
        ]
    }


@router.get("/share/{token}")
async def lookup_share(token: str, payload: Optional[dict] = Depends(optional_auth)):
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT sl.*, p.name as project_name, p.workspace_id
            FROM share_links sl
            JOIN projects p ON sl.project_id = p.id
            WHERE sl.token = $1 AND sl.revoked_at IS NULL
              AND (sl.expires_at IS NULL OR sl.expires_at > now())
            """,
            token,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="share not found")

        if row["max_uses"]:
            try:
                if int(row["uses"]) >= int(row["max_uses"]):
                    raise HTTPException(status_code=status.HTTP_410_GONE, detail="share link expired")
            except (ValueError, TypeError):
                pass

        return {
            "id": str(row["id"]),
            "project_id": str(row["project_id"]),
            "project_name": row["project_name"],
            "role": row["role"],
        }


@router.post("/share/{token}/accept")
async def accept_share(token: str, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM share_links WHERE token = $1 AND revoked_at IS NULL",
            token,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="share not found")

        ws_id = str(row["project_id"])

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

        return {"role": role}


_MAX_AGENT_ITERATIONS = 10

_AGENT_SYSTEM_ADDENDUM = (
    "\n\nYou have file tools to inspect and modify the user's CAD project. "
    "Always read a file before editing it. Use edit_file with unique substrings to make targeted changes. "
    "Use write_file only when the change is large or for new files. "
    "After tool calls, give a brief summary of what changed — do NOT repeat the full file contents back unless asked. "
    "The user can see the file change in their editor automatically."
)

_logger = logging.getLogger(__name__)


def _default_state_path() -> Optional[str]:
    """Return canonical path to state.json: $KERF_STATE_PATH or ~/.config/kerf/state.json."""
    v = os.environ.get("KERF_STATE_PATH", "").strip()
    if v:
        return v
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if not xdg:
        home = os.path.expanduser("~")
        xdg = os.path.join(home, ".config")
    return os.path.join(xdg, "kerf", "state.json")


def _friendly_llm_error(provider_name: str, err: Exception) -> str:
    msg = str(err).lower()
    if "rate limit" in msg or "429" in msg:
        return "The model provider rate-limited the request. Please try again in a moment."
    if "401" in msg or "unauthorized" in msg or "invalid api key" in msg:
        return "The provider rejected the API key. Check the server's environment variables."
    if "context" in msg and "length" in msg:
        return "This thread is too long for the selected model. Start a fresh thread or pick a model with a larger context."
    if "timeout" in msg or "deadline" in msg:
        return "The model took too long to respond. Try again or pick a faster model."
    if "deprecated" in msg:
        return "The selected model rejected one of the request parameters. Try picking a different model — this usually means the catalog needs updating."
    return "The model returned an error. Try again, or pick a different model from the dropdown."


def _get_llm_registry() -> llm_module.Registry:
    return llm_module.Registry(llm_module.LLMConfig(
        anthropic_api_key=settings.anthropic_api_key,
        openai_api_key=settings.openai_api_key,
        moonshot_api_key=settings.moonshot_api_key,
        gemini_api_key=settings.gemini_api_key,
        default_model=settings.default_model,
    ))


@router.get("/bootstrap")
async def bootstrap():
    if not settings.local_mode:
        return {"has_state": False}
    state_path = _default_state_path()
    if not state_path:
        return {"has_state": False}
    try:
        if not os.path.exists(state_path):
            return {"has_state": False}
        with open(state_path, "r") as f:
            state = json.load(f)
        if not state.get("refresh_token"):
            return {"has_state": False}
        return {
            "has_state": True,
            "refresh_token": state["refresh_token"],
            "user": state.get("user"),
        }
    except Exception:
        return {"has_state": False}


@router.get("/workspaces")
async def list_workspaces(payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT w.id, w.slug, w.name, w.avatar_storage_key, w.created_by,
                   w.created_at, w.updated_at, m.role,
                   (SELECT count(*) FROM workspace_members wm WHERE wm.workspace_id = w.id) as member_count,
                   (SELECT count(*) FROM projects p WHERE p.workspace_id = w.id) as project_count
            FROM workspaces w
            JOIN workspace_members m ON m.workspace_id = w.id
            WHERE m.user_id = $1
            ORDER BY w.created_at ASC
            """,
            user_id,
        )

        if not rows:
            user_row = await conn.fetchrow("SELECT name, email FROM users WHERE id = $1", user_id)
            display = user_row["name"].strip() if user_row else ""
            if not display:
                email = user_row["email"] if user_row else ""
                at_idx = email.find("@")
                display = email[:at_idx] if at_idx > 0 else "My"
            ws = await create_personal_workspace(conn, user_id, display)
            if ws:
                rows = [ws]

        out = []
        for row in rows:
            ws = dict(row)
            key = ws.get("avatar_storage_key")
            ws["avatar_url"] = None
            if key:
                ws["avatar_url"] = f"/api/workspaces/avatar/{ws['id']}"
            ws["my_role"] = ws.pop("role", None)
            ws["id"] = str(ws["id"])
            ws["created_by"] = str(ws["created_by"]) if ws.get("created_by") else None
            out.append(ws)
        return out


class CreateWorkspaceRequest(BaseModel):
    name: str
    slug: Optional[str] = None


@router.post("/workspaces")
async def create_workspace(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")

    slug = req.slug.strip().lower() if req.slug else slug_from_name(name)
    if not slug_re.match(slug):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid slug")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                workspace = await workspaces_queries.create_workspace(conn, slug, name, user_id)
            except asyncpg.UniqueViolationError:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="slug already in use")

            await workspaces_queries.add_workspace_member(conn, workspace["id"], user_id, "owner")

            workspace["my_role"] = "owner"
            workspace["member_count"] = 1
            return workspace_to_response(workspace)


@router.get("/workspaces/{slug}")
async def get_workspace(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws = await workspaces_queries.get_workspace_by_slug(conn, slug)
        if not ws:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        role = await get_user_workspace_role(conn, str(ws["id"]), user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        members = await workspaces_queries.list_workspace_members(conn, ws["id"])

        ws = dict(ws)
        ws["my_role"] = role
        ws["member_count"] = len(members)

        key = ws.get("avatar_storage_key")
        ws["avatar_url"] = None
        if key:
            ws["avatar_url"] = f"/api/workspaces/avatar/{ws['id']}"

        return {
            **workspace_to_response(ws),
            "members": [user_to_response(m) for m in members],
        }


class UpdateWorkspaceRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None


@router.patch("/workspaces/{slug}")
async def update_workspace(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws = await workspaces_queries.get_workspace_by_slug(conn, slug)
        if not ws:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        role = await get_user_workspace_role(conn, str(ws["id"]), user_id)
        if not role or role not in ("owner", "admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner or admin required")

        updates = {}
        if req.name is not None:
            name = req.name.strip()
            if not name:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name cannot be empty")
            updates["name"] = name

        if req.slug is not None:
            s = req.slug.strip().lower()
            if not slug_re.match(s):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid slug")
            updates["slug"] = s

        if updates:
            ws = await workspaces_queries.update_workspace(conn, ws["id"], **updates)

        ws = dict(ws)
        ws["my_role"] = role
        key = ws.get("avatar_storage_key")
        ws["avatar_url"] = None
        if key:
            ws["avatar_url"] = f"/api/workspaces/avatar/{ws['id']}"
        return workspace_to_response(ws)


@router.delete("/workspaces/{slug}")
async def delete_workspace(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws = await workspaces_queries.get_workspace_by_slug(conn, slug)
        if not ws:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        role = await get_user_workspace_role(conn, str(ws["id"]), user_id)
        if role != "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner only")

        await workspaces_queries.delete_workspace(conn, ws["id"])
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/workspaces/accept")
async def accept_workspace_invite(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT id, workspace_id, role FROM workspace_invites WHERE token = $1",
                token,
            )
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invite not found")

            await workspaces_queries.add_workspace_member(conn, row["workspace_id"], user_id, row["role"])
            await conn.execute("DELETE FROM workspace_invites WHERE id = $1", row["id"])

            ws = await workspaces_queries.get_workspace(conn, row["workspace_id"])
            return workspace_to_response(ws)


@router.get("/workspaces/avatar/{id}")
async def serve_workspace_avatar(request: Request, id: str):
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT avatar_storage_key FROM workspaces WHERE id = $1",
            id,
        )
        if not row or not row["avatar_storage_key"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

        return Response(status_code=status.HTTP_200_OK)


@router.post("/workspaces/{slug}/avatar")
async def upload_workspace_avatar(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws = await workspaces_queries.get_workspace_by_slug(conn, slug)
        if not ws:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        role = await get_user_workspace_role(conn, str(ws["id"]), user_id)
        if not role or role not in ("owner", "admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner or admin required")

        return {"status": "ok"}


@router.delete("/workspaces/{slug}/avatar")
async def delete_workspace_avatar(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws = await workspaces_queries.get_workspace_by_slug(conn, slug)
        if not ws:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        role = await get_user_workspace_role(conn, str(ws["id"]), user_id)
        if not role or role not in ("owner", "admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner or admin required")

        return Response(status_code=status.HTTP_204_NO_CONTENT)


class InviteMemberRequest(BaseModel):
    email: str
    role: str = "member"


@router.post("/workspaces/{slug}/members")
async def invite_workspace_member(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws = await workspaces_queries.get_workspace_by_slug(conn, slug)
        if not ws:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        role = await get_user_workspace_role(conn, str(ws["id"]), user_id)
        if not role or role not in ("owner", "admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner or admin required")

        email = req.email.strip().lower()
        if not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email is required")

        role_map = {"owner": "owner", "admin": "admin", "member": "member", "editor": "member", "viewer": "member"}
        mapped_role = role_map.get(req.role, "member")

        user = await users_queries.get_user_by_email(conn, email)
        if user:
            member = await workspaces_queries.add_workspace_member(conn, ws["id"], str(user["id"]), mapped_role)
            return {"added": member}

        return {"invite": {"email": email, "role": mapped_role}}


class ChangeRoleRequest(BaseModel):
    role: str


@router.patch("/workspaces/{slug}/members/{member_id}")
async def change_workspace_member_role(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws = await workspaces_queries.get_workspace_by_slug(conn, slug)
        if not ws:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        role = await get_user_workspace_role(conn, str(ws["id"]), user_id)
        if not role or role not in ("owner", "admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner or admin required")

        current = await workspaces_queries.get_workspace_member(conn, ws["id"], member_id)
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")

        if current["role"] == "owner" and req.role != "owner":
            owner_count = await conn.fetchval(
                "SELECT count(*) FROM workspace_members WHERE workspace_id = $1 AND role = 'owner'",
                ws["id"]
            )
            if owner_count <= 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot demote the only owner")

        member = await workspaces_queries.add_workspace_member(conn, ws["id"], member_id, req.role)
        return member


@router.delete("/workspaces/{slug}/members/{member_id}")
async def remove_workspace_member(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws = await workspaces_queries.get_workspace_by_slug(conn, slug)
        if not ws:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        role = await get_user_workspace_role(conn, str(ws["id"]), user_id)
        if not role or role not in ("owner", "admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner or admin required")

        current = await workspaces_queries.get_workspace_member(conn, ws["id"], member_id)
        if not current:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")

        if current["role"] == "owner":
            owner_count = await conn.fetchval(
                "SELECT count(*) FROM workspace_members WHERE workspace_id = $1 AND role = 'owner'",
                ws["id"]
            )
            if owner_count <= 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot remove the only owner")

        await workspaces_queries.remove_workspace_member(conn, ws["id"], member_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects")
async def list_projects(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = workspace_id
        if not ws_id and workspace_slug:
            ws = await workspaces_queries.get_workspace_by_slug(conn, workspace_slug)
            if ws:
                ws_id = str(ws["id"])

        if ws_id:
            role = await get_user_workspace_role(conn, ws_id, user_id)
            if not role:
                return []

        tags_arg = None
        if tag:
            tags_arg = tag

        rows = await conn.fetch(
            """
            SELECT p.id, p.workspace_id, p.name, p.description, p.visibility, p.tags,
                   p.thumbnail_storage_key, p.thumbnail_updated_at,
                   p.created_at, p.updated_at, m.role
            FROM projects p
            JOIN workspace_members m ON m.workspace_id = p.workspace_id
            WHERE m.user_id = $1
              AND ($2::uuid IS NULL OR p.workspace_id = $2)
              AND ($3::text[] IS NULL OR p.tags @> $3::text[])
            ORDER BY p.updated_at DESC
            """,
            user_id, ws_id if ws_id else None, tags_arg,
        )

        out = []
        for row in rows:
            p = dict(row)
            p["id"] = str(p["id"])
            p["workspace_id"] = str(p["workspace_id"])
            if p.get("thumbnail_storage_key"):
                p["thumbnail_url"] = f"/api/projects/{p['id']}/thumbnail"
            else:
                p["thumbnail_url"] = None
            out.append(p)
        return out


class CreateProjectRequest(BaseModel):
    workspace_id: Optional[str] = None
    workspace_slug: Optional[str] = None
    name: str
    description: str = ""
    tags: list[str] = []
    starter: str = "jscad"


default_jscad = """// Kerf: default export receives the @jscad/modeling module and returns parts.
export default function ({ primitives, transforms, booleans }) {
  const base = primitives.cuboid({ size: [40, 40, 10] })
  const peg  = transforms.translate([0, 0, 10], primitives.cylinder({ radius: 6, height: 20 }))
  return [
    { id: 'base', geom: base },
    { id: 'peg',  geom: peg  },
  ]
}
"""


@router.post("/projects")
async def create_project(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")

    ws_id = req.workspace_id
    if not ws_id and req.workspace_slug:
        ws = await get_workspace_by_slug(req.workspace_slug)
        if ws:
            ws_id = str(ws["id"])

    if not ws_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="workspace_id or workspace_slug required")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        tags = list(set(t.strip() for t in req.tags if t.strip()))

        starter = req.starter.strip() if req.starter else "jscad"
        starter_content = ""
        starter_kind = "file"
        if starter == "jscad":
            starter_content = default_jscad
            starter_kind = "script"
        elif starter == "blank":
            starter_content = ""
        elif starter == "circuit":
            starter_content = ""
            starter_kind = "circuit"

        async with conn.transaction():
            project = await projects_queries.create_project(conn, ws_id, name, req.description, "private", tags)

            if starter_content:
                await files_queries.create_file(conn, project["id"], starter, starter_kind, None, starter_content)

        return {
            **project,
            "my_role": role if role == "owner" else "editor",
        }


@router.get("/projects/{pid}")
async def get_project(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, workspace_id, name, description, visibility, tags, created_at, updated_at FROM projects WHERE id = $1",
            pid,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        ws_id = str(row["workspace_id"])
        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        p = dict(row)
        p["my_role"] = role
        return p


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    visibility: Optional[str] = None
    workspace_id: Optional[str] = None
    tags: Optional[list[str]] = None


@router.patch("/projects/{pid}")
async def update_project(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, workspace_id, name, description, visibility, tags FROM projects WHERE id = $1",
            pid,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        ws_id = str(row["workspace_id"])
        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot edit project")

        if req.visibility and req.visibility not in ("private", "unlisted", "public"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid visibility")

        updates = {}
        if req.name is not None:
            updates["name"] = req.name.strip()
        if req.description is not None:
            updates["description"] = req.description
        if req.visibility is not None:
            updates["visibility"] = req.visibility
        if req.tags is not None:
            updates["tags"] = list(set(t.strip() for t in req.tags if t.strip()))

        if updates:
            project = await projects_queries.update_project(conn, pid, **updates)
        else:
            project = dict(row)

        project["my_role"] = role
        return project


@router.delete("/projects/{pid}")
async def delete_project(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT workspace_id FROM projects WHERE id = $1", pid)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        ws_id = str(row["workspace_id"])
        role = await get_user_workspace_role(conn, ws_id, user_id)
        if role != "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner only")

        await projects_queries.delete_project(conn, pid)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{pid}/bom")
async def get_bom(pid: str, request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        rows = await conn.fetch(
            "SELECT id, parent_id, name, kind, content FROM files "
            "WHERE project_id = $1 AND deleted_at IS NULL "
            "AND kind IN ('assembly', 'part', 'folder', 'file', 'step', 'drawing', 'sketch')",
            pid,
        )

        by_id = {}
        files = []
        for row in rows:
            f = {
                "id": row["id"],
                "parent_id": row["parent_id"],
                "name": row["name"],
                "kind": row["kind"],
                "content": row["content"] or "",
            }
            files.append(f)
            by_id[f["id"]] = f

        paths = {}
        for f in files:
            parts = [f["name"]]
            cur = f["parent_id"]
            for _ in range(64):
                if cur is None:
                    break
                p = by_id.get(cur)
                if not p:
                    break
                parts.insert(0, p["name"])
                cur = p["parent_id"]
            paths[f["id"]] = "/" + "/".join(parts)

        aggregates = {}

        def parse_part_content(content: str) -> dict:
            if not content or not content.strip():
                return {"version": 1, "distributors": []}
            try:
                doc = json.loads(content)
            except Exception:
                return {"version": 1, "distributors": []}
            if doc.get("version", 0) == 0:
                doc["version"] = 1
            if "distributors" not in doc or doc["distributors"] is None:
                doc["distributors"] = []
            return doc

        def parse_bom_components(content: str) -> list:
            if not content or not content.strip():
                return []
            try:
                d = json.loads(content)
            except Exception:
                return []
            if d.get("components"):
                return d["components"]
            if d.get("children"):
                return d["children"]
            return []

        def parse_bom_overrides(content: str) -> list:
            if not content or not content.strip():
                return None
            try:
                d = json.loads(content)
            except Exception:
                return None
            return d.get("overrides")

        def resolve_active_config(doc: dict, pinned: str) -> str:
            configs = doc.get("configurations", [])
            if not configs:
                return ""
            if pinned:
                for c in configs:
                    if c.get("id") == pinned:
                        return c.get("id", "")
            default = doc.get("default_config", "").strip()
            if default:
                for c in configs:
                    if c.get("id") == default:
                        return c.get("id", "")
            return configs[0].get("id", "") if configs else ""

        def add_part(part_file: dict, quantity: int, config_id: str):
            doc = parse_part_content(part_file["content"])
            mpn = doc.get("mpn", "").strip()
            if not mpn:
                base = f"fid:{part_file['id']}"
            else:
                base = mpn
            key = base
            if config_id:
                key = base + "|cfg=" + config_id
            if key not in aggregates:
                aggregates[key] = {
                    "count": 0,
                    "file_id": part_file["id"],
                    "file_row": part_file,
                    "config_id": config_id,
                }
            aggregates[key]["count"] += quantity

        async def walk(fid: str, multiplier: int, config_hint: str, visited: dict):
            f = by_id.get(fid)
            if f is None:
                return
            if f["kind"] == "part":
                doc = parse_part_content(f["content"])
                cfg_id = resolve_active_config(doc, config_hint)
                add_part(f, multiplier, cfg_id)
                return
            if f["kind"] != "assembly":
                return
            if fid in visited:
                return
            visited[fid] = True

            for c in parse_bom_components(f["content"]):
                file_id_str = c.get("file_id", "")
                if not file_id_str:
                    continue
                q = 1
                if c.get("quantity") and c["quantity"] > 0:
                    q = c["quantity"]
                next_hint = config_hint
                if c.get("config_id"):
                    next_hint = c["config_id"]
                await walk(file_id_str, multiplier * q, next_hint, visited)

        override_by_part = {}
        warnings = []

        for f in files:
            if f["kind"] == "assembly":
                visited = {}
                await walk(f["id"], 1, "", visited)
                overrides = parse_bom_overrides(f["content"])
                if overrides:
                    for ov in overrides:
                        pfid = (ov.get("part_file_id") or "").strip()
                        if not pfid or pfid in override_by_part:
                            continue
                        override_by_part[pfid] = ov

        out = []
        grand_total = 0.0
        has_any_price = False

        for key, a in aggregates.items():
            doc = parse_part_content(a["file_row"]["content"])
            ov = override_by_part.get(a["file_id"])
            count = a["count"]
            non_stocked = False
            note = ""
            if ov:
                if ov.get("quantity_override") is not None and ov["quantity_override"] >= 0:
                    count = ov["quantity_override"]
                non_stocked = bool(ov.get("non_stocked"))
                note = ov.get("note") or ""

            row = {
                "part": doc,
                "file_id": str(a["file_id"]),
                "path": paths.get(a["file_id"], ""),
                "count": count,
                "material_path": doc.get("material_path", ""),
            }
            if non_stocked:
                row["non_stocked"] = True
            if note:
                row["note"] = note
            if a["config_id"]:
                row["config_id"] = a["config_id"]
                for c in doc.get("configurations", []):
                    if c.get("id") == a["config_id"]:
                        row["config_label"] = c.get("label") or c.get("id", "")
                        break

            unit_price = None
            primary_dist = None
            for dist in doc.get("distributors", []):
                if dist.get("price_usd") is not None:
                    unit_price = dist["price_usd"]
                    primary_dist = {
                        "name": dist.get("name", ""),
                        "url": dist.get("url", ""),
                        "sku": dist.get("sku", ""),
                    }
                    break
            if primary_dist is None and doc.get("distributors"):
                d0 = doc["distributors"][0]
                primary_dist = {
                    "name": d0.get("name", ""),
                    "url": d0.get("url", ""),
                    "sku": d0.get("sku", ""),
                }
            if primary_dist is not None:
                row["primary_distributor"] = primary_dist
            if unit_price is not None:
                row["unit_price_usd"] = unit_price
                tot = unit_price * count
                row["total_price_usd"] = tot
                if not non_stocked:
                    grand_total += tot
                    has_any_price = True
            if not doc.get("mpn"):
                warnings.append(f'Part "{doc.get("name", "")}" has no MPN')
            out.append(row)

        out.sort(key=lambda r: (r["part"].get("name", ""), r.get("config_id", ""), r["path"]))

        total_ptr = None
        if has_any_price:
            total_ptr = grand_total

        return {
            "rows": out,
            "total_price_usd": total_ptr,
            "warnings": warnings,
        }


@router.get("/projects/{pid}/files")
async def list_files(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        rows = await conn.fetch(
            """
            SELECT f.id, f.project_id, f.parent_id, f.name, f.kind, f.extension,
                   f.storage_key, f.mime_type, f.size, f.mesh_storage_key,
                   j.status as tessellation_status,
                   f.created_at, f.updated_at
            FROM files f
            LEFT JOIN step_tessellation_jobs j ON j.file_id = f.id
            WHERE f.project_id = $1 AND f.deleted_at IS NULL
            ORDER BY f.kind DESC, f.name ASC
            """,
            pid,
        )

        out = []
        for row in rows:
            f = dict(row)
            f["id"] = str(f["id"])
            f["project_id"] = str(f["project_id"])
            if f.get("storage_key"):
                f["download_url"] = f"/api/projects/{pid}/files/{f['id']}/download"
            out.append(f)
        return out


class CreateFileRequest(BaseModel):
    name: str
    kind: str = "file"
    extension: Optional[str] = None
    parent_id: Optional[str] = None
    content: Optional[str] = None


@router.post("/projects/{pid}/files")
async def create_file(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot create files")

        if not req.name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")

        valid_kinds = ("file", "folder", "assembly", "drawing", "sketch", "part", "feature", "circuit", "equations", "script", "fem", "cam")
        if req.kind not in valid_kinds:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid kind")

        content = req.content or ""

        f = await files_queries.create_file(
            conn, pid, req.name, req.kind, req.parent_id, content, None, None, None, req.extension
        )

        f = dict(f)
        if f.get("storage_key"):
            f["download_url"] = f"/api/projects/{pid}/files/{f['id']}/download"
        return f


@router.get("/projects/{pid}/files/{fid}")
async def get_file(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            """
            SELECT f.id, f.project_id, f.parent_id, f.name, f.kind, f.extension, f.content,
                   f.storage_key, f.mime_type, f.size, f.mesh_storage_key,
                   j.status as tessellation_status,
                   f.created_at, f.updated_at
            FROM files f
            LEFT JOIN step_tessellation_jobs j ON j.file_id = f.id
            WHERE f.id = $1 AND f.project_id = $2 AND f.deleted_at IS NULL
            """,
            fid, pid,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

        f = dict(row)
        if f.get("storage_key"):
            f["download_url"] = f"/api/projects/{pid}/files/{f['id']}/download"
        return f


class UpdateFileRequest(BaseModel):
    name: Optional[str] = None
    extension: Optional[str] = None
    content: Optional[str] = None
    parent_id: Optional[str] = None


@router.patch("/projects/{pid}/files/{fid}")
async def update_file(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot edit files")

        f = await files_queries.update_file(
            conn, fid,
            name=req.name,
            content=req.content,
            parent_id=req.parent_id,
            extension=req.extension,
        )

        if not f:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

        f = dict(f)
        if f.get("storage_key"):
            f["download_url"] = f"/api/projects/{pid}/files/{f['id']}/download"
        return f


@router.delete("/projects/{pid}/files/{fid}")
async def delete_file(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot delete files")

        await files_queries.delete_file(conn, fid, soft=True)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{pid}/files/{fid}/download")
async def download_file(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            "SELECT storage_key, name, kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
            fid, pid,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

        if row['kind'] == 'step-ref':
            ref = json.loads(row['content'])
            blob_key = f"blobs/step/{ref['hash']}"
            storage = get_storage_required()
            blob_io, _ = await storage.get(blob_key)
            blob_bytes = blob_io.read()
            original_name = ref.get('original_name', row['name'].replace('.step-ref', '.step'))
            mime = ref.get('mime', 'model/step')
            from fastapi.responses import Response as FastAPIResponse
            return FastAPIResponse(
                content=blob_bytes,
                media_type=mime,
                headers={'Content-Disposition': f'attachment; filename="{original_name}"'},
            )

        return {"url": f"/api/blobs/{row['storage_key']}"}


@router.post("/projects/{pid}/files/{fid}/tessellate")
async def tessellate(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        await conn.execute(
            """
            INSERT INTO step_tessellation_jobs (file_id) VALUES ($1)
            ON CONFLICT (file_id) DO UPDATE SET status='queued', error=null, started_at=null, finished_at=null
            """,
            fid,
        )
        return {"status": "queued"}


@router.delete("/projects/{pid}/files/{fid}/tessellate")
async def purge_tessellation(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            "SELECT mesh_storage_key FROM files WHERE id=$1 AND project_id=$2 AND deleted_at IS NULL",
            fid, pid,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

        await conn.execute(
            """
            UPDATE step_tessellation_jobs SET status='queued', error=null, mesh_storage_key=null,
            started_at=null, finished_at=null WHERE file_id=$1
            """,
            fid,
        )
        return {"status": "purged"}


@router.post("/projects/{pid}/files/{fid}/fem")
async def run_fem(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot run FEM")

        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        input_spec = json.dumps(body) if body else "{}"

        row = await conn.fetchrow(
            """INSERT INTO fem_jobs (file_id, project_id, input_spec)
               VALUES ($1, $2, $3)
               ON CONFLICT (file_id) WHERE status IN ('queued', 'running')
               DO UPDATE SET input_spec = $3, status = 'queued', error = NULL,
                   started_at = NULL, finished_at = NULL
               RETURNING id""",
            fid, pid, input_spec,
        )
        return {"job_id": str(row["id"]), "status": "queued"}


@router.get("/projects/{pid}/files/{fid}/fem/status")
async def fem_job_status(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            "SELECT id, status, result_json, error FROM fem_jobs WHERE file_id = $1 ORDER BY created_at DESC LIMIT 1",
            fid,
        )
        if not row:
            return {"status": "not_found"}

        resp = {
            "job_id": str(row["id"]),
            "status": row["status"],
            "result": row["result_json"],
            "error": row["error"],
        }
        return resp


@router.post("/projects/{pid}/files/{fid}/solve-mates")
async def solve_mates(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
    """Solve assembly geometric constraints and return component transforms."""
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            "SELECT kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
            fid, pid,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
        if row["kind"] != "assembly":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file is not an assembly")

        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        fixed_component_id = body.get("fixed_component_id") if body else None

        try:
            doc = json.loads(row["content"] or "{}")
        except Exception:
            doc = {}

        components = doc.get("components", [])
        mates = doc.get("mates", [])

        # Try pyworker first, fall back to in-process
        pyworker_url = os.environ.get("PYWORKER_URL", "http://localhost:9090")
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{pyworker_url}/run-mates",
                    json={"components": components, "mates": mates, "fixed_component_id": fixed_component_id},
                )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass

        # In-process fallback
        from tools.solvespace_wrapper import solve_assembly
        result = solve_assembly(components, mates, fixed_component_id=fixed_component_id)
        return result


@router.post("/projects/{pid}/files/{fid}/tolerance/run")
async def run_tolerance(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
    """Run tolerance stack-up (worst_case, rss, or monte_carlo) for a .tolerance file."""
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            "SELECT kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
            fid, pid,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
        if row["kind"] != "tolerance":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file is not a .tolerance file")

        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        method = body.get("method", "monte_carlo") if body else "monte_carlo"
        samples = body.get("samples", 10000) if body else 10000
        rss_k = body.get("rss_k", 3.0) if body else 3.0

        try:
            doc = json.loads(row["content"] or "{}")
        except Exception:
            doc = {}

        dimensions = doc.get("tolerances", [])
        if not dimensions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no tolerances defined in file")

        from tools.tolerance import worst_case, rss, monte_carlo
        if method == "worst_case":
            return worst_case(dimensions)
        elif method == "rss":
            return rss(dimensions, rss_k=float(rss_k))
        else:
            return monte_carlo(dimensions, samples=int(samples))


@router.post("/projects/{pid}/files/{fid}/cam")
async def run_cam(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot run CAM")

        body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        input_spec = json.dumps(body) if body else "{}"

        row = await conn.fetchrow(
            """INSERT INTO cam_jobs (file_id, project_id, input_spec)
               VALUES ($1, $2, $3)
               ON CONFLICT (file_id) WHERE status IN ('queued', 'running')
               DO UPDATE SET input_spec = $3, status = 'queued', error = NULL,
                   started_at = NULL, finished_at = NULL
               RETURNING id""",
            fid, pid, input_spec,
        )
        return {"job_id": str(row["id"]), "status": "queued"}


@router.get("/projects/{pid}/files/{fid}/cam/status")
async def cam_job_status(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            "SELECT id, status, result_json, output_key, error FROM cam_jobs WHERE file_id = $1 ORDER BY created_at DESC LIMIT 1",
            fid,
        )
        if not row:
            return {"status": "not_found"}

        resp = {
            "job_id": str(row["id"]),
            "status": row["status"],
            "result": row["result_json"],
            "output_key": row["output_key"],
            "error": row["error"],
        }
        return resp


@router.post("/projects/{pid}/files/{fid}/sim")
async def run_sim(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot run simulation")

        body = await request.json()
        analysis = body.get("analysis", {})
        netlist = body.get("netlist")
        input_spec = {"analysis": analysis}
        if netlist:
            input_spec["netlist"] = netlist

        row = await conn.fetchrow(
            "INSERT INTO sim_jobs (file_id, project_id, input_spec) VALUES ($1, $2, $3) RETURNING id",
            fid, pid, json.dumps(input_spec),
        )
        return {"job_id": str(row["id"])}


@router.get("/projects/{pid}/files/{fid}/sim/status")
async def sim_job_status(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            "SELECT id, status, result_json, error FROM sim_jobs WHERE file_id = $1 ORDER BY created_at DESC LIMIT 1",
            fid,
        )
        if not row:
            return {"status": "not_found"}

        return {
            "job_id": str(row["id"]),
            "status": row["status"],
            "result": row["result_json"],
            "error": row["error"],
        }


DERIVED_KIND_ALLOWED = {"jscad_mesh", "sketch_geom2", "circuit_board_3d"}
DERIVED_MAX_PAYLOAD_BYTES = 16 << 20


def compute_content_sha(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


class DerivedLookupRequest(BaseModel):
    derived_kind: str


class DerivedStoreRequest(BaseModel):
    derived_kind: str
    payload_b64: str


@router.post("/projects/{pid}/files/{fid}/derived")
async def lookup_derived_artifact(
    pid: str,
    fid: str,
    request: Request,
    payload: dict = Depends(require_auth),
):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid body")

        derived_kind = body.get("derived_kind", "")
        if derived_kind not in DERIVED_KIND_ALLOWED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid derived_kind")

        content_row = await conn.fetchrow(
            "SELECT COALESCE(content, '') FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
            fid, pid,
        )
        if not content_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

        content = content_row[0]
        content_hash = compute_content_sha(content)

        row = await conn.fetchrow(
            """
            UPDATE derived_artifacts
            SET last_accessed_at = now()
            WHERE source_file_id = $1 AND content_sha256 = $2 AND derived_kind = $3
            RETURNING payload
            """,
            fid, content_hash, derived_kind,
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="compile-on-demand-not-yet-wired",
            )

        return {
            "cached": True,
            "derived_kind": derived_kind,
            "payload_b64": base64.b64encode(row["payload"]).decode(),
        }


@router.post("/projects/{pid}/files/{fid}/derived/store")
async def store_derived_artifact(
    pid: str,
    fid: str,
    request: Request,
    payload: dict = Depends(require_auth),
):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid body")

        derived_kind = body.get("derived_kind", "")
        if derived_kind not in DERIVED_KIND_ALLOWED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid derived_kind")

        payload_b64 = body.get("payload_b64", "")
        try:
            payload_bytes = base64.b64decode(payload_b64)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid payload_b64")

        if len(payload_bytes) > DERIVED_MAX_PAYLOAD_BYTES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payload exceeds 16MiB cap")

        content_row = await conn.fetchrow(
            "SELECT COALESCE(content, '') FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
            fid, pid,
        )
        if not content_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

        content = content_row[0]
        content_hash = compute_content_sha(content)

        await conn.execute(
            """
            INSERT INTO derived_artifacts(source_file_id, content_sha256, derived_kind, payload, payload_size_bytes)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (source_file_id, content_sha256, derived_kind) DO UPDATE SET
                payload = excluded.payload,
                payload_size_bytes = excluded.payload_size_bytes,
                last_accessed_at = now()
            """,
            fid, content_hash, derived_kind, payload_bytes, len(payload_bytes),
        )

        return {
            "stored": True,
            "derived_kind": derived_kind,
            "payload_size_bytes": len(payload_bytes),
        }


@router.delete("/projects/{pid}/files/{fid}/derived")
async def purge_derived_artifacts(
    pid: str,
    fid: str,
    request: Request,
    payload: dict = Depends(require_auth),
):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        exists_row = await conn.fetchrow(
            "SELECT true FROM files WHERE id = $1 AND project_id = $2",
            fid, pid,
        )
        if not exists_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

        result = await conn.execute(
            "DELETE FROM derived_artifacts WHERE source_file_id = $1",
            fid,
        )

        deleted_count = 0
        if result == "DELETE 1":
            deleted_count = 1
        elif result.startswith("DELETE "):
            try:
                deleted_count = int(result.split(" ")[1])
            except (IndexError, ValueError):
                pass

        return {"purged": deleted_count}


@router.get("/projects/{pid}/files/{fid}/diff")
async def get_file_diff(
    pid: str,
    fid: str,
    request: Request,
    payload: dict = Depends(require_auth),
    against: Optional[str] = None,
):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        file_row = await conn.fetchrow(
            "SELECT id, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
            fid, pid,
        )
        if not file_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

        current_content = file_row["content"] or ""

        against_revision_id = None
        against_content = None

        try:
            if against:
                rev_row = await conn.fetchrow(
                    """
                    SELECT fr.id, fr.content
                    FROM file_revisions fr
                    JOIN files f ON f.id = fr.file_id
                    WHERE fr.id = $1 AND fr.file_id = $2 AND f.project_id = $3
                    """,
                    against, fid, pid,
                )
                if not rev_row:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="revision not found")
                against_revision_id = str(rev_row["id"])
                against_content = rev_row["content"] or ""
            else:
                rev_row = await conn.fetchrow(
                    """
                    SELECT id, content
                    FROM file_revisions
                    WHERE file_id = $1
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    fid,
                )
                if rev_row:
                    against_revision_id = str(rev_row["id"])
                    against_content = rev_row["content"] or ""
                else:
                    return {
                        "components_added": 0,
                        "components_removed": 0,
                        "components_delta": 0,
                        "bom_total_delta_usd": 0.0,
                        "against": None,
                        "note": "no_prior_revision",
                    }
        except HTTPException:
            raise
        except Exception:
            return {
                "components_added": 0,
                "components_removed": 0,
                "components_delta": 0,
                "bom_total_delta_usd": 0.0,
                "against": None,
                "note": "no_prior_revision",
            }

        def parse_components(raw):
            try:
                obj = json.loads(raw) if raw else {}
                return obj.get("components") or obj.get("children") or []
            except Exception:
                return []

        against_components = parse_components(against_content)
        current_components = parse_components(current_content)

        against_ids = {c.get("id") for c in against_components if c.get("id")}
        current_ids = {c.get("id") for c in current_components if c.get("id")}

        components_added = len(current_ids - against_ids)
        components_removed = len(against_ids - current_ids)
        components_delta = len(current_components) - len(against_components)

        async def compute_bom_total(components_list):
            total = 0.0
            for comp in components_list:
                ref_file_id = comp.get("file_id")
                if not ref_file_id:
                    continue
                qty = comp.get("quantity") or 1
                try:
                    ref_row = await conn.fetchrow(
                        "SELECT kind, content FROM files WHERE id = $1 AND deleted_at IS NULL",
                        ref_file_id,
                    )
                    if not ref_row or ref_row["kind"] != "part":
                        continue
                    ref_content = ref_row["content"] or ""
                    ref_obj = json.loads(ref_content)
                    distributors = ref_obj.get("distributors") or []
                    price = None
                    for d in distributors:
                        p = d.get("price_usd")
                        if p is not None:
                            price = float(p)
                            break
                    if price is not None:
                        total += price * qty
                except Exception:
                    continue
            return total

        against_total = await compute_bom_total(against_components)
        current_total = await compute_bom_total(current_components)

        if against_total == 0.0 and current_total == 0.0:
            bom_total_delta_usd = None
        else:
            bom_total_delta_usd = current_total - against_total

        return {
            "components_added": components_added,
            "components_removed": components_removed,
            "components_delta": components_delta,
            "bom_total_delta_usd": bom_total_delta_usd,
            "against": against_revision_id,
        }


@router.post("/projects/{pid}/assets")
async def upload_asset(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot upload")

        return {"status": "ok"}


@router.get("/projects/{pid}/threads")
async def list_threads(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        rows = await conn.fetch(
            "SELECT * FROM chat_threads WHERE project_id = $1 ORDER BY last_message_at DESC",
            pid,
        )
        return [dict(row) for row in rows]


class CreateThreadRequest(BaseModel):
    file_id: Optional[str] = None
    title: str = ""
    model: Optional[str] = None


@router.post("/projects/{pid}/threads")
async def create_thread(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            """
            INSERT INTO chat_threads (project_id, file_id, title, model)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            pid, req.file_id, req.title, req.model,
        )
        return dict(row)


@router.patch("/projects/{pid}/threads/{tid}")
async def update_thread(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        return {"status": "ok"}


@router.delete("/projects/{pid}/threads/{tid}")
async def delete_thread(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        await conn.execute("DELETE FROM chat_threads WHERE id = $1", tid)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{pid}/threads/{tid}/messages")
async def list_messages(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        rows = await conn.fetch(
            "SELECT * FROM chat_messages WHERE thread_id = $1 ORDER BY created_at ASC",
            tid,
        )
        return [dict(row) for row in rows]


class PostMessageRequest(BaseModel):
    content: str
    part_refs: list = []
    model: Optional[str] = None


async def _insert_assistant_message(conn, tid: str, content: str, model_id: str, tool_calls: list) -> dict:
    tc_json = json.dumps([
        {"id": tc.id, "name": tc.name, "arguments": tc.arguments_json}
        for tc in (tool_calls or [])
    ])
    row = await conn.fetchrow(
        """
        INSERT INTO chat_messages (thread_id, role, content, part_refs, tool_calls, model)
        VALUES ($1, 'assistant', $2, '[]'::jsonb, $3::jsonb, $4)
        RETURNING *
        """,
        tid, content, tc_json, model_id,
    )
    return dict(row)


async def _insert_tool_message(conn, tid: str, tool_call_id: str, content: str) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO chat_messages (thread_id, role, content, part_refs, tool_call_id)
        VALUES ($1, 'tool', $2, '[]'::jsonb, $3)
        RETURNING *
        """,
        tid, content, tool_call_id,
    )
    return dict(row)


async def _load_llm_history(conn, thread_id: str, exclude_id: str) -> list:
    rows = await conn.fetch(
        """
        SELECT role, content, tool_calls, tool_call_id
        FROM chat_messages
        WHERE thread_id = $1 AND id <> $2
        ORDER BY created_at ASC
        """,
        thread_id, exclude_id,
    )
    out = []
    for row in rows:
        role = row["role"]
        content = row["content"] or ""
        tc_raw = row["tool_calls"]
        tc_id = row["tool_call_id"]
        msg = llm_module.Message(role=role, content=content)
        if tc_id:
            msg.tool_call_id = str(tc_id)
        if tc_raw and tc_raw not in ("null", "[]", b"null", b"[]"):
            try:
                arr = json.loads(tc_raw) if isinstance(tc_raw, (str, bytes)) else tc_raw
                for w in arr:
                    msg.tool_calls.append(llm_module.ToolCall(
                        id=w.get("id", ""),
                        name=w.get("name", ""),
                        arguments_json=w.get("arguments", "{}"),
                    ))
            except Exception:
                pass
        out.append(msg)
    return out


async def _load_part_contexts(conn, project_id: str, refs: list) -> list:
    if not refs:
        return []
    out = []
    for ref in refs:
        file_id = ref.get("file_id") if isinstance(ref, dict) else getattr(ref, "file_id", None)
        part_id = ref.get("part_id") if isinstance(ref, dict) else getattr(ref, "part_id", None)
        if not file_id:
            continue
        row = await conn.fetchrow(
            "SELECT name, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
            file_id, project_id,
        )
        if row:
            out.append(llm_module.PartContext(
                file_path=row["name"],
                part_id=part_id or "",
                content=row["content"] or "",
            ))
    return out


async def _auto_title_thread(tid: str, user_content: str, assistant_content: str,
                              provider: llm_module.Provider, model_id: str, pool) -> None:
    prompt = (
        "Generate a concise 3-6 word title for the following CAD chat exchange. "
        "Return ONLY the title, no quotes, no trailing punctuation, no preamble.\n\n"
        f"User: {user_content[:600]}\n\nAssistant: {assistant_content[:600]}"
    )
    try:
        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: provider.complete(llm_module.CompleteRequest(
                model=model_id,
                system="You name CAD chat threads succinctly. Output only the title.",
                messages=[llm_module.Message(role="user", content=prompt)],
                max_tokens=32,
            ))
        )
        title = resp.content.strip().strip("\"'`").rstrip(".!?")
        if len(title) > 80:
            title = title[:80]
        if not title:
            return
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE chat_threads SET title = $1, updated_at = now() WHERE id = $2",
                title, tid,
            )
    except Exception as e:
        _logger.warning(f"auto-title: {e}")


@router.post("/projects/{pid}/threads/{tid}/messages")
async def post_message(pid: str, tid: str, req: PostMessageRequest, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()

    ws_id = await project_workspace_id(pid)
    if not ws_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

    async with pool.acquire() as conn:
        role = await get_user_workspace_role(conn, ws_id, user_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    if role == "viewer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot post messages")

    # Validate thread belongs to project
    async with pool.acquire() as conn:
        thread_row = await conn.fetchrow(
            "SELECT id FROM chat_threads WHERE id = $1 AND project_id = $2", tid, pid
        )
    if not thread_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")

    if not req.content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="content is required")

    part_refs = req.part_refs or []

    # Count existing user messages for auto-title trigger
    async with pool.acquire() as conn:
        existing_user_count = await conn.fetchval(
            "SELECT count(*) FROM chat_messages WHERE thread_id = $1 AND role = 'user'", tid
        )
    is_first_user_message = (existing_user_count == 0)

    # Resolve model: body.model -> thread.model -> default
    async with pool.acquire() as conn:
        thread_model_row = await conn.fetchrow("SELECT model FROM chat_threads WHERE id = $1", tid)
    thread_model = thread_model_row["model"] if thread_model_row else None
    if req.model:
        chosen_model = req.model
    elif thread_model:
        chosen_model = thread_model
    else:
        chosen_model = settings.default_model

    # Insert user message
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            """
            INSERT INTO chat_messages (thread_id, role, content, part_refs)
            VALUES ($1, 'user', $2, $3::jsonb)
            RETURNING *
            """,
            tid, req.content, json.dumps(part_refs),
        )
    user_msg = dict(user_row)

    # Build LLM history
    async with pool.acquire() as conn:
        history_msgs = await _load_llm_history(conn, tid, str(user_msg["id"]))
        part_contexts = await _load_part_contexts(conn, pid, part_refs)

    final_user_content = llm_module.build_user_message(req.content, part_contexts)
    history_msgs.append(llm_module.Message(role="user", content=final_user_content))

    registry = _get_llm_registry()

    if not registry.has_any():
        async with pool.acquire() as conn:
            assistant_msg = await _insert_assistant_message(
                conn, tid, "LLM not configured — set ANTHROPIC_API_KEY", "none", None
            )
            await conn.execute(
                "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
            )
        return {"user_message": user_msg, "assistant_message": assistant_msg, "tool_messages": []}

    try:
        provider, provider_model_id = registry.resolve(chosen_model)
    except ValueError as e:
        _logger.warning(f"llm: resolve {chosen_model!r} failed: {e}")
        async with pool.acquire() as conn:
            assistant_msg = await _insert_assistant_message(
                conn, tid,
                "That model isn't available right now. Try picking a different one from the model dropdown.",
                "none", None,
            )
            await conn.execute(
                "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
            )
        return {"user_message": user_msg, "assistant_message": assistant_msg, "tool_messages": []}

    # Resolve project tags addendum
    async with pool.acquire() as conn:
        proj_row = await conn.fetchrow("SELECT tags FROM projects WHERE id = $1", pid)
    project_tags = proj_row["tags"] if proj_row and proj_row["tags"] else []
    type_addendum = llm_module.build_project_tags_addendum(project_tags)

    # Build tool specs for this role
    tool_specs = tools_specs(role)

    # Project context for tool runner
    proj_ctx = ProjectCtx(
        pool=pool,
        storage=get_storage_required(),
        project_id=uuid.UUID(pid),
        user_id=uuid.UUID(user_id),
        role=role,
        http_client=httpx.AsyncClient(timeout=30.0),
        file_revisions_max=settings.file_revisions_max,
    )

    last_assistant: dict = {}
    tool_msgs: list = []

    for iteration in range(_MAX_AGENT_ITERATIONS):
        try:
            resp = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: provider.complete(llm_module.CompleteRequest(
                    model=provider_model_id,
                    system=llm_module.SystemPrompt + _AGENT_SYSTEM_ADDENDUM + type_addendum,
                    messages=history_msgs,
                    tools=tool_specs,
                ))
            )
        except Exception as e:
            _logger.error(
                f"llm: provider {provider.name()} model {provider_model_id} call failed "
                f"(iter={iteration}): {e}"
            )
            async with pool.acquire() as conn:
                last_assistant = await _insert_assistant_message(
                    conn, tid, _friendly_llm_error(provider.name(), e), provider_model_id, None
                )
                await conn.execute(
                    "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
                )
            return {"user_message": user_msg, "assistant_message": last_assistant, "tool_messages": tool_msgs}

        # Persist assistant turn
        async with pool.acquire() as conn:
            last_assistant = await _insert_assistant_message(
                conn, tid, resp.content, provider_model_id, resp.tool_calls
            )

        # Record token usage (cloud only)
        if settings.usage_enabled and (resp.input_tokens > 0 or resp.output_tokens > 0):
            try:
                from cloud.usage import record_token_event
                await record_token_event(
                    pool, user_id, pid, provider_model_id,
                    resp.input_tokens, resp.output_tokens, cost_usd=0.0,
                )
            except Exception as ue:
                _logger.warning(f"usage: record token event: {ue}")

        # Append assistant turn to history
        history_msgs.append(llm_module.Message(
            role="assistant",
            content=resp.content,
            tool_calls=resp.tool_calls,
        ))

        if not resp.tool_calls or resp.stop_reason == "stop":
            break

        # Execute each tool call
        for tc in resp.tool_calls:
            result = await tools_execute(proj_ctx, tc.name, tc.arguments_json.encode())
            async with pool.acquire() as conn:
                tm = await _insert_tool_message(conn, tid, tc.id, result)
            tm["tool_name"] = tc.name
            tool_msgs.append(tm)
            history_msgs.append(llm_module.Message(
                role="tool",
                content=result,
                tool_call_id=tc.id,
            ))

        if iteration == _MAX_AGENT_ITERATIONS - 1:
            async with pool.acquire() as conn:
                last_assistant = await _insert_assistant_message(
                    conn, tid, "(stopped: max tool iterations reached)", provider_model_id, None
                )
            break

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
        )

    # Auto-title on first exchange (fire and forget)
    if is_first_user_message and registry.has_any():
        assistant_content = last_assistant.get("content", "") if last_assistant else ""
        asyncio.create_task(_auto_title_thread(
            tid, req.content, assistant_content, provider, provider_model_id, pool
        ))

    return {
        "user_message": user_msg,
        "assistant_message": last_assistant,
        "tool_messages": tool_msgs,
    }


@router.post("/projects/{pid}/share/links")
async def create_share_link(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        token = secrets.token_urlsafe(32)
        row = await conn.fetchrow(
            """
            INSERT INTO share_links (project_id, token, role, created_by)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            pid, token, role if role in ("owner", "admin") else "editor", user_id,
        )
        return dict(row)


@router.get("/projects/{pid}/share/links")
async def list_share_links(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        rows = await conn.fetch(
            "SELECT * FROM share_links WHERE project_id = $1 ORDER BY created_at DESC",
            pid,
        )
        return [dict(row) for row in rows]


@router.delete("/projects/{pid}/share/links/{lid}")
async def delete_share_link(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        await conn.execute("UPDATE share_links SET revoked_at = now() WHERE id = $1", lid)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{pid}/members")
async def list_members(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        members = await workspaces_queries.list_workspace_members(conn, ws_id)
        return [user_to_response(m) for m in members]


@router.post("/projects/{pid}/members")
async def add_member(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role not in ("owner", "admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner or admin required")

        email = req.email.strip().lower()
        user = await users_queries.get_user_by_email(conn, email)
        if user:
            member = await workspaces_queries.add_workspace_member(conn, ws_id, str(user["id"]), req.role)
            return {"added": member}
        return {"invite": {"email": email, "role": req.role}}


@router.patch("/projects/{pid}/members/{uid}")
async def update_member(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role not in ("owner", "admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner or admin required")

        member = await workspaces_queries.add_workspace_member(conn, ws_id, uid, req.role)
        return member


@router.delete("/projects/{pid}/members/{uid}")
async def remove_member(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role not in ("owner", "admin"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner or admin required")

        await workspaces_queries.remove_workspace_member(conn, ws_id, uid)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{pid}/files/{fid}/revisions")
async def list_revisions(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        if limit > 200:
            limit = 200

        rows = await conn.fetch(
            """
            SELECT fr.id, fr.file_id, fr.source, fr.user_id, u.name as user_name,
                   fr.created_at, COALESCE(fr.content_preview, LEFT(fr.content, 200)) as content_preview
            FROM file_revisions fr
            LEFT JOIN users u ON u.id = fr.user_id
            WHERE fr.file_id = $1
            ORDER BY fr.created_at DESC
            LIMIT $2
            """,
            fid, limit,
        )
        return [dict(row) for row in rows]


@router.get("/projects/{pid}/files/{fid}/revisions/{rid}")
async def get_revision(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            """
            SELECT fr.id, fr.file_id, fr.source, fr.user_id, u.name as user_name, fr.created_at
            FROM file_revisions fr
            LEFT JOIN users u ON u.id = fr.user_id
            INNER JOIN files f ON f.id = fr.file_id
            WHERE fr.id = $1 AND fr.file_id = $2 AND f.project_id = $3
            """,
            rid, fid, pid,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="revision not found")

        rev = dict(row)
        rev["content"] = ""
        return rev


@router.post("/projects/{pid}/files/{fid}/revisions/{rid}/restore")
async def restore_revision(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot restore revisions")

        await conn.execute(
            "UPDATE files SET deleted_at = null, updated_at = now() WHERE id = $1 AND project_id = $2",
            fid, pid,
        )
        return {"status": "restored"}


@router.get("/blobs/{path:path}")
async def serve_blob(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    return Response(status_code=status.HTTP_200_OK)


# Upload Handlers (uploads.go)


class InitUploadRequest(BaseModel):
    filename: str
    size: int
    mime: Optional[str] = ""
    sha256: str


class InitUploadResponse(BaseModel):
    upload_id: str
    chunk_size: int
    received_chunks: list[int]
    total_chunks: int
    complete: bool


@router.post("/projects/{pid}/uploads")
async def init_upload(
    request: Request,
    pid: str,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, uid)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        if role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot upload")

        try:
            req = InitUploadRequest(**await request.json())
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid body")

        req.filename = req.filename.strip()
        req.sha256 = req.sha256.strip().lower()
        if not req.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="filename required")
        if req.size <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="size must be > 0")
        if settings.step_max_bytes > 0 and req.size > settings.step_max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"file too large (> {settings.step_max_bytes} bytes)",
            )
        if len(req.sha256) != 64:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sha256 must be a 64-char hex digest")

        try:
            int(req.sha256, 16)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sha256 must be hex")

        chunk_size = settings.upload_chunk_size
        if chunk_size <= 0:
            chunk_size = 5_242_880
        total_chunks = (req.size + chunk_size - 1) // chunk_size
        if total_chunks <= 0:
            total_chunks = 1

        existing = await conn.fetchrow(
            """
            select id, complete, received_chunks, bytes_received, total_chunks
            from upload_sessions
            where project_id = $1 and sha256 = $2 and expires_at > now()
            order by created_at desc
            limit 1
            """,
            pid, req.sha256,
        )
        if existing:
            received = [int(x) for x in existing["received_chunks"]] if existing["received_chunks"] else []
            return {
                "upload_id": str(existing["id"]),
                "chunk_size": chunk_size,
                "received_chunks": received,
                "total_chunks": existing["total_chunks"],
                "complete": existing["complete"],
            }

        upload_id = str(uuid.uuid4())
        storage_key = upload_id
        ttl_hours = settings.upload_session_ttl_hours
        if ttl_hours <= 0:
            ttl_hours = 24
        expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

        await conn.execute(
            """
            insert into upload_sessions
              (id, project_id, user_id, filename, size, mime, sha256,
               storage_key, chunk_size, total_chunks, expires_at)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            uuid.UUID(upload_id),
            uuid.UUID(pid),
            uuid.UUID(uid),
            req.filename,
            req.size,
            req.mime or None,
            req.sha256,
            storage_key,
            chunk_size,
            total_chunks,
            expires_at,
        )

        return {
            "upload_id": upload_id,
            "chunk_size": chunk_size,
            "received_chunks": [],
            "total_chunks": total_chunks,
            "complete": False,
        }


@router.put("/projects/{pid}/uploads/{uid}/chunks/{n}")
async def put_chunk(
    request: Request,
    pid: str,
    uid: str,
    n: int,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, uid)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        if role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot upload")

        try:
            uuid.UUID(uid)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid upload id")

        if n < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid chunk index")

        row = await conn.fetchrow(
            """
            select id, project_id, user_id, filename, size, mime, sha256, storage_key,
                   chunk_size, total_chunks, received_chunks, bytes_received, complete, expires_at
            from upload_sessions
            where id = $1 and project_id = $2
            """,
            uuid.UUID(uid),
            uuid.UUID(pid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="upload not found")

        if row["complete"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="upload already complete")
        if n >= row["total_chunks"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="chunk index out of range")

        if row["expires_at"] < datetime.utcnow():
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="upload expired")

        storage = get_storage_required()

        chunk_slack = row["chunk_size"] + 64 * 1024
        body = await request.body()
        if len(body) > chunk_slack:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="chunk too large")

        await storage.put_chunk(row["storage_key"], n, io.BytesIO(body))

        received_chunks = list(row["received_chunks"]) if row["received_chunks"] else []
        if n not in received_chunks:
            received_chunks.append(n)
            bytes_received = (row["bytes_received"] or 0) + len(body)
        else:
            bytes_received = row["bytes_received"]

        await conn.execute(
            """
            update upload_sessions
            set received_chunks = $2, bytes_received = $3
            where id = $1
            """,
            uuid.UUID(uid),
            received_chunks,
            bytes_received,
        )

        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{pid}/uploads/{uid}")
async def get_upload(
    request: Request,
    pid: str,
    uid: str,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, uid)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        if role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot upload")

        try:
            uuid.UUID(uid)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid upload id")

        row = await conn.fetchrow(
            """
            select id, project_id, user_id, filename, size, mime, sha256, storage_key,
                   chunk_size, total_chunks, received_chunks, bytes_received, complete, expires_at
            from upload_sessions
            where id = $1 and project_id = $2
            """,
            uuid.UUID(uid),
            uuid.UUID(pid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="upload not found")

        if row["expires_at"] < datetime.utcnow():
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="upload expired")

        received = [int(x) for x in row["received_chunks"]] if row["received_chunks"] else []
        return {
            "upload_id": str(row["id"]),
            "received_chunks": received,
            "total_chunks": row["total_chunks"],
            "bytes_received": row["bytes_received"] or 0,
            "complete": row["complete"],
        }


class FinalizeUploadRequest(BaseModel):
    kind: str = "step"
    parent_id: Optional[str] = None


@router.post("/projects/{pid}/uploads/{uid}/finalize")
async def finalize_upload(
    request: Request,
    pid: str,
    uid: str,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, uid)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        if role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot upload")

        try:
            uuid.UUID(uid)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid upload id")

        row = await conn.fetchrow(
            """
            select id, project_id, user_id, filename, size, mime, sha256, storage_key,
                   chunk_size, total_chunks, received_chunks, bytes_received, complete, expires_at
            from upload_sessions
            where id = $1 and project_id = $2
            """,
            uuid.UUID(uid),
            uuid.UUID(pid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="upload not found")

        received_chunks = [int(x) for x in row["received_chunks"]] if row["received_chunks"] else []
        if len(received_chunks) != row["total_chunks"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"missing chunks: have {len(received_chunks)} of {row['total_chunks']}",
            )

        parent_id = None
        req_body = await request.body()
        if req_body:
            try:
                req = FinalizeUploadRequest(**json.loads(req_body))
            except Exception:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid body")
            if req.kind and req.kind != "step":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="only kind='step' is supported")
            if req.parent_id:
                try:
                    uuid.UUID(req.parent_id)
                except ValueError:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid parent_id")
                parent_row = await conn.fetchrow(
                    "select kind from files where id = $1 and project_id = $2 and deleted_at is null",
                    uuid.UUID(req.parent_id),
                    uuid.UUID(pid),
                )
                if not parent_row:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="parent not found")
                if parent_row["kind"] != "folder":
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parent must be a folder")
                parent_id = req.parent_id

        storage = get_storage_required()

        final_key = f"projects/{pid}/assets/{uuid.uuid4()}-{row['filename']}"
        size = await storage.concat_chunks_to(row["storage_key"], final_key)

        mime_type = row["mime"] or "model/step"

        is_step_mime = (mime_type or '').startswith('model/')
        is_step_ext = row['filename'].lower().endswith(('.step', '.stp'))
        if size > LARGE_STEP_THRESHOLD and (is_step_mime or is_step_ext):
            blob_io, _ = await storage.get(final_key)
            blob_bytes = blob_io.read()
            sha256_hex = hashlib.sha256(blob_bytes).hexdigest()
            blob_key = f'blobs/step/{sha256_hex}'
            await storage.put(blob_key, io.BytesIO(blob_bytes), mime_type, size)
            await storage.delete(final_key)
            ref_data = {'hash': sha256_hex, 'size': size, 'original_name': row['filename'], 'mime': mime_type}
            ref_json = json.dumps(ref_data)
            base_name = row['filename']
            for ext in ('.step', '.stp', '.STEP', '.STP'):
                if base_name.endswith(ext):
                    base_name = base_name[:-len(ext)]
                    break
            ref_name = base_name + '.step-ref'
            f = await conn.fetchrow(
                """
                insert into files(project_id, parent_id, name, kind, content, storage_key, mime_type, size)
                values ($1, $2, $3, 'step-ref', $4, NULL, 'application/json', $5)
                returning id, project_id, parent_id, name, kind, content, storage_key, mime_type, size, created_at, updated_at
                """,
                uuid.UUID(pid),
                uuid.UUID(parent_id) if parent_id else None,
                ref_name,
                ref_json,
                len(ref_json.encode()),
            )
            await storage.delete_upload(row["storage_key"])
            await conn.execute("delete from upload_sessions where id = $1", uuid.UUID(uid))
            if settings.usage_enabled and size > 0:
                await usage_queries.record_storage(conn, uid, pid, size)
            try:
                await notify_step_uploaded(conn, str(f["id"]))
            except Exception:
                pass
            result = dict(f)
            result["download_url"] = f"/api/projects/{pid}/files/{result['id']}/download"
            return result

        f = await conn.fetchrow(
            """
            insert into files(project_id, parent_id, name, kind, content, storage_key, mime_type, size)
            values ($1, $2, $3, 'step', '', $4, $5, $6)
            returning id, project_id, parent_id, name, kind, content, storage_key, mime_type, size, created_at, updated_at
            """,
            uuid.UUID(pid),
            uuid.UUID(parent_id) if parent_id else None,
            row["filename"],
            final_key,
            mime_type,
            size,
        )

        await storage.delete_upload(row["storage_key"])
        await conn.execute("delete from upload_sessions where id = $1", uuid.UUID(uid))

        if settings.usage_enabled and size > 0:
            await usage_queries.record_storage(conn, uid, pid, size)

        await conn.execute(
            """
            insert into step_tessellation_jobs (file_id) values ($1)
            on conflict (file_id) do nothing
            """,
            f["id"],
        )

        try:
            await notify_step_uploaded(conn, str(f["id"]))
        except Exception:
            pass

        result = dict(f)
        if result.get("storage_key"):
            result["download_url"] = f"/api/projects/{pid}/files/{result['id']}/download"
        return result


@router.delete("/projects/{pid}/uploads/{uid}")
async def cancel_upload(
    request: Request,
    pid: str,
    uid: str,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, uid)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        if role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot upload")

        try:
            uuid.UUID(uid)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid upload id")

        row = await conn.fetchrow(
            """
            select id, project_id, user_id, filename, size, mime, sha256, storage_key,
                   chunk_size, total_chunks, received_chunks, bytes_received, complete, expires_at
            from upload_sessions
            where id = $1 and project_id = $2
            """,
            uuid.UUID(uid),
            uuid.UUID(pid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="upload not found")

        storage = get_storage_required()
        await storage.delete_upload(row["storage_key"])

        await conn.execute("delete from upload_sessions where id = $1", uuid.UUID(uid))

        return Response(status_code=status.HTTP_204_NO_CONTENT)


# Project Export (project_export.go)

EXPORT_MAX_BYTES = 500 * 1024 * 1024


def slugify_name(name: str) -> str:
    name = name.strip()
    if not name:
        return "project"
    result = []
    prev_dash = False
    for r in name.lower():
        if r.isalnum() or r in "-_":
            result.append(r)
            prev_dash = False
        else:
            if not prev_dash and result:
                result.append("-")
                prev_dash = True
    out = "".join(result).strip("-")
    if not out:
        return "project"
    if len(out) > 60:
        out = out[:60]
    return out


@router.get("/projects/{pid}/export")
async def export_project(
    request: Request,
    pid: str,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, uid)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            """
            select name, description, coalesce(tags, '{}'),
                   to_char(created_at at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                   thumbnail_storage_key
            from projects where id = $1
            """,
            uuid.UUID(pid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        name = row["name"]
        description = row["description"]
        tags = list(row["tags"]) if row["tags"] else []
        created_at = row["to_char"]
        thumb_key = row["thumbnail_storage_key"]

        file_rows = await conn.fetch(
            """
            select id, parent_id, name, kind, coalesce(content, ''),
                   storage_key, mime_type, size
            from files
            where project_id = $1 and deleted_at is null
            """,
            uuid.UUID(pid),
        )

        by_id = {}
        for fr in file_rows:
            by_id[str(fr["id"])] = {
                "id": str(fr["id"]),
                "parent_id": str(fr["parent_id"]) if fr["parent_id"] else None,
                "name": fr["name"],
                "kind": fr["kind"],
                "content": fr["coalesce"],
                "storage_key": fr["storage_key"],
                "mime_type": fr["mime_type"],
                "size": fr["size"],
            }

        path_of = {}

        def resolve(id_val: str) -> str:
            if id_val in path_of:
                return path_of[id_val]
            f = by_id.get(id_val)
            if not f:
                return ""
            parent_id = f["parent_id"]
            if not parent_id:
                p = f["name"]
            else:
                parent = resolve(parent_id)
                p = f["name"] if not parent else f"{parent}/{f['name']}"
            path_of[id_val] = p
            return p

        roots = []
        children_of = {}
        for id_val, f in by_id.items():
            parent_id = f["parent_id"]
            if not parent_id:
                roots.append(id_val)
            else:
                if parent_id not in children_of:
                    children_of[parent_id] = []
                children_of[parent_id].append(id_val)

        ordered = []
        queue = list(roots)
        while queue:
            id_val = queue.pop(0)
            ordered.append(id_val)
            queue.extend(children_of.get(id_val, []))

        manifest_files = []
        pendings = []
        seen_blob = set()

        for id_val in ordered:
            f = by_id[id_val]
            rel = resolve(id_val)

            entry = {"path": rel, "kind": f["kind"]}
            if f["mime_type"]:
                entry["mime_type"] = f["mime_type"]
            if f["size"]:
                entry["size"] = f["size"]

            if f["kind"] == "folder":
                pass
            elif f["storage_key"]:
                key = f["storage_key"]
                entry["storage_key"] = key
                if key not in seen_blob:
                    seen_blob.add(key)
                    pendings.append({"path": f"blobs/{key}", "blob_key": key})
            else:
                entry["content"] = f["content"]
                pendings.append({"path": f"files/{rel}", "content": f["content"]})

            manifest_files.append(entry)

        manifest = {
            "version": 1,
            "name": name,
            "description": description,
            "tags": tags,
            "created_at": created_at,
            "files": manifest_files,
        }

        slug = slugify_name(name)
        short = pid[:8]
        filename = f"{slug}-{short}.zip"

        async def generate():
            storage = get_storage_required()
            written = 0

            with zipfile.ZipFile(io.BytesIO(), "w", zipfile.ZIP_DEFLATED) as zf:
                manifest_json = json.dumps(manifest, indent=2)
                manifest_bytes = manifest_json.encode()
                written += len(manifest_bytes)
                if written > EXPORT_MAX_BYTES:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="export exceeds 500MB cap")
                zf.writestr("manifest.json", manifest_bytes)

                for p in pendings:
                    if p.get("blob_key"):
                        try:
                            blob_data, _ = await storage.get(p["blob_key"])
                            blob_bytes = blob_data.read()
                            written += len(blob_bytes)
                            if written > EXPORT_MAX_BYTES:
                                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="export exceeds 500MB cap")
                            zf.writestr(p["path"], blob_bytes)
                        except Exception:
                            pass
                    else:
                        content = p.get("content", "")
                        content_bytes = content.encode() if isinstance(content, str) else content
                        written += len(content_bytes)
                        if written > EXPORT_MAX_BYTES:
                            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="export exceeds 500MB cap")
                        zf.writestr(p["path"], content_bytes)

                if thumb_key:
                    try:
                        thumb_data, _ = await storage.get(thumb_key)
                        thumb_bytes = thumb_data.read()
                        written += len(thumb_bytes)
                        if written > EXPORT_MAX_BYTES:
                            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="export exceeds 500MB cap")
                        zf.writestr("thumbnail.jpg", thumb_bytes)
                    except Exception:
                        pass

                yield zf.writestr.__self__.getvalue()

        return StreamingResponse(
            generate(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


# Project Thumbnail (project_thumbnail.go)

THUMB_MAX_BYTES = 512 * 1024
THUMB_TARGET_DIM = 512
THUMB_JPEG_Q = 80


@router.post("/projects/{pid}/thumbnail")
async def upload_project_thumbnail(
    request: Request,
    pid: str,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, uid)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        if role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewers cannot upload thumbnails")

        form = await request.form()
        file = form.get("file")
        if not file:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing 'file' field")

        content = await file.read()
        if len(content) > THUMB_MAX_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="thumbnail too large (>512KB)")

        storage = get_storage_required()

        try:
            from PIL import Image
            import io as pil_io

            img = Image.open(pil_io.BytesIO(content))
            w, h = img.size
            if w == 0 or h == 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="zero-pixel image")

            if w > THUMB_TARGET_DIM or h > THUMB_TARGET_DIM:
                ratio = THUMB_TARGET_DIM / max(w, h)
                nw = int(w * ratio)
                nh = int(h * ratio)
                img = img.resize((nw, nh), Image.LANCZOS)

            buf = pil_io.BytesIO()
            img.save(buf, format="JPEG", quality=THUMB_JPEG_Q)
            jpg_bytes = buf.getvalue()
        except ImportError:
            jpg_bytes = content
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"decode/resize: {str(e)}")

        key = f"projects/{pid}/thumbnail.jpg"
        await storage.put(key, io.BytesIO(jpg_bytes), "image/jpeg", len(jpg_bytes))

        now = datetime.utcnow()
        public_url = storage.public_url(key, now)

        row = await conn.fetchrow(
            """
            update projects
               set thumbnail_storage_key = $2,
                   thumbnail_updated_at = now()
             where id = $1
            returning thumbnail_updated_at
            """,
            uuid.UUID(pid),
            key,
        )

        return {
            "id": pid,
            "thumbnail_url": public_url,
            "updated_at": row["thumbnail_updated_at"].isoformat() if row else now.isoformat(),
        }


# Avatar (avatar.go)

AVATAR_MAX_BYTES = 1 * 1024 * 1024
AVATAR_TARGET_DIM = 256
AVATAR_JPEG_Q = 85


@router.post("/me/avatar")
async def upload_avatar(
    request: Request,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        form = await request.form()
        file = form.get("file")
        if not file:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing 'file' field")

        content = await file.read()
        if len(content) > AVATAR_MAX_BYTES:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="avatar too large (>1MB)")

        storage = get_storage_required()

        try:
            from PIL import Image
            import io as pil_io

            img = Image.open(pil_io.BytesIO(content))
            w, h = img.size
            if w <= 0 or h <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="image has zero dimension")

            dst_w, dst_h = w, h
            if w > AVATAR_TARGET_DIM or h > AVATAR_TARGET_DIM:
                if w >= h:
                    dst_w = AVATAR_TARGET_DIM
                    dst_h = max(1, (h * AVATAR_TARGET_DIM) // w)
                else:
                    dst_h = AVATAR_TARGET_DIM
                    dst_w = max(1, (w * AVATAR_TARGET_DIM) // h)

            img = img.resize((dst_w, dst_h), Image.LANCZOS)

            buf = pil_io.BytesIO()
            img.save(buf, format="JPEG", quality=AVATAR_JPEG_Q)
            jpg_bytes = buf.getvalue()
        except ImportError:
            jpg_bytes = content
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"decode/resize: {str(e)}")

        key = f"users/{uid}/avatar.jpg"
        await storage.put(key, io.BytesIO(jpg_bytes), "image/jpeg", len(jpg_bytes))

        now = datetime.utcnow()
        public_url = storage.public_url(key, now)

        prev_key = None
        row = await conn.fetchrow(
            """
            with prev as (
                select avatar_storage_key from users where id = $1
            )
            update users
               set avatar_storage_key = $2,
                   avatar_updated_at = now(),
                   avatar_url = $3
              from prev
             where users.id = $1
            returning prev.avatar_storage_key, users.id, users.email, users.name,
                     users.avatar_url, users.avatar_updated_at, users.account_role,
                     users.is_system, users.created_at
            """,
            uuid.UUID(uid),
            key,
            public_url,
        )

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

        if row["prev"]["avatar_storage_key"] and row["prev"]["avatar_storage_key"] != key:
            await storage.delete(row["prev"]["avatar_storage_key"])

        return {
            "id": str(row["id"]),
            "email": row["email"],
            "name": row["name"],
            "avatar_url": row["avatar_url"] or "",
            "account_role": row["account_role"],
            "is_system": row["is_system"],
            "created_at": row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else row["created_at"],
        }


@router.delete("/me/avatar")
async def delete_avatar(
    request: Request,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            with prev as (
                select avatar_storage_key from users where id = $1
            )
            update users
               set avatar_storage_key = null,
                   avatar_updated_at = now(),
                   avatar_url = ''
              from prev
             where users.id = $1
            returning prev.avatar_storage_key, users.id, users.email, users.name,
                     users.avatar_url, users.avatar_updated_at, users.account_role,
                     users.is_system, users.created_at
            """,
            uuid.UUID(uid),
        )

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

        if row["prev"]["avatar_storage_key"]:
            storage = get_storage_required()
            await storage.delete(row["prev"]["avatar_storage_key"])

        return {
            "id": str(row["id"]),
            "email": row["email"],
            "name": row["name"],
            "avatar_url": row["avatar_url"] or "",
            "account_role": row["account_role"],
            "is_system": row["is_system"],
            "created_at": row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else row["created_at"],
        }


# Distributor Admin (distributor_admin.go)

_distributor_registry = None


def get_registry():
    return _distributor_registry


def set_registry(r):
    global _distributor_registry
    _distributor_registry = r


async def require_admin(request: Request) -> bool:
    payload = await require_auth.__wrapped__(request) if hasattr(require_auth, '__wrapped__') else None
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select account_role from users where id = $1",
            uuid.UUID(uid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        if row["account_role"] not in ("admin", "system"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
        return True


@router.get("/admin/distributors")
async def list_distributors(
    request: Request,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select account_role from users where id = $1",
            uuid.UUID(uid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        if row["account_role"] not in ("admin", "system"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")

    try:
        reg = get_registry()
        if reg is not None:
            metas = reg.meta()
            return {"distributors": [vars(m) if hasattr(m, '__dict__') else m for m in metas]}
    except Exception:
        pass
    return {"distributors": []}


class UpdateDistributorRequest(BaseModel):
    enabled: Optional[bool] = None
    rate_limit_per_minute: Optional[int] = None
    secret: Optional[dict] = None


@router.put("/admin/distributors/{name}")
async def update_distributor(
    request: Request,
    name: str,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select account_role from users where id = $1",
            uuid.UUID(uid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        if row["account_role"] not in ("admin", "system"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")

    try:
        reg = get_registry()
        if reg is None:
            return {"error": "distributor registry not initialized"}
        body_data = await request.json()
        from distributors.service import Credentials, validate_credentials

        secret = body_data.get("secret", {})
        creds = Credentials(
            client_id=secret.get("client_id", ""),
            client_secret=secret.get("client_secret", ""),
            api_key=secret.get("api_key", ""),
        )
        enabled = body_data.get("enabled", True)
        rate_limit = body_data.get("rate_limit_per_minute", 60)
        try:
            validate_credentials(name, creds)
        except ValueError as e:
            return {"error": str(e)}
        meta = await reg.upsert(name, enabled, rate_limit, creds)
        await reg.reload()
        return vars(meta) if hasattr(meta, '__dict__') else meta
    except Exception as e:
        return {"error": str(e)}


@router.delete("/admin/distributors/{name}")
async def delete_distributor(
    request: Request,
    name: str,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select account_role from users where id = $1",
            uuid.UUID(uid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        if row["account_role"] not in ("admin", "system"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{pid}/files/{fid}/distributors/refresh")
async def refresh_part_distributors(
    request: Request,
    pid: str,
    fid: str,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, uid)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        if role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot refresh distributors")

        row = await conn.fetchrow(
            "select kind, content from files where id = $1 and project_id = $2 and deleted_at is null",
            uuid.UUID(fid),
            uuid.UUID(pid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

        if row["kind"] != "part":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file is not a Part")

    try:
        reg = get_registry()
        if reg is not None:
            from distributors.sync import refresh_part
            new_content, n, _ = await refresh_part(pool, reg, row["content"])
            if n > 0:
                async with pool.acquire() as conn2:
                    await conn2.execute(
                        "update files set content = $2, updated_at = now() where id = $1 and deleted_at is null",
                        uuid.UUID(fid),
                        new_content,
                    )
                return {"updated": n, "content": new_content}
    except Exception:
        pass
    return {"updated": 0, "content": row["content"]}


# Admin Publishers (admin_publishers.go)


class PublisherRow(BaseModel):
    id: str
    email: str
    name: str
    avatar_url: Optional[str] = ""
    is_verified_publisher: bool
    is_system: bool
    account_role: str
    library_count: int
    created_at: str


class PublisherListResponse(BaseModel):
    rows: list[PublisherRow]
    next_cursor: Optional[str] = None


@router.get("/admin/publishers")
async def list_publishers(
    request: Request,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select account_role from users where id = $1",
            uuid.UUID(uid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        if row["account_role"] not in ("admin", "system"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")

    search = request.query_params.get("search", "").strip()
    verified_only = request.query_params.get("verified_only") == "true"
    cursor = request.query_params.get("cursor", "").strip()
    limit_str = request.query_params.get("limit", "50").strip()

    limit = 50
    try:
        n = int(limit_str)
        if n > 0 and n <= 200:
            limit = n
    except ValueError:
        pass

    args = []
    conditions = ["u.is_system = false"]

    if verified_only:
        conditions.append("u.is_verified_publisher = true")

    if search:
        conditions.append("(lower(u.email) like $1 or lower(coalesce(u.name, '')) like $1)")
        args.append(f"%{search.lower()}%")

    if cursor:
        try:
            cursor_time = datetime.fromisoformat(cursor)
            conditions.append(f"u.created_at < ${len(args) + 1}")
            args.append(cursor_time)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid cursor")

    args.append(limit + 1)

    query = f"""
        select
            u.id, u.email, coalesce(u.name, ''),
            coalesce(u.avatar_url, ''),
            u.is_verified_publisher, u.is_system, u.account_role,
            u.created_at,
            coalesce((
                select count(distinct f.id)
                from files f
                join projects p on p.id = f.project_id
                where p.owner_id = u.id
                  and f.kind = 'part'
                  and f.deleted_at is null
            ), 0) as library_count
        from users u
        where {" and ".join(conditions)}
        order by u.created_at desc
        limit ${len(args)}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *args)

        result_rows = []
        for r in rows[:limit]:
            result_rows.append(PublisherRow(
                id=str(r["id"]),
                email=r["email"],
                name=r["name"],
                avatar_url=r["coalesce"] or "",
                is_verified_publisher=r["is_verified_publisher"],
                is_system=r["is_system"],
                account_role=r["account_role"],
                library_count=r["library_count"],
                created_at=r["created_at"].isoformat() if isinstance(r["created_at"], datetime) else str(r["created_at"]),
            ))

        resp = PublisherListResponse(rows=result_rows)
        if len(rows) > limit:
            resp.next_cursor = result_rows[-1].created_at

        return resp


class SetVerifiedRequest(BaseModel):
    is_verified_publisher: bool


@router.put("/admin/publishers/{user_id}")
async def set_publisher_verified(
    request: Request,
    user_id: str,
    payload: dict = Depends(require_auth),
):
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select account_role from users where id = $1",
            uuid.UUID(uid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        if row["account_role"] not in ("admin", "system"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")

    try:
        req = SetVerifiedRequest(**await request.json())
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid body")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            update users
               set is_verified_publisher = $2
             where id = $1
            returning id, email, coalesce(name, ''), coalesce(avatar_url, ''),
                     is_verified_publisher, is_system, account_role, created_at
            """,
            uuid.UUID(user_id),
            req.is_verified_publisher,
        )

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

        library_count = await conn.fetchval(
            """
            select count(distinct f.id)
              from files f
              join projects p on p.id = f.project_id
             where p.owner_id = $1
               and f.kind = 'part'
               and f.deleted_at is null
            """,
            uuid.UUID(user_id),
        )

        return PublisherRow(
            id=str(row["id"]),
            email=row["email"],
            name=row["name"],
            avatar_url=row["coalesce"] or "",
            is_verified_publisher=row["is_verified_publisher"],
            is_system=row["is_system"],
            account_role=row["account_role"],
            library_count=library_count or 0,
            created_at=row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else str(row["created_at"]),
        )


# ---------------------------------------------------------------------------
# KiCad import
# ---------------------------------------------------------------------------

@router.post("/projects/{pid}/imports/kicad")
async def import_kicad_file(
    pid: str,
    request: Request,
    file: UploadFile,
    payload: dict = Depends(require_auth),
):
    """Accept a .kicad_sch / .kicad_pcb / .zip upload, forward to pyworker,
    write result as a new JSON file in the project, and return its file_id."""
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot import files")

    pyworker_url = os.getenv("PYWORKER_URL", "http://localhost:8090")
    content = await file.read()

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                f"{pyworker_url}/import-kicad",
                files={"file": (file.filename, content, file.content_type or "application/octet-stream")},
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                                detail=f"pyworker error: {resp.text[:300]}")
        data = resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"pyworker unreachable: {exc}")

    errors = data.get("errors") or []
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=errors[0])

    stem = file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename
    new_filename = f"{stem}.kicad.json"
    circuit_content = data.get("circuit_json", "{}")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        new_file_id = str(uuid.uuid4())
        await conn.execute(
            """INSERT INTO files (id, project_id, name, kind, content, created_at, updated_at)
               VALUES ($1, $2, $3, 'data', $4, NOW(), NOW())""",
            uuid.UUID(new_file_id), uuid.UUID(pid), new_filename, circuit_content,
        )

    return {
        "file_id": new_file_id,
        "filename": new_filename,
        "warnings": data.get("warnings", []),
    }


# ---------------------------------------------------------------------------
# Workshop endpoints
# ---------------------------------------------------------------------------

def _project_to_workshop_row(p: dict) -> dict:
    """Normalise a DB project dict into the workshop wire shape."""
    return {
        "project_id": str(p["id"]),
        "name": p.get("name", ""),
        "description": p.get("description", ""),
        "tags": list(p.get("tags") or []),
        "workspace_slug": p.get("workspace_slug", ""),
        "workspace_name": p.get("workspace_name", ""),
        "author_name": p.get("author_name", ""),
        "likes_count": int(p.get("likes_count") or 0),
        "liked_by_me": bool(p.get("liked_by_me", False)),
        "thumbnail_storage_key": p.get("thumbnail_storage_key"),
        "created_at": p["created_at"].isoformat() if p.get("created_at") else None,
        "updated_at": p["updated_at"].isoformat() if p.get("updated_at") else None,
    }


@router.get("/workshop/")
async def workshop_list(
    page: int = 1,
    sort: str = "newest",
    tag: Optional[Any] = None,
    auth: Optional[dict] = Depends(optional_auth),
):
    """GET /api/workshop/?page=&sort=&tag= — list public projects gallery."""
    # `tag` can appear multiple times; FastAPI gives a scalar when single
    # We'll read raw query params for multi-value tag support.
    per_page = 20
    offset = (max(page, 1) - 1) * per_page

    # tag may be a single string from query param default
    if isinstance(tag, str):
        tags = [tag] if tag else []
    elif isinstance(tag, list):
        tags = [t for t in tag if t]
    else:
        tags = []

    viewer_id = uuid.UUID(auth["sub"]) if auth else None

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        rows = await projects_queries.list_public_projects(
            conn,
            tags=tags or None,
            sort=sort,
            limit=per_page,
            offset=offset,
            viewer_user_id=viewer_id,
        )

    return {"rows": [_project_to_workshop_row(r) for r in rows], "page": page, "per_page": per_page}


@router.get("/workshop/parts")
async def workshop_list_parts_deprecated(
    search: Optional[str] = None,
    category: Optional[str] = None,
    verified_only: Optional[str] = None,
):
    """GET /api/workshop/parts — deprecated alias of library parts list."""
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        result = await library_queries.list_public_parts(
            conn,
            search=search or None,
            category=category or None,
            verified_only=(verified_only == "true"),
            limit=100,
            offset=0,
        )
    return result


@router.get("/workshop/{slug}")
async def workshop_get(
    slug: str,
    auth: Optional[dict] = Depends(optional_auth),
):
    """GET /api/workshop/:slug — public project detail (slug = project_id)."""
    try:
        project_id = uuid.UUID(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail="Project not found")

    viewer_id = uuid.UUID(auth["sub"]) if auth else None

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        project = await projects_queries.get_public_project(conn, project_id, viewer_user_id=viewer_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return _project_to_workshop_row(project)


class WorkshopPublishRequest(BaseModel):
    project_id: str
    title: str = ""
    description: str = ""


@router.post("/workshop/publish")
async def workshop_publish(
    body: WorkshopPublishRequest,
    auth: dict = Depends(require_auth),
):
    """POST /api/workshop/publish — owner-only, sets visibility='public'. Idempotent."""
    try:
        project_id = uuid.UUID(body.project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id")

    user_id = auth["sub"]
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        project = await projects_queries.get_project(conn, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # verify ownership via workspace membership
        role = await get_user_workspace_role(conn, str(project["workspace_id"]), user_id)
        if role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Not authorized")

        updates: dict = {"visibility": "public"}
        if body.title:
            updates["name"] = body.title
        if body.description:
            updates["description"] = body.description

        updated = await projects_queries.update_project(conn, project_id, **updates)

    return {"project_id": str(project_id), "visibility": "public", "name": updated.get("name", "")}


@router.delete("/workshop/{slug}")
async def workshop_unpublish(
    slug: str,
    auth: dict = Depends(require_auth),
):
    """DELETE /api/workshop/:slug — owner-only, sets visibility back to private."""
    try:
        project_id = uuid.UUID(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail="Project not found")

    user_id = auth["sub"]
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        project = await projects_queries.get_project(conn, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        role = await get_user_workspace_role(conn, str(project["workspace_id"]), user_id)
        if role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Not authorized")

        await projects_queries.update_project(conn, project_id, visibility="private")

    return {"project_id": str(project_id), "visibility": "private"}


@router.post("/workshop/{slug}/like")
async def workshop_toggle_like(
    slug: str,
    auth: dict = Depends(require_auth),
):
    """POST /api/workshop/:slug/like — toggle like. Returns {liked_by_me, likes_count}."""
    try:
        project_id = uuid.UUID(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail="Project not found")

    user_id = uuid.UUID(auth["sub"])
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        # ensure project exists and is public
        row = await conn.fetchval("SELECT id FROM projects WHERE id = $1 AND visibility = 'public'", project_id)
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")

        result = await workshop_likes_queries.toggle_like(conn, user_id, project_id)

    return result


class WorkshopForkRequest(BaseModel):
    project_name: Optional[str] = None


@router.post("/workshop/{slug}/fork")
async def workshop_fork(
    slug: str,
    body: WorkshopForkRequest = WorkshopForkRequest(),
    auth: dict = Depends(require_auth),
):
    """POST /api/workshop/:slug/fork — clones project+files under the caller's workspace."""
    try:
        source_project_id = uuid.UUID(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail="Project not found")

    user_id = auth["sub"]
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        # get source project (must be public)
        source = await conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1 AND visibility = 'public'",
            source_project_id,
        )
        if not source:
            raise HTTPException(status_code=404, detail="Project not found")

        # get caller's workspace
        workspace, _ = await get_default_workspace(conn, user_id)
        if not workspace:
            raise HTTPException(status_code=400, detail="No workspace found for user")

        fork_name = body.project_name or f"{source['name']} (fork)"
        new_project_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO projects (id, workspace_id, name, description, visibility, tags, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'private', $5, now(), now())
            """,
            new_project_id,
            workspace["id"],
            fork_name,
            source.get("description", ""),
            list(source.get("tags") or []),
        )

        # copy non-deleted files
        source_files = await conn.fetch(
            "SELECT * FROM files WHERE project_id = $1 AND deleted_at IS NULL",
            source_project_id,
        )
        truncated = False
        MAX_FILES = 500
        if len(source_files) > MAX_FILES:
            source_files = source_files[:MAX_FILES]
            truncated = True

        for f in source_files:
            await conn.execute(
                """
                INSERT INTO files (id, project_id, parent_id, name, kind, content,
                                   storage_key, mime_type, size, created_at, updated_at, extension)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now(), now(), $10)
                """,
                uuid.uuid4(),
                new_project_id,
                None,  # parent_id reset — flat fork
                f["name"],
                f["kind"],
                f["content"],
                f["storage_key"],
                f["mime_type"],
                f["size"],
                f["extension"],
            )

    return {"project_id": str(new_project_id), "truncated": truncated}


# ---------------------------------------------------------------------------
# Library endpoints
# ---------------------------------------------------------------------------

@router.get("/library/parts")
async def library_list_parts(
    search: Optional[str] = None,
    category: Optional[str] = None,
    verified_only: Optional[str] = None,
):
    """GET /api/library/parts?search=&category=&verified_only= — parts catalog."""
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        result = await library_queries.list_public_parts(
            conn,
            search=search or None,
            category=category or None,
            verified_only=(verified_only == "true"),
            limit=100,
            offset=0,
        )
    return result


@router.get("/library/parts/{slug}")
async def library_get_part(slug: str):
    """GET /api/library/parts/:slug — single part detail (slug = file_id or path)."""
    # Slug may be a UUID file_id or a path like workspace/project/filename.
    # We try UUID first; path-based lookup is a future enhancement.
    try:
        file_id = uuid.UUID(slug)
    except ValueError:
        raise HTTPException(status_code=404, detail="Part not found")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        part = await library_queries.get_public_part(conn, file_id)

    if not part:
        raise HTTPException(status_code=404, detail="Part not found")

    return part


class LibrarySubmissionRequest(BaseModel):
    target_workspace_slug: str
    payload: dict


@router.post("/library/submissions", status_code=201)
async def library_submit_part(
    body: LibrarySubmissionRequest,
    auth: dict = Depends(require_auth),
):
    """POST /api/library/submissions — submit a part for review."""
    user_id = uuid.UUID(auth["sub"])
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws = await workspaces_queries.get_workspace_by_slug(conn, body.target_workspace_slug)
        if not ws:
            raise HTTPException(status_code=404, detail="Target workspace not found")

        submission = await library_queries.create_library_submission(
            conn,
            submitter_user_id=user_id,
            target_workspace_id=ws["id"],
            payload=body.payload,
        )

    return {"id": str(submission["id"])}


# ---------------------------------------------------------------------------
# Admin library submission routes
# ---------------------------------------------------------------------------

@router.get("/admin/library/submissions")
async def admin_list_library_submissions(
    status_filter: Optional[str] = None,
    auth: dict = Depends(require_auth),
):
    """GET /api/admin/library/submissions — admin-only list."""
    user_id = auth["sub"]
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        user = await users_queries.get_user(conn, uuid.UUID(user_id))
        if not user or user.get("account_role") != "admin":
            raise HTTPException(status_code=403, detail="Admin only")

        rows = await library_queries.list_library_submissions(
            conn,
            status=status_filter or None,
        )

    return {
        "rows": [
            {
                **{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in row.items()},
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
            }
            for row in rows
        ]
    }


class AdminSubmissionAction(BaseModel):
    action: str  # "approve" | "reject"
    review_note: str = ""


@router.put("/admin/library/submissions/{submission_id}")
async def admin_update_library_submission(
    submission_id: str,
    body: AdminSubmissionAction,
    auth: dict = Depends(require_auth),
):
    """PUT /api/admin/library/submissions/{id} — approve or reject."""
    user_id = auth["sub"]
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        user = await users_queries.get_user(conn, uuid.UUID(user_id))
        if not user or user.get("account_role") != "admin":
            raise HTTPException(status_code=403, detail="Admin only")

        try:
            sub_id = uuid.UUID(submission_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid submission id")

        reviewer_id = uuid.UUID(user_id)
        if body.action == "approve":
            updated = await library_queries.approve_library_submission(
                conn, sub_id, reviewer_id, body.review_note
            )
        elif body.action == "reject":
            updated = await library_queries.reject_library_submission(
                conn, sub_id, reviewer_id, body.review_note
            )
        else:
            raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

        if not updated:
            raise HTTPException(status_code=404, detail="Submission not found or not in pending state")

    return {"id": submission_id, "status": updated["status"]}
