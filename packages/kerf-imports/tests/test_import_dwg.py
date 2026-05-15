"""
test_import_dwg.py — hermetic tests for the DWG bridge and import_dwg tool (T-8).

All tests mock the libredwg bridge / subprocess — no real libredwg installation
is required.  The test suite covers:

  Bridge layer (kerf_imports.dwg.bridge)
  ---------------------------------------
  1.  bridge_absent_returns_unavailable     — both back-ends absent → available=False
  2.  bridge_python_detected                — Python binding stub → backend="python"
  3.  bridge_cli_detected                   — dwgread on PATH stub → backend="cli"
  4.  bridge_cli_version_from_stdout        — version string parsed from subprocess
  5.  bridge_unavailable_raises             — convert_dwg_to_dxf raises DwgBridgeUnavailable
  6.  bridge_python_conversion_ok           — python binding returns DXF string
  7.  bridge_python_conversion_bytes_ok     — python binding returns bytes, auto-decoded
  8.  bridge_python_empty_result_raises     — empty return raises DwgConversionError
  9.  bridge_cli_conversion_ok              — subprocess writes DXF side-by-side file
  10. bridge_cli_stdout_fallback            — subprocess writes to stdout when no file
  11. bridge_cli_nonzero_exit_raises        — non-zero returncode raises DwgConversionError
  12. bridge_cli_timeout_raises             — TimeoutExpired wrapped in DwgConversionError
  13. bridge_empty_input_raises             — empty bytes raises DwgConversionError
  14. bridge_cache_invalidation             — _reset_cache re-detects backend
  15. get_bridge_info_shape                 — returns dict with expected keys

  Tool layer (kerf_imports.tools.import_dwg)
  -------------------------------------------
  16. tool_bridge_absent_friendly_error     — no bridge → {ok:false, code:DWG_BRIDGE_UNAVAILABLE}
  17. tool_bad_json_args                    — non-JSON args → BAD_ARGS
  18. tool_missing_project_id               — omit project_id → BAD_ARGS
  19. tool_missing_blob_ref                 — omit blob ref → BAD_ARGS
  20. tool_no_storage                       — ctx.storage=None → NO_STORAGE
  21. tool_blob_not_found                   — storage.get returns None → NOT_FOUND
  22. tool_conversion_error_propagated      — bridge raises DwgConversionError → error
  23. tool_routes_through_dxf_mapper        — mocked bridge → DXF with LINE → sketch entity
  24. tool_text_goes_to_drawing             — DXF with TEXT entity → drawing annotation
  25. tool_expand_inserts_false             — expand_inserts=False → insert entity not expanded
  26. tool_custom_import_folder             — custom folder stored in result
  27. tool_empty_dxf_output                 — bridge returns whitespace-only → error
  28. tool_stats_shape                      — result.stats has all required keys

"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import uuid
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


def _line_dxf(x1=0, y1=0, x2=10, y2=0, layer="0") -> str:
    return f"""\
  0
SECTION
  2
ENTITIES
  0
LINE
  8
{layer}
 10
{x1}
 20
{y1}
 11
{x2}
 21
{y2}
  0
ENDSEC
  0
EOF
"""


def _text_dxf(x=5, y=5, value="hello") -> str:
    return f"""\
  0
SECTION
  2
ENTITIES
  0
TEXT
  8
0
 10
{x}
 20
{y}
  1
{value}
  0
ENDSEC
  0
EOF
"""


def _circle_dxf(cx=0, cy=0, r=5.0) -> str:
    return f"""\
  0
SECTION
  2
ENTITIES
  0
CIRCLE
  8
0
 10
{cx}
 20
{cy}
 40
{r}
  0
ENDSEC
  0
EOF
"""


class FakeStorage:
    def __init__(self, data: bytes | None = b"\x00dwg-fake-bytes"):
        self._data = data

    async def get(self, key: str) -> bytes | None:
        return self._data


class FakePool:
    """Minimal pool stub that records INSERTs and returns fake UUIDs."""

    def __init__(self):
        self.rows: list[dict] = []
        self._folder_id = uuid.uuid4()

    async def fetchrow(self, query, *args):
        # For folder lookups return None (force creation)
        return None

    async def fetchval(self, query, *args):
        fid = uuid.uuid4()
        self.rows.append({"id": fid, "args": args})
        return fid


def make_ctx(storage=None, pool=None):
    from kerf_core.utils.context import ProjectCtx
    return ProjectCtx(
        pool=pool or FakePool(),
        storage=storage,
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )


# ---------------------------------------------------------------------------
# Reset bridge cache before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_bridge_cache():
    from kerf_imports.dwg import bridge as _b
    _b._reset_cache()
    yield
    _b._reset_cache()


# ===========================================================================
# Bridge layer tests (1-15)
# ===========================================================================

class TestBridgeDetection:
    def test_1_bridge_absent_returns_unavailable(self):
        """When neither libredwg import nor dwgread binary exists, available=False."""
        from kerf_imports.dwg.bridge import dwg_bridge_available, _detect_backend

        with patch.dict(sys.modules, {"libredwg": None}):
            with patch("shutil.which", return_value=None):
                from kerf_imports.dwg import bridge as _b
                _b._reset_cache()
                assert not dwg_bridge_available()

    def test_2_bridge_python_detected(self):
        """Python binding stub → backend='python'."""
        fake_libredwg = types.ModuleType("libredwg")
        fake_libredwg.__version__ = "0.13.0"
        with patch.dict(sys.modules, {"libredwg": fake_libredwg}):
            from kerf_imports.dwg import bridge as _b
            _b._reset_cache()
            info = _b.get_bridge_info()
        assert info["available"] is True
        assert info["backend"] == "python"
        assert "0.13" in (info["version"] or "")

    def test_3_bridge_cli_detected(self):
        """dwgread on PATH stub → backend='cli'."""
        with patch.dict(sys.modules, {"libredwg": None}):
            with patch("shutil.which", return_value="/usr/bin/dwgread"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        stdout="dwgread 0.13\n",
                        stderr="",
                        returncode=0,
                    )
                    from kerf_imports.dwg import bridge as _b
                    _b._reset_cache()
                    info = _b.get_bridge_info()
        assert info["available"] is True
        assert info["backend"] == "cli"

    def test_4_bridge_cli_version_from_stdout(self):
        """Version string is taken from the first line of dwgread --version output."""
        with patch.dict(sys.modules, {"libredwg": None}):
            with patch("shutil.which", return_value="/usr/local/bin/dwgread"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        stdout="dwgread 0.12.4\nextra\n",
                        stderr="",
                        returncode=0,
                    )
                    from kerf_imports.dwg import bridge as _b
                    _b._reset_cache()
                    info = _b.get_bridge_info()
        assert info["version"] == "dwgread 0.12.4"

    def test_5_bridge_unavailable_raises(self):
        """convert_dwg_to_dxf raises DwgBridgeUnavailable when no back-end present."""
        from kerf_imports.dwg.bridge import convert_dwg_to_dxf, DwgBridgeUnavailable

        with patch.dict(sys.modules, {"libredwg": None}):
            with patch("shutil.which", return_value=None):
                from kerf_imports.dwg import bridge as _b
                _b._reset_cache()
                with pytest.raises(DwgBridgeUnavailable):
                    convert_dwg_to_dxf(b"\x00fake-dwg")

    def test_6_bridge_python_conversion_ok(self):
        """Python binding dwg2dxf() → DXF string returned as-is."""
        line_dxf = _line_dxf()
        fake_libredwg = types.ModuleType("libredwg")
        fake_libredwg.__version__ = "0.13"
        fake_libredwg.dwg2dxf = lambda data: line_dxf

        with patch.dict(sys.modules, {"libredwg": fake_libredwg}):
            from kerf_imports.dwg import bridge as _b
            _b._reset_cache()
            result = _b.convert_dwg_to_dxf(b"\x00dwg")
        assert "LINE" in result

    def test_7_bridge_python_conversion_bytes_ok(self):
        """Python binding that returns bytes is auto-decoded."""
        line_dxf = _line_dxf()
        fake_libredwg = types.ModuleType("libredwg")
        fake_libredwg.__version__ = "0.13"
        fake_libredwg.dwg2dxf = lambda data: line_dxf.encode("utf-8")

        with patch.dict(sys.modules, {"libredwg": fake_libredwg}):
            from kerf_imports.dwg import bridge as _b
            _b._reset_cache()
            result = _b.convert_dwg_to_dxf(b"\x00dwg")
        assert isinstance(result, str)
        assert "LINE" in result

    def test_8_bridge_python_empty_result_raises(self):
        """Python binding returning empty string raises DwgConversionError."""
        from kerf_imports.dwg.bridge import DwgConversionError

        fake_libredwg = types.ModuleType("libredwg")
        fake_libredwg.__version__ = "0.13"
        fake_libredwg.dwg2dxf = lambda data: ""

        with patch.dict(sys.modules, {"libredwg": fake_libredwg}):
            from kerf_imports.dwg import bridge as _b
            _b._reset_cache()
            with pytest.raises(DwgConversionError):
                _b.convert_dwg_to_dxf(b"\x00dwg")

    def test_9_bridge_cli_conversion_ok(self, tmp_path):
        """CLI back-end: subprocess writes DXF file alongside input → read back."""
        line_dxf = _line_dxf()

        def fake_run(cmd, **kwargs):
            # dwgread writes input.dxf in cwd (tmpdir)
            cwd = kwargs.get("cwd", str(tmp_path))
            dxf_out = cwd + "/input.dxf"
            with open(dxf_out, "w") as fh:
                fh.write(line_dxf)
            return MagicMock(returncode=0, stdout=b"", stderr=b"")

        with patch.dict(sys.modules, {"libredwg": None}):
            with patch("shutil.which", return_value="/usr/bin/dwgread"):
                with patch("subprocess.run", side_effect=fake_run):
                    from kerf_imports.dwg import bridge as _b
                    _b._reset_cache()
                    # Detect CLI
                    _ = _b.get_bridge_info()

                    with patch("subprocess.run", side_effect=fake_run):
                        result = _b.convert_dwg_to_dxf(b"\x00fake-dwg")
        assert "LINE" in result

    def test_10_bridge_cli_stdout_fallback(self):
        """CLI back-end: when no file is written, stdout is used as DXF text."""
        line_dxf = _line_dxf()

        def fake_run_stdout(cmd, **kwargs):
            return MagicMock(returncode=0, stdout=line_dxf.encode(), stderr=b"")

        with patch.dict(sys.modules, {"libredwg": None}):
            with patch("shutil.which", return_value="/usr/bin/dwgread"):
                with patch("subprocess.run") as mock_run:
                    # First call: --version (detection)
                    mock_run.return_value = MagicMock(
                        stdout="dwgread 0.13\n", stderr="", returncode=0
                    )
                    from kerf_imports.dwg import bridge as _b
                    _b._reset_cache()
                    _ = _b.get_bridge_info()

                # Second call: actual conversion (no file written → stdout)
                with patch("subprocess.run", side_effect=fake_run_stdout):
                    result = _b.convert_dwg_to_dxf(b"\x00fake-dwg")
        assert "LINE" in result

    def test_11_bridge_cli_nonzero_exit_raises(self):
        """CLI non-zero exit code raises DwgConversionError."""
        from kerf_imports.dwg.bridge import DwgConversionError

        def fake_run_fail(cmd, **kwargs):
            return MagicMock(
                returncode=1,
                stdout=b"",
                stderr=b"unsupported DWG version",
            )

        with patch.dict(sys.modules, {"libredwg": None}):
            with patch("shutil.which", return_value="/usr/bin/dwgread"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        stdout="dwgread 0.13\n", stderr="", returncode=0
                    )
                    from kerf_imports.dwg import bridge as _b
                    _b._reset_cache()
                    _ = _b.get_bridge_info()

                with patch("subprocess.run", side_effect=fake_run_fail):
                    with pytest.raises(DwgConversionError, match="exited with code 1"):
                        _b.convert_dwg_to_dxf(b"\x00fake-dwg")

    def test_12_bridge_cli_timeout_raises(self):
        """subprocess.TimeoutExpired is wrapped in DwgConversionError."""
        import subprocess
        from kerf_imports.dwg.bridge import DwgConversionError

        def fake_run_timeout(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 60)

        with patch.dict(sys.modules, {"libredwg": None}):
            with patch("shutil.which", return_value="/usr/bin/dwgread"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        stdout="dwgread 0.13\n", stderr="", returncode=0
                    )
                    from kerf_imports.dwg import bridge as _b
                    _b._reset_cache()
                    _ = _b.get_bridge_info()

                with patch("subprocess.run", side_effect=fake_run_timeout):
                    with pytest.raises(DwgConversionError, match="timed out"):
                        _b.convert_dwg_to_dxf(b"\x00fake-dwg")

    def test_13_bridge_empty_input_raises(self):
        """Empty bytes input raises DwgConversionError without calling any backend."""
        from kerf_imports.dwg.bridge import DwgConversionError

        fake_libredwg = types.ModuleType("libredwg")
        fake_libredwg.__version__ = "0.13"
        fake_libredwg.dwg2dxf = lambda data: _line_dxf()

        with patch.dict(sys.modules, {"libredwg": fake_libredwg}):
            from kerf_imports.dwg import bridge as _b
            _b._reset_cache()
            with pytest.raises(DwgConversionError, match="empty"):
                _b.convert_dwg_to_dxf(b"")

    def test_14_bridge_cache_invalidation(self):
        """After _reset_cache, detection runs again."""
        from kerf_imports.dwg import bridge as _b

        # First detection: no backend
        with patch.dict(sys.modules, {"libredwg": None}):
            with patch("shutil.which", return_value=None):
                _b._reset_cache()
                assert not _b.dwg_bridge_available()

        # Reset and re-detect with python binding
        fake_libredwg = types.ModuleType("libredwg")
        fake_libredwg.__version__ = "0.13"
        with patch.dict(sys.modules, {"libredwg": fake_libredwg}):
            _b._reset_cache()
            assert _b.dwg_bridge_available()

    def test_15_get_bridge_info_shape(self):
        """get_bridge_info() always returns a dict with available, backend, version."""
        from kerf_imports.dwg import bridge as _b

        with patch.dict(sys.modules, {"libredwg": None}):
            with patch("shutil.which", return_value=None):
                _b._reset_cache()
                info = _b.get_bridge_info()
        assert set(info.keys()) >= {"available", "backend", "version"}
        assert isinstance(info["available"], bool)
        assert info["backend"] is None


# ===========================================================================
# Tool layer tests (16-28)
# ===========================================================================

def _fake_python_binding(dxf_text: str):
    """Return a fake libredwg module that yields dxf_text from dwg2dxf()."""
    mod = types.ModuleType("libredwg")
    mod.__version__ = "0.13"
    mod.dwg2dxf = lambda data: dxf_text
    return mod


class TestImportDwgTool:
    def _run_tool(self, args: dict, storage=None, pool=None, binding_dxf: str | None = None):
        """Helper: run import_dwg with optional mocked python binding."""
        from kerf_imports.tools.import_dwg import import_dwg
        from kerf_imports.dwg import bridge as _b

        ctx = make_ctx(storage=storage, pool=pool or FakePool())

        if binding_dxf is not None:
            fake = _fake_python_binding(binding_dxf)
            patch_modules = patch.dict(sys.modules, {"libredwg": fake})
        else:
            patch_modules = patch.dict(sys.modules, {"libredwg": None})

        with patch_modules:
            _b._reset_cache()
            if binding_dxf is None:
                with patch("shutil.which", return_value=None):
                    result_str = run(import_dwg(ctx, json.dumps(args).encode()))
            else:
                result_str = run(import_dwg(ctx, json.dumps(args).encode()))

        return json.loads(result_str)

    def test_16_tool_bridge_absent_friendly_error(self):
        """No bridge present → {error:..., code:'DWG_BRIDGE_UNAVAILABLE'}."""
        result = self._run_tool(
            {"project_id": str(uuid.uuid4()), "file_blob_id_or_storage_key": "blob-1"},
            storage=FakeStorage(),
            binding_dxf=None,
        )
        assert "error" in result
        assert "DWG_BRIDGE_UNAVAILABLE" in result.get("code", "")
        assert "libredwg" in result.get("error", "").lower()

    def test_17_tool_bad_json_args(self):
        """Non-JSON args byte string → BAD_ARGS."""
        from kerf_imports.tools.import_dwg import import_dwg
        from kerf_imports.dwg import bridge as _b

        ctx = make_ctx(storage=FakeStorage())
        with patch.dict(sys.modules, {"libredwg": None}):
            _b._reset_cache()
            with patch("shutil.which", return_value=None):
                result_str = run(import_dwg(ctx, b"not-valid-json!!!"))
        result = json.loads(result_str)
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_18_tool_missing_project_id(self):
        """Missing project_id → BAD_ARGS."""
        result = self._run_tool(
            {"file_blob_id_or_storage_key": "blob-1"},
            storage=FakeStorage(),
            binding_dxf=_line_dxf(),
        )
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_19_tool_missing_blob_ref(self):
        """Missing file_blob_id_or_storage_key → BAD_ARGS."""
        result = self._run_tool(
            {"project_id": str(uuid.uuid4())},
            storage=FakeStorage(),
            binding_dxf=_line_dxf(),
        )
        assert "error" in result
        assert result.get("code") == "BAD_ARGS"

    def test_20_tool_no_storage(self):
        """ctx.storage=None → NO_STORAGE."""
        result = self._run_tool(
            {"project_id": str(uuid.uuid4()), "file_blob_id_or_storage_key": "b"},
            storage=None,
            binding_dxf=_line_dxf(),
        )
        assert "error" in result
        assert result.get("code") == "NO_STORAGE"

    def test_21_tool_blob_not_found(self):
        """storage.get returns None → NOT_FOUND."""
        result = self._run_tool(
            {"project_id": str(uuid.uuid4()), "file_blob_id_or_storage_key": "missing"},
            storage=FakeStorage(data=None),
            binding_dxf=_line_dxf(),
        )
        assert "error" in result
        assert result.get("code") == "NOT_FOUND"

    def test_22_tool_conversion_error_propagated(self):
        """Bridge raising DwgConversionError → DWG_CONVERSION_ERROR."""
        from kerf_imports.dwg.bridge import DwgConversionError
        from kerf_imports.tools.import_dwg import import_dwg
        from kerf_imports.dwg import bridge as _b

        fake = types.ModuleType("libredwg")
        fake.__version__ = "0.13"
        fake.dwg2dxf = MagicMock(side_effect=DwgConversionError("corrupt file"))

        ctx = make_ctx(storage=FakeStorage())
        with patch.dict(sys.modules, {"libredwg": fake}):
            _b._reset_cache()
            result_str = run(import_dwg(
                ctx,
                json.dumps({
                    "project_id": str(uuid.uuid4()),
                    "file_blob_id_or_storage_key": "blob-1",
                }).encode(),
            ))
        result = json.loads(result_str)
        assert "error" in result
        assert "DWG_CONVERSION_ERROR" in result.get("code", "")

    def test_23_tool_routes_through_dxf_mapper(self):
        """Mocked bridge returns DXF with a LINE → result has sketch with entity."""
        pool = FakePool()
        result = self._run_tool(
            {"project_id": str(uuid.uuid4()), "file_blob_id_or_storage_key": "b"},
            storage=FakeStorage(),
            pool=pool,
            binding_dxf=_line_dxf(x1=0, y1=0, x2=10, y2=0),
        )
        assert "error" not in result, f"unexpected error: {result}"
        created = result.get("created_files", [])
        assert any(f["kind"] == "sketch" for f in created), f"No sketch file: {created}"
        assert result["stats"]["entities"] >= 1

    def test_24_tool_text_goes_to_drawing(self):
        """DXF with TEXT entity → drawing annotation created."""
        pool = FakePool()
        result = self._run_tool(
            {"project_id": str(uuid.uuid4()), "file_blob_id_or_storage_key": "b"},
            storage=FakeStorage(),
            pool=pool,
            binding_dxf=_text_dxf(value="Title Block"),
        )
        assert "error" not in result, f"unexpected error: {result}"
        created = result.get("created_files", [])
        assert any(f["kind"] == "drawing" for f in created), f"No drawing file: {created}"
        assert result["stats"]["annotations"] >= 1

    def test_25_tool_expand_inserts_false(self):
        """expand_inserts=False passes through to mapper without crashing."""
        dxf = """\
  0
SECTION
  2
BLOCKS
  0
BLOCK
  2
MYBLK
 10
0.0
 20
0.0
  0
LINE
  8
0
 10
1.0
 20
0.0
 11
2.0
 21
0.0
  0
ENDBLK
  0
ENDSEC
  0
SECTION
  2
ENTITIES
  0
INSERT
  2
MYBLK
 10
5.0
 20
5.0
  0
ENDSEC
  0
EOF
"""
        result = self._run_tool(
            {
                "project_id": str(uuid.uuid4()),
                "file_blob_id_or_storage_key": "b",
                "expand_inserts": False,
            },
            storage=FakeStorage(),
            pool=FakePool(),
            binding_dxf=dxf,
        )
        assert "error" not in result, f"unexpected error: {result}"

    def test_26_tool_custom_import_folder(self):
        """custom import_folder is reflected in result."""
        result = self._run_tool(
            {
                "project_id": str(uuid.uuid4()),
                "file_blob_id_or_storage_key": "b",
                "import_folder": "/arch/floors/ground",
            },
            storage=FakeStorage(),
            pool=FakePool(),
            binding_dxf=_line_dxf(),
        )
        assert "error" not in result, f"unexpected error: {result}"
        assert "/arch/floors/ground" in result.get("import_folder", "")

    def test_27_tool_empty_dxf_output(self):
        """Bridge returning whitespace-only DXF → DWG_CONVERSION_ERROR."""
        from kerf_imports.tools.import_dwg import import_dwg
        from kerf_imports.dwg import bridge as _b

        fake = types.ModuleType("libredwg")
        fake.__version__ = "0.13"
        fake.dwg2dxf = lambda data: "   \n  "   # whitespace only

        ctx = make_ctx(storage=FakeStorage())
        with patch.dict(sys.modules, {"libredwg": fake}):
            _b._reset_cache()
            result_str = run(import_dwg(
                ctx,
                json.dumps({
                    "project_id": str(uuid.uuid4()),
                    "file_blob_id_or_storage_key": "b",
                }).encode(),
            ))
        result = json.loads(result_str)
        assert "error" in result
        assert "DWG_CONVERSION_ERROR" in result.get("code", "")

    def test_28_tool_stats_shape(self):
        """Result stats dict has all required keys."""
        result = self._run_tool(
            {"project_id": str(uuid.uuid4()), "file_blob_id_or_storage_key": "b"},
            storage=FakeStorage(),
            pool=FakePool(),
            binding_dxf=_line_dxf(),
        )
        assert "error" not in result, f"unexpected error: {result}"
        stats = result.get("stats", {})
        for key in ("entities", "annotations", "blocks", "warnings", "loops"):
            assert key in stats, f"missing stats key: {key}"

    def test_bridge_info_in_ok_result(self):
        """Successful import includes bridge info in result."""
        result = self._run_tool(
            {"project_id": str(uuid.uuid4()), "file_blob_id_or_storage_key": "b"},
            storage=FakeStorage(),
            pool=FakePool(),
            binding_dxf=_line_dxf(),
        )
        assert "error" not in result, f"unexpected error: {result}"
        bridge = result.get("bridge", {})
        assert bridge.get("available") is True
        assert bridge.get("backend") == "python"

    def test_circle_entity_in_sketch(self):
        """CIRCLE in DWG-converted DXF → circle entity in sketch output."""
        pool = FakePool()
        result = self._run_tool(
            {"project_id": str(uuid.uuid4()), "file_blob_id_or_storage_key": "b"},
            storage=FakeStorage(),
            pool=pool,
            binding_dxf=_circle_dxf(cx=5, cy=5, r=3.0),
        )
        assert "error" not in result, f"unexpected error: {result}"
        assert result["stats"]["entities"] >= 1
        # loops detected: circle is a trivial loop
        assert result["stats"]["loops"] >= 1

    def test_default_import_folder(self):
        """Default import_folder is /dwg_import."""
        result = self._run_tool(
            {"project_id": str(uuid.uuid4()), "file_blob_id_or_storage_key": "b"},
            storage=FakeStorage(),
            pool=FakePool(),
            binding_dxf=_line_dxf(),
        )
        assert "error" not in result, f"unexpected error: {result}"
        assert result.get("import_folder") == "/dwg_import"
