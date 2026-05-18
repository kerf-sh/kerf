"""Pure-Python diff helpers for the git commit diff endpoint (T-186).

Provides:
  - ``file_kind_from_path``  — map a filename extension to a kind label
  - ``is_binary_content``    — classify bytes as binary (using the same
                               ``should_store_as_blob`` predicate from T-133)
  - ``unified_text_diff``    — produce a unified-diff string from two byte
                               strings decoded as UTF-8 (errors='replace')

No I/O, no network, no DB dependencies.
"""

from __future__ import annotations

import difflib
import posixpath

from kerf_core.storage.classify import should_store_as_blob

__all__ = [
    "file_kind_from_path",
    "is_binary_content",
    "unified_text_diff",
]

# ---------------------------------------------------------------------------
# Extension → kind label
# ---------------------------------------------------------------------------

_EXT_KIND: dict[str, str] = {
    # CAD / geometry
    ".step": "step",
    ".stp": "step",
    ".stl": "stl",
    ".obj": "obj",
    ".iges": "iges",
    ".igs": "iges",
    ".brep": "brep",
    ".3mf": "3mf",
    # Images / raster
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".bmp": "image",
    ".tiff": "image",
    ".tif": "image",
    ".svg": "svg",
    # Scripts / source
    ".py": "script",
    ".js": "script",
    ".ts": "script",
    ".jsx": "script",
    ".tsx": "script",
    ".jscad": "script",
    ".lua": "script",
    ".sh": "script",
    # Markup / data
    ".json": "data",
    ".yaml": "data",
    ".yml": "data",
    ".toml": "data",
    ".xml": "data",
    ".csv": "data",
    # Text
    ".txt": "text",
    ".md": "text",
    ".rst": "text",
    ".org": "text",
    # Drawing / PCB
    ".dxf": "drawing",
    ".dwg": "drawing",
    ".kicad_pcb": "pcb",
    ".kicad_sch": "schematic",
    # Firmware / ELF
    ".elf": "binary",
    ".hex": "binary",
    ".bin": "binary",
    # Compressed / archive
    ".zip": "archive",
    ".tar": "archive",
    ".gz": "archive",
    ".xz": "archive",
}


def file_kind_from_path(path: str) -> str:
    """Return a kind label for the file at *path* based on its extension.

    Falls back to ``"file"`` for unknown extensions.
    """
    _, ext = posixpath.splitext(path.lower())
    return _EXT_KIND.get(ext, "file")


# ---------------------------------------------------------------------------
# Binary classification
# ---------------------------------------------------------------------------

# Sample size sent to should_store_as_blob — mirrors the constant in
# materialize.py so the two classifiers always agree.
_SAMPLE_BYTES = 8192

# Use a very large threshold so the decision is purely encoding-based:
# we never want to declare a small-but-binary file as "text" just because
# it is below the storage threshold.  Integer too large for any real file.
_HUGE = 1 << 62


def is_binary_content(data: bytes) -> bool:
    """Return True if *data* should be treated as binary (non-diffable).

    Delegates to the canonical T-133 ``should_store_as_blob`` classifier
    with a threshold large enough that size alone never triggers the blob
    decision — only the UTF-8 probe matters.
    """
    return should_store_as_blob(
        "",  # name unused by classifier
        len(data),
        data[:_SAMPLE_BYTES],
        threshold=_HUGE,
    )


# ---------------------------------------------------------------------------
# Unified text diff
# ---------------------------------------------------------------------------

def unified_text_diff(
    old_bytes: bytes,
    new_bytes: bytes,
    fromfile: str = "a",
    tofile: str = "b",
    *,
    context: int = 3,
) -> str:
    """Return a unified-diff string comparing *old_bytes* to *new_bytes*.

    Both sides are decoded as UTF-8 with ``errors='replace'`` so that
    partial-binary files (e.g. a script with one bad byte) still produce a
    readable diff instead of raising.

    Returns an empty string when the contents are identical.
    """
    old_text = old_bytes.decode("utf-8", errors="replace")
    new_text = new_bytes.decode("utf-8", errors="replace")

    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    chunks = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{fromfile}",
            tofile=f"b/{tofile}",
            n=context,
        )
    )
    return "".join(chunks)
