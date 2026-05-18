"""
kerf_mold.mold
==============
Pure-Python injection-mold tooling data model and design functions.

Data models
-----------
Face           — a planar or curved face described by vertices + outward normal.
EjectorPin     — position, diameter, length.
GateLocation   — gate point, type (edge / pin / submarine / direct).
PartingLine    — ordered loop of 3-D points bounding the parting surface.
MoldDesign     — top-level assembly: core, cavity, parting surface, ejectors, gate.

Design functions
----------------
generate_parting_surface(parting_line, style) -> dict
    Extend a closed parting-line loop into a flat or ruled surface patch.
    Returns vertices + face indices of the triangulated surface patch.

check_moldability(mold_design, min_draft_deg, max_wall_ratio) -> dict
    Validate:
      1. minimum draft angle per face vs pull direction
      2. maximum wall thickness uniformity (max/min ratio <= max_wall_ratio)
      3. parting-surface continuity (normals within 5° of the pull direction)
    Returns ok + per-check results + list of failing faces.

draft_angle_per_face(faces, pull_dir) -> list[dict]
    Signed draft angle for each face (asin of normal · pull_hat).

All functions return plain dicts:
    success -> {"ok": True, ...fields..., "warnings": [...]}
    failure -> {"ok": False, "reason": "<human-readable>"}
Functions NEVER raise.

References
----------
Menges G., Michaeli W., Mohren P. "How to Make Injection Molds", 3rd ed.,
  Hanser 2001 — §4 Mold design; §7 Ejector systems; §8 Gating.
Rosato D.V., Rosato M.G. "Injection Molding Handbook", 3rd ed.,
  Kluwer Academic 2000 — §5 Parting line and surface; §6 Draft.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Face:
    """A single face of a mold core or cavity.

    Parameters
    ----------
    vertices : list of [x, y, z] points (at least 3, CCW winding outward)
    normal   : outward unit normal [nx, ny, nz]
    face_id  : optional label
    """
    vertices: List[List[float]]
    normal: List[float]
    face_id: str = ""

    def __post_init__(self) -> None:
        if len(self.vertices) < 3:
            raise ValueError(f"Face '{self.face_id}': need >= 3 vertices")
        n = self.normal
        if len(n) != 3:
            raise ValueError(f"Face '{self.face_id}': normal must be length-3")
        mag = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        if mag < 1e-12:
            raise ValueError(f"Face '{self.face_id}': degenerate normal (zero vector)")
        self.normal = [n[0] / mag, n[1] / mag, n[2] / mag]


@dataclass
class EjectorPin:
    """Cylindrical ejector pin.

    Parameters
    ----------
    position   : [x, y, z] tip location in the part coordinate system
    diameter_mm: pin diameter (mm)
    length_mm  : pin travel length (mm)
    """
    position: List[float]
    diameter_mm: float
    length_mm: float


@dataclass
class GateLocation:
    """Gate entry point and type.

    Parameters
    ----------
    point    : [x, y, z] gate centre
    gate_type: one of 'edge', 'pin', 'submarine', 'direct', 'hot_tip'
    """
    point: List[float]
    gate_type: str = "edge"

    _VALID_TYPES = frozenset({"edge", "pin", "submarine", "direct", "hot_tip"})

    def __post_init__(self) -> None:
        if self.gate_type not in self._VALID_TYPES:
            raise ValueError(
                f"gate_type must be one of {sorted(self._VALID_TYPES)!r}, "
                f"got {self.gate_type!r}"
            )


@dataclass
class PartingLine:
    """Ordered closed loop of 3-D points defining the parting boundary.

    Parameters
    ----------
    points : list of [x, y, z] in order; last point connects back to first.
    """
    points: List[List[float]]

    def __post_init__(self) -> None:
        if len(self.points) < 3:
            raise ValueError("PartingLine needs >= 3 points to form a closed loop")


@dataclass
class MoldDesign:
    """Top-level injection-mold design assembly.

    Parameters
    ----------
    core_faces    : faces belonging to the core half (A-side)
    cavity_faces  : faces belonging to the cavity half (B-side)
    parting_line  : closed parting-line loop
    pull_direction: mold opening direction [dx, dy, dz] (need not be unit)
    ejector_pins  : list of EjectorPin
    gate          : GateLocation
    part_name     : optional label
    wall_thicknesses_mm : sampled wall thickness values (mm) used for
                          uniformity checks; if empty, uniformity is skipped.
    """
    core_faces: List[Face]
    cavity_faces: List[Face]
    parting_line: PartingLine
    pull_direction: List[float]
    ejector_pins: List[EjectorPin] = field(default_factory=list)
    gate: Optional[GateLocation] = None
    part_name: str = ""
    wall_thicknesses_mm: List[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        pd = self.pull_direction
        if len(pd) != 3:
            raise ValueError("pull_direction must be a 3-element list")
        mag = math.sqrt(pd[0] ** 2 + pd[1] ** 2 + pd[2] ** 2)
        if mag < 1e-12:
            raise ValueError("pull_direction must be non-zero")
        self.pull_direction = [pd[0] / mag, pd[1] / mag, pd[2] / mag]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dot3(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross3(a: Sequence[float], b: Sequence[float]) -> List[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _norm3(v: Sequence[float]) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def _unit3(v: Sequence[float]) -> List[float]:
    m = _norm3(v)
    if m < 1e-15:
        return [0.0, 0.0, 1.0]
    return [v[0] / m, v[1] / m, v[2] / m]


# ---------------------------------------------------------------------------
# draft_angle_per_face
# ---------------------------------------------------------------------------

def draft_angle_per_face(
    faces: List[Face],
    pull_dir: Sequence[float],
) -> List[dict]:
    """Return signed draft angle (degrees) for each face.

    draft_deg = degrees(asin(n · pull_hat))

    Positive → face tilts away from the pull direction (good draft).
    Negative → undercut (face blocks ejection).
    Zero      → face is parallel to pull (no draft — may stick).

    Returns a list of dicts, one per face:
        face_id, draft_deg, is_undercut, normal
    Never raises; degenerate faces get draft_deg=NaN.
    """
    pull = _unit3(list(pull_dir))
    results = []
    for f in faces:
        n = f.normal
        cos_a = max(-1.0, min(1.0, _dot3(n, pull)))
        draft_deg = math.degrees(math.asin(cos_a))
        results.append({
            "face_id": f.face_id,
            "draft_deg": draft_deg,
            "is_undercut": draft_deg < 0.0,
            "normal": list(n),
        })
    return results


# ---------------------------------------------------------------------------
# generate_parting_surface
# ---------------------------------------------------------------------------

def generate_parting_surface(
    parting_line: PartingLine,
    style: str = "flat",
    pull_dir: Optional[Sequence[float]] = None,
    extrusion_depth_mm: float = 50.0,
) -> dict:
    """Extend a closed parting-line loop into a surface patch.

    Parameters
    ----------
    parting_line      : closed loop of 3-D points
    style             : 'flat' — project all points onto a best-fit plane and
                        triangulate; 'ruled' — extrude each edge outward along
                        pull_dir to depth extrusion_depth_mm.
    pull_dir          : required for 'ruled'; ignored for 'flat'.
    extrusion_depth_mm: extrusion depth for 'ruled' style (default 50 mm).

    Returns
    -------
    dict
        ok, style, vertices (list of [x,y,z]), faces (list of [i,j,k] triangles),
        area_mm2, is_flat (bool for 'flat' style), centroid, warnings.
    """
    try:
        pts = [list(map(float, p[:3])) for p in parting_line.points]
        n_pts = len(pts)
        if n_pts < 3:
            return {"ok": False, "reason": "parting_line needs >= 3 points"}

        warnings: List[str] = []

        if style == "flat":
            # Compute centroid
            cx = sum(p[0] for p in pts) / n_pts
            cy = sum(p[1] for p in pts) / n_pts
            cz = sum(p[2] for p in pts) / n_pts
            centroid = [cx, cy, cz]

            # Best-fit normal via Newell's method
            nx = ny = nz = 0.0
            for i in range(n_pts):
                pi = pts[i]
                pj = pts[(i + 1) % n_pts]
                nx += (pi[1] - pj[1]) * (pi[2] + pj[2])
                ny += (pi[2] - pj[2]) * (pi[0] + pj[0])
                nz += (pi[0] - pj[0]) * (pi[1] + pj[1])
            plane_normal = _unit3([nx, ny, nz])

            # Project points onto the plane through centroid
            proj_pts = []
            for p in pts:
                dx, dy, dz = p[0] - cx, p[1] - cy, p[2] - cz
                dist = dx * plane_normal[0] + dy * plane_normal[1] + dz * plane_normal[2]
                proj = [
                    p[0] - dist * plane_normal[0],
                    p[1] - dist * plane_normal[1],
                    p[2] - dist * plane_normal[2],
                ]
                proj_pts.append(proj)

            # Fan triangulation from centroid
            vertices = [centroid] + proj_pts
            faces_list = []
            for i in range(1, n_pts + 1):
                j = i % n_pts + 1
                faces_list.append([0, i, j])

            # Surface area (sum of triangle areas)
            area = 0.0
            for tri in faces_list:
                a, b, c = vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]
                ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]]
                ac = [c[0] - a[0], c[1] - a[1], c[2] - a[2]]
                cross = _cross3(ab, ac)
                area += 0.5 * _norm3(cross)

            # Check planarity: max deviation of projected pts from the plane
            max_dev = 0.0
            for p, q in zip(pts, proj_pts):
                dev = math.sqrt(
                    (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
                )
                if dev > max_dev:
                    max_dev = dev
            is_flat = max_dev < 1e-6  # flat to micrometer
            if not is_flat:
                warnings.append(
                    f"parting line is not planar: max deviation {max_dev:.6f} mm"
                )

            return {
                "ok": True,
                "style": "flat",
                "vertices": vertices,
                "faces": faces_list,
                "area_mm2": area,
                "is_flat": is_flat,
                "plane_normal": plane_normal,
                "centroid": centroid,
                "warnings": warnings,
            }

        elif style == "ruled":
            if pull_dir is None:
                return {"ok": False, "reason": "'ruled' style requires pull_dir"}
            pull = _unit3(list(pull_dir))
            depth = float(extrusion_depth_mm)
            if depth <= 0.0:
                return {"ok": False, "reason": "extrusion_depth_mm must be > 0"}

            # For each edge, produce a ruled quad (2 triangles)
            vertices: List[List[float]] = []
            faces_list = []
            area = 0.0
            for i in range(n_pts):
                a = pts[i]
                b = pts[(i + 1) % n_pts]
                # Extrude a and b outward along pull_dir by depth
                c = [a[0] + pull[0] * depth, a[1] + pull[1] * depth, a[2] + pull[2] * depth]
                d = [b[0] + pull[0] * depth, b[1] + pull[1] * depth, b[2] + pull[2] * depth]

                base = len(vertices)
                vertices.extend([a, b, c, d])
                # Quad a-b-d-c → triangles (a,b,d) and (a,d,c)
                faces_list.append([base, base + 1, base + 3])
                faces_list.append([base, base + 3, base + 2])

                # Triangle areas
                for tri_idx in [faces_list[-2], faces_list[-1]]:
                    v0, v1, v2 = vertices[tri_idx[0]], vertices[tri_idx[1]], vertices[tri_idx[2]]
                    ab_v = [v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2]]
                    ac_v = [v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2]]
                    cross = _cross3(ab_v, ac_v)
                    area += 0.5 * _norm3(cross)

            cx = sum(p[0] for p in pts) / n_pts
            cy = sum(p[1] for p in pts) / n_pts
            cz = sum(p[2] for p in pts) / n_pts
            centroid = [cx, cy, cz]

            return {
                "ok": True,
                "style": "ruled",
                "vertices": vertices,
                "faces": faces_list,
                "area_mm2": area,
                "is_flat": False,
                "centroid": centroid,
                "extrusion_depth_mm": depth,
                "pull_direction": list(pull),
                "warnings": warnings,
            }

        else:
            return {"ok": False, "reason": f"unknown style {style!r}; use 'flat' or 'ruled'"}

    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# check_moldability
# ---------------------------------------------------------------------------

def check_moldability(
    mold_design: MoldDesign,
    min_draft_deg: float = 1.0,
    max_wall_ratio: float = 3.0,
) -> dict:
    """Check injection-mold design for common moldability issues.

    Three checks are performed:

    1. Draft-angle check — every core and cavity face must have a draft angle
       >= min_draft_deg (default 1°).  Faces failing this are listed in
       failing_faces.

    2. Wall-thickness uniformity — if mold_design.wall_thicknesses_mm is
       provided, max/min <= max_wall_ratio (default 3.0).  Ratios above this
       risk sink marks or differential shrinkage.

    3. Parting-surface continuity — the parting line should lie in a plane
       consistent with the pull direction.  The best-fit plane normal must
       be within 5° of the pull direction.

    Parameters
    ----------
    mold_design    : MoldDesign instance
    min_draft_deg  : minimum acceptable draft angle in degrees (default 1°)
    max_wall_ratio : maximum acceptable wall thickness ratio (default 3.0)

    Returns
    -------
    dict
        ok, all_checks_pass (bool), checks (dict with per-check results),
        failing_faces (list), warnings.
    """
    try:
        pull = mold_design.pull_direction  # already unit-normalised
        warnings: List[str] = []
        checks: dict = {}

        # ── 1. Draft-angle check ─────────────────────────────────────────
        all_faces = [
            (f, "core") for f in mold_design.core_faces
        ] + [
            (f, "cavity") for f in mold_design.cavity_faces
        ]

        draft_results = []
        failing_faces = []
        for f, half in all_faces:
            n = f.normal
            cos_a = max(-1.0, min(1.0, _dot3(n, pull)))
            draft_deg = math.degrees(math.asin(cos_a))
            passes = draft_deg >= min_draft_deg
            entry = {
                "face_id": f.face_id,
                "half": half,
                "draft_deg": round(draft_deg, 4),
                "passes": passes,
            }
            draft_results.append(entry)
            if not passes:
                failing_faces.append(entry)

        draft_ok = len(failing_faces) == 0
        checks["draft_angle"] = {
            "ok": draft_ok,
            "min_draft_deg": min_draft_deg,
            "num_faces_checked": len(draft_results),
            "num_failing": len(failing_faces),
            "results": draft_results,
        }

        # ── 2. Wall-thickness uniformity ─────────────────────────────────
        t_vals = mold_design.wall_thicknesses_mm
        if t_vals:
            t_min = min(t_vals)
            t_max = max(t_vals)
            if t_min <= 0.0:
                checks["wall_uniformity"] = {
                    "ok": False,
                    "reason": "wall_thicknesses_mm contains non-positive value",
                }
            else:
                ratio = t_max / t_min
                wall_ok = ratio <= max_wall_ratio
                checks["wall_uniformity"] = {
                    "ok": wall_ok,
                    "t_min_mm": t_min,
                    "t_max_mm": t_max,
                    "ratio": round(ratio, 4),
                    "max_wall_ratio": max_wall_ratio,
                }
                if not wall_ok:
                    warnings.append(
                        f"wall thickness ratio {ratio:.2f} > {max_wall_ratio} "
                        f"(min={t_min:.2f} mm, max={t_max:.2f} mm)"
                    )
        else:
            checks["wall_uniformity"] = {
                "ok": True,
                "reason": "no wall_thicknesses_mm provided; check skipped",
            }

        # ── 3. Parting-surface continuity ─────────────────────────────────
        pl_pts = [list(map(float, p[:3])) for p in mold_design.parting_line.points]
        n_pl = len(pl_pts)
        if n_pl >= 3:
            cx = sum(p[0] for p in pl_pts) / n_pl
            cy = sum(p[1] for p in pl_pts) / n_pl
            cz = sum(p[2] for p in pl_pts) / n_pl
            # Newell normal
            nx = ny = nz = 0.0
            for i in range(n_pl):
                pi = pl_pts[i]
                pj = pl_pts[(i + 1) % n_pl]
                nx += (pi[1] - pj[1]) * (pi[2] + pj[2])
                ny += (pi[2] - pj[2]) * (pi[0] + pj[0])
                nz += (pi[0] - pj[0]) * (pi[1] + pj[1])
            plane_normal = _unit3([nx, ny, nz])
            # Angle between plane normal and pull direction
            cos_a = abs(max(-1.0, min(1.0, _dot3(plane_normal, pull))))
            angle_deg = math.degrees(math.acos(cos_a))
            # Continuity is OK if plane normal is within 5° of pull direction
            parting_ok = angle_deg <= 5.0
            checks["parting_continuity"] = {
                "ok": parting_ok,
                "plane_normal": plane_normal,
                "angle_to_pull_deg": round(angle_deg, 4),
                "threshold_deg": 5.0,
            }
            if not parting_ok:
                warnings.append(
                    f"parting surface normal deviates {angle_deg:.1f}° from pull "
                    f"direction (threshold 5°)"
                )
        else:
            checks["parting_continuity"] = {
                "ok": False,
                "reason": "parting_line has fewer than 3 points",
            }

        # ── overall ───────────────────────────────────────────────────────
        all_pass = all(v["ok"] for v in checks.values())

        return {
            "ok": True,
            "all_checks_pass": all_pass,
            "checks": checks,
            "failing_faces": failing_faces,
            "warnings": warnings,
        }

    except Exception as exc:
        return {"ok": False, "reason": str(exc)}
