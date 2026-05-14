import numpy as np
from geom.nurbs import NurbsCurve, NurbsSurface


def blend_srf(surf1: NurbsSurface, surf2: NurbsSurface,
              curve1: NurbsCurve, curve2: NurbsCurve,
              blend_dist: float) -> NurbsSurface:
    if blend_dist <= 0:
        raise ValueError("blend_dist must be positive")

    num_cp_u1 = surf1.num_control_points_u
    num_cp_v1 = surf1.num_control_points_v
    num_cp_u2 = surf2.num_control_points_u
    num_cp_v2 = surf2.num_control_points_v

    max_cp_u = max(num_cp_u1, num_cp_u2)
    max_cp_v = max(num_cp_v1, num_cp_v2) + 2
    dim = surf1.control_points.shape[2]

    degree_u = max(surf1.degree_u, surf2.degree_u)
    degree_v = max(surf1.degree_v, surf2.degree_v) + 1

    control_points = np.zeros((max_cp_u, max_cp_v, dim))

    for i in range(num_cp_u1):
        for j in range(num_cp_v1):
            control_points[i, j] = surf1.control_points[i, j]

    for i in range(num_cp_u2):
        for j in range(num_cp_v2):
            control_points[i, max_cp_v - num_cp_v2 + j] = surf2.control_points[i, j]

    blend_region_size = max(2, int(blend_dist * 5))

    for i in range(max_cp_u):
        for j in range(blend_region_size):
            t = j / blend_region_size if blend_region_size > 1 else 0.5

            if j < num_cp_v1:
                p1 = surf1.control_points[i % num_cp_u1, num_cp_v1 - 1 - j]

            if j < num_cp_v2:
                p2 = surf2.control_points[i % num_cp_u2, j]

            if j < num_cp_v1 and j < num_cp_v2:
                blend_factor = smooth_blend(t)
                control_points[i, num_cp_v1 + j] = (1 - blend_factor) * p1 + blend_factor * p2

    knots_u1 = surf1.knots_u
    knots_u2 = surf2.knots_u
    knots_v1 = surf1.knots_v
    knots_v2 = surf2.knots_v

    knots_u = merge_knot_vectors([knots_u1, knots_u2])
    knots_v = np.concatenate([knots_v1, np.array([knots_v1[-1] + (knots_v2[1] - knots_v2[0]) * i for i in range(1, 4)])])

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=knots_v
    )


def smooth_blend(t: float) -> float:
    return t * t * (3 - 2 * t)


def blend_srf_g1(surf1: NurbsSurface, surf2: NurbsSurface,
                 edge1_idx: int, edge2_idx: int,
                 blend_dist: float,
                 continuity: str = "G1") -> NurbsSurface:
    if blend_dist <= 0:
        raise ValueError("blend_dist must be positive")

    num_cp_u1 = surf1.num_control_points_u
    num_cp_v1 = surf1.num_control_points_v
    num_cp_u2 = surf2.num_control_points_u
    num_cp_v2 = surf2.num_control_points_v

    dim = surf1.control_points.shape[2]

    blend_rows = max(3, int(blend_dist * 5))

    new_num_cp_v = num_cp_v1 + blend_rows + num_cp_v2

    degree_u = max(surf1.degree_u, surf2.degree_u)
    degree_v = max(surf1.degree_v, surf2.degree_v)

    control_points = np.zeros((max(num_cp_u1, num_cp_u2), new_num_cp_v, dim))

    for i in range(num_cp_u1):
        for j in range(num_cp_v1):
            control_points[i, j] = surf1.control_points[i, j]

    for i in range(num_cp_u2):
        for j in range(num_cp_v2):
            control_points[i, new_num_cp_v - num_cp_v2 + j] = surf2.control_points[i, j]

    if edge1_idx >= 0 and edge1_idx < num_cp_v1:
        edge1_pts = surf1.control_points[:, edge1_idx]

    if edge2_idx >= 0 and edge2_idx < num_cp_v2:
        edge2_pts = surf2.control_points[:, edge2_idx]

    if continuity in ["G1", "G2"]:
        blend_start = num_cp_v1
        blend_end = new_num_cp_v - num_cp_v2

        for i in range(max(num_cp_u1, num_cp_u2)):
            prev_pt = surf1.control_points[i % num_cp_u1, edge1_idx] if edge1_idx < num_cp_v1 else None
            next_pt = surf2.control_points[i % num_cp_u2, edge2_idx] if edge2_idx < num_cp_v2 else None

            if prev_pt is not None and next_pt is not None:
                for j in range(blend_rows):
                    t = (j + 1) / (blend_rows + 1)

                    if continuity == "G1":
                        blend_pt = g1_blend_point(prev_pt, next_pt, t, blend_dist)
                    else:
                        blend_pt = g2_blend_point(prev_pt, next_pt, t, blend_dist)

                    control_points[i, blend_start + j] = blend_pt

    knots_v1 = surf1.knots_v
    knots_v2 = surf2.knots_v

    knots_v = np.linspace(0, 1, new_num_cp_v + degree_v + 1)

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=surf1.knots_u,
        knots_v=knots_v
    )


def g1_blend_point(p1: np.ndarray, p2: np.ndarray, t: float, blend_dist: float) -> np.ndarray:
    blend_t = smooth_blend(t)
    return (1 - blend_t) * p1 + blend_t * p2


def g2_blend_point(p1: np.ndarray, p2: np.ndarray, t: float, blend_dist: float) -> np.ndarray:
    blend_t = smooth_blend(t)

    pt = (1 - blend_t) * p1 + blend_t * p2

    curvature_adjustment = t * (1 - t) * blend_dist * 0.1
    adjustment = np.array([curvature_adjustment, curvature_adjustment, curvature_adjustment])

    return pt + adjustment


def blend_srf_with_curves(surf1: NurbsSurface, surf2: NurbsSurface,
                           blend_curve1: NurbsCurve, blend_curve2: NurbsCurve,
                           blend_dist: float) -> NurbsSurface:
    if blend_dist <= 0:
        raise ValueError("blend_dist must be positive")

    num_cp_u1 = surf1.num_control_points_u
    num_cp_v1 = surf1.num_control_points_v
    num_cp_u2 = surf2.num_control_points_u
    num_cp_v2 = surf2.num_control_points_v

    num_blend_pts = max(blend_curve1.num_control_points, blend_curve2.num_control_points)

    new_num_cp_v = num_cp_v1 + num_blend_pts + num_cp_v2
    new_num_cp_u = max(num_cp_u1, num_cp_u2)

    dim = surf1.control_points.shape[2]

    degree_u = max(surf1.degree_u, surf2.degree_u)
    degree_v = max(surf1.degree_v, surf2.degree_v, blend_curve1.degree, blend_curve2.degree)

    control_points = np.zeros((new_num_cp_u, new_num_cp_v, dim))

    for i in range(num_cp_u1):
        for j in range(num_cp_v1):
            control_points[i, j] = surf1.control_points[i, j]

    for i in range(num_cp_u2):
        for j in range(num_cp_v2):
            control_points[i, new_num_cp_v - num_cp_v2 + j] = surf2.control_points[i, j]

    for j in range(num_blend_pts):
        t = j / (num_blend_pts - 1) if num_blend_pts > 1 else 0.5

        blend_pt1 = blend_curve1.evaluate(t) if j < blend_curve1.num_control_points else blend_curve1.control_points[-1]
        blend_pt2 = blend_curve2.evaluate(t) if j < blend_curve2.num_control_points else blend_curve2.control_points[-1]

        for i in range(new_num_cp_u):
            control_points[i, num_cp_v1 + j] = (blend_pt1 + blend_pt2) / 2

    knots_v = np.linspace(0, 1, new_num_cp_v + degree_v + 1)

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=merge_knot_vectors([surf1.knots_u, surf2.knots_u]),
        knots_v=knots_v
    )


def merge_knot_vectors(knot_vectors: list) -> np.ndarray:
    if not knot_vectors:
        return np.array([])

    max_length = max(len(kv) for kv in knot_vectors)
    merged = np.zeros(max_length)
    counts = np.zeros(max_length)

    for kv in knot_vectors:
        for i, k in enumerate(kv):
            merged[i] += k
            counts[i] += 1

    for i in range(max_length):
        if counts[i] > 0:
            merged[i] /= counts[i]

    return merged


def validate_surface_blend(surf1: NurbsSurface, surf2: NurbsSurface,
                           curve1: NurbsCurve, curve2: NurbsCurve) -> tuple:
    if surf1.control_points.shape[2] != surf2.control_points.shape[2]:
        return False, "Surface dimensions don't match"

    if curve1.control_points.shape[1] != surf1.control_points.shape[2]:
        return False, "Curve1 dimension doesn't match surface"

    if curve2.control_points.shape[1] != surf2.control_points.shape[2]:
        return False, "Curve2 dimension doesn't match surface"

    return True, "Valid"


def compute_blend_surface_isocurves(surf1: NurbsSurface, surf2: NurbsSurface,
                                     num_isocurves: int = 10) -> list:
    isocurves = []

    for i in range(num_isocurves):
        t = i / (num_isocurves - 1) if num_isocurves > 1 else 0.5

        isocurve_pts = []

        for j in range(surf1.num_control_points_u):
            p1 = surf1.control_points[j, -1]
            p2 = surf2.control_points[j, 0]
            pt = (1 - t) * p1 + t * p2
            isocurve_pts.append(pt)

        isocurves.append(np.array(isocurve_pts))

    return isocurves


def blend_srf_fillet(surf1: NurbsSurface, surf2: NurbsSurface,
                     radius: float, num_segments: int = 10) -> NurbsSurface:
    if radius <= 0:
        raise ValueError("radius must be positive")

    num_cp_u1 = surf1.num_control_points_u
    num_cp_v1 = surf1.num_control_points_v
    num_cp_u2 = surf2.num_control_points_u
    num_cp_v2 = surf2.num_control_points_v

    num_fillet_pts = num_segments

    new_num_cp_v = num_cp_v1 + num_fillet_pts + num_cp_v2

    dim = surf1.control_points.shape[2]

    degree_u = max(surf1.degree_u, surf2.degree_u)
    degree_v = max(surf1.degree_v, surf2.degree_v)

    control_points = np.zeros((max(num_cp_u1, num_cp_u2), new_num_cp_v, dim))

    for i in range(num_cp_u1):
        for j in range(num_cp_v1):
            control_points[i, j] = surf1.control_points[i, j]

    for i in range(num_cp_u2):
        for j in range(num_cp_v2):
            control_points[i, new_num_cp_v - num_cp_v2 + j] = surf2.control_points[i, j]

    for i in range(max(num_cp_u1, num_cp_u2)):
        p1 = surf1.control_points[i % num_cp_u1, -1]
        p2 = surf2.control_points[i % num_cp_u2, 0]

        fillet_center = (p1 + p2) / 2 + np.array([0, 0, radius])

        for j in range(num_fillet_pts):
            angle = np.pi * (j + 1) / (num_fillet_pts + 1)

            fillet_pt = fillet_center + radius * np.array([
                np.cos(angle),
                np.sin(angle),
                0
            ])

            control_points[i, num_cp_v1 + j] = fillet_pt

    knots_v = np.linspace(0, 1, new_num_cp_v + degree_v + 1)

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=merge_knot_vectors([surf1.knots_u, surf2.knots_u]),
        knots_v=knots_v
    )