"""
kerf_cad_core.reverse_engineering.pipeline — Top-level reverse-engineering pipeline.

Public API
----------
recognize(pts, ...)                 → FeatureTree + metadata
sample_feature_tree(tree)           → re-sampled point cloud
hausdorff_distance(a, b)            → float (max directed Hausdorff, point clouds)
max_point_to_surface_distance(pts, tree) → float (max exact point-to-surface dist)

Round-trip oracle
-----------------
For noise-free synthetic inputs the **max point-to-surface distance** between
the original cloud and the recovered feature tree's surfaces should be ≤ 1e-3
(in the same units as the input).

``max_point_to_surface_distance(pts, tree)`` computes the exact distance from
each input point to its closest fitted surface (using the analytic distance
functions from ``scan.fit``), then returns the maximum.  This is the correct
oracle for the T-332 v1 DoD:

    "re-evaluate the feature tree → Hausdorff ≤ 1e-3 vs the original surface"

because a grid re-sampling of the surface at any finite density will have
finite grid spacing, so a cloud ↔ re-sampled-cloud Hausdorff is always bounded
below by half the sample spacing — which can exceed 1e-3 even for a perfect fit.

The ``hausdorff_distance`` helper is retained for general use (e.g. comparing
two clouds at equal density).

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any

from kerf_cad_core.reverse_engineering.segmentation import sequential_ransac
from kerf_cad_core.reverse_engineering.feature_map import segments_to_feature_tree

# Type alias
FeatureTree = list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def recognize(
    pts: list[list[float]],
    primitives: list[str] | None = None,
    threshold: float = 0.01,
    min_inliers: int = 6,
    min_inlier_fraction: float = 0.05,
    seed: int = 42,
) -> dict[str, Any]:
    """Run the full reverse-engineering pipeline on a point cloud.

    Steps:
    1. Sequential RANSAC segmentation (plane / cylinder / sphere / cone).
    2. Map each segment to a feature node (feature_map).
    3. Return feature tree + metadata.

    Parameters
    ----------
    pts:
        Input point cloud [[x, y, z], ...].
    primitives:
        Ordered list of primitive types to try.  Default order:
        ``["plane", "cylinder", "sphere", "cone"]``.
    threshold:
        RANSAC inlier distance threshold (model units).
    min_inliers:
        Absolute minimum inlier count for a segment.
    min_inlier_fraction:
        Minimum fraction of the remaining cloud a fit must claim.
    seed:
        Random seed for RANSAC reproducibility.

    Returns
    -------
    dict with keys:
        ok              bool
        feature_tree    FeatureTree (list of feature node dicts)
        segments        list of raw segment dicts (for debugging)
        unassigned_pts  list of unassigned [x,y,z] points
        total_count     int
        segment_count   int
        unassigned_count int
    """
    seg_result = sequential_ransac(
        pts,
        primitives=primitives,
        threshold=threshold,
        min_inliers=min_inliers,
        min_inlier_fraction=min_inlier_fraction,
        seed=seed,
    )

    if not seg_result.get("ok"):
        return {
            "ok": False,
            "reason": seg_result.get("reason", "segmentation failed"),
        }

    segments = seg_result["segments"]
    feature_tree = segments_to_feature_tree(segments)

    return {
        "ok": True,
        "feature_tree": feature_tree,
        "segments": segments,
        "unassigned_pts": seg_result["unassigned"],
        "total_count": seg_result["total_count"],
        "segment_count": seg_result["segment_count"],
        "unassigned_count": len(seg_result["unassigned"]),
    }


# ---------------------------------------------------------------------------
# Re-sampling: feature tree → point cloud
# ---------------------------------------------------------------------------

def _sample_sphere(
    centre: list[float],
    radius: float,
    n: int = 200,
) -> list[list[float]]:
    """Sample n points uniformly on a sphere surface (golden angle)."""
    pts = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    cx, cy, cz = centre
    for i in range(n):
        y_f = 1.0 - (i / max(n - 1, 1)) * 2.0
        rad = math.sqrt(max(0.0, 1.0 - y_f * y_f))
        theta = golden * i
        pts.append([
            cx + math.cos(theta) * rad * radius,
            cy + y_f * radius,
            cz + math.sin(theta) * rad * radius,
        ])
    return pts


def _sample_cylinder(
    axis: list[float],
    axis_point: list[float],
    radius: float,
    height: float,
    n: int = 200,
) -> list[list[float]]:
    """Sample n points uniformly on a cylinder lateral surface."""
    from kerf_cad_core.scan.fit import _normalise, _cross, _dot, _add, _scale

    ax = _normalise(axis)
    ref = [1.0, 0.0, 0.0]
    if abs(ax[0]) > 0.9:
        ref = [0.0, 1.0, 0.0]
    u = _normalise(_cross(ax, ref))
    v = _cross(ax, u)

    # Split n across theta and height
    n_theta = max(int(math.sqrt(n)), 4)
    n_h = max(n // n_theta, 2)
    pts = []
    for ih in range(n_h):
        h = -height / 2.0 + ih * height / max(n_h - 1, 1)
        for it in range(n_theta):
            theta = 2.0 * math.pi * it / n_theta
            p = _add(
                _add(axis_point, _scale(ax, h)),
                _add(_scale(u, radius * math.cos(theta)),
                     _scale(v, radius * math.sin(theta))),
            )
            pts.append(p)
    return pts


def _sample_plane(
    normal: list[float],
    d: float,
    centre: list[float],
    extent: float,
    n: int = 200,
) -> list[list[float]]:
    """Sample n points on a finite plane patch (square of side 2*extent)."""
    from kerf_cad_core.scan.fit import _normalise, _cross, _add, _scale

    norm = _normalise(normal)
    ref = [1.0, 0.0, 0.0]
    if abs(norm[0]) > 0.9:
        ref = [0.0, 1.0, 0.0]
    u = _normalise(_cross(norm, ref))
    v = _cross(norm, u)

    side = max(extent, 0.01)
    sq = int(math.sqrt(n)) + 1
    pts = []
    for i in range(sq):
        for j in range(sq):
            su = -side + 2.0 * side * i / max(sq - 1, 1)
            sv = -side + 2.0 * side * j / max(sq - 1, 1)
            pts.append(_add(centre, _add(_scale(u, su), _scale(v, sv))))
            if len(pts) >= n:
                return pts
    return pts


def _sample_cone(
    apex: list[float],
    axis: list[float],
    half_angle: float,
    height: float,
    n: int = 200,
) -> list[list[float]]:
    """Sample n points on a cone lateral surface."""
    from kerf_cad_core.scan.fit import _normalise, _cross, _add, _scale

    ax = _normalise(axis)
    ref = [1.0, 0.0, 0.0]
    if abs(ax[0]) > 0.9:
        ref = [0.0, 1.0, 0.0]
    u = _normalise(_cross(ax, ref))
    v = _cross(ax, u)

    tan_ha = math.tan(half_angle)
    n_theta = max(int(math.sqrt(n)), 4)
    n_h = max(n // n_theta, 2)
    pts = []
    for ih in range(n_h):
        h = ih * height / max(n_h - 1, 1)
        r = h * tan_ha
        for it in range(n_theta):
            theta = 2.0 * math.pi * it / n_theta
            p = _add(
                _add(apex, _scale(ax, h)),
                _add(_scale(u, r * math.cos(theta)),
                     _scale(v, r * math.sin(theta))),
            )
            pts.append(p)
    return pts


def sample_feature_tree(
    feature_tree: FeatureTree,
    n_per_feature: int = 200,
) -> list[list[float]]:
    """Re-sample each feature in the tree to produce a point cloud.

    Parameters
    ----------
    feature_tree:
        List of feature node dicts as returned by ``recognize()``.
    n_per_feature:
        Approximate number of sample points per feature.

    Returns
    -------
    Merged point cloud (list of [x, y, z]).
    """
    all_pts: list[list[float]] = []

    for node in feature_tree:
        op = node.get("op", "")
        if op == "extrude":
            normal = node["normal"]
            d = node["d"]
            centre = node["centre"]
            extent = node.get("extent", 1.0) or 1.0
            all_pts.extend(_sample_plane(normal, d, centre, extent, n_per_feature))

        elif op == "revolve":
            all_pts.extend(_sample_cylinder(
                node["axis"], node["axis_point"],
                node["radius"], node.get("height", 1.0) or 1.0,
                n_per_feature,
            ))

        elif op == "sphere":
            all_pts.extend(_sample_sphere(
                node["centre"], node["radius"], n_per_feature,
            ))

        elif op == "cone":
            import math as _math
            all_pts.extend(_sample_cone(
                node["apex"], node["axis"],
                _math.radians(node["half_angle_deg"]),
                node.get("height", 1.0) or 1.0,
                n_per_feature,
            ))

    return all_pts


# ---------------------------------------------------------------------------
# Hausdorff distance (symmetric, exact O(N²))
# ---------------------------------------------------------------------------

def _directed_hausdorff(a: list[list[float]], b: list[list[float]]) -> float:
    """max_{p in a} min_{q in b} dist(p, q)"""
    if not a or not b:
        return float("inf")
    max_min = 0.0
    for p in a:
        px, py, pz = p
        min_d = float("inf")
        for q in b:
            dx = px - q[0]; dy = py - q[1]; dz = pz - q[2]
            d2 = dx*dx + dy*dy + dz*dz
            if d2 < min_d:
                min_d = d2
        max_min = max(max_min, min_d)
    return math.sqrt(max_min)


def hausdorff_distance(
    a: list[list[float]],
    b: list[list[float]],
) -> float:
    """Symmetric Hausdorff distance between two point clouds.

    Returns max(h(A, B), h(B, A)) where h is the directed Hausdorff.
    O(|A|·|B|) — suitable for clouds up to ~1 000 points.
    """
    return max(
        _directed_hausdorff(a, b),
        _directed_hausdorff(b, a),
    )


# ---------------------------------------------------------------------------
# Point-to-surface distance oracle (for round-trip testing)
# ---------------------------------------------------------------------------

def _dist_point_to_node(p: list[float], node: dict[str, Any]) -> float:
    """Exact analytic distance from point p to the surface described by node."""
    import math as _math
    from kerf_cad_core.scan.fit import (
        _dot, _sub, _scale, _norm, _normalise,
        _dist_to_plane, _dist_to_sphere, _dist_to_cylinder,
    )
    op = node.get("op", "")

    if op == "extrude":
        return _dist_to_plane(p, node["normal"], node["d"])

    elif op == "revolve":
        return _dist_to_cylinder(p, node["axis"], node["axis_point"], node["radius"])

    elif op == "sphere":
        return _dist_to_sphere(p, node["centre"], node["radius"])

    elif op == "cone":
        from kerf_cad_core.reverse_engineering.segmentation import _dist_to_cone
        half_angle = _math.radians(node["half_angle_deg"])
        return _dist_to_cone(p, node["apex"], node["axis"], half_angle)

    return float("inf")


def max_point_to_surface_distance(
    pts: list[list[float]],
    feature_tree: FeatureTree,
) -> float:
    """For each point find its nearest fitted surface; return the maximum distance.

    This is the correct round-trip oracle: it measures how well the recovered
    feature tree explains the original point cloud, independent of re-sampling
    density.

    Returns
    -------
    float — max over all pts of min over all feature nodes of distance(p, surface).
    Returns ``float("inf")`` if feature_tree is empty.
    """
    if not feature_tree:
        return float("inf")
    if not pts:
        return 0.0

    max_d = 0.0
    for p in pts:
        min_d = min(_dist_point_to_node(p, node) for node in feature_tree)
        if min_d > max_d:
            max_d = min_d
    return max_d
