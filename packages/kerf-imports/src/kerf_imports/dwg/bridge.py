"""
bridge.py — libredwg DWG→DXF conversion bridge (T-8).

Feature-detects two back-ends (tried in order):
  1. Python binding  ``libredwg`` — ``libredwg.dwg2dxf(bytes) -> str``
  2. CLI subprocess  ``dwgread``  — writes a temp DXF, reads it back

If neither is present the bridge is disabled and all public entry-points
return a friendly result rather than raising.

Public API
----------
dwg_bridge_available() -> bool
    True when at least one back-end is functional.

convert_dwg_to_dxf(dwg_bytes: bytes) -> str
    Convert raw .dwg bytes to DXF ASCII text.
    Raises DwgBridgeUnavailable when no back-end is present.
    Raises DwgConversionError on conversion failure.

get_bridge_info() -> dict
    Returns {"available": bool, "backend": str | None, "version": str | None}.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DwgBridgeUnavailable(RuntimeError):
    """Raised when no libredwg back-end is installed."""


class DwgConversionError(RuntimeError):
    """Raised when the bridge is present but conversion fails."""


# ---------------------------------------------------------------------------
# Back-end detection (lazy, cached)
# ---------------------------------------------------------------------------

_SENTINEL = object()
_cached_backend: object = _SENTINEL   # None | "python" | "cli"
_cached_version: Optional[str] = None


def _detect_backend() -> tuple[Optional[str], Optional[str]]:
    """
    Return (backend_name, version_string).

    backend_name is one of: "python", "cli", or None (unavailable).
    """
    # 1. Python binding
    try:
        import libredwg as _ldwg  # type: ignore[import]
        version = getattr(_ldwg, "__version__", None) or "unknown"
        logger.debug("dwg bridge: python binding available (libredwg %s)", version)
        return "python", version
    except ImportError:
        pass

    # 2. CLI binary (dwgread ships with libredwg; produces .dxf side-by-side)
    dwgread_path = shutil.which("dwgread")
    if dwgread_path:
        try:
            result = subprocess.run(
                [dwgread_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            raw = (result.stdout or result.stderr or "").strip()
            # dwgread --version typically prints e.g. "dwgread 0.13"
            version = raw.split("\n")[0] if raw else "unknown"
            logger.debug("dwg bridge: CLI available at %s (%s)", dwgread_path, version)
            return "cli", version
        except Exception as exc:
            logger.debug("dwg bridge: dwgread found but --version failed: %s", exc)
            return "cli", None

    logger.debug("dwg bridge: no back-end found")
    return None, None


def _get_backend() -> tuple[Optional[str], Optional[str]]:
    """Cached detection (module-level singleton)."""
    global _cached_backend, _cached_version
    if _cached_backend is _SENTINEL:
        _cached_backend, _cached_version = _detect_backend()
    return _cached_backend, _cached_version  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def dwg_bridge_available() -> bool:
    """Return True when at least one libredwg back-end is detected."""
    backend, _ = _get_backend()
    return backend is not None


def get_bridge_info() -> dict:
    """
    Return a dict describing bridge availability::

        {
            "available": True | False,
            "backend": "python" | "cli" | None,
            "version": "0.13" | None
        }
    """
    backend, version = _get_backend()
    return {
        "available": backend is not None,
        "backend": backend,
        "version": version,
    }


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def convert_dwg_to_dxf(dwg_bytes: bytes) -> str:
    """
    Convert raw .dwg *bytes* to DXF ASCII text.

    Tries the Python binding first, falls back to the CLI subprocess.

    Parameters
    ----------
    dwg_bytes:
        Raw bytes of the .dwg file.

    Returns
    -------
    str
        DXF ASCII text (UTF-8 / latin-1 decoded).

    Raises
    ------
    DwgBridgeUnavailable
        When no back-end is installed.
    DwgConversionError
        When the back-end is present but conversion fails (e.g. corrupt
        file, unsupported DWG version, or subprocess error).
    """
    if not dwg_bytes:
        raise DwgConversionError("empty DWG input")

    backend, _ = _get_backend()

    if backend is None:
        raise DwgBridgeUnavailable(
            "DWG bridge not available — install libredwg "
            "(pip install libredwg  OR  brew install libredwg)"
        )

    if backend == "python":
        return _convert_python(dwg_bytes)
    else:
        return _convert_cli(dwg_bytes)


# ---------------------------------------------------------------------------
# Back-end implementations
# ---------------------------------------------------------------------------

def _convert_python(dwg_bytes: bytes) -> str:
    """Convert via the ``libredwg`` Python binding."""
    try:
        import libredwg as _ldwg  # type: ignore[import]
    except ImportError as exc:
        raise DwgBridgeUnavailable("libredwg Python binding not importable") from exc

    try:
        # The binding may expose dwg2dxf(bytes) -> str  or  dwg_to_dxf_string(bytes)
        # We try the most common signatures.
        if hasattr(_ldwg, "dwg2dxf"):
            result = _ldwg.dwg2dxf(dwg_bytes)
        elif hasattr(_ldwg, "dwg_to_dxf_string"):
            result = _ldwg.dwg_to_dxf_string(dwg_bytes)
        else:
            # Fallback: write to temp file, call via file API
            result = _convert_python_via_file(_ldwg, dwg_bytes)

        if isinstance(result, bytes):
            result = _safe_decode(result)
        if not result or not isinstance(result, str):
            raise DwgConversionError("libredwg returned empty or non-string result")
        return result
    except (DwgBridgeUnavailable, DwgConversionError):
        raise
    except Exception as exc:
        raise DwgConversionError(f"libredwg Python binding error: {exc}") from exc


def _convert_python_via_file(ldwg, dwg_bytes: bytes) -> str:
    """Write to a temp file and use file-based libredwg API."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dwg_path = os.path.join(tmpdir, "input.dwg")
        dxf_path = os.path.join(tmpdir, "input.dxf")
        with open(dwg_path, "wb") as fh:
            fh.write(dwg_bytes)

        if hasattr(ldwg, "dwg_to_dxf"):
            ldwg.dwg_to_dxf(dwg_path, dxf_path)
        elif hasattr(ldwg, "convert"):
            ldwg.convert(dwg_path, dxf_path)
        else:
            raise DwgConversionError(
                "libredwg Python binding has no recognised conversion entry point"
            )

        if not os.path.exists(dxf_path):
            raise DwgConversionError("libredwg produced no output DXF file")
        with open(dxf_path, "rb") as fh:
            return _safe_decode(fh.read())


def _convert_cli(dwg_bytes: bytes) -> str:
    """Convert via the ``dwgread`` CLI subprocess."""
    dwgread_path = shutil.which("dwgread")
    if not dwgread_path:
        raise DwgBridgeUnavailable(
            "dwgread not found on PATH — install libredwg"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        dwg_path = os.path.join(tmpdir, "input.dwg")
        # dwgread -O DXF writes input.dxf alongside the input file
        dxf_path = os.path.join(tmpdir, "input.dxf")

        with open(dwg_path, "wb") as fh:
            fh.write(dwg_bytes)

        try:
            result = subprocess.run(
                [dwgread_path, "-O", "DXF", dwg_path],
                capture_output=True,
                text=False,
                timeout=60,
                cwd=tmpdir,
            )
        except subprocess.TimeoutExpired as exc:
            raise DwgConversionError("dwgread timed out after 60 s") from exc
        except OSError as exc:
            raise DwgConversionError(f"dwgread subprocess failed to launch: {exc}") from exc

        if result.returncode != 0:
            stderr = _safe_decode(result.stderr or b"")[:400]
            raise DwgConversionError(
                f"dwgread exited with code {result.returncode}: {stderr}"
            )

        if not os.path.exists(dxf_path):
            # Some versions write to stdout instead
            stdout = _safe_decode(result.stdout or b"")
            if stdout.strip():
                return stdout
            raise DwgConversionError(
                "dwgread produced no DXF output (neither file nor stdout)"
            )

        with open(dxf_path, "rb") as fh:
            return _safe_decode(fh.read())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_decode(data: bytes) -> str:
    """Decode bytes, trying UTF-8 then latin-1."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


# ---------------------------------------------------------------------------
# Cache invalidation (useful in tests)
# ---------------------------------------------------------------------------

def _reset_cache() -> None:
    """Reset the module-level backend detection cache (test helper)."""
    global _cached_backend, _cached_version
    _cached_backend = _SENTINEL
    _cached_version = None
