"""
Constant-tilt surface-finishing strategy (T3).

Algorithm
---------
For each UV iso-curve row at *step_over_mm* spacing:
  for each sample point along the iso-curve:
    1.  Query surface normal n at (u, v).
    2.  Query U-direction tangent t at (u, v) — this is the path-tangent.
    3.  Tilt the tool axis a = rotate(n, t, tilt_deg)
        (positive tilt = lean forward in the direction of travel).
    4.  Ball-end tip math:
          ball_centre = surface_point + r * n   (centre touches the surface)
          tip         = ball_centre - r * a     (tip along axis direction)
    5.  Emit { x, y, z, i, j, k } (tip position + tool-axis unit vector).

The tilt rotation uses the Rodrigues formula so there is no dependency
on numpy or scipy.

Returns a CAMResult dict:
    {
        "cl_points": [{"x": ..., "y": ..., "z": ..., "i": ..., "j": ..., "k": ...}, ...],
        "warnings": [...],
        "skipped_uv": int,   # CC points where normal was undefined
    }

G-code emission is deferred to T5 / T6 — this module only produces CL data.
"""

from __future__ import annotations

import math
from typing import Any

# Drive-face helpers (same package, no OCC direct dependency here).
from kerf_cam.five_axis.drive_face import (
    extract_drive_face,
    surface_normal_at,
    surface_d1u_at,
    uv_iso_curves,
)


# ---------------------------------------------------------------------------
# Rodrigues rotation
# ---------------------------------------------------------------------------

def _rotate_vec(v: tuple, axis: tuple, angle_deg: float) -> tuple:
    """Rotate vector *v* about *axis* by *angle_deg* degrees (Rodrigues formula).

    *axis* must be a unit vector.  Returns a unit vector.
    """
    if abs(angle_deg) < 1e-10:
        return v

    theta = math.radians(angle_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    vx, vy, vz = v
    ax, ay, az = axis

    # dot(axis, v)
    dot = ax * vx + ay * vy + az * vz

    # cross(axis, v)
    cx = ay * vz - az * vy
    cy = az * vx - ax * vz
    cz = ax * vy - ay * vx

    rx = vx * cos_t + cx * sin_t + ax * dot * (1 - cos_t)
    ry = vy * cos_t + cy * sin_t + ay * dot * (1 - cos_t)
    rz = vz * cos_t + cz * sin_t + az * dot * (1 - cos_t)

    mag = math.sqrt(rx * rx + ry * ry + rz * rz)
    if mag < 1e-12:
        return v  # degenerate — return input unchanged
    return (rx / mag, ry / mag, rz / mag)


def _add(a: tuple, b: tuple, scale: float = 1.0) -> tuple:
    """a + scale * b for 3-tuples."""
    return (a[0] + scale * b[0], a[1] + scale * b[1], a[2] + scale * b[2])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_constant_tilt(spec: dict[str, Any]) -> dict[str, Any]:
    """Compute constant-tilt finishing CL points for *spec*.

    Spec keys
    ---------
    brep_path       : str   — path to STEP or BRep file containing the drive face.
    drive_face_id   : int   — zero-based face index (from TopExp_Explorer walk).
    tilt_deg        : float — tool axis tilt off surface normal (°); 0–30.
    step_over_mm    : float — iso-curve spacing and row step-over (mm).
    ball_radius_mm  : float — ball-end mill radius (mm).
    tool_length_mm  : float — (informational; not used in tip math — T5/T6 job).
    lead_deg        : float — (optional) additional lead/lag tilt along path, default 0.

    Returns a CAMResult dict (see module docstring).
    """
    brep_path = spec["brep_path"]
    face_id = int(spec.get("drive_face_id", 0))
    tilt_deg = float(spec.get("tilt_deg", 0.0))
    step_over_mm = float(spec.get("step_over_mm", 1.0))
    ball_r = float(spec.get("ball_radius_mm", 1.5))
    lead_deg = float(spec.get("lead_deg", 0.0))

    if tilt_deg < 0 or tilt_deg > 30:
        return {
            "cl_points": [],
            "warnings": [],
            "skipped_uv": 0,
            "errors": [f"tilt_deg={tilt_deg} out of range [0, 30] — rejected"],
        }

    face = extract_drive_face(brep_path, face_id)

    rows = uv_iso_curves(face, step_over_mm)

    cl_points: list[dict[str, float]] = []
    warnings: list[str] = []
    skipped = 0

    for row in rows:
        for u, v in row:
            result = surface_normal_at(face, u, v)
            if result is None:
                skipped += 1
                continue
            point, n = result

            # Path tangent — fall back to (1, 0, 0) if degenerate.
            tangent = surface_d1u_at(face, u, v)
            if tangent is None:
                tangent = (1.0, 0.0, 0.0)

            # Tool axis: tilt normal by tilt_deg about the path tangent.
            axis = _rotate_vec(n, tangent, tilt_deg)

            # Optional lead/lag: tilt further about (n × tangent).
            if abs(lead_deg) > 1e-6:
                nx, ny, nz = n
                tx, ty, tz = tangent
                cross = (
                    ny * tz - nz * ty,
                    nz * tx - nx * tz,
                    nx * ty - ny * tx,
                )
                mag = math.sqrt(sum(c * c for c in cross))
                if mag > 1e-9:
                    cross = (cross[0] / mag, cross[1] / mag, cross[2] / mag)
                    axis = _rotate_vec(axis, cross, lead_deg)

            # Ball-end tip: surface contact at CC point, ball centre offset
            # by radius along normal, tip at ball centre minus radius along axis.
            #   ball_centre = point + r * n
            #   tip         = ball_centre - r * axis
            ball_centre = _add(point, n, ball_r)
            tip = _add(ball_centre, axis, -ball_r)

            cl_points.append({
                "x": tip[0],
                "y": tip[1],
                "z": tip[2],
                "i": axis[0],
                "j": axis[1],
                "k": axis[2],
            })

    if skipped:
        warnings.append(
            f"Skipped {skipped} CC point(s) where surface normal was undefined "
            "(degenerate UV region — e.g. pole of sphere or seam). "
            "Verify the toolpath visually before machining."
        )

    return {
        "cl_points": cl_points,
        "warnings": warnings,
        "skipped_uv": skipped,
    }
