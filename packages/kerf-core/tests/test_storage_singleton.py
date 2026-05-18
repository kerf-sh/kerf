"""Regression: the storage singleton MUST be initialised at app startup.

Live dev 500 root cause: handlers call kerf_core.storage.get_storage_required()
(the module singleton), but _wire_storage() only set app.state.storage and
set_storage() was never called *anywhere*. So every storage-touching
endpoint — chat-with-parts, project thumbnails for ALL kinds, uploads,
derived artifacts — raised RuntimeError("Storage not initialized") → 500.

These pin: (1) get_storage_required raises only until set_storage, (2)
the app's storage-wiring path (_wire_storage + set_storage) makes it
usable, (3) app.py's _load_plugins still wires the singleton (source
guard so the call can't be silently dropped again).
"""
from __future__ import annotations

import pathlib

import pytest

import kerf_core.storage as storage_mod
from kerf_core.app import _wire_storage
from kerf_core.config import Config


def test_get_storage_required_raises_until_set():
    storage_mod.set_storage(None)
    with pytest.raises(RuntimeError, match="Storage not initialized"):
        storage_mod.get_storage_required()


def test_app_storage_wiring_initialises_the_singleton(tmp_path):
    storage_mod.set_storage(None)  # simulate fresh process
    cfg = Config(storage_backend="local", local_storage_path=str(tmp_path))

    # Exactly what _load_plugins does:
    storage = _wire_storage(cfg)
    storage_mod.set_storage(storage)

    got = storage_mod.get_storage_required()  # must NOT raise
    assert got is storage
    assert got is not None


def test_load_plugins_source_still_wires_singleton():
    """Guard: _load_plugins must call set_storage right after _wire_storage."""
    src = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src/kerf_core/app.py"
    ).read_text()
    assert "_set_storage(storage)" in src, (
        "app.py no longer calls set_storage — storage singleton will be "
        "uninitialised and every storage endpoint will 500"
    )
    w = src.index("storage = _wire_storage(config)")
    s = src.index("_set_storage(storage)")
    assert s > w, "_set_storage must run after _wire_storage"
