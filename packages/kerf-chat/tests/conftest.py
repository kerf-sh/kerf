"""
Ensure both backend/ and kerf-chat/src/ are on sys.path so that:
- bare 'tools.*' imports in kerf_chat.tools modules resolve to backend/tools
- package imports (kerf_chat.*) resolve from src/

This mirrors the pattern used by kerf-bim/conftest.py.
"""
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)                            # packages/kerf-chat/
_PACKAGES = os.path.dirname(_PLUGIN_ROOT)                       # packages/
_REPO_ROOT = os.path.dirname(_PACKAGES)                         # worktree root
_BACKEND = os.path.join(_REPO_ROOT, "backend")
_SRC = os.path.join(_PLUGIN_ROOT, "src")

for p in (_BACKEND, _SRC):
    if p not in sys.path:
        sys.path.insert(0, p)
