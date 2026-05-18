"""Unit tests for kerf_core.storage.diff (T-186).

Pure-Python: no DB, no network, no filesystem I/O.

Run:
    PYTHONPATH=packages/kerf-core/src:packages/kerf-api/src \\
        python3 -m pytest packages/kerf-core/tests/test_storage_diff.py -q
"""
from __future__ import annotations

import pytest

from kerf_core.storage.diff import (
    file_kind_from_path,
    is_binary_content,
    unified_text_diff,
)


# ---------------------------------------------------------------------------
# file_kind_from_path
# ---------------------------------------------------------------------------

class TestFileKindFromPath:
    def test_step_extension(self):
        assert file_kind_from_path("models/part.step") == "step"

    def test_stp_extension(self):
        assert file_kind_from_path("part.STP") == "step"  # case-insensitive

    def test_python_script(self):
        assert file_kind_from_path("src/main.py") == "script"

    def test_json_data(self):
        assert file_kind_from_path("config.json") == "data"

    def test_markdown_text(self):
        assert file_kind_from_path("README.md") == "text"

    def test_png_image(self):
        assert file_kind_from_path("assets/photo.png") == "image"

    def test_unknown_extension_returns_file(self):
        assert file_kind_from_path("data.xyz123") == "file"

    def test_no_extension_returns_file(self):
        assert file_kind_from_path("Makefile") == "file"

    def test_deeply_nested_path(self):
        assert file_kind_from_path("a/b/c/model.stl") == "stl"

    def test_jscad_script(self):
        assert file_kind_from_path("project.jscad") == "script"


# ---------------------------------------------------------------------------
# is_binary_content
# ---------------------------------------------------------------------------

class TestIsBinaryContent:
    def test_valid_utf8_is_not_binary(self):
        data = b"def main():\n    return 'hello'\n"
        assert is_binary_content(data) is False

    def test_empty_bytes_is_not_binary(self):
        assert is_binary_content(b"") is False

    def test_invalid_utf8_is_binary(self):
        # Bytes that are not valid UTF-8 → binary
        # \xff is not valid UTF-8 (it never appears in valid UTF-8)
        assert is_binary_content(b"\xff\xfe") is True

    def test_high_bytes_binary(self):
        data = bytes(range(256)) * 4
        assert is_binary_content(data) is True

    def test_large_utf8_still_not_binary(self):
        # Size alone never triggers binary detection (threshold set huge)
        data = ("x" * 2_000_000).encode("utf-8")
        assert is_binary_content(data) is False

    def test_step_like_text_not_binary(self):
        # STEP files are ASCII text; small ones are not binary
        step_header = (
            b"ISO-10303-21;\n"
            b"HEADER;\n"
            b"FILE_DESCRIPTION(('Open CASCADE Model'),'2;1');\n"
            b"ENDSEC;\n"
        )
        assert is_binary_content(step_header) is False


# ---------------------------------------------------------------------------
# unified_text_diff
# ---------------------------------------------------------------------------

class TestUnifiedTextDiff:
    def test_identical_returns_empty(self):
        data = b"hello world\n"
        result = unified_text_diff(data, data)
        assert result == ""

    def test_added_line(self):
        old = b"line1\nline2\n"
        new = b"line1\nline2\nline3\n"
        diff = unified_text_diff(old, new, fromfile="old.py", tofile="new.py")
        assert "+line3" in diff
        assert "--- a/old.py" in diff
        assert "+++ b/new.py" in diff

    def test_removed_line(self):
        old = b"line1\nline2\nline3\n"
        new = b"line1\nline3\n"
        diff = unified_text_diff(old, new)
        assert "-line2" in diff

    def test_modified_line(self):
        old = b"value = 1\n"
        new = b"value = 2\n"
        diff = unified_text_diff(old, new)
        assert "-value = 1" in diff
        assert "+value = 2" in diff

    def test_binary_bytes_decoded_with_replacement(self):
        # Should not raise even for non-UTF-8 bytes
        old = b"header\n\xff\xfe\n"
        new = b"header\n\xff\xfe\nfooter\n"
        diff = unified_text_diff(old, new)
        # The replacement char U+FFFD is used for bad bytes
        assert isinstance(diff, str)

    def test_empty_old_to_new(self):
        old = b""
        new = b"brand new content\n"
        diff = unified_text_diff(old, new)
        assert "+brand new content" in diff

    def test_new_to_empty(self):
        old = b"removed content\n"
        new = b""
        diff = unified_text_diff(old, new)
        assert "-removed content" in diff

    def test_context_lines_respected(self):
        # With context=0, there should be no unchanged context lines
        lines = [f"line{i}\n" for i in range(10)]
        old_data = "".join(lines).encode()
        lines[5] = "CHANGED\n"
        new_data = "".join(lines).encode()
        diff0 = unified_text_diff(old_data, new_data, context=0)
        diff3 = unified_text_diff(old_data, new_data, context=3)
        # context=3 diff should be longer (includes surrounding unchanged lines)
        assert len(diff3) > len(diff0)
