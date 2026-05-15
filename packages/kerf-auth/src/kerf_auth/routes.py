import asyncio
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

import asyncpg
import bcrypt
import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Cookie
from pydantic import BaseModel
from urllib.parse import urlencode, urlparse

from kerf_core.config import get_settings
from kerf_core.db.connection import get_pool_required
from kerf_core.db.queries import users as users_queries
from kerf_core.db.queries import workspaces as workspaces_queries
from kerf_core.db.queries import refresh_tokens as rt_queries
from kerf_core.db.queries import api_tokens as api_tokens_queries
from kerf_core.dependencies import require_auth

router = APIRouter()
api_tokens_router = APIRouter()
settings = get_settings()


def random_nonce() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(16)).decode().rstrip("=")


def hash_password(password: str) -> str:
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


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    avatar_url: str
    account_role: str
    is_system: bool
    created_at: datetime


class WorkspaceResponse(BaseModel):
    id: str
    slug: str
    name: str
    avatar_url: Optional[str] = None
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserResponse
    default_workspace: Optional[WorkspaceResponse] = None


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class CreateTokenRequest(BaseModel):
    name: str


class TokenResponse(BaseModel):
    id: str
    name: str
    token: Optional[str] = None
    scopes: list[str]
    created_at: datetime


async def create_personal_workspace(conn: asyncpg.Connection, user_id: str, display_name: str) -> Optional[dict]:
    slug = f"personal-{user_id[:8]}-{secrets.token_hex(4)}"
    slug = slug.lower()
    try:
        workspace = await workspaces_queries.create_workspace(conn, slug, display_name, user_id)
        await workspaces_queries.add_workspace_member(conn, workspace["id"], user_id, "owner")
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


def user_to_response(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["id"]),
        email=user["email"],
        name=user["name"],
        avatar_url=user["avatar_url"] or "",
        account_role=user["account_role"],
        is_system=user["is_system"],
        created_at=user["created_at"],
    )


def workspace_to_response(ws: dict) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=str(ws["id"]),
        slug=ws["slug"],
        name=ws["name"],
        avatar_url=ws.get("avatar_url"),
        created_at=ws["created_at"],
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, response: Response):
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        email = req.email.strip().lower()
        if not email or not req.password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email and password are required")
        if len(req.password) < 8:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password must be at least 8 characters")

        password_hash = hash_password(req.password)

        try:
            user = await users_queries.create_user(conn, email, req.name, password_hash)
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")

        display_name = req.name
        if not display_name:
            at_idx = email.find("@")
            if at_idx > 0:
                display_name = email[:at_idx]
            else:
                display_name = "My"
        await create_personal_workspace(conn, str(user["id"]), display_name)

        access_token, refresh_token = await issue_tokens(conn, str(user["id"]))
        default_ws, _ = await get_default_workspace(conn, str(user["id"]))

        # Fire-and-forget onboarding welcome email via kerf-cloud provider layer.
        # Wrapped in try/except so a misconfigured mailer never blocks signup.
        try:
            from kerf_cloud.email.providers import send_email
            from kerf_cloud.email.templates import renderer as _email_renderer

            _msg = _email_renderer.render(
                "welcome",
                email,
                {
                    "Name": display_name,
                    "AppURL": settings.cors_origin or "https://app.kerf.sh",
                },
            )
            send_email(
                to=email,
                subject=_msg.Subject,
                html=_msg.HTML,
                text=_msg.Text,
                settings=settings,
            )
        except Exception:
            pass  # email failure must never fail registration

        response.status_code = status.HTTP_201_CREATED
        return AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_to_response(user),
            default_workspace=workspace_to_response(default_ws) if default_ws else None,
        )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        email = req.email.strip().lower()
        user = await users_queries.get_user_by_email(conn, email)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

        if not user["password_hash"] or not check_password(user["password_hash"], req.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

        access_token, refresh_token = await issue_tokens(conn, str(user["id"]))

        default_ws, ws_exists = await get_default_workspace(conn, str(user["id"]))
        if not ws_exists:
            display = user["name"].strip()
            if not display:
                at_idx = email.find("@")
                if at_idx > 0:
                    display = email[:at_idx]
                else:
                    display = "My"
            default_ws = await create_personal_workspace(conn, str(user["id"]), display)

        return AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_to_response(user),
            default_workspace=workspace_to_response(default_ws) if default_ws else None,
        )


@router.post("/refresh", response_model=AuthResponse)
async def refresh(req: RefreshRequest):
    if not req.refresh_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid body")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        token_hash = hash_token(req.refresh_token)
        rt = await rt_queries.get_refresh_token(conn, token_hash)
        if not rt:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")

        await rt_queries.revoke_refresh_token(conn, token_hash)
        new_access, new_refresh = await issue_tokens(conn, str(rt["user_id"]))

        user = await users_queries.get_user(conn, rt["user_id"])
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")

        default_ws, _ = await get_default_workspace(conn, str(user["id"]))

        return AuthResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            user=user_to_response(user),
            default_workspace=workspace_to_response(default_ws) if default_ws else None,
        )


@router.post("/logout")
async def logout(req: RefreshRequest, response: Response):
    if req.refresh_token:
        pool = await get_pool_required()
        async with pool.acquire() as conn:
            token_hash = hash_token(req.refresh_token)
            await rt_queries.revoke_refresh_token(conn, token_hash)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/github/login/start")
async def github_login_start(request: Request):
    """Sign in with GitHub — login/signup entry point.

    Separate from the kerf-cloud /auth/github/start repo-connect flow
    (scope=repo, requires an already-authenticated user). This route uses
    scope=read:user user:email and finds-or-creates the Kerf account.
    """
    if not settings.cloud_github_client_id or not settings.cloud_github_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="github oauth not configured",
        )

    redirect = request.query_params.get("redirect", "")
    state = json.dumps({"n": random_nonce(), "r": redirect})
    encoded_state = base64.urlsafe_b64encode(state.encode()).decode().rstrip("=")

    # Derive the callback URL from cloud_github_redirect_url's scheme+host,
    # but always point at the login callback path (not the repo-connect one).
    parsed = urlparse(settings.cloud_github_redirect_url)
    login_callback_url = f"{parsed.scheme}://{parsed.netloc}/auth/github/login/callback"

    params = {
        "client_id": settings.cloud_github_client_id,
        "redirect_uri": login_callback_url,
        "scope": "read:user user:email",
        "state": encoded_state,
    }
    url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    response = Response(status_code=status.HTTP_302_FOUND)
    response.headers["Location"] = url
    response.set_cookie(
        key="kerf_github_login_state",
        value=encoded_state,
        path="/",
        httponly=True,
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/github/login/callback")
async def github_login_callback(request: Request):
    """GitHub OAuth callback for login/signup (mirrors google_callback)."""
    if not settings.cloud_github_client_id or not settings.cloud_github_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="github oauth not configured",
        )

    state_cookie = request.cookies.get("kerf_github_login_state")
    state_param = request.query_params.get("state", "")

    frontend = settings.cors_origin
    if frontend == "*":
        frontend = "http://localhost:5173"

    # GitHub sends ?error=access_denied when user clicks "Cancel".
    error_param = request.query_params.get("error", "")
    if error_param:
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": f"{frontend}/auth/callback?error=github_denied"},
        )

    if not state_param or state_param != state_cookie:
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": f"{frontend}/auth/callback?error=github_state"},
        )

    code = request.query_params.get("code")
    if not code:
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": f"{frontend}/auth/callback?error=github_state"},
        )

    parsed = urlparse(settings.cloud_github_redirect_url)
    login_callback_url = f"{parsed.scheme}://{parsed.netloc}/auth/github/login/callback"

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "code": code,
                "client_id": settings.cloud_github_client_id,
                "client_secret": settings.cloud_github_client_secret,
                "redirect_uri": login_callback_url,
            },
        )

    if token_resp.status_code >= 400:
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": f"{frontend}/auth/callback?error=github_state"},
        )

    token_data = token_resp.json()
    gh_access_token = token_data.get("access_token")
    if not gh_access_token:
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": f"{frontend}/auth/callback?error=missing_tokens"},
        )

    async with httpx.AsyncClient() as client:
        user_resp, emails_resp = await asyncio.gather(
            client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {gh_access_token}",
                    "Accept": "application/vnd.github+json",
                },
            ),
            client.get(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {gh_access_token}",
                    "Accept": "application/vnd.github+json",
                },
            ),
        )

    if user_resp.status_code >= 400 or emails_resp.status_code >= 400:
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": f"{frontend}/auth/callback?error=github_state"},
        )

    gh_user = user_resp.json()
    github_id = str(gh_user.get("id", ""))
    name = gh_user.get("name") or gh_user.get("login") or ""
    avatar_url = gh_user.get("avatar_url") or ""

    # Pick primary verified email; fall back to first verified, then any.
    emails_list = emails_resp.json() if isinstance(emails_resp.json(), list) else []
    email = ""
    for entry in emails_list:
        if entry.get("primary") and entry.get("verified"):
            email = entry["email"].strip().lower()
            break
    if not email:
        for entry in emails_list:
            if entry.get("verified"):
                email = entry["email"].strip().lower()
                break
    if not email and emails_list:
        email = emails_list[0].get("email", "").strip().lower()

    if not email:
        return Response(
            status_code=status.HTTP_302_FOUND,
            headers={"Location": f"{frontend}/auth/callback?error=github_state"},
        )

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        # Try to find by github_id first, then by email; create if new.
        row = await conn.fetchrow(
            """
            UPDATE users SET
                name = COALESCE(NULLIF($2, ''), name),
                avatar_url = COALESCE(NULLIF($3, ''), avatar_url)
            WHERE github_id = $1
            RETURNING id, email, name, avatar_url, account_role, is_system, created_at
            """,
            github_id, name, avatar_url,
        )
        if row:
            user = dict(row)
        else:
            row = await conn.fetchrow(
                """
                UPDATE users SET
                    github_id = $1,
                    name = COALESCE(NULLIF($3, ''), name),
                    avatar_url = COALESCE(NULLIF($4, ''), avatar_url)
                WHERE email = $2
                RETURNING id, email, name, avatar_url, account_role, is_system, created_at
                """,
                github_id, email, name, avatar_url,
            )
            if row:
                user = dict(row)
            else:
                row = await conn.fetchrow(
                    """
                    INSERT INTO users (email, github_id, name, avatar_url)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, email, name, avatar_url, account_role, is_system, created_at
                    """,
                    email, github_id, name, avatar_url,
                )
                user = dict(row)
                display = name
                if not display:
                    at_idx = email.find("@")
                    if at_idx > 0:
                        display = email[:at_idx]
                    else:
                        display = "My"
                await create_personal_workspace(conn, str(user["id"]), display)

        access_token_jwt, refresh_token = await issue_tokens(conn, str(user["id"]))

        dest = f"{frontend}/auth/callback?access_token={access_token_jwt}&refresh_token={refresh_token}"

        response = Response(status_code=status.HTTP_302_FOUND)
        response.headers["Location"] = dest
        return response


@router.get("/google/start")
async def google_start(request: Request):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="google oauth not configured")

    redirect = request.query_params.get("redirect", "")
    state = json.dumps({"n": random_nonce(), "r": redirect})
    encoded_state = base64.urlsafe_b64encode(state.encode()).decode().rstrip("=")

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_url,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "state": encoded_state,
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    response = Response(status_code=status.HTTP_302_FOUND)
    response.headers["Location"] = url
    response.set_cookie(
        key="kerf_oauth_state",
        value=encoded_state,
        path="/",
        httponly=True,
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/google/callback")
async def google_callback(request: Request):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="google oauth not configured")

    state_cookie = request.cookies.get("kerf_oauth_state")
    state_param = request.query_params.get("state", "")

    if not state_param or state_param != state_cookie:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="state mismatch")

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing code")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_url,
                "grant_type": "authorization_code",
            },
        )

    if token_resp.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="oauth exchange failed")

    token_data = token_resp.json()
    access_token_google = token_data.get("access_token")

    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token_google}"},
        )

    if userinfo_resp.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="userinfo fetch failed")

    user_info = userinfo_resp.json()
    google_sub = user_info.get("sub", "")
    email = user_info.get("email", "").strip().lower()
    name = user_info.get("name", "")
    picture = user_info.get("picture", "")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users SET
                name = COALESCE(NULLIF($2, ''), name),
                avatar_url = COALESCE(NULLIF($3, ''), avatar_url)
            WHERE google_id = $1
            RETURNING id, email, name, avatar_url, account_role, is_system, created_at
            """,
            google_sub, name, picture,
        )
        if row:
            user = dict(row)
        else:
            row = await conn.fetchrow(
                """
                UPDATE users SET
                    google_id = $1,
                    name = COALESCE(NULLIF($3, ''), name),
                    avatar_url = COALESCE(NULLIF($4, ''), avatar_url)
                WHERE email = $2
                RETURNING id, email, name, avatar_url, account_role, is_system, created_at
                """,
                google_sub, email, name, picture,
            )
            if row:
                user = dict(row)
            else:
                row = await conn.fetchrow(
                    """
                    INSERT INTO users (email, google_id, name, avatar_url)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, email, name, avatar_url, account_role, is_system, created_at
                    """,
                    email, google_sub, name, picture,
                )
                user = dict(row)
                display = name
                if not display:
                    at_idx = email.find("@")
                    if at_idx > 0:
                        display = email[:at_idx]
                    else:
                        display = "My"
                await create_personal_workspace(conn, str(user["id"]), display)

        access_token_jwt, _ = await issue_tokens(conn, str(user["id"]))

        frontend = settings.cors_origin
        if frontend == "*":
            frontend = "http://localhost:5173"
        dest = f"{frontend}/auth/callback?access_token={access_token_jwt}"

        response = Response(status_code=status.HTTP_302_FOUND)
        response.headers["Location"] = dest
        return response


@router.post("/bootstrap-local", response_model=AuthResponse)
async def bootstrap_local(response: Response):
    if not settings.local_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    email = settings.system_user_email.strip().lower() if settings.system_user_email else "local@kerf.local"
    name = settings.system_user_name.strip() if settings.system_user_name else "Local"

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        user = await users_queries.get_user_by_email(conn, email)
        if not user:
            try:
                user = await users_queries.create_user(conn, email, name, None, None)
                user = dict(user)
            except asyncpg.UniqueViolationError:
                user = await users_queries.get_user_by_email(conn, email)

        if not user:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="failed to create or find user")

        access_token, refresh_token = await issue_tokens(conn, str(user["id"]))
        default_ws, _ = await get_default_workspace(conn, str(user["id"]))

        return AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_to_response(user),
            default_workspace=workspace_to_response(default_ws) if default_ws else None,
        )


def generate_api_token() -> str:
    return secrets.token_urlsafe(32)


@api_tokens_router.post("/api-tokens", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def create_api_token(request: Request, req: CreateTokenRequest, payload: dict = Depends(require_auth)):
    if not req.name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")

    user_id = payload.get("sub")
    workspace_id = getattr(request.state, "workspace_id", None)

    if not workspace_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="workspace context required")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        token = generate_api_token()
        token_hash = hash_token(token)
        scopes = ["workspace:member-role"]
        result = await api_tokens_queries.create_api_token(conn, workspace_id, user_id, token_hash, req.name, scopes)
        return TokenResponse(
            id=str(result["id"]),
            name=result["name"],
            token=token,
            scopes=result["scopes"] or [],
            created_at=result["created_at"],
        )


@api_tokens_router.get("/api-tokens", response_model=list[TokenResponse])
async def list_api_tokens(request: Request, payload: dict = Depends(require_auth)):
    user_id = payload.get("sub")
    workspace_id = getattr(request.state, "workspace_id", None)

    if not workspace_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="workspace context required")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        tokens = await api_tokens_queries.list_api_tokens(conn, workspace_id, user_id)
        return [
            TokenResponse(
                id=str(t["id"]),
                name=t["name"],
                scopes=t["scopes"] or [],
                created_at=t["created_at"],
            )
            for t in tokens
        ]


@api_tokens_router.delete("/api-tokens/{token_id}")
async def revoke_api_token(request: Request, token_id: str, payload: dict = Depends(require_auth)):
    workspace_id = getattr(request.state, "workspace_id", None)

    if not workspace_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="workspace context required")

    pool = await get_pool_required()
    async with pool.acquire() as conn:
        await api_tokens_queries.revoke_api_token(conn, token_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
