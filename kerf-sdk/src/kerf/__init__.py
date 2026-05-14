"""
kerf — Python SDK for Kerf (https://kerf.app).

Quickstart:
    import kerf
    k = kerf.from_env()
    files = k.files.list(project_id="...")

Auth: set KERF_API_TOKEN (and optionally KERF_API_URL) in your environment,
or pass token/base_url explicitly to connect().
"""

from .auth import load_token, load_url
from .client import Kerf, KerfError

__all__ = ["connect", "from_env", "Kerf", "KerfError"]


def connect(token: str, base_url: str = "https://kerf.app") -> Kerf:
    """Create a Kerf client with an explicit token and server URL."""
    return Kerf(token=token, base_url=base_url)


def from_env() -> Kerf:
    """Create a Kerf client from KERF_API_TOKEN + KERF_API_URL env vars."""
    return Kerf(token=load_token(), base_url=load_url())
