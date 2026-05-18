"""Tests for the export / materialize spine (T-123).

Covers:
  - materialize_project_tree() with a mix of inline and blob files
  - kerf-manifest.json structure (path, kind, classification, oid, size)
  - Inline files written at their correct POSIX path inside the ZIP
  - Blob files fetched from LocalStorage and written at their correct path
  - autodetect predicate (should_store_as_blob) classifies correctly:
      * UTF-8 text file   → inline (False)
      * >1 MiB binary     → blob  (True)
      * <1 MiB binary     → blob  (True, non-UTF-8)
  - Round-trip: the existing GET /projects/{pid}/export route still returns
    a valid ZIP with a kerf-manifest.json for a project with only inline files

DB SAFETY:
  - Only inserts rows with a uuid-suffixed unique prefix.
  - Cleans up its own rows in the finally block.
  - Does NOT DROP / CREATE / TRUNCATE / reset migrations.
  - storage_backend=local (temp dir), never real S3.

Run:
    DATABASE_URL="postgres://pc@localhost:5432/kerf?sslmode=disable" \\
        python3 -m pytest packages/kerf-api/tests/test_export_spine.py -q
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import secrets
import sys
import tempfile
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator

import asyncpg
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# sys.path bootstrap
# ---------------------------------------------------------------------------
import pathlib

_HERE = pathlib.Path(__file__).parent
_PACKAGES_ROOT = _HERE.parent.parent

for _entry in _PACKAGES_ROOT.iterdir():
    if not _entry.name.startswith("kerf-"):
        continue
    _src = _entry / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DB_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgres://pc@localhost:5432/kerf?sslmode=disable",
)
_JWT_SECRET: str = "dev-secret-change-in-production"
_RUN_PREFIX: str = f"export-{secrets.token_hex(4)}"


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _mint_jwt(user_id: str) -> str:
    now = datetime.now(tz=timezone.utc)
    return jwt.encode(
        {"sub": user_id, "exp": now + timedelta(hours=1), "iat": now},
        _JWT_SECRET,
        algorithm="HS256",
    )


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_mint_jwt(user_id)}"}


# ---------------------------------------------------------------------------
# DB fixture helpers
# ---------------------------------------------------------------------------

async def _create_fixtures(db_url: str, storage_root: str) -> dict:
    """Insert test rows for the route smoke test."""
    suffix = _RUN_PREFIX
    user_email = f"{suffix}@export.test"
    ws_slug = f"ws-{suffix}"
    proj_name = f"ExportProj {suffix}"

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=3)
    try:
        async with pool.acquire() as conn:
            user_row = await conn.fetchrow(
                """
                INSERT INTO users (email, name, account_role, is_system)
                VALUES ($1, $2, 'user', false)
                RETURNING id
                """,
                user_email, f"Export {suffix}",
            )
            user_id = str(user_row["id"])

            ws_row = await conn.fetchrow(
                """
                INSERT INTO workspaces (slug, name, created_by)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                ws_slug, f"WS {suffix}", user_row["id"],
            )
            ws_id = str(ws_row["id"])

            await conn.execute(
                """
                INSERT INTO workspace_members (workspace_id, user_id, role)
                VALUES ($1, $2, 'owner')
                """,
                ws_row["id"], user_row["id"],
            )

            proj_row = await conn.fetchrow(
                """
                INSERT INTO projects
                    (workspace_id, name, description, visibility, tags)
                VALUES ($1, $2, 'desc', 'private', '{}')
                RETURNING id
                """,
                ws_row["id"], proj_name,
            )
            proj_id = str(proj_row["id"])

            # Inline file
            inline_content = "// hello world inline\nconst x = 42;\n"
            inline_row = await conn.fetchrow(
                """
                INSERT INTO files (project_id, name, kind, content)
                VALUES ($1, $2, 'script', $3)
                RETURNING id
                """,
                proj_row["id"],
                f"main-{suffix}.jscad",
                inline_content,
            )
            inline_id = str(inline_row["id"])

            # Blob file — store real bytes in LocalStorage, set storage_key
            blob_payload = b"\x00\x01\x02\x03" * 64  # 256 bytes of binary (non-UTF-8)
            storage_key = f"blobs/test/{suffix}.bin"
            blob_path = pathlib.Path(storage_root) / "blobs" / "test" / f"{suffix}.bin"
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_bytes(blob_payload)

            blob_row = await conn.fetchrow(
                """
                INSERT INTO files (project_id, name, kind, content, storage_key, size)
                VALUES ($1, $2, 'file', '', $3, $4)
                RETURNING id
                """,
                proj_row["id"],
                f"data-{suffix}.bin",
                storage_key,
                len(blob_payload),
            )
            blob_id = str(blob_row["id"])
    finally:
        await pool.close()

    return {
        "user_id": user_id,
        "ws_id": ws_id,
        "proj_id": proj_id,
        "inline_id": inline_id,
        "inline_content": inline_content,
        "blob_id": blob_id,
        "storage_key": storage_key,
        "blob_payload": blob_payload,
    }


async def _delete_fixtures(db_url: str, ids: dict) -> None:
    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM files WHERE project_id = $1",
                uuid.UUID(ids["proj_id"]),
            )
            await conn.execute(
                "DELETE FROM projects WHERE id = $1",
                uuid.UUID(ids["proj_id"]),
            )
            await conn.execute(
                "DELETE FROM workspace_members WHERE workspace_id = $1",
                uuid.UUID(ids["ws_id"]),
            )
            await conn.execute(
                "DELETE FROM workspaces WHERE id = $1",
                uuid.UUID(ids["ws_id"]),
            )
            await conn.execute(
                "DELETE FROM refresh_tokens WHERE user_id = $1",
                uuid.UUID(ids["user_id"]),
            )
            await conn.execute(
                "DELETE FROM email_tokens WHERE user_id = $1",
                uuid.UUID(ids["user_id"]),
            )
            await conn.execute(
                "DELETE FROM users WHERE id = $1",
                uuid.UUID(ids["user_id"]),
            )
    finally:
        await pool.close()


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------

_STORAGE_TMPDIR: str | None = None
_FIXTURE_IDS: dict | None = None


def _get_storage_root() -> str:
    global _STORAGE_TMPDIR
    if _STORAGE_TMPDIR is None:
        _STORAGE_TMPDIR = tempfile.mkdtemp(prefix="kerf-export-test-")
    return _STORAGE_TMPDIR


def _get_fixture_ids() -> dict:
    global _FIXTURE_IDS
    if _FIXTURE_IDS is None:
        _FIXTURE_IDS = asyncio.run(_create_fixtures(_DB_URL, _get_storage_root()))
    return _FIXTURE_IDS


@pytest.fixture(scope="session", autouse=True)
def session_fixtures() -> Generator[dict, None, None]:
    ids = _get_fixture_ids()
    yield ids
    asyncio.run(_delete_fixtures(_DB_URL, ids))


# ---------------------------------------------------------------------------
# Test app + client (mirrors test_api_smoke pattern)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    import kerf_core.db.connection as _conn
    from kerf_core.storage.local import LocalStorage
    from kerf_core.storage import set_storage as _ss

    pool = await asyncpg.create_pool(_DB_URL, min_size=2, max_size=5)
    _conn._pool = pool
    _ss(LocalStorage(root=_get_storage_root()))
    yield
    _conn._pool = None
    await pool.close()


def _build_test_app() -> FastAPI:
    from kerf_api.routes import router as api_router

    app = FastAPI(lifespan=_lifespan)
    app.include_router(api_router, prefix="/api")
    return app


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    app = _build_test_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _ids() -> dict:
    return _get_fixture_ids()


# ===========================================================================
# Unit tests — materialize_project_tree (no DB, no HTTP)
# ===========================================================================

class TestMaterializeProjectTree:
    """Direct unit tests for the reusable materialize_project_tree function."""

    def _make_storage(self, tmp_path: pathlib.Path):
        from kerf_core.storage.local import LocalStorage
        return LocalStorage(root=str(tmp_path))

    def test_inline_file_at_correct_path(self, tmp_path: pathlib.Path):
        """An inline file appears at its POSIX path inside the ZIP, not files/{path}."""
        from kerf_api.routes import materialize_project_tree, _FileRecord

        content = "hello world"
        rec = _FileRecord(
            id="1", parent_id=None, name="hello.txt",
            kind="script", content=content,
            storage_key=None, mime_type="text/plain", size=len(content),
        )
        storage = self._make_storage(tmp_path)

        result = asyncio.run(materialize_project_tree(
            files=[rec],
            storage=storage,
            project_name="Test",
        ))

        with zipfile.ZipFile(io.BytesIO(result.zip_bytes)) as zf:
            names = zf.namelist()
            assert "hello.txt" in names, f"expected hello.txt in {names}"
            assert "files/hello.txt" not in names, "should not be under files/ prefix"
            data = zf.read("hello.txt")
            assert data == content.encode("utf-8")

    def test_blob_file_at_correct_path_with_real_bytes(self, tmp_path: pathlib.Path):
        """A blob file is fetched from storage and written at its POSIX path."""
        from kerf_api.routes import materialize_project_tree, _FileRecord

        blob_bytes = bytes(range(256))  # 256 bytes, non-UTF-8
        storage = self._make_storage(tmp_path)
        # Write the blob into local storage
        asyncio.run(storage.put(
            "myblob-key",
            io.BytesIO(blob_bytes),
            "application/octet-stream",
            len(blob_bytes),
        ))

        rec = _FileRecord(
            id="2", parent_id=None, name="data.bin",
            kind="file", content="",
            storage_key="myblob-key", mime_type=None, size=len(blob_bytes),
        )

        result = asyncio.run(materialize_project_tree(
            files=[rec],
            storage=storage,
            project_name="Test",
        ))

        with zipfile.ZipFile(io.BytesIO(result.zip_bytes)) as zf:
            names = zf.namelist()
            assert "data.bin" in names, f"expected data.bin in {names}"
            data = zf.read("data.bin")
            assert data == blob_bytes

    def test_manifest_contains_kerf_manifest_json(self, tmp_path: pathlib.Path):
        """ZIP always contains kerf-manifest.json at the root."""
        from kerf_api.routes import materialize_project_tree, _FileRecord

        rec = _FileRecord(
            id="1", parent_id=None, name="a.txt",
            kind="script", content="abc",
            storage_key=None, mime_type=None, size=3,
        )
        storage = self._make_storage(tmp_path)
        result = asyncio.run(materialize_project_tree(
            files=[rec], storage=storage, project_name="P",
        ))

        with zipfile.ZipFile(io.BytesIO(result.zip_bytes)) as zf:
            assert "kerf-manifest.json" in zf.namelist()
            manifest = json.loads(zf.read("kerf-manifest.json"))
            assert manifest["version"] == 1

    def test_manifest_inline_classification_and_oid(self, tmp_path: pathlib.Path):
        """Inline file manifest entry has classification=inline and correct sha256 oid."""
        from kerf_api.routes import materialize_project_tree, _FileRecord

        content = "// kerf script\n"
        content_bytes = content.encode("utf-8")
        expected_oid = hashlib.sha256(content_bytes).hexdigest()

        rec = _FileRecord(
            id="1", parent_id=None, name="main.jscad",
            kind="script", content=content,
            storage_key=None, mime_type=None, size=len(content_bytes),
        )
        storage = self._make_storage(tmp_path)
        result = asyncio.run(materialize_project_tree(
            files=[rec], storage=storage,
        ))

        manifest = result.manifest
        file_entry = next(e for e in manifest["files"] if e["path"] == "main.jscad")
        assert file_entry["classification"] == "inline"
        assert file_entry["oid"] == expected_oid
        assert file_entry["size"] == len(content_bytes)

    def test_manifest_blob_classification_and_oid(self, tmp_path: pathlib.Path):
        """Blob file manifest entry has classification=blob and correct sha256 oid."""
        from kerf_api.routes import materialize_project_tree, _FileRecord

        blob_bytes = b"\xff\xfe\xfd" * 100  # non-UTF-8
        expected_oid = hashlib.sha256(blob_bytes).hexdigest()
        storage = self._make_storage(tmp_path)
        asyncio.run(storage.put(
            "blob-sha-key", io.BytesIO(blob_bytes),
            "application/octet-stream", len(blob_bytes),
        ))

        rec = _FileRecord(
            id="3", parent_id=None, name="mesh.bin",
            kind="file", content="",
            storage_key="blob-sha-key", mime_type=None, size=len(blob_bytes),
        )
        result = asyncio.run(materialize_project_tree(
            files=[rec], storage=storage,
        ))

        manifest = result.manifest
        file_entry = next(e for e in manifest["files"] if e["path"] == "mesh.bin")
        assert file_entry["classification"] == "blob"
        assert file_entry["oid"] == expected_oid
        assert file_entry["size"] == len(blob_bytes)

    def test_mixed_inline_and_blob(self, tmp_path: pathlib.Path):
        """Mix of inline and blob files: both appear at correct paths with right manifest entries."""
        from kerf_api.routes import materialize_project_tree, _FileRecord

        inline_content = "let x = 1;\n"
        blob_bytes = bytes(range(256))
        storage = self._make_storage(tmp_path)
        asyncio.run(storage.put(
            "blob-mixed-key", io.BytesIO(blob_bytes),
            "application/octet-stream", len(blob_bytes),
        ))

        files = [
            _FileRecord(
                id="a", parent_id=None, name="src",
                kind="folder", content="",
                storage_key=None, mime_type=None, size=None,
            ),
            _FileRecord(
                id="b", parent_id="a", name="index.jscad",
                kind="script", content=inline_content,
                storage_key=None, mime_type=None, size=len(inline_content),
            ),
            _FileRecord(
                id="c", parent_id=None, name="model.bin",
                kind="file", content="",
                storage_key="blob-mixed-key", mime_type=None, size=len(blob_bytes),
            ),
        ]
        result = asyncio.run(materialize_project_tree(
            files=files, storage=storage, project_name="Mixed",
        ))

        with zipfile.ZipFile(io.BytesIO(result.zip_bytes)) as zf:
            names = zf.namelist()
            assert "src/index.jscad" in names
            assert "model.bin" in names
            assert zf.read("src/index.jscad") == inline_content.encode("utf-8")
            assert zf.read("model.bin") == blob_bytes

        # Manifest entries
        m = result.manifest
        entries = {e["path"]: e for e in m["files"]}
        assert entries["src/index.jscad"]["classification"] == "inline"
        assert entries["model.bin"]["classification"] == "blob"
        assert entries["src"]["classification"] == "folder"

    def test_folder_entries_excluded_from_zip_body(self, tmp_path: pathlib.Path):
        """Folder entries appear in manifest but are not added as ZIP entries."""
        from kerf_api.routes import materialize_project_tree, _FileRecord

        files = [
            _FileRecord(
                id="f1", parent_id=None, name="models",
                kind="folder", content="",
                storage_key=None, mime_type=None, size=None,
            ),
            _FileRecord(
                id="f2", parent_id="f1", name="part.jscad",
                kind="script", content="// part",
                storage_key=None, mime_type=None, size=7,
            ),
        ]
        storage = self._make_storage(tmp_path)
        result = asyncio.run(materialize_project_tree(
            files=files, storage=storage,
        ))

        with zipfile.ZipFile(io.BytesIO(result.zip_bytes)) as zf:
            names = zf.namelist()
            assert "models/part.jscad" in names
            # No bare "models" directory entry needed — the path implies it.
            assert "models" not in names

    def test_manifest_has_all_required_fields(self, tmp_path: pathlib.Path):
        """Every non-folder manifest entry has path, kind, classification, oid, size."""
        from kerf_api.routes import materialize_project_tree, _FileRecord

        content = "x = 1"
        rec = _FileRecord(
            id="1", parent_id=None, name="test.py",
            kind="script", content=content,
            storage_key=None, mime_type="text/x-python", size=len(content),
        )
        storage = self._make_storage(tmp_path)
        result = asyncio.run(materialize_project_tree(
            files=[rec], storage=storage,
        ))

        entry = result.manifest["files"][0]
        for field in ("path", "kind", "classification", "oid", "size"):
            assert field in entry, f"manifest entry missing field '{field}': {entry}"
        assert entry["mime_type"] == "text/x-python"


# ===========================================================================
# Autodetect predicate unit tests
# ===========================================================================

class TestShouldStoreAsBlob:
    """Tests for the should_store_as_blob predicate from kerf_core.storage.classify."""

    def test_utf8_text_file_is_inline(self):
        """A small UTF-8 text file is not a blob."""
        from kerf_core.storage.classify import should_store_as_blob

        content = b"// hello world\nconst x = 42;\n"
        result = should_store_as_blob("hello.jscad", len(content), content, threshold=1024 * 1024)
        assert result is False, "small UTF-8 text should be inline"

    def test_large_file_is_blob_regardless_of_encoding(self):
        """A file > threshold is always a blob even if valid UTF-8."""
        from kerf_core.storage.classify import should_store_as_blob

        threshold = 1024 * 1024  # 1 MiB
        # 1.5 MiB of valid ASCII
        content = b"a" * (threshold + 512 * 1024)
        result = should_store_as_blob("big.txt", len(content), content[:8192], threshold=threshold)
        assert result is True, ">1 MiB file should be blob"

    def test_small_binary_is_blob(self):
        """A small (<1 MiB) non-UTF-8 binary is a blob."""
        from kerf_core.storage.classify import should_store_as_blob

        # 512 bytes that are not valid UTF-8 (high bytes)
        content = bytes(range(256)) * 2
        result = should_store_as_blob("data.bin", len(content), content, threshold=1024 * 1024)
        assert result is True, "non-UTF-8 binary should be blob"

    def test_large_binary_is_blob(self):
        """A >1 MiB non-UTF-8 binary is definitely a blob."""
        from kerf_core.storage.classify import should_store_as_blob

        threshold = 1024 * 1024
        content = bytes(range(256)) * (threshold // 256 + 1)
        result = should_store_as_blob("mesh.bin", len(content), content[:8192], threshold=threshold)
        assert result is True

    def test_empty_file_is_inline(self):
        """An empty file is not a blob."""
        from kerf_core.storage.classify import should_store_as_blob

        result = should_store_as_blob("empty.txt", 0, b"", threshold=1024 * 1024)
        assert result is False


# ===========================================================================
# Route integration smoke test
# ===========================================================================

class TestExportRouteSmoke:
    """HTTP-level smoke test for GET /api/projects/{pid}/export."""

    def test_export_returns_zip_with_kerf_manifest(
        self, client: TestClient, session_fixtures
    ):
        """Export route returns a ZIP containing kerf-manifest.json."""
        ids = _ids()
        pid = ids["proj_id"]
        uid = ids["user_id"]

        r = client.get(
            f"/api/projects/{pid}/export",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200, f"export {r.status_code}: {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("application/zip"), (
            f"expected zip content-type, got {r.headers.get('content-type')}"
        )

        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            names = zf.namelist()
            assert "kerf-manifest.json" in names, f"kerf-manifest.json missing from {names}"
            manifest = json.loads(zf.read("kerf-manifest.json"))
            assert manifest["version"] == 1
            assert "files" in manifest
            assert isinstance(manifest["files"], list)

    def test_export_inline_file_at_correct_path(
        self, client: TestClient, session_fixtures
    ):
        """Inline file appears at its name (not files/{name}) in the export ZIP."""
        ids = _ids()
        pid = ids["proj_id"]
        uid = ids["user_id"]
        inline_content = ids["inline_content"]

        r = client.get(
            f"/api/projects/{pid}/export",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200

        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            names = zf.namelist()
            # Find the inline file — it should be at its bare name, not files/{name}
            inline_names = [n for n in names if n.endswith(".jscad")]
            assert len(inline_names) >= 1, f"no .jscad file in zip: {names}"
            for n in inline_names:
                assert not n.startswith("files/"), (
                    f"inline file should not be under files/ prefix: {n}"
                )

    def test_export_manifest_has_classification(
        self, client: TestClient, session_fixtures
    ):
        """Manifest entries have 'classification' field (inline or blob)."""
        ids = _ids()
        pid = ids["proj_id"]
        uid = ids["user_id"]

        r = client.get(
            f"/api/projects/{pid}/export",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200

        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            manifest = json.loads(zf.read("kerf-manifest.json"))

        for entry in manifest["files"]:
            assert "classification" in entry, (
                f"manifest entry missing 'classification': {entry}"
            )
            assert entry["classification"] in ("inline", "blob", "folder"), (
                f"unexpected classification: {entry['classification']}"
            )

    def test_export_manifest_has_oid_for_non_folder(
        self, client: TestClient, session_fixtures
    ):
        """Non-folder manifest entries have an 'oid' field (sha256 hex)."""
        ids = _ids()
        pid = ids["proj_id"]
        uid = ids["user_id"]

        r = client.get(
            f"/api/projects/{pid}/export",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200

        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            manifest = json.loads(zf.read("kerf-manifest.json"))

        for entry in manifest["files"]:
            if entry.get("classification") in ("inline", "blob"):
                assert "oid" in entry, f"non-folder entry missing 'oid': {entry}"
                assert len(entry["oid"]) == 64, f"oid should be 64-char sha256 hex: {entry['oid']}"

    def test_export_blob_file_in_zip(
        self, client: TestClient, session_fixtures
    ):
        """Blob file (storage_key set) is included in the ZIP at its correct path."""
        ids = _ids()
        pid = ids["proj_id"]
        uid = ids["user_id"]
        blob_payload = ids["blob_payload"]

        r = client.get(
            f"/api/projects/{pid}/export",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 200

        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            names = zf.namelist()
            blob_names = [n for n in names if n.endswith(".bin")]
            assert len(blob_names) >= 1, f"no .bin file in zip: {names}"
            # The blob should not be at blobs/{key} but at the file's name
            for n in blob_names:
                assert not n.startswith("blobs/"), (
                    f"blob file should not be under blobs/ prefix: {n}"
                )
            # Verify content matches what we stored
            data = zf.read(blob_names[0])
            assert data == blob_payload, "blob content mismatch"

    def test_export_unknown_project_returns_404(
        self, client: TestClient, session_fixtures
    ):
        """Exporting a non-existent project returns 404."""
        ids = _ids()
        uid = ids["user_id"]
        fake_pid = str(uuid.uuid4())

        r = client.get(
            f"/api/projects/{fake_pid}/export",
            headers=_auth_headers(uid),
        )
        assert r.status_code == 404, f"expected 404, got {r.status_code}"
