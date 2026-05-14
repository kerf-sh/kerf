"""
kerf_imports.freecad
====================
Pure-Python parser for FreeCAD .FCStd archives + BRep-lift importer.

No FreeCAD or Coin3D install required — .FCStd is just a zip archive of XML
+ ASCII BRep blobs, parseable with stdlib only.

Public API::

    from kerf_imports.freecad.parser import parse_fcstd
    from kerf_imports.freecad.types import FCStdDocument, FCStdObject, LinkRef
    from kerf_imports.freecad.types import FCStdUnsupportedVersionError

    # T2 BRep-lift (requires pythonocc-core / OCC.Core.*)
    from kerf_imports.freecad import (
        lift_brep_blob,
        build_feature_tree,
        ImportResult,
        BRepLiftError,
    )

The FastAPI router for the legacy /import-freecad stub is re-exported so
plugin.py's ``from kerf_imports.freecad import router`` still works.
"""
# Re-export the FastAPI router so plugin.py's existing import is unchanged.
from kerf_imports.freecad.route import router  # noqa: F401

# T2 BRep-lift exports — imported lazily-friendly but available at package level.
from kerf_imports.freecad.brep_importer import (  # noqa: F401
    lift_brep_blob,
    build_feature_tree,
    ImportResult,
    BRepLiftError,
    FeaturePayload,
    FeatureNode,
)
