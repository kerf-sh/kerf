"""GK-P50 wiring test: write_3dm export route in routes.py."""
from __future__ import annotations

import pathlib
import re

_WORKTREE = pathlib.Path(__file__).parents[3]
_ROUTES = _WORKTREE / "packages" / "kerf-api" / "src" / "kerf_api" / "routes.py"


def _routes_text() -> str:
    return _ROUTES.read_text(encoding="utf-8")


def test_export_3dm_route_registered():
    """GET /projects/{pid}/export-3dm must be defined in routes.py."""
    text = _routes_text()
    assert "/export-3dm" in text, "export-3dm route missing from routes.py"


def test_export_3dm_route_uses_write_3dm_or_export_to_3dm():
    """Route must reference write_3dm or export_to_3dm."""
    text = _routes_text()
    assert "write_3dm" in text or "export_to_3dm" in text, (
        "routes.py export-3dm route must reference write_3dm or export_to_3dm"
    )


def test_export_3dm_route_returns_model_vnd_3dm():
    """Route must set model/vnd.3dm media type."""
    text = _routes_text()
    assert "model/vnd.3dm" in text, "export-3dm route missing model/vnd.3dm media type"


def test_export_3dm_route_has_auth():
    """Route must check require_auth."""
    text = _routes_text()
    # Find the @router.get definition (not a comment) for export-3dm
    idx = text.find('@router.get("/projects/{pid}/export-3dm")')
    assert idx >= 0, "export-3dm @router.get not found"
    # Check within 800 chars after the route decorator
    vicinity = text[idx:idx + 800]
    assert "require_auth" in vicinity or "Depends" in vicinity, (
        "export-3dm route should require authentication"
    )


def test_export_3dm_route_has_503_fallback():
    """Route must handle the case when rhino3dm is unavailable (HTTP 503)."""
    text = _routes_text()
    assert "503" in text or "SERVICE_UNAVAILABLE" in text, (
        "export-3dm route should return 503 when rhino3dm is unavailable"
    )
