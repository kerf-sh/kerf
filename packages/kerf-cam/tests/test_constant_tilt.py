"""
T3 tests: constant-tilt finishing CL generation.

Tests exercise:
  - tilt=0 on a flat face → tool axis = surface normal everywhere (0,0,±1)
  - tilt=15 on a flat face → all axes tilted exactly 15° off the face normal
  - ball-end tip geometry: verify tip is below CC point on a +Z plane
  - skipped_uv count is 0 on a non-degenerate surface
  - tilt_deg out of range returns an error
  - lead_deg rotates the axis further

All tests require pythonOCC and write a temporary STEP file to disk.
They are skipped when pythonOCC is absent.
"""

import math
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

try:
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCC.Core.STEPControl import STEPControl_Writer
    from OCC.Core.IFSelect import IFSelect_RetDone
    _has_occ = True
except ImportError:
    _has_occ = False

requires_occ = pytest.mark.skipif(not _has_occ, reason="pythonOCC not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_box_step(tmpdir: str, x=10.0, y=10.0, z=10.0, filename="box.step") -> str:
    """Write a box STEP file, return path."""
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCC.Core.STEPControl import STEPControl_Writer
    from OCC.Core.IFSelect import IFSelect_RetDone

    shape = BRepPrimAPI_MakeBox(x, y, z).Shape()
    path = os.path.join(tmpdir, filename)
    writer = STEPControl_Writer()
    writer.Transfer(shape, 0)
    status = writer.Write(path)
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEPControl_Writer failed (status={status})")
    return path


def _top_face_id_of_box(step_path: str) -> int:
    """Return the face_id of the top (highest Z centroid) face in *step_path*."""
    from kerf_cam.five_axis.drive_face import extract_drive_face
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.BRepGProp import brepgprop
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.IFSelect import IFSelect_RetDone

    reader = STEPControl_Reader()
    reader.ReadFile(step_path)
    reader.TransferRoots()
    shape = reader.OneShape()

    faces = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        faces.append(exp.Current())
        exp.Next()

    best_z = -1e30
    best_idx = 0
    for idx, face in enumerate(faces):
        gp = GProp_GProps()
        brepgprop.SurfaceProperties(face, gp)
        z = gp.CentreOfMass().Z()
        if z > best_z:
            best_z = z
            best_idx = idx
    return best_idx


def _angle_between(a: tuple, b: tuple) -> float:
    """Return angle in degrees between two 3-tuples (unit vectors assumed)."""
    dot = sum(ai * bi for ai, bi in zip(a, b))
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


# ---------------------------------------------------------------------------
# T3a: tilt=0 on flat face → tool axis = face normal
# ---------------------------------------------------------------------------

@requires_occ
def test_tilt_zero_flat_face_axis_equals_normal():
    """
    On a flat (planar) top face with tilt_deg=0, every tool axis must equal
    the face normal (within 1e-5 degrees).
    """
    from kerf_cam.five_axis.constant_tilt import run_constant_tilt

    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = _write_box_step(tmpdir, 10.0, 10.0, 10.0)
        face_id = _top_face_id_of_box(step_path)

        result = run_constant_tilt({
            "brep_path": step_path,
            "drive_face_id": face_id,
            "tilt_deg": 0.0,
            "step_over_mm": 2.0,
            "ball_radius_mm": 1.5,
        })

    assert "errors" not in result or not result.get("errors"), (
        f"Unexpected errors: {result.get('errors')}"
    )

    cl_pts = result["cl_points"]
    assert len(cl_pts) > 0, "Expected CL points from flat face tilt=0"

    # The face normal of the top face is ±Z.
    # All tool axes must point in the same direction (|nz|=1).
    for pt in cl_pts:
        axis = (pt["i"], pt["j"], pt["k"])
        assert abs(abs(axis[2]) - 1.0) < 1e-5, (
            f"tilt=0 flat face: expected |nz|=1, got axis={axis}"
        )


# ---------------------------------------------------------------------------
# T3b: tilt=15 on flat face → all axes tilted exactly 15° off normal
# ---------------------------------------------------------------------------

@requires_occ
def test_tilt_15_flat_face_correct_tilt_angle():
    """
    With tilt_deg=15 on the flat top face, every tool axis must be exactly 15°
    away from the surface normal (within 0.5° tolerance for float rounding).
    """
    from kerf_cam.five_axis.constant_tilt import run_constant_tilt
    from kerf_cam.five_axis.drive_face import extract_drive_face, surface_normal_at
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.BRepTools import BRepTools

    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = _write_box_step(tmpdir, 10.0, 10.0, 10.0)
        face_id = _top_face_id_of_box(step_path)

        result = run_constant_tilt({
            "brep_path": step_path,
            "drive_face_id": face_id,
            "tilt_deg": 15.0,
            "step_over_mm": 2.0,
            "ball_radius_mm": 1.5,
        })

    assert "errors" not in result or not result.get("errors")
    cl_pts = result["cl_points"]
    assert len(cl_pts) > 0

    # On a flat +Z face the surface normal is (0,0,1) (or 0,0,-1 depending on
    # orientation).  The tilt rotates about the tangent by 15°.  We just verify
    # that no axis has |nz| == 1 (i.e., all axes are tilted away from straight up).
    # More precisely: since the tilt is about the U tangent (X direction for a box
    # top face), the Z component of the tilted axis must be cos(15°) ≈ 0.9659.
    cos15 = math.cos(math.radians(15.0))
    for pt in cl_pts:
        axis = (pt["i"], pt["j"], pt["k"])
        # |axis| must be 1.0 (unit vector check).
        mag = math.sqrt(sum(c * c for c in axis))
        assert abs(mag - 1.0) < 1e-6, f"axis not unit: mag={mag}"
        # The tilt angle off +Z (or -Z) must be 15°.
        nz_ref = (0.0, 0.0, 1.0) if axis[2] > 0 else (0.0, 0.0, -1.0)
        angle = _angle_between(axis, nz_ref)
        assert abs(angle - 15.0) < 0.5, (
            f"Expected 15° tilt, got {angle:.3f}° for axis={axis}"
        )


# ---------------------------------------------------------------------------
# T3c: ball-end tip is below the surface CC point for a +Z plane
# ---------------------------------------------------------------------------

@requires_occ
def test_ball_end_tip_below_surface():
    """
    For tilt=0 on a flat top face at Z=10, the ball-end tip must be at
    Z = surface_z - ball_radius (because the tool axis is +Z, ball centre
    is above surface, tip is back along the axis by r → tip.z = surface.z).

    Specifically: tip.z == surface_point.z exactly when tilt=0 and the normal
    is +Z (ball centre at z+r, tip at z+r - r = z).
    """
    from kerf_cam.five_axis.constant_tilt import run_constant_tilt

    ball_r = 2.0
    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = _write_box_step(tmpdir, 10.0, 10.0, 10.0)
        face_id = _top_face_id_of_box(step_path)

        result = run_constant_tilt({
            "brep_path": step_path,
            "drive_face_id": face_id,
            "tilt_deg": 0.0,
            "step_over_mm": 2.0,
            "ball_radius_mm": ball_r,
        })

    cl_pts = result["cl_points"]
    assert len(cl_pts) > 0

    # Top face is at Z=10 mm.  tip.z should equal 10.0 (ball_centre.z = 12,
    # tip.z = 12 - 2 = 10).
    surface_z = 10.0
    for pt in cl_pts:
        assert abs(pt["z"] - surface_z) < 1e-4, (
            f"tip.z={pt['z']:.6f} != surface_z={surface_z} (expected equal for tilt=0)"
        )


# ---------------------------------------------------------------------------
# T3d: CL points are non-empty for a valid spec
# ---------------------------------------------------------------------------

@requires_occ
def test_cl_points_non_empty():
    """run_constant_tilt on a real face must return at least one CL point."""
    from kerf_cam.five_axis.constant_tilt import run_constant_tilt
    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = _write_box_step(tmpdir)
        result = run_constant_tilt({
            "brep_path": step_path,
            "drive_face_id": 0,
            "tilt_deg": 10.0,
            "step_over_mm": 3.0,
            "ball_radius_mm": 1.0,
        })
    assert len(result["cl_points"]) > 0, "Expected at least one CL point"


# ---------------------------------------------------------------------------
# T3e: tilt_deg out of range returns error, no CL points
# ---------------------------------------------------------------------------

@requires_occ
def test_tilt_out_of_range_returns_error():
    """tilt_deg > 30 must return errors list and no CL points."""
    from kerf_cam.five_axis.constant_tilt import run_constant_tilt
    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = _write_box_step(tmpdir)
        result = run_constant_tilt({
            "brep_path": step_path,
            "drive_face_id": 0,
            "tilt_deg": 45.0,   # out of range
            "step_over_mm": 2.0,
            "ball_radius_mm": 1.5,
        })
    assert result.get("errors"), "Expected errors for tilt_deg=45"
    assert len(result["cl_points"]) == 0


@requires_occ
def test_tilt_negative_returns_error():
    """Negative tilt_deg must also be rejected."""
    from kerf_cam.five_axis.constant_tilt import run_constant_tilt
    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = _write_box_step(tmpdir)
        result = run_constant_tilt({
            "brep_path": step_path,
            "drive_face_id": 0,
            "tilt_deg": -5.0,
            "step_over_mm": 2.0,
            "ball_radius_mm": 1.5,
        })
    assert result.get("errors"), "Expected errors for negative tilt_deg"
    assert len(result["cl_points"]) == 0


# ---------------------------------------------------------------------------
# T3f: skipped_uv is 0 on a non-degenerate planar surface
# ---------------------------------------------------------------------------

@requires_occ
def test_no_skipped_uv_on_plane():
    """On a flat planar face every normal is defined — skipped_uv must be 0."""
    from kerf_cam.five_axis.constant_tilt import run_constant_tilt
    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = _write_box_step(tmpdir)
        face_id = _top_face_id_of_box(step_path)
        result = run_constant_tilt({
            "brep_path": step_path,
            "drive_face_id": face_id,
            "tilt_deg": 0.0,
            "step_over_mm": 2.0,
            "ball_radius_mm": 1.5,
        })
    assert result["skipped_uv"] == 0, (
        f"Expected 0 skipped UV points on flat face, got {result['skipped_uv']}"
    )


# ---------------------------------------------------------------------------
# T3g: lead_deg non-zero shifts the axis further from normal
# ---------------------------------------------------------------------------

@requires_occ
def test_lead_deg_shifts_axis():
    """
    Adding lead_deg=10 to an already-tilted axis should produce a further
    rotation — the resulting axis must differ from tilt_deg-only.
    """
    from kerf_cam.five_axis.constant_tilt import run_constant_tilt
    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = _write_box_step(tmpdir)
        face_id = _top_face_id_of_box(step_path)

        result_no_lead = run_constant_tilt({
            "brep_path": step_path,
            "drive_face_id": face_id,
            "tilt_deg": 10.0,
            "step_over_mm": 3.0,
            "ball_radius_mm": 1.5,
            "lead_deg": 0.0,
        })
        result_with_lead = run_constant_tilt({
            "brep_path": step_path,
            "drive_face_id": face_id,
            "tilt_deg": 10.0,
            "step_over_mm": 3.0,
            "ball_radius_mm": 1.5,
            "lead_deg": 10.0,
        })

    pts_no = result_no_lead["cl_points"]
    pts_w = result_with_lead["cl_points"]
    assert len(pts_no) > 0
    assert len(pts_w) > 0

    # At least one CL point must differ between the two runs.
    n = min(len(pts_no), len(pts_w))
    diffs = [
        any(abs(pts_no[i][k] - pts_w[i][k]) > 1e-6 for k in ("i", "j", "k"))
        for i in range(n)
    ]
    assert any(diffs), "lead_deg=10 produced identical axes to lead_deg=0"
