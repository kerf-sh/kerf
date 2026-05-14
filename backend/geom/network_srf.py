import numpy as np
from geom.nurbs import NurbsCurve, NurbsSurface


def network_srf(curves: list[NurbsCurve], degree_u: int = 3) -> NurbsSurface:
    if len(curves) < 2:
        raise ValueError("At least 2 curves are required for skinning")

    for i, curve in enumerate(curves):
        if curve.control_points.shape[1] != curves[0].control_points.shape[1]:
            raise ValueError(f"Curve {i} has incompatible dimension")

    num_curves = len(curves)
    num_profile_pts = curves[0].num_control_points
    dim = curves[0].control_points.shape[1]

    aligned_curves = align_knot_vectors(curves)

    degree_v = max(c.degree for c in aligned_curves)

    common_knots_v = aligned_curves[0].knots.copy()

    control_points = np.zeros((num_curves, num_profile_pts, dim))

    for i, curve in enumerate(aligned_curves):
        control_points[i, :, :] = curve.control_points

    knots_u = compute_interpolation_knots(num_curves, degree_u)
    knots_u = ensure_valid_knot_vector(knots_u, degree_u, num_curves)

    final_surface = NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=common_knots_v
    )

    return final_surface


def align_knot_vectors(curves: list[NurbsCurve]) -> list[NurbsCurve]:
    from geom.nurbs import knot_insertion

    max_num_knots = max(len(c.knots) for c in curves)
    target_knots = np.linspace(0, 1, max_num_knots)

    aligned = []
    for curve in curves:
        if len(curve.knots) < max_num_knots - 1:
            num_insertions = max_num_knots - len(curve.knots)
            u_values = np.linspace(curve.knots[curve.degree],
                                    curve.knots[-curve.degree - 1],
                                    num_insertions + 2)[1:-1]
            aligned_curve = curve
            for u in u_values:
                aligned_curve = knot_insertion(aligned_curve, u)
            aligned.append(aligned_curve)
        else:
            aligned.append(curve)

    return aligned


def compute_interpolation_knots(num_points: int, degree: int) -> np.ndarray:
    num_knots = num_points + degree + 1

    if num_points <= degree:
        knots = np.zeros(num_knots)
        knots[:degree + 1] = 0.0
        knots[-degree - 1:] = 1.0
        return knots

    knots = np.zeros(num_knots)

    knots[:degree + 1] = 0.0
    knots[-degree - 1:] = 1.0

    internal_count = num_knots - 2 * (degree + 1)
    if internal_count > 0:
        internal_knots = np.linspace(0, 1, internal_count + 2)[1:-1]
        knots[degree + 1:-degree - 1] = internal_knots

    return knots


def ensure_valid_knot_vector(knots: np.ndarray, degree: int, num_control_points: int) -> np.ndarray:
    expected_length = num_control_points + degree + 1

    if len(knots) < expected_length:
        additional = np.linspace(knots[-1], 1.0, expected_length - len(knots) + 1)[1:]
        knots = np.concatenate([knots, additional])

    return knots


def network_srf_with_compatibility(curves: list[NurbsCurve],
                                    degree_u: int = 3,
                                    continuity: str = "C1") -> NurbsSurface:
    if len(curves) < 2:
        raise ValueError("At least 2 curves are required")

    if continuity == "C0":
        return network_srf(curves, degree_u)

    aligned_curves = align_knot_vectors(curves)

    if continuity == "C1":
        aligned_curves = compute_tangent_constraints(aligned_curves)

    return network_srf(aligned_curves, degree_u)


def compute_tangent_constraints(curves: list[NurbsCurve]) -> list[NurbsCurve]:
    if len(curves) < 2:
        return curves

    constrained = [curves[0]]

    for i in range(1, len(curves)):
        curve = curves[i]
        prev_curve = curves[i - 1]

        t = i / (len(curves) - 1)

        constrained.append(curve)

    return constrained


def network_srf_global(curves: list[NurbsCurve],
                       degree_u: int = 3,
                       degree_v: int = 3) -> NurbsSurface:
    if len(curves) < 2:
        raise ValueError("At least 2 curves are required")

    num_curves = len(curves)
    num_profile_pts = curves[0].num_control_points
    dim = curves[0].control_points.shape[1]

    for curve in curves:
        if curve.num_control_points != num_profile_pts:
            raise ValueError("All curves must have the same number of control points")

    aligned_curves = align_knot_vectors(curves)

    common_knots_v = aligned_curves[0].knots.copy()

    control_points = np.zeros((num_curves, num_profile_pts, dim))
    for i, curve in enumerate(aligned_curves):
        control_points[i, :, :] = curve.control_points

    if degree_u > degree_v:
        for i in range(num_curves):
            for j in range(num_profile_pts):
                for k in range(dim):
                    control_points[i, j, k] = interpolate_along_v(
                        [curves[m].control_points[j, k] for m in range(num_curves)],
                        i / (num_curves - 1) if num_curves > 1 else 0.5,
                        degree_v
                    )

    knots_u = compute_interpolation_knots(num_curves, degree_u)
    knots_u = ensure_valid_knot_vector(knots_u, degree_u, num_curves)

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=common_knots_v
    )


def interpolate_along_v(values: list, t: float, degree: int) -> float:
    n = len(values) - 1
    if n == 0:
        return values[0]

    for k in range(1, n + 1):
        for i in range(n, k - 1, -1):
            alpha = t if i < n else 1.0
            values[i] = alpha * values[i] + (1 - alpha) * values[i - 1]

    return values[n]


def network_srf_from_cross_sections(u_curves: list[NurbsCurve],
                                    v_curves: list[NurbsCurve],
                                    degree_u: int = 3,
                                    degree_v: int = 3) -> NurbsSurface:
    if len(u_curves) < 2 or len(v_curves) < 2:
        raise ValueError("At least 2 curves in each direction required")

    u_surface = network_srf(u_curves, degree_v)
    v_surface = network_srf(v_curves, degree_u)

    num_u = u_surface.num_control_points_u
    num_v = u_surface.num_control_points_v
    dim = u_surface.control_points.shape[2]

    control_points = np.zeros((num_u, num_v, dim))

    for i in range(num_u):
        for j in range(num_v):
            control_points[i, j] = (u_surface.control_points[i, j] +
                                     v_surface.control_points[i, j]) / 2

    merged_knots_u = merge_knot_vectors([u_surface.knots_u, v_surface.knots_u])
    merged_knots_v = merge_knot_vectors([u_surface.knots_v, v_surface.knots_v])

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=merged_knots_u,
        knots_v=merged_knots_v
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


def validate_curves_for_skinning(curves: list[NurbsCurve]) -> tuple:
    if len(curves) < 2:
        return False, "Need at least 2 curves"

    num_pts = curves[0].num_control_points
    dim = curves[0].control_points.shape[1]

    for i, curve in enumerate(curves):
        if curve.num_control_points != num_pts:
            return False, f"Curve {i} has {curve.num_control_points} control points, expected {num_pts}"
        if curve.control_points.shape[1] != dim:
            return False, f"Curve {i} has dimension {curve.control_points.shape[1]}, expected {dim}"

    return True, "Valid"


def approximate_network_srf(u_curves: list[NurbsCurve],
                           v_curves: list[NurbsCurve],
                           degree_u: int = 3,
                           degree_v: int = 3) -> NurbsSurface:
    if not u_curves or not v_curves:
        raise ValueError("Both u_curves and v_curves must be non-empty")

    num_u = len(u_curves)
    num_v = len(v_curves)

    u_aligned = align_knot_vectors(u_curves)
    v_aligned = align_knot_vectors(v_curves)

    dim = u_aligned[0].control_points.shape[1]

    num_cp_u = num_u
    num_cp_v = u_aligned[0].num_control_points

    control_points = np.zeros((num_cp_u, num_cp_v, dim))

    for i in range(num_cp_u):
        control_points[i, :, :] = u_aligned[i].control_points

    knots_u = compute_interpolation_knots(num_cp_u, degree_u)
    knots_u = ensure_valid_knot_vector(knots_u, degree_u, num_cp_u)

    knots_v = v_aligned[0].knots.copy()

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=knots_v
    )