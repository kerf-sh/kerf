"""Pytest config for kerf-bim tests.

Ensures plugin src/ is on sys.path so test files can import kerf_bim.*
directly without requiring `pip install -e`.
"""
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_PLUGIN_ROOT, "src")

if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
