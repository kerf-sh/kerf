"""
3D-print slicing route.

POST /run-print-slice
Body:  { "stl_path": "<abs-path>", "settings": { ... } }
Returns:
  {
    "gcode": "<full G-code string>",
    "layer_count": <int>,
    "print_time_s": <int | null>,
    "filament_mm": <float | null>,
    "gcode_bytes": <int>,
    "warnings": ["..."]
  }
  or on error:
  { "gcode": null, "warnings": ["<message>"], "error": "<message>" }

The route never crashes even when CuraEngine is not installed — it returns a
descriptive error payload instead so the frontend can surface a helpful message.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from kerf_core.dependencies import require_auth

router = APIRouter()

# Concurrency cap: at most 4 simultaneous slicing jobs.  CuraEngine is a
# subprocess that can run for up to 60 s on large meshes; running too many
# in parallel saturates the worker's CPU.
_SLICE_SEM = asyncio.Semaphore(4)

_BAD_PATH_RESPONSE = {
    "gcode": None,
    "layer_count": 0,
    "print_time_s": None,
    "filament_mm": None,
    "gcode_bytes": 0,
    "warnings": ["'stl_path' must not be absolute or contain '..' traversal sequences"],
    "error": "BAD_PATH",
}


def _get_storage_root() -> Path:
    """Return the configured local storage root, resolved to an absolute path."""
    try:
        from kerf_core.config import get_settings
        settings = get_settings()
        root = getattr(settings, "local_storage_path", "./.kerf-storage")
    except Exception:
        root = "./.kerf-storage"
    return Path(root).expanduser().resolve()


def _assert_within_storage(path_str: str) -> Path:
    """
    Resolve path_str and assert it lives inside the configured storage root.

    Raises HTTPException(400) when the path would escape the storage root.
    Also rejects absolute paths that point outside storage, or any path
    containing '..' that resolves outside the root.
    """
    storage_root = _get_storage_root()
    resolved = Path(path_str).resolve()
    try:
        resolved.relative_to(storage_root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"stl_path must be within the storage root ({storage_root})",
        )
    return resolved


@router.post("/run-print-slice")
async def run_print_slice_route(req: dict, _auth: dict = Depends(require_auth)) -> dict:
    """Slice an STL file to G-code via CuraEngine subprocess."""
    stl_path = req.get("stl_path", "")
    settings = req.get("settings") or {}

    if not stl_path or not isinstance(stl_path, str):
        return {
            "gcode": None,
            "layer_count": 0,
            "print_time_s": None,
            "filament_mm": None,
            "gcode_bytes": 0,
            "warnings": ["'stl_path' must be a non-empty string"],
            "error": "BAD_ARGS",
        }

    # Path confinement: reject traversal and paths outside storage root.
    _assert_within_storage(stl_path)

    from kerf_slicing.cura_runner import (
        CuraEngineError,
        CuraEngineNotInstalledError,
        run_cura_slice,
    )

    if _SLICE_SEM.locked():
        raise HTTPException(status_code=429, detail="Too many concurrent slicing jobs — try again shortly")

    try:
        # run_cura_slice shells out to CuraEngine (subprocess, up to 60 s).
        # Offload to a thread-pool executor so the event loop stays free.
        async with _SLICE_SEM:
            result = await asyncio.to_thread(run_cura_slice, stl_path, settings)
    except CuraEngineNotInstalledError as exc:
        return {
            "gcode": None,
            "layer_count": 0,
            "print_time_s": None,
            "filament_mm": None,
            "gcode_bytes": 0,
            "warnings": [str(exc)],
            "error": "CURA_NOT_INSTALLED",
        }
    except FileNotFoundError:
        return {
            "gcode": None,
            "layer_count": 0,
            "print_time_s": None,
            "filament_mm": None,
            "gcode_bytes": 0,
            "warnings": [f"STL file not found: {stl_path}"],
            "error": "STL_NOT_FOUND",
        }
    except CuraEngineError as exc:
        return {
            "gcode": None,
            "layer_count": 0,
            "print_time_s": None,
            "filament_mm": None,
            "gcode_bytes": 0,
            "warnings": [str(exc)],
            "error": "CURA_ERROR",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "gcode": None,
            "layer_count": 0,
            "print_time_s": None,
            "filament_mm": None,
            "gcode_bytes": 0,
            "warnings": [f"Unexpected error: {exc}"],
            "error": "ERROR",
        }

    return {
        "gcode": result.gcode,
        "layer_count": result.layer_count,
        "print_time_s": result.print_time_s,
        "filament_mm": result.filament_mm,
        "gcode_bytes": result.gcode_bytes,
        "warnings": result.warnings,
        "error": None,
    }
