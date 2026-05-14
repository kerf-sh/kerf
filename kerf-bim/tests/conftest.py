"""
Ensure both backend/ and the plugin's src/ are on sys.path so that:
- bare 'tools.*' imports in migrated tool modules resolve correctly
- plugin package imports (kerf_bim.*) resolve from src/

Pre-import the real 'tools' package so that sys.modules["tools.context"]
is locked to the real ProjectCtx before any individual test stubs it.
This mirrors what backend/tests/conftest.py does.
"""
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)        # e.g. kerf-bim/
_REPO_ROOT = os.path.dirname(_PLUGIN_ROOT)   # repo root (worktree root)
_BACKEND = os.path.join(_REPO_ROOT, "backend")
_SRC = os.path.join(_PLUGIN_ROOT, "src")

for p in (_BACKEND, _SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

# Lock in the real tools package before any test stubs override it
import tools  # noqa: F401
