"""Tests for `kerf export` and `kerf import` (T-128).

All HTTP is mocked — no network, no server.
Mirrors the style of test_hydrate.py.
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: run a kerf subcommand
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
# Build a mock urlopen response
# ---------------------------------------------------------------------------

def _mock_resp(body: bytes, status: int = 200, headers: dict | None = None):
    mock = MagicMock()
    mock.read.return_value = body
    mock.getheader = MagicMock(
        side_effect=lambda h, default="": (headers or {}).get(h, default)
    )
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _make_zip(files: dict[str, bytes], manifest: dict | None = None) -> bytes:
    """Build an in-memory ZIP with optional kerf-manifest.json."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if manifest is not None:
            zf.writestr("kerf-manifest.json", json.dumps(manifest))
        for name, content in files.items():
            zf.writestr(name, content)
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
        args = _build_parser().parse_args(["export", "proj-uuid", "--out", "my-dir"])
        assert args.out == "my-dir"

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
        args = _build_parser().parse_args(["import", "/some/dir", "--name", "My Project"])
        assert args.name == "My Project"

    def test_import_dispatches_to_cmd_import(self):
        from kerf_cli.main import _build_parser, _cmd_import
        args = _build_parser().parse_args(["import", "/a/dir"])
        assert args.func is _cmd_import


# ---------------------------------------------------------------------------
# export — behaviour tests
# ---------------------------------------------------------------------------

class TestExportBehaviour:
    def test_export_writes_directory_tree(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        import hashlib, zipfile as _zf
        content = b"STEP data"
        manifest = {
            "version": 1, "name": "Test", "description": "", "tags": [],
            "created_at": "", "workspace_id_hint": "aaaabbbb",
            "files": [{"path": "design.step", "kind": "file", "classification": "inline",
                       "oid": hashlib.sha256(content).hexdigest(), "size": len(content)}],
        }
        buf = io.BytesIO()
        with _zf.ZipFile(buf, "w") as zf:
            zf.writestr("kerf-manifest.json", json.dumps(manifest))
            zf.writestr("design.step", content)
        zip_content = buf.getvalue()

        mock = _mock_resp(zip_content)
        out_dir = tmp_path / "out-dir"

        with patch("urllib.request.urlopen", return_value=mock):
            code, _, err = _run_cmd([
                "export", "proj-uuid",
                "--out", str(out_dir),
                "--url", "http://fake-api",
                "--token", "kerf_sk_test",
            ])

        assert code == 0
        assert out_dir.is_dir()
        assert (out_dir / "design.step").read_bytes() == content
        assert "Exported" in err

    def test_export_writes_kerf_metadata(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        import hashlib, zipfile as _zf
        content = b"hello"
        manifest = {
            "version": 1, "name": "Slug Test", "description": "", "tags": [],
            "created_at": "", "workspace_id_hint": "00001111",
            "files": [{"path": "f.txt", "kind": "file", "classification": "inline",
                       "oid": hashlib.sha256(content).hexdigest(), "size": len(content)}],
        }
        buf = io.BytesIO()
        with _zf.ZipFile(buf, "w") as zf:
            zf.writestr("kerf-manifest.json", json.dumps(manifest))
            zf.writestr("f.txt", content)
        zip_content = buf.getvalue()

        mock = _mock_resp(zip_content)
        out_dir = tmp_path / "slug-test"

        with patch("urllib.request.urlopen", return_value=mock):
            code, _, err = _run_cmd([
                "export", "00001111-0000-0000-0000-000000000000",
                "--out", str(out_dir),
                "--url", "http://fake-api",
            ])

        assert code == 0
        assert (out_dir / ".kerf" / "metadata.json").exists()

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


# ---------------------------------------------------------------------------
# import — behaviour tests
# ---------------------------------------------------------------------------

def _make_export_dir(tmp_path: Path, files: dict, project_name: str = "Test Project") -> Path:
    """Build a minimal export directory (as kerf export would produce)."""
    import hashlib, zipfile as _zf, json as _json
    out_dir = tmp_path
    manifest_files = []
    for path, content in files.items():
        oid = hashlib.sha256(content).hexdigest()
        manifest_files.append({
            "path": path, "kind": "file", "classification": "inline",
            "oid": oid, "size": len(content),
        })
        dest = out_dir / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

    kerf_dir = out_dir / ".kerf"
    kerf_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "kerf_export_version": 1,
        "project_id": "test-pid",
        "name": project_name,
        "description": "", "tags": [],
        "created_at": "", "workspace_id_hint": "aaaabbbb",
    }
    (kerf_dir / "metadata.json").write_text(_json.dumps(metadata), encoding="utf-8")
    lock = {
        "kerf_lock_version": 1,
        "files": manifest_files,
    }
    (kerf_dir / "manifest.lock").write_text(_json.dumps(lock), encoding="utf-8")
    return out_dir


class TestImportBehaviour:
    def test_import_creates_project_and_uploads_files(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        files = {"design.step": b"STEP AP214", "notes.txt": b"some notes"}
        export_dir = _make_export_dir(tmp_path / "exp", files, project_name="Test Project")

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

        assert code == 0
        assert "new-proj-id" in err
        assert "2/2" in err

    def test_import_uses_metadata_name(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        export_dir = _make_export_dir(tmp_path / "exp", {"a.txt": b"hello"}, project_name="From Metadata")

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

        export_dir = _make_export_dir(tmp_path / "exp", {}, project_name="Old Name")

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

    def test_import_round_trip(self, tmp_path, monkeypatch):
        """Round-trip: content uploaded matches content in the export directory."""
        monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_test")

        original_content = b"This is the source of truth."
        export_dir = _make_export_dir(tmp_path / "exp", {"src.txt": original_content}, project_name="RT")

        uploaded_content = []

        def _urlopen(req, timeout=None):
            if hasattr(req, "data") and req.data:
                body = json.loads(req.data.decode())
                if "content" in body:
                    uploaded_content.append(body["content"])
            return _mock_resp(json.dumps({"id": "pid-rt"}).encode())

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            code, _, _ = _run_cmd([
                "import", str(export_dir),
                "--url", "http://fake-api",
            ])

        assert code == 0
        assert original_content.decode() in uploaded_content


# ---------------------------------------------------------------------------
# _create_project unit tests
# ---------------------------------------------------------------------------

class TestCreateProject:
    def test_returns_project_id(self):
        from kerf_cli.portability import _create_project

        resp = _mock_resp(json.dumps({"id": "the-new-pid"}).encode())
        with patch("urllib.request.urlopen", return_value=resp):
            pid = _create_project("http://api", "tok", "My Project")
        assert pid == "the-new-pid"

    def test_auth_failure_raises_api_error(self):
        from kerf_cli.portability import _create_project, _ApiError
        import urllib.error

        exc = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        with patch("urllib.request.urlopen", side_effect=exc):
            with pytest.raises(_ApiError) as exc_info:
                _create_project("http://api", "bad", "Proj")
        assert exc_info.value.exit_code == 2
