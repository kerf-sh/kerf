"""
3+2 indexed strategy (T4).

Algorithm
---------
1.  Accept ``drive_face_normal`` as a (nx, ny, nz) unit-ish vector (the normal
    of the face the user wants to mill normal-to).
2.  Build a 3×3 rotation matrix R such that  R @ drive_face_normal = (0, 0, 1).
3.  Apply R to all STL triangles (in-memory; pure Python, vectorised by list
    comprehension — fast enough for meshes < 100 k tris; see R1 in the plan).
4.  Run the requested 3-axis sub-op (``parallel_3d`` / ``face`` / ``waterline``)
    against the rotated STL surface using the existing opencamlib helpers.
5.  Return a CAMResult dict:
    {
        "cl_points": [{"x": ..., "y": ..., "z": ...}, ...],  # in rotated frame
        "rotation_matrix": [[r00, r01, r02], [r10, r11, r12], [r20, r21, r22]],
        "rotated_normal": [0, 0, 1],   # sanity check
        "warnings": [...],
    }

The CL points are in the rotated coordinate frame.  The T5/T6 post-processor
will emit:
    G0 A<a_deg> C<c_deg>          ; index to drive-face orientation
    ... 3-axis G-code in rotated frame ...
    G0 A0 C0                      ; unindex

rotation_from_to
-----------------
Uses Rodrigues' rotation formula to build a 3×3 matrix from any source vector
to the target (+Z in our case).  Handles the degenerate case where source ≈ +Z
(identity) or source ≈ -Z (180° flip about X).

No numpy / scipy dependency — pure Python floats.
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Pure-Python 3×3 rotation-matrix utilities
# ---------------------------------------------------------------------------

def rotation_from_to(src: tuple, dst: tuple) -> list[list[float]]:
    """Return a 3×3 rotation matrix R such that R @ src ≈ dst.

    *src* and *dst* need not be unit vectors — they are normalised internally.
    Returns a list-of-lists (row-major) 3×3 matrix.

    Degenerate cases:
      * src ≈ dst  → identity matrix.
      * src ≈ -dst → 180° rotation about an orthogonal axis.
    """
    def _norm(v):
        mag = math.sqrt(sum(c * c for c in v))
        if mag < 1e-12:
            raise ValueError(f"zero-length vector: {v}")
        return (v[0] / mag, v[1] / mag, v[2] / mag)

    def _cross(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    def _dot(a, b):
        return sum(ai * bi for ai, bi in zip(a, b))

    s = _norm(src)
    d = _norm(dst)

    cos_t = _dot(s, d)
    cos_t = max(-1.0, min(1.0, cos_t))

    # Nearly identical: return identity.
    if cos_t > 1.0 - 1e-10:
        return [[1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0]]

    # Antiparallel: rotate 180° about an axis perpendicular to src.
    if cos_t < -1.0 + 1e-10:
        # Choose a perpendicular axis by crossing with a vector that is NOT
        # parallel to s.  Use whichever of X/Y/Z has the smallest |dot| with s.
        candidates = ((1.0,0.0,0.0), (0.0,1.0,0.0), (0.0,0.0,1.0))
        perp = min(candidates, key=lambda p: abs(_dot(s, p)))
        k = _cross(s, perp)
        k = _norm(k)
        # Rodrigues with theta = pi: R = 2 * k*k^T - I
        return [
            [2*k[0]*k[0] - 1, 2*k[0]*k[1],     2*k[0]*k[2]    ],
            [2*k[1]*k[0],     2*k[1]*k[1] - 1, 2*k[1]*k[2]    ],
            [2*k[2]*k[0],     2*k[2]*k[1],     2*k[2]*k[2] - 1],
        ]

    # General case: axis = cross(s, d) / sin(theta), use Rodrigues.
    axis = _cross(s, d)
    sin_t = math.sqrt(sum(c * c for c in axis))
    if sin_t < 1e-12:
        return [[1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0]]
    k = (axis[0] / sin_t, axis[1] / sin_t, axis[2] / sin_t)

    # Rodrigues: R = I*cos + (1-cos)*k*k^T + sin * [k]×
    c = cos_t
    s_ = sin_t
    kx, ky, kz = k
    return [
        [c + kx*kx*(1-c),    kx*ky*(1-c) - kz*s_, kx*kz*(1-c) + ky*s_],
        [ky*kx*(1-c) + kz*s_, c + ky*ky*(1-c),    ky*kz*(1-c) - kx*s_],
        [kz*kx*(1-c) - ky*s_, kz*ky*(1-c) + kx*s_, c + kz*kz*(1-c)   ],
    ]


def apply_rotation_matrix(R: list[list[float]], v: tuple) -> tuple:
    """Apply 3×3 rotation matrix R to vector v = (x, y, z)."""
    x, y, z = v
    return (
        R[0][0]*x + R[0][1]*y + R[0][2]*z,
        R[1][0]*x + R[1][1]*y + R[1][2]*z,
        R[2][0]*x + R[2][1]*y + R[2][2]*z,
    )


# ---------------------------------------------------------------------------
# STL rotation
# ---------------------------------------------------------------------------

def _rotate_stl_triangles(triangles: list, R: list[list[float]]) -> list:
    """Return new triangle list with each vertex rotated by R.

    *triangles* is a list of 3-tuples of (x,y,z) float 3-tuples:
        [(v0, v1, v2), ...]
    where each v_i is (x, y, z).
    """
    return [
        (
            apply_rotation_matrix(R, tri[0]),
            apply_rotation_matrix(R, tri[1]),
            apply_rotation_matrix(R, tri[2]),
        )
        for tri in triangles
    ]


def _load_stl_triangles(stl_path: str) -> list:
    """Parse an ASCII STL file, returning list of triangles as ((x,y,z)*3)."""
    triangles = []
    verts = []
    with open(stl_path, "r", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("vertex "):
                parts = line.split()
                verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
                if len(verts) == 3:
                    triangles.append(tuple(verts))
                    verts = []
    return triangles


def _triangles_to_ocl_surface(triangles: list):
    """Build an ocl.STLSurf from a list of (v0, v1, v2) tuples."""
    import opencamlib as ocl
    surface = ocl.STLSurf()
    for v0, v1, v2 in triangles:
        surface.addTriangle(ocl.Triangle(
            ocl.Point(*v0),
            ocl.Point(*v1),
            ocl.Point(*v2),
        ))
    return surface


# ---------------------------------------------------------------------------
# Three-axis sub-op dispatch
# ---------------------------------------------------------------------------

def _run_sub_op(
    sub_op: str,
    surface,
    op_params: dict,
) -> list:
    """Dispatch to the appropriate 3-axis opencamlib helper.

    Returns a list of CL points with .x, .y, .z attributes (ocl.CLPoint).
    """
    from kerf_cam.routes import (
        CAMOperation, _run_parallel_3d, _run_waterline, _run_ocl_op,
    )
    import opencamlib as ocl

    cam_op = CAMOperation(
        type=sub_op,
        tool_diameter=float(op_params.get("tool_diameter", 3.0)),
        step_down=float(op_params.get("step_down", 0.5)),
        step_over=float(op_params.get("step_over", 1.0)),
        feed_rate=float(op_params.get("feed_rate", 1000.0)),
        spindle_rpm=int(op_params.get("spindle_rpm", 10000)),
        coolant=op_params.get("coolant", "flood"),
        direction=op_params.get("direction", "x"),
        angle_deg=op_params.get("angle_deg"),
    )

    tool_r = cam_op.tool_diameter / 2000.0  # mm → m for ocl
    tool_h = 50.0 / 1000.0                  # 50 mm flute height (default)
    tool = ocl.BallCutter(cam_op.tool_diameter / 1000.0, tool_h)

    if sub_op in ("face", "parallel_3d"):
        return _run_parallel_3d(tool, cam_op, surface)
    elif sub_op == "waterline":
        return _run_waterline(tool, cam_op, surface)
    else:
        # contour / pocket / profile — use generic OCL op (no B-rep for a raw STL).
        return _run_ocl_op(sub_op, tool, cam_op, surface)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_3_2_indexed(spec: dict[str, Any]) -> dict[str, Any]:
    """Compute 3+2 indexed CL points for *spec*.

    Spec keys
    ---------
    stl_path           : str   — path to ASCII STL of the part.
    drive_face_normal  : list  — [nx, ny, nz] normal to align with +Z.
    three_axis_op      : str   — sub-op: "face" | "parallel_3d" | "waterline" |
                                 "pocket" | "contour" | "profile".
    tool_diameter      : float — mm (default 3.0).
    step_over          : float — mm (default 1.0).
    step_down          : float — mm (default 0.5).
    feed_rate          : float — mm/min (default 1000.0).
    spindle_rpm        : int   — (default 10000).
    direction          : str   — "x" | "y" for parallel_3d (default "x").

    Returns a CAMResult dict:
    {
        "cl_points":       [{"x": ..., "y": ..., "z": ...}, ...],
        "rotation_matrix": [[r00, ...], ...],
        "rotated_normal":  [0.0, 0.0, 1.0],
        "warnings":        [...],
    }

    The cl_points are in the *rotated* coordinate frame (i.e., after applying R).
    The T5/T6 post-processor will prepend a G0 A<a> C<c> positioning move
    before emitting the 3-axis G-code from these points.
    """
    stl_path = spec["stl_path"]
    raw_normal = spec.get("drive_face_normal", [0.0, 0.0, 1.0])
    sub_op = spec.get("three_axis_op", "face")
    warnings: list[str] = []

    # Normalise drive_face_normal.
    nx, ny, nz = float(raw_normal[0]), float(raw_normal[1]), float(raw_normal[2])
    mag = math.sqrt(nx*nx + ny*ny + nz*nz)
    if mag < 1e-9:
        return {
            "cl_points": [],
            "rotation_matrix": [],
            "rotated_normal": [],
            "warnings": [],
            "errors": ["drive_face_normal is a zero vector — cannot compute rotation"],
        }
    src = (nx / mag, ny / mag, nz / mag)

    # Build rotation that takes src → +Z.
    dst = (0.0, 0.0, 1.0)
    R = rotation_from_to(src, dst)

    # Sanity-check: R @ src should be ≈ +Z.
    rotated_src = apply_rotation_matrix(R, src)
    if abs(rotated_src[2] - 1.0) > 1e-5:
        warnings.append(
            f"Rotation sanity check failed: R @ src = {rotated_src} (expected ~(0,0,1)). "
            "Proceeding anyway — verify toolpath."
        )

    # Load and rotate STL.
    triangles = _load_stl_triangles(stl_path)
    if not triangles:
        return {
            "cl_points": [],
            "rotation_matrix": R,
            "rotated_normal": list(rotated_src),
            "warnings": warnings,
            "errors": [f"No triangles found in STL file: {stl_path}"],
        }

    rotated_tris = _rotate_stl_triangles(triangles, R)

    # Build ocl surface from rotated triangles.
    try:
        surface = _triangles_to_ocl_surface(rotated_tris)
    except ImportError:
        return {
            "cl_points": [],
            "rotation_matrix": R,
            "rotated_normal": list(rotated_src),
            "warnings": warnings,
            "errors": ["opencamlib not installed — cannot run 3-axis sub-op"],
        }

    # Run the requested 3-axis op.
    ocl_points = _run_sub_op(sub_op, surface, spec)

    cl_points = [
        {"x": pt.x, "y": pt.y, "z": pt.z}
        for pt in ocl_points
    ]

    if not cl_points:
        warnings.append(
            f"3-axis sub-op '{sub_op}' produced no CL points on the rotated surface. "
            "Check step_over/step_down vs surface size."
        )

    # No collision check in v1 — emit a mandatory warning per plan (R7).
    warnings.append(
        "No collision/gouge check performed — verify toolpath with CAMotics "
        "before sending to machine (5-axis R7)."
    )

    return {
        "cl_points": cl_points,
        "rotation_matrix": R,
        "rotated_normal": [rotated_src[0], rotated_src[1], rotated_src[2]],
        "warnings": warnings,
    }
