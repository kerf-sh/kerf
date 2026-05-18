"""
Git-LFS pointer spec v1 — parse and serialize.

Canonical format (LF line endings, trailing LF, exact key order):

    version https://git-lfs.github.com/spec/v1\n
    oid sha256:<64 lowercase hex chars>\n
    size <decimal bytes, no leading zeros>\n

No I/O, no DB, no external dependencies.
"""

from __future__ import annotations

import re

__all__ = ["LfsPointerError", "serialize", "parse"]

_VERSION_LINE = b"version https://git-lfs.github.com/spec/v1"
_OID_RE = re.compile(r"^[0-9a-f]{64}$")

# Pre-compiled pattern: exactly three LF-terminated lines, nothing more.
_POINTER_RE = re.compile(
    rb"^"
    rb"version https://git-lfs\.github\.com/spec/v1\n"
    rb"oid sha256:([0-9a-f]{64})\n"
    rb"size ([0-9]+)\n"
    rb"$",
)


class LfsPointerError(ValueError):
    """Raised when a Git-LFS pointer is malformed or fails validation."""


def serialize(oid_hex: str, size: int) -> bytes:
    """Return the canonical byte representation of a Git-LFS v1 pointer.

    Args:
        oid_hex: Exactly 64 lowercase hexadecimal characters (SHA-256 digest).
        size:    Non-negative integer byte count.

    Returns:
        UTF-8 bytes with LF line endings and a trailing LF.

    Raises:
        LfsPointerError: If *oid_hex* or *size* fail validation.
    """
    if not isinstance(oid_hex, str):
        raise LfsPointerError(f"oid_hex must be a str, got {type(oid_hex).__name__}")
    if not _OID_RE.match(oid_hex):
        raise LfsPointerError(
            "oid_hex must be exactly 64 lowercase hex characters (sha256 digest); "
            f"got {oid_hex!r}"
        )
    if not isinstance(size, int) or isinstance(size, bool):
        raise LfsPointerError(f"size must be an int, got {type(size).__name__}")
    if size < 0:
        raise LfsPointerError(f"size must be non-negative, got {size}")

    return (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + oid_hex.encode() + b"\n"
        b"size " + str(size).encode() + b"\n"
    )


def parse(data: bytes | str) -> dict[str, object]:
    """Parse a Git-LFS v1 pointer into its components.

    Args:
        data: Raw pointer bytes or a str (decoded as UTF-8).

    Returns:
        ``{"oid": str, "size": int}`` where *oid* is the bare 64-char hex
        digest (no ``sha256:`` prefix) and *size* is a non-negative int.

    Raises:
        LfsPointerError: If *data* is not a byte-exact valid v1 pointer.
    """
    if isinstance(data, str):
        try:
            raw = data.encode("utf-8")
        except Exception as exc:
            raise LfsPointerError(f"Cannot encode input to UTF-8: {exc}") from exc
    elif isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
    else:
        raise LfsPointerError(
            f"data must be bytes or str, got {type(data).__name__}"
        )

    # Reject Windows/old-Mac line endings before any structural check.
    if b"\r" in raw:
        raise LfsPointerError("Pointer must use LF line endings; CR byte found")

    m = _POINTER_RE.fullmatch(raw)
    if m is None:
        _diagnose(raw)  # raises a descriptive LfsPointerError

    oid_hex = m.group(1).decode()
    size_str = m.group(2).decode()

    # Reject leading zeros (e.g. "007") — they would parse but violate canonical form.
    if size_str != str(int(size_str)):
        raise LfsPointerError(
            f"size must have no leading zeros, got {size_str!r}"
        )

    return {"oid": oid_hex, "size": int(size_str)}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _diagnose(raw: bytes) -> None:
    """Raise a descriptive LfsPointerError explaining why *raw* is invalid.

    This is only called when the fast regex fails, so we can afford more
    detailed (but still cheap) checks.
    """
    lines = raw.split(b"\n")

    # A valid pointer is exactly [line0, line1, line2, ""] after split on \n.
    if len(lines) != 4 or lines[3] != b"":
        if not raw.endswith(b"\n"):
            raise LfsPointerError("Pointer must end with a trailing LF")
        raise LfsPointerError(
            f"Pointer must have exactly 3 lines; got {len(lines) - 1} "
            f"(trailing LF counts as a line terminator, not an extra line)"
        )

    line0, line1, line2, _ = lines

    if line0 != _VERSION_LINE:
        raise LfsPointerError(
            f"First line must be {_VERSION_LINE.decode()!r}; got {line0.decode()!r}"
        )

    if not line1.startswith(b"oid sha256:"):
        if line1.startswith(b"oid "):
            raise LfsPointerError(
                f"Only sha256 OIDs are supported; got {line1.decode()!r}"
            )
        raise LfsPointerError(
            f"Second line must start with 'oid sha256:'; got {line1.decode()!r}"
        )

    oid_part = line1[len(b"oid sha256:"):]
    if not re.fullmatch(rb"[0-9a-f]{64}", oid_part):
        if re.search(rb"[A-F]", oid_part):
            raise LfsPointerError(
                "OID hex digits must be lowercase; got uppercase characters"
            )
        raise LfsPointerError(
            f"OID must be exactly 64 lowercase hex chars; got {len(oid_part)} chars"
        )

    if not line2.startswith(b"size "):
        raise LfsPointerError(
            f"Third line must start with 'size '; got {line2.decode()!r}"
        )

    size_part = line2[len(b"size "):]
    if not re.fullmatch(rb"[0-9]+", size_part):
        raise LfsPointerError(
            f"size value must be a non-negative integer; got {size_part.decode()!r}"
        )

    # Should not reach here, but guard against edge cases.
    raise LfsPointerError("Pointer is malformed (unspecified reason)")
