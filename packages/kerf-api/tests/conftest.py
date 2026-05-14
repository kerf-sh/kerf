"""
Ensure both backend/ and the plugin's src/ are on sys.path so that:
- bare 'tools.*' imports in migrated tool modules resolve correctly
- plugin package imports (kerf_api.*) resolve from src/
"""
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)        # e.g. packages/kerf-api/
_parent = os.path.dirname(_PLUGIN_ROOT)
# Handle both flat layout (kerf-X/ directly in repo root) and
# monorepo layout (packages/kerf-X/ inside packages/).
_REPO_ROOT = os.path.dirname(_parent) if os.path.basename(_parent) == "packages" else _parent
_BACKEND = os.path.join(_REPO_ROOT, "backend")
_SRC = os.path.join(_PLUGIN_ROOT, "src")

for p in (_BACKEND, _SRC):
    if p not in sys.path:
        sys.path.insert(0, p)
