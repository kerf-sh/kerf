import numpy as np
from geom.nurbs import NurbsCurve, NurbsSurface


def sweep2(profile: NurbsCurve, rail1: NurbsCurve, rail2: NurbsCurve) -> NurbsSurface:
    if profile.degree < 1 or rail1.degree < 1 or rail2.degree < 1:
        raise ValueError("Profile and rails must have degree >= 1")

    if rail1.num_control_points != rail2.num_control_points:
        raise ValueError("Rail1 and Rail2 must have same number of control points")

    num_profile_pts = profile.num_control_points
    num_path_pts = rail1.num_control_points

    degree_u = profile.degree
    degree_v = max(rail1.degree, rail2.degree)

    control_points = np.zeros((num_profile_pts, num_path_pts, 3))

    for i in range(num_path_pts):
        p1 = rail1.control_points[i]
        p2 = rail2.control_points[i]

        tangent1 = rail1.derivative(rail1.knots[rail1.degree + i]) if i < len(rail1.knots) - rail1.degree - 1 else p1 - rail1.control_points[max(i - 1, 0)]
        tangent2 = rail2.derivative(rail2.knots[rail2.degree + i]) if i < len(rail2.knots) - rail2.degree - 1 else p2 - rail2.control_points[max(i - 1, 0)]

        if i > 0:
            tangent1 = p1 - rail1.control_points[i - 1]
            tangent2 = p2 - rail2.control_points[i - 1]
        else:
            tangent1 = rail1.control_points[1] - p1 if len(rail1.control_points) > 1 else np.array([1, 0, 0])
            tangent2 = rail2.control_points[1] - p2 if len(rail2.control_points) > 1 else np.array([1, 0, 0])

        tangent1 = tangent1 / (np.linalg.norm(tangent1) + 1e-10)
        tangent2 = tangent2 / (np.linalg.norm(tangent2) + 1e-10)

        rail_direction = p2 - p1
        rail_direction = rail_direction / (np.linalg.norm(rail_direction) + 1e-10)

        frame = compute_adaptive_frame(rail_direction, tangent1, tangent2)

        for j in range(num_profile_pts):
            profile_pt = profile.control_points[j]

            t = j / (num_profile_pts - 1) if num_profile_pts > 1 else 0.5
            base_pt = (1 - t) * p1 + t * p2

            offset = frame @ profile_pt

            world_pt = base_pt + offset
            control_points[j, i] = world_pt

    knots_u = profile.knots.copy()
    knots_v = merge_knot_vectors([rail1.knots, rail2.knots])

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=knots_v
    )


def compute_adaptive_frame(rail_direction: np.ndarray,
                           tangent1: np.ndarray,
                           tangent2: np.ndarray) -> np.ndarray:
    reference = np.array([0, 0, 1])
    if abs(np.dot(rail_direction, reference)) > 0.9:
        reference = np.array([0, 1, 0])

    normal = np.cross(rail_direction, reference)
    normal = normal / (np.linalg.norm(normal) + 1e-10)

    binormal = np.cross(rail_direction, normal)
    binormal = binormal / (np.linalg.norm(binormal) + 1e-10)

    frame = np.column_stack([rail_direction, normal, binormal])
    return frame


def merge_knot_vectors(knot_vectors: list) -> np.ndarray:
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


def sweep2_with_scaling(profile: NurbsCurve, rail1: NurbsCurve, rail2: NurbsCurve,
                         scale1: float = 1.0, scale2: float = 1.0) -> NurbsSurface:
    if rail1.num_control_points != rail2.num_control_points:
        raise ValueError("Rail1 and Rail2 must have same number of control points")

    num_profile_pts = profile.num_control_points
    num_path_pts = rail1.num_control_points

    degree_u = profile.degree
    degree_v = max(rail1.degree, rail2.degree)

    control_points = np.zeros((num_profile_pts, num_path_pts, 3))

    for i in range(num_path_pts):
        p1 = rail1.control_points[i]
        p2 = rail2.control_points[i]

        if i > 0:
            tangent1 = p1 - rail1.control_points[i - 1]
            tangent2 = p2 - rail2.control_points[i - 1]
        else:
            tangent1 = rail1.control_points[1] - p1 if len(rail1.control_points) > 1 else np.array([1, 0, 0])
            tangent2 = rail2.control_points[1] - p2 if len(rail2.control_points) > 1 else np.array([1, 0, 0])

        tangent1 = tangent1 / (np.linalg.norm(tangent1) + 1e-10)
        tangent2 = tangent2 / (np.linalg.norm(tangent2) + 1e-10)

        rail_direction = p2 - p1
        rail_length = np.linalg.norm(rail_direction)
        if rail_length > 1e-10:
            rail_direction = rail_direction / rail_length
        else:
            rail_direction = np.array([1, 0, 0])

        frame = compute_adaptive_frame(rail_direction, tangent1, tangent2)

        for j in range(num_profile_pts):
            profile_pt = profile.control_points[j]

            t = j / (num_profile_pts - 1) if num_profile_pts > 1 else 0.5
            scale = (1 - t) * scale1 + t * scale2

            base_pt = (1 - t) * p1 + t * p2

            scaled_profile_pt = profile_pt * scale
            offset = frame @ scaled_profile_pt

            world_pt = base_pt + offset
            control_points[j, i] = world_pt

    knots_u = profile.knots.copy()
    knots_v = merge_knot_vectors([rail1.knots, rail2.knots])

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=knots_v
    )


def sweep2_with_twist(profile: NurbsCurve, rail1: NurbsCurve, rail2: NurbsCurve,
                      twist_per_unit: float = 0.0) -> NurbsSurface:
    if rail1.num_control_points != rail2.num_control_points:
        raise ValueError("Rail1 and Rail2 must have same number of control points")

    num_profile_pts = profile.num_control_points
    num_path_pts = rail1.num_control_points

    degree_u = profile.degree
    degree_v = max(rail1.degree, rail2.degree)

    control_points = np.zeros((num_profile_pts, num_path_pts, 3))

    accumulated_twist = 0.0
    prev_p1 = rail1.control_points[0]
    prev_p2 = rail2.control_points[0]

    for i in range(num_path_pts):
        p1 = rail1.control_points[i]
        p2 = rail2.control_points[i]

        if i > 0:
            path_segment = (p1 + p2) / 2 - (prev_p1 + prev_p2) / 2
            segment_length = np.linalg.norm(path_segment)
            accumulated_twist += twist_per_unit * segment_length

        if i > 0:
            tangent1 = p1 - rail1.control_points[i - 1]
            tangent2 = p2 - rail2.control_points[i - 1]
        else:
            tangent1 = rail1.control_points[1] - p1 if len(rail1.control_points) > 1 else np.array([1, 0, 0])
            tangent2 = rail2.control_points[1] - p2 if len(rail2.control_points) > 1 else np.array([1, 0, 0])

        tangent1 = tangent1 / (np.linalg.norm(tangent1) + 1e-10)
        tangent2 = tangent2 / (np.linalg.norm(tangent2) + 1e-10)

        rail_direction = p2 - p1
        rail_length = np.linalg.norm(rail_direction)
        if rail_length > 1e-10:
            rail_direction = rail_direction / rail_length
        else:
            rail_direction = np.array([1, 0, 0])

        frame = compute_adaptive_frame(rail_direction, tangent1, tangent2)

        twist_rotation = rotation_matrix_3d(rail_direction, accumulated_twist)
        frame = frame @ twist_rotation

        for j in range(num_profile_pts):
            profile_pt = profile.control_points[j]

            t = j / (num_profile_pts - 1) if num_profile_pts > 1 else 0.5
            base_pt = (1 - t) * p1 + t * p2

            offset = frame @ profile_pt

            world_pt = base_pt + offset
            control_points[j, i] = world_pt

        prev_p1 = p1
        prev_p2 = p2

    knots_u = profile.knots.copy()
    knots_v = merge_knot_vectors([rail1.knots, rail2.knots])

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=knots_v
    )


def rotation_matrix_3d(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = axis / (np.linalg.norm(axis) + 1e-10)
    c = np.cos(angle)
    s = np.sin(angle)
    t = 1 - c

    return np.array([
        [t * axis[0] * axis[0] + c, t * axis[0] * axis[1] - s * axis[2], t * axis[0] * axis[2] + s * axis[1]],
        [t * axis[0] * axis[1] + s * axis[2], t * axis[1] * axis[1] + c, t * axis[1] * axis[2] - s * axis[0]],
        [t * axis[0] * axis[2] - s * axis[1], t * axis[1] * axis[2] + s * axis[0], t * axis[2] * axis[2] + c]
    ])


def check_rail_compatibility(rail1: NurbsCurve, rail2: NurbsCurve) -> bool:
    if rail1.degree != rail2.degree:
        return False
    if abs(rail1.knots[-1] - rail2.knots[-1]) > 1e-6:
        return False
    if abs(rail1.knots[0] - rail2.knots[0]) > 1e-6:
        return False
    return True


def normalize_rails(rail1: NurbsCurve, rail2: NurbsCurve) -> tuple:
    from geom.nurbs import knot_insertion

    if not check_rail_compatibility(rail1, rail2):
        max_knots = max(len(rail1.knots), len(rail2.knots))
        target_knots = np.linspace(0, 1, max_knots)

        normalized1 = rail1
        normalized2 = rail2

        return normalized1, normalized2

    return rail1, rail2