"""Customer share-link for jewelry (and any) project revisions.

A jeweller calls create_share(project_id, revision_id) → gets a short
URL-safe token that can be handed to a customer.  The customer opens
/share/<token>, sees the 3-D preview + specs + price, and can leave a
comment or approve the design.

Storage: filesystem JSON under data/cloud/share/<token>.json.
No DB dependency so the feature works in local-install mode.

All public functions follow a "never raise" contract:
    - On success return the described value.
    - On failure return None / empty dict / False (documented per function).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Storage root (overridable for tests via env-var)
# ---------------------------------------------------------------------------

def _store_dir() -> str:
    base = os.environ.get("KERF_SHARE_DIR") or os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "..", "data", "cloud", "share"
    )
    return os.path.abspath(base)


def _token_path(token: str) -> str:
    return os.path.join(_store_dir(), f"{token}.json")


# ---------------------------------------------------------------------------
# Signing helpers
# ---------------------------------------------------------------------------

_SIGN_KEY_ENV = "KERF_SHARE_SECRET"
_FALLBACK_SECRET = "kerf-share-dev-secret-change-in-prod"

def _secret() -> bytes:
    raw = os.environ.get(_SIGN_KEY_ENV) or _FALLBACK_SECRET
    return raw.encode()


def _sign(token: str) -> str:
    return hmac.new(_secret(), token.encode(), hashlib.sha256).hexdigest()[:16]


def _make_token() -> str:
    """Return a short URL-safe token with an embedded HMAC check digit."""
    raw = secrets.token_urlsafe(12)  # 16 chars after base64
    sig = _sign(raw)
    return f"{raw}.{sig}"


def _verify_token(token: str) -> bool:
    """Return True if the token's signature is valid."""
    try:
        raw, sig = token.rsplit(".", 1)
        expected = _sign(raw)
        return hmac.compare_digest(sig, expected)
    except (ValueError, Exception):
        return False


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load(token: str) -> dict | None:
    path = _token_path(token)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _save(token: str, data: dict) -> bool:
    path = _token_path(token)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_share(
    project_id: str,
    revision_id: str,
    ttl_days: int = 30,
    allow_comments: bool = True,
    allow_approve: bool = True,
    metadata: dict | None = None,
) -> str | None:
    """Create a share link and return the token.

    Returns the token string on success, None on failure.
    """
    try:
        token = _make_token()
        expires_at = _now_ts() + ttl_days * 86400
        record: dict[str, Any] = {
            "token": token,
            "project_id": project_id,
            "revision_id": revision_id,
            "created_at": _now_iso(),
            "expires_at": expires_at,
            "ttl_days": ttl_days,
            "allow_comments": allow_comments,
            "allow_approve": allow_approve,
            "revoked": False,
            "comments": [],
            "approvals": [],
            "metadata": metadata or {},
        }
        if not _save(token, record):
            return None
        return token
    except Exception:
        return None


def resolve_share(token: str) -> dict | None:
    """Resolve a token to its share record.

    Returns a dict with keys:
        project_id, revision_id, allow_comments, allow_approve, metadata

    Returns None when:
        - token signature is invalid
        - record does not exist
        - token has been revoked
        - token has expired
    """
    try:
        if not _verify_token(token):
            return None
        record = _load(token)
        if record is None:
            return None
        if record.get("revoked"):
            return None
        expires_at = record.get("expires_at", 0)
        if _now_ts() > expires_at:
            return None
        return {
            "project_id": record["project_id"],
            "revision_id": record["revision_id"],
            "allow_comments": record.get("allow_comments", True),
            "allow_approve": record.get("allow_approve", True),
            "metadata": record.get("metadata", {}),
            "created_at": record.get("created_at"),
        }
    except Exception:
        return None


def add_comment(token: str, customer_name: str, body: str) -> bool:
    """Append a customer comment to a share link.

    Returns True on success.  Returns False when:
        - token invalid / expired / revoked
        - comments not allowed on this share
        - body is empty
        - storage failure
    """
    try:
        if not body or not body.strip():
            return False
        info = resolve_share(token)
        if info is None:
            return False
        if not info.get("allow_comments"):
            return False
        record = _load(token)
        if record is None:
            return False
        comment = {
            "customer_name": customer_name or "Anonymous",
            "body": body.strip(),
            "created_at": _now_iso(),
        }
        record.setdefault("comments", []).append(comment)
        return _save(token, record)
    except Exception:
        return False


def record_approval(token: str, customer_name: str, signature: str) -> bool:
    """Record a customer approval (signature blob or free-text).

    Returns True on success.  Returns False when:
        - token invalid / expired / revoked
        - approvals not allowed on this share
        - signature is empty
        - storage failure
    """
    try:
        if not signature or not str(signature).strip():
            return False
        info = resolve_share(token)
        if info is None:
            return False
        if not info.get("allow_approve"):
            return False
        record = _load(token)
        if record is None:
            return False
        approval = {
            "customer_name": customer_name or "Anonymous",
            "signature": str(signature).strip(),
            "approved_at": _now_iso(),
        }
        record.setdefault("approvals", []).append(approval)
        return _save(token, record)
    except Exception:
        return False


def revoke_share(token: str) -> bool:
    """Revoke a share link so it can no longer be resolved.

    Returns True on success, False on failure or if the record does not exist.
    """
    try:
        if not _verify_token(token):
            return False
        record = _load(token)
        if record is None:
            return False
        record["revoked"] = True
        record["revoked_at"] = _now_iso()
        return _save(token, record)
    except Exception:
        return False


def get_comments(token: str) -> list[dict]:
    """Return the comment list for a share link.

    Returns an empty list when the token is invalid or has no comments.
    """
    try:
        if not _verify_token(token):
            return []
        record = _load(token)
        if record is None:
            return []
        return list(record.get("comments", []))
    except Exception:
        return []


def get_approvals(token: str) -> list[dict]:
    """Return the approval list for a share link.

    Returns an empty list when the token is invalid or has no approvals.
    """
    try:
        if not _verify_token(token):
            return []
        record = _load(token)
        if record is None:
            return []
        return list(record.get("approvals", []))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Optional LLM tool registration
# ---------------------------------------------------------------------------

try:
    from kerf_core.plugin import register as _register_tool  # type: ignore

    @_register_tool("share.create")
    def _tool_create_share(project_id: str, revision_id: str, ttl_days: int = 30) -> dict:
        """Create a customer share link for a jewelry project revision."""
        token = create_share(project_id, revision_id, ttl_days=ttl_days)
        if token is None:
            return {"ok": False, "error": "failed to create share link"}
        return {"ok": True, "token": token}

    @_register_tool("share.resolve")
    def _tool_resolve_share(token: str) -> dict:
        """Resolve a share token to project/revision info."""
        info = resolve_share(token)
        if info is None:
            return {"ok": False, "error": "invalid, expired, or revoked token"}
        return {"ok": True, **info}

    @_register_tool("share.add_comment")
    def _tool_add_comment(token: str, customer_name: str, body: str) -> dict:
        """Add a customer comment to a shared design."""
        ok = add_comment(token, customer_name, body)
        return {"ok": ok}

    @_register_tool("share.record_approval")
    def _tool_record_approval(token: str, customer_name: str, signature: str) -> dict:
        """Record a customer approval on a shared design."""
        ok = record_approval(token, customer_name, signature)
        return {"ok": ok}

    @_register_tool("share.revoke")
    def _tool_revoke_share(token: str) -> dict:
        """Revoke a share link."""
        ok = revoke_share(token)
        return {"ok": ok}

except (ImportError, AttributeError):
    # kerf_core.plugin tool registry is optional — share_link works standalone.
    pass
