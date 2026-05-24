import hashlib
import jwt
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from kerf_core.config import get_settings

settings = get_settings()
security = HTTPBearer(auto_error=False)

API_TOKEN_PREFIX = "kerf_sk_"


class UserContext:
    def __init__(self, user_id: str, workspace_id: Optional[str] = None, scopes: Optional[list[str]] = None):
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.scopes = scopes or []


class APITokenMeta:
    def __init__(self, user_id: str, workspace_id: Optional[str] = None, scopes: Optional[list[str]] = None):
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.scopes = scopes or []


def decode_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_ttl_minutes)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


async def _resolve_api_token(request: Request, token: str) -> dict:
    from kerf_core.db.connection import get_pool_required
    from kerf_core.db.queries import api_tokens as api_tokens_queries

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        row = await api_tokens_queries.get_api_token_by_hash(conn, token_hash)
    if not row or row.get("revoked_at"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api token")

    request.state.workspace_id = str(row["workspace_id"])
    request.state.scopes = row.get("scopes") or []
    return {"sub": str(row["user_id"]), "workspace_id": str(row["workspace_id"]), "scopes": row.get("scopes") or []}


async def optional_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    if credentials is None:
        return None
    token = credentials.credentials
    if token.startswith(API_TOKEN_PREFIX):
        try:
            return await _resolve_api_token(request, token)
        except HTTPException:
            return None
    try:
        return decode_jwt(token)
    except HTTPException:
        return None


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    if token.startswith(API_TOKEN_PREFIX):
        return await _resolve_api_token(request, token)
    return decode_jwt(token)


async def get_user_id(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = auth_header[7:]
    payload = decode_jwt(token)
    return payload.get("sub", "")


async def get_workspace_id(request: Request) -> Optional[str]:
    return getattr(request.state, "workspace_id", None)


async def get_token_scopes(request: Request) -> list[str]:
    return getattr(request.state, "scopes", [])


def has_scope(request: Request, required: str) -> bool:
    scopes = getattr(request.state, "scopes", [])
    return required in scopes


def rate_limit(
    max_per_window: int,
    window_seconds: int = 60,
    key_prefix: str = "",
) -> "callable":
    """Build a FastAPI dependency that enforces a rate limit.

    Key composition: ``f"{key_prefix}:{user_id_or_ip}"``.

    Use after ``require_auth`` so ``user_id`` is available when the caller
    is authenticated. For unauthenticated endpoints (login, register) the
    key falls back to the client IP.

    Example::

        @router.post("/auth/login")
        async def login(
            req: LoginRequest,
            _: None = Depends(rate_limit(10, 60, "auth:login")),
        ):
            ...
    """
    from fastapi import Request

    async def _dep(request: Request) -> None:
        from kerf_core.db.connection import get_pool_required
        from kerf_core.rate_limit import enforce

        # Try authenticated user_id first; fall back to client IP.
        user_id: Optional[str] = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token = auth_header[7:]
                if not token.startswith(API_TOKEN_PREFIX):
                    payload = decode_jwt(token)
                    user_id = payload.get("sub")
            except HTTPException:
                pass

        if user_id:
            caller = user_id
        else:
            # X-Forwarded-For is set by Koyeb / Fly.io / nginx; fall back to direct IP.
            forwarded = request.headers.get("X-Forwarded-For", "")
            caller = forwarded.split(",")[0].strip() if forwarded else (
                request.client.host if request.client else "unknown"
            )

        bucket = f"{key_prefix}:{caller}" if key_prefix else caller

        pool = await get_pool_required()
        await enforce(pool, bucket, max_per_window, window_seconds)

    return _dep
