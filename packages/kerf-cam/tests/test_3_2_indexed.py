"""
T4 tests: 3+2 indexed via STL rotation to align drive-face normal with +Z.

Tests are split into:
  1.  Pure-Python rotation-math tests (no OCC/OCL dependency) — always run.
  2.  Full integration tests (require opencamlib to run the sub-op).

The core assertion: rotation_from_to(n, +Z) applied to n must yield (0,0,1)
within float tolerance.
"""

import math
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

from kerf_cam.five_axis.indexed_3_2 import (
    rotation_from_to,
    apply_rotation_matrix,
    _rotate_stl_triangles,
    _load_stl_triangles,
)

try:
    import opencamlib as _ocl  # noqa: F401
    _has_ocl = True
except ImportError:
    _has_ocl = False

requires_ocl = pytest.mark.skipif(not _has_ocl, reason="opencamlib not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _close(a: tuple, b: tuple, tol: float = 1e-9) -> bool:
    return all(abs(ai - bi) <= tol for ai, bi in zip(a, b))


def _write_ascii_stl(path: str, triangles: list) -> None:
    """Write a minimal ASCII STL file from a list of (v0,v1,v2) tuples."""
    lines = ["solid test"]
    for v0, v1, v2 in triangles:
        # Compute a rough normal (not used in tests — only vertex positions matter).
        e1 = (v1[0]-v0[0], v1[1]-v0[1], v1[2]-v0[2])
        e2 = (v2[0]-v0[0], v2[1]-v0[1], v2[2]-v0[2])
        nx = e1[1]*e2[2] - e1[2]*e2[1]
        ny = e1[2]*e2[0] - e1[0]*e2[2]
        nz = e1[0]*e2[1] - e1[1]*e2[0]
        mag = math.sqrt(nx*nx + ny*ny + nz*nz) or 1.0
        lines.append(f"  facet normal {nx/mag:.6f} {ny/mag:.6f} {nz/mag:.6f}")
        lines.append("    outer loop")
        for vx, vy, vz in (v0, v1, v2):
            lines.append(f"      vertex {vx:.6f} {vy:.6f} {vz:.6f}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid test")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def _make_flat_stl(tmpdir: str, normal_dir: tuple, filename: str = "flat.stl") -> str:
    """Write a two-triangle flat quad STL with centroid at origin.

    The quad lies in the plane perpendicular to *normal_dir*.
    We choose two basis vectors perpendicular to the normal and build a 2×2
    quad in that plane.
    """
    nx, ny, nz = normal_dir
    mag = math.sqrt(nx*nx + ny*ny + nz*nz)
    n = (nx/mag, ny/mag, nz/mag)

    # Pick a tangent vector perpendicular to n.
    if abs(n[0]) < 0.9:
        raw = (1.0, 0.0, 0.0)
    else:
        raw = (0.0, 1.0, 0.0)

    # t1 = cross(raw, n)
    t1 = (
        raw[1]*n[2] - raw[2]*n[1],
        raw[2]*n[0] - raw[0]*n[2],
        raw[0]*n[1] - raw[1]*n[0],
    )
    m1 = math.sqrt(sum(c*c for c in t1))
    t1 = (t1[0]/m1, t1[1]/m1, t1[2]/m1)

    # t2 = cross(n, t1)
    t2 = (
        n[1]*t1[2] - n[2]*t1[1],
        n[2]*t1[0] - n[0]*t1[2],
        n[0]*t1[1] - n[1]*t1[0],
    )

    # Four corners of a 2×2 quad centred at origin.
    p00 = (-t1[0]-t2[0], -t1[1]-t2[1], -t1[2]-t2[2])
    p10 = ( t1[0]-t2[0],  t1[1]-t2[1],  t1[2]-t2[2])
    p11 = ( t1[0]+t2[0],  t1[1]+t2[1],  t1[2]+t2[2])
    p01 = (-t1[0]+t2[0], -t1[1]+t2[1], -t1[2]+t2[2])

    tris = [(p00, p10, p11), (p00, p11, p01)]
    path = os.path.join(tmpdir, filename)
    _write_ascii_stl(path, tris)
    return path


# ---------------------------------------------------------------------------
# Pure-Python rotation tests (no OCC/OCL required — always run)
# ---------------------------------------------------------------------------

def test_rotation_from_to_identity():
    """rotation_from_to(v, v) == identity."""
    R = rotation_from_to((0, 0, 1), (0, 0, 1))
    rotated = apply_rotation_matrix(R, (0.0, 0.0, 1.0))
    assert _close(rotated, (0.0, 0.0, 1.0)), f"expected (0,0,1), got {rotated}"


def test_rotation_from_to_45_deg_z_normal():
    """
    Rotate a normal at 45° off +Z back to +Z.
    The rotation must map the source vector to (0,0,1) exactly.
    """
    # Normal at 45° from +Z (tilted toward +X).
    s = math.sin(math.radians(45))
    c = math.cos(math.radians(45))
    src = (s, 0.0, c)  # ≈ (0.707, 0, 0.707)

    R = rotation_from_to(src, (0.0, 0.0, 1.0))
    rotated = apply_rotation_matrix(R, src)
    assert _close(rotated, (0.0, 0.0, 1.0), tol=1e-9), (
        f"Expected (0,0,1), got {rotated}"
    )


def test_rotation_from_to_minus_z_normal():
    """-Z normal → +Z rotation (180° flip)."""
    R = rotation_from_to((0.0, 0.0, -1.0), (0.0, 0.0, 1.0))
    rotated = apply_rotation_matrix(R, (0.0, 0.0, -1.0))
    assert _close(rotated, (0.0, 0.0, 1.0), tol=1e-9), (
        f"Expected (0,0,1), got {rotated}"
    )


def test_rotation_from_to_arbitrary_normal():
    """Arbitrary tilted normal must be mapped to (0,0,1) within 1e-9."""
    for nx, ny, nz in [
        (0.5, 0.5, 0.707),
        (-0.3, 0.8, 0.5),
        (0.0, 1.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.577, 0.577, 0.577),
    ]:
        mag = math.sqrt(nx*nx + ny*ny + nz*nz)
        src = (nx/mag, ny/mag, nz/mag)
        R = rotation_from_to(src, (0.0, 0.0, 1.0))
        rotated = apply_rotation_matrix(R, src)
        assert _close(rotated, (0.0, 0.0, 1.0), tol=1e-9), (
            f"Failed for src={src}: got {rotated}"
        )


def test_rotation_matrix_is_orthogonal():
    """R^T R should equal the identity (orthogonal matrix)."""
    src = (0.5, 0.5, 0.707)
    mag = math.sqrt(sum(c*c for c in src))
    src = tuple(c/mag for c in src)
    R = rotation_from_to(src, (0.0, 0.0, 1.0))

    # R^T @ R
    tol = 1e-9
    for i in range(3):
        for j in range(3):
            val = sum(R[k][i] * R[k][j] for k in range(3))
            expected = 1.0 if i == j else 0.0
            assert abs(val - expected) < tol, (
                f"R^T R [{i},{j}] = {val}, expected {expected}"
            )


def test_rotate_stl_triangles_maps_normal_to_z():
    """
    Given a flat quad with normal at 45°, rotating triangles by R should
    place all vertices in the +Z-up plane.

    We verify: if original centroid_z ≈ 0 and tilt is 45°, after rotation
    centroid_z_new = centroid_z * sin(45°) ≈ 0 still (flat centred quad).
    And the resulting normal from the rotated triangles is (0,0,1).
    """
    angle_rad = math.radians(45)
    # Flat quad with normal (sin45, 0, cos45) — tilted 45° toward +X.
    s = math.sin(angle_rad)
    c = math.cos(angle_rad)
    normal = (s, 0.0, c)
    # Build a simple 2-triangle quad perpendicular to this normal.
    with tempfile.TemporaryDirectory() as tmpdir:
        stl_path = _make_flat_stl(tmpdir, normal)
        triangles = _load_stl_triangles(stl_path)

    R = rotation_from_to(normal, (0.0, 0.0, 1.0))
    rotated = _rotate_stl_triangles(triangles, R)

    # Compute normal of the first rotated triangle via cross product.
    v0, v1, v2 = rotated[0]
    e1 = (v1[0]-v0[0], v1[1]-v0[1], v1[2]-v0[2])
    e2 = (v2[0]-v0[0], v2[1]-v0[1], v2[2]-v0[2])
    cross = (
        e1[1]*e2[2] - e1[2]*e2[1],
        e1[2]*e2[0] - e1[0]*e2[2],
        e1[0]*e2[1] - e1[1]*e2[0],
    )
    mag = math.sqrt(sum(c_*c_ for c_ in cross))
    face_normal_rotated = tuple(c_/mag for c_ in cross)

    # The face normal of the rotated triangle must be ±Z.
    assert abs(abs(face_normal_rotated[2]) - 1.0) < 1e-6, (
        f"Rotated face normal {face_normal_rotated} is not ±Z"
    )


def test_zero_length_normal_returns_error():
    """run_3_2_indexed with zero normal vector must return errors."""
    from kerf_cam.five_axis.indexed_3_2 import run_3_2_indexed
    with tempfile.TemporaryDirectory() as tmpdir:
        stl_path = _make_flat_stl(tmpdir, (0, 0, 1))
        result = run_3_2_indexed({
            "stl_path": stl_path,
            "drive_face_normal": [0.0, 0.0, 0.0],
            "three_axis_op": "face",
        })
    assert result.get("errors"), "Expected error for zero-length normal"
    assert len(result["cl_points"]) == 0


def test_rotation_from_to_45_tilted_stl_normal_becomes_z():
    """
    Key T4 assertion: rotate a 45°-tilted-plane STL; assert the rotated normal
    is (0,0,1) within float tolerance.
    """
    angle = math.radians(45)
    normal = (math.sin(angle), 0.0, math.cos(angle))

    R = rotation_from_to(normal, (0.0, 0.0, 1.0))

    rotated_n = apply_rotation_matrix(R, normal)
    assert _close(rotated_n, (0.0, 0.0, 1.0), tol=1e-9), (
        f"45° tilted normal not aligned to Z after rotation: {rotated_n}"
    )


# ---------------------------------------------------------------------------
# Integration test — requires opencamlib
# ---------------------------------------------------------------------------

@requires_ocl
def test_run_3_2_indexed_returns_cl_points():
    """
    run_3_2_indexed on a flat tilted STL with a face sub-op must return
    at least one CL point and rotated_normal ≈ (0,0,1).
    """
    from kerf_cam.five_axis.indexed_3_2 import run_3_2_indexed

    angle = math.radians(30)
    normal = (math.sin(angle), 0.0, math.cos(angle))  # 30° tilted

    with tempfile.TemporaryDirectory() as tmpdir:
        stl_path = _make_flat_stl(tmpdir, normal)
        result = run_3_2_indexed({
            "stl_path": stl_path,
            "drive_face_normal": list(normal),
            "three_axis_op": "face",
            "tool_diameter": 2.0,
            "step_over": 0.5,
            "step_down": 0.5,
            "feed_rate": 1000.0,
            "spindle_rpm": 10000,
        })

    assert "errors" not in result or not result.get("errors"), (
        f"Unexpected errors: {result.get('errors')}"
    )

    rn = result["rotated_normal"]
    assert _close(tuple(rn), (0.0, 0.0, 1.0), tol=1e-5), (
        f"rotated_normal should be (0,0,1), got {rn}"
    )

    # No collision warning must be present (R7 compliance).
    assert any("collision" in w.lower() or "camotics" in w.lower()
               for w in result.get("warnings", [])), (
        "Expected a no-collision-check warning (R7)"
    )


@requires_ocl
def test_run_3_2_indexed_rotation_matrix_is_correct():
    """rotation_matrix in result must map drive_face_normal → (0,0,1)."""
    from kerf_cam.five_axis.indexed_3_2 import run_3_2_indexed

    angle = math.radians(45)
    normal = (math.sin(angle), 0.0, math.cos(angle))

    with tempfile.TemporaryDirectory() as tmpdir:
        stl_path = _make_flat_stl(tmpdir, normal)
        result = run_3_2_indexed({
            "stl_path": stl_path,
            "drive_face_normal": list(normal),
            "three_axis_op": "face",
            "step_over": 0.5,
            "step_down": 0.5,
        })

    R = result["rotation_matrix"]
    rotated = apply_rotation_matrix(R, normal)
    assert _close(rotated, (0.0, 0.0, 1.0), tol=1e-9), (
        f"R @ normal ≠ (0,0,1): got {rotated}"
    )
