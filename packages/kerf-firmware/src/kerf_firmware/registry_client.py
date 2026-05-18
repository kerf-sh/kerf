"""Pure-Python HTTP client for the PlatformIO and Arduino library registries.

Uses only stdlib (urllib). No subprocess. Responses are cached to disk via
SHA-256 of the request URL.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# ── Cache helpers ─────────────────────────────────────────────────────────────

def _default_cache_dir() -> Path:
    return Path(tempfile.gettempdir()) / "kerf_firmware_cache"


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _cache_path(url: str, cache_dir: Path) -> Path:
    return cache_dir / (_cache_key(url) + ".json")


def _fetch_json(url: str, *, cache_dir: Path | None = None) -> Any:
    """Fetch *url*, returning parsed JSON.  Caches to *cache_dir* if provided."""
    if cache_dir is None:
        cache_dir = _default_cache_dir()

    path = _cache_path(url, cache_dir)

    if path.exists():
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    cache_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "kerf-firmware/0.1 (https://github.com/kerf-dev/kerf)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        raw = resp.read()

    data = json.loads(raw)

    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh)

    return data


# ── Public API ────────────────────────────────────────────────────────────────

PLATFORMIO_REGISTRY_BASE = "https://api.registry.platformio.org/v3/libraries"
ARDUINO_LIBRARY_INDEX_URL = (
    "https://downloads.arduino.cc/libraries/library_index.json"
)


def search_libraries(
    query: str,
    *,
    cache_dir: Path | None = None,
    _fetcher=None,
) -> list[dict]:
    """Search the PlatformIO registry for libraries matching *query*.

    Returns a list of library dicts as returned by the registry.
    The *_fetcher* parameter exists solely for testing (dependency injection).
    """
    url = f"{PLATFORMIO_REGISTRY_BASE}?names={urllib.parse.quote(query)}"
    fetcher = _fetcher or (lambda u: _fetch_json(u, cache_dir=cache_dir))
    data = fetcher(url)
    # Registry returns {"items": [...], ...} or a list
    if isinstance(data, dict):
        return data.get("items", data.get("libraries", []))
    return list(data)


def arduino_library_index(
    *,
    cache_dir: Path | None = None,
    _fetcher=None,
) -> list[dict]:
    """Fetch the Arduino library index.

    Returns the list of library dicts from ``library_index.json``.
    The *_fetcher* parameter exists solely for testing (dependency injection).
    """
    url = ARDUINO_LIBRARY_INDEX_URL
    fetcher = _fetcher or (lambda u: _fetch_json(u, cache_dir=cache_dir))
    data = fetcher(url)
    if isinstance(data, dict):
        return data.get("libraries", [])
    return list(data)
