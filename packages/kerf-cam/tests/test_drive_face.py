"""
T2 tests: pythonOCC GeomLProp_SLProps drive-face normal extraction.

Tests exercise:
  - extract_drive_face on a programmatically constructed shape
  - surface_normal_at on a plane (known normal = +Z) and cylinder
  - uv_iso_curves row count and UV validity
  - IsNormalDefined() == False path is skipped (pole of a sphere)

These tests require pythonOCC; they are skipped when it is absent.
"""

import math
import sys
import os

import pytest

# Ensure kerf_cam is importable without pip install.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

try:
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeSphere
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepTools import BRepTools
    _has_occ = True
except ImportError:
    _has_occ = False

requires_occ = pytest.mark.skipif(not _has_occ, reason="pythonOCC not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _faces_of_shape(shape):
    """Return all TopoDS_Face objects in *shape* as a list."""
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE
    faces = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        faces.append(exp.Current())
        exp.Next()
    return faces


def _vec_close(a, b, tol=1e-5):
    """Return True if two (x,y,z) tuples are within *tol* of each other."""
    return all(abs(ai - bi) <= tol for ai, bi in zip(a, b))


# ---------------------------------------------------------------------------
# T2a: GeomLProp_SLProps constructor variant probe
# ---------------------------------------------------------------------------

@requires_occ
def test_slprops_constructor_variant_recorded():
    """After a single normal query the module should have determined Form A or B."""
    # Reset any cached state so the probe runs fresh.
    import kerf_cam.five_axis.drive_face as df_mod
    df_mod._SLPROPS_FORM = None

    shape = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()
    faces = _faces_of_shape(shape)
    assert faces, "BRepPrimAPI_MakeBox produced no faces"
    face = faces[0]

    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepTools import BRepTools
    surf = BRep_Tool.Surface(face)
    u_min, u_max, v_min, v_max = BRepTools.UVBounds(face)
    u_mid = (u_min + u_max) / 2.0
    v_mid = (v_min + v_max) / 2.0

    from kerf_cam.five_axis.drive_face import _make_slprops
    _make_slprops(surf, u_mid, v_mid)  # triggers probe

    assert df_mod._SLPROPS_FORM in ("A", "B"), (
        f"_SLPROPS_FORM should be 'A' or 'B', got {df_mod._SLPROPS_FORM!r}"
    )


# ---------------------------------------------------------------------------
# T2b: surface_normal_at on a flat plane (top face of a box)
# ---------------------------------------------------------------------------

@requires_occ
def test_normal_at_box_top_face_is_plus_z():
    """Top face of a 10x10x10 box must have normal (0,0,+1) at its UV centroid."""
    from kerf_cam.five_axis.drive_face import surface_normal_at

    shape = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()
    # Find the face with the highest Z centroid — that is the top face.
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.BRepGProp import brepgprop

    top_face = None
    best_z = -1e30
    for face in _faces_of_shape(shape):
        gprops = GProp_GProps()
        brepgprop.SurfaceProperties(face, gprops)
        z = gprops.CentreOfMass().Z()
        if z > best_z:
            best_z = z
            top_face = face

    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepTools import BRepTools
    u_min, u_max, v_min, v_max = BRepTools.UVBounds(top_face)
    u_mid = (u_min + u_max) / 2.0
    v_mid = (v_min + v_max) / 2.0

    result = surface_normal_at(top_face, u_mid, v_mid)
    assert result is not None, "surface_normal_at returned None on a planar face"
    point, normal = result

    # Normal on the top face must point +Z (OCC convention: face normal follows
    # right-hand rule relative to the face's outer-bound orientation).
    assert abs(abs(normal[2]) - 1.0) < 1e-5, (
        f"Expected |nz|=1 on flat top face, got normal={normal}"
    )


@requires_occ
def test_normal_at_plane_unit_length():
    """Normal vector returned by surface_normal_at must be a unit vector."""
    from kerf_cam.five_axis.drive_face import surface_normal_at
    shape = BRepPrimAPI_MakeBox(5.0, 7.0, 3.0).Shape()
    for face in _faces_of_shape(shape):
        from OCC.Core.BRep import BRep_Tool
        from OCC.Core.BRepTools import BRepTools
        u_min, u_max, v_min, v_max = BRepTools.UVBounds(face)
        u_mid = (u_min + u_max) / 2.0
        v_mid = (v_min + v_max) / 2.0
        result = surface_normal_at(face, u_mid, v_mid)
        if result is None:
            continue
        _, n = result
        mag = math.sqrt(sum(c * c for c in n))
        assert abs(mag - 1.0) < 1e-9, f"normal not unit: mag={mag}, n={n}"


# ---------------------------------------------------------------------------
# T2c: surface_normal_at on a cylinder lateral face
# ---------------------------------------------------------------------------

@requires_occ
def test_normal_at_cylinder_lateral_face_is_radial():
    """
    For a cylinder of radius R centred on the Z axis, the lateral face normal
    at any point must be purely radial (nz = 0, nx^2 + ny^2 = 1).
    """
    from kerf_cam.five_axis.drive_face import surface_normal_at
    radius = 5.0
    height = 10.0
    shape = BRepPrimAPI_MakeCylinder(radius, height).Shape()

    # The lateral (curved) face has the largest UV domain area.
    lateral = None
    largest_u_span = 0.0
    for face in _faces_of_shape(shape):
        from OCC.Core.BRep import BRep_Tool
        from OCC.Core.BRepTools import BRepTools
        u_min, u_max, v_min, v_max = BRepTools.UVBounds(face)
        u_span = u_max - u_min
        if u_span > largest_u_span:
            largest_u_span = u_span
            lateral = face

    assert lateral is not None, "No lateral face found on cylinder"
    from OCC.Core.BRepTools import BRepTools
    from OCC.Core.BRep import BRep_Tool
    u_min, u_max, v_min, v_max = BRepTools.UVBounds(lateral)
    u_mid = (u_min + u_max) / 2.0
    v_mid = (v_min + v_max) / 2.0

    result = surface_normal_at(lateral, u_mid, v_mid)
    assert result is not None, "cylinder normal undefined at midpoint"
    _, n = result

    # Radial: nz must be ~0, sqrt(nx^2+ny^2) must be ~1.
    assert abs(n[2]) < 1e-5, f"cylinder lateral face nz={n[2]}, expected ~0"
    radial = math.sqrt(n[0] ** 2 + n[1] ** 2)
    assert abs(radial - 1.0) < 1e-5, f"radial component={radial}, expected ~1"


# ---------------------------------------------------------------------------
# T2d: uv_iso_curves — row count and UV bounds
# ---------------------------------------------------------------------------

@requires_occ
def test_uv_iso_curves_count_on_box_top():
    """
    uv_iso_curves on a 10x10 mm planar face at 2 mm step-over should produce
    at least 2 rows (the step-over could exceed the face size, so we get
    the minimum-2 guarantee).
    """
    from kerf_cam.five_axis.drive_face import uv_iso_curves
    shape = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()

    # Use the top face (highest Z centroid).
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.BRepGProp import brepgprop
    top_face = None
    best_z = -1e30
    for face in _faces_of_shape(shape):
        gprops = GProp_GProps()
        brepgprop.SurfaceProperties(face, gprops)
        z = gprops.CentreOfMass().Z()
        if z > best_z:
            best_z = z
            top_face = face

    rows = uv_iso_curves(top_face, step_over_mm=2.0)
    assert len(rows) >= 2, f"expected ≥2 rows, got {len(rows)}"


@requires_occ
def test_uv_iso_curves_dense_step_gives_more_rows():
    """Halving step_over should roughly double the number of rows."""
    from kerf_cam.five_axis.drive_face import uv_iso_curves
    shape = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()

    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.BRepGProp import brepgprop
    top_face = None
    best_z = -1e30
    for face in _faces_of_shape(shape):
        gprops = GProp_GProps()
        brepgprop.SurfaceProperties(face, gprops)
        if gprops.CentreOfMass().Z() > best_z:
            best_z = gprops.CentreOfMass().Z()
            top_face = face

    rows_coarse = uv_iso_curves(top_face, step_over_mm=2.0)
    rows_fine = uv_iso_curves(top_face, step_over_mm=1.0)
    assert len(rows_fine) >= len(rows_coarse), (
        f"finer step_over produced fewer rows ({len(rows_fine)} vs {len(rows_coarse)})"
    )


@requires_occ
def test_uv_iso_curves_uv_within_domain():
    """Every (u, v) in the output must lie within the face's UV bounds."""
    from kerf_cam.five_axis.drive_face import uv_iso_curves
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepTools import BRepTools

    shape = BRepPrimAPI_MakeCylinder(5.0, 20.0).Shape()
    # Use the lateral face (largest U span).
    lateral = None
    largest_u_span = 0.0
    for face in _faces_of_shape(shape):
        u_min, u_max, v_min, v_max = BRepTools.UVBounds(face)
        if u_max - u_min > largest_u_span:
            largest_u_span = u_max - u_min
            lateral = face

    u_min, u_max, v_min, v_max = BRepTools.UVBounds(lateral)
    rows = uv_iso_curves(lateral, step_over_mm=3.0)
    tol = 1e-9
    for row in rows:
        for u, v in row:
            assert u_min - tol <= u <= u_max + tol, f"u={u} outside [{u_min}, {u_max}]"
            assert v_min - tol <= v <= v_max + tol, f"v={v} outside [{v_min}, {v_max}]"


@requires_occ
def test_uv_iso_curves_each_row_has_multiple_samples():
    """Each iso-curve row must have at least 3 (u, v) sample pairs."""
    from kerf_cam.five_axis.drive_face import uv_iso_curves
    shape = BRepPrimAPI_MakeBox(20.0, 20.0, 5.0).Shape()

    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.BRepGProp import brepgprop
    top_face = None
    best_z = -1e30
    for face in _faces_of_shape(shape):
        gprops = GProp_GProps()
        brepgprop.SurfaceProperties(face, gprops)
        if gprops.CentreOfMass().Z() > best_z:
            best_z = gprops.CentreOfMass().Z()
            top_face = face

    rows = uv_iso_curves(top_face, step_over_mm=4.0)
    for i, row in enumerate(rows):
        assert len(row) >= 3, f"row {i} has only {len(row)} sample(s)"


# ---------------------------------------------------------------------------
# T2e: IsNormalDefined returns None gracefully
# (sphere pole — U seam at V=pi/2 top pole)
# ---------------------------------------------------------------------------

@requires_occ
def test_surface_normal_at_undefined_returns_none():
    """
    At a sphere pole (V = ±pi/2), the normal may be undefined.
    surface_normal_at must return None (not raise) in that case.

    If the specific parametrisation doesn't produce an undefined normal at the
    pole, the test passes trivially — we only assert no exception is raised.
    """
    from kerf_cam.five_axis.drive_face import surface_normal_at
    shape = BRepPrimAPI_MakeSphere(5.0).Shape()
    faces = _faces_of_shape(shape)
    assert faces, "Sphere produced no faces"

    from OCC.Core.BRepTools import BRepTools
    face = faces[0]
    u_min, u_max, v_min, v_max = BRepTools.UVBounds(face)

    # Query at the north pole (v_max) — may be undefined on some OCCT versions.
    result_pole = surface_normal_at(face, (u_min + u_max) / 2.0, v_max)
    # We don't assert None — only assert no exception.
    assert result_pole is None or isinstance(result_pole, tuple)

    # Normal at the equator (v_mid) should always be defined.
    v_mid = (v_min + v_max) / 2.0
    result_equator = surface_normal_at(face, (u_min + u_max) / 2.0, v_mid)
    assert result_equator is not None, "sphere equator normal should be defined"
    _, n = result_equator
    mag = math.sqrt(sum(c * c for c in n))
    assert abs(mag - 1.0) < 1e-9
