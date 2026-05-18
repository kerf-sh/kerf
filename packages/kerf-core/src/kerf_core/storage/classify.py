"""Large-file autodetect classifier.

``should_store_as_blob`` is the canonical predicate used by all storage
paths to decide whether a file should be stored as a Tigris blob (pointer
in git) versus inlined as a regular git tree object.

Decision rules (size dominates):
    1. If ``size_bytes > threshold`` → blob.  A 5 MB ASCII STEP file is
       huge regardless of encoding, so this check happens first.
    2. If ``sample`` is not valid UTF-8 → blob.  Binary payloads (images,
       compiled STEP caches, FEM meshes, …) are never diff-able.
    3. Otherwise → inline.
"""

from __future__ import annotations

from functools import lru_cache


def should_store_as_blob(
    name: str,  # noqa: ARG001 — reserved for future extension (e.g. forced extensions)
    size_bytes: int,
    sample: bytes,
    *,
    threshold: int | None = None,
) -> bool:
    """Return True if the file should be stored as a Tigris blob.

    Args:
        name: File name / relative path (currently unused; reserved for
            extension-based overrides in a future task).
        size_bytes: Total size of the file in bytes.
        sample: A prefix of the file content (e.g. first 8 KiB).  Used
            only to probe UTF-8 validity when the file is small enough
            that size alone does not determine the outcome.
        threshold: Byte threshold above which the file is unconditionally
            a blob.  Defaults to the ``git_inline_max_bytes`` setting.

    Returns:
        True  → store as blob (pointer in git, content in object store).
        False → inline in git tree (text diff preserved).
    """
    if threshold is None:
        threshold = _default_threshold()

    # Rule 1: size dominates — even valid UTF-8 giants are blobs.
    if size_bytes > threshold:
        return True

    # Rule 2: non-UTF-8 content is always a blob.
    try:
        sample.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        return True

    return False


@lru_cache(maxsize=1)
def _default_threshold() -> int:
    """Lazy import to avoid circular imports at module load time."""
    from kerf_core.config import get_settings  # noqa: PLC0415

    return get_settings().git_inline_max_bytes
