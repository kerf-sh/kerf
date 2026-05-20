"""Round-trip tests for ``kerf export`` / ``kerf import`` (T-322).

Covers the full export → wipe → import → diff cycle using an in-memory
fixture.  All HTTP is mocked — no network, no server, no database.

Test structure mirrors test_portability.py (the ZIP-based predecessor).

Round-trip oracle
-----------------
Export produces a directory tree; import reads it and uploads files whose
content matches the original bytes verbatim (UTF-8 text files) or empty
string (binary files that cannot be decoded).  The round-trip is:

    original_bytes → exported_file_on_disk → imported_content == original
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: run CLI subcommands
# ---------------------------------------------------------------------------

def _run_cmd(argv: list[str]) -> tuple[int, str, str]:
    """Run a kerf subcommand and return (exit_code, stdout, stderr)."""
    from kerf_cli.main import _build_parser

    parser = _build_parser()
    captured_out = io.StringIO()
    captured_err = io.StringIO()

    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = captured_out, captured_err

    exit_code = 0
    try:
        args = parser.parse_args(argv)
        exit_code = args.func(args)
    except SystemExit as exc:
        exit_code = int(exc.code) if exc.code is not None else 0
    finally:
        sys.stdout, sys.stderr = old_out, old_err

    return exit_code, captured_out.getvalue(), captured_err.getvalue()


# ---------------------------------------------------------------------------
# Helpers: build server-response fixtures
# ---------------------------------------------------------------------------

def _mock_resp(body: bytes, status: int = 200, headers: dict | None = None):
    """Build a mock urllib response context manager."""
    mock = MagicMock()
    mock.read.return_value = body
    mock.getheader = MagicMock(
        side_effect=lambda h, default="": (headers or {}).get(h, default)
    )
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _make_server_zip(
    files: dict[str, bytes],
    *,
    project_name: str = "Test Project",
    project_id: str = "aaaabbbb-0000-0000-0000-000000000000",
    workspace_id: str = "ws-0000-0000-0000-000000000001",
    default_branch: str = "main",
    description: str = "",
    tags: list[str] | None = None,
    created_at: str = "2026-01-01T00:00:00Z",
) -> bytes:
    """Build a ZIP archive that mimics what ``GET /api/projects/{pid}/export``
    returns (i.e. what ``materialize_project_tree`` produces on the server)."""
    manifest_files = []
    for path, content in files.items():
        oid = hashlib.sha256(content).hexdigest()
        manifest_files.append({
            "path": path,
            "kind": "file",
            "classification": "inline",
            "oid": oid,
            "size": len(content),
        })

    manifest = {
        "version": 1,
        "name": project_name,
        "description": description,
        "tags": tags or [],
        "created_at": created_at,
        "workspace_id_hint": workspace_id[:8],
        "cloud_git_repo": {
            "default_branch": default_branch,
        },
        "files": manifest_files,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("kerf-manifest.json", json.dumps(manifest, indent=2))
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# export — parser smoke tests
# ---------------------------------------------------------------------------

class TestExportParserSmoke:
    def test_export_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc_info:
            from kerf_cli.main import _build_parser
            _build_parser().parse_args(["export", "--help"])
        assert exc_info.value.code == 0

    def test_export_defaults(self):
        from kerf_cli.main import _build_parser
        args = _build_parser().parse_args(["export", "proj-uuid"])
        assert args.project_id == "proj-uuid"
        assert args.out == ""
        assert args.url == ""
        assert args.token == ""

    def test_export_out_flag(self):
        from kerf_cli.main import _build_parser
        args = _build_parser().parse_args(["export", "proj-uuid", "--out", "/tmp/my-export"])
        assert args.out == "/tmp/my-export"

    def test_export_dispatches_to_cmd_export(self):
        from kerf_cli.main import _build_parser, _cmd_export
        args = _build_parser().parse_args(["export", "p"])
        assert args.func is _cmd_export


# ---------------------------------------------------------------------------
# import — parser smoke tests
# ---------------------------------------------------------------------------

class TestImportParserSmoke:
    def test_import_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc_info:
            from kerf_cli.main import _build_parser
            _build_parser().parse_args(["import", "--help"])
        assert exc_info.value.code == 0

    def test_import_defaults(self):
        from kerf_cli.main import _build_parser
        args = _build_parser().parse_args(["import", "/some/dir"])
        assert args.import_dir == "/some/dir"
        assert args.name == ""
        assert args.url == ""
        assert args.token == ""

    def test_import_name_flag(self):
        from kerf_cli.main import _build_parser
        args = _build_parser().parse_args(["import", "/dir", "--name", "My Project"])
        assert args.name == "My Project"

    def test_import_dispatches_to_cmd_import(self):
        from kerf_cli.main import _build_parser, _cmd_import
        args = _build_parser().parse_args(["import", "/dir"])
        assert args.func is _cmd_import


# ---------------------------------------------------------------------------
# export — behaviour tests
# ---------------------------------------------------------------------------

class TestExportBehaviour:
    def test_export_writes_directory_tree(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        files = {
            "design.step": b"STEP AP214",
            "notes.txt": b"some notes",
            "sub/config.json": b'{"key": "value"}',
        }
        zip_bytes = _make_server_zip(files, project_name="My Design")
        mock = _mock_resp(zip_bytes)
        out_dir = tmp_path / "export-out"

        with patch("urllib.request.urlopen", return_value=mock):
            code, _, err = _run_cmd([
                "export", "proj-uuid",
                "--out", str(out_dir),
                "--url", "http://fake-api",
                "--token", "kerf_sk_test",
            ])

        assert code == 0, f"exit code {code}, stderr: {err}"
        assert out_dir.is_dir()
        assert (out_dir / "design.step").read_bytes() == b"STEP AP214"
        assert (out_dir / "notes.txt").read_bytes() == b"some notes"
        assert (out_dir / "sub" / "config.json").read_bytes() == b'{"key": "value"}'

    def test_export_writes_kerf_metadata_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        zip_bytes = _make_server_zip(
            {"a.txt": b"hi"},
            project_name="Alpha",
            project_id="pid-0001-0000-0000-000000000000",
            workspace_id="ws-00000001-xxxx",
            description="Test description",
            tags=["tag1", "tag2"],
        )
        mock = _mock_resp(zip_bytes)
        out_dir = tmp_path / "meta-test"

        with patch("urllib.request.urlopen", return_value=mock):
            _run_cmd([
                "export", "pid-0001-0000-0000-000000000000",
                "--out", str(out_dir),
                "--url", "http://fake-api",
            ])

        metadata_path = out_dir / ".kerf" / "metadata.json"
        assert metadata_path.exists()
        meta = json.loads(metadata_path.read_text())
        assert meta["name"] == "Alpha"
        assert meta["project_id"] == "pid-0001-0000-0000-000000000000"
        assert "kerf_export_version" in meta

    def test_export_writes_kerf_manifest_lock(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        content = b"The quick brown fox."
        expected_oid = hashlib.sha256(content).hexdigest()
        zip_bytes = _make_server_zip(
            {"fox.txt": content},
            default_branch="develop",
        )
        mock = _mock_resp(zip_bytes)
        out_dir = tmp_path / "lock-test"

        with patch("urllib.request.urlopen", return_value=mock):
            _run_cmd([
                "export", "proj-lock",
                "--out", str(out_dir),
                "--url", "http://fake-api",
            ])

        lock_path = out_dir / ".kerf" / "manifest.lock"
        assert lock_path.exists()
        lock = json.loads(lock_path.read_text())
        assert lock["kerf_lock_version"] == 1
        assert lock["cloud_git_repo"]["default_branch"] == "develop"

        file_entries = {e["path"]: e for e in lock["files"]}
        assert "fox.txt" in file_entries
        assert file_entries["fox.txt"]["oid"] == expected_oid
        assert file_entries["fox.txt"]["size"] == len(content)

    def test_export_no_token_exits_2(self, tmp_path, monkeypatch):
        monkeypatch.delenv("KERF_API_TOKEN", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from kerf_cli import credentials
        import importlib
        importlib.reload(credentials)

        code, _, err = _run_cmd(["export", "proj-uuid"])
        assert code == 2
        assert "KERF_API_TOKEN" in err

    def test_export_404_exits_3(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        import urllib.error
        exc = urllib.error.HTTPError("http://fake-api/...", 404, "Not Found", {}, None)

        with patch("urllib.request.urlopen", side_effect=exc):
            code, _, err = _run_cmd([
                "export", "bad-id",
                "--url", "http://fake-api",
            ])

        assert code == 3
        assert "not found" in err.lower()

    def test_export_auth_failure_exits_2(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "bad_token")

        import urllib.error
        exc = urllib.error.HTTPError("http://fake-api/...", 401, "Unauthorized", {}, None)

        with patch("urllib.request.urlopen", side_effect=exc):
            code, _, err = _run_cmd([
                "export", "proj-uuid",
                "--url", "http://fake-api",
                "--token", "bad_token",
            ])

        assert code == 2
        assert "auth" in err.lower()

    def test_export_default_dir_name(self, tmp_path, monkeypatch):
        """When --out is omitted, default dir is kerf-export-<short-id>."""
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")
        monkeypatch.chdir(tmp_path)

        zip_bytes = _make_server_zip({"f.txt": b"x"})
        mock = _mock_resp(zip_bytes)

        pid = "aabbccdd-1234-5678-abcd-000000000000"
        with patch("urllib.request.urlopen", return_value=mock):
            code, _, _ = _run_cmd([
                "export", pid,
                "--url", "http://fake-api",
            ])

        assert code == 0
        expected_dir = tmp_path / f"kerf-export-{pid[:8]}"
        assert expected_dir.is_dir()


# ---------------------------------------------------------------------------
# import — behaviour tests
# ---------------------------------------------------------------------------

class TestImportBehaviour:
    def _make_export_dir(self, tmp_path: Path, files: dict[str, bytes], **kw) -> Path:
        """Helper: create a pre-populated export directory as kerf export would."""
        from kerf_cli.export import _extract_to_dir, _build_manifest_lock
        import json

        pid = kw.get("project_id", "pid-00000000-0000-0000-0000-000000000000")
        name = kw.get("project_name", "Test Project")
        ws = kw.get("workspace_id", "ws-00000001")

        zip_bytes = _make_server_zip(files, project_name=name, project_id=pid, workspace_id=ws)
        out_dir = tmp_path / "export"

        import io as _io, zipfile as _zf
        manifest = json.loads(
            _zf.ZipFile(_io.BytesIO(zip_bytes)).read("kerf-manifest.json").decode()
        )
        _extract_to_dir(zip_bytes, out_dir)

        kerf_dir = out_dir / ".kerf"
        kerf_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "kerf_export_version": 1,
            "project_id": pid,
            "name": name,
            "description": kw.get("description", ""),
            "tags": kw.get("tags", []),
            "created_at": "2026-01-01T00:00:00Z",
            "workspace_id_hint": ws[:8],
        }
        (kerf_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

        lock = _build_manifest_lock(out_dir, manifest)
        (kerf_dir / "manifest.lock").write_text(
            json.dumps(lock, indent=2, sort_keys=True), encoding="utf-8"
        )
        return out_dir

    def test_import_creates_project_and_uploads_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        files = {
            "design.step": b"STEP AP214",
            "notes.txt": b"some notes",
        }
        export_dir = self._make_export_dir(tmp_path, files, project_name="Test Project")

        create_resp = _mock_resp(json.dumps({"id": "new-proj-id"}).encode())
        upload_resp = _mock_resp(json.dumps({"id": "f1"}).encode())

        call_index = [0]
        resps = [create_resp] + [upload_resp] * len(files)

        def _urlopen(req, timeout=None):
            idx = call_index[0]
            call_index[0] += 1
            return resps[idx]

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            code, _, err = _run_cmd([
                "import", str(export_dir),
                "--url", "http://fake-api",
                "--token", "kerf_sk_test",
            ])

        assert code == 0, f"exit={code}, stderr={err}"
        assert "new-proj-id" in err
        assert f"{len(files)}/{len(files)}" in err

    def test_import_uses_metadata_name(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        export_dir = self._make_export_dir(tmp_path, {"a.txt": b"hello"}, project_name="From Metadata")

        captured_name = []

        def _urlopen(req, timeout=None):
            if hasattr(req, "data") and req.data:
                body = json.loads(req.data.decode())
                if "name" in body and "content" not in body:
                    captured_name.append(body["name"])
            return _mock_resp(json.dumps({"id": "pid-xyz"}).encode())

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            code, _, _ = _run_cmd([
                "import", str(export_dir),
                "--url", "http://fake-api",
            ])

        assert code == 0
        assert "From Metadata" in captured_name

    def test_import_custom_name_overrides_metadata(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        export_dir = self._make_export_dir(tmp_path, {}, project_name="Old Name")

        captured_name = []

        def _urlopen(req, timeout=None):
            if hasattr(req, "data") and req.data:
                body = json.loads(req.data.decode())
                if "name" in body and "content" not in body:
                    captured_name.append(body["name"])
            return _mock_resp(json.dumps({"id": "pid-yyy"}).encode())

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            _run_cmd([
                "import", str(export_dir),
                "--name", "Custom Name",
                "--url", "http://fake-api",
            ])

        assert "Custom Name" in captured_name

    def test_import_no_token_exits_2(self, tmp_path, monkeypatch):
        monkeypatch.delenv("KERF_API_TOKEN", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from kerf_cli import credentials
        import importlib
        importlib.reload(credentials)

        fake_dir = tmp_path / "export-dir"
        fake_dir.mkdir()

        code, _, err = _run_cmd(["import", str(fake_dir)])
        assert code == 2
        assert "KERF_API_TOKEN" in err

    def test_import_missing_dir_exits_1(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        code, _, err = _run_cmd([
            "import", str(tmp_path / "nonexistent"),
            "--url", "http://fake-api",
        ])
        assert code == 1
        assert "not found" in err.lower() or "directory" in err.lower()


# ---------------------------------------------------------------------------
# Full round-trip: export → wipe → import → diff = empty
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """End-to-end: export writes files, import reads them back, content is
    identical — diff is empty."""

    def test_round_trip_text_file(self, tmp_path, monkeypatch):
        """Round-trip a UTF-8 text file: uploaded content == original bytes."""
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        original = b"Source of truth: the fox jumps.\n"
        files = {"source.txt": original}
        zip_bytes = _make_server_zip(files, project_name="RT-Text")
        export_dir = tmp_path / "rt-export"

        # ---- step 1: export (mock server returning the ZIP) -----------------
        with patch("urllib.request.urlopen", return_value=_mock_resp(zip_bytes)):
            code, _, err = _run_cmd([
                "export", "rt-proj-id",
                "--out", str(export_dir),
                "--url", "http://fake-api",
            ])
        assert code == 0, f"export failed: {err}"

        # Verify the file landed on disk.
        assert (export_dir / "source.txt").read_bytes() == original

        # ---- step 2: wipe the in-memory "server" state ----------------------
        # (Nothing to wipe — we never wrote to a real server.)

        # ---- step 3: import (mock server accepting the upload) --------------
        uploaded: list[dict] = []

        def _urlopen(req, timeout=None):
            if hasattr(req, "data") and req.data:
                body = json.loads(req.data.decode())
                uploaded.append(body)
            return _mock_resp(json.dumps({"id": "imported-pid"}).encode())

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            code, _, err = _run_cmd([
                "import", str(export_dir),
                "--url", "http://fake-api",
            ])
        assert code == 0, f"import failed: {err}"

        # ---- step 4: diff — uploaded content must match original ------------
        # First call is the project-create POST (has "name" but no "content").
        file_uploads = [u for u in uploaded if "content" in u]
        assert len(file_uploads) == 1, f"expected 1 file upload, got {len(file_uploads)}"
        assert file_uploads[0]["content"] == original.decode("utf-8")

    def test_round_trip_multiple_files(self, tmp_path, monkeypatch):
        """Round-trip multiple files; every file's content is preserved."""
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        originals = {
            "models/part.step": b"ISO-10303-21;",
            "docs/readme.txt": b"Read me.\n",
            "scripts/gen.py": b"print('hello')\n",
        }
        zip_bytes = _make_server_zip(originals, project_name="RT-Multi")
        export_dir = tmp_path / "rt-multi"

        with patch("urllib.request.urlopen", return_value=_mock_resp(zip_bytes)):
            code, _, err = _run_cmd([
                "export", "rt-multi-pid",
                "--out", str(export_dir),
                "--url", "http://fake-api",
            ])
        assert code == 0, f"export failed: {err}"

        # Verify all files are on disk.
        for rel, content in originals.items():
            assert (export_dir / rel).read_bytes() == content

        uploaded: list[dict] = []

        def _urlopen(req, timeout=None):
            if hasattr(req, "data") and req.data:
                body = json.loads(req.data.decode())
                uploaded.append(body)
            return _mock_resp(json.dumps({"id": "mp-pid"}).encode())

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            code, _, err = _run_cmd([
                "import", str(export_dir),
                "--url", "http://fake-api",
            ])
        assert code == 0, f"import failed: {err}"

        file_uploads = {u["name"]: u["content"] for u in uploaded if "content" in u}
        # Each file should have been uploaded with content matching the original.
        for rel, content in originals.items():
            name = Path(rel).name
            assert name in file_uploads, f"missing upload for {name}"
            assert file_uploads[name] == content.decode("utf-8"), (
                f"content mismatch for {name}"
            )

    def test_round_trip_manifest_lock_oids_match_disk(self, tmp_path, monkeypatch):
        """OIDs in manifest.lock == SHA-256 of the actual on-disk files."""
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        content = b"Deterministic content for OID verification."
        files = {"verify.txt": content}
        zip_bytes = _make_server_zip(files)
        export_dir = tmp_path / "oid-test"

        with patch("urllib.request.urlopen", return_value=_mock_resp(zip_bytes)):
            _run_cmd([
                "export", "oid-proj",
                "--out", str(export_dir),
                "--url", "http://fake-api",
            ])

        lock = json.loads((export_dir / ".kerf" / "manifest.lock").read_text())
        lock_index = {e["path"]: e for e in lock["files"]}

        assert "verify.txt" in lock_index
        expected_oid = hashlib.sha256(content).hexdigest()
        assert lock_index["verify.txt"]["oid"] == expected_oid
        assert lock_index["verify.txt"]["size"] == len(content)

        # Verify on-disk file SHA matches what the lock recorded.
        actual_oid = hashlib.sha256((export_dir / "verify.txt").read_bytes()).hexdigest()
        assert actual_oid == lock_index["verify.txt"]["oid"]

    def test_round_trip_metadata_json_fields(self, tmp_path, monkeypatch):
        """metadata.json records project_id, name, workspace_id_hint."""
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        zip_bytes = _make_server_zip(
            {},
            project_name="Meta Check",
            project_id="deadbeef-1234-5678-abcd-000000000000",
            workspace_id="cafebabe-0000-0000-0000-000000000000",
            description="Desc here",
            tags=["cad", "mechanical"],
            created_at="2026-03-15T10:00:00Z",
        )
        export_dir = tmp_path / "meta-check"

        with patch("urllib.request.urlopen", return_value=_mock_resp(zip_bytes)):
            _run_cmd([
                "export", "deadbeef-1234-5678-abcd-000000000000",
                "--out", str(export_dir),
                "--url", "http://fake-api",
            ])

        meta = json.loads((export_dir / ".kerf" / "metadata.json").read_text())
        assert meta["name"] == "Meta Check"
        assert meta["project_id"] == "deadbeef-1234-5678-abcd-000000000000"
        assert meta["description"] == "Desc here"
        assert meta["tags"] == ["cad", "mechanical"]
        assert meta["created_at"] == "2026-03-15T10:00:00Z"
        # workspace_id_hint is anonymised (first 8 chars only).
        assert meta["workspace_id_hint"] == "cafebabe"

    def test_round_trip_kerf_dir_not_uploaded(self, tmp_path, monkeypatch):
        """.kerf/ metadata files are NOT uploaded as project files."""
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        files = {"real.txt": b"real content"}
        zip_bytes = _make_server_zip(files, project_name="No-Meta-Upload")
        export_dir = tmp_path / "no-meta"

        with patch("urllib.request.urlopen", return_value=_mock_resp(zip_bytes)):
            _run_cmd([
                "export", "nm-proj",
                "--out", str(export_dir),
                "--url", "http://fake-api",
            ])

        uploaded_names: list[str] = []

        def _urlopen(req, timeout=None):
            if hasattr(req, "data") and req.data:
                body = json.loads(req.data.decode())
                if "name" in body:
                    uploaded_names.append(body["name"])
            return _mock_resp(json.dumps({"id": "np-pid"}).encode())

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            _run_cmd([
                "import", str(export_dir),
                "--url", "http://fake-api",
            ])

        # metadata.json and manifest.lock must NOT appear in upload calls.
        assert "metadata.json" not in uploaded_names
        assert "manifest.lock" not in uploaded_names
        # The real file should be uploaded.
        assert "real.txt" in uploaded_names


# ---------------------------------------------------------------------------
# export module unit tests
# ---------------------------------------------------------------------------

class TestExportModule:
    def test_extract_to_dir_writes_files(self, tmp_path):
        from kerf_cli.export import _extract_to_dir

        files = {"a/b.txt": b"hello", "c.txt": b"world"}
        zip_bytes = _make_server_zip(files)
        manifest = _extract_to_dir(zip_bytes, tmp_path / "out")

        assert (tmp_path / "out" / "a" / "b.txt").read_bytes() == b"hello"
        assert (tmp_path / "out" / "c.txt").read_bytes() == b"world"
        assert isinstance(manifest, dict)
        assert manifest["name"] == "Test Project"

    def test_extract_to_dir_skips_manifest_json(self, tmp_path):
        from kerf_cli.export import _extract_to_dir

        files = {"real.txt": b"real"}
        zip_bytes = _make_server_zip(files)
        out = tmp_path / "skip-test"
        _extract_to_dir(zip_bytes, out)

        assert not (out / "kerf-manifest.json").exists()

    def test_build_manifest_lock_structure(self, tmp_path):
        from kerf_cli.export import _extract_to_dir, _build_manifest_lock

        content = b"lock test"
        files = {"file.txt": content}
        zip_bytes = _make_server_zip(files, default_branch="main")
        out = tmp_path / "lock-struct"
        manifest = _extract_to_dir(zip_bytes, out)
        lock = _build_manifest_lock(out, manifest)

        assert lock["kerf_lock_version"] == 1
        assert "files" in lock
        assert lock["cloud_git_repo"]["default_branch"] == "main"

        entries = {e["path"]: e for e in lock["files"]}
        assert "file.txt" in entries
        assert entries["file.txt"]["oid"] == hashlib.sha256(content).hexdigest()
        assert entries["file.txt"]["size"] == len(content)


# ---------------------------------------------------------------------------
# import module unit tests
# ---------------------------------------------------------------------------

class TestImportModule:
    def test_create_project_returns_id(self):
        from kerf_cli.import_ import _create_project

        resp = _mock_resp(json.dumps({"id": "new-pid"}).encode())
        with patch("urllib.request.urlopen", return_value=resp):
            pid = _create_project("http://api", "tok", "My Project")
        assert pid == "new-pid"

    def test_create_project_auth_failure_raises(self):
        from kerf_cli.import_ import _create_project, _ApiError
        import urllib.error

        exc = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            with pytest.raises(_ApiError) as exc_info:
                _create_project("http://api", "bad", "Proj")
        assert exc_info.value.exit_code == 2

    def test_upload_file_returns_true_on_success(self):
        from kerf_cli.import_ import _upload_file

        resp = _mock_resp(json.dumps({"id": "fid"}).encode())
        with patch("urllib.request.urlopen", return_value=resp):
            ok = _upload_file("http://api", "pid", "tok", "f.txt", "file", b"content")
        assert ok is True

    def test_upload_file_returns_false_on_auth_error(self):
        from kerf_cli.import_ import _upload_file
        import urllib.error

        exc = urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            ok = _upload_file("http://api", "pid", "bad", "f.txt", "file", b"content")
        assert ok is False
