"""Scalability hardening regression tests.

Covers the five items from the 2026-05-24 scalability audit:
1. files(kind) index present in baseline migration
2. DB pool max_size env-configurable via KERF_DB_MAX_CONNS
3. _load_llm_history bounded by LIMIT (no unbounded scan)
4. S3 multipart state DB-backed path (schema columns present)
5. Request body size limit middleware wired into create_app
"""
from __future__ import annotations

import importlib
import os
import pathlib
import re
import sys
import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────

_BASELINE_0001 = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src/kerf_core/db/migrations/0001_core_identity.sql"
).read_text()

_BASELINE_0002 = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src/kerf_core/db/migrations/0002_project_ingestion.sql"
).read_text()

_UPLOAD_SESSIONS_QUERIES = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src/kerf_core/db/queries/upload_sessions.py"
).read_text()

_APP_SRC = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src/kerf_core/app.py"
).read_text()

_CONNECTION_SRC = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src/kerf_core/db/connection.py"
).read_text()


# ═══════════════════════════════════════════════════════
# 1. files(kind) index
# ═══════════════════════════════════════════════════════

def test_files_kind_index_in_baseline():
    """CREATE INDEX on files(kind) must be in 0001_core_identity.sql."""
    assert re.search(
        r"create\s+index\s+if\s+not\s+exists\s+files_kind_idx\s+on\s+files\s*\(\s*kind\s*\)",
        _BASELINE_0001, re.I,
    ), "files_kind_idx index missing from 0001_core_identity.sql"


def test_no_alter_table_add_files_kind_index():
    """No ALTER TABLE shim for files(kind) — must be folded into baseline."""
    migrations_dir = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src/kerf_core/db/migrations"
    )
    forbidden = re.compile(r"create\s+index.*files_kind", re.I)
    for f in sorted(migrations_dir.glob("*.sql")):
        if f.name == "0001_core_identity.sql":
            continue
        m = forbidden.search(f.read_text())
        assert m is None, (
            f"{f.name} contains a files_kind index outside the baseline migration."
        )


# ═══════════════════════════════════════════════════════
# 2. DB pool env-configurable
# ═══════════════════════════════════════════════════════

def test_connection_py_reads_kerf_db_max_conns_env():
    """create_pool_from_config must consult KERF_DB_MAX_CONNS."""
    assert "KERF_DB_MAX_CONNS" in _CONNECTION_SRC, (
        "connection.py does not reference KERF_DB_MAX_CONNS env var"
    )


@pytest.mark.asyncio
async def test_create_pool_from_config_uses_env_max_conns(monkeypatch):
    """When KERF_DB_MAX_CONNS=5, create_pool_from_config must pass max_size=5."""
    monkeypatch.setenv("KERF_DB_MAX_CONNS", "5")

    created_kwargs: dict = {}

    async def fake_create_pool(dsn, **kwargs):
        created_kwargs.update(kwargs)
        pool = MagicMock()
        pool.close = AsyncMock()
        return pool

    import kerf_core.db.connection as conn_mod
    with patch.object(conn_mod.asyncpg, "create_pool", new=fake_create_pool):
        cfg = MagicMock()
        cfg.database_url = "postgres://localhost/test"
        cfg.db_max_conns = 10  # default — env should win
        await conn_mod.create_pool_from_config(cfg)

    assert created_kwargs.get("max_size") == 5, (
        f"Expected max_size=5 from env, got {created_kwargs.get('max_size')}"
    )


@pytest.mark.asyncio
async def test_create_pool_from_config_default_max_conns(monkeypatch):
    """Without KERF_DB_MAX_CONNS set, default of 10 is used."""
    monkeypatch.delenv("KERF_DB_MAX_CONNS", raising=False)

    created_kwargs: dict = {}

    async def fake_create_pool(dsn, **kwargs):
        created_kwargs.update(kwargs)
        pool = MagicMock()
        pool.close = AsyncMock()
        return pool

    import kerf_core.db.connection as conn_mod
    with patch.object(conn_mod.asyncpg, "create_pool", new=fake_create_pool):
        cfg = MagicMock()
        cfg.database_url = "postgres://localhost/test"
        cfg.db_max_conns = 10
        await conn_mod.create_pool_from_config(cfg)

    assert created_kwargs.get("max_size") == 10


# ═══════════════════════════════════════════════════════
# 3. Unbounded chat history — _load_llm_history has LIMIT
# ═══════════════════════════════════════════════════════

def test_load_llm_history_has_limit():
    """_load_llm_history SQL must contain a LIMIT clause."""
    routes_src = (
        pathlib.Path(__file__).resolve().parents[3]
        / "packages/kerf-api/src/kerf_api/routes.py"
    ).read_text()

    # Find the _load_llm_history function body
    fn_start = routes_src.index("async def _load_llm_history(")
    # Take enough text — function is ~60 lines
    fn_body = routes_src[fn_start: fn_start + 2000]

    assert "LIMIT" in fn_body.upper(), (
        "_load_llm_history does not contain a LIMIT — chat history is unbounded"
    )


def test_load_llm_history_uses_env_limit():
    """_CHAT_HISTORY_LIMIT must be env-configurable (KERF_CHAT_HISTORY_LIMIT)."""
    routes_src = (
        pathlib.Path(__file__).resolve().parents[3]
        / "packages/kerf-api/src/kerf_api/routes.py"
    ).read_text()
    assert "KERF_CHAT_HISTORY_LIMIT" in routes_src, (
        "KERF_CHAT_HISTORY_LIMIT env var not referenced in routes.py"
    )


# ═══════════════════════════════════════════════════════
# 4. S3 multipart state — DB columns in upload_sessions
# ═══════════════════════════════════════════════════════

def test_upload_sessions_has_s3_upload_id_column():
    """upload_sessions CREATE TABLE must include s3_upload_id column."""
    assert re.search(r"\bs3_upload_id\b", _BASELINE_0002, re.I), (
        "s3_upload_id column missing from upload_sessions in 0002_project_ingestion.sql"
    )


def test_upload_sessions_has_s3_parts_column():
    """upload_sessions CREATE TABLE must include s3_parts jsonb column."""
    assert re.search(r"\bs3_parts\b", _BASELINE_0002, re.I), (
        "s3_parts column missing from upload_sessions in 0002_project_ingestion.sql"
    )


def test_upload_sessions_has_s3_temp_key_column():
    """upload_sessions CREATE TABLE must include s3_temp_key column."""
    assert re.search(r"\bs3_temp_key\b", _BASELINE_0002, re.I), (
        "s3_temp_key column missing from upload_sessions in 0002_project_ingestion.sql"
    )


def test_upload_sessions_queries_has_init_s3_multipart():
    """upload_sessions.py must export init_s3_multipart helper."""
    assert "init_s3_multipart" in _UPLOAD_SESSIONS_QUERIES, (
        "init_s3_multipart function missing from upload_sessions.py"
    )


def test_upload_sessions_queries_has_append_s3_part():
    """upload_sessions.py must export append_s3_part helper."""
    assert "append_s3_part" in _UPLOAD_SESSIONS_QUERIES


def test_upload_sessions_queries_has_get_s3_multipart_state():
    """upload_sessions.py must export get_s3_multipart_state helper."""
    assert "get_s3_multipart_state" in _UPLOAD_SESSIONS_QUERIES


def test_s3_put_chunk_accepts_conn_and_session_id():
    """S3Storage.put_chunk must accept conn and session_id kwargs."""
    s3_src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src/kerf_core/storage/s3.py"
    ).read_text()
    assert "session_id" in s3_src, "s3.py put_chunk does not accept session_id"
    assert "conn" in s3_src, "s3.py put_chunk does not accept conn"


# ═══════════════════════════════════════════════════════
# 5. Request body size limit middleware
# ═══════════════════════════════════════════════════════

def test_body_size_middleware_defined_in_app():
    """_BodySizeLimitMiddleware must be defined in app.py."""
    assert "_BodySizeLimitMiddleware" in _APP_SRC, (
        "_BodySizeLimitMiddleware class not found in app.py"
    )


def test_body_size_middleware_registered_in_create_app():
    """create_app must add _BodySizeLimitMiddleware."""
    assert "add_middleware(_BodySizeLimitMiddleware" in _APP_SRC, (
        "_BodySizeLimitMiddleware not wired via add_middleware in create_app"
    )


def test_body_size_env_var_configurable():
    """KERF_MAX_BODY_BYTES must be read in app.py."""
    assert "KERF_MAX_BODY_BYTES" in _APP_SRC, (
        "KERF_MAX_BODY_BYTES env var not referenced in app.py"
    )


@pytest.mark.asyncio
async def test_body_size_middleware_rejects_oversized_request():
    """_BodySizeLimitMiddleware must return 413 when Content-Length > limit."""
    from kerf_core.app import _BodySizeLimitMiddleware
    from starlette.testclient import TestClient
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(_BodySizeLimitMiddleware, max_bytes=100)

    @app.post("/upload")
    async def upload():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    # Provide Content-Length header exceeding the limit
    resp = client.post(
        "/upload",
        content=b"x" * 10,
        headers={"content-length": "200"},
    )
    assert resp.status_code == 413, f"Expected 413, got {resp.status_code}"


@pytest.mark.asyncio
async def test_body_size_middleware_passes_normal_request():
    """_BodySizeLimitMiddleware must not block requests within the limit."""
    from kerf_core.app import _BodySizeLimitMiddleware
    from starlette.testclient import TestClient
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(_BodySizeLimitMiddleware, max_bytes=1024)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/ping")
    assert resp.status_code == 200
