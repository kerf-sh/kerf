"""
Tests for zip-slip / path-traversal protection in kerf_imports.

Covers:
  - safe_basename rejects ``..`` and path-separator tricks
  - _safe_extract skips members whose resolved path escapes the dest dir
  - _safe_extract extracts legitimate members normally
"""

import io
import zipfile
from pathlib import Path

import pytest

from kerf_imports._compat import _safe_extract, safe_basename


# ---------------------------------------------------------------------------
# safe_basename
# ---------------------------------------------------------------------------

class TestSafeBasename:
    def test_plain_name_passes(self):
        assert safe_basename("project.zip") == "project.zip"

    def test_strips_unix_path(self):
        assert safe_basename("some/path/file.kicad_sym") == "file.kicad_sym"

    def test_strips_windows_path(self):
        assert safe_basename("C:\\Users\\attacker\\evil.zip") == "evil.zip"

    def test_double_dot_raises(self):
        with pytest.raises(ValueError):
            safe_basename("..")

    def test_pure_dots_raises(self):
        with pytest.raises(ValueError):
            safe_basename(".")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            safe_basename("")

    def test_traversal_filename_stripped_to_basename(self):
        # The component after the last slash is "authorized_keys" — safe
        result = safe_basename("../../.ssh/authorized_keys")
        assert result == "authorized_keys"


# ---------------------------------------------------------------------------
# _safe_extract
# ---------------------------------------------------------------------------

def _make_zip(members: dict[str, bytes]) -> zipfile.ZipFile:
    """Return an in-memory ZipFile with the given {name: content} members."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    buf.seek(0)
    return zipfile.ZipFile(buf, "r")


def test_safe_extract_normal_member(tmp_path):
    """A normal member (no traversal) must be extracted."""
    zf = _make_zip({"hello.txt": b"world"})
    _safe_extract(zf, tmp_path)
    assert (tmp_path / "hello.txt").read_bytes() == b"world"


def test_safe_extract_nested_normal_member(tmp_path):
    """Subdirectory members that stay inside dest must be extracted."""
    zf = _make_zip({"subdir/data.kicad_sym": b"(kicad_symbol)"})
    _safe_extract(zf, tmp_path)
    assert (tmp_path / "subdir" / "data.kicad_sym").exists()


def test_safe_extract_blocks_traversal(tmp_path):
    """Members whose path resolves outside dest must be skipped."""
    zf = _make_zip({"../../evil.txt": b"pwned"})
    _safe_extract(zf, tmp_path)
    # The file must NOT appear in the parent of tmp_path
    assert not (tmp_path.parent / "evil.txt").exists()
    assert not (tmp_path.parent.parent / "evil.txt").exists()
    # tmp_path itself must be empty (nothing extracted)
    assert list(tmp_path.iterdir()) == []


def test_safe_extract_absolute_path_lands_inside_dest(tmp_path):
    """An absolute-path member (non-standard zip) is safe because Python's
    zipfile strips the leading '/' before resolving, so the member lands
    inside the extraction directory rather than at the filesystem root.
    _safe_extract should therefore extract it (it passes the containment check).
    """
    zf = _make_zip({"/etc/passwd": b"fake"})
    _safe_extract(zf, tmp_path)
    # Python strips the leading '/', so the file lands at tmp_path/etc/passwd
    # — still inside tmp_path, which is safe.
    assert (tmp_path / "etc" / "passwd").exists()


def test_safe_extract_mixed_members(tmp_path):
    """Malicious members are skipped; safe members are still extracted."""
    zf = _make_zip({
        "safe.txt": b"safe content",
        "../../escape.txt": b"bad content",
    })
    _safe_extract(zf, tmp_path)
    assert (tmp_path / "safe.txt").read_bytes() == b"safe content"
    assert not (tmp_path.parent / "escape.txt").exists()
    assert not (tmp_path.parent.parent / "escape.txt").exists()
