"""Tests for kerf_core.storage.classify.should_store_as_blob (T-133).

Coverage matrix:
- small valid UTF-8                → inline (False)
- >1 MiB valid UTF-8 STEP-like    → blob   (True)  [size dominates]
- small invalid UTF-8 (binary)    → blob   (True)
- threshold is honoured from config setting
- exactly-at-threshold boundary   → inline (False)  [> not >=]
- exactly one byte over threshold  → blob  (True)
"""

import pytest

from kerf_core.storage.classify import should_store_as_blob


_ONE_MIB = 1_048_576
_DEFAULT_THRESHOLD = _ONE_MIB  # matches git_inline_max_bytes default


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ascii_sample(n: int = 512) -> bytes:
    """Return n bytes of valid ASCII / UTF-8 content."""
    chunk = b"STEP file body line\n"
    return (chunk * ((n // len(chunk)) + 1))[:n]


def _binary_sample() -> bytes:
    """Return a few bytes that are not valid UTF-8."""
    return bytes([0xFF, 0xFE, 0x00, 0x01])


# ---------------------------------------------------------------------------
# Core predicate tests
# ---------------------------------------------------------------------------


class TestInlineSmallUtf8:
    """Small, valid UTF-8 file → inline."""

    def test_small_ascii_is_inline(self):
        assert should_store_as_blob("hello.py", 256, _ascii_sample(256), threshold=_DEFAULT_THRESHOLD) is False

    def test_zero_bytes_is_inline(self):
        assert should_store_as_blob("empty.txt", 0, b"", threshold=_DEFAULT_THRESHOLD) is False

    def test_exactly_at_threshold_is_inline(self):
        # > threshold, not >= threshold; exactly at boundary → inline
        assert (
            should_store_as_blob(
                "big.step", _DEFAULT_THRESHOLD, _ascii_sample(512), threshold=_DEFAULT_THRESHOLD
            )
            is False
        )


class TestBlobLargeUtf8:
    """File larger than threshold → blob, even if valid UTF-8 (STEP-is-ASCII case)."""

    def test_five_mib_step_is_blob(self):
        size = 5 * _ONE_MIB  # 5 MiB — valid ASCII but huge
        assert should_store_as_blob("model.step", size, _ascii_sample(8192), threshold=_DEFAULT_THRESHOLD) is True

    def test_one_byte_over_threshold_is_blob(self):
        size = _DEFAULT_THRESHOLD + 1
        assert should_store_as_blob("just-over.txt", size, _ascii_sample(512), threshold=_DEFAULT_THRESHOLD) is True

    def test_exact_large_size_with_custom_threshold(self):
        custom = 4096
        assert should_store_as_blob("file.bin", custom + 1, _ascii_sample(256), threshold=custom) is True


class TestBlobInvalidUtf8:
    """Small but binary content → blob."""

    def test_binary_bytes_is_blob(self):
        sample = _binary_sample()
        assert should_store_as_blob("texture.png", len(sample), sample, threshold=_DEFAULT_THRESHOLD) is True

    def test_high_bytes_are_blob(self):
        # 0x80–0xBF are continuation bytes that are invalid as stand-alone UTF-8
        sample = bytes(range(0x80, 0x90))
        assert should_store_as_blob("mesh.bin", len(sample), sample, threshold=_DEFAULT_THRESHOLD) is True

    def test_mixed_valid_then_invalid_utf8_is_blob(self):
        sample = b"valid prefix\xff\xfe"
        assert should_store_as_blob("mixed.dat", len(sample), sample, threshold=_DEFAULT_THRESHOLD) is True


# ---------------------------------------------------------------------------
# Threshold customisation
# ---------------------------------------------------------------------------


class TestCustomThreshold:
    """Explicit threshold values are honoured."""

    def test_zero_threshold_small_utf8_is_blob(self):
        # threshold=0 → any non-empty file is > 0 → blob
        assert should_store_as_blob("tiny.py", 1, b"x", threshold=0) is True

    def test_very_large_threshold_keeps_large_utf8_inline(self):
        threshold = 100 * _ONE_MIB  # 100 MiB
        size = 5 * _ONE_MIB         # 5 MiB < threshold → inline if UTF-8
        assert should_store_as_blob("big_but_ok.step", size, _ascii_sample(512), threshold=threshold) is False


# ---------------------------------------------------------------------------
# Config integration (reads Settings.git_inline_max_bytes via default path)
# ---------------------------------------------------------------------------


class TestConfigDefaultThreshold:
    """Calling without an explicit threshold reads from Settings."""

    def test_default_threshold_from_config_for_small_file(self):
        # A tiny file should be inline when no explicit threshold is passed
        assert should_store_as_blob("readme.txt", 100, b"Hello world") is False

    def test_default_threshold_from_config_for_large_file(self):
        # A file larger than 1 MiB should be a blob by default
        size = _DEFAULT_THRESHOLD + 1
        assert should_store_as_blob("big.step", size, _ascii_sample(512)) is True
