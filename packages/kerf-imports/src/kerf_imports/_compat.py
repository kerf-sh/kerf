"""Compatibility shims for running kerf_imports tools outside of the legacy backend."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict


_registry: list = []


def register(spec: "ToolSpec", write: bool = False):
    def decorator(fn: Callable) -> Callable:
        _registry.append({"spec": spec, "write": write, "fn": fn})
        return fn
    return decorator


def ok_payload(v: Any) -> str:
    return json.dumps(v)


def err_payload(msg: str, code: str) -> str:
    return json.dumps({"error": msg, "code": code})


def safe_basename(filename: str) -> str:
    """Return a safe basename for an upload filename.

    Strips all directory components and rejects names that are empty or
    consist solely of dots (e.g. ``..``).  Raises ``ValueError`` for
    names that cannot be made safe.
    """
    # Use Path to strip directory components (handles both / and \ separators).
    name = Path(filename.replace("\\", "/")).name
    if not name or name in {".", ".."}:
        raise ValueError(f"Unsafe upload filename: {filename!r}")
    return name


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract *zf* into *dest* while blocking zip-slip / path-traversal.

    Each member's resolved destination must be inside *dest*.  Members that
    escape the extraction directory are skipped with a warning rather than
    extracted.  Raises ``ValueError`` if the zip contains no safe members
    and is entirely empty after filtering.
    """
    dest_resolved = dest.resolve()
    skipped: list[str] = []

    for member in zf.infolist():
        # Normalise the member name to use forward slashes, strip leading /
        # and reject absolute paths (ZipInfo.filename should never start with
        # '/' in a well-formed zip, but be defensive).
        member_name = member.filename.replace("\\", "/").lstrip("/")
        candidate = (dest / member_name).resolve()

        try:
            candidate.relative_to(dest_resolved)
        except ValueError:
            skipped.append(member.filename)
            continue

        zf.extract(member, dest)

    if skipped:
        import logging
        logging.getLogger(__name__).warning(
            "zip-slip: skipped %d unsafe member(s): %s", len(skipped), skipped
        )


class ProjectCtx:
    def __init__(self, pool=None, project_id=None, user_id=None, storage=None,
                 http_client=None, file_revisions_max: int = 200, role: str = "owner"):
        self.pool = pool
        self.project_id = project_id
        self.user_id = user_id
        self.storage = storage
        self.http_client = http_client
        self.file_revisions_max = file_revisions_max
        self.role = role
