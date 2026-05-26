import re
import secrets
import hashlib
import hmac
import base64
import bcrypt
import json
import logging
import os
import asyncio
import time
import uuid
import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Any

import asyncpg
import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Cookie, UploadFile, Form, Query
from fastapi.responses import StreamingResponse, RedirectResponse
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
from kerf_core.dependencies import require_auth, optional_auth, rate_limit
from kerf_core.storage import get_storage_required
from kerf_core.storage.materialize import blob_storage_key
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
    # Use bcrypt (same algorithm as kerf-auth) — pepper mixed in before hashing.
    pepper = settings.password_pepper
    peppered = (password + pepper).encode("utf-8")
    return bcrypt.hashpw(peppered, bcrypt.gensalt()).decode("utf-8")


def check_password(stored_hash: str, password: str) -> bool:
    if not stored_hash:
        return False
    pepper = settings.password_pepper
    peppered = (password + pepper).encode("utf-8")
    try:
        return bcrypt.checkpw(peppered, stored_hash.encode("utf-8"))
    except ValueError:
        return False


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


def workspace_member_to_response(m: dict) -> dict:
    """Serialize a workspace_members⋈users row for the members UI.

    NOT user_to_response: these rows have `user_id` (not `id`) and no
    account_role/is_system, so user_to_response raised KeyError → the
    workspace-settings page 500'd. Shape matches WorkspaceMembers.jsx:
    m.user_id, m.role, m.user.{name,email,avatar_url}.
    """
    return {
        "user_id": str(m["user_id"]),
        "role": m.get("role"),
        "user": {
            "id": str(m["user_id"]),
            "name": m.get("name") or "",
            "email": m.get("email") or "",
            "avatar_url": m.get("avatar_url") or "",
        },
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
    # Dynamic: the registry exposes the model CATALOG filtered to the
    # providers whose API key is actually configured (anthropic / openai
    # / moonshot / gemini). So adding an OpenAI/Gemini key makes those
    # models appear without code changes. (Was a hard-coded
    # Anthropic-only list — that's why only Anthropic showed.)
    reg = _get_llm_registry()
    models = [
        {
            "id": m["id"],
            "name": m.get("label") or m["id"],
            "label": m.get("label") or m["id"],
            "provider": m.get("provider"),
            "context_window": m.get("context_window"),
        }
        for m in reg.available()
    ]
    if not models:
        # No provider keys configured at all — keep the dropdown
        # non-empty; resolve() still errors gracefully if picked.
        models = [{
            "id": reg.default(), "name": reg.default(),
            "label": reg.default(), "provider": "anthropic",
        }]
    return {"models": models}


# ── BYO provider-key management (R13, T-402b) ────────────────────────────────

_BYO_SUPPORTED_PROVIDERS = frozenset({"anthropic", "openai", "moonshot", "gemini"})


class SaveProviderKeyRequest(BaseModel):
    provider: str
    api_key: str


async def _validate_provider_key(provider: str, api_key: str) -> None:
    """Make a minimal live call to *provider* using *api_key*.

    Raises HTTPException(422) with detail="provider_key_invalid" on any
    auth failure.  Raises HTTPException(422) with
    detail="provider_key_validation_failed" on network/server errors so the
    caller can surface a clean message either way.
    """
    try:
        if provider == "anthropic":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
            if resp.status_code in (401, 403):
                raise HTTPException(status_code=422, detail="provider_key_invalid")
            if resp.status_code >= 400 and resp.status_code not in (529, 500, 503):
                # Non-auth error that looks like a bad key (e.g. 400 with wrong format)
                raise HTTPException(status_code=422, detail="provider_key_invalid")

        elif provider == "openai":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            if resp.status_code in (401, 403):
                raise HTTPException(status_code=422, detail="provider_key_invalid")
            if resp.status_code >= 400 and resp.status_code not in (529, 500, 503):
                raise HTTPException(status_code=422, detail="provider_key_invalid")

        elif provider == "moonshot":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.moonshot.cn/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            if resp.status_code in (401, 403):
                raise HTTPException(status_code=422, detail="provider_key_invalid")
            if resp.status_code >= 400 and resp.status_code not in (529, 500, 503):
                raise HTTPException(status_code=422, detail="provider_key_invalid")

        elif provider == "gemini":
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                )
            if resp.status_code in (400, 401, 403):
                raise HTTPException(status_code=422, detail="provider_key_invalid")
            if resp.status_code >= 400 and resp.status_code not in (500, 503):
                raise HTTPException(status_code=422, detail="provider_key_invalid")

        else:
            raise HTTPException(status_code=422, detail="provider_key_invalid")

    except HTTPException:
        raise
    except Exception:
        _logger.exception("provider_key_validation: network error for provider=%s", provider)
        raise HTTPException(status_code=422, detail="provider_key_validation_failed")


@router.post("/provider-keys", status_code=200)
async def save_provider_key(
    req: SaveProviderKeyRequest,
    payload: dict = Depends(require_auth),
):
    """POST /api/provider-keys — validate + save a BYO provider API key.

    Validates the key by making a minimal live call to the provider.
    On success, encrypts and upserts into ``user_provider_keys``.
    On validation failure, returns 422 with ``detail="provider_key_invalid"``.
    """
    user_id = payload.get("sub")
    provider = req.provider.strip().lower()

    if provider not in _BYO_SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=422,
            detail="provider_key_invalid",
        )

    api_key = req.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=422, detail="provider_key_invalid")

    # Validate key against the live provider before storing.
    await _validate_provider_key(provider, api_key)

    # Encrypt and upsert.
    from kerf_core.utils.encrypt import encrypt_secret
    encrypted = encrypt_secret(api_key.encode(), "byo-provider-key")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_provider_keys (user_id, provider, encrypted_key)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, provider)
            DO UPDATE SET encrypted_key = EXCLUDED.encrypted_key,
                          created_at    = now()
            """,
            user_id, provider, encrypted,
        )

    return {"provider": provider, "saved": True}


@router.delete("/provider-keys/{provider}", status_code=200)
async def delete_provider_key(
    provider: str,
    payload: dict = Depends(require_auth),
):
    """DELETE /api/provider-keys/:provider — remove a BYO provider key."""
    user_id = payload.get("sub")
    provider = provider.strip().lower()

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM user_provider_keys WHERE user_id = $1 AND provider = $2",
            user_id, provider,
        )

    # asyncpg execute returns a command tag string like "DELETE 1"
    deleted = result.split()[-1] if result else "0"
    if deleted == "0":
        raise HTTPException(status_code=404, detail="provider_key_not_found")

    return {"provider": provider, "deleted": True}


# ─────────────────────────────────────────────────────────────────────────────

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

        # Resolve the project's workspace — share_links.project_id is not a workspace_id
        ws_row = await conn.fetchrow(
            "SELECT workspace_id FROM projects WHERE id = $1",
            row["project_id"],
        )
        if not ws_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        ws_id = str(ws_row["workspace_id"])

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
    # ModuleNotFoundError on a provider SDK dependency — most common cause
    # is a missing pip entry. Surface this concretely so the next E2E
    # probe doesn't have to SSH into the box to find it.
    if "modulenotfounderror" in type(err).__name__.lower() or "no module named" in msg:
        return f"The {provider_name} provider's SDK is not installed on the server (missing pip dependency)."
    # Last-resort: include the exception class name + a short fragment of
    # the message so operators can grep logs. Don't leak internal stack
    # frames — just a labelled tail.
    detail = str(err).strip().splitlines()[-1] if str(err).strip() else ""
    if detail:
        return f"The model returned an error ({type(err).__name__}: {detail[:160]}). Try again or pick a different model."
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
    BYO key.

    R12: on any failure (missing row, decryption error, unsupported provider)
    we raise HTTP 402 with ``detail="byo_key_unavailable"`` rather than
    silently falling back to Kerf's server key.  Falling back would bill $0
    (bucket=Byo) while using Kerf's API key — Kerf eats the provider cost.
    The ``fallback`` parameter is kept for signature compatibility but is
    never used; callers should expect a possible 402.
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
            _logger.warning("byo: no key row for user_id=%s provider=%s", user_id, provider_name)
            raise HTTPException(status_code=402, detail="byo_key_unavailable")
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
        # Unsupported provider name — refuse rather than fall back.
        _logger.warning("byo: unsupported provider=%s for user_id=%s", provider_name, user_id)
        raise HTTPException(status_code=402, detail="byo_key_unavailable")
    except HTTPException:
        raise
    except Exception:
        _logger.exception("byo: provider override failed — raising 402 (not falling back)")
        raise HTTPException(status_code=402, detail="byo_key_unavailable")


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
            "members": [workspace_member_to_response(m) for m in members],
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


class AcceptInviteRequest(BaseModel):
    token: str


@router.post("/workspaces/accept")
async def accept_workspace_invite(req: AcceptInviteRequest, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")

    if not req.token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token is required")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT id, workspace_id, email, role FROM workspace_invites WHERE token = $1",
                req.token,
            )
            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invite not found")

            # Email-binding: the invite is bound to a specific invitee email.
            # Verify the authenticated user's email matches the invite's email.
            user_row = await conn.fetchrow(
                "SELECT email FROM users WHERE id = $1", uuid.UUID(user_id)
            )
            if not user_row or user_row["email"].lower() != row["email"].lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="invite is not for your account",
                )

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
            # Frontend (ProjectCard.isOwner / role badge) consumes my_role,
            # not the raw workspace-member column name.
            p["my_role"] = p.pop("role", None)
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


DEFAULT_CIRCUIT = '''import { Circuit } from "tscircuit"

// Kerf: default export is a JSX element OR a Circuit instance. The editor
// renders the schematic, PCB, and 3D views in their respective tabs.
export default (
  <board width="20mm" height="20mm">
    <resistor name="R1" resistance="10k" footprint="0402" pcbX={-5} pcbY={0} schX={-3} />
    <resistor name="R2" resistance="10k" footprint="0402" pcbX={0}  pcbY={0} schX={0}  />
    <resistor name="R3" resistance="10k" footprint="0402" pcbX={5}  pcbY={0} schX={3}  />
    <trace from=".R1 .pin2" to=".R2 .pin1" />
    <trace from=".R2 .pin2" to=".R3 .pin1" />
  </board>
)
'''

DEFAULT_DRAWING = '''{
  "frame": {
    "size": "A3",
    "orientation": "landscape",
    "title": "Untitled Drawing"
  },
  "views": [],
  "dimensions": [],
  "annotations": []
}'''

DEFAULT_STARTER = "jscad"

# Project starter catalog: starter id -> (filename, file kind, seed content).
# One coherent scaffold per project type, mirrored on the frontend by
# src/lib/projectTags.js STARTER_OPTIONS (kept in lockstep — see
# tests/test_project_starters.py). 2D/feature kinds whose canonical seed is
# computed by a JS serializer (sketch/part) are intentionally NOT project
# starters; those are created in-project via the FileTree "+ New" menu with
# their exact seeds. "blank" seeds nothing. Every kind here must be in the
# FILE_KINDS allow-list.
STARTER_SEEDS: dict[str, tuple[str, str, str]] = {
    "jscad":    ("main.jscad",        "script",   default_jscad),
    "assembly": ("main.assembly",     "assembly", '{"components":[]}'),
    "feature":  ("main.feature",      "feature",  '{"features":[]}'),
    "drawing":  ("main.drawing",      "drawing",  DEFAULT_DRAWING),
    "circuit":  ("main.circuit.tsx",  "circuit",  DEFAULT_CIRCUIT),
    "blank":    ("",                  "file",     ""),
}


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

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        # No explicit workspace? Resolve the caller's default workspace
        # (self-healing if somehow absent) instead of 400. The server is
        # the authority on workspace membership, so forcing the client to
        # echo an id back was fragile coupling: a transient client-side
        # workspace-load failure (cold autoscaled machine / token race
        # right after OAuth) would otherwise make project creation
        # permanently impossible for the session. This is the root cause
        # of the recurring "workspace_id or workspace_slug required".
        if not ws_id:
            default_ws, exists = await get_default_workspace(conn, user_id)
            if not exists:
                urow = await conn.fetchrow(
                    "SELECT name, email FROM users WHERE id = $1", user_id
                )
                display = (urow["name"].strip() if urow and urow["name"] else "")
                if not display:
                    email = urow["email"] if urow and urow["email"] else ""
                    at = email.find("@")
                    display = email[:at] if at > 0 else "My"
                default_ws = await create_personal_workspace(conn, user_id, display)
            if default_ws:
                ws_id = str(default_ws["id"])

        if not ws_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="no workspace available for user",
            )

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")

        tags = list(set(t.strip() for t in req.tags if t.strip()))

        starter = req.starter.strip() if req.starter else DEFAULT_STARTER
        starter_name, starter_kind, starter_content = STARTER_SEEDS.get(
            starter, STARTER_SEEDS[DEFAULT_STARTER]
        )

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
            project = await projects_queries.create_project(
                conn, ws_id, name, req.description, default_visibility, tags,
                created_by=payload.get("sub"),
            )

            if starter_name and starter_content:
                await files_queries.create_file(
                    conn, project["id"], starter_name, starter_kind, None, starter_content,
                    created_by=payload.get("sub"),
                )

    # Auto-init cloud git repo for every new project (cloud only).
    # Failure is non-fatal: the user can always retry via the git panel.
    if settings.cloud_enabled:
        try:
            from kerf_cloud.routes import ensure_git_repo
            await ensure_git_repo(pool, str(project["id"]))
        except Exception as _git_exc:
            _logger.warning(f"auto git init for project {project['id']}: {_git_exc}")

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
    logger = logging.getLogger(__name__)

    pool = await get_pool_required()

    # ── Phase 1: auth + collect storage keys BEFORE deleting rows ──────────
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT workspace_id FROM projects WHERE id = $1", pid)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        ws_id = str(row["workspace_id"])
        role = await get_user_workspace_role(conn, ws_id, user_id)
        if role != "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner only")

        # Collect every blob storage_key / mesh_storage_key from files rows.
        file_rows = await conn.fetch(
            "SELECT storage_key, mesh_storage_key, content, kind FROM files WHERE project_id = $1",
            pid,
        )
        blob_keys: list[str] = []
        for r in file_rows:
            if r["storage_key"]:
                blob_keys.append(r["storage_key"])
            if r["mesh_storage_key"]:
                blob_keys.append(r["mesh_storage_key"])
            # Photos embedded in Part content JSON: photos/<pid>/<fid>/...
            if r["kind"] == "part" and r["content"]:
                try:
                    content_obj = json.loads(r["content"])
                    for photo_key in (content_obj.get("photos") or []):
                        if photo_key:
                            blob_keys.append(photo_key)
                except Exception:
                    pass

        # cover / thumbnail keys on the project row itself
        proj_row = await conn.fetchrow(
            "SELECT thumbnail_storage_key, cover_storage_key FROM projects WHERE id = $1",
            pid,
        )
        if proj_row:
            if proj_row["thumbnail_storage_key"]:
                blob_keys.append(proj_row["thumbnail_storage_key"])
            if proj_row["cover_storage_key"]:
                blob_keys.append(proj_row["cover_storage_key"])

        # step_tessellation_jobs mesh keys (may not overlap with files.mesh_storage_key)
        tess_rows = await conn.fetch(
            """
            SELECT stj.mesh_storage_key
            FROM step_tessellation_jobs stj
            JOIN files f ON f.id = stj.file_id
            WHERE f.project_id = $1 AND stj.mesh_storage_key IS NOT NULL
            """,
            pid,
        )
        for r in tess_rows:
            if r["mesh_storage_key"]:
                blob_keys.append(r["mesh_storage_key"])

    # Git working-tree prefix used by S3GitStorer.
    git_prefix = f"workspaces/{ws_id}/git/{pid}/"
    # Photos prefix (catches any photos not yet reconciled to file content).
    photos_prefix = f"photos/{pid}/"

    # ── Phase 2: delete S3 blobs BEFORE deleting the DB row ──────────────
    # Best-effort: orphan blobs can be GC'd later; we must not let blob
    # failures block the project deletion.
    storage = get_storage_required()

    unique_keys = list(dict.fromkeys(k for k in blob_keys if k))
    removed_blobs = 0
    for key in unique_keys:
        try:
            await storage.delete(key)
            removed_blobs += 1
        except Exception as exc:
            logger.warning("delete_project: failed to remove blob %s: %s", key, exc)

    for prefix in (git_prefix, photos_prefix):
        try:
            n = await storage.delete_prefix(prefix)
            removed_blobs += n
        except Exception as exc:
            logger.warning("delete_project: failed to clean prefix %s: %s", prefix, exc)

    # ── Phase 3: delete the project row; FK cascades do the rest ─────────
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM projects WHERE id = $1", pid)

    return {"deleted": True, "project_id": pid, "removed_blobs": removed_blobs}


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


# Canonical file-kind allow-list. MUST stay in sync with the
# files_kind_check DB constraint (latest migration: 061_kind_wiring.sql)
# and the FileTree "+ New" menu KIND_ORDER. Module-level so tests can
# import and assert the menu set is a subset.
FILE_KINDS = (
    "file", "text", "folder", "assembly", "step", "drawing", "sketch", "part",
    "feature", "circuit", "equations", "material", "simulation", "script",
    "step-ref", "assembly_lock", "canvas", "schedule", "view", "sheet",
    "duct", "pipe", "conduit", "subd", "mesh", "render", "section",
    "cam_layered", "tool", "plc_st", "plc_ld", "quadmesh", "print", "gem", "wiring",
    "firmware", "mold", "pid", "optics", "layup", "dental",
    # T-248: silicon / EDA / firmware file kinds
    "hdl_vhdl", "hdl_verilog", "spice_netlist", "gds_layout", "oasis_layout",
    "lef_lib", "def_design", "liberty_lib", "silicon_flow", "silicon_pdk",
    "firmware_project",
    # T-330: PLM depth — ECO (Engineering Change Order) and SysML-light trace
    "eco", "sysml",
    # T-325: 1D system simulation — .system lumped-parameter network
    "system",
    # T-323: 3D in-vehicle wiring harness — .harness routed through the DMU
    "harness",
)


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

        if req.kind not in FILE_KINDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid kind")

        content = req.content or ""

        f = await files_queries.create_file(
            conn, pid, req.name, req.kind, req.parent_id, content, None, None, None, req.extension,
            created_by=user_id,
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
                   f.storage_key, f.mime_type, f.size, f.mesh_storage_key, f.version,
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
    expected_version: Optional[int] = None


_IDEMPOTENCY_WINDOW_SECS = 5


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

        # OCC: If content is being updated and expected_version was supplied,
        # check for a version mismatch before writing.
        if req.content is not None and req.expected_version is not None:
            current_row = await conn.fetchrow(
                "SELECT version, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
                fid, pid,
            )
            if not current_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
            if current_row["version"] != req.expected_version:
                # Return conflict with enough info for the client to show a banner.
                content_preview = (current_row["content"] or "")[:200]
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "current_version": current_row["version"],
                        "current_content_preview": content_preview,
                        "message": "File was modified by another session. Reload before saving.",
                    },
                )

        # Idempotency: identical content re-submitted within the window does
        # NOT bump version. Compare content_sha256 of the most recent revision.
        bump_version = req.content is not None
        if req.content is not None:
            new_sha = compute_content_sha(req.content)
            recent = await conn.fetchrow(
                """
                SELECT content_sha256 FROM file_revisions
                WHERE file_id = $1
                  AND created_at >= now() - ($2 * interval '1 second')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                fid, _IDEMPOTENCY_WINDOW_SECS,
            )
            if recent and recent["content_sha256"] is not None:
                # content_sha256 may be stored as bytes/memoryview or hex text
                stored = recent["content_sha256"]
                if isinstance(stored, memoryview):
                    stored = bytes(stored).hex()
                elif isinstance(stored, bytes):
                    stored = stored.hex()
                if stored == new_sha:
                    bump_version = False

        if bump_version:
            # Atomically increment version and update content.
            f = await conn.fetchrow(
                """
                UPDATE files
                SET content = $2,
                    version = version + 1,
                    updated_at = now()
                WHERE id = $1 AND deleted_at IS NULL
                RETURNING *
                """,
                fid, req.content,
            )
            if not f:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")
            f = dict(f)
            # Apply any other non-content field changes on top.
            if req.name is not None or req.parent_id is not None or req.extension is not None:
                f2 = await files_queries.update_file(
                    conn, fid,
                    name=req.name,
                    parent_id=req.parent_id,
                    extension=req.extension,
                )
                if f2:
                    f = dict(f2)
        else:
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


@router.get("/projects/{pid}/activity")
async def get_project_activity(
    pid: str,
    limit: int = Query(default=50, ge=1, le=200),
    before: Optional[str] = Query(default=None),
    payload: dict = Depends(require_auth),
):
    """Return a merged activity feed for a project.

    Shape: {events: [...], next_cursor: null | iso8601}

    Each event: {kind, source?, created_at, user: {id, name, avatar_url},
                 file?: {id, name}, thread?: {id, title}, content_preview?}

    Events are ordered newest-first (created_at DESC). Three sources are
    merged via UNION ALL:
      - file_revisions  → kind='edit', file, source from the revision
      - files.created_at (non-deleted) → kind='file_created', file
      - files.deleted_at (not null)   → kind='file_deleted', file
      - chat_messages (role='user')   → kind='chat', thread, content_preview
      - projects.created_at           → kind='project_created'

    Pagination uses an ISO before cursor: only events with created_at < before
    are returned. next_cursor is the oldest event's created_at when the page
    is full, else null.
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

        # Build optional before-cursor clause. Parameterised to avoid injection.
        # We add a position placeholder $3 for `before` when supplied.
        if before:
            before_clause = "AND sub.created_at < $3::timestamptz"
            params = [pid, limit + 1, before]
        else:
            before_clause = ""
            params = [pid, limit + 1]

        sql = f"""
            SELECT
                sub.kind,
                sub.source,
                sub.created_at,
                sub.user_id,
                u.name        AS user_name,
                u.avatar_url  AS user_avatar_url,
                sub.file_id,
                sub.file_name,
                sub.thread_id,
                sub.thread_title,
                sub.content_preview
            FROM (
                -- (a) file edits
                SELECT
                    'edit'::text           AS kind,
                    fr.source              AS source,
                    fr.created_at          AS created_at,
                    COALESCE(fr.user_id, NULL) AS user_id,
                    f.id                   AS file_id,
                    f.name                 AS file_name,
                    NULL::uuid             AS thread_id,
                    NULL::text             AS thread_title,
                    fr.content_preview     AS content_preview
                FROM file_revisions fr
                JOIN files f ON f.id = fr.file_id
                WHERE f.project_id = $1
                  AND fr.source IN ('llm', 'tool', 'restore')

                UNION ALL

                -- (b) file_created: files that are not soft-deleted, keyed on files.created_at.
                -- user comes from files.created_by (folded into baseline 0001) so
                -- the activity row attributes "<user> created main.jscad" instead
                -- of "Someone created main.jscad".
                SELECT
                    'file_created'::text   AS kind,
                    NULL::text             AS source,
                    f.created_at           AS created_at,
                    f.created_by           AS user_id,
                    f.id                   AS file_id,
                    f.name                 AS file_name,
                    NULL::uuid             AS thread_id,
                    NULL::text             AS thread_title,
                    NULL::text             AS content_preview
                FROM files f
                WHERE f.project_id = $1
                  AND f.deleted_at IS NULL

                UNION ALL

                -- (c) file_deleted: files that have been soft-deleted.
                -- The deleter isn't tracked separately; attribute to the
                -- file's original creator (better than "Someone deleted …").
                SELECT
                    'file_deleted'::text   AS kind,
                    NULL::text             AS source,
                    f.deleted_at           AS created_at,
                    f.created_by           AS user_id,
                    f.id                   AS file_id,
                    f.name                 AS file_name,
                    NULL::uuid             AS thread_id,
                    NULL::text             AS thread_title,
                    NULL::text             AS content_preview
                FROM files f
                WHERE f.project_id = $1
                  AND f.deleted_at IS NOT NULL

                UNION ALL

                -- (d) chat messages (role='user'). user_id comes from the
                -- chat_messages row itself; chat_messages.user_id was added
                -- in the consolidated baseline so the activity feed can
                -- attribute "<user> asked …" instead of showing Unknown.
                SELECT
                    'chat'::text                                AS kind,
                    NULL::text                                  AS source,
                    cm.created_at                               AS created_at,
                    cm.user_id                                  AS user_id,
                    NULL::uuid                                  AS file_id,
                    NULL::text                                  AS file_name,
                    ct.id                                       AS thread_id,
                    ct.title                                    AS thread_title,
                    LEFT(cm.content, 240)                       AS content_preview
                FROM chat_messages cm
                JOIN chat_threads ct ON ct.id = cm.thread_id
                WHERE ct.project_id = $1
                  AND cm.role = 'user'

                UNION ALL

                -- (e) project creation. user comes from projects.created_by
                -- (consolidated baseline) so the row attributes "<user>
                -- created the project" instead of "Unknown created …".
                SELECT
                    'project_created'::text AS kind,
                    NULL::text              AS source,
                    p.created_at            AS created_at,
                    p.created_by            AS user_id,
                    NULL::uuid              AS file_id,
                    NULL::text              AS file_name,
                    NULL::uuid              AS thread_id,
                    NULL::text              AS thread_title,
                    NULL::text              AS content_preview
                FROM projects p
                WHERE p.id = $1
            ) sub
            LEFT JOIN users u ON u.id = sub.user_id
            WHERE TRUE {before_clause}
            ORDER BY sub.created_at DESC
            LIMIT $2
        """

        rows = await conn.fetch(sql, *params)

    # Determine pagination cursor. We fetched limit+1 rows to detect a next
    # page without a separate COUNT query.
    has_more = len(rows) > limit
    page = rows[:limit]

    next_cursor = None
    if has_more and page:
        last_ts = page[-1]["created_at"]
        # asyncpg returns timestamptz as datetime; convert to ISO-8601.
        if hasattr(last_ts, "isoformat"):
            next_cursor = last_ts.isoformat()
        else:
            next_cursor = str(last_ts)

    events = []
    for row in page:
        ev = {
            "kind": row["kind"],
            "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
            "user": {
                "id": str(row["user_id"]) if row["user_id"] else None,
                "name": row["user_name"] or "",
                "avatar_url": row["user_avatar_url"] or "",
            },
        }
        if row["source"] is not None:
            ev["source"] = row["source"]
        if row["file_id"] is not None:
            ev["file"] = {
                "id": str(row["file_id"]),
                "name": row["file_name"] or "",
            }
        if row["thread_id"] is not None:
            ev["thread"] = {
                "id": str(row["thread_id"]),
                "title": row["thread_title"] or "",
            }
        if row["content_preview"] is not None:
            ev["content_preview"] = row["content_preview"]
        events.append(ev)

    return {"events": events, "next_cursor": next_cursor}


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
            INSERT INTO chat_threads (project_id, file_id, title, model, created_by)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            pid, req.file_id, req.title, req.model, user_id,
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

        # part_refs / tool_calls are jsonb. asyncpg returns jsonb as a
        # raw string (no global JSON codec is registered — many handlers
        # json.loads it explicitly), so returning dict(row) verbatim
        # ships e.g. part_refs:"[]" and the client does "[]".map(...) →
        # "part_refs.map is not a function". Decode here so the API
        # contract is always arrays.
        def _msg(row):
            m = dict(row)
            for k in ("part_refs", "tool_calls"):
                v = m.get(k)
                if isinstance(v, (str, bytes)):
                    try:
                        m[k] = json.loads(v) if v else []
                    except (ValueError, TypeError):
                        m[k] = []
                elif v is None:
                    m[k] = []
            return m

        return [_msg(row) for row in rows]


class PostMessageRequest(BaseModel):
    content: str
    part_refs: list = []
    model: Optional[str] = None


async def _insert_assistant_message(conn, tid: str, content: str, model_id: str, tool_calls: list) -> dict:
    tc_json = json.dumps([
        {
            "id": tc.id,
            "name": tc.name,
            "arguments": tc.arguments_json,
            # Persist provider_metadata so opaque round-trip tokens
            # (Gemini 3 thought_signature, etc.) survive across turns.
            # Empty dict serialises to "{}" — cheap.
            "provider_metadata": getattr(tc, "provider_metadata", None) or {},
        }
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


async def _insert_tool_message(conn, tid: str, tool_call_id: str, content: str, is_error: bool = False) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO chat_messages (thread_id, role, content, part_refs, tool_call_id, is_error)
        VALUES ($1, 'tool', $2, '[]'::jsonb, $3, $4)
        RETURNING *
        """,
        tid, content, tool_call_id, is_error,
    )
    return dict(row)


_CHAT_HISTORY_LIMIT = int(__import__("os").environ.get("KERF_CHAT_HISTORY_LIMIT", "200"))


async def _load_llm_history(conn, thread_id: str, exclude_id: str) -> list:
    # Fetch the most-recent N messages to bound memory usage, then re-order
    # chronologically so the LLM receives them oldest-first.
    rows = await conn.fetch(
        """
        SELECT role, content, tool_calls, tool_call_id, is_error
        FROM (
            SELECT role, content, tool_calls, tool_call_id, is_error, created_at
            FROM chat_messages
            WHERE thread_id = $1 AND id <> $2
            ORDER BY created_at DESC
            LIMIT $3
        ) sub
        ORDER BY created_at ASC
        """,
        thread_id, exclude_id, _CHAT_HISTORY_LIMIT,
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
        if row["is_error"]:
            msg.is_error = True
        if tc_raw and tc_raw not in ("null", "[]", b"null", b"[]"):
            try:
                arr = json.loads(tc_raw) if isinstance(tc_raw, (str, bytes)) else tc_raw
                for w in arr:
                    msg.tool_calls.append(llm_module.ToolCall(
                        id=w.get("id", ""),
                        name=w.get("name", ""),
                        arguments_json=w.get("arguments", "{}"),
                        provider_metadata=w.get("provider_metadata") or {},
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


async def _auto_title_thread(
    tid: str,
    user_content: str,
    assistant_content: str,
    provider: llm_module.Provider,
    model_id: str,
    pool,
    *,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> None:
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
            # R22: emit operator-cost row so auto-title COGS are auditable.
            if settings.usage_enabled and user_id:
                try:
                    await usage_queries.create_usage_event(
                        conn,
                        user_id=uuid.UUID(user_id),
                        kind="operator_token",
                        project_id=uuid.UUID(project_id) if project_id else None,
                        model=model_id,
                        input_tokens=resp.input_tokens if hasattr(resp, "input_tokens") else 0,
                        output_tokens=resp.output_tokens if hasattr(resp, "output_tokens") else 0,
                        payer="operator",
                    )
                except Exception as _ue:
                    _logger.warning("auto-title: usage event failed: %s", _ue)
    except Exception as e:
        _logger.warning(f"auto-title: {e}")


@router.post("/projects/{pid}/threads/{tid}/messages")
async def post_message(
    pid: str,
    tid: str,
    req: PostMessageRequest,
    payload: dict = Depends(require_auth),
    _rl: None = Depends(rate_limit(max_per_window=30, window_seconds=60, key_prefix="api:messages")),
):
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

    # Insert user message — attribute it to the caller so the activity
    # feed can render "<user> asked …" instead of "Unknown asked …".
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            """
            INSERT INTO chat_messages (thread_id, role, content, part_refs, user_id)
            VALUES ($1, 'user', $2, $3::jsonb, $4)
            RETURNING *
            """,
            tid, req.content, json.dumps(part_refs), user_id,
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
            # at provider COGS × markup.  Off by an order of magnitude on
            # large turns, but the spend-commit path settles against the
            # real numbers so this only gates rejection.
            bucket_model_info_price = await _get_price(
                pool, bucket_provider_name, provider_model_id,
            )
            est_cogs = bucket_model_info_price.compute_cost_usd(1000, 1000) \
                if bucket_model_info_price else 0.0
            # R7: read markup from settings
            _token_markup = 1.0 + settings.cloud_pricing_token_markup_pct / 100.0
            est_billed = est_cogs * _token_markup

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
        except ImportError as bx:
            # Billing module not installed (OSS/local mode) — safe to skip.
            _logger.debug(f"bucket-select: billing module unavailable, skipping: {bx}")
            bucket = None
        except Exception as bx:
            # Unexpected error in billing gate — fail closed to avoid a free
            # expensive-model call.
            _logger.error(f"bucket-select: unexpected billing error: {bx}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="billing service error — please try again",
            )

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
        # R10: re-snapshot user_billing and re-pick bucket on every iteration
        # (except the first, which was already resolved above) so that a
        # drained free-tier quota from a prior commit_spend stops the loop
        # rather than letting later iterations proceed on a stale snapshot.
        if iteration > 0 and settings.usage_enabled and bucket is not None:
            try:
                from kerf_billing.buckets import (
                    load_user_billing as _lub,
                    pick_bucket as _pb,
                    InsufficientCredits as _IC,
                )
                _user_billing_fresh = await _lub(pool, user_id)
                _bucket_fresh = _pb(
                    _user_billing_fresh, bucket_model_info, est_billed,
                    estimated_input_tokens=1000, estimated_output_tokens=1000,
                )
                if isinstance(_bucket_fresh, _IC):
                    code = (
                        "INSUFFICIENT_CREDITS_BYO_AVAILABLE"
                        if _bucket_fresh.byo_available
                        else "INSUFFICIENT_CREDITS"
                    )
                    async with pool.acquire() as conn:
                        last_assistant = await _insert_assistant_message(
                            conn, tid,
                            "Insufficient credits to continue.",
                            provider_model_id, None,
                        )
                        await conn.execute(
                            "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
                        )
                    raise HTTPException(
                        status_code=402,
                        detail={"code": code, "provider": bucket_provider_name},
                    )
                bucket = _bucket_fresh
            except HTTPException:
                raise
            except ImportError:
                pass
            except Exception as _rebucket_exc:
                _logger.error(
                    "bucket-recheck: unexpected error at iter=%d: %s",
                    iteration, _rebucket_exc,
                )
                raise HTTPException(
                    status_code=503,
                    detail="billing service error — please try again",
                )

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
                    # R7: read markup from settings rather than hardcoding 1.20
                    billed = cogs * (1.0 + settings.cloud_pricing_token_markup_pct / 100.0)
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
                        # R9: known cap-exceeded is a legitimate 402 — log and
                        # raise so the caller gets a proper error, not silence.
                        _logger.warning(
                            "usage: api token daily cap exceeded — "
                            "user_id=%s model=%s est_cost=%.6f: %s",
                            user_id, provider_model_id, billed, cap,
                        )
                        raise HTTPException(
                            status_code=402,
                            detail={"code": "API_TOKEN_DAILY_CAP_EXCEEDED"},
                        )
                    except Exception as billing_exc:
                        # R9: unexpected billing failure — log with full context
                        # and surface as 503 so the LLM call is not treated as
                        # successfully billed.
                        _logger.error(
                            "usage: commit_spend failed (UNEXPECTED) — "
                            "user_id=%s model=%s est_cost=%.6f: %s",
                            user_id, provider_model_id, billed, billing_exc,
                            exc_info=True,
                        )
                        raise HTTPException(
                            status_code=503,
                            detail={"code": "BILLING_WRITE_FAILED"},
                        )
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
            tool_is_error = False
            try:
                result = await tools_execute(proj_ctx, tc.name, tc.arguments_json.encode())
                # Detect error payloads returned by the executor
                # (err_payload returns {"error": ..., "code": ...}).
                try:
                    _parsed = json.loads(result)
                    if isinstance(_parsed, dict) and "error" in _parsed and "code" in _parsed:
                        tool_is_error = True
                except Exception:
                    pass
            except Exception as tool_exc:
                result = json.dumps({"error": str(tool_exc), "code": "ERROR"})
                tool_is_error = True
            async with pool.acquire() as conn:
                tm = await _insert_tool_message(conn, tid, tc.id, result, is_error=tool_is_error)
            tm["tool_name"] = tc.name
            tool_msgs.append(tm)
            history_msgs.append(llm_module.Message(
                role="tool",
                content=result,
                tool_call_id=tc.id,
                is_error=tool_is_error,
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
            tid, req.content, assistant_content, provider, provider_model_id, pool,
            user_id=user_id, project_id=pid,
        ))

    return {
        "user_message": user_msg,
        "assistant_message": last_assistant,
        "tool_messages": tool_msgs,
    }


# ---------------------------------------------------------------------------
# Streaming chat endpoint — SSE
# ---------------------------------------------------------------------------

def _sse_frame(event_name: str, data: dict) -> str:
    """Format a single SSE frame."""
    return f"event: {event_name}\ndata: {json.dumps(data)}\n\n"


@router.post("/projects/{pid}/threads/{tid}/messages/stream")
async def post_message_stream(
    pid: str,
    tid: str,
    req: PostMessageRequest,
    payload: dict = Depends(require_auth),
    _rl: None = Depends(rate_limit(max_per_window=30, window_seconds=60, key_prefix="api:messages_stream")),
):
    """Streaming (SSE) variant of POST /messages.

    Returns a text/event-stream response. The client reads Kerf-native events:
      assistant_text_delta, tool_use_start, tool_use_input_delta,
      tool_use_complete, tool_executing, tool_result, assistant_done, error.

    The endpoint is backward-compatible — the non-streaming POST /messages
    endpoint is kept unchanged.
    """
    user_id = payload.get("sub")
    pool = await get_pool_required()

    # ── Auth / project access ────────────────────────────────────────────────
    ws_id = await project_workspace_id(pid)
    if not ws_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

    async with pool.acquire() as conn:
        role = await get_user_workspace_role(conn, ws_id, user_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    if role == "viewer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot post messages")

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

    # Insert user message synchronously (so the optimistic-by-ID handshake works).
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            """
            INSERT INTO chat_messages (thread_id, role, content, part_refs, user_id)
            VALUES ($1, 'user', $2, $3::jsonb, $4)
            RETURNING *
            """,
            tid, req.content, json.dumps(part_refs), user_id,
        )
    user_msg = dict(user_row)

    # Build LLM history
    async with pool.acquire() as conn:
        history_msgs = await _load_llm_history(conn, tid, str(user_msg["id"]))
        part_contexts = await _load_part_contexts(conn, pid, part_refs)

    final_user_content = llm_module.build_user_message(req.content, part_contexts)
    history_msgs.append(llm_module.Message(role="user", content=final_user_content))

    registry = _get_llm_registry()

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

    async def _event_generator():
        nonlocal history_msgs

        # Emit the user_message id first so the client can anchor its UI.
        yield _sse_frame("user_message", {"id": str(user_msg["id"])})

        if not registry.has_any():
            yield _sse_frame("error", {"message": "LLM not configured — set ANTHROPIC_API_KEY", "is_error": True})
            async with pool.acquire() as conn:
                await _insert_assistant_message(
                    conn, tid, "LLM not configured — set ANTHROPIC_API_KEY", "none", None
                )
                await conn.execute(
                    "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
                )
            return

        try:
            provider, provider_model_id = registry.resolve(chosen_model)
        except ValueError as e:
            _logger.warning(f"llm stream: resolve {chosen_model!r} failed: {e}")
            msg = "That model isn't available right now. Try picking a different one from the model dropdown."
            yield _sse_frame("error", {"message": msg, "is_error": True})
            async with pool.acquire() as conn:
                await _insert_assistant_message(conn, tid, msg, "none", None)
                await conn.execute(
                    "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
                )
            return

        # ── Three-bucket billing (cloud only) ───────────────────────────────
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

                bucket_model_info = await load_model_info(pool, bucket_provider_name, provider_model_id)
                if bucket_model_info is None:
                    msg = "That model isn't in the pricing table yet — contact admin to refresh /api/admin/pricing/refresh."
                    yield _sse_frame("error", {"message": msg, "is_error": True})
                    async with pool.acquire() as conn:
                        await _insert_assistant_message(conn, tid, msg, "none", None)
                        await conn.execute(
                            "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
                        )
                    return

                user_billing = await load_user_billing(pool, user_id)
                bucket_model_info_price = await _get_price(pool, bucket_provider_name, provider_model_id)
                est_cogs = bucket_model_info_price.compute_cost_usd(1000, 1000) if bucket_model_info_price else 0.0
                # R7: read markup from settings
                _token_markup = 1.0 + settings.cloud_pricing_token_markup_pct / 100.0
                est_billed = est_cogs * _token_markup

                bucket = pick_bucket(
                    user_billing, bucket_model_info, est_billed,
                    estimated_input_tokens=1000, estimated_output_tokens=1000,
                )

                if isinstance(bucket, InsufficientCredits):
                    code = "INSUFFICIENT_CREDITS_BYO_AVAILABLE" if bucket.byo_available else "INSUFFICIENT_CREDITS"
                    yield _sse_frame("error", {"message": code, "is_error": True, "code": code})
                    return

                if isinstance(bucket, Byo):
                    provider = await _make_byo_provider(
                        pool, user_id, bucket.provider, fallback=provider,
                    )
            except (GeneratorExit, asyncio.CancelledError):
                return
            except ImportError as bx:
                # Billing module not installed (OSS/local mode) — safe to skip.
                _logger.debug(f"bucket-select stream: billing module unavailable, skipping: {bx}")
                bucket = None
            except Exception as bx:
                # Unexpected billing error — fail closed.
                _logger.error(f"bucket-select stream: unexpected billing error: {bx}")
                yield _sse_frame("error", {"message": "billing service error — please try again", "is_error": True})
                return

        last_assistant_content = ""
        last_assistant_tool_calls: list = []
        last_assistant_model = provider_model_id
        last_assistant_db: dict = {}

        try:
            for iteration in range(_MAX_AGENT_ITERATIONS):
                # R10: re-snapshot user_billing and re-pick bucket on every
                # iteration after the first so a drained quota stops the loop.
                if iteration > 0 and settings.usage_enabled and bucket is not None:
                    try:
                        from kerf_billing.buckets import (
                            load_user_billing as _lub,
                            pick_bucket as _pb,
                            InsufficientCredits as _IC,
                        )
                        _user_billing_fresh = await _lub(pool, user_id)
                        _bucket_fresh = _pb(
                            _user_billing_fresh, bucket_model_info, est_billed,
                            estimated_input_tokens=1000, estimated_output_tokens=1000,
                        )
                        if isinstance(_bucket_fresh, _IC):
                            code = (
                                "INSUFFICIENT_CREDITS_BYO_AVAILABLE"
                                if _bucket_fresh.byo_available
                                else "INSUFFICIENT_CREDITS"
                            )
                            yield _sse_frame("error", {
                                "message": "Insufficient credits to continue",
                                "code": code,
                                "is_error": True,
                            })
                            return
                        bucket = _bucket_fresh
                    except (GeneratorExit, asyncio.CancelledError):
                        return
                    except ImportError:
                        pass
                    except Exception as _rebucket_exc:
                        _logger.error(
                            "bucket-recheck stream: unexpected error at iter=%d: %s",
                            iteration, _rebucket_exc,
                        )
                        yield _sse_frame("error", {
                            "message": "billing service error — please try again",
                            "is_error": True,
                        })
                        return

                complete_req = llm_module.CompleteRequest(
                    model=provider_model_id,
                    system=llm_module.SystemPrompt + _AGENT_SYSTEM_ADDENDUM + type_addendum,
                    messages=history_msgs,
                    tools=tool_specs,
                )

                # ── Per-turn state ───────────────────────────────────────────
                turn_text_parts: list[str] = []
                turn_tool_calls: list[llm_module.ToolCall] = []
                # Map tool_use_id -> ToolCall (assembled from stream events)
                pending_tools: dict[str, llm_module.ToolCall] = {}
                stop_reason = "end_turn"
                input_tokens = 0
                output_tokens = 0

                # Heartbeat bookkeeping
                last_heartbeat = asyncio.get_event_loop().time()

                try:
                    stream_iter = provider.stream(complete_req)
                    async for ev in stream_iter:
                        # Emit heartbeat every 25 s to keep proxies alive
                        now = asyncio.get_event_loop().time()
                        if now - last_heartbeat >= 25:
                            yield ": keepalive\n\n"
                            last_heartbeat = now

                        if ev.type == "assistant_text_delta":
                            turn_text_parts.append(ev.data.get("text", ""))
                            yield _sse_frame("assistant_text_delta", ev.data)

                        elif ev.type == "tool_use_start":
                            tid_key = ev.data["tool_use_id"]
                            pending_tools[tid_key] = llm_module.ToolCall(
                                id=tid_key,
                                name=ev.data["name"],
                                arguments_json="{}",
                            )
                            yield _sse_frame("tool_use_start", ev.data)

                        elif ev.type == "tool_use_input_delta":
                            yield _sse_frame("tool_use_input_delta", ev.data)

                        elif ev.type == "tool_use_complete":
                            tid_key = ev.data["tool_use_id"]
                            assembled_input = ev.data.get("input", {})
                            if tid_key in pending_tools:
                                pending_tools[tid_key].arguments_json = json.dumps(assembled_input)
                                # Carry provider_metadata (e.g. Gemini 3's
                                # thought_signature) into the ToolCall so
                                # it gets persisted + echoed on the next
                                # turn. Empty dict if the provider didn't
                                # emit any opaque metadata.
                                pm = ev.data.get("provider_metadata") or {}
                                if pm:
                                    pending_tools[tid_key].provider_metadata = pm
                                turn_tool_calls.append(pending_tools[tid_key])
                            yield _sse_frame("tool_use_complete", ev.data)

                        elif ev.type == "assistant_done":
                            stop_reason = ev.data.get("stop_reason", "end_turn")
                            input_tokens = ev.data.get("input_tokens", 0)
                            output_tokens = ev.data.get("output_tokens", 0)

                except NotImplementedError:
                    # Provider doesn't support streaming — fall back to blocking.
                    try:
                        resp = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: provider.complete(complete_req),
                        )
                    except Exception as e:
                        err_msg = _friendly_llm_error(provider.name(), e)
                        yield _sse_frame("error", {"message": err_msg, "is_error": True})
                        async with pool.acquire() as conn:
                            await _insert_assistant_message(conn, tid, err_msg, provider_model_id, None)
                            await conn.execute(
                                "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
                            )
                        return
                    turn_text_parts = [resp.content]
                    turn_tool_calls = resp.tool_calls
                    stop_reason = resp.stop_reason
                    input_tokens = resp.input_tokens
                    output_tokens = resp.output_tokens
                    # Emit the complete text as one delta so frontend renders it.
                    if resp.content:
                        yield _sse_frame("assistant_text_delta", {"text": resp.content})

                except Exception as e:
                    err_msg = _friendly_llm_error(provider.name(), e)
                    _logger.error(f"llm stream: provider {provider.name()} model {provider_model_id} failed: {e}")
                    yield _sse_frame("error", {"message": err_msg, "is_error": True})
                    async with pool.acquire() as conn:
                        await _insert_assistant_message(conn, tid, err_msg, provider_model_id, None)
                        await conn.execute(
                            "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
                        )
                    return

                # ── Persist assistant turn ───────────────────────────────────
                assistant_content = "".join(turn_text_parts)
                last_assistant_content = assistant_content
                last_assistant_tool_calls = turn_tool_calls
                last_assistant_model = provider_model_id
                async with pool.acquire() as conn:
                    last_assistant_db = await _insert_assistant_message(
                        conn, tid, assistant_content, provider_model_id, turn_tool_calls
                    )

                # ── Record token usage (cloud only) ──────────────────────────
                if settings.usage_enabled and (input_tokens > 0 or output_tokens > 0):
                    try:
                        if bucket is not None and bucket_model_info is not None:
                            from kerf_billing.spend import commit_spend, ApiTokenDailyCapExceeded
                            cogs = bucket_model_info_price.compute_cost_usd(input_tokens, output_tokens) \
                                if bucket_model_info_price else 0.0
                            # R7: read markup from settings
                            billed = cogs * (1.0 + settings.cloud_pricing_token_markup_pct / 100.0)
                            try:
                                await commit_spend(
                                    pool, bucket=bucket, user_id=user_id, project_id=pid,
                                    model=provider_model_id,
                                    input_tokens=input_tokens, output_tokens=output_tokens,
                                    cogs_usd=cogs, billed_usd=billed, api_token_id=None,
                                )
                            except ApiTokenDailyCapExceeded as cap:
                                # R9: known cap — emit SSE error and stop the loop.
                                _logger.warning(
                                    "usage stream: api token daily cap exceeded — "
                                    "user_id=%s model=%s est_cost=%.6f: %s",
                                    user_id, provider_model_id, billed, cap,
                                )
                                yield _sse_frame("error", {
                                    "message": "API token daily cap exceeded",
                                    "code": "API_TOKEN_DAILY_CAP_EXCEEDED",
                                    "is_error": True,
                                })
                                return
                            except Exception as billing_exc:
                                # R9: unexpected billing failure — emit SSE error
                                # and stop; do not let the loop continue unbilled.
                                _logger.error(
                                    "usage stream: commit_spend failed (UNEXPECTED) — "
                                    "user_id=%s model=%s est_cost=%.6f: %s",
                                    user_id, provider_model_id, billed, billing_exc,
                                    exc_info=True,
                                )
                                yield _sse_frame("error", {
                                    "message": "Billing write failed — please try again",
                                    "code": "BILLING_WRITE_FAILED",
                                    "is_error": True,
                                })
                                return
                        else:
                            from cloud.usage import record_token_event
                            await record_token_event(
                                pool, user_id, pid, provider_model_id,
                                input_tokens, output_tokens, cost_usd=0.0,
                            )
                    except (GeneratorExit, asyncio.CancelledError):
                        return
                    except Exception as ue:
                        _logger.warning(f"usage stream: record token event: {ue}")

                # Append assistant turn to history
                history_msgs.append(llm_module.Message(
                    role="assistant",
                    content=assistant_content,
                    tool_calls=turn_tool_calls,
                ))

                if not turn_tool_calls or stop_reason == "stop":
                    # Final turn — emit assistant_done and break.
                    yield _sse_frame("assistant_done", {
                        "stop_reason": stop_reason,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "model": provider_model_id,
                    })
                    break

                # ── Execute tool calls ────────────────────────────────────────
                for tc in turn_tool_calls:
                    yield _sse_frame("tool_executing", {"tool_use_id": tc.id, "name": tc.name})

                    tool_is_error = False
                    try:
                        result = await tools_execute(proj_ctx, tc.name, tc.arguments_json.encode())
                        try:
                            _parsed = json.loads(result)
                            if isinstance(_parsed, dict) and "error" in _parsed and "code" in _parsed:
                                tool_is_error = True
                        except Exception:
                            pass
                    except Exception as tool_exc:
                        result = json.dumps({"error": str(tool_exc), "code": "ERROR"})
                        tool_is_error = True

                    async with pool.acquire() as conn:
                        tm = await _insert_tool_message(conn, tid, tc.id, result, is_error=tool_is_error)

                    content_preview = result[:200] if result else ""
                    yield _sse_frame("tool_result", {
                        "tool_use_id": tc.id,
                        "is_error": tool_is_error,
                        "content_preview": content_preview,
                    })

                    history_msgs.append(llm_module.Message(
                        role="tool",
                        content=result,
                        tool_call_id=tc.id,
                        is_error=tool_is_error,
                    ))

                if stop_reason != "tool_use" and not turn_tool_calls:
                    yield _sse_frame("assistant_done", {
                        "stop_reason": stop_reason,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "model": provider_model_id,
                    })
                    break

                if iteration == _MAX_AGENT_ITERATIONS - 1:
                    msg = "(stopped: max tool iterations reached)"
                    async with pool.acquire() as conn:
                        last_assistant_db = await _insert_assistant_message(
                            conn, tid, msg, provider_model_id, None
                        )
                    yield _sse_frame("assistant_done", {
                        "stop_reason": "max_iterations",
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "model": provider_model_id,
                    })
                    break

        except (asyncio.CancelledError, GeneratorExit):
            # Client disconnected — persist whatever partial assistant text we have.
            if last_assistant_content or last_assistant_tool_calls:
                try:
                    async with pool.acquire() as conn:
                        if not last_assistant_db:
                            await _insert_assistant_message(
                                conn, tid, last_assistant_content,
                                provider_model_id, last_assistant_tool_calls or None,
                            )
                except Exception:
                    pass
            return
        except Exception as e:
            err_msg = _friendly_llm_error("unknown", e)
            _logger.error(f"llm stream: unexpected error: {e}")
            yield _sse_frame("error", {"message": err_msg, "is_error": True})

        finally:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE chat_threads SET last_message_at = now(), updated_at = now() WHERE id = $1", tid
                )

        # Auto-title on first exchange (fire and forget)
        if is_first_user_message and registry.has_any() and last_assistant_content:
            asyncio.create_task(_auto_title_thread(
                tid, req.content, last_assistant_content, provider, provider_model_id, pool,
                user_id=user_id, project_id=pid,
            ))

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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

        # Confirm link belongs to this project (prevents IDOR across projects)
        await conn.execute(
            "UPDATE share_links SET revoked_at = now() WHERE id = $1 AND project_id = $2",
            lid,
            pid,
        )
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


@router.get("/projects/{pid}/revisions/size")
async def get_revisions_size(pid: str, payload: dict = Depends(require_auth)):
    """Return the estimated storage used by file_revisions for a project.

    Response shape::

        {
            "total_bytes": 4321567,
            "revision_count": 230,
            "by_file": [
                {"file_id": "uuid", "file_name": "main.jscad", "bytes": 1234567, "count": 87},
                ...
            ]
        }

    Byte estimates use ``pg_column_size(content_gz)`` for the gzip column and
    ``octet_length(content)`` for the text column (both NULL-safe via COALESCE).
    Results are ordered descending by bytes (largest file first).
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

        rows = await conn.fetch(
            """
            SELECT
                f.id                                              AS file_id,
                f.name                                           AS file_name,
                COALESCE(SUM(
                    COALESCE(pg_column_size(fr.content_gz), 0) +
                    COALESCE(octet_length(fr.content), 0)
                ), 0)                                            AS bytes,
                COUNT(fr.id)                                     AS count
            FROM files f
            LEFT JOIN file_revisions fr ON fr.file_id = f.id
            WHERE f.project_id = $1
            GROUP BY f.id, f.name
            ORDER BY bytes DESC
            """,
            pid,
        )

        by_file = [
            {
                "file_id": str(row["file_id"]),
                "file_name": row["file_name"],
                "bytes": int(row["bytes"]),
                "count": int(row["count"]),
            }
            for row in rows
        ]
        total_bytes = sum(item["bytes"] for item in by_file)
        revision_count = sum(item["count"] for item in by_file)

        return {
            "total_bytes": total_bytes,
            "revision_count": revision_count,
            "by_file": by_file,
        }


@router.delete("/projects/{pid}/revisions")
async def purge_project_revisions_route(
    pid: str,
    payload: dict = Depends(require_auth),
    keep_last: int = 5,
    confirm: str = "",
):
    """Purge old file_revisions for a project, keeping the most recent N per file.

    Requires:
      - confirm=PURGE query param (defence-in-depth)
      - keep_last >= 1 (always keep at least one revision per file)
      - Editor or owner role (not viewer)

    Returns {removed_rows, freed_bytes}.
    """
    user_id = payload.get("sub")

    if confirm != "PURGE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm param must equal 'PURGE'",
        )
    if keep_last < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="keep_last must be >= 1",
        )

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot purge revisions")

    from kerf_core.revisions import purge_project_revisions as _purge
    result = await _purge(pool, pid, keep_last_per_file=keep_last)
    return result


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

        await storage.put_chunk(
            row["storage_key"], n, io.BytesIO(body),
            conn=conn, session_id=row["id"],
        )

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
        size = await storage.concat_chunks_to(
            row["storage_key"], final_key,
            conn=conn, session_id=row["id"],
        )

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


@dataclass
class _FileRecord:
    """Normalised file record used by materialize_project_tree."""
    id: str
    parent_id: Optional[str]
    name: str
    kind: str
    content: str          # inline text content (may be empty when storage_key is set)
    storage_key: Optional[str]   # object-store key; set → blob, None → inline
    mime_type: Optional[str]
    size: Optional[int]


@dataclass
class MaterializeTreeResult:
    """Return value from materialize_project_tree.

    zip_bytes: raw bytes of the self-contained ZIP archive.
    manifest:  the kerf-manifest.json dict (also embedded in the archive).
    """
    zip_bytes: bytes
    manifest: dict


async def materialize_project_tree(
    *,
    files: list[_FileRecord],
    storage,
    project_name: str = "",
    project_description: str = "",
    project_tags: list = None,
    project_created_at: str = "",
    thumbnail_storage_key: Optional[str] = None,
    max_bytes: int = EXPORT_MAX_BYTES,
) -> MaterializeTreeResult:
    """Build a self-contained ZIP archive for a project's file tree.

    This is the shared materialization spine reused by the export route,
    sync (T-127), and import (T-128).  It is a pure async function with
    no DB dependency — the caller resolves the file records and passes
    them in.

    Classification rules (mirrors the DB seam):
    - ``storage_key`` is set   → *blob*: real bytes are fetched from
      ``storage`` and written at the file's resolved path.
    - ``storage_key`` is None  → *inline*: ``content`` bytes are written
      verbatim at the file's resolved path.

    The archive always contains a top-level ``kerf-manifest.json`` listing
    every file with:
    - ``path``           — POSIX repo-relative path
    - ``kind``           — file kind (script, step, folder, …)
    - ``classification`` — ``"inline"`` or ``"blob"``
    - ``size``           — byte size of the actual content
    - ``oid``            — sha256 hex digest of the content (blobs and
                           inline files alike, so importers can verify)
    - ``mime_type``      — optional; omitted when absent

    Raises:
        HTTPException(413): if the accumulated archive size exceeds
            ``max_bytes`` (default: 500 MB).
        Any storage.get() exception propagates unchanged so callers can
            decide how to handle missing blobs.

    Args:
        files:                   Normalised file records (from ``files``
                                 table rows).
        storage:                 Kerf storage backend (LocalStorage /
                                 S3Storage).
        project_name:            Project name — embedded in the manifest.
        project_description:     Project description — embedded in the
                                 manifest.
        project_tags:            Project tags list — embedded in the manifest.
        project_created_at:      ISO-8601 string — embedded in the manifest.
        thumbnail_storage_key:   When set, the thumbnail is fetched and
                                 added to the archive as ``thumbnail.jpg``.
        max_bytes:               Hard cap on the uncompressed content
                                 written to the archive (default 500 MB).

    Returns:
        ``MaterializeTreeResult`` with ``zip_bytes`` and ``manifest``.
    """
    if project_tags is None:
        project_tags = []

    # --- 1. Build id→record index and resolve POSIX paths ----------------
    by_id: dict[str, _FileRecord] = {f.id: f for f in files}
    path_of: dict[str, str] = {}

    def _resolve(fid: str) -> str:
        if fid in path_of:
            return path_of[fid]
        rec = by_id.get(fid)
        if not rec:
            return ""
        if not rec.parent_id:
            p = rec.name
        else:
            parent_path = _resolve(rec.parent_id)
            p = rec.name if not parent_path else f"{parent_path}/{rec.name}"
        path_of[fid] = p
        return p

    # BFS ordering so parent paths are resolved before children.
    roots = [f.id for f in files if not f.parent_id]
    children_of: dict[str, list[str]] = {}
    for f in files:
        if f.parent_id:
            children_of.setdefault(f.parent_id, []).append(f.id)

    ordered: list[str] = []
    queue = list(roots)
    while queue:
        fid = queue.pop(0)
        ordered.append(fid)
        queue.extend(children_of.get(fid, []))

    # --- 2. Build manifest entries and collect pending writes -------------
    manifest_files: list[dict] = []

    # Each pending: {"path": str, "content_bytes": bytes | None,
    #                "blob_key": str | None}
    # We defer blob fetches so inline files are always written even if a
    # blob fetch fails.
    pendings: list[dict] = []
    seen_blob_key: set[str] = set()

    for fid in ordered:
        rec = by_id[fid]
        rel = _resolve(fid)

        entry: dict = {"path": rel, "kind": rec.kind}
        if rec.mime_type:
            entry["mime_type"] = rec.mime_type

        if rec.kind == "folder":
            entry["classification"] = "folder"
            manifest_files.append(entry)
            continue

        if rec.storage_key:
            # Blob — real bytes live in the object store.
            entry["classification"] = "blob"
            entry["oid"] = rec.storage_key  # storage_key is the sha256 oid
            if rec.size is not None:
                entry["size"] = rec.size
            if rec.storage_key not in seen_blob_key:
                seen_blob_key.add(rec.storage_key)
                pendings.append({
                    "zip_path": rel,
                    "blob_key": rec.storage_key,
                    "content_bytes": None,
                })
        else:
            # Inline — content column holds the text.
            content_bytes = rec.content.encode("utf-8") if isinstance(rec.content, str) else (rec.content or b"")
            oid = hashlib.sha256(content_bytes).hexdigest()
            entry["classification"] = "inline"
            entry["oid"] = oid
            entry["size"] = len(content_bytes)
            pendings.append({
                "zip_path": rel,
                "blob_key": None,
                "content_bytes": content_bytes,
            })

        manifest_files.append(entry)

    # --- 3. Fetch blob content and finalise oids before building manifest --
    # We resolve all blob bytes first so kerf-manifest.json can be written
    # with accurate oid and size values in a single pass.
    for p in pendings:
        if p["blob_key"]:
            blob_io, _ = await storage.get(p["blob_key"])
            blob_bytes = blob_io.read()
            p["content_bytes"] = blob_bytes
            # Update the manifest entry with the real sha256 oid and size.
            oid = hashlib.sha256(blob_bytes).hexdigest()
            for me in manifest_files:
                if me.get("classification") == "blob" and me.get("oid") == p["blob_key"]:
                    me["oid"] = oid
                    me["size"] = len(blob_bytes)
                    break

    manifest: dict = {
        "version": 1,
        "name": project_name,
        "description": project_description,
        "tags": project_tags,
        "created_at": project_created_at,
        "files": manifest_files,
    }

    # --- 4. Assemble ZIP in-memory ----------------------------------------
    buf = io.BytesIO()
    written = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        written += len(manifest_bytes)
        if written > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="export exceeds 500MB cap",
            )
        zf.writestr("kerf-manifest.json", manifest_bytes)

        for p in pendings:
            content_bytes = p["content_bytes"] or b""
            written += len(content_bytes)
            if written > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="export exceeds 500MB cap",
                )
            zf.writestr(p["zip_path"], content_bytes)

        if thumbnail_storage_key:
            try:
                thumb_io, _ = await storage.get(thumbnail_storage_key)
                thumb_bytes = thumb_io.read()
                written += len(thumb_bytes)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="export exceeds 500MB cap",
                    )
                zf.writestr("thumbnail.jpg", thumb_bytes)
            except Exception:
                pass

    return MaterializeTreeResult(zip_bytes=buf.getvalue(), manifest=manifest)


@router.get("/projects/{pid}/export")
async def export_project(
    request: Request,
    pid: str,
    payload: dict = Depends(require_auth),
    # R14: per-user rate limit — 20 exports per hour
    _rl: None = Depends(rate_limit(max_per_window=20, window_seconds=3600, key_prefix="api:export")),
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
            select name, description, coalesce(tags, '{}') as tags,
                   to_char(created_at at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at,
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
        created_at = row["created_at"]
        thumb_key = row["thumbnail_storage_key"]

        file_rows = await conn.fetch(
            """
            select id, parent_id, name, kind, coalesce(content, '') as content,
                   storage_key, mime_type, size
            from files
            where project_id = $1 and deleted_at is null
            """,
            uuid.UUID(pid),
        )

        records = [
            _FileRecord(
                id=str(fr["id"]),
                parent_id=str(fr["parent_id"]) if fr["parent_id"] else None,
                name=fr["name"],
                kind=fr["kind"],
                content=fr["content"],
                storage_key=fr["storage_key"],
                mime_type=fr["mime_type"],
                size=fr["size"],
            )
            for fr in file_rows
        ]

    storage = get_storage_required()
    result = await materialize_project_tree(
        files=records,
        storage=storage,
        project_name=name,
        project_description=description or "",
        project_tags=tags,
        project_created_at=created_at or "",
        thumbnail_storage_key=thumb_key,
    )

    # R14: record egress bytes so we can audit outbound bandwidth per user.
    bytes_sent = len(result.zip_bytes)
    if settings.usage_enabled and uid:
        try:
            async with pool.acquire() as conn:
                await usage_queries.create_usage_event(
                    conn,
                    user_id=uuid.UUID(uid),
                    kind="egress",
                    project_id=uuid.UUID(pid),
                    bytes_delta=bytes_sent,
                )
        except Exception as _eg_exc:
            _logger.warning("egress: failed to record export usage — uid=%s: %s", uid, _eg_exc)

    slug = slugify_name(name)
    short = pid[:8]
    filename = f"{slug}-{short}.zip"

    return StreamingResponse(
        iter([result.zip_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# GK-P50: Project 3DM export — wire write_3dm into the project download route.
#
# GET /projects/{pid}/export-3dm
# Returns a Rhino .3dm binary containing all feature/surf/sketch/mesh files
# in the project.  Delegates to kerf_imports.export_3dm.export_to_3dm (which
# uses the rhino3dm PyPI package when available, or the minimal fixture-format
# writer as a fallback).
#
# This sits alongside the existing /projects/{pid}/export (ZIP) route and the
# /export-3dm POST route in kerf-imports (which handles object-level exports).
# The project-level route is the "download the whole project as a 3DM" action
# that mirrors Rhino's "Save As .3dm" from within the kerf UI.

@router.get("/projects/{pid}/export-3dm")
async def export_project_3dm(
    request: Request,
    pid: str,
    payload: dict = Depends(require_auth),
):
    """Export all geometry files in a project as a single Rhino .3dm binary.

    Returns the .3dm file as an attachment download.  Requires read access to
    the project.  Uses kerf_imports.export_3dm when available; falls back to
    kerf_cad_core.geom.io.rhino3dm.write_3dm minimal writer.

    HTTP 503 is returned when neither rhino3dm backend is available.
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

        row = await conn.fetchrow(
            "select name from projects where id = $1",
            uuid.UUID(pid),
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")

        project_name = row["name"] or "export"

        # Fetch all feature/surf/sketch/mesh files for this project.
        file_rows = await conn.fetch(
            """
            select id, name, kind, coalesce(content, '') as content
            from files
            where project_id = $1
              and deleted_at is null
              and kind in ('feature', 'surf', 'sketch', 'mesh')
            """,
            uuid.UUID(pid),
        )

    if not file_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="project has no geometry files to export",
        )

    # Build the KerfObject list for export_to_3dm.
    objects = []
    for fr in file_rows:
        try:
            content_json = json.loads(fr["content"]) if fr["content"] else {}
        except Exception:
            content_json = {"raw": fr["content"]}
        objects.append({"kind": fr["kind"], "content_json": content_json})

    # Attempt export via kerf_imports.export_3dm (full rhino3dm path).
    try:
        from kerf_imports.export_3dm import export_to_3dm  # type: ignore[import]
        three_dm_bytes: bytes = export_to_3dm(objects)
    except ImportError:
        # Fall back to write_3dm minimal writer via a temp file.
        try:
            import tempfile
            import os
            from kerf_cad_core.geom.io.rhino3dm import write_3dm  # type: ignore[import]
            with tempfile.NamedTemporaryFile(suffix=".3dm", delete=False) as tf:
                tmp_path = tf.name
            try:
                write_3dm(None, tmp_path, surfaces=[], curves=[])
                with open(tmp_path, "rb") as f:
                    three_dm_bytes = f.read()
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"3DM export unavailable: {exc}. "
                    "Install the 'rhino3dm' Python package to enable .3dm export."
                ),
            ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"3DM export failed: {exc}",
        )

    slug = slugify_name(project_name)
    short = pid[:8]
    filename = f"{slug}-{short}.3dm"

    from fastapi.responses import Response as _FastAPIResponse
    return _FastAPIResponse(
        content=three_dm_bytes,
        media_type="model/vnd.3dm",
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
        # Thumbnails stay in the PRIVATE bucket — they're served via the
        # auth-gated streaming endpoint (/api/projects/:id/thumbnail), which
        # enforces project visibility. Returning that relative URL (not a
        # public CDN URL) keeps private-project thumbnails confidential.
        await storage.put(key, io.BytesIO(jpg_bytes), "image/jpeg", len(jpg_bytes))

        now = datetime.utcnow()

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
            "thumbnail_url": f"/api/projects/{pid}/thumbnail",
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

        # Workshop convention (files-in-repo): a project file named
        # cover.{png,jpg,jpeg,webp,gif} overrides the auto-generated cover.
        # The generated cover stays the DEFAULT — the repo file only wins
        # when present. Resolved here so the public URL stays stable.
        override = await conn.fetchrow(
            """
            SELECT storage_key FROM files
            WHERE project_id = $1 AND kind = 'file' AND deleted_at IS NULL
              AND storage_key IS NOT NULL
              AND lower(name) IN ('cover.png','cover.jpg','cover.jpeg','cover.webp','cover.gif')
            ORDER BY (parent_id IS NULL) DESC, updated_at DESC
            LIMIT 1
            """,
            uuid.UUID(pid),
        )
        key = (override["storage_key"] if override else None) or proj.get("cover_storage_key")
        if not key:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no cover available")

    storage = get_storage_required()
    body, content_type = await storage.get(key)
    return StreamingResponse(body, media_type=content_type or "image/png")


@router.get("/projects/{pid}/thumbnail")
async def serve_project_thumbnail(
    pid: str,
    auth: Optional[dict] = Depends(optional_auth),
):
    """GET /api/projects/:pid/thumbnail — serve the auto-captured editor
    thumbnail (all project kinds).

    This GET route was MISSING entirely — only the POST existed — so
    every thumbnail_url (project lists + Workshop cards) 404'd. Mirrors
    serve_project_cover: public projects are anonymously accessible
    (Workshop), private require workspace membership, 404 when none
    captured yet.
    """
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        proj = await conn.fetchrow(
            "SELECT workspace_id, visibility, thumbnail_storage_key FROM projects WHERE id = $1",
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

        key = proj.get("thumbnail_storage_key")
        if not key:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no thumbnail available")

    storage = get_storage_required()
    body, content_type = await storage.get(key)
    return StreamingResponse(body, media_type=content_type or "image/jpeg")



# ── Workshop media (files-in-repo) ──────────────────────────────────
# Workshop images are repo files under a project `workshop/` folder
# (GitHub-style), replacing the retired project_workshop_images gallery
# table. This public route streams such a file's bytes with the same
# visibility rules as the cover route.
@router.get("/projects/{pid}/workshop-media/{file_id}")
async def serve_workshop_media(
    pid: str,
    file_id: str,
    auth: Optional[dict] = Depends(optional_auth),
):
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        proj = await conn.fetchrow(
            "SELECT workspace_id, visibility FROM projects WHERE id = $1",
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
        f = await conn.fetchrow(
            """
            SELECT storage_key FROM files
            WHERE id = $2 AND project_id = $1 AND deleted_at IS NULL
              AND kind = 'file'
            """,
            uuid.UUID(pid), uuid.UUID(file_id),
        )
        if not f or not f["storage_key"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        key = f["storage_key"]
    storage = get_storage_required()
    body, content_type = await storage.get(key)
    return StreamingResponse(body, media_type=content_type or "image/png")


# ── Project-scoped blob serve (kerf hydrate backend, T-140) ─────────────────
# Streams a content-addressed object that the project actually references.
# Auth + visibility: mirrors serve_project_cover exactly —
#   public project  → anonymous access OK
#   private project → workspace membership required (else 404 to avoid info leak)
# 404 when:
#   • project does not exist
#   • blob_refs has no (oid, project_id) row   → cross-project or phantom oid
#   • object is not in storage
@router.get("/projects/{pid}/blobs/{oid}")
async def serve_project_blob(
    request: Request,
    pid: str,
    oid: str,
    auth: Optional[dict] = Depends(optional_auth),
    # R15: per-user/per-IP rate limit — 120 blob fetches per minute
    _rl: None = Depends(rate_limit(max_per_window=120, window_seconds=60, key_prefix="api:blobs")),
):
    """GET /api/projects/:pid/blobs/:oid — serve a content-addressed object.

    R15 (T-409): When ``STORAGE_BACKEND=s3``, redirects (HTTP 302) to a
    Tigris presigned GET URL instead of streaming bytes through the app.
    This offloads egress bandwidth from Koyeb to Tigris/CDN.  For
    local/self-host mode (any other backend) the original stream-through
    path is preserved.

    The oid must be referenced by the project (a ``blob_refs`` row exists for
    ``(oid, project_id)``).  Returns 404 for any oid the project does not own,
    preventing cross-project data access without leaking information about
    other projects' blobs.

    Visibility rules are identical to ``serve_project_cover``:
      * public project → anonymous callers may download
      * private project → caller must be a workspace member
    """
    try:
        proj_uuid = uuid.UUID(pid)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        proj = await conn.fetchrow(
            "SELECT workspace_id, visibility FROM projects WHERE id = $1",
            proj_uuid,
        )
        if not proj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

        if proj["visibility"] != "public":
            uid = auth.get("sub") if auth else None
            if not uid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="authentication required",
                )
            role = await get_user_workspace_role(conn, str(proj["workspace_id"]), uid)
            if not role:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

        # Verify the project actually references this oid; prevents cross-project
        # access even when the caller is a member of a different workspace.
        ref_exists = await conn.fetchval(
            "SELECT 1 FROM blob_refs WHERE oid = $1 AND project_id = $2 LIMIT 1",
            oid,
            proj_uuid,
        )
        if not ref_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    storage = get_storage_required()
    key = blob_storage_key(oid)

    # R15 (T-409): S3 backend → redirect to a presigned URL; avoids proxying
    # bytes through the app and eliminates Koyeb egress cost.
    from kerf_core.storage.s3 import S3Storage as _S3Storage
    if isinstance(storage, _S3Storage):
        try:
            presigned = await storage.signed_url(key, ttl_seconds=900)
        except Exception:
            _logger.exception("serve_project_blob: failed to presign oid=%s", oid)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
        return RedirectResponse(url=presigned, status_code=302)

    # Local / self-host fallback: stream bytes through the app.
    try:
        body, content_type = await storage.get(key)
    except (FileNotFoundError, KeyError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return StreamingResponse(body, media_type=content_type or "application/octet-stream")


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
        # Avatars render as a direct <img src> (no auth-gated endpoint), so
        # they go to the public CDN bucket. Everything else stays private.
        await storage.put_public(key, io.BytesIO(jpg_bytes), "image/jpeg", len(jpg_bytes))

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
            await storage.delete_public(row["prev"]["avatar_storage_key"])

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
                where p.created_by = u.id
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
             where p.created_by = $1
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

    Workshop media is files-in-repo (GitHub-style): the gallery is
    derived from image files under a project `workshop/` folder and the
    cover is a repo cover.* file, with the auto-captured
    thumbnail_storage_key as the default. `workshop_images` /
    `workshop_model_*` are attached by workshop_get on the detail path
    (the browse grid keeps just the cheap thumbnail).
    """
    pid = str(p["id"])

    thumbnail_url = (
        f"/api/projects/{pid}/thumbnail" if p.get("thumbnail_storage_key") else None
    )
    images = [
        {
            "id": str(im["id"]),
            "name": im.get("name") or "",
            "url": f"/api/projects/{pid}/workshop-media/{im['id']}",
        }
        for im in (p.get("workshop_images") or [])
    ]
    model_id = p.get("workshop_model_id")

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
        # A Workshop project belongs to its WORKSPACE, not a person —
        # show the workspace as the author identity. id stays the
        # publishing user (ownership checks like isOwner depend on it);
        # user_name is kept so the UI can still show "both" if desired.
        "author": {
            "id": str(p["author_id"]) if p.get("author_id") else None,
            "name": p.get("workspace_name") or p.get("author_name") or "unknown",
            "avatar_url": p.get("author_avatar_url"),
            "is_verified_publisher": bool(p.get("is_verified_publisher", False)),
            "workspace_name": p.get("workspace_name") or "",
            "workspace_slug": p.get("workspace_slug") or "",
            "user_name": p.get("author_name") or "",
        },
        "likes_count": int(p.get("likes_count") or 0),
        "liked_by_me": bool(p.get("liked_by_me", False)),
        "forks_count": int(p.get("forks_count") or 0),
        "file_count": int(p.get("file_count") or 0),
        "total_bytes": int(p.get("total_bytes") or 0),
        "thumbnail_storage_key": p.get("thumbnail_storage_key"),
        "thumbnail_url": thumbnail_url,
        "images": images,
        "model_file_id": str(model_id) if model_id else None,
        "model_name": p.get("workshop_model_name") or None,
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


_IMG_RE = r'\.(png|jpe?g|webp|gif)$'
_MODEL_RE = r'\.(jscad|scad|feature|step|stp|stl|glb|gltf|json|obj)$'


async def _attach_workshop_media(conn, project_id, project: dict) -> dict:
    """Files-in-repo Workshop media (detail path only).

    Gallery = image files under a project `workshop/` folder
    (GitHub-style), excluding the cover.*. Model = a renderable file in
    that folder (a `workshop.*` model wins, else the most-recent one) —
    surfaced as a pointer the frontend opens in the editor's 3D view.
    The browse grid stays cheap (thumbnail/cover only) so this is not
    run there.
    """
    images = await conn.fetch(
        """
        SELECT f.id, f.name
        FROM files f
        JOIN files d ON d.id = f.parent_id AND d.kind = 'folder'
                    AND lower(d.name) = 'workshop' AND d.deleted_at IS NULL
        WHERE f.project_id = $1 AND f.kind = 'file' AND f.deleted_at IS NULL
          AND f.storage_key IS NOT NULL
          AND lower(f.name) ~ $2
          AND lower(f.name) NOT LIKE 'cover.%'
        ORDER BY lower(f.name)
        """,
        project_id, _IMG_RE,
    )
    project["workshop_images"] = [dict(r) for r in images]

    model = await conn.fetchrow(
        """
        SELECT f.id, f.name
        FROM files f
        JOIN files d ON d.id = f.parent_id AND d.kind = 'folder'
                    AND lower(d.name) = 'workshop' AND d.deleted_at IS NULL
        WHERE f.project_id = $1 AND f.kind = 'file' AND f.deleted_at IS NULL
          AND lower(f.name) ~ $2
        ORDER BY (lower(f.name) LIKE 'workshop.%') DESC, f.updated_at DESC
        LIMIT 1
        """,
        project_id, _MODEL_RE,
    )
    if model:
        project["workshop_model_id"] = model["id"]
        project["workshop_model_name"] = model["name"]
    return project


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
        # Browse grid: thumbnail/cover only — gallery + model are
        # resolved on the detail path (workshop_get), not per grid row.

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
        project = dict(project)

        # Workshop convention (files-in-repo = source of truth): a
        # project README.md file overrides the DB `readme` column. The
        # auto-generated thumbnail/cover stay the DEFAULT; a repo file
        # overrides it. Resolved on the detail path only (single
        # project) — the browse grid keeps the cheap generated default.
        readme_row = await conn.fetchrow(
            """
            SELECT content FROM files
            WHERE project_id = $1 AND lower(name) = 'readme.md'
              AND kind = 'file' AND deleted_at IS NULL
            ORDER BY (parent_id IS NULL) DESC, updated_at DESC
            LIMIT 1
            """,
            project_id,
        )
        if readme_row and (readme_row["content"] or "").strip():
            project["readme"] = readme_row["content"]

        # Cover override: a repo cover.* file beats the auto-generated
        # cover (which stays the default). serve_project_cover resolves
        # the actual bytes; here we only need cover_storage_key to be
        # truthy so _project_to_workshop_row emits the /cover URL even
        # for a project that never had an auto cover generated.
        if not project.get("cover_storage_key"):
            cover_file = await conn.fetchrow(
                """
                SELECT storage_key FROM files
                WHERE project_id = $1 AND kind = 'file' AND deleted_at IS NULL
                  AND storage_key IS NOT NULL
                  AND lower(name) IN ('cover.png','cover.jpg','cover.jpeg','cover.webp','cover.gif')
                ORDER BY (parent_id IS NULL) DESC, updated_at DESC
                LIMIT 1
                """,
                project_id,
            )
            if cover_file and cover_file["storage_key"]:
                project["cover_storage_key"] = cover_file["storage_key"]

        # Files-in-repo gallery + designated 3D model (detail path).
        await _attach_workshop_media(conn, project_id, project)

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
    *,
    user_id: Optional[str] = None,
) -> Optional[str]:
    """Attempt to auto-render a hero cover for the project.

    Uses kerf-render if Blender is available; falls back to the existing
    thumbnail_storage_key gracefully (no exception raised).

    ``user_id`` is required in cloud mode (usage_enabled=True): the billing
    gate is checked BEFORE the HTTP call so the publisher's account is charged
    rather than the platform absorbing an unmetered GPU render (R6 fix).

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

        # ── R6: pre-gate billing BEFORE dispatching the HTTP render call ──────
        # Estimate GPU-seconds for 64 samples at 1280×960 (matches the payload
        # below).  This uses the same formula as run_render so the gate sees a
        # consistent estimate.
        _pixels_ratio = (1280 * 960) / (1920 * 1080)
        _est_gpu_seconds = max(5.0, 64 * _pixels_ratio * 0.1)
        from kerf_render.routes import _run_billing_gate  # type: ignore[import]
        await _run_billing_gate(user_id, _est_gpu_seconds)
        # ─────────────────────────────────────────────────────────────────────

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

                _readme_used_llm = False
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
                    _readme_used_llm = True
                else:
                    from kerf_chat.readme_gen import generate_readme_template
                    readme_text = generate_readme_template(project_ctx, bom_rows=bom_rows or None)

                # R22: audit operator-cost LLM call in usage_events.
                if _readme_used_llm and settings.usage_enabled:
                    try:
                        await usage_queries.create_usage_event(
                            conn,
                            user_id=uuid.UUID(user_id),
                            kind="operator_token",
                            project_id=project_id,
                            model="claude-haiku-4-5",
                            payer="operator",
                        )
                    except Exception as _ue:
                        logging.getLogger(__name__).warning("workshop_publish: readme usage event failed: %s", _ue)
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
        # Pass user_id so _generate_project_cover can pre-gate billing before
        # dispatching the HTTP render call (R6 fix — prevents unmetered renders).
        cover_key: Optional[str] = None
        try:
            storage = get_storage_required()
            cover_key = await _generate_project_cover(
                conn, project, project_id, storage, user_id=user_id
            )
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

            _readme_used_llm = False
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
                _readme_used_llm = True
            else:
                readme_text = generate_readme_template(project_ctx, bom_rows=bom_rows or None)

            # R22: audit operator-cost LLM call in usage_events.
            if _readme_used_llm and settings.usage_enabled:
                try:
                    await usage_queries.create_usage_event(
                        conn,
                        user_id=uuid.UUID(user_id),
                        kind="operator_token",
                        project_id=project_id,
                        model="claude-haiku-4-5",
                        payer="operator",
                    )
                except Exception as _ue:
                    logging.getLogger(__name__).warning("workshop_regenerate_readme: usage event failed: %s", _ue)
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
            INSERT INTO projects (id, workspace_id, name, description, visibility, tags,
                                  forked_from_project_id, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'private', $5, $6, now(), now())
            """,
            new_project_id,
            workspace["id"],
            fork_name,
            source.get("description", ""),
            list(source.get("tags") or []),
            source_project_id,
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
# Topology optimisation run
# ---------------------------------------------------------------------------

@router.post("/projects/{pid}/files/{fid}/topo/run")
async def run_topo_proxy(pid: str, fid: str, request: Request, payload: dict = Depends(require_auth)):
    """
    Forward the .topo file's JSON spec to the pyworker /run-topo route.
    Returns { job_id, status } or { status: 'pending' } when pyworker
    is unavailable (engine not yet deployed).

    The file must be of kind 'topo'.  Viewers and editors may trigger this.
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
        if row["kind"] != "topo":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="file is not a .topo file",
            )

        try:
            spec = json.loads(row["content"] or "{}")
        except Exception:
            spec = {}

    spec["file_id"] = fid
    spec["project_id"] = pid

    pyworker_url = os.environ.get("PYWORKER_URL", "http://localhost:9090")
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{pyworker_url}/run-topo",
                json=spec,
            )
        if resp.status_code == 200:
            return resp.json()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"pyworker error: {resp.text[:300]}",
        )
    except _httpx.HTTPError:
        # Engine not yet deployed — return pending status so the UI can
        # show the ENGINE_PENDING warning instead of a hard error.
        return {"status": "pending", "message": "Engine pending — FEniCSx not yet deployed."}


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


# ---------------------------------------------------------------------------
# Part photo upload (T-310: rate-limited)
# ---------------------------------------------------------------------------

@router.post("/projects/{pid}/files/{fid}/photos", status_code=201)
async def upload_part_photo(
    pid: str,
    fid: str,
    file: UploadFile,
    request: Request,
    payload: dict = Depends(require_auth),
    _rl: None = Depends(rate_limit(max_per_window=60, window_seconds=60, key_prefix="api:photos")),
):
    """Upload a photo for a library Part file.

    Stores the raw bytes under a storage key and appends the key to the
    Part's ``photos`` array in the JSON content. The first photo is
    auto-promoted as the primary photo.

    Returns ``{"storage_key": "<key>", "photos": [...]}``.
    """
    user_id = payload.get("sub")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        ws_id = await project_workspace_id(pid)
        if not ws_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
        role = await get_user_workspace_role(conn, ws_id, user_id)
        if not role or role == "viewer":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="viewer cannot upload photos")

        row = await conn.fetchrow(
            "SELECT id, kind, content FROM files WHERE id = $1 AND project_id = $2 AND deleted_at IS NULL",
            fid, pid,
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="file not found")

    storage_inst = get_storage_required()
    content_bytes = await file.read()
    ext = (file.filename or "photo.jpg").rsplit(".", 1)[-1].lower()
    storage_key = f"photos/{pid}/{fid}/{uuid.uuid4()}.{ext}"
    await storage_inst.put(storage_key, content_bytes, content_type=file.content_type or "image/jpeg")

    async with pool.acquire() as conn:
        # Parse existing content JSON; append new photo key.
        try:
            content_obj = json.loads(row["content"] or "{}")
        except Exception:
            content_obj = {}
        photos = content_obj.get("photos") or []
        photos.append(storage_key)
        content_obj["photos"] = photos
        await conn.execute(
            "UPDATE files SET content = $1, updated_at = now() WHERE id = $2",
            json.dumps(content_obj),
            fid,
        )

    return {"storage_key": storage_key, "photos": photos}
