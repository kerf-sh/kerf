"""
Drive-face normal extraction via pythonOCC GeomLProp_SLProps.

T2 deliverable — exposes:
  extract_drive_face(brep_path, face_id)   -> TopoDS_Face
  surface_normal_at(face, u, v)            -> tuple[Point3, Vec3]   (or None)
  uv_iso_curves(face, step_over_mm)        -> list[list[tuple[u, v]]]

GeomLProp_SLProps constructor variant
--------------------------------------
pythonOCC wraps the OCCT C++ class which has two constructors:
  (a) GeomLProp_SLProps(surf, u, v, order, resolution)   -- parameterised form
  (b) GeomLProp_SLProps(surf, order, resolution)          -- deferred-parameter form
      then call .SetParameters(u, v) before querying

We try (a) first (used everywhere in routes.py); fall back to (b).
The T1 audit confirmed the installed wheel is opencamlib 2023.1.11;
pythonocc-core ships the same OCCT 7.x ABI, so (a) is available.

Point3 / Vec3 are plain (x, y, z) float tuples for zero-dependency usage
from constant_tilt.py and indexed_3_2.py.
"""

from __future__ import annotations

import math
from typing import Optional

# pythonOCC is optional — callers that don't have it get ImportError at call-site,
# not at module-import time.  That lets the module be imported for pure-Python
# tests (e.g. rotation-matrix tests in test_3_2_indexed.py).
_occ_available = False
try:
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepTools import BRepTools
    from OCC.Core.GeomLProp import GeomLProp_SLProps
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.IFSelect import IFSelect_RetDone
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopoDS import TopoDS_Face
    _occ_available = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Public type aliases (plain tuples; no numpy dependency required)
# ---------------------------------------------------------------------------
Point3 = tuple  # (x, y, z) floats in mm
Vec3 = tuple    # (x, y, z) unit vector


# ---------------------------------------------------------------------------
# GeomLProp_SLProps constructor probe
# ---------------------------------------------------------------------------
# The OCCT C++ API has two valid forms:
#   Form A: GeomLProp_SLProps(surf, u, v, order, resolution)
#   Form B: GeomLProp_SLProps(surf, order, resolution) then .SetParameters(u, v)
#
# Form A is used throughout routes.py (line 246) and is the primary form used in
# practice.  We probe both at first call and cache the working variant.

_SLPROPS_FORM: Optional[str] = None  # "A" | "B" — set on first successful call


def _make_slprops(surf, u: float, v: float):
    """Return a ready-to-query GeomLProp_SLProps instance."""
    global _SLPROPS_FORM

    if not _occ_available:
        raise ImportError("pythonOCC (OCC.Core.GeomLProp) is required for surface-normal queries")

    if _SLPROPS_FORM == "A":
        return GeomLProp_SLProps(surf, u, v, 1, 1e-6)
    if _SLPROPS_FORM == "B":
        props = GeomLProp_SLProps(surf, 1, 1e-6)
        props.SetParameters(u, v)
        return props

    # First call — probe both forms.
    try:
        props = GeomLProp_SLProps(surf, u, v, 1, 1e-6)
        _SLPROPS_FORM = "A"
        return props
    except (TypeError, Exception):
        pass

    try:
        props = GeomLProp_SLProps(surf, 1, 1e-6)
        props.SetParameters(u, v)
        _SLPROPS_FORM = "B"
        return props
    except (TypeError, Exception) as exc:
        raise RuntimeError(
            "GeomLProp_SLProps: neither Form-A(surf,u,v,order,res) "
            "nor Form-B(surf,order,res)+SetParameters worked. "
            f"pythonocc-core version mismatch? Underlying error: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# extract_drive_face
# ---------------------------------------------------------------------------

def extract_drive_face(brep_path: str, face_id: int) -> "TopoDS_Face":
    """Load a STEP/BRep file and return the face at index *face_id*.

    Face ordering follows a forward TopExp_Explorer walk over TopAbs_FACE,
    which is deterministic for a given STEP file.  Index 0 = first face
    encountered.

    Raises:
        ImportError  — pythonOCC not installed.
        RuntimeError — STEP load failed or face_id out of range.
    """
    if not _occ_available:
        raise ImportError("pythonOCC is required — install pythonocc-core")

    path_lower = brep_path.lower()
    if path_lower.endswith(".step") or path_lower.endswith(".stp"):
        reader = STEPControl_Reader()
        status = reader.ReadFile(brep_path)
        if status != IFSelect_RetDone:
            raise RuntimeError(f"STEPControl_Reader failed on '{brep_path}' (status={status})")
        reader.TransferRoots()
        shape = reader.OneShape()
    else:
        # Assume BRep text format.
        from OCC.Core.BRep import BRep_Builder
        from OCC.Core.BRepTools import breptools
        from OCC.Core.TopoDS import TopoDS_Shape
        builder = BRep_Builder()
        shape = TopoDS_Shape()
        ok = breptools.Read(shape, brep_path, builder)
        if not ok:
            raise RuntimeError(f"BRepTools.Read failed on '{brep_path}'")

    faces = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        faces.append(exp.Current())
        exp.Next()

    if not faces:
        raise RuntimeError(f"No faces found in '{brep_path}'")
    if face_id < 0 or face_id >= len(faces):
        raise RuntimeError(
            f"face_id={face_id} out of range — shape has {len(faces)} face(s)"
        )

    return faces[face_id]


# ---------------------------------------------------------------------------
# surface_normal_at
# ---------------------------------------------------------------------------

def surface_normal_at(
    face: "TopoDS_Face",
    u: float,
    v: float,
) -> Optional[tuple[Point3, Vec3]]:
    """Return (point, unit_normal) at UV parameter (u, v) on *face*.

    Returns None if the normal is undefined at that UV (e.g. pole of a sphere,
    degenerate seam).  Callers should skip CC points where None is returned and
    add a ``warnings[]`` entry.

    Coordinates are in the native OCC geometry units (mm for standard STEP).
    """
    if not _occ_available:
        raise ImportError("pythonOCC is required — install pythonocc-core")

    surf = BRep_Tool.Surface(face)
    props = _make_slprops(surf, u, v)

    point = surf.Value(u, v)
    p3: Point3 = (point.X(), point.Y(), point.Z())

    if not props.IsNormalDefined():
        return None

    n = props.Normal()
    nx, ny, nz = n.X(), n.Y(), n.Z()
    mag = math.sqrt(nx * nx + ny * ny + nz * nz)
    if mag < 1e-12:
        return None

    return p3, (nx / mag, ny / mag, nz / mag)


# ---------------------------------------------------------------------------
# uv_iso_curves
# ---------------------------------------------------------------------------

def uv_iso_curves(
    face: "TopoDS_Face",
    step_over_mm: float,
) -> list[list[tuple[float, float]]]:
    """Sample UV iso-curves at *step_over_mm* spacing across the face domain.

    The face's UV parameter domain is divided into rows along the V direction
    at approximately *step_over_mm* arc-length spacing (approximated via a
    linear chord from one corner to another — fine for moderately-curved faces).

    Each row is sampled along U at 4x denser resolution (step_over_mm / 4) so
    that each iso-line has enough CC points for finishing.

    Returns a list of rows; each row is a list of (u, v) tuples.  The list
    will have at least 2 rows even if the surface is narrower than step_over_mm.
    """
    if not _occ_available:
        raise ImportError("pythonOCC is required — install pythonocc-core")

    surf = BRep_Tool.Surface(face)
    u_min, u_max, v_min, v_max = BRepTools.UVBounds(face)

    # Estimate arc length along V direction by sampling the mid-U column.
    u_mid = (u_min + u_max) / 2.0
    p_v_min = surf.Value(u_mid, v_min)
    p_v_max = surf.Value(u_mid, v_max)
    v_arc_len = math.sqrt(
        (p_v_max.X() - p_v_min.X()) ** 2 +
        (p_v_max.Y() - p_v_min.Y()) ** 2 +
        (p_v_max.Z() - p_v_min.Z()) ** 2
    )

    # Number of V steps — at least 1 interval (2 rows).
    n_v = max(1, round(v_arc_len / step_over_mm))
    n_v_steps = n_v  # number of intervals → n_v+1 rows

    # Estimate arc length along U direction at mid-V.
    v_mid = (v_min + v_max) / 2.0
    p_u_min = surf.Value(u_min, v_mid)
    p_u_max = surf.Value(u_max, v_mid)
    u_arc_len = math.sqrt(
        (p_u_max.X() - p_u_min.X()) ** 2 +
        (p_u_max.Y() - p_u_min.Y()) ** 2 +
        (p_u_max.Z() - p_u_min.Z()) ** 2
    )
    # Sample U at step_over/4 for a dense-enough iso-curve.
    sample_step = step_over_mm / 4.0
    n_u = max(2, round(u_arc_len / sample_step))

    rows: list[list[tuple[float, float]]] = []
    for i in range(n_v_steps + 1):
        v = v_min + i * (v_max - v_min) / n_v_steps
        row = []
        for j in range(n_u + 1):
            u = u_min + j * (u_max - u_min) / n_u
            row.append((u, v))
        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Tangent helpers (used by constant_tilt.py)
# ---------------------------------------------------------------------------

def surface_d1u_at(face: "TopoDS_Face", u: float, v: float) -> Optional[Vec3]:
    """Return the unit tangent in the U-parameter direction at (u, v).

    Returns None if the derivative is zero (degenerate point).
    """
    if not _occ_available:
        raise ImportError("pythonOCC is required — install pythonocc-core")

    surf = BRep_Tool.Surface(face)
    props = _make_slprops(surf, u, v)

    d1u = props.D1U()
    dx, dy, dz = d1u.X(), d1u.Y(), d1u.Z()
    mag = math.sqrt(dx * dx + dy * dy + dz * dz)
    if mag < 1e-12:
        return None
    return (dx / mag, dy / mag, dz / mag)
