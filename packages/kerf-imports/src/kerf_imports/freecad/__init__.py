"""
kerf_imports.freecad
====================
Pure-Python parser for FreeCAD .FCStd archives.

No FreeCAD or Coin3D install required — .FCStd is just a zip archive of XML
+ ASCII BRep blobs, parseable with stdlib only.

Public API::

    from kerf_imports.freecad.parser import parse_fcstd
    from kerf_imports.freecad.types import FCStdDocument, FCStdObject, LinkRef
    from kerf_imports.freecad.types import FCStdUnsupportedVersionError

The FastAPI router for the legacy /import-freecad stub is re-exported so
plugin.py's ``from kerf_imports.freecad import router`` still works.
"""
# Re-export the FastAPI router so plugin.py's existing import is unchanged.
from kerf_imports.freecad.route import router  # noqa: F401
