"""Pytest bootstrap: add every kerf-* src/ directory to sys.path so imports
resolve without requiring pip install -e of each package.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)
_PACKAGES_ROOT = os.path.dirname(_PLUGIN_ROOT)

if os.path.basename(_PACKAGES_ROOT) == "packages":
    for entry in os.listdir(_PACKAGES_ROOT):
        if not entry.startswith("kerf-"):
            continue
        src = os.path.join(_PACKAGES_ROOT, entry, "src")
        if os.path.isdir(src) and src not in sys.path:
            sys.path.insert(0, src)
