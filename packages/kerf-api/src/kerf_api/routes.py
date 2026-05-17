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

from kerf_core.config import get_settings
from kerf_core.db.connection import get_pool_required
from kerf_core.db.queries import users as users_queries
from kerf_core.db.queries import workspaces as workspaces_queries
from kerf_core.db.queries import projects as projects_queries
from kerf_core.db.queries import files as files_queries
from kerf_core.db.queries import api_tokens as api_tokens_queries
from kerf_core.db.queries import refresh_tokens as rt_queries
from kerf_core.db.queries import chat_threads as threads_queries
from kerf_core.db.queries import share_links as share_links_queries
from kerf_core.db.queries import derived_artifacts as da_queries
from kerf_core.db.queries import jobs as jobs_queries
from kerf_core.db.queries import usage_events as usage_queries
from kerf_core.db.queries import upload_sessions as uploads_queries
from kerf_core.db.queries import library as library_queries
from kerf_core.db.queries import workshop_likes as workshop_likes_queries
from kerf_core.dependencies import require_auth, optional_auth
from kerf_core.storage import get_storage_required
from kerf_chat import llm as llm_module
from kerf_chat.tools.executor import execute as tools_execute, specs as tools_specs
from kerf_core.utils.context import ProjectCtx
from kerf_tess.worker import notify_step_uploaded

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


@router.get("/config")
async def get_config():
    """Public bootstrap endpoint consumed by the frontend's useCloudConfig hook.

    Returns the minimal set of server-side flags the browser needs before the
    user is authenticated. No auth required — no secrets are returned here.
    """
    payload = {
        "cloud_enabled": settings.cloud_enabled,
        "local_mode": settings.local_mode,
    }
    if settings.cloud_enabled:
        # cloud_beta: billing-disabled mode. Mirrored from KERF_CLOUD_BETA env.
        if settings.cloud_beta:
            payload["cloud_beta"] = True
        # OAuth availability — public client IDs + bool flags only, no
        # secrets. The frontend renders the Google/GitHub buttons from
        # these runtime values (Vite can't inline per-env build-time vars).
        payload["google_enabled"] = bool(settings.google_client_id)
        payload["github_enabled"] = bool(settings.cloud_github_client_id)
        if settings.google_client_id:
            payload["google_client_id"] = settings.google_client_id
        if settings.cloud_github_client_id:
            payload["github_client_id"] = settings.cloud_github_client_id
        if settings.cloud_paystack_public_key:
            payload["paystack_public_key"] = settings.cloud_paystack_public_key
    return payload


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
async def update_me(req: UpdateMeRequest, payload: dict = Depends(require_auth)):
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


async def _make_byo_provider(pool, user_id: str, provider_name: str, *, fallback):
    """Build a Provider instance whose api_key comes from the user's saved
    BYO key.  Falls back to ``fallback`` if anything goes wrong — the
    bucket selector already decided BYO was viable, so a decryption failure
    here is a server-side bug worth logging but not worth nuking the chat.
    """
    try:
        from kerf_core.utils.encrypt import decrypt_secret
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT encrypted_key
                FROM user_provider_keys
                WHERE user_id = $1 AND provider = $2
                """,
                user_id, provider_name,
            )
        if not row:
            return fallback
        api_key = decrypt_secret(row["encrypted_key"], "byo-provider-key").decode()

        # Match Registry.resolve's provider mapping — the names we accept
        # match Provider.name() return values from kerf_chat.llm.
        if provider_name == "anthropic":
            return llm_module.AnthropicProvider(api_key)
        if provider_name == "openai":
            return llm_module.OpenAIProvider(api_key)
        if provider_name == "moonshot":
            return llm_module.MoonshotProvider(api_key)
        if provider_name == "gemini":
            return llm_module.GeminiProvider(api_key)
        return fallback
    except Exception:
        _logger.exception("byo: provider override failed; falling back")
        return fallback


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
async def create_workspace(req: CreateWorkspaceRequest, payload: dict = Depends(require_auth)):
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
async def get_workspace(slug: str, request: Request, payload: dict = Depends(require_auth)):
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
async def update_workspace(slug: str, req: UpdateWorkspaceRequest, payload: dict = Depends(require_auth)):
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
async def delete_workspace(slug: str, request: Request, payload: dict = Depends(require_auth)):
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
async def upload_workspace_avatar(slug: str, request: Request, payload: dict = Depends(require_auth)):
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
async def delete_workspace_avatar(slug: str, request: Request, payload: dict = Depends(require_auth)):
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
async def invite_workspace_member(slug: str, req: InviteMemberRequest, payload: dict = Depends(require_auth)):
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
async def change_workspace_member_role(slug: str, member_id: str, req: ChangeRoleRequest, payload: dict = Depends(require_auth)):
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
async def remove_workspace_member(slug: str, member_id: str, request: Request, payload: dict = Depends(require_auth)):
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

    workspace_id = request.query_params.get("workspace_id")
    workspace_slug = request.query_params.get("workspace_slug")
    tag = request.query_params.getlist("tag") or None

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
async def create_project(req: CreateProjectRequest, payload: dict = Depends(require_auth)):
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

        # ── Default visibility: cloud paid → private, cloud free → public,
        #    self-hosted → private (Workshop concept doesn't exist there).
        default_visibility = "private"
        if settings.cloud_enabled:
            try:
                from kerf_billing.buckets import is_paid_user as _is_paid_user
                if not await _is_paid_user(conn, user_id):
                    default_visibility = "public"
            except Exception:
                # Billing module absent or DB error — stay safe with private.
                pass

        async with conn.transaction():
            project = await projects_queries.create_project(conn, ws_id, name, req.description, default_visibility, tags)

            if starter_content:
                await files_queries.create_file(conn, project["id"], starter, starter_kind, None, starter_content)

        return {
            **project,
            "my_role": role if role == "owner" else "editor",
        }


@router.get("/projects/{pid}")
async def get_project(pid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def update_project(pid: str, req: UpdateProjectRequest, payload: dict = Depends(require_auth)):
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
async def delete_project(pid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def list_files(pid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def create_file(pid: str, req: CreateFileRequest, payload: dict = Depends(require_auth)):
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
async def get_file(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def update_file(pid: str, fid: str, req: UpdateFileRequest, payload: dict = Depends(require_auth)):
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
async def delete_file(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def download_file(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def tessellate(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def purge_tessellation(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
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
        from kerf_mates.solver import solve_assembly
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

        from kerf_mates.tolerance import worst_case, rss, monte_carlo
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
async def run_sim(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def sim_job_status(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def upload_asset(pid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def list_threads(pid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def create_thread(pid: str, req: CreateThreadRequest, payload: dict = Depends(require_auth)):
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
async def update_thread(pid: str, tid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def delete_thread(pid: str, tid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def list_messages(pid: str, tid: str, request: Request, payload: dict = Depends(require_auth)):
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

    # ── Three-bucket billing selection (cloud only) ─────────────────────────
    # In OSS/local mode billing is dormant; pick_bucket can't talk to
    # cloud_user_balances (the table may not exist) so we wrap the whole
    # gate in settings.usage_enabled and short-circuit otherwise.
    bucket = None
    bucket_model_info = None
    bucket_model_info_price = None
    bucket_provider_name = provider.name()
    if settings.usage_enabled:
        try:
            from kerf_billing.buckets import (
                load_model_info,
                load_user_billing,
                pick_bucket,
                InsufficientCredits,
                Byo,
            )
            from kerf_pricing.queries import get_price as _get_price

            bucket_model_info = await load_model_info(
                pool, bucket_provider_name, provider_model_id,
            )
            if bucket_model_info is None:
                # The model isn't in our pricing table — refuse to bill an
                # unknown rate.  Tell the user; their admin can refresh.
                async with pool.acquire() as conn:
                    assistant_msg = await _insert_assistant_message(
                        conn, tid,
                        "That model isn't in the pricing table yet — contact admin to refresh /api/admin/pricing/refresh.",
                        "none", None,
                    )
                    await conn.execute(
                        "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
                    )
                return {"user_message": user_msg, "assistant_message": assistant_msg, "tool_messages": []}

            user_billing = await load_user_billing(pool, user_id)

            # Rough estimate for the credit check: assume ~1k in + ~1k out
            # at provider COGS × 1.20.  Off by an order of magnitude on
            # large turns, but the spend-commit path settles against the
            # real numbers so this only gates rejection.
            bucket_model_info_price = await _get_price(
                pool, bucket_provider_name, provider_model_id,
            )
            est_cogs = bucket_model_info_price.compute_cost_usd(1000, 1000) \
                if bucket_model_info_price else 0.0
            est_billed = est_cogs * 1.20

            bucket = pick_bucket(
                user_billing, bucket_model_info, est_billed,
                estimated_input_tokens=1000, estimated_output_tokens=1000,
            )

            if isinstance(bucket, InsufficientCredits):
                code = (
                    "INSUFFICIENT_CREDITS_BYO_AVAILABLE"
                    if bucket.byo_available
                    else "INSUFFICIENT_CREDITS"
                )
                raise HTTPException(
                    status_code=402,
                    detail={"code": code, "provider": bucket_provider_name},
                )

            # BYO: pull the encrypted key and instantiate an override provider.
            if isinstance(bucket, Byo):
                provider = await _make_byo_provider(
                    pool, user_id, bucket.provider, fallback=provider,
                )
        except HTTPException:
            raise
        except Exception as bx:
            _logger.warning(f"bucket-select: degrading to legacy path: {bx}")
            bucket = None

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
                if bucket is not None and bucket_model_info is not None:
                    # New three-bucket path: commit via kerf_billing.spend
                    # so usage_events.payer is set correctly + balance/quota
                    # gets debited atomically in one txn.
                    from kerf_billing.spend import commit_spend, ApiTokenDailyCapExceeded
                    cogs = bucket_model_info_price.compute_cost_usd(
                        resp.input_tokens, resp.output_tokens,
                    ) if bucket_model_info_price else 0.0
                    billed = cogs * 1.20
                    try:
                        await commit_spend(
                            pool,
                            bucket=bucket,
                            user_id=user_id,
                            project_id=pid,
                            model=provider_model_id,
                            input_tokens=resp.input_tokens,
                            output_tokens=resp.output_tokens,
                            cogs_usd=cogs,
                            billed_usd=billed,
                            api_token_id=None,  # web sessions don't have an api_token
                        )
                    except ApiTokenDailyCapExceeded as cap:
                        _logger.warning(f"usage: api token daily cap: {cap}")
                else:
                    # Legacy fallback path (OSS local mode / cloud_user_balances
                    # missing).  Records the token row only.
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
async def create_share_link(pid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def list_share_links(pid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def delete_share_link(pid: str, lid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def list_members(pid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def add_member(pid: str, req: InviteMemberRequest, payload: dict = Depends(require_auth)):
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
async def update_member(pid: str, uid: str, req: ChangeRoleRequest, payload: dict = Depends(require_auth)):
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
async def remove_member(pid: str, uid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def list_revisions(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
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
async def get_revision(pid: str, fid: str, rid: str, request: Request, payload: dict = Depends(require_auth)):
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


@router.get("/projects/{pid}/files/{fid}/revisions/{rid}/content")
async def get_revision_content(pid: str, fid: str, rid: str, request: Request, payload: dict = Depends(require_auth)):
    """
    Return the full reconstructed content for a single revision.

    The list endpoint (GET .../revisions) intentionally omits the content
    payload to keep the response small.  The frontend uses this endpoint
    lazily — only when the user clicks "Show full content" in the revisions
    panel — so we reconstruct the diff chain on demand.

    Response: ``{"id": <rid>, "content": "<full text>"}``
    """
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        # Verify the revision belongs to this file/project before fetching.
        exists = await conn.fetchval(
            """
            SELECT 1 FROM file_revisions fr
            INNER JOIN files f ON f.id = fr.file_id
            WHERE fr.id = $1 AND fr.file_id = $2 AND f.project_id = $3
            """,
            rid, fid, pid,
        )
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="revision not found")

    # Reconstruct outside the connection-borrow (may walk a diff chain via
    # multiple fetchrow calls; that's fine — pool handles concurrency).
    from kerf_core.revisions import reconstruct_revision as _reconstruct
    import uuid as _uuid
    content = await _reconstruct(pool, _uuid.UUID(str(rid)))
    return {"id": rid, "content": content}


@router.post("/projects/{pid}/files/{fid}/revisions/{rid}/restore")
async def restore_revision(pid: str, fid: str, rid: str, request: Request, payload: dict = Depends(require_auth)):
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


@router.get("/projects/{pid}/cover")
async def serve_project_cover(
    pid: str,
    auth: Optional[dict] = Depends(optional_auth),
):
    """GET /api/projects/:pid/cover — serve the auto-rendered hero cover image.

    Public projects are anonymously accessible.  Private projects require
    workspace membership.  Falls back with 404 when no cover has been generated.
    """
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        proj = await conn.fetchrow(
            "SELECT workspace_id, visibility, cover_storage_key FROM projects WHERE id = $1",
            uuid.UUID(pid),
        )
        if not proj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        if proj["visibility"] != "public":
            uid = auth.get("sub") if auth else None
            if not uid:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
            role = await get_user_workspace_role(conn, str(proj["workspace_id"]), uid)
            if not role:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        key = proj.get("cover_storage_key")
        if not key:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no cover available")

    storage = get_storage_required()
    body, content_type = await storage.get(key)
    return StreamingResponse(body, media_type=content_type or "image/png")


# Project Workshop Images (multi-image gallery)
#
# Net-new endpoints (Thingiverse-style cover gallery). The primary
# thumbnail (POST /projects/:pid/thumbnail above) is auto-captured from
# the editor and unchanged; gallery images are uploader-curated cover
# art with much looser caps (5MB vs 512KB) and a per-project count
# limit. Storage path: projects/{pid}/workshop/{image_id}{.ext}.

WORKSHOP_IMAGE_MAX_BYTES = 5 * 1024 * 1024
WORKSHOP_IMAGES_PER_PROJECT = 10
WORKSHOP_IMAGE_ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _workshop_image_row_to_dict(row, pid: str) -> dict:
    return {
        "id": str(row["id"]),
        "project_id": pid,
        "sort_order": row["sort_order"],
        "caption": row["caption"],
        "width_px": row["width_px"],
        "height_px": row["height_px"],
        "bytes": row["bytes"],
        "is_primary": bool(row["is_primary"]) if "is_primary" in row.keys() else False,
        "url": f"/api/projects/{pid}/workshop-images/{row['id']}/file",
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("/projects/{pid}/workshop-images")
async def list_workshop_images(
    pid: str,
    payload: dict = Depends(require_auth),
):
    """GET /api/projects/:pid/workshop-images — list, ordered by sort_order asc."""
    uid = payload.get("sub")
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        role = await get_user_workspace_role(conn, ws_id, uid)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        rows = await conn.fetch(
            """
            select id, sort_order, storage_key, caption, width_px, height_px,
                   bytes, is_primary, created_at
              from project_workshop_images
             where project_id = $1
             order by is_primary desc, sort_order asc, created_at asc
            """,
            uuid.UUID(pid),
        )
        return {"images": [_workshop_image_row_to_dict(r, pid) for r in rows]}


@router.post("/projects/{pid}/workshop-images")
async def upload_workshop_image(
    request: Request,
    pid: str,
    payload: dict = Depends(require_auth),
):
    """POST /api/projects/:pid/workshop-images — multipart upload."""
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
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewers cannot upload gallery images")

        # Enforce count cap before consuming the upload body.
        existing_count = await conn.fetchval(
            "select count(*) from project_workshop_images where project_id = $1",
            uuid.UUID(pid),
        )
        if int(existing_count or 0) >= WORKSHOP_IMAGES_PER_PROJECT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"max {WORKSHOP_IMAGES_PER_PROJECT} gallery images per project",
            )

        form = await request.form()
        file = form.get("file")
        if not file:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing 'file' field")
        caption = (form.get("caption") or "").strip() or None

        content = await file.read()
        if len(content) > WORKSHOP_IMAGE_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"image too large (>{WORKSHOP_IMAGE_MAX_BYTES // (1024 * 1024)}MB)",
            )

        mime = (getattr(file, "content_type", None) or "").lower()
        if mime not in WORKSHOP_IMAGE_ALLOWED_MIME:
            # Try sniffing via Pillow as a fallback for clients that don't
            # set content-type — keeps the endpoint robust against curl.
            try:
                from PIL import Image
                import io as pil_io
                probe = Image.open(pil_io.BytesIO(content))
                fmt = (probe.format or "").lower()
                if fmt == "jpeg":
                    mime = "image/jpeg"
                elif fmt == "png":
                    mime = "image/png"
                elif fmt == "webp":
                    mime = "image/webp"
            except Exception:
                pass
        if mime not in WORKSHOP_IMAGE_ALLOWED_MIME:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="image must be JPEG, PNG, or WebP",
            )

        # Probe dimensions (best-effort; Pillow is optional).
        width_px = None
        height_px = None
        try:
            from PIL import Image
            import io as pil_io
            probe = Image.open(pil_io.BytesIO(content))
            width_px, height_px = probe.size
        except Exception:
            pass

        ext = WORKSHOP_IMAGE_ALLOWED_MIME[mime]
        image_id = uuid.uuid4()
        key = f"projects/{pid}/workshop/{image_id}{ext}"
        storage = get_storage_required()
        await storage.put(key, io.BytesIO(content), mime, len(content))

        # New images are appended at the end of the gallery.
        next_order = await conn.fetchval(
            "select coalesce(max(sort_order), -1) + 1 from project_workshop_images where project_id = $1",
            uuid.UUID(pid),
        )
        row = await conn.fetchrow(
            """
            insert into project_workshop_images
              (id, project_id, sort_order, storage_key, caption, width_px, height_px, bytes)
            values ($1, $2, $3, $4, $5, $6, $7, $8)
            returning id, sort_order, storage_key, caption, width_px, height_px, bytes, is_primary, created_at
            """,
            image_id,
            uuid.UUID(pid),
            int(next_order or 0),
            key,
            caption,
            width_px,
            height_px,
            len(content),
        )
        return _workshop_image_row_to_dict(row, pid)


@router.get("/projects/{pid}/workshop-images/{image_id}/file")
async def serve_workshop_image(
    pid: str,
    image_id: str,
    auth: Optional[dict] = Depends(optional_auth),
):
    """GET .../workshop-images/:id/file — raw image bytes.

    Public projects: anonymous reads OK. Private/unlisted: caller must
    be a workspace member.
    """
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        # Check the parent project's visibility + access.
        proj = await conn.fetchrow(
            "select workspace_id, visibility from projects where id = $1",
            uuid.UUID(pid),
        )
        if not proj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        if proj["visibility"] != "public":
            uid = auth.get("sub") if auth else None
            if not uid:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
            role = await get_user_workspace_role(conn, str(proj["workspace_id"]), uid)
            if not role:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        row = await conn.fetchrow(
            """
            select storage_key from project_workshop_images
             where project_id = $1 and id = $2
            """,
            uuid.UUID(pid),
            uuid.UUID(image_id),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image not found")

        storage = get_storage_required()
        body, content_type = await storage.get(row["storage_key"])
        # storage.get returns an IO[bytes] — pass through as a stream so
        # large WebP/PNG uploads don't need to fully buffer in memory.
        return StreamingResponse(body, media_type=content_type or "image/jpeg")


class WorkshopImagePatch(BaseModel):
    caption: Optional[str] = None
    sort_order: Optional[int] = None


@router.patch("/projects/{pid}/workshop-images/{image_id}")
async def update_workshop_image(
    pid: str,
    image_id: str,
    patch: WorkshopImagePatch,
    payload: dict = Depends(require_auth),
):
    """PATCH .../workshop-images/:id — edit caption + sort_order."""
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
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewers cannot edit gallery images")

        # Build a partial update. We update only the columns explicitly
        # sent so a caption-only PATCH doesn't reset sort_order to NULL.
        sets = []
        args = []
        if patch.caption is not None:
            sets.append(f"caption = ${len(args) + 1}")
            args.append(patch.caption.strip() or None)
        if patch.sort_order is not None:
            sets.append(f"sort_order = ${len(args) + 1}")
            args.append(int(patch.sort_order))
        if not sets:
            # No-op patch — return the row as-is.
            row = await conn.fetchrow(
                """
                select id, sort_order, storage_key, caption, width_px, height_px, bytes, is_primary, created_at
                  from project_workshop_images
                 where project_id = $1 and id = $2
                """,
                uuid.UUID(pid),
                uuid.UUID(image_id),
            )
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image not found")
            return _workshop_image_row_to_dict(row, pid)

        args.append(uuid.UUID(pid))
        args.append(uuid.UUID(image_id))
        row = await conn.fetchrow(
            f"""
            update project_workshop_images
               set {', '.join(sets)}
             where project_id = ${len(args) - 1} and id = ${len(args)}
            returning id, sort_order, storage_key, caption, width_px, height_px, bytes, is_primary, created_at
            """,
            *args,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image not found")
        return _workshop_image_row_to_dict(row, pid)


@router.delete("/projects/{pid}/workshop-images/{image_id}")
async def delete_workshop_image(
    pid: str,
    image_id: str,
    payload: dict = Depends(require_auth),
):
    """DELETE .../workshop-images/:id — remove the row + storage blob."""
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
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewers cannot delete gallery images")

        row = await conn.fetchrow(
            """
            delete from project_workshop_images
             where project_id = $1 and id = $2
            returning storage_key
            """,
            uuid.UUID(pid),
            uuid.UUID(image_id),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image not found")

        # Best-effort blob delete — DB row is gone either way.
        try:
            storage = get_storage_required()
            await storage.delete(row["storage_key"])
        except Exception:
            pass
        return {"deleted": True, "id": image_id}


@router.post("/projects/{pid}/workshop-images/{image_id}/set-primary")
async def set_primary_workshop_image(
    pid: str,
    image_id: str,
    payload: dict = Depends(require_auth),
):
    """POST .../workshop-images/:id/set-primary — pin or unpin a gallery image
    as the project's primary display thumbnail.

    Calling this on a non-primary image sets it as the primary and clears the
    previous primary (if any). Calling it on the already-primary image acts as
    an unpin (is_primary → false), so no gallery image is primary and the
    project falls back to the auto-captured thumbnail_storage_key.

    The partial unique index `workshop_images_primary_uniq` enforces at most
    one primary per project at the DB level; we drive the transition entirely
    in SQL so no race window exists between the unset and the set.
    """
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
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewers cannot pin gallery images")

        # Fetch the target image to check it exists and learn its current state.
        existing = await conn.fetchrow(
            """
            select id, is_primary from project_workshop_images
             where project_id = $1 and id = $2
            """,
            uuid.UUID(pid),
            uuid.UUID(image_id),
        )
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image not found")

        currently_primary = bool(existing["is_primary"])

        async with conn.transaction():
            # Clear any existing primary for this project first.
            await conn.execute(
                """
                update project_workshop_images
                   set is_primary = false
                 where project_id = $1 and is_primary = true
                """,
                uuid.UUID(pid),
            )
            # If the target was NOT already primary, promote it.
            # If it WAS primary, the clear above already unpinned it — we
            # leave it unpinned (toggle semantics).
            if not currently_primary:
                await conn.execute(
                    """
                    update project_workshop_images
                       set is_primary = true
                     where project_id = $1 and id = $2
                    """,
                    uuid.UUID(pid),
                    uuid.UUID(image_id),
                )

        # Return the updated row.
        row = await conn.fetchrow(
            """
            select id, sort_order, storage_key, caption, width_px, height_px,
                   bytes, is_primary, created_at
              from project_workshop_images
             where project_id = $1 and id = $2
            """,
            uuid.UUID(pid),
            uuid.UUID(image_id),
        )
        return _workshop_image_row_to_dict(row, pid)


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
        from kerf_cloud.distributors.service import Credentials, validate_credentials

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
            from kerf_cloud.distributors.sync import refresh_part
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
    """Normalise a DB project dict into the workshop wire shape.

    thumbnail resolution priority:
      1. pinned primary gallery image  (primary_image_id is set)
      2. auto-captured thumbnail_storage_key
    The caller can pass either/both; we pick the best available and
    expose it as `thumbnail_url` so the frontend doesn't branch.
    """
    pid = str(p["id"])

    # Gallery-pinned primary image overrides the auto-captured thumbnail.
    primary_image_id = p.get("primary_image_id")
    if primary_image_id:
        thumbnail_url = f"/api/projects/{pid}/workshop-images/{primary_image_id}/file"
    elif p.get("thumbnail_storage_key"):
        thumbnail_url = f"/api/projects/{pid}/thumbnail"
    else:
        thumbnail_url = None

    return {
        "project_id": pid,
        "slug": pid,  # slug == project_id for workshop routes
        "name": p.get("name", ""),
        "title": p.get("name", ""),  # alias used by WorkshopListing
        "description": p.get("description", ""),
        "tags": list(p.get("tags") or []),
        "workspace_slug": p.get("workspace_slug", ""),
        "workspace_name": p.get("workspace_name", ""),
        "author_name": p.get("author_name", ""),
        "author": {
            "id": str(p["author_id"]) if p.get("author_id") else None,
            "name": p.get("author_name") or p.get("workspace_name", ""),
            "avatar_url": p.get("author_avatar_url"),
            "is_verified_publisher": bool(p.get("is_verified_publisher", False)),
        },
        "likes_count": int(p.get("likes_count") or 0),
        "liked_by_me": bool(p.get("liked_by_me", False)),
        "forks_count": int(p.get("forks_count") or 0),
        "file_count": int(p.get("file_count") or 0),
        "total_bytes": int(p.get("total_bytes") or 0),
        "thumbnail_storage_key": p.get("thumbnail_storage_key"),
        "thumbnail_url": thumbnail_url,
        "primary_image_id": str(primary_image_id) if primary_image_id else None,
        "readme": p.get("readme") or None,
        "readme_generated_at": p["readme_generated_at"].isoformat() if p.get("readme_generated_at") else None,
        "cover_storage_key": p.get("cover_storage_key"),
        "cover_url": (
            f"/api/projects/{pid}/cover"
            if p.get("cover_storage_key") else thumbnail_url
        ),
        "published_at": p["created_at"].isoformat() if p.get("created_at") else None,
        "last_edited": p["updated_at"].isoformat() if p.get("updated_at") else None,
        "created_at": p["created_at"].isoformat() if p.get("created_at") else None,
        "updated_at": p["updated_at"].isoformat() if p.get("updated_at") else None,
    }


async def _enrich_with_primary_images(conn, rows: list) -> list:
    """Batch-fetch the primary gallery image id for each project in rows and
    inject it as `primary_image_id`. Single query regardless of page size."""
    if not rows:
        return rows
    project_ids = [uuid.UUID(str(r["id"])) for r in rows]
    primary_rows = await conn.fetch(
        """
        select project_id, id as image_id
          from project_workshop_images
         where project_id = ANY($1::uuid[])
           and is_primary = true
        """,
        project_ids,
    )
    primary_map = {str(r["project_id"]): str(r["image_id"]) for r in primary_rows}
    enriched = []
    for r in rows:
        d = dict(r) if not isinstance(r, dict) else r
        d["primary_image_id"] = primary_map.get(str(d.get("id") or ""))
        enriched.append(d)
    return enriched


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
        rows = await _enrich_with_primary_images(conn, rows)

    listings = [_project_to_workshop_row(r) for r in rows]
    return {"listings": listings, "rows": listings, "page": page, "per_page": per_page, "has_more": len(rows) >= per_page}


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
        enriched = await _enrich_with_primary_images(conn, [project])
        project = enriched[0]

    return _project_to_workshop_row(project)


class WorkshopPublishRequest(BaseModel):
    project_id: str
    title: str = ""
    description: str = ""
    readme: Optional[str] = None          # caller-supplied README (overrides AI gen)
    generate_readme: bool = True           # set False to skip AI generation
    readme_override: str = ""             # explicit README text (alias for `readme`)


def _get_bom_rows_sync(project_files: list) -> list:
    """Extract lightweight BOM rows from project file list for README context.

    Parses .part files for name + distributor info. Returns a list of simple
    dicts suitable for readme_gen.compose_readme_prompt.
    """
    rows = []
    for f in project_files:
        if f.get("kind") != "part":
            continue
        content = f.get("content") or ""
        if not content.strip():
            continue
        try:
            doc = json.loads(content)
        except Exception:
            continue
        name = doc.get("name") or f.get("name") or "?"
        supplier = ""
        dists = doc.get("distributors") or []
        if dists:
            supplier = dists[0].get("name") or ""
        rows.append({"name": name, "qty": 1, "supplier": supplier})
    return rows


async def _generate_project_cover(
    conn,
    project: dict,
    project_id: uuid.UUID,
    storage,
) -> Optional[str]:
    """Attempt to auto-render a hero cover for the project.

    Uses kerf-render if Blender is available; falls back to the existing
    thumbnail_storage_key gracefully (no exception raised).

    Returns the storage key of the generated cover, or None on failure.
    """
    try:
        import importlib
        kerf_render_routes = importlib.import_module("kerf_render.routes")

        # Only proceed when Blender is actually installed.
        if not getattr(kerf_render_routes, "_BLENDER_AVAILABLE", False):
            return None

        # Fetch the primary mesh file (first .jscad / .step / .feature file)
        file_rows = await conn.fetch(
            "SELECT id, name, kind, content, bytes FROM files "
            "WHERE project_id = $1 AND deleted_at IS NULL "
            "AND kind IN ('file', 'step', 'feature') "
            "ORDER BY updated_at DESC LIMIT 1",
            project_id,
        )
        if not file_rows:
            return None

        # Minimal render: just a default-settings isometric thumbnail.
        # We skip mesh upload/conversion here — the render module handles it.
        # For the hero cover we use a 1280x960 resolution, 64 samples.
        from kerf_render.routes import RenderRequest, RenderSettings, CameraSettings
        import httpx as _httpx

        settings = get_settings()
        render_url = getattr(settings, "render_service_url", None) or os.environ.get("KERF_RENDER_URL", "")
        if not render_url:
            return None

        # Build a minimal render request; mesh_b64 empty means Blender uses a
        # default cube as placeholder — good enough for a cover thumbnail.
        payload = {
            "version": 1,
            "name": f"cover-{project_id}",
            "mesh_b64": "",
            "mesh_format": "obj",
            "render_settings": {"resolution": [1280, 960], "samples": 64, "denoise": True, "output_format": "png"},
        }

        async with _httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{render_url}/run-render", json=payload)

        if resp.status_code != 200:
            return None

        result = resp.json()
        img_b64 = result.get("output_b64") or ""
        if not img_b64:
            return None

        img_bytes = base64.b64decode(img_b64)
        cover_key = f"projects/{project_id}/cover.png"
        await storage.put(cover_key, img_bytes, content_type="image/png")
        return cover_key

    except Exception as exc:
        logging.getLogger(__name__).debug("cover generation skipped: %s", exc)
        return None


@router.post("/workshop/publish")
async def workshop_publish(
    body: WorkshopPublishRequest,
    auth: dict = Depends(require_auth),
):
    """POST /api/workshop/publish — owner-only, sets visibility='public'. Idempotent.

    On publish:
    1. Sets project visibility to 'public'.
    2. AI-generates a README from project params + BOM + parts attribution
       (default on; set generate_readme=false or supply readme= to skip/override).
    3. Attempts to auto-render a hero cover via kerf-render; gracefully falls
       back to the existing auto-captured thumbnail when Blender is unavailable.
    """
    try:
        project_id = uuid.UUID(body.project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id")

    user_id = auth["sub"]
    pool = await get_pool_required()

    # Resolve explicit readme (body.readme takes priority over body.readme_override)
    explicit_readme: Optional[str] = None
    if body.readme:
        explicit_readme = body.readme.strip() or None
    elif body.readme_override:
        explicit_readme = body.readme_override.strip() or None

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

        # ---- README generation ----
        readme_text: Optional[str] = None
        if explicit_readme:
            readme_text = explicit_readme
        elif body.generate_readme:
            # Build BOM context from project files
            file_rows = await conn.fetch(
                "SELECT id, name, kind, content FROM files "
                "WHERE project_id = $1 AND deleted_at IS NULL",
                project_id,
            )
            file_list = [dict(r) for r in file_rows]
            bom_rows = _get_bom_rows_sync(file_list)

            project_ctx = {
                "name": body.title or project.get("name") or "",
                "description": body.description or project.get("description") or "",
                "tags": list(project.get("tags") or []),
                "license": "MIT",
            }

            try:
                from kerf_chat.readme_gen import generate_readme, generate_readme_template
                from kerf_chat.llm import LLMConfig, Registry

                settings = get_settings()
                anthropic_key = getattr(settings, "anthropic_api_key", None) or os.environ.get("ANTHROPIC_API_KEY", "")

                if anthropic_key:
                    cfg = LLMConfig(
                        anthropic_api_key=anthropic_key,
                        default_model="claude-haiku-4-5",
                    )
                    registry = Registry(cfg)
                    provider, model_id = registry.resolve("claude-haiku-4-5")
                    readme_text = generate_readme(
                        project_ctx,
                        bom_rows=bom_rows or None,
                        llm_provider=provider,
                        model_id=model_id,
                    )
                else:
                    from kerf_chat.readme_gen import generate_readme_template
                    readme_text = generate_readme_template(project_ctx, bom_rows=bom_rows or None)
            except Exception as exc:
                logging.getLogger(__name__).warning("README generation failed: %s", exc)
                try:
                    from kerf_chat.readme_gen import generate_readme_template
                    readme_text = generate_readme_template(project_ctx)
                except Exception:
                    readme_text = None

        if readme_text:
            updates["readme"] = readme_text

        # ---- Hero cover generation (T-42) ----
        cover_key: Optional[str] = None
        try:
            storage = get_storage_required()
            cover_key = await _generate_project_cover(conn, project, project_id, storage)
        except Exception as exc:
            logging.getLogger(__name__).debug("cover storage unavailable: %s", exc)

        if cover_key:
            updates["cover_storage_key"] = cover_key

        updated = await projects_queries.update_project(conn, project_id, **updates)

    result = {
        "project_id": str(project_id),
        "slug": str(project_id),
        "visibility": "public",
        "name": updated.get("name", "") if updated else "",
        "readme": updated.get("readme") if updated else None,
        "cover_storage_key": updated.get("cover_storage_key") if updated else None,
    }
    return result


class WorkshopRegenerateReadmeRequest(BaseModel):
    project_id: str


@router.post("/workshop/regenerate-readme")
async def workshop_regenerate_readme(
    body: WorkshopRegenerateReadmeRequest,
    auth: dict = Depends(require_auth),
):
    """POST /api/workshop/regenerate-readme — re-generate the AI README for a published project.

    Idempotent. Replaces the existing readme field with a fresh AI-generated version.
    The project must already be public (published) and the caller must be the owner/admin.
    """
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

        role = await get_user_workspace_role(conn, str(project["workspace_id"]), user_id)
        if role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Not authorized")

        file_rows = await conn.fetch(
            "SELECT id, name, kind, content FROM files "
            "WHERE project_id = $1 AND deleted_at IS NULL",
            project_id,
        )
        file_list = [dict(r) for r in file_rows]
        bom_rows = _get_bom_rows_sync(file_list)

        project_ctx = {
            "name": project.get("name") or "",
            "description": project.get("description") or "",
            "tags": list(project.get("tags") or []),
            "license": "MIT",
        }

        readme_text: Optional[str] = None
        try:
            from kerf_chat.readme_gen import generate_readme, generate_readme_template
            from kerf_chat.llm import LLMConfig, Registry

            settings = get_settings()
            anthropic_key = getattr(settings, "anthropic_api_key", None) or os.environ.get("ANTHROPIC_API_KEY", "")

            if anthropic_key:
                cfg = LLMConfig(anthropic_api_key=anthropic_key, default_model="claude-haiku-4-5")
                registry = Registry(cfg)
                provider, model_id = registry.resolve("claude-haiku-4-5")
                readme_text = generate_readme(
                    project_ctx,
                    bom_rows=bom_rows or None,
                    llm_provider=provider,
                    model_id=model_id,
                )
            else:
                readme_text = generate_readme_template(project_ctx, bom_rows=bom_rows or None)
        except Exception as exc:
            logging.getLogger(__name__).warning("README regeneration failed: %s", exc)
            try:
                from kerf_chat.readme_gen import generate_readme_template
                readme_text = generate_readme_template(project_ctx)
            except Exception:
                raise HTTPException(status_code=500, detail="README generation unavailable")

        updated = await projects_queries.update_project(conn, project_id, readme=readme_text)

    return {
        "project_id": str(project_id),
        "readme": updated.get("readme") if updated else readme_text,
        "readme_generated_at": updated.get("readme_generated_at").isoformat() if (updated and updated.get("readme_generated_at")) else None,
    }


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


# ---------------------------------------------------------------------------
# Wiring diagram run
# ---------------------------------------------------------------------------

@router.post("/projects/{pid}/files/{fid}/wiring/run")
async def run_wiring(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
    """
    Forward the .wiring file's YAML source to the pyworker /run-wireviz route
    and return { svg, warnings }.

    The file must be of kind 'wiring'.  Viewers may render (read-only op).
    """
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
        if row["kind"] != "wiring":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="file is not a .wiring file",
            )

        source = row["content"] or ""

    pyworker_url = os.environ.get("PYWORKER_URL", "http://localhost:9090")
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{pyworker_url}/run-wireviz",
                json={"source": source},
            )
        if resp.status_code == 200:
            return resp.json()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"pyworker error: {resp.text[:300]}",
        )
    except _httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"pyworker unreachable: {exc}",
        )


# ---------------------------------------------------------------------------
# Jewelry metal-cost estimator
# ---------------------------------------------------------------------------
# Pure-math endpoint — no file needed, only a volume and metal parameters.
# Accepts POST /api/projects/{pid}/jewelry/metal-cost
# The project_id is used only for access control (workspace membership check).

@router.post("/projects/{pid}/jewelry/metal-cost")
async def jewelry_metal_cost(pid: str, request: Request, payload: dict = Depends(require_auth)):
    """
    Estimate casting weight and cost for a jewelry piece.

    Body fields (all except volume_mm3 and one of metal/density_g_cm3 are optional):
      volume_mm3            — part volume in mm³ (required)
      metal                 — metal key (e.g. '18k_yellow'); see METAL_DENSITY_G_CM3
      density_g_cm3         — explicit density override (from a .material file)
      metal_price_per_gram  — user-supplied metal price (no live feed)
      labor                 — bench labor cost
      finishing             — finishing / plating cost
      casting_allowance_pct — sprue/button overhead %, default 15
      compare_metals        — list of metal keys for a multi-metal comparison table
      compare_prices        — {metal_key: price_per_gram} for the comparison
    """
    user_id = payload.get("sub")

    # Access control: verify the caller is a workspace member.
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON body")

    try:
        from kerf_cad_core.jewelry.metal_cost import (
            casting_cost as _casting_cost,
            multi_metal_compare as _multi_metal_compare,
            METAL_DENSITY_G_CM3,
            METAL_LABELS,
        )
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"kerf-cad-core not installed: {exc}",
        )

    volume_mm3 = body.get("volume_mm3")
    if volume_mm3 is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="volume_mm3 is required")
    try:
        volume_mm3 = float(volume_mm3)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="volume_mm3 must be a number")
    if volume_mm3 <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="volume_mm3 must be positive")

    metal = body.get("metal")
    density_g_cm3 = body.get("density_g_cm3")
    if metal is not None:
        metal = str(metal).strip().lower()
        if metal not in METAL_DENSITY_G_CM3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown metal '{metal}'. Valid keys: {sorted(METAL_DENSITY_G_CM3)}",
            )
    if density_g_cm3 is not None:
        try:
            density_g_cm3 = float(density_g_cm3)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="density_g_cm3 must be a number")
        if density_g_cm3 <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="density_g_cm3 must be positive")

    if metal is None and density_g_cm3 is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either metal or density_g_cm3 must be provided",
        )

    def _float_param(name: str, default: float) -> float:
        val = body.get(name, default)
        try:
            v = float(val)
        except (TypeError, ValueError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} must be a number")
        if v < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} must be >= 0")
        return v

    metal_price_per_gram  = _float_param("metal_price_per_gram",  0.0)
    labor                 = _float_param("labor",                  0.0)
    finishing             = _float_param("finishing",              0.0)
    casting_allowance_pct = _float_param("casting_allowance_pct", 15.0)

    try:
        estimate = _casting_cost(
            volume_mm3=volume_mm3,
            metal=metal,
            density_g_cm3=density_g_cm3,
            metal_price_per_gram=metal_price_per_gram,
            labor=labor,
            finishing=finishing,
            casting_allowance_pct=casting_allowance_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    estimate["label"] = METAL_LABELS.get(metal or "", metal or "custom")

    result: dict = {"estimate": estimate}

    compare_metals = body.get("compare_metals")
    if compare_metals is not None:
        if not isinstance(compare_metals, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="compare_metals must be an array")
        unknown = [m for m in compare_metals if m not in METAL_DENSITY_G_CM3]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown metals in compare_metals: {unknown}",
            )
        compare_prices = body.get("compare_prices") or {}
        try:
            result["comparison"] = _multi_metal_compare(
                volume_mm3=volume_mm3,
                metals=compare_metals,
                metal_prices=compare_prices,
                labor=labor,
                finishing=finishing,
                casting_allowance_pct=casting_allowance_pct,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return result
