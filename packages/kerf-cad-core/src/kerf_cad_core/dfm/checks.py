"""
kerf_cad_core.dfm.checks
========================
Pure-Python Design-for-Manufacture (DFM) geometric checks.

All functions accept plain Python objects (no OCC / Three.js dependency) so
they run in any environment and can be tested hermetically.

Geometry conventions
--------------------
mesh_or_solid : dict with keys:
    "vertices"  — list of [x, y, z] float lists
    "triangles" — list of [i, j, k] integer index triples (into vertices)
    Optional:
    "normals"   — list of [nx, ny, nz] per-triangle normals (auto-computed if absent)

edges : list of dicts { "a": [x,y,z], "b": [x,y,z], "angle_deg": float }
    Edge angle = interior angle at the edge (concave interior corner < 180°).

faces : list of dicts { "normal": [nx,ny,nz], "centroid": [cx,cy,cz], "area": float }

pull_direction : [dx, dy, dz] — tooling pull / demould axis (need not be unit length)

Returns
-------
Every function returns a list of issue dicts or a scalar — never raises.
Issue dict shape:
    {
      "kind":       str,            # e.g. "thin_wall"
      "position":   [x, y, z],     # world position of the problem centre
      "severity":   str,            # "error" | "warning" | "info"
      "value":      float,          # measured value (thickness, angle, score …)
      "suggestion": str,            # human-readable fix hint
    }

dfm_audit issues are additionally prioritised by severity (errors first).

References
----------
Boothroyd, G., Dewhurst, P., Knight, W. "Product Design for Manufacture and
Assembly", 3rd ed.
Kalpakjian, S. & Schmid, S.R. "Manufacturing Engineering & Technology", 7th ed.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

# numpy is used for fast mesh operations (normals, cross products, dot products).
# In constrained environments where numpy is absent the pure-Python fallback
# path below is used: all numpy-dependent functions (wall_thickness_min,
# no_draft_faces, undercut_regions, machinability_score) return safe empty
# results or degraded scalar values rather than crashing on import.
try:
    import numpy as np
    _NP_AVAILABLE = True
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]
    _NP_AVAILABLE = False

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PROCESSES = frozenset({"injection_moulding", "cnc_milling", "die_casting", "3d_printing"})

_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}


def _unit(v: Sequence[float]) -> "np.ndarray":
    a = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(a))
    return a / n if n > 1e-15 else np.array([0.0, 0.0, 1.0])


def _tri_normal(a: "np.ndarray", b: "np.ndarray", c: "np.ndarray") -> "np.ndarray":
    return _unit(np.cross(b - a, c - a))


def _tri_centroid(a: "np.ndarray", b: "np.ndarray", c: "np.ndarray") -> "np.ndarray":
    return (a + b + c) / 3.0


def _tri_area(a: "np.ndarray", b: "np.ndarray", c: "np.ndarray") -> float:
    return float(np.linalg.norm(np.cross(b - a, c - a))) / 2.0


def _issue(
    kind: str,
    position: Sequence[float],
    severity: str,
    value: float,
    suggestion: str,
) -> dict:
    return {
        "kind": kind,
        "position": [float(x) for x in position],
        "severity": severity,
        "value": float(value),
        "suggestion": suggestion,
    }


def _parse_mesh(mesh_or_solid: dict) -> "Optional[Tuple[np.ndarray, np.ndarray]]":
    """Return (vertices [N,3], triangles [M,3]) or None on bad input."""
    if not _NP_AVAILABLE:
        return None
    try:
        verts = np.asarray(mesh_or_solid["vertices"], dtype=float)
        tris = np.asarray(mesh_or_solid["triangles"], dtype=int)
        if verts.ndim != 2 or verts.shape[1] < 3:
            return None
        if tris.ndim != 2 or tris.shape[1] < 3:
            return None
        return verts[:, :3], tris[:, :3]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# wall_thickness_min
# ---------------------------------------------------------------------------

def wall_thickness_min(
    mesh_or_solid: dict,
    threshold_mm: float = 1.0,
) -> List[dict]:
    """Detect regions where estimated wall thickness is below *threshold_mm*.

    Strategy: for each mesh triangle, cast a ray from the centroid in the
    *inward* normal direction and find the closest opposing triangle.  The
    distance between the two centroids is used as a proxy for wall thickness.
    This is a fast, pure-Python approximation — good for flagging obvious
    problem regions.

    Parameters
    ----------
    mesh_or_solid : dict  with "vertices" and "triangles" lists
    threshold_mm  : float  minimum acceptable wall thickness in mm

    Returns
    -------
    list of issue dicts (kind="thin_wall")
    """
    parsed = _parse_mesh(mesh_or_solid)
    if parsed is None:
        return []

    verts, tris = parsed
    if len(tris) == 0:
        return []

    # Pre-compute per-triangle normals and centroids.
    tri_norms = []
    tri_cents = []
    for tri in tris:
        a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
        tri_norms.append(_tri_normal(a, b, c))
        tri_cents.append(_tri_centroid(a, b, c))

    tri_norms_arr = np.array(tri_norms)
    tri_cents_arr = np.array(tri_cents)

    issues: List[dict] = []
    threshold = float(threshold_mm)

    for i in range(len(tris)):
        origin = tri_cents_arr[i]
        inward = -tri_norms_arr[i]  # fire toward interior

        # Find all triangles whose centroid is roughly "across" the wall from
        # this triangle (normal roughly opposing) and close enough to be relevant.
        # We use a simple dot-product filter: opposing normals → dot(N_i, N_j) < 0.
        dots = tri_norms_arr.dot(tri_norms_arr[i])  # (M,) cos angles
        # Candidates: opposing orientation and not self
        candidates = np.where(dots < -0.3)[0]
        if len(candidates) == 0:
            continue

        # Distance from origin to each candidate centroid along inward ray.
        diffs = tri_cents_arr[candidates] - origin  # (K, 3)
        # Project diffs onto inward ray to get "depth" candidates.
        ray_dots = diffs.dot(inward)
        # Only consider candidates that are actually in the inward direction.
        fwd_mask = ray_dots > 1e-3
        if not np.any(fwd_mask):
            continue

        ray_dots_fwd = ray_dots[fwd_mask]
        # Perpendicular distance from ray.
        cands_fwd = diffs[fwd_mask]
        proj = np.outer(ray_dots_fwd, inward)
        perp = np.linalg.norm(cands_fwd - proj, axis=1)

        # Consider candidates within a cone radius proportional to threshold.
        cone_r = max(threshold * 2.0, 1.0)
        close_mask = perp < cone_r
        if not np.any(close_mask):
            continue

        min_depth = float(np.min(ray_dots_fwd[close_mask]))
        if min_depth < threshold:
            sev = "error" if min_depth < threshold * 0.5 else "warning"
            issues.append(_issue(
                kind="thin_wall",
                position=origin.tolist(),
                severity=sev,
                value=min_depth,
                suggestion=(
                    f"Wall thickness {min_depth:.2f} mm is below the minimum "
                    f"{threshold:.2f} mm. Increase section thickness or add ribs."
                ),
            ))

    return issues


# ---------------------------------------------------------------------------
# sharp_internal_corners
# ---------------------------------------------------------------------------

def sharp_internal_corners(
    edges: List[dict],
    threshold_deg: float = 30.0,
) -> List[dict]:
    """Flag concave (internal) edges whose interior angle is below *threshold_deg*.

    Parameters
    ----------
    edges         : list of { "a": [x,y,z], "b": [x,y,z], "angle_deg": float }
                    angle_deg is the INTERIOR angle at the edge (between adjacent
                    faces).  Convex exterior corners have angle > 180°; concave
                    interior corners have angle < 180°.  The threshold applies
                    to interior angles only (angle_deg < 180°).
    threshold_deg : float  maximum acceptable interior angle for flagging

    Returns
    -------
    list of issue dicts (kind="sharp_corner")
    """
    issues: List[dict] = []
    try:
        thresh = float(threshold_deg)
        for e in (edges or []):
            angle = float(e.get("angle_deg", 180.0))
            # Only flag concave / re-entrant edges (interior angle < 180°)
            if angle >= 180.0:
                continue
            if angle < thresh:
                a = e.get("a", [0.0, 0.0, 0.0])
                b = e.get("b", [0.0, 0.0, 0.0])
                midpoint = [(a[k] + b[k]) / 2.0 for k in range(3)]
                sev = "error" if angle < thresh * 0.5 else "warning"
                issues.append(_issue(
                    kind="sharp_corner",
                    position=midpoint,
                    severity=sev,
                    value=angle,
                    suggestion=(
                        f"Internal corner angle {angle:.1f}° is below {thresh:.1f}°. "
                        "Add a fillet radius (≥ tool radius for CNC; ≥ 0.5 mm for moulding) "
                        "to reduce stress concentration and ease tooling."
                    ),
                ))
    except Exception:
        pass
    return issues


# ---------------------------------------------------------------------------
# no_draft_faces
# ---------------------------------------------------------------------------

def no_draft_faces(
    faces: List[dict],
    pull_direction: Sequence[float],
    required_draft_deg: float = 0.5,
) -> List[dict]:
    """Flag faces that have insufficient draft angle relative to the pull direction.

    A face with a normal perpendicular to the pull direction (wall parallel to
    pull) has 0° draft.  Faces opposing the pull (undercuts) are flagged
    separately by `undercut_regions`.

    Parameters
    ----------
    faces             : list of { "normal": [nx,ny,nz], "centroid": [cx,cy,cz],
                                   "area": float }
    pull_direction    : [dx, dy, dz]  demould / tool pull axis
    required_draft_deg: float  minimum acceptable draft angle in degrees

    Returns
    -------
    list of issue dicts (kind="no_draft")
    """
    issues: List[dict] = []
    if not _NP_AVAILABLE:
        return issues
    try:
        pull = _unit(pull_direction)
        req = float(required_draft_deg)
        for face in (faces or []):
            normal = _unit(face.get("normal", [0.0, 0.0, 1.0]))
            centroid = face.get("centroid", [0.0, 0.0, 0.0])
            # Draft angle = asin(|dot(normal, pull)|) — 0° when normal ⊥ pull.
            cos_a = float(np.clip(np.dot(normal, pull), -1.0, 1.0))
            draft_deg = math.degrees(math.asin(abs(cos_a)))
            # Only flag insufficient positive draft (not undercuts).
            if cos_a < 0:
                continue  # undercut — handled elsewhere
            if draft_deg < req:
                sev = "error" if draft_deg < req * 0.5 else "warning"
                issues.append(_issue(
                    kind="no_draft",
                    position=centroid,
                    severity=sev,
                    value=draft_deg,
                    suggestion=(
                        f"Face has only {draft_deg:.2f}° draft (need ≥ {req:.1f}°). "
                        "Add draft to allow part ejection / demoulding without damage."
                    ),
                ))
    except Exception:
        pass
    return issues


# ---------------------------------------------------------------------------
# undercut_regions
# ---------------------------------------------------------------------------

def undercut_regions(
    faces: List[dict],
    pull_direction: Sequence[float],
) -> List[dict]:
    """Flag faces that form undercuts relative to the pull direction.

    An undercut face has a negative draft angle: its normal *opposes* the pull
    vector (dot < 0), meaning straight-pull tooling cannot release the part.

    Parameters
    ----------
    faces          : list of { "normal": [nx,ny,nz], "centroid": [cx,cy,cz],
                                "area": float }
    pull_direction : [dx, dy, dz]

    Returns
    -------
    list of issue dicts (kind="undercut")
    """
    issues: List[dict] = []
    if not _NP_AVAILABLE:
        return issues
    try:
        pull = _unit(pull_direction)
        for face in (faces or []):
            normal = _unit(face.get("normal", [0.0, 0.0, 1.0]))
            centroid = face.get("centroid", [0.0, 0.0, 0.0])
            cos_a = float(np.dot(normal, pull))
            if cos_a >= 0:
                continue
            draft_deg = math.degrees(math.asin(abs(cos_a)))  # magnitude
            sev = "error" if draft_deg > 10.0 else "warning"
            issues.append(_issue(
                kind="undercut",
                position=centroid,
                severity=sev,
                value=-draft_deg,  # negative to signal undercut
                suggestion=(
                    f"Face is an undercut ({draft_deg:.1f}° into pull direction). "
                    "Redesign with side-action cores, split the part, or re-orient the pull axis."
                ),
            ))
    except Exception:
        pass
    return issues


# ---------------------------------------------------------------------------
# machinability_score
# ---------------------------------------------------------------------------

def machinability_score(part: dict) -> float:
    """Estimate a machinability score [0.0–1.0] for a part.

    Higher = easier to machine.  The score aggregates:
    - Face count (more faces → more setups)
    - Presence of deep pockets (depth / width ratio)
    - Aspect ratio of bounding box
    - Thin-wall penalty

    Parameters
    ----------
    part : dict with optional keys:
        "faces"          — list of face dicts (as above)
        "bounding_box"   — { "min": [x,y,z], "max": [x,y,z] }
        "deep_pockets"   — list of { "depth": float, "width": float }
        "thin_wall_count"— int

    Returns
    -------
    float in [0.0, 1.0]
    """
    try:
        score = 1.0

        faces = part.get("faces") or []
        face_count = len(faces)
        # Penalise very high face counts (complex geometry).
        if face_count > 100:
            score -= 0.1
        if face_count > 500:
            score -= 0.15

        # Bounding-box aspect ratio penalty.
        bb = part.get("bounding_box")
        if bb and "min" in bb and "max" in bb:
            if _NP_AVAILABLE:
                lo = np.asarray(bb["min"], dtype=float)
                hi = np.asarray(bb["max"], dtype=float)
                dims = np.abs(hi - lo)
                dims = np.where(dims < 1e-9, 1e-9, dims)
                aspect = float(np.max(dims) / np.min(dims))
            else:
                lo = bb["min"]
                hi = bb["max"]
                dims = [max(abs(hi[k] - lo[k]), 1e-9) for k in range(3)]
                aspect = max(dims) / min(dims)
            if aspect > 10:
                score -= 0.15
            elif aspect > 5:
                score -= 0.05

        # Deep pocket penalty.
        pockets = part.get("deep_pockets") or []
        for pocket in pockets:
            depth = float(pocket.get("depth", 0.0))
            width = max(float(pocket.get("width", 1.0)), 1e-9)
            ratio = depth / width
            if ratio > 4.0:
                score -= 0.20
            elif ratio > 2.0:
                score -= 0.10

        # Thin-wall penalty.
        thin = int(part.get("thin_wall_count", 0))
        score -= min(0.30, thin * 0.05)

        return float(max(0.0, min(1.0, score)))
    except Exception:
        return 0.5


# ---------------------------------------------------------------------------
# dfm_audit
# ---------------------------------------------------------------------------

_PROCESS_DEFAULTS: Dict[str, dict] = {
    "injection_moulding": {
        "wall_threshold_mm": 1.5,
        "draft_deg": 1.5,
        "corner_threshold_deg": 45.0,
    },
    "die_casting": {
        "wall_threshold_mm": 1.0,
        "draft_deg": 1.0,
        "corner_threshold_deg": 30.0,
    },
    "cnc_milling": {
        "wall_threshold_mm": 0.5,
        "draft_deg": 0.0,      # draft not required for CNC
        "corner_threshold_deg": 30.0,
    },
    "3d_printing": {
        "wall_threshold_mm": 0.8,
        "draft_deg": 0.0,      # no draft for additive
        "corner_threshold_deg": 20.0,
    },
}


def dfm_audit(
    part: dict,
    process: str = "cnc_milling",
    pull_direction: Optional[Sequence[float]] = None,
) -> dict:
    """Run the full DFM check suite for a chosen manufacturing process.

    Parameters
    ----------
    part          : dict with optional keys "mesh", "edges", "faces",
                    "bounding_box", "deep_pockets", "thin_wall_count"
    process       : one of "injection_moulding", "cnc_milling",
                    "die_casting", "3d_printing"  (default "cnc_milling")
    pull_direction: [dx, dy, dz] — required for injection_moulding /
                    die_casting; defaults to [0, 0, 1] if omitted.

    Returns
    -------
    dict:
      {
        "ok":      bool,   # True when no errors found
        "process": str,
        "score":   float,  # machinability score [0, 1]
        "issues":  list,   # prioritised: errors first, then warnings, then info
        "summary": str,
      }
    """
    try:
        proc = str(process).lower()
        defaults = _PROCESS_DEFAULTS.get(proc, _PROCESS_DEFAULTS["cnc_milling"])

        pull = list(pull_direction) if pull_direction is not None else [0.0, 0.0, 1.0]

        issues: List[dict] = []

        # 1. Thin-wall check.
        mesh = part.get("mesh")
        if mesh is not None:
            issues.extend(wall_thickness_min(mesh, defaults["wall_threshold_mm"]))

        # 2. Sharp internal corners.
        edges = part.get("edges")
        if edges is not None:
            issues.extend(sharp_internal_corners(edges, defaults["corner_threshold_deg"]))

        # 3. Draft / undercut checks (process-dependent).
        faces = part.get("faces")
        if faces is not None and proc in {"injection_moulding", "die_casting"}:
            issues.extend(no_draft_faces(faces, pull, defaults["draft_deg"]))
            issues.extend(undercut_regions(faces, pull))

        # 4. Machinability score.
        score = machinability_score(part)

        # Prioritise: errors first, then warnings, then info.
        issues.sort(key=lambda i: _SEVERITY_RANK.get(i.get("severity", "info"), 2))

        error_count = sum(1 for i in issues if i.get("severity") == "error")
        warn_count = sum(1 for i in issues if i.get("severity") == "warning")

        ok = error_count == 0
        summary = (
            f"{proc}: {error_count} error(s), {warn_count} warning(s). "
            f"Machinability score: {score:.2f}/1.0."
        )

        return {
            "ok": ok,
            "process": proc,
            "score": score,
            "issues": issues,
            "summary": summary,
        }
    except Exception as exc:
        return {
            "ok": False,
            "process": str(process),
            "score": 0.0,
            "issues": [],
            "summary": f"audit failed: {exc}",
        }


# ---------------------------------------------------------------------------
# LLM tool registration
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    import json as _json
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False


if _REGISTRY_AVAILABLE:

    _dfm_audit_spec = ToolSpec(
        name="dfm_audit",
        description=(
            "Run a Design-for-Manufacture (DFM) audit on a part for a chosen process. "
            "Flags thin walls, sharp internal corners, undrafted faces, undercuts, and "
            "returns a machinability score. Issues are prioritised (errors first).\n\n"
            "Returns: {ok, process, score, issues, summary}. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "part": {
                    "type": "object",
                    "description": (
                        "Part geometry dict. Keys: "
                        "mesh ({vertices, triangles}), "
                        "edges ([{a,b,angle_deg}]), "
                        "faces ([{normal,centroid,area}]), "
                        "bounding_box ({min,max}), "
                        "deep_pockets ([{depth,width}]), "
                        "thin_wall_count (int)."
                    ),
                },
                "process": {
                    "type": "string",
                    "enum": ["injection_moulding", "die_casting", "cnc_milling", "3d_printing"],
                    "description": "Manufacturing process to check against.",
                },
                "pull_direction": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "3-element pull / demould direction (default [0,0,1]).",
                },
            },
            "required": ["part"],
        },
    )

    @register(_dfm_audit_spec)
    async def run_dfm_audit(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        part = a.get("part")
        if not isinstance(part, dict):
            return err_payload("part must be a dict", "BAD_ARGS")

        proc = a.get("process", "cnc_milling")
        pull = a.get("pull_direction")

        result = dfm_audit(part, proc, pull)
        return ok_payload(result)

    _wall_thickness_spec = ToolSpec(
        name="dfm_wall_thickness",
        description=(
            "Check a mesh for regions where estimated wall thickness is below "
            "a threshold. Returns a list of {position, thickness, severity} issues.\n\n"
            "Returns: list of issue dicts. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "mesh": {
                    "type": "object",
                    "description": "Mesh dict with 'vertices' and 'triangles' lists.",
                },
                "threshold_mm": {
                    "type": "number",
                    "description": "Minimum acceptable wall thickness in mm (default 1.0).",
                },
            },
            "required": ["mesh"],
        },
    )

    @register(_wall_thickness_spec)
    async def run_dfm_wall_thickness(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        mesh = a.get("mesh")
        if not isinstance(mesh, dict):
            return err_payload("mesh must be a dict with vertices and triangles", "BAD_ARGS")

        threshold = float(a.get("threshold_mm", 1.0))
        issues = wall_thickness_min(mesh, threshold)
        return ok_payload({"issues": issues, "count": len(issues)})
