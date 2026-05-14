import numpy as np
from geom.nurbs import NurbsCurve, NurbsSurface


def sweep1(profile: NurbsCurve, path: NurbsCurve, scale: float = 1.0) -> NurbsSurface:
    if profile.degree < 1 or path.degree < 1:
        raise ValueError("Profile and path must have degree >= 1")

    num_profile_pts = profile.num_control_points
    num_path_pts = path.num_control_points

    degree_u = profile.degree
    degree_v = path.degree

    control_points = np.zeros((num_profile_pts, num_path_pts, 3))

    for i in range(num_path_pts):
        path_pt = path.control_points[i]
        path_tangent = path.derivative(path.knots[path.degree + i]) if i < len(path.knots) - path.degree - 1 else path.control_points[min(i + 1, num_path_pts - 1)] - path.control_points[max(i - 1, 0)]

        if i > 0:
            path_tangent = path.control_points[i] - path.control_points[i - 1]
        else:
            path_tangent = path.control_points[1] - path.control_points[0]

        path_tangent = path_tangent / (np.linalg.norm(path_tangent) + 1e-10)

        Frenet_frame = compute_frenet_frame(path_tangent)

        for j in range(num_profile_pts):
            profile_pt = profile.control_points[j]
            scaled_pt = profile_pt * scale

            world_pt = path_pt + Frenet_frame @ scaled_pt
            control_points[j, i] = world_pt

    knots_u = profile.knots.copy()
    knots_v = path.knots.copy()

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=knots_v
    )


def compute_frenet_frame(tangent: np.ndarray) -> np.ndarray:
    if abs(tangent[2]) < 0.9:
        binormal = np.cross(tangent, np.array([0, 0, 1]))
    else:
        binormal = np.cross(tangent, np.array([0, 1, 0]))
    binormal = binormal / (np.linalg.norm(binormal) + 1e-10)

    normal = np.cross(binormal, tangent)
    normal = normal / (np.linalg.norm(normal) + 1e-10)

    frame = np.column_stack([tangent, normal, binormal])
    return frame


def sweep1_with_twist(profile: NurbsCurve, path: NurbsCurve,
                       scale: float = 1.0, twist: float = 0.0) -> NurbsSurface:
    if profile.degree < 1 or path.degree < 1:
        raise ValueError("Profile and path must have degree >= 1")

    num_profile_pts = profile.num_control_points
    num_path_pts = path.num_control_points

    degree_u = profile.degree
    degree_v = path.degree

    control_points = np.zeros((num_profile_pts, num_path_pts, 3))

    angle = twist

    for i in range(num_path_pts):
        path_pt = path.control_points[i]

        if i > 0:
            path_tangent = path.control_points[i] - path.control_points[i - 1]
        else:
            path_tangent = path.control_points[1] - path.control_points[0]

        path_tangent = path_tangent / (np.linalg.norm(path_tangent) + 1e-10)
        Frenet_frame = compute_frenet_frame(path_tangent)

        for j in range(num_profile_pts):
            profile_pt = profile.control_points[j]
            scaled_pt = profile_pt * scale

            rotation_matrix = rotation_matrix_3d(tangent=path_tangent, angle=angle)
            rotated_pt = rotation_matrix @ scaled_pt

            world_pt = path_pt + Frenet_frame @ rotated_pt
            control_points[j, i] = world_pt

        angle += twist / num_path_pts

    knots_u = profile.knots.copy()
    knots_v = path.knots.copy()

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=knots_v
    )


def rotation_matrix_3d(tangent: np.ndarray, angle: float) -> np.ndarray:
    K = np.array([
        [0, -tangent[2], tangent[1]],
        [tangent[2], 0, -tangent[0]],
        [-tangent[1], tangent[0], 0]
    ])
    R = np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * (K @ K)
    return R


def sweep1_variable_scale(profile: NurbsCurve, path: NurbsCurve,
                           scale_profile: callable = None) -> NurbsSurface:
    if profile.degree < 1 or path.degree < 1:
        raise ValueError("Profile and path must have degree >= 1")

    if scale_profile is None:
        scale_profile = lambda u: 1.0

    num_profile_pts = profile.num_control_points
    num_path_pts = path.num_control_points

    degree_u = profile.degree
    degree_v = path.degree

    control_points = np.zeros((num_profile_pts, num_path_pts, 3))

    path_knots = np.linspace(0, 1, num_path_pts)

    for i in range(num_path_pts):
        u = path_knots[i]
        path_pt = path.evaluate(u)

        if i > 0:
            path_tangent = path.evaluate(path_knots[min(i + 1, len(path_knots) - 1)]) - path.evaluate(path_knots[max(i - 1, 0)])
        else:
            path_tangent = path.evaluate(path_knots[1]) - path.evaluate(path_knots[0])

        path_tangent = path_tangent / (np.linalg.norm(path_tangent) + 1e-10)
        Frenet_frame = compute_frenet_frame(path_tangent)

        scale = scale_profile(u)

        for j in range(num_profile_pts):
            profile_pt = profile.control_points[j]
            scaled_pt = profile_pt * scale

            world_pt = path_pt + Frenet_frame @ scaled_pt
            control_points[j, i] = world_pt

    knots_u = profile.knots.copy()
    knots_v = path.knots.copy()

    return NurbsSurface(
        degree_u=degree_u,
        degree_v=degree_v,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=knots_v
    )


def profile_along_path(profile: NurbsCurve, path: NurbsCurve,
                       num_sections: int = 20) -> list:
    sections = []
    for i in range(num_sections):
        u = i / (num_sections - 1)
        path_pt = path.evaluate(u)

        if i > 0:
            path_tangent = path.evaluate((i + 1) / (num_sections - 1)) - path.evaluate((i - 1) / (num_sections - 1))
        elif i < num_sections - 1:
            path_tangent = path.evaluate((i + 1) / (num_sections - 1)) - path.evaluate(u)
        else:
            path_tangent = path.evaluate(u) - path.evaluate((i - 1) / (num_sections - 1))

        path_tangent = path_tangent / (np.linalg.norm(path_tangent) + 1e-10)
        Frenet_frame = compute_frenet_frame(path_tangent)

        section_pts = []
        for j in range(profile.num_control_points):
            world_pt = path_pt + Frenet_frame @ profile.control_points[j]
            section_pts.append(world_pt)
        sections.append(np.array(section_pts))

    return sections