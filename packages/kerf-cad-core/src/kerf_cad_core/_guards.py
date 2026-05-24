"""
kerf_cad_core._guards — shared input-validation helpers.

All functions return a human-readable error string on failure, or None on
success.  The pattern allows callers to collect multiple errors before
constructing an ``_err()`` response.

Public helpers
--------------
_guard_positive(name, value)  — value must be a finite number > 0
_guard_nonneg(name, value)    — value must be a finite number >= 0
_guard_finite(name, value)    — value must be a finite number (any sign)
_err(reason)                  — build {"ok": False, "reason": reason}
"""

from __future__ import annotations

import math
from typing import Any


def _guard_positive(name: str, value: Any) -> str | None:
    """Return error string if *value* is not a finite positive number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _guard_nonneg(name: str, value: Any) -> str | None:
    """Return error string if *value* is not a finite non-negative number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


def _guard_finite(name: str, value: Any) -> str | None:
    """Return error string if *value* is not a finite number."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    return None


def _err(reason: str) -> dict:
    """Return a standard error dict."""
    return {"ok": False, "reason": reason}
