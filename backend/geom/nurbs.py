import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class NurbsCurve:
    degree: int
    control_points: np.ndarray
    knots: np.ndarray

    def __post_init__(self):
        if self.control_points.ndim == 1:
            self.control_points = self.control_points.reshape(-1, 1)
        if self.knots.ndim != 1:
            raise ValueError("Knots must be 1D array")

    @property
    def num_control_points(self) -> int:
        return len(self.control_points)

    @property
    def num_knots(self) -> int:
        return len(self.knots)

    def evaluate(self, u: float) -> np.ndarray:
        return de_boor(self, u)

    def derivative(self, u: float, order: int = 1) -> np.ndarray:
        return curve_derivative(self, u, order)


@dataclass
class NurbsSurface:
    degree_u: int
    degree_v: int
    control_points: np.ndarray
    knots_u: np.ndarray
    knots_v: np.ndarray

    def __post_init__(self):
        if self.control_points.ndim != 3:
            raise ValueError("Control points must be 3D array (nu x nv x dim)")
        if self.knots_u.ndim != 1 or self.knots_v.ndim != 1:
            raise ValueError("Knots must be 1D arrays")

    @property
    def num_control_points_u(self) -> int:
        return self.control_points.shape[0]

    @property
    def num_control_points_v(self) -> int:
        return self.control_points.shape[1]

    def evaluate(self, u: float, v: float) -> np.ndarray:
        return surface_evaluate(self, u, v)


def find_span(n: int, degree: int, u: float, knots: np.ndarray) -> int:
    if u >= knots[n + 1]:
        return n
    if u <= knots[degree]:
        return degree

    low = degree
    high = n + 1
    mid = (low + high) // 2

    while u < knots[mid] or u >= knots[mid + 1]:
        if u < knots[mid]:
            high = mid
        else:
            low = mid
        mid = (low + high) // 2

    return mid


def basis_functions(i: int, u: float, degree: int, knots: np.ndarray) -> np.ndarray:
    n = len(knots) - degree - 1
    N = np.zeros(degree + 1)
    N[0] = 1.0

    for k in range(1, degree + 1):
        denom_prev = 0.0
        for j in range(k):
            denom = knots[i + j + 1] - knots[i + j]
            if denom != 0.0:
                val = N[j] / denom * (u - knots[i + j])
            else:
                val = 0.0
            N[j] = N[j + 1] if j + 1 <= k - 1 else 0.0
            N[j] += val

    return N[:degree + 1]


def de_boor(curve: NurbsCurve, u: float) -> np.ndarray:
    degree = curve.degree
    n = curve.num_control_points - 1
    p = degree

    span = find_span(n, p, u, curve.knots)
    U = curve.knots
    P = curve.control_points

    d = [P[span - p + j] for j in range(p + 1)]

    for k in range(1, p + 1):
        for j in range(p, k - 1, -1):
            idx_j = span - p + j
            idx_j_minus_k = span - p + j - k
            denom = U[idx_j + 1] - U[idx_j_minus_k]
            if denom == 0.0:
                coeff = 0.0
            else:
                coeff = (u - U[idx_j_minus_k]) / denom
            d[j] = (1 - coeff) * d[j - 1] + coeff * d[j]

    return d[p]


def curve_derivative(curve: NurbsCurve, u: float, order: int = 1) -> np.ndarray:
    degree = curve.degree
    n = curve.num_control_points - 1

    if order > degree:
        return np.zeros(curve.control_points.shape[1])

    span = find_span(n, degree, u, curve.knots)
    P = curve.control_points
    k = order

    PK = np.zeros((k + 1, degree + 1, curve.control_points.shape[1]))
    for j in range(degree + 1):
        PK[0, j] = P[span - degree + j]

    for k_idx in range(1, k + 1):
        for i in range(degree - k_idx + 1):
            denom = curve.knots[span + i + 1] - curve.knots[span + i]
            if denom != 0.0:
                factor = k_idx / denom
                PK[k_idx, i] = factor * (PK[k_idx - 1, i + 1] - PK[k_idx - 1, i])
            else:
                PK[k_idx, i] = np.zeros(curve.control_points.shape[1])

    deriv = PK[k, 0]
    norm = np.linalg.norm(deriv)
    if norm > 1e-10:
        deriv = deriv / norm
    return deriv


def surface_evaluate(surf: NurbsSurface, u: float, v: float) -> np.ndarray:
    span_u = find_span(surf.num_control_points_u - 1, surf.degree_u, u, surf.knots_u)
    span_v = find_span(surf.num_control_points_v - 1, surf.degree_v, v, surf.knots_v)

    Nu = basis_functions(span_u, u, surf.degree_u, surf.knots_u)
    Nv = basis_functions(span_v, v, surf.degree_v, surf.knots_v)

    result = np.zeros(surf.control_points.shape[2])
    for i in range(surf.degree_u + 1):
        for j in range(surf.degree_v + 1):
            idx_i = span_u - surf.degree_u + i
            idx_j = span_v - surf.degree_v + j
            result += Nu[i] * Nv[j] * surf.control_points[idx_i, idx_j]

    return result


def knot_insertion(curve: NurbsCurve, u: float, num_insertions: int = 1) -> NurbsCurve:
    degree = curve.degree
    n = curve.num_control_points - 1
    m = n + degree + 1
    P = curve.control_points
    U = curve.knots

    new_num_pts = n + num_insertions + 1
    new_P = np.zeros((new_num_pts, P.shape[1]))
    new_U = np.zeros(m + num_insertions + 1)

    k = find_span(n, degree, u, U)
    s = sum(1 for ui in U if abs(ui - u) < 1e-10)

    for j in range(k - degree + 1):
        new_P[j] = P[j]
    for j in range(k - s, n + 1):
        new_P[j + num_insertions] = P[j]
    for j in range(k - degree + 1):
        new_U[j] = U[j]
    for j in range(k - s, m + 1):
        new_U[j + num_insertions] = U[j]

    for i in range(1, num_insertions + 1):
        for j in range(k - degree + i, k - s + i + 1):
            alpha = (u - U[j - 1]) / (U[j + degree - i] - U[j - 1]) if (U[j + degree - i] - U[j - 1]) != 0 else 0
            new_P[j] = (1 - alpha) * new_P[j - 1] + alpha * new_P[j]

    return NurbsCurve(degree=degree, control_points=new_P, knots=new_U)


def degree_elevation(curve: NurbsCurve, new_degree: int) -> NurbsCurve:
    if new_degree <= curve.degree:
        return curve

    degree = curve.degree
    n = curve.num_control_points - 1
    P = curve.control_points
    U = curve.knots

    m = n + degree + 1
    new_n = n + (new_degree - degree)
    new_m = new_n + new_degree + 1

    num_new_knots = new_m + 1
    new_U = np.zeros(num_new_knots)
    new_P = np.zeros((new_n + 1, P.shape[1]))

    bezier_points = np.zeros((degree + 1, P.shape[1]))
    for i in range(degree + 1):
        bezier_points[i] = P[i]

    alpha = np.zeros(new_degree + 1)
    beta = np.zeros(new_degree + 1)

    for k in range(1, new_degree - degree + 1):
        for i in range(degree - k + 1):
            alpha[i] = i / (i + k)
            beta[i] = 1 - alpha[i]

        new_bez = np.zeros((degree - k + 2, P.shape[1]))
        new_bez[0] = bezier_points[0]
        new_bez[-1] = bezier_points[-1]

        for i in range(1, len(bezier_points)):
            new_bez[i] = alpha[i - 1] * bezier_points[i - 1] + beta[i - 1] * bezier_points[i]

        bezier_points = new_bez

    new_P[:len(bezier_points)] = bezier_points
    if len(bezier_points) < len(new_P):
        new_P[len(bezier_points):] = bezier_points[-1]

    for i in range(degree + 1):
        new_U[i] = U[0]
        new_U[-(i + 1)] = U[-1]

    if len(U) > 2 * (degree + 1):
        internal_knots = U[degree + 1:-(degree + 1)]
        step = 1.0 / (new_degree - degree + 1)
        for idx, t in enumerate(internal_knots):
            for k in range(1, new_degree - degree + 1):
                new_U[degree + k] = t

    return NurbsCurve(degree=new_degree, control_points=new_P, knots=new_U)


def curve_curve_intersection(curve1: NurbsCurve, curve2: NurbsCurve, 
                             num_samples: int = 100,
                             tolerance: float = 1e-6) -> list:
    u1_samples = np.linspace(curve1.knots[curve1.degree],
                              curve1.knots[-curve1.degree - 1],
                              num_samples)
    u2_samples = np.linspace(curve2.knots[curve2.degree],
                              curve2.knots[-curve2.degree - 1],
                              num_samples)

    intersections = []

    for i in range(len(u1_samples) - 1):
        p1 = curve1.evaluate(u1_samples[i])
        p2 = curve1.evaluate(u1_samples[i + 1])

        for j in range(len(u2_samples) - 1):
            q1 = curve2.evaluate(u2_samples[j])
            q2 = curve2.evaluate(u2_samples[j + 1])

            if segments_intersect(p1, p2, q1, q2, tolerance):
                u1_est = (u1_samples[i] + u1_samples[i + 1]) / 2
                u2_est = (u2_samples[j] + u2_samples[j + 1]) / 2

                for _ in range(5):
                    p_est = curve1.evaluate(u1_est)
                    q_est = curve2.evaluate(u2_est)
                    diff = p_est - q_est
                    if np.linalg.norm(diff) < tolerance:
                        break
                    dist1 = np.array([np.linalg.norm(p1 - q_est), np.linalg.norm(p2 - q_est)])
                    dist2 = np.array([np.linalg.norm(q1 - p_est), np.linalg.norm(q2 - p_est)])
                    if dist1[0] + dist1[1] < dist2[0] + dist2[1]:
                        u1_est = u1_samples[i] if np.linalg.norm(p1 - q_est) < np.linalg.norm(p2 - q_est) else u1_samples[i + 1]
                    else:
                        u2_est = u2_samples[j] if np.linalg.norm(q1 - p_est) < np.linalg.norm(q2 - p_est) else u2_samples[j + 1]

                intersections.append((u1_est, u2_est, (p_est + q_est) / 2))

    return intersections


def segments_intersect(p1: np.ndarray, p2: np.ndarray, 
                       q1: np.ndarray, q2: np.ndarray,
                       tolerance: float) -> bool:
    d1 = direction(q1, q2, p1)
    d2 = direction(q1, q2, p2)
    d3 = direction(p1, p2, q1)
    d4 = direction(p1, p2, q2)

    if d1 * d2 > 0 and d3 * d4 > 0:
        return False

    if abs(d1) < tolerance or abs(d2) < tolerance or abs(d3) < tolerance or abs(d4) < tolerance:
        return True

    return True


def direction(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    return np.cross(p2 - p1, p3 - p1)


def make_circle_nurbs(center: np.ndarray, radius: float, num_control_points: int = 9) -> NurbsCurve:
    if num_control_points < 3:
        num_control_points = 3
    if num_control_points % 2 == 0:
        num_control_points += 1

    degree = 2
    n = num_control_points - 1
    num_knots = n + degree + 1

    control_points = np.zeros((num_control_points, 3))
    knots = np.zeros(num_knots)

    angle_step = 2 * np.pi / (num_control_points - 1)
    for i in range(num_control_points):
        angle = i * angle_step
        control_points[i] = center + radius * np.array([np.cos(angle), np.sin(angle), 0])

    knots[0:degree + 1] = 0.0
    knots[-degree - 1:] = 1.0

    internal_knots = np.linspace(0, 1, num_knots - 2 * (degree + 1) + 2)[1:-1]
    knots[degree + 1:-degree - 1] = internal_knots

    return NurbsCurve(degree=degree, control_points=control_points, knots=knots)


def make_line_nurbs(p1: np.ndarray, p2: np.ndarray) -> NurbsCurve:
    degree = 1
    control_points = np.array([p1, p2])
    knots = np.array([0.0, 0.0, 1.0, 1.0])
    return NurbsCurve(degree=degree, control_points=control_points, knots=knots)


def nurbs_to_occt_curve(curve: NurbsCurve):
    try:
        from OCC.Core.Geom import Geom_BSplineCurve
        from OCC.Core.TColgp import TColgp_Array1OfPnt
        from OCC.Core.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger

        num_poles = curve.num_control_points
        degree = curve.degree
        num_knots = curve.num_knots

        poles = TColgp_Array1OfPnt(1, num_poles)
        for i, cp in enumerate(curve.control_points):
            poles.SetValue(i + 1, cp.tolist())

        knots = TColStd_Array1OfReal(1, num_knots)
        for i, k in enumerate(curve.knots):
            knots.SetValue(i + 1, k)

        mults = TColStd_Array1OfInteger(1, num_knots)
        for i in range(num_knots):
            mults.SetValue(i + 1, 1)

        return Geom_BSplineCurve(poles, knots, mults, degree, False)
    except ImportError:
        return None


def occt_curve_to_nurbs(occt_curve) -> NurbsCurve:
    try:
        from OCC.Core.Geom import Geom_BSplineCurve
        from OCC.Core.TColgp import TColgp_Array1OfPnt

        if not isinstance(occt_curve, Geom_BSplineCurve):
            raise ValueError("Input must be a Geom_BSplineCurve")

        degree = occt_curve.Degree()
        num_poles = occt_curve.NbPoles()
        num_knots = occt_curve.NbKnots()

        poles_array = occt_curve.Poles()
        poles = np.array([[p.X(), p.Y(), p.Z()] for p in poles_array])

        knots_array = occt_curve.Knots()
        knots = np.array([knots_array.Value(i + 1) for i in range(num_knots)])

        return NurbsCurve(degree=degree, control_points=poles, knots=knots)
    except ImportError:
        return None


def nurbs_to_occt_surface(surf: NurbsSurface):
    try:
        from OCC.Core.Geom import Geom_BSplineSurface
        from OCC.Core.TColgp import TColgp_Array2OfPnt
        from OCC.Core.TColStd import TColStd_Array1OfReal, TColStd_Array1OfInteger

        num_poles_u = surf.num_control_points_u
        num_poles_v = surf.num_control_points_v
        degree_u = surf.degree_u
        degree_v = surf.degree_v
        num_knots_u = len(surf.knots_u)
        num_knots_v = len(surf.knots_v)

        poles = TColgp_Array2OfPnt(1, num_poles_u, 1, num_poles_v)
        for i in range(num_poles_u):
            for j in range(num_poles_v):
                cp = surf.control_points[i, j]
                poles.SetValue(i + 1, j + 1, cp.tolist())

        knots_u = TColStd_Array1OfReal(1, num_knots_u)
        for i, k in enumerate(surf.knots_u):
            knots_u.SetValue(i + 1, k)

        knots_v = TColStd_Array1OfReal(1, num_knots_v)
        for i, k in enumerate(surf.knots_v):
            knots_v.SetValue(i + 1, k)

        return Geom_BSplineSurface(poles, knots_u, knots_v, degree_u, degree_v, False, False)
    except ImportError:
        return None


def occt_surface_to_nurbs(occt_surface) -> NurbsSurface:
    try:
        from OCC.Core.Geom import Geom_BSplineSurface

        if not isinstance(occt_surface, Geom_BSplineSurface):
            raise ValueError("Input must be a Geom_BSplineSurface")

        degree_u = occt_surface.UDegree()
        degree_v = occt_surface.VDegree()
        num_poles_u = occt_surface.NbUPoles()
        num_poles_v = occt_surface.NbVPoles()
        num_knots_u = occt_surface.NbUKnots()
        num_knots_v = occt_surface.NbVKnots()

        poles_array = occt_surface.Poles()
        poles = np.zeros((num_poles_u, num_poles_v, 3))
        for i in range(num_poles_u):
            for j in range(num_poles_v):
                p = poles_array.Value(i + 1, j + 1)
                poles[i, j] = [p.X(), p.Y(), p.Z()]

        knots_u = np.array([occt_surface.UKnot(i + 1) for i in range(num_knots_u)])
        knots_v = np.array([occt_surface.VKnot(i + 1) for i in range(num_knots_v)])

        return NurbsSurface(degree_u=degree_u, degree_v=degree_v,
                            control_points=poles, knots_u=knots_u, knots_v=knots_v)
    except ImportError:
        return None