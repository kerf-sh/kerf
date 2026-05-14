"""
brep_importer.py — T2 BRep-lift importer.

Converts a parsed :class:`~kerf_imports.freecad.types.FCStdDocument`
into an :class:`ImportResult` containing one :class:`FeaturePayload` per
top-level PartDesign::Body.

No FreeCAD install is required.  Geometry is loaded via pythonocc-core
(``OCC.Core.*`` / ``OCP.*``) using ``BRepTools::Read``.

Usage::

    from kerf_imports.freecad.parser import parse_fcstd
    from kerf_imports.freecad.brep_importer import build_feature_tree

    doc = parse_fcstd(path_or_bytes)
    result = build_feature_tree(doc)
    # result.features  — list[FeaturePayload], one per Body
    # result.assets    — dict[str, bytes], placeholder_id → raw BRep bytes
"""
from __future__ import annotations

import hashlib
import io
import tempfile
import os
from typing import NamedTuple, Any

from .types import FCStdDocument, FCStdObject

# ---------------------------------------------------------------------------
# pythonocc-core import — try OCC.Core first (canonical name used by the
# kerf monorepo), fall back to OCP (conda-forge build name).
# ---------------------------------------------------------------------------

def _import_occ():
    """Return (BRepTools, BRep_Builder, TopoDS_Shape) from whichever
    pythonocc binding is available.  Raises ImportError if neither is."""
    try:
        from OCC.Core.BRepTools import BRepTools as _BRepTools
        from OCC.Core.BRep import BRep_Builder as _BRep_Builder
        from OCC.Core.TopoDS import TopoDS_Shape as _TopoDS_Shape
        return _BRepTools, _BRep_Builder, _TopoDS_Shape
    except ImportError:
        pass
    try:
        from OCP.BRepTools import BRepTools as _BRepTools  # type: ignore[import]
        from OCP.BRep import BRep_Builder as _BRep_Builder  # type: ignore[import]
        from OCP.TopoDS import TopoDS_Shape as _TopoDS_Shape  # type: ignore[import]
        return _BRepTools, _BRep_Builder, _TopoDS_Shape
    except ImportError:
        pass
    raise ImportError(
        "pythonocc-core is required for BRep-lift.  "
        "Install via 'conda install -c conda-forge pythonocc-core' "
        "or 'pip install pythonocc-core'."
    )


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------

class BRepLiftError(Exception):
    """Raised when a BRep blob cannot be parsed into a valid TopoDS_Shape."""


# ---------------------------------------------------------------------------
# Public data-classes
# ---------------------------------------------------------------------------

class FeatureNode(NamedTuple):
    """A single node inside a .feature file."""
    kind: str           # e.g. "import_brep"
    params: dict        # node-kind–specific params


class FeaturePayload(NamedTuple):
    """One .feature file (one per top-level Body)."""
    body_name: str      # FCStd internal object name
    body_label: str     # user-visible label
    nodes: list         # list[FeatureNode]


class ImportResult(NamedTuple):
    """Return value of :func:`build_feature_tree`."""
    features: list      # list[FeaturePayload]
    assets: dict        # dict[str, bytes]  placeholder_id → BRep bytes


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def lift_brep_blob(blob: bytes) -> Any:
    """
    Parse raw BRep *blob* bytes and return a ``TopoDS_Shape``.

    Uses ``BRepTools::Read`` via pythonocc-core.  The blob is written to a
    temporary file and cleaned up in a ``try/finally`` block, which is the
    most portable path across OCC / OCP builds (some older builds do not
    support the ``io.BytesIO`` overload of ``Read_s``).

    Parameters
    ----------
    blob :
        Raw ASCII BRep bytes as produced by ``BRepTools::Write`` /
        ``breptools_Write`` / the FreeCAD ``PartShape*.brp`` member.

    Returns
    -------
    TopoDS_Shape

    Raises
    ------
    BRepLiftError
        If the blob cannot be parsed or produces a null shape.
    ImportError
        If pythonocc-core is not installed.
    """
    BRepTools, BRep_Builder, TopoDS_Shape = _import_occ()

    # Prefer the in-memory BytesIO path; it avoids a disk round-trip and is
    # supported by both current OCC (7.7+) and OCP (2024+) builds.
    shape = TopoDS_Shape()
    builder = BRep_Builder()

    # --- try BytesIO first (no tempfile needed) ---
    try:
        buf = io.BytesIO(blob)
        BRepTools.Read_s(shape, buf, builder)
        if not shape.IsNull():
            return shape
    except Exception:
        # Some OCC builds raise instead of producing a null shape on corrupt
        # input via the stream overload; fall through to the file path.
        pass

    # --- fallback: write to tempfile, read back ---
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".brp")
    try:
        os.write(tmp_fd, blob)
        os.close(tmp_fd)
        tmp_fd = -1  # mark as closed so finally block doesn't double-close
        shape2 = TopoDS_Shape()
        ok = BRepTools.Read_s(shape2, tmp_path, builder)
        # Read_s returns bool on the file overload; some builds return None
        if ok is False or shape2.IsNull():
            raise BRepLiftError(
                "BRep blob could not be parsed into a valid TopoDS_Shape "
                f"({len(blob)} bytes).  The blob may be corrupt or from an "
                "incompatible OpenCascade version."
            )
        return shape2
    except BRepLiftError:
        raise
    except Exception as exc:
        raise BRepLiftError(
            f"BRep read failed: {exc} ({len(blob)} bytes)"
        ) from exc
    finally:
        if tmp_fd != -1:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# _brep_blob_for_body — locate the BRep blob that belongs to a Body
# ---------------------------------------------------------------------------

_BODY_TYPE = "PartDesign::Body"


def _body_brep_blob(
    body: FCStdObject, doc: FCStdDocument
) -> tuple[str | None, bytes | None]:
    """
    Find the BRep blob associated with *body*.

    Strategy (in order):
    1. Check the ``Shape`` property of every feature that directly references
       this Body via ``BaseFeature`` or ``Model`` props — the last feature's
       ``Shape`` FileIncluded blob is the evaluated solid.
    2. Fall back to any ``.brp`` member whose name starts with the body name
       (e.g. ``"Body.brp"``).
    3. If only one blob exists in the whole document, use it (common for
       single-body files).

    Returns ``(blob_name, blob_bytes)`` or ``(None, None)``.
    """
    # --- Strategy 1: look through all objects for the tip shape belonging to
    # this body.  FreeCAD stores the final solid in the Tip feature's Shape
    # property as a FileIncluded blob; parser.py already inlined it as bytes.
    tip_name: str | None = body.properties.get("Tip")
    if isinstance(tip_name, str) and tip_name:
        tip_obj = doc.object_by_name(tip_name)
        if tip_obj is not None:
            shape_bytes = tip_obj.properties.get("Shape")
            if isinstance(shape_bytes, bytes) and shape_bytes:
                return (f"{tip_name}.brp", shape_bytes)

    # --- Strategy 2: scan the brep_blobs dict for a name matching this body
    lower_body = body.name.lower()
    for bname, bblob in doc.brep_blobs.items():
        stem = bname.split(".")[0].lower()
        if stem == lower_body or stem.startswith(lower_body):
            return (bname, bblob)

    # --- Strategy 3: single-blob document short-circuit
    if len(doc.brep_blobs) == 1:
        bname, bblob = next(iter(doc.brep_blobs.items()))
        return (bname, bblob)

    return (None, None)


# ---------------------------------------------------------------------------
# build_feature_tree
# ---------------------------------------------------------------------------

def build_feature_tree(doc: FCStdDocument) -> ImportResult:
    """
    Convert a parsed :class:`FCStdDocument` into an :class:`ImportResult`.

    One :class:`FeaturePayload` is emitted per top-level
    ``PartDesign::Body`` object found in *doc*.  Each payload contains a
    single ``import_brep`` node whose ``asset_id`` is a placeholder
    ``"brep:<sha256>"`` string.  The route layer (T7) replaces this with
    the real blob-storage key after uploading the asset.

    Parameters
    ----------
    doc :
        A parsed ``FCStdDocument`` as returned by
        :func:`~kerf_imports.freecad.parser.parse_fcstd`.

    Returns
    -------
    ImportResult
        ``.features`` — one entry per Body.
        ``.assets``   — mapping from placeholder asset_id to raw BRep bytes.

    Raises
    ------
    BRepLiftError
        If a body's BRep blob is found but cannot be parsed.
    """
    bodies = doc.objects_by_type(_BODY_TYPE)

    # If no explicit Body objects, treat the whole document as one implicit
    # body (Part workbench files often have no PartDesign::Body wrapper).
    if not bodies:
        # Build a synthetic body-like object from the first available blob.
        if doc.brep_blobs:
            first_name, first_blob = next(iter(doc.brep_blobs.items()))
            stem = first_name.rsplit(".", 1)[0]
            synthetic = FCStdObject(
                name=stem, type=_BODY_TYPE, label=stem, properties={}
            )
            # Inline the blob so _body_brep_blob can find it
            doc = FCStdDocument(
                schema_version=doc.schema_version,
                program_version=doc.program_version,
                objects=list(doc.objects) + [synthetic],
                properties=doc.properties,
                brep_blobs=doc.brep_blobs,
                raw_xml=doc.raw_xml,
            )
            bodies = [synthetic]

    features: list[FeaturePayload] = []
    assets: dict[str, bytes] = {}

    for body in bodies:
        blob_name, blob_bytes = _body_brep_blob(body, doc)

        if blob_bytes is None:
            # No blob found for this body — emit an empty placeholder node.
            node = FeatureNode(
                kind="import_brep",
                params={
                    "asset_id": None,
                    "source_body": body.name,
                    "warning": "no_brep_blob_found",
                },
            )
            features.append(
                FeaturePayload(
                    body_name=body.name,
                    body_label=body.label,
                    nodes=[node],
                )
            )
            continue

        # Validate the BRep — this raises BRepLiftError on corrupt blobs.
        lift_brep_blob(blob_bytes)

        # Content-address the blob.
        sha256 = hashlib.sha256(blob_bytes).hexdigest()
        asset_id = f"brep:{sha256}"
        assets[asset_id] = blob_bytes

        node = FeatureNode(
            kind="import_brep",
            params={
                "asset_id": asset_id,       # T7 replaces with real storage key
                "source_body": body.name,
                "source_label": body.label,
                "source_blob": blob_name,   # original zip member name (informational)
            },
        )
        features.append(
            FeaturePayload(
                body_name=body.name,
                body_label=body.label,
                nodes=[node],
            )
        )

    return ImportResult(features=features, assets=assets)
