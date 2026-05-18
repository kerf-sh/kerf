"""kerf-mold plugin entry point."""
from __future__ import annotations


def register(app=None) -> None:  # pragma: no cover
    """Register the kerf-mold plugin with the Kerf application."""
    # Tools are self-registering via @register decorators in tools.py.
    # Import tools module to trigger decorator execution.
    try:
        import kerf_mold.tools  # noqa: F401
    except ImportError:
        pass
