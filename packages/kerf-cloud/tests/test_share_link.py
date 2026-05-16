"""Hermetic tests for kerf_cloud.share_link.

All tests use a temp directory so no real data/cloud/share/* files are written.
"""
from __future__ import annotations

import os
import time
import pytest

# ---------------------------------------------------------------------------
# Fixtures: redirect storage to a temp dir
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_share_dir(tmp_path, monkeypatch):
    share_dir = tmp_path / "share"
    share_dir.mkdir()
    monkeypatch.setenv("KERF_SHARE_DIR", str(share_dir))
    yield share_dir


# Reload module after env-var is set so _store_dir() picks up the patch.
@pytest.fixture(autouse=True)
def fresh_module(tmp_share_dir):
    import importlib
    import kerf_cloud.share_link as m
    importlib.reload(m)
    yield m


@pytest.fixture()
def sl(fresh_module):
    return fresh_module


# ---------------------------------------------------------------------------
# 1. create_share returns a non-empty token string
# ---------------------------------------------------------------------------

def test_create_returns_string(sl):
    token = sl.create_share("proj-1", "rev-abc")
    assert isinstance(token, str)
    assert len(token) > 0


# ---------------------------------------------------------------------------
# 2. create→resolve round-trip preserves project_id and revision_id
# ---------------------------------------------------------------------------

def test_create_resolve_roundtrip(sl):
    token = sl.create_share("proj-1", "rev-abc")
    info = sl.resolve_share(token)
    assert info is not None
    assert info["project_id"] == "proj-1"
    assert info["revision_id"] == "rev-abc"


# ---------------------------------------------------------------------------
# 3. resolve returns allow_comments and allow_approve from create args
# ---------------------------------------------------------------------------

def test_create_resolve_permissions(sl):
    token = sl.create_share("proj-2", "rev-1", allow_comments=False, allow_approve=True)
    info = sl.resolve_share(token)
    assert info["allow_comments"] is False
    assert info["allow_approve"] is True


# ---------------------------------------------------------------------------
# 4. default permissions are allow_comments=True, allow_approve=True
# ---------------------------------------------------------------------------

def test_default_permissions(sl):
    token = sl.create_share("proj-3", "rev-1")
    info = sl.resolve_share(token)
    assert info["allow_comments"] is True
    assert info["allow_approve"] is True


# ---------------------------------------------------------------------------
# 5. Expired token is rejected (ttl_days=0 expires immediately)
# ---------------------------------------------------------------------------

def test_expired_token_rejected(sl, monkeypatch):
    token = sl.create_share("proj-4", "rev-1", ttl_days=0)
    # ttl_days=0 → expires_at = now; sleep 0.01 to ensure it is past
    time.sleep(0.05)
    assert sl.resolve_share(token) is None


# ---------------------------------------------------------------------------
# 6. Signing: tampered token is rejected
# ---------------------------------------------------------------------------

def test_tampered_token_rejected(sl):
    token = sl.create_share("proj-5", "rev-1")
    # Flip the last character of the raw part
    raw, sig = token.rsplit(".", 1)
    bad_raw = raw[:-1] + ("z" if raw[-1] != "z" else "a")
    bad_token = f"{bad_raw}.{sig}"
    assert sl.resolve_share(bad_token) is None


# ---------------------------------------------------------------------------
# 7. Signing: tampered signature is rejected
# ---------------------------------------------------------------------------

def test_tampered_signature_rejected(sl):
    token = sl.create_share("proj-6", "rev-1")
    raw, _ = token.rsplit(".", 1)
    bad_token = f"{raw}.{'x' * 16}"
    assert sl.resolve_share(bad_token) is None


# ---------------------------------------------------------------------------
# 8. Completely fabricated token is rejected
# ---------------------------------------------------------------------------

def test_fabricated_token_rejected(sl):
    assert sl.resolve_share("notavalidtoken") is None
    assert sl.resolve_share("abc.def") is None


# ---------------------------------------------------------------------------
# 9. add_comment appends to comment list
# ---------------------------------------------------------------------------

def test_add_comment_appends(sl):
    token = sl.create_share("proj-7", "rev-1")
    ok = sl.add_comment(token, "Alice", "Looks beautiful!")
    assert ok is True
    comments = sl.get_comments(token)
    assert len(comments) == 1
    assert comments[0]["body"] == "Looks beautiful!"
    assert comments[0]["customer_name"] == "Alice"


# ---------------------------------------------------------------------------
# 10. Multiple comments accumulate in order
# ---------------------------------------------------------------------------

def test_multiple_comments_accumulate(sl):
    token = sl.create_share("proj-8", "rev-1")
    sl.add_comment(token, "Alice", "First comment")
    sl.add_comment(token, "Bob", "Second comment")
    comments = sl.get_comments(token)
    assert len(comments) == 2
    assert comments[0]["customer_name"] == "Alice"
    assert comments[1]["customer_name"] == "Bob"


# ---------------------------------------------------------------------------
# 11. add_comment fails when allow_comments=False
# ---------------------------------------------------------------------------

def test_add_comment_blocked_when_not_allowed(sl):
    token = sl.create_share("proj-9", "rev-1", allow_comments=False)
    ok = sl.add_comment(token, "Alice", "Hello!")
    assert ok is False
    assert sl.get_comments(token) == []


# ---------------------------------------------------------------------------
# 12. add_comment fails for empty body
# ---------------------------------------------------------------------------

def test_add_comment_empty_body_rejected(sl):
    token = sl.create_share("proj-10", "rev-1")
    assert sl.add_comment(token, "Alice", "") is False
    assert sl.add_comment(token, "Alice", "   ") is False


# ---------------------------------------------------------------------------
# 13. record_approval stores approval
# ---------------------------------------------------------------------------

def test_record_approval_stores(sl):
    token = sl.create_share("proj-11", "rev-1")
    ok = sl.record_approval(token, "Alice", "Alice Smith")
    assert ok is True
    approvals = sl.get_approvals(token)
    assert len(approvals) == 1
    assert approvals[0]["customer_name"] == "Alice"
    assert approvals[0]["signature"] == "Alice Smith"


# ---------------------------------------------------------------------------
# 14. record_approval fails when allow_approve=False
# ---------------------------------------------------------------------------

def test_record_approval_blocked_when_not_allowed(sl):
    token = sl.create_share("proj-12", "rev-1", allow_approve=False)
    ok = sl.record_approval(token, "Alice", "Alice Smith")
    assert ok is False
    assert sl.get_approvals(token) == []


# ---------------------------------------------------------------------------
# 15. record_approval fails for empty signature
# ---------------------------------------------------------------------------

def test_record_approval_empty_sig_rejected(sl):
    token = sl.create_share("proj-13", "rev-1")
    assert sl.record_approval(token, "Alice", "") is False
    assert sl.record_approval(token, "Alice", "   ") is False


# ---------------------------------------------------------------------------
# 16. revoke_share makes resolve return None
# ---------------------------------------------------------------------------

def test_revoke_makes_resolve_fail(sl):
    token = sl.create_share("proj-14", "rev-1")
    assert sl.resolve_share(token) is not None
    ok = sl.revoke_share(token)
    assert ok is True
    assert sl.resolve_share(token) is None


# ---------------------------------------------------------------------------
# 17. add_comment fails after revocation
# ---------------------------------------------------------------------------

def test_comment_fails_after_revoke(sl):
    token = sl.create_share("proj-15", "rev-1")
    sl.revoke_share(token)
    assert sl.add_comment(token, "Alice", "Too late") is False


# ---------------------------------------------------------------------------
# 18. approval fails after revocation
# ---------------------------------------------------------------------------

def test_approval_fails_after_revoke(sl):
    token = sl.create_share("proj-16", "rev-1")
    sl.revoke_share(token)
    assert sl.record_approval(token, "Alice", "sig") is False


# ---------------------------------------------------------------------------
# 19. Two create_share calls produce distinct tokens
# ---------------------------------------------------------------------------

def test_distinct_tokens(sl):
    t1 = sl.create_share("proj-17", "rev-1")
    t2 = sl.create_share("proj-17", "rev-1")
    assert t1 != t2


# ---------------------------------------------------------------------------
# 20. Token has URL-safe characters only (no +, / or =)
# ---------------------------------------------------------------------------

def test_token_url_safe(sl):
    for _ in range(10):
        token = sl.create_share("proj-18", "rev-1")
        assert token is not None
        for ch in token:
            assert ch not in ("+", "/", "="), f"non URL-safe char {ch!r} in {token!r}"


# ---------------------------------------------------------------------------
# 21. metadata is round-tripped through resolve
# ---------------------------------------------------------------------------

def test_metadata_roundtrip(sl):
    meta = {"piece_type": "ring", "metal": "18k_yellow", "total": 1234.56}
    token = sl.create_share("proj-19", "rev-1", metadata=meta)
    info = sl.resolve_share(token)
    assert info["metadata"] == meta


# ---------------------------------------------------------------------------
# 22. get_comments on invalid token returns empty list (never raises)
# ---------------------------------------------------------------------------

def test_get_comments_invalid_token_returns_empty(sl):
    result = sl.get_comments("totally.invalid")
    assert result == []


# ---------------------------------------------------------------------------
# 23. get_approvals on invalid token returns empty list (never raises)
# ---------------------------------------------------------------------------

def test_get_approvals_invalid_token_returns_empty(sl):
    result = sl.get_approvals("totally.invalid")
    assert result == []


# ---------------------------------------------------------------------------
# 24. revoke_share returns False for unknown / invalid token
# ---------------------------------------------------------------------------

def test_revoke_unknown_token_returns_false(sl):
    assert sl.revoke_share("totally.invalid") is False


# ---------------------------------------------------------------------------
# 25. ttl_days=1 token is valid immediately and has created_at in resolve
# ---------------------------------------------------------------------------

def test_valid_token_has_created_at(sl):
    token = sl.create_share("proj-20", "rev-1", ttl_days=1)
    info = sl.resolve_share(token)
    assert info is not None
    assert "created_at" in info
    assert info["created_at"]  # non-empty string


# ---------------------------------------------------------------------------
# 26. comment created_at timestamp is populated
# ---------------------------------------------------------------------------

def test_comment_has_created_at(sl):
    token = sl.create_share("proj-21", "rev-1")
    sl.add_comment(token, "Carol", "Nice design")
    comments = sl.get_comments(token)
    assert "created_at" in comments[0]
    assert comments[0]["created_at"]


# ---------------------------------------------------------------------------
# 27. approval approved_at timestamp is populated
# ---------------------------------------------------------------------------

def test_approval_has_approved_at(sl):
    token = sl.create_share("proj-22", "rev-1")
    sl.record_approval(token, "Dave", "Dave Brown")
    approvals = sl.get_approvals(token)
    assert "approved_at" in approvals[0]
    assert approvals[0]["approved_at"]


# ---------------------------------------------------------------------------
# 28. JSON file is written under the configured share dir
# ---------------------------------------------------------------------------

def test_file_written_to_share_dir(sl, tmp_share_dir):
    token = sl.create_share("proj-23", "rev-1")
    expected = tmp_share_dir / f"{token}.json"
    assert expected.exists(), f"share file not found: {expected}"


# ---------------------------------------------------------------------------
# 29. resolve returns None for non-existent token with valid signature shape
# ---------------------------------------------------------------------------

def test_resolve_nonexistent_file(sl):
    # Forge a structurally valid-looking token (right format, wrong sig) that
    # doesn't have a file behind it.
    import secrets as _s
    import hashlib, hmac as _hmac
    raw = _s.token_urlsafe(12)
    sig = _hmac.new(b"wrong-key", raw.encode(), hashlib.sha256).hexdigest()[:16]
    fake_token = f"{raw}.{sig}"
    assert sl.resolve_share(fake_token) is None


# ---------------------------------------------------------------------------
# 30. Multiple approvals accumulate
# ---------------------------------------------------------------------------

def test_multiple_approvals_accumulate(sl):
    token = sl.create_share("proj-24", "rev-1")
    sl.record_approval(token, "Eve", "Eve Jones")
    sl.record_approval(token, "Frank", "Frank Lee")
    approvals = sl.get_approvals(token)
    assert len(approvals) == 2
    assert approvals[0]["customer_name"] == "Eve"
    assert approvals[1]["customer_name"] == "Frank"
