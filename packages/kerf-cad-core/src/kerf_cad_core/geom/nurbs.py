import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class NurbsCurve:
    degree: int
    control_points: np.ndarray
    knots: np.ndarray
    # Optional per-control-point weights for rational NURBS.  ``None`` means a
    # non-rational (polynomial) B-spline (all weights = 1).  Control points are
    # always stored in *Cartesian* (un-projected) form so existing callers that
    # read ``control_points`` as plain XYZ keep working unchanged; the weight
    # vector is kept separate.
    weights: Optional[np.ndarray] = None

    def __post_init__(self):
        if self.control_points.ndim == 1:
            self.control_points = self.control_points.reshape(-1, 1)
        if self.knots.ndim != 1:
            raise ValueError("Knots must be 1D array")
        if self.weights is not None:
            self.weights = np.asarray(self.weights, dtype=float).ravel()
            if self.weights.shape[0] != self.control_points.shape[0]:
                raise ValueError("weights length must match control_points")

    @property
    def num_control_points(self) -> int:
        return len(self.control_points)

    @property
    def num_knots(self) -> int:
        return len(self.knots)

    @property
    def is_rational(self) -> bool:
        return self.weights is not None and not np.allclose(self.weights, 1.0)

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
    # Optional (nu x nv) weight grid for rational NURBS surfaces.  ``None``
    # means non-rational.  Control points stay Cartesian (see NurbsCurve).
    weights: Optional[np.ndarray] = None

    def __post_init__(self):
        if self.control_points.ndim != 3:
            raise ValueError("Control points must be 3D array (nu x nv x dim)")
        if self.knots_u.ndim != 1 or self.knots_v.ndim != 1:
            raise ValueError("Knots must be 1D arrays")
        if self.weights is not None:
            self.weights = np.asarray(self.weights, dtype=float)
            if self.weights.shape != self.control_points.shape[:2]:
                raise ValueError("weights shape must be (nu, nv)")

    @property
    def num_control_points_u(self) -> int:
        return self.control_points.shape[0]

    @property
    def num_control_points_v(self) -> int:
        return self.control_points.shape[1]

    @property
    def is_rational(self) -> bool:
        return self.weights is not None and not np.allclose(self.weights, 1.0)

    def evaluate(self, u: float, v: float) -> np.ndarray:
        return surface_evaluate(self, u, v)

    def derivative(self, u: float, v: float, ku: int = 1, kv: int = 0) -> np.ndarray:
        return surface_derivative(self, u, v, ku, kv)


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


# ---------------------------------------------------------------------------
# GK-01 — Correct, unified Cox-de Boor B-spline core
# ---------------------------------------------------------------------------
#
# The previous ``basis_functions`` used an index-shifting recurrence that does
# not implement the triangular Cox-de Boor relation correctly (only N[0] is
# trustworthy for degree > 1).  This was documented in
# ``geom/intersection.py`` which carries its own correct ``_basis_fns``.
# We now host the single correct implementation here; every evaluator (curve,
# surface, rational) and the analytic derivative routines delegate to it.


def _basis_funcs(span: int, u: float, degree: int, knots: np.ndarray) -> np.ndarray:
    """The (degree+1) non-zero B-spline basis functions at *u*.

    Standard triangular Cox-de Boor recurrence (Piegl & Tiller, Alg. A2.2).
    Returns ``N[0..degree]`` with ``N[j] = N_{span-degree+j, degree}(u)``.
    This is the canonical, correct implementation; it is numerically identical
    to the known-good ``intersection._basis_fns``.
    """
    N = np.zeros(degree + 1)
    N[0] = 1.0
    left = np.zeros(degree + 1)
    right = np.zeros(degree + 1)
    for j in range(1, degree + 1):
        left[j] = u - knots[span + 1 - j]
        right[j] = knots[span + j] - u
        saved = 0.0
        for r in range(j):
            denom = right[r + 1] + left[j - r]
            temp = N[r] / denom if abs(denom) > 1e-15 else 0.0
            N[r] = saved + right[r + 1] * temp
            saved = left[j - r] * temp
        N[j] = saved
    return N


def basis_functions(i: int, u: float, degree: int, knots: np.ndarray) -> np.ndarray:
    """Backwards-compatible alias for the corrected basis-function evaluator.

    Historic call sites passed the knot *span* as ``i`` (see
    ``intersection._nurbs_surface_eval`` parity), which is exactly the
    convention used by :func:`_basis_funcs`.
    """
    return _basis_funcs(i, float(u), degree, knots)


def _basis_funcs_derivs(span: int, u: float, degree: int,
                        knots: np.ndarray, n_der: int) -> np.ndarray:
    """Basis functions and their derivatives up to order *n_der*.

    Piegl & Tiller, Algorithm A2.3.  Returns array ``ders`` of shape
    ``(n_der+1, degree+1)`` where ``ders[k, j]`` is the k-th derivative of the
    basis function ``N_{span-degree+j, degree}`` at *u*.
    """
    ndu = np.zeros((degree + 1, degree + 1))
    ndu[0, 0] = 1.0
    left = np.zeros(degree + 1)
    right = np.zeros(degree + 1)
    for j in range(1, degree + 1):
        left[j] = u - knots[span + 1 - j]
        right[j] = knots[span + j] - u
        saved = 0.0
        for r in range(j):
            ndu[j, r] = right[r + 1] + left[j - r]
            denom = ndu[j, r]
            temp = ndu[r, j - 1] / denom if abs(denom) > 1e-15 else 0.0
            ndu[r, j] = saved + right[r + 1] * temp
            saved = left[j - r] * temp
        ndu[j, j] = saved

    ders = np.zeros((n_der + 1, degree + 1))
    for j in range(degree + 1):
        ders[0, j] = ndu[j, degree]

    a = np.zeros((2, degree + 1))
    for r in range(degree + 1):
        s1, s2 = 0, 1
        a[0, 0] = 1.0
        for k in range(1, n_der + 1):
            d = 0.0
            rk = r - k
            pk = degree - k
            if r >= k:
                a[s2, 0] = a[s1, 0] / ndu[pk + 1, rk] if abs(ndu[pk + 1, rk]) > 1e-15 else 0.0
                d = a[s2, 0] * ndu[rk, pk]
            j1 = 1 if rk >= -1 else -rk
            j2 = k - 1 if (r - 1) <= pk else degree - r
            for j in range(j1, j2 + 1):
                denom = ndu[pk + 1, rk + j]
                a[s2, j] = (a[s1, j] - a[s1, j - 1]) / denom if abs(denom) > 1e-15 else 0.0
                d += a[s2, j] * ndu[rk + j, pk]
            if r <= pk:
                denom = ndu[pk + 1, r]
                a[s2, k] = -a[s1, k - 1] / denom if abs(denom) > 1e-15 else 0.0
                d += a[s2, k] * ndu[r, pk]
            ders[k, r] = d
            s1, s2 = s2, s1

    fac = float(degree)
    for k in range(1, n_der + 1):
        for j in range(degree + 1):
            ders[k, j] *= fac
        fac *= float(degree - k)
    return ders


def _curve_weights(curve: NurbsCurve) -> Optional[np.ndarray]:
    if curve.weights is None:
        return None
    return curve.weights


def de_boor(curve: NurbsCurve, u: float) -> np.ndarray:
    """Evaluate a (rational) NURBS curve at *u*.

    Non-rational curves use plain de Boor on the control points.  Rational
    curves are evaluated by running the algorithm on homogeneous coordinates
    ``(w*P, w)`` and projecting back, which is the exact rational result.
    """
    degree = curve.degree
    n = curve.num_control_points - 1
    p = degree
    u = float(u)

    span = find_span(n, p, u, curve.knots)
    N = _basis_funcs(span, u, p, curve.knots)
    P = curve.control_points
    w = _curve_weights(curve)

    dim = P.shape[1]
    num = np.zeros(dim)
    den = 0.0
    for j in range(p + 1):
        idx = span - p + j
        wj = 1.0 if w is None else float(w[idx])
        num += N[j] * wj * P[idx]
        den += N[j] * wj
    if abs(den) < 1e-300:
        return num
    return num / den


def curve_derivative(curve: NurbsCurve, u: float, order: int = 1) -> np.ndarray:
    """GK-03 — TRUE (un-normalised), rational-correct curve derivative.

    Returns the genuine *order*-th derivative C^(order)(u).  The historic
    implementation incorrectly L2-normalised the first derivative, which broke
    every consumer that needed the actual derivative magnitude (arc length,
    curvature, Newton steps).  This now returns the exact derivative.

    For rational curves the quotient rule on homogeneous coordinates
    (Piegl & Tiller, Eq. 4.8) is applied so the result is rational-correct.
    """
    from math import comb

    degree = curve.degree
    n = curve.num_control_points - 1
    dim = curve.control_points.shape[1]
    u = float(u)

    if order < 0:
        raise ValueError("order must be >= 0")
    if order > degree:
        return np.zeros(dim)

    span = find_span(n, degree, u, curve.knots)
    ders_N = _basis_funcs_derivs(span, u, degree, curve.knots, order)
    P = curve.control_points
    w = _curve_weights(curve)

    # Homogeneous derivatives A^(k) (numerator) and w^(k) (denominator).
    A = np.zeros((order + 1, dim))
    wd = np.zeros(order + 1)
    for k in range(order + 1):
        for j in range(degree + 1):
            idx = span - degree + j
            wj = 1.0 if w is None else float(w[idx])
            A[k] += ders_N[k, j] * wj * P[idx]
            wd[k] += ders_N[k, j] * wj

    if w is None:
        # Non-rational: A^(order) is already the true derivative.
        return A[order]

    # Rational quotient rule: C^(k) = (A^(k) - sum C(k,i) w^(i) C^(k-i)) / w
    C = np.zeros((order + 1, dim))
    for k in range(order + 1):
        v = A[k].copy()
        for i in range(1, k + 1):
            v = v - comb(k, i) * wd[i] * C[k - i]
        C[k] = v / wd[0] if abs(wd[0]) > 1e-300 else v
    return C[order]


# Backwards-compatible name retained for any external caller that wanted the
# rational derivative explicitly (it is now the same correct routine).
def rational_curve_derivative(curve: NurbsCurve, u: float, order: int = 1) -> np.ndarray:
    return curve_derivative(curve, u, order)


# ---------------------------------------------------------------------------
# GK-01 — single canonical surface evaluator (rational, weight-aware)
# ---------------------------------------------------------------------------


def surface_evaluate(surf: NurbsSurface, u: float, v: float) -> np.ndarray:
    """Evaluate a (rational) NURBS surface at *(u, v)*.

    Single canonical evaluator using the correct tensor-product Cox-de Boor
    basis.  For non-rational surfaces this is numerically identical to the
    known-good ``intersection._nurbs_surface_eval``.  For rational surfaces
    (``surf.weights`` provided) the standard
    ``Σ N_i N_j w_ij P_ij / Σ N_i N_j w_ij`` projection is applied.
    """
    u = float(u)
    v = float(v)
    n_u = surf.num_control_points_u - 1
    n_v = surf.num_control_points_v - 1
    span_u = find_span(n_u, surf.degree_u, u, surf.knots_u)
    span_v = find_span(n_v, surf.degree_v, v, surf.knots_v)

    Nu = _basis_funcs(span_u, u, surf.degree_u, surf.knots_u)
    Nv = _basis_funcs(span_v, v, surf.degree_v, surf.knots_v)

    P = surf.control_points
    W = surf.weights
    dim = P.shape[2]
    num = np.zeros(dim)
    den = 0.0
    for i in range(surf.degree_u + 1):
        idx_i = span_u - surf.degree_u + i
        for j in range(surf.degree_v + 1):
            idx_j = span_v - surf.degree_v + j
            wij = 1.0 if W is None else float(W[idx_i, idx_j])
            coef = Nu[i] * Nv[j] * wij
            num += coef * P[idx_i, idx_j]
            den += coef
    if W is None:
        return num
    if abs(den) < 1e-300:
        return num
    return num / den


# ---------------------------------------------------------------------------
# GK-02 — Analytic surface derivatives + unit normal (rational-correct)
# ---------------------------------------------------------------------------


def surface_derivatives(surf: NurbsSurface, u: float, v: float,
                        d: int = 2) -> np.ndarray:
    """All partial derivatives S^(k,l) up to total order *d*.

    Piegl & Tiller Algorithm A3.6 (B-spline tensor product) followed by the
    rational quotient rule Algorithm A4.4 when ``surf.weights`` is present.

    Returns an array ``SKL`` of shape ``(d+1, d+1, dim)`` where
    ``SKL[k, l]`` is ``∂^{k+l} S / ∂u^k ∂v^l`` (entries with
    ``k+l > d`` are zero).  The result is the *true* (un-normalised)
    derivative and is rational-exact.
    """
    from math import comb

    u = float(u)
    v = float(v)
    pu, pv = surf.degree_u, surf.degree_v
    n_u = surf.num_control_points_u - 1
    n_v = surf.num_control_points_v - 1
    P = surf.control_points
    W = surf.weights
    dim = P.shape[2]

    du = min(d, pu)
    dv = min(d, pv)

    span_u = find_span(n_u, pu, u, surf.knots_u)
    span_v = find_span(n_v, pv, v, surf.knots_v)
    ders_u = _basis_funcs_derivs(span_u, u, pu, surf.knots_u, du)
    ders_v = _basis_funcs_derivs(span_v, v, pv, surf.knots_v, dv)

    # Homogeneous derivative table A^(k,l) (numerator) and w^(k,l).
    A = np.zeros((d + 1, d + 1, dim))
    Wd = np.zeros((d + 1, d + 1))
    for k in range(du + 1):
        for l in range(dv + 1):
            tmp_num = np.zeros(dim)
            tmp_den = 0.0
            for i in range(pu + 1):
                idx_i = span_u - pu + i
                for j in range(pv + 1):
                    idx_j = span_v - pv + j
                    wij = 1.0 if W is None else float(W[idx_i, idx_j])
                    c = ders_u[k, i] * ders_v[l, j] * wij
                    tmp_num += c * P[idx_i, idx_j]
                    tmp_den += c
            A[k, l] = tmp_num
            Wd[k, l] = tmp_den

    if W is None:
        return A

    # Rational quotient rule (Piegl & Tiller, Alg. A4.4).
    SKL = np.zeros((d + 1, d + 1, dim))
    for k in range(du + 1):
        for l in range(dv + 1):
            if k + l > d:
                continue
            v_ = A[k, l].copy()
            for j in range(1, l + 1):
                v_ = v_ - comb(l, j) * Wd[0, j] * SKL[k, l - j]
            for i in range(1, k + 1):
                v_ = v_ - comb(k, i) * Wd[i, 0] * SKL[k - i, l]
                v2 = np.zeros(dim)
                for j in range(1, l + 1):
                    v2 = v2 + comb(l, j) * Wd[i, j] * SKL[k - i, l - j]
                v_ = v_ - comb(k, i) * v2
            SKL[k, l] = v_ / Wd[0, 0] if abs(Wd[0, 0]) > 1e-300 else v_
    return SKL


def surface_derivative(surf: NurbsSurface, u: float, v: float,
                       ku: int = 1, kv: int = 0) -> np.ndarray:
    """Mixed partial ∂^{ku+kv} S / ∂u^{ku} ∂v^{kv} at *(u, v)*.

    Analytic (replaces the old finite-difference path).  Rational-correct.
    """
    if ku < 0 or kv < 0:
        raise ValueError("derivative orders must be >= 0")
    d = ku + kv
    SKL = surface_derivatives(surf, u, v, d=max(1, d))
    return SKL[ku, kv]


def surface_normal(surf: NurbsSurface, u: float, v: float) -> np.ndarray:
    """Unit surface normal n = (S_u x S_v) / |S_u x S_v| at *(u, v)*.

    Uses the analytic first partials.  Falls back to a nearby parameter if the
    cross product is degenerate (e.g. at a pole) so the result is still a
    sensible unit vector.
    """
    SKL = surface_derivatives(surf, u, v, d=1)
    su = SKL[1, 0][:3]
    sv = SKL[0, 1][:3]
    nrm = np.cross(su, sv)
    mag = np.linalg.norm(nrm)
    if mag > 1e-12:
        return nrm / mag
    # Degenerate (pole / coincident partials): nudge parameters and retry.
    u0, u1 = float(surf.knots_u[surf.degree_u]), float(surf.knots_u[-surf.degree_u - 1])
    v0, v1 = float(surf.knots_v[surf.degree_v]), float(surf.knots_v[-surf.degree_v - 1])
    eps_u = (u1 - u0) * 1e-4 + 1e-9
    eps_v = (v1 - v0) * 1e-4 + 1e-9
    uu = min(max(u + eps_u, u0), u1)
    vv = min(max(v + eps_v, v0), v1)
    SKL2 = surface_derivatives(surf, uu, vv, d=1)
    nrm = np.cross(SKL2[1, 0][:3], SKL2[0, 1][:3])
    mag = np.linalg.norm(nrm)
    if mag > 1e-12:
        return nrm / mag
    return np.array([0.0, 0.0, 1.0])


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


# ---------------------------------------------------------------------------
# GK-04 — Exact rational quadratic circle / arc / ellipse
# ---------------------------------------------------------------------------


def make_circle_nurbs(center: np.ndarray, radius: float,
                       num_control_points: int = 9,
                       x_axis: Optional[np.ndarray] = None,
                       y_axis: Optional[np.ndarray] = None) -> NurbsCurve:
    """Exact full circle as the standard rational quadratic 9-point NURBS.

    Four quadratic rational Bezier segments (Piegl & Tiller §7.5).  Control
    points are the on-circle quadrant points and the square-corner shoulder
    points; weights are ``[1, √2/2, 1, √2/2, 1, √2/2, 1, √2/2, 1]`` with
    knot vector ``[0,0,0, ¼,¼, ½,½, ¾,¾, 1,1,1]``.  The curve is the *exact*
    circle: every point is at distance ``radius`` from ``center`` and the
    curve closes exactly (C(0) == C(1)).

    The ``num_control_points`` argument is retained for signature
    compatibility but is always the 9-point exact construction (any other
    value would only yield an approximate polygonal "circle").
    """
    center = np.asarray(center, dtype=float).ravel()
    if center.shape[0] < 3:
        center = np.concatenate([center, np.zeros(3 - center.shape[0])])
    center = center[:3]

    if x_axis is None:
        x_axis = np.array([1.0, 0.0, 0.0])
    if y_axis is None:
        y_axis = np.array([0.0, 1.0, 0.0])
    X = np.asarray(x_axis, dtype=float).ravel()[:3]
    Y = np.asarray(y_axis, dtype=float).ravel()[:3]
    X = X / (np.linalg.norm(X) + 1e-300)
    Y = Y / (np.linalg.norm(Y) + 1e-300)

    r = float(radius)
    s = np.sqrt(2.0) / 2.0

    # Local-frame offsets: quadrant points at radius r, shoulder points at the
    # square corners (distance r in each axis ⇒ the rational curve passes
    # exactly through the quadrant points).
    offs = [
        ( r,  0.0),
        ( r,  r),
        ( 0.0,  r),
        (-r,  r),
        (-r,  0.0),
        (-r, -r),
        ( 0.0, -r),
        ( r, -r),
        ( r,  0.0),
    ]
    cps = np.array([center + a * X + b * Y for (a, b) in offs])
    weights = np.array([1.0, s, 1.0, s, 1.0, s, 1.0, s, 1.0])
    knots = np.array([0.0, 0.0, 0.0,
                      0.25, 0.25, 0.5, 0.5, 0.75, 0.75,
                      1.0, 1.0, 1.0])
    return NurbsCurve(degree=2, control_points=cps, knots=knots, weights=weights)


def make_arc_nurbs(center: np.ndarray, radius: float,
                    start_angle: float, end_angle: float,
                    x_axis: Optional[np.ndarray] = None,
                    y_axis: Optional[np.ndarray] = None) -> NurbsCurve:
    """Exact rational quadratic circular arc on ``[start_angle, end_angle]``.

    Implements the multi-segment rational arc of Piegl & Tiller §7.3
    (Algorithm A7.1): split the sweep into ``ceil(Δθ / 90°)`` segments, each
    an exact rational quadratic Bezier.  Every sampled point lies on the
    circle of the given ``radius`` to machine precision and the arc subtends
    exactly ``end_angle - start_angle``.
    """
    center = np.asarray(center, dtype=float).ravel()
    if center.shape[0] < 3:
        center = np.concatenate([center, np.zeros(3 - center.shape[0])])
    center = center[:3]

    if x_axis is None:
        x_axis = np.array([1.0, 0.0, 0.0])
    if y_axis is None:
        y_axis = np.array([0.0, 1.0, 0.0])
    X = np.asarray(x_axis, dtype=float).ravel()[:3]
    Y = np.asarray(y_axis, dtype=float).ravel()[:3]
    X = X / (np.linalg.norm(X) + 1e-300)
    Y = Y / (np.linalg.norm(Y) + 1e-300)

    r = float(radius)
    theta = float(end_angle) - float(start_angle)
    if abs(theta) < 1e-14:
        raise ValueError("arc sweep must be non-zero")

    n_seg = int(np.ceil(abs(theta) / (np.pi / 2.0) - 1e-12))
    n_seg = max(1, n_seg)
    dtheta = theta / n_seg
    w_mid = np.cos(abs(dtheta) / 2.0)  # interior (shoulder) weight

    def P(ang):
        return center + r * (np.cos(ang) * X + np.sin(ang) * Y)

    def T(ang):
        # unit tangent direction (d/dθ of P)
        return -np.sin(ang) * X + np.cos(ang) * Y

    cps = [P(float(start_angle))]
    weights = [1.0]
    a0 = float(start_angle)
    for k in range(n_seg):
        a1 = a0 + dtheta
        p0 = P(a0)
        p2 = P(a1)
        t0 = T(a0)
        t2 = T(a1)
        # Intersection of the two end tangents = the shoulder control point.
        # Solve p0 + alpha t0 = p2 - beta t2 in the local 2D frame.
        M = np.array([
            [np.dot(t0, X), -np.dot(t2, X)],
            [np.dot(t0, Y), -np.dot(t2, Y)],
        ])
        rhs = np.array([
            np.dot(p2 - p0, X),
            np.dot(p2 - p0, Y),
        ])
        try:
            alpha = np.linalg.solve(M, rhs)[0]
        except np.linalg.LinAlgError:
            alpha = 0.0
        shoulder = p0 + alpha * t0
        cps.append(shoulder)
        weights.append(w_mid)
        cps.append(p2)
        weights.append(1.0)
        a0 = a1

    cps = np.array(cps)
    weights = np.array(weights)

    # Clamped degree-2 knot vector: triple at ends, double at each interior
    # segment boundary, parameterised uniformly on [0, 1].
    knots = [0.0, 0.0, 0.0]
    for k in range(1, n_seg):
        t = k / n_seg
        knots += [t, t]
    knots += [1.0, 1.0, 1.0]
    return NurbsCurve(degree=2, control_points=cps,
                      knots=np.array(knots, dtype=float), weights=weights)


def make_ellipse_nurbs(center: np.ndarray, a: float, b: float,
                        x_axis: Optional[np.ndarray] = None,
                        y_axis: Optional[np.ndarray] = None) -> NurbsCurve:
    """Exact full ellipse as a rational quadratic 9-point NURBS.

    Built by anisotropically scaling the unit circle's control net by the
    semi-axes ``a`` (along ``x_axis``) and ``b`` (along ``y_axis``).  The
    weight vector is the circle's; a rational quadratic NURBS is closed under
    affine maps, so the result is the *exact* ellipse
    ``(x/a)² + (y/b)² = 1``.
    """
    circ = make_circle_nurbs(center, 1.0, x_axis=x_axis, y_axis=y_axis)
    center = np.asarray(center, dtype=float).ravel()
    if center.shape[0] < 3:
        center = np.concatenate([center, np.zeros(3 - center.shape[0])])
    center = center[:3]

    if x_axis is None:
        x_axis = np.array([1.0, 0.0, 0.0])
    if y_axis is None:
        y_axis = np.array([0.0, 1.0, 0.0])
    X = np.asarray(x_axis, dtype=float).ravel()[:3]
    Y = np.asarray(y_axis, dtype=float).ravel()[:3]
    X = X / (np.linalg.norm(X) + 1e-300)
    Y = Y / (np.linalg.norm(Y) + 1e-300)

    new_cps = np.zeros_like(circ.control_points)
    for i, cp in enumerate(circ.control_points):
        local = cp - center
        u = np.dot(local, X)
        w = np.dot(local, Y)
        new_cps[i] = center + (float(a) * u) * X + (float(b) * w) * Y
    return NurbsCurve(degree=2, control_points=new_cps,
                      knots=circ.knots.copy(), weights=circ.weights.copy())


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

        if curve.weights is not None:
            warr = TColStd_Array1OfReal(1, num_poles)
            for i, wv in enumerate(curve.weights):
                warr.SetValue(i + 1, float(wv))
            return Geom_BSplineCurve(poles, warr, knots, mults, degree, False)
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


# ---------------------------------------------------------------------------
# GK-96 — Reverse curve / reverse surface direction
# ---------------------------------------------------------------------------

def reverse_curve(curve: NurbsCurve) -> NurbsCurve:
    """Return a new NurbsCurve with the parameterisation reversed.

    The *geometry* is identical: the physical point at parameter *t* on the
    reversed curve equals the point at parameter ``(a + b - t)`` on the
    original, where ``[a, b]`` is the knot domain.  In normalised form
    (domain [0, 1]) this is simply ``1 - t``.

    Algorithm (Piegl & Tiller §5.4):
      * Reverse the control-point sequence.
      * Reverse and reflect the knot vector:
        ``knots_rev[i] = a + b - knots[m - i]``  (``m = len(knots) - 1``).
      * Reverse the weight sequence (if present).

    Oracle: ``reverse_curve(reverse_curve(c))`` is identical to ``c``.
    """
    n = len(curve.knots)
    a = curve.knots[0]
    b = curve.knots[-1]
    knots_rev = a + b - curve.knots[::-1]

    cp_rev = curve.control_points[::-1].copy()
    weights_rev = curve.weights[::-1].copy() if curve.weights is not None else None

    return NurbsCurve(
        degree=curve.degree,
        control_points=cp_rev,
        knots=knots_rev,
        weights=weights_rev,
    )


def reverse_surface(surface: NurbsSurface, direction: str = 'u') -> NurbsSurface:
    """Return a new NurbsSurface with the parameterisation reversed along *direction*.

    *direction* must be ``'u'`` or ``'v'``.

    * ``'u'``: flip rows (u-direction CPs), reflect knots_u.
    * ``'v'``: flip columns (v-direction CPs), reflect knots_v.

    The geometry is preserved; only the parameterisation (and therefore surface
    normals, which flip sign in the reversed direction) change.

    Oracle: ``reverse_surface(reverse_surface(s, d), d)`` is identical to ``s``.
    """
    if direction not in ('u', 'v'):
        raise ValueError("direction must be 'u' or 'v'")

    if direction == 'u':
        a = surface.knots_u[0]
        b = surface.knots_u[-1]
        knots_u_rev = a + b - surface.knots_u[::-1]
        knots_v_rev = surface.knots_v.copy()
        # Flip control-point rows (axis 0 = u).
        cp_rev = surface.control_points[::-1, :, :].copy()
        weights_rev = (
            surface.weights[::-1, :].copy() if surface.weights is not None else None
        )
        return NurbsSurface(
            degree_u=surface.degree_u,
            degree_v=surface.degree_v,
            control_points=cp_rev,
            knots_u=knots_u_rev,
            knots_v=knots_v_rev,
            weights=weights_rev,
        )
    else:  # direction == 'v'
        a = surface.knots_v[0]
        b = surface.knots_v[-1]
        knots_u_rev = surface.knots_u.copy()
        knots_v_rev = a + b - surface.knots_v[::-1]
        # Flip control-point columns (axis 1 = v).
        cp_rev = surface.control_points[:, ::-1, :].copy()
        weights_rev = (
            surface.weights[:, ::-1].copy() if surface.weights is not None else None
        )
        return NurbsSurface(
            degree_u=surface.degree_u,
            degree_v=surface.degree_v,
            control_points=cp_rev,
            knots_u=knots_u_rev,
            knots_v=knots_v_rev,
            weights=weights_rev,
        )


# ---------------------------------------------------------------------------
# GK-135 — Degree reduction (curve + surface; inverse of degree elevation)
# ---------------------------------------------------------------------------

def _bezier_degree_elevate_once(P: np.ndarray) -> np.ndarray:
    """Elevate a single Bezier segment of degree n by 1 (→ degree n+1).

    Uses the standard Bezier degree elevation formula:
      Q_i = (i / (n+1)) * P_{i-1} + (1 - i/(n+1)) * P_i,  for i=0..n+1
    where P_{-1} and P_{n+1} are not defined (end conditions fold in naturally).

    Returns the (n+2,) array of elevated control points.
    """
    n = len(P) - 1  # original degree
    dim = P.shape[1]
    Q = np.zeros((n + 2, dim))
    Q[0] = P[0].copy()
    Q[n + 1] = P[n].copy()
    for i in range(1, n + 1):
        alpha = i / (n + 1)
        Q[i] = alpha * P[i - 1] + (1.0 - alpha) * P[i]
    return Q


def _elevate_curve_bspline(curve: NurbsCurve, times: int = 1) -> NurbsCurve:
    """Correctly elevate a B-spline curve by *times* degrees (default 1).

    Works by decomposing into Bezier segments, elevating each, then
    reassembling.  This is a correct implementation used by GK-135 tests
    (and internally) since the legacy ``degree_elevation`` function has a
    known implementation defect.
    """
    if times <= 0:
        return curve

    p = curve.degree
    P = curve.control_points.copy().astype(float)
    U = curve.knots.copy().astype(float)
    W = curve.weights

    if W is not None:
        Pw = np.column_stack([P * W[:, None], W])
    else:
        Pw = P.copy()

    # One elevation step at a time
    for _ in range(times):
        segs = _decompose_to_bezier(Pw, U, p)
        if not segs:
            break

        # Elevate each segment
        elevated_segs = [(_bezier_degree_elevate_once(seg), u_lo, u_hi)
                         for seg, u_lo, u_hi in segs]

        new_p = p + 1

        # Merge: share endpoints between adjacent segments
        # First segment: include all its CPs
        merged = [row.copy() for row in elevated_segs[0][0]]
        for k in range(1, len(elevated_segs)):
            seg_e, u_lo, u_hi = elevated_segs[k]
            # Average shared endpoint
            prev_last = merged[-1].copy()
            cur_first = seg_e[0].copy()
            merged[-1] = 0.5 * (prev_last + cur_first)
            merged.extend([row.copy() for row in seg_e[1:]])
        Pw = np.array(merged, dtype=float)

        # Rebuild knot vector with multiplicity new_p at internal breakpoints
        breakpoints = [segs[0][1]] + [u_hi for _, _, u_hi in segs]
        new_U_list = [breakpoints[0]] * (new_p + 1)
        for bp in breakpoints[1:-1]:
            new_U_list.extend([bp] * new_p)
        new_U_list.extend([breakpoints[-1]] * (new_p + 1))
        U = np.array(new_U_list, dtype=float)

        # Validate
        expected = len(Pw) + new_p + 1
        if len(U) != expected:
            n_int = len(Pw) - new_p - 1
            a, b = curve.knots[0], curve.knots[-1]
            interior = np.linspace(a, b, n_int + 2)[1:-1] if n_int > 0 else np.array([])
            U = np.concatenate([
                np.full(new_p + 1, a),
                interior,
                np.full(new_p + 1, b),
            ])

        p = new_p

    if W is not None:
        new_W = Pw[:, -1].copy()
        new_P_cart = np.where(
            new_W[:, None] > 1e-14,
            Pw[:, :-1] / new_W[:, None],
            Pw[:, :-1],
        )
        return NurbsCurve(degree=p, control_points=new_P_cart, knots=U, weights=new_W)
    else:
        return NurbsCurve(degree=p, control_points=Pw, knots=U)


def _bezier_degree_reduce_once(P: np.ndarray) -> np.ndarray:
    """Reduce a single Bezier segment of degree n by 1 (→ degree n-1).

    Uses the Forrest–Piegl least-squares split: solve from both ends and
    average at the midpoint.  Returns the (n,) array of reduced control points
    (n = len(P) - 1, i.e., we go from n+1 points to n points).

    Reference: Piegl & Tiller, "The NURBS Book" §5.5, Algorithm A5.6.
    """
    n = len(P) - 1  # original degree
    r = n - 1       # target degree
    dim = P.shape[1]
    Q = np.zeros((r + 1, dim))

    # Endpoints are always preserved exactly
    Q[0] = P[0].copy()
    Q[r] = P[n].copy()

    half = r // 2

    # Forward recurrence: Q_i = ((r+1)*P_i - i*Q_{i-1}) / (r+1-i)
    for i in range(1, half + 1):
        denom = r + 1 - i
        if abs(denom) < 1e-15:
            break
        Q[i] = ((r + 1) * P[i] - i * Q[i - 1]) / denom

    # Backward recurrence from right end
    for i in range(r - 1, half, -1):
        denom = i + 1
        if abs(denom) < 1e-15:
            break
        Q[i] = ((r + 1) * P[i + 1] - (r - i) * Q[i + 1]) / denom

    # Average at midpoint when r is even
    if r % 2 == 0:
        mid = half
        denom_fwd = r + 1 - half
        denom_bwd = half + 1
        if abs(denom_fwd) > 1e-15 and abs(denom_bwd) > 1e-15:
            q_fwd = ((r + 1) * P[half] - half * Q[half - 1]) / denom_fwd
            q_bwd = ((r + 1) * P[half + 1] - (r - half) * Q[half + 1]) / denom_bwd
            Q[mid] = 0.5 * (q_fwd + q_bwd)

    return Q


def _correct_knot_insert(Pw: np.ndarray, U: np.ndarray, p: int,
                          u: float) -> tuple:
    """Insert knot *u* once into a B-spline (Pw, U, degree p).

    Uses the standard Boehm insertion formula.  Returns (new_Pw, new_U).
    Works for any consistent knot vector.
    """
    n = len(Pw) - 1
    m = len(U) - 1
    dim = Pw.shape[1]
    tol = 1e-14

    # Find insertion span: largest k s.t. U[k] <= u and U[k] < U[k+1]
    k = p
    for j in range(p, m):
        if float(U[j]) <= u + tol and float(U[j + 1]) > float(U[j]) + tol:
            if u < float(U[j + 1]) - tol or j == m - p - 1:
                k = j
                if u < float(U[j + 1]) - tol:
                    break

    # Current multiplicity s of knot u
    s = sum(1 for uj in U if abs(float(uj) - u) < tol)

    # New arrays (one extra CP and one extra knot)
    new_Pw = np.zeros((n + 2, dim))
    new_U = np.zeros(m + 2)

    # Insert the new knot at position k+1
    new_U[:k + 1] = U[:k + 1]
    new_U[k + 1] = u
    new_U[k + 2:] = U[k + 1:]

    # Copy unchanged CPs (before and after blend zone)
    for j in range(k - p + 1):
        new_Pw[j] = Pw[j]
    for j in range(k - s, n + 1):
        new_Pw[j + 1] = Pw[j]

    # Blend CPs in the range [k-p+1 .. k-s]
    for j in range(k - p + 1, k - s + 1):
        lo_knot = float(new_U[j])
        hi_knot = float(new_U[j + p + 1])
        denom = hi_knot - lo_knot
        alpha = (u - lo_knot) / denom if abs(denom) > tol else 0.0
        new_Pw[j] = (1.0 - alpha) * Pw[j - 1] + alpha * Pw[j]

    return new_Pw, new_U


def _decompose_to_bezier(Pw: np.ndarray, U: np.ndarray, p: int) -> list:
    """Decompose a B-spline (homogeneous CPs *Pw*, knots *U*, degree *p*)
    into Bezier segments by raising each internal knot to multiplicity *p*.

    Returns list of (seg_Pw, u_lo, u_hi) where seg_Pw has shape (p+1, dim).
    Adjacent segments share the boundary CP.
    """
    cPw = Pw.copy().astype(float)
    cU = np.array(U, dtype=float)
    tol = 1e-14

    u_lo_v = float(cU[0])
    u_hi_v = float(cU[-1])

    # Collect internal knots and raise each to multiplicity p
    changed = True
    while changed:
        changed = False
        inner = {}
        for uj in cU:
            v = float(uj)
            if v > u_lo_v + tol and v < u_hi_v - tol:
                key = round(v, 12)
                inner[key] = inner.get(key, 0) + 1
        for t_key in sorted(inner.keys()):
            mult = inner[t_key]
            if mult < p:
                for _ in range(p - mult):
                    cPw, cU = _correct_knot_insert(cPw, cU, p, t_key)
                changed = True
                break

    # With all internal knots at mult = p, adjacent Bezier segs share 1 CP.
    # n_segs = (len(cPw) - 1) // p
    n = len(cPw) - 1
    n_segs = n // p if p > 0 else 1

    segs = []
    for k in range(n_segs):
        idx0 = k * p
        seg = cPw[idx0:idx0 + p + 1].copy()
        u_lo_seg = float(cU[idx0 + p])
        u_hi_seg = float(cU[idx0 + p + 1]) if idx0 + p + 1 < len(cU) else u_hi_v
        segs.append((seg, u_lo_seg, u_hi_seg))

    # Ensure last CP of last segment = actual last CP (clamped endpoint)
    if segs and len(cPw) > 0:
        last_seg, u_lo_s, u_hi_s = segs[-1]
        if not np.allclose(last_seg[-1], cPw[-1], atol=tol):
            last_seg = last_seg.copy()
            last_seg[-1] = cPw[-1].copy()
            segs[-1] = (last_seg, u_lo_s, u_hi_s)

    return segs


def reduce_degree_curve(curve: NurbsCurve, tol: float = 1e-6) -> NurbsCurve:
    """Attempt to reduce the degree of *curve* by 1, staying within *tol*.

    Algorithm (Piegl & Tiller §5.5, Forrest–Piegl):
    1. Decompose into Bezier segments via full knot-multiplicity insertion.
    2. Reduce each Bezier segment by 1 using the Forrest–Piegl split.
    3. Check the maximum deviation (Hausdorff sample over the segment) against
       *tol*.
    4. If ALL segments pass, reassemble and return the degree-(p-1) curve.
       If any segment fails, return *curve* unchanged.

    Weights: performed in homogeneous (weighted) space when rational.

    Returns *curve* unchanged if:
    - ``curve.degree <= 1`` (cannot reduce below degree 1), or
    - the geometric deviation after reduction exceeds *tol*.
    """
    if curve.degree <= 1:
        return curve

    p = curve.degree
    P = curve.control_points.copy().astype(float)
    U = curve.knots.copy().astype(float)
    W = curve.weights

    # Work in homogeneous space for rational curves
    if W is not None:
        Pw = np.column_stack([P * W[:, None], W])
    else:
        Pw = P.copy()

    segs = _decompose_to_bezier(Pw, U, p)
    if not segs:
        return curve

    CHECK_SAMPLES = 16
    reduced_segs = []

    for seg_Pw, u_lo, u_hi in segs:
        seg_Pw_reduced = _bezier_degree_reduce_once(seg_Pw)

        # Check deviation
        max_err = 0.0
        for s in range(CHECK_SAMPLES + 1):
            t = s / CHECK_SAMPLES

            # de Casteljau on original (degree p)
            pts_orig = seg_Pw.copy()
            for r_it in range(p):
                for j in range(p - r_it):
                    pts_orig[j] = (1 - t) * pts_orig[j] + t * pts_orig[j + 1]
            pt_orig = pts_orig[0]

            # de Casteljau on reduced (degree p-1)
            r_deg = p - 1
            pts_red = seg_Pw_reduced.copy()
            for r_it in range(r_deg):
                for j in range(r_deg - r_it):
                    pts_red[j] = (1 - t) * pts_red[j] + t * pts_red[j + 1]
            pt_red = pts_red[0]

            # Project from homogeneous if rational
            if W is not None:
                wo = pt_orig[-1]
                wr = pt_red[-1]
                pt_orig_c = pt_orig[:-1] / wo if abs(wo) > 1e-14 else pt_orig[:-1]
                pt_red_c = pt_red[:-1] / wr if abs(wr) > 1e-14 else pt_red[:-1]
            else:
                pt_orig_c = pt_orig
                pt_red_c = pt_red

            err = float(np.linalg.norm(pt_orig_c - pt_red_c))
            if err > max_err:
                max_err = err

        if max_err > tol:
            return curve  # cannot reduce within tolerance

        reduced_segs.append(seg_Pw_reduced)

    # Reassemble into a B-spline of degree p-1
    new_p = p - 1

    # Merge Bezier segments.
    # For a single segment: just copy all its CPs.
    # For multiple segments: adjacent segments share one endpoint — average it.
    merged_Pw = [row.copy() for row in reduced_segs[0]]
    for k in range(1, len(reduced_segs)):
        # Average the shared knot (last of previous, first of current)
        prev_last = merged_Pw[-1].copy()
        cur_first = reduced_segs[k][0].copy()
        merged_Pw[-1] = 0.5 * (prev_last + cur_first)
        merged_Pw.extend([row.copy() for row in reduced_segs[k][1:]])
    merged_Pw = np.array(merged_Pw, dtype=float)

    # Build clamped knot vector with internal breakpoints of multiplicity new_p
    breakpoints = [segs[0][1]] + [u_hi for _, _, u_hi in segs]
    new_U_list = [breakpoints[0]] * (new_p + 1)
    for bp in breakpoints[1:-1]:
        new_U_list.extend([bp] * new_p)
    new_U_list.extend([breakpoints[-1]] * (new_p + 1))
    new_U = np.array(new_U_list, dtype=float)

    # Validate length; rebuild uniformly if something went wrong
    expected_len = len(merged_Pw) + new_p + 1
    if len(new_U) != expected_len:
        n_int = len(merged_Pw) - new_p - 1
        a, b = U[0], U[-1]
        interior = np.linspace(a, b, n_int + 2)[1:-1] if n_int > 0 else np.array([])
        new_U = np.concatenate([
            np.full(new_p + 1, a),
            interior,
            np.full(new_p + 1, b),
        ])

    # Convert back from homogeneous if rational
    if W is not None:
        new_W = merged_Pw[:, -1].copy()
        new_P_cart = np.where(
            new_W[:, None] > 1e-14,
            merged_Pw[:, :-1] / new_W[:, None],
            merged_Pw[:, :-1],
        )
        return NurbsCurve(degree=new_p, control_points=new_P_cart,
                          knots=new_U, weights=new_W)
    else:
        return NurbsCurve(degree=new_p, control_points=merged_Pw, knots=new_U)


def reduce_degree_surface(surface: NurbsSurface,
                          direction: str = 'u',
                          tol: float = 1e-6) -> NurbsSurface:
    """Attempt to reduce the degree of *surface* by 1 along *direction*.

    *direction* is ``'u'`` or ``'v'``.

    Applies :func:`reduce_degree_curve` independently to every iso-parametric
    column (``'u'``) or row (``'v'``).  If every curve reduces successfully
    (all within *tol*), return the lower-degree surface; otherwise return
    *surface* unchanged.

    Oracle: elevate in U then ``reduce_degree_surface(s, 'u')`` recovers the
    original degree and control-point grid ± *tol*.
    """
    if direction not in ('u', 'v'):
        raise ValueError("direction must be 'u' or 'v'")

    if direction == 'u':
        if surface.degree_u <= 1:
            return surface
        nv = surface.num_control_points_v
        dim = surface.control_points.shape[2]
        W = surface.weights

        reduced_cols = []
        new_knots_u = None

        for j in range(nv):
            col_pts = surface.control_points[:, j, :].copy()
            col_w = W[:, j].copy() if W is not None else None
            col_curve = NurbsCurve(
                degree=surface.degree_u,
                control_points=col_pts,
                knots=surface.knots_u.copy(),
                weights=col_w,
            )
            reduced = reduce_degree_curve(col_curve, tol=tol)
            if reduced.degree == surface.degree_u:
                return surface  # reduction failed
            reduced_cols.append(reduced)
            if new_knots_u is None:
                new_knots_u = reduced.knots.copy()

        new_nu = reduced_cols[0].num_control_points
        new_cp = np.zeros((new_nu, nv, dim))
        new_W = np.zeros((new_nu, nv)) if W is not None else None

        for j, rc in enumerate(reduced_cols):
            new_cp[:, j, :] = rc.control_points
            if W is not None:
                new_W[:, j] = (
                    rc.weights if rc.weights is not None else np.ones(new_nu)
                )

        return NurbsSurface(
            degree_u=surface.degree_u - 1,
            degree_v=surface.degree_v,
            control_points=new_cp,
            knots_u=new_knots_u,
            knots_v=surface.knots_v.copy(),
            weights=new_W,
        )

    else:  # direction == 'v'
        if surface.degree_v <= 1:
            return surface
        nu = surface.num_control_points_u
        dim = surface.control_points.shape[2]
        W = surface.weights

        reduced_rows = []
        new_knots_v = None

        for i in range(nu):
            row_pts = surface.control_points[i, :, :].copy()
            row_w = W[i, :].copy() if W is not None else None
            row_curve = NurbsCurve(
                degree=surface.degree_v,
                control_points=row_pts,
                knots=surface.knots_v.copy(),
                weights=row_w,
            )
            reduced = reduce_degree_curve(row_curve, tol=tol)
            if reduced.degree == surface.degree_v:
                return surface  # reduction failed
            reduced_rows.append(reduced)
            if new_knots_v is None:
                new_knots_v = reduced.knots.copy()

        new_nv = reduced_rows[0].num_control_points
        new_cp = np.zeros((nu, new_nv, dim))
        new_W = np.zeros((nu, new_nv)) if W is not None else None

        for i, rr in enumerate(reduced_rows):
            new_cp[i, :, :] = rr.control_points
            if W is not None:
                new_W[i, :] = (
                    rr.weights if rr.weights is not None else np.ones(new_nv)
                )

        return NurbsSurface(
            degree_u=surface.degree_u,
            degree_v=surface.degree_v - 1,
            control_points=new_cp,
            knots_u=surface.knots_u.copy(),
            knots_v=new_knots_v,
            weights=new_W,
        )


# ---------------------------------------------------------------------------
# GK-102 — Knot removal / minimal-CP refit
# ---------------------------------------------------------------------------
#
# References:
#   Piegl & Tiller, "The NURBS Book", 2nd ed., §5.4 — RemoveCurveKnot.
#
# Strategy
# --------
# For each attempted removal of one instance of *knot_value*:
#   1. Locate the knot span *r* (rightmost occurrence) and current multiplicity *s*.
#   2. Build candidate new control points in homogeneous space (rational support)
#      by solving the two-sided linear system for the knot-removal equations.
#   3. Evaluate the maximum geometric deviation over CHECK_SAMPLES sample points
#      comparing the original curve with the would-be candidate curve.
#   4. Accept the removal only if deviation <= tol; otherwise stop early.


def remove_knot(
    curve: NurbsCurve,
    knot_value: float,
    num: int = 1,
    tol: float = 1e-6,
) -> "NurbsCurve":
    """Remove up to *num* instances of *knot_value* from *curve* within *tol*.

    Implements Piegl & Tiller §5.4 RemoveCurveKnot.  Only removals that keep
    the maximum geometric deviation ≤ *tol* are accepted; the rest are silently
    skipped (returning the curve with as many removals as were feasible).

    Parameters
    ----------
    curve:
        Input NURBS curve.
    knot_value:
        The knot to remove (must be an interior knot; clamped end-knots whose
        multiplicity equals ``degree+1`` cannot be removed without changing the
        curve endpoints).
    num:
        Maximum number of times to remove this knot.  Defaults to 1.
    tol:
        Maximum allowable deviation (Euclidean, same units as control points).

    Returns
    -------
    NurbsCurve
        A new curve with up to *num* instances of *knot_value* removed, or the
        original curve if zero removals were feasible.
    """
    current = curve
    for _ in range(num):
        result = _remove_knot_once(current, knot_value, tol)
        if result is current:
            break  # no progress — stop
        current = result
    return current


def _remove_knot_once(
    curve: NurbsCurve,
    u_remove: float,
    tol: float,
) -> "NurbsCurve":
    """Attempt to remove one instance of *u_remove* from *curve*.

    Implements the knot-removal algorithm from Piegl & Tiller §5.4.
    Returns *curve* unchanged if the removal would exceed *tol*.

    The knot-removal equations (inverted Boehm blending):
      Forward (knot insertion):
        P_old[i] = (1 - alpha_i) * P_new[i-1] + alpha_i * P_new[i]
      Invert from left:
        P_new[i] = (P_old[i] - (1-alpha_i) * P_new[i-1]) / alpha_i
      Invert from right:
        P_new[i-1] = (P_old[i] - alpha_i * P_new[i]) / (1 - alpha_i)

    where alpha_i = (u - U[i]) / (U[i+p+1] - U[i]).

    We solve from both ends inward, then compare at the midpoint to decide
    whether the removal is compatible with the tolerance.
    """
    p = curve.degree
    U = curve.knots.astype(float)
    P = curve.control_points.astype(float)
    W = curve.weights
    num_cp = curve.num_control_points  # = n+1
    n = num_cp - 1                     # last old CP index
    m = len(U) - 1                     # last knot index

    # Work in homogeneous space for rational curves
    if W is not None:
        Pw = np.column_stack([P * W[:, None], W])
    else:
        Pw = P.copy()
    dim_h = Pw.shape[1]

    # Locate rightmost occurrence index of u_remove in U
    r = -1
    for idx in range(m, -1, -1):
        if abs(U[idx] - u_remove) < 1e-12:
            r = idx
            break
    if r == -1:
        return curve  # knot not present

    # Current multiplicity of u_remove
    s = int(np.sum(np.abs(U - u_remove) < 1e-12))

    # Never touch end clamps (multiplicity = p+1)
    if abs(u_remove - U[0]) < 1e-12 and s >= p + 1:
        return curve
    if abs(u_remove - U[-1]) < 1e-12 and s >= p + 1:
        return curve

    # After removing one instance the new array has (n) CPs (indices 0..n-1)
    # and (m) knots (one fewer).
    #
    # The affected CP indices in the OLD array are [first..last+1] where:
    #   first = r - p
    #   last  = r - s   (last affected index; after the loop last+1 is unaffected)
    first = r - p
    last = r - s

    # Blending coefficients alpha[i] = (u - U[i]) / (U[i+p+1] - U[i])
    # These come from the ORIGINAL knot vector U (before removal).
    def alpha(i: int) -> float:
        denom = U[i + p + 1] - U[i]
        if abs(denom) < 1e-14:
            return 0.0
        return (u_remove - U[i]) / denom

    # Temp arrays in the NEW CP indexing (0..n-1).
    # We solve from the left (indices first..mid) and from the right (last..mid).
    # In the new array, old index k maps to new index k for k < r, and k-1 for k > r.
    # But it is simpler to keep a full-length working buffer and build Pw_cand from it.

    # Left-side solution array (new-index space): new[first-1] = old[first-1] is known.
    # We compute new[first], new[first+1], ...
    left = np.zeros((num_cp, dim_h))    # indexed by NEW CP index
    right = np.zeros((num_cp, dim_h))   # indexed by NEW CP index

    # Boundary: the unaffected CPs on both sides are known.
    # On the left, the last unaffected new CP is new[first-1] = old[first-1] = Pw[first-1].
    # (If first == 0 this boundary isn't needed because alpha[0] should be 0.)
    # On the right, the first unaffected new CP is new[last] = old[last+1] = Pw[last+1].
    # (new index = old index - 1 for indices > r; old[last+1] → new[last+1-1] = new[last])

    if first > 0:
        left[first - 1] = Pw[first - 1]
    right[last] = Pw[last + 1]

    # Left inversion: compute new[first .. ?] from the left
    # P_old[i] = (1-a)*new[i-1] + a*new[i]  →  new[i] = (P_old[i] - (1-a)*new[i-1])/a
    # Here i runs from first to some mid_L, using OLD Pw[i] and alpha(i).
    lft = first    # next new-index to compute from left
    rgt = last - 1  # next new-index to compute from right (starts just left of new[last])

    # Compute left side
    for i in range(first, last + 1):
        a = alpha(i)
        if abs(a) < 1e-14:
            # alpha==0 means new[i] == Pw[i] (no blend from left)
            left[i] = Pw[i]
        else:
            left[i] = (Pw[i] - (1.0 - a) * left[i - 1]) / a

    # Compute right side:
    # P_old[j+1] = (1-a)*new[j] + a*new[j+1]  →  new[j] = (P_old[j+1] - a*new[j+1])/(1-a)
    # j = last-1, last-2, ...  (new index), P_old index = j+1+1 = j+2
    # Wait: in old indexing, new[k] corresponds to old[k] for k <= r-1 and old[k+1] for k >= r.
    # After one removal at position r, the mapping is:
    #   new_CP[k] = old_CP[k]     for k in [0, r-1]  (left of removed knot)
    #   new_CP[k] = old_CP[k+1]   for k in [r, n-1]  (right of removed knot, shifted)
    # The Boehm insertion formula (in old indices) is:
    #   old[i] = (1-alpha(i))*new[i-1] + alpha(i)*new[i]   for i in [first, last+1]
    #
    # For the right side we go from the right. Let's index differently:
    # For j in [first, last] (new indices), the "right equation" uses old[j+1]:
    #   old[j+1] = (1-alpha(j+1))*new[j] + alpha(j+1)*new[j+1]
    #   → new[j] = (old[j+1] - alpha(j+1)*new[j+1]) / (1 - alpha(j+1))

    for j in range(last - 1, first - 1, -1):
        a = alpha(j + 1)
        if abs(1.0 - a) < 1e-14:
            right[j] = Pw[j + 1]
        else:
            right[j] = (Pw[j + 1] - a * right[j + 1]) / (1.0 - a)

    # Determine the split point: how many steps from each side
    # For a single removal (t=1 in P&T) the overlap condition is checked at
    # new index floor((first + last - 1) / 2) for even, exact mid for odd.
    # A simpler approach: pick the midpoint and compare left vs right.

    # Check if left and right agree within tol at the midpoint
    mid = (first + last - 1) // 2  # midpoint in new-index space
    if last >= first:
        err_mid = float(np.linalg.norm(left[mid] - right[mid]))
        if err_mid > tol:
            return curve

    # Build Pw_cand: take left side up to mid, right side after mid
    Pw_cand = np.zeros((n, dim_h))
    # Copy left-unaffected part
    for k in range(first):
        Pw_cand[k] = Pw[k]
    # Left solved part: new indices [first .. mid]
    for k in range(first, mid + 1):
        Pw_cand[k] = left[k]
    # Right solved part: new indices [mid+1 .. last-1]
    for k in range(mid + 1, last):
        Pw_cand[k] = right[k]
    # Right boundary (new[last] = old[last+1])
    if last < n:
        Pw_cand[last] = right[last]
    # Copy right-unaffected part (new indices [last+1 .. n-1] = old[last+2 .. n])
    for k in range(last + 1, n):
        Pw_cand[k] = Pw[k + 1]

    # Build candidate new knot vector: remove one instance at index r
    U_new = np.concatenate([U[:r], U[r + 1:]])

    # Sanity: new num_cp = n, new knot length = n + p + 1
    if len(U_new) != n + p + 1:
        return curve

    # Build candidate curve
    if W is not None:
        new_W_arr = Pw_cand[:, -1].copy()
        safe_w = np.where(np.abs(new_W_arr) > 1e-14, new_W_arr, 1.0)
        new_P_cart = Pw_cand[:, :-1] / safe_w[:, None]
        candidate = NurbsCurve(
            degree=p, control_points=new_P_cart, knots=U_new, weights=new_W_arr,
        )
    else:
        candidate = NurbsCurve(degree=p, control_points=Pw_cand, knots=U_new)

    # Final deviation check: sample over full parameter domain
    CHECK_SAMPLES = 32
    u0 = float(U[p])
    u1 = float(U[-(p + 1)])
    max_err = 0.0
    for k in range(CHECK_SAMPLES + 1):
        t = u0 + (u1 - u0) * k / CHECK_SAMPLES
        pt_orig = curve.evaluate(t)
        pt_cand = candidate.evaluate(t)
        err = float(np.linalg.norm(pt_orig - pt_cand))
        if err > max_err:
            max_err = err

    if max_err > tol:
        return curve

    return candidate


def minimal_cp_refit(curve: NurbsCurve, tol: float = 1e-6) -> "NurbsCurve":
    """Remove all removable interior knots from *curve*, minimising CP count.

    Iterates over each distinct interior knot value, attempting to remove all
    instances of it within *tol* via :func:`remove_knot`.  Repeats until no
    further removal is possible.

    This is the curve-simplification operation from Piegl & Tiller §5.4:
    given a curve that may have been produced by knot insertion (e.g. for
    editing or splitting), recover the minimal representation.

    Parameters
    ----------
    curve:
        Input NURBS curve.
    tol:
        Maximum allowable geometric deviation for each knot removal step.

    Returns
    -------
    NurbsCurve
        A new curve with the same geometry (within *tol*) but potentially
        fewer control points (and knots).
    """
    current = curve
    changed = True
    while changed:
        changed = False
        p = current.degree
        U = current.knots
        # Collect distinct interior knot values (exclude clamped ends)
        u0 = U[p]
        u1 = U[-(p + 1)]
        interior = [
            v for v in np.unique(U)
            if v > u0 + 1e-12 and v < u1 - 1e-12
        ]
        for uv in interior:
            prev_n = current.num_control_points
            next_curve = remove_knot(current, float(uv), num=p + 1, tol=tol)
            if next_curve.num_control_points < prev_n:
                current = next_curve
                changed = True
    return current


# ---------------------------------------------------------------------------
# GK-97: Reparametrize curve / surface
# ---------------------------------------------------------------------------

def _rescale_knots(knots: np.ndarray, new_a: float, new_b: float) -> np.ndarray:
    """Linearly map *knots* from their current domain [a, b] to [new_a, new_b]."""
    a = float(knots[0])
    b = float(knots[-1])
    if abs(b - a) < 1e-15:
        raise ValueError("Knot vector has zero-length domain; cannot rescale.")
    return new_a + (new_b - new_a) * (knots - a) / (b - a)


def normalize_knots(curve_or_surface):
    """Rescale knot vector(s) so the domain becomes [0, 1].

    Supports both :class:`NurbsCurve` and :class:`NurbsSurface`.  Control
    points and weights are unchanged; only the knot values are remapped.

    Parameters
    ----------
    curve_or_surface:
        A :class:`NurbsCurve` or :class:`NurbsSurface`.

    Returns
    -------
    Same type as the input, with knot vector(s) rescaled to [0, 1].
    """
    if isinstance(curve_or_surface, NurbsCurve):
        c = curve_or_surface
        new_knots = _rescale_knots(c.knots, 0.0, 1.0)
        return NurbsCurve(
            degree=c.degree,
            control_points=c.control_points.copy(),
            knots=new_knots,
            weights=c.weights.copy() if c.weights is not None else None,
        )
    elif isinstance(curve_or_surface, NurbsSurface):
        s = curve_or_surface
        new_ku = _rescale_knots(s.knots_u, 0.0, 1.0)
        new_kv = _rescale_knots(s.knots_v, 0.0, 1.0)
        return NurbsSurface(
            degree_u=s.degree_u,
            degree_v=s.degree_v,
            control_points=s.control_points.copy(),
            knots_u=new_ku,
            knots_v=new_kv,
            weights=s.weights.copy() if s.weights is not None else None,
        )
    else:
        raise TypeError(
            f"normalize_knots expects a NurbsCurve or NurbsSurface, got {type(curve_or_surface)}"
        )


def reparametrize_curve(
    curve: NurbsCurve,
    t0: float = 0.0,
    t1: float = 1.0,
) -> NurbsCurve:
    """Return a new :class:`NurbsCurve` whose domain is ``[t0, t1]``.

    This is a pure knot-rescaling operation: the geometry (positions in space)
    is entirely preserved.  Only the parameterisation is shifted/scaled.

    Parameters
    ----------
    curve:
        Input NURBS curve.
    t0:
        New start parameter (default 0.0).
    t1:
        New end parameter (default 1.0). Must satisfy ``t1 > t0``.

    Returns
    -------
    NurbsCurve
        A new curve with knots linearly mapped to ``[t0, t1]``.
    """
    if t1 <= t0:
        raise ValueError(f"t1 ({t1}) must be greater than t0 ({t0}).")
    new_knots = _rescale_knots(curve.knots, float(t0), float(t1))
    return NurbsCurve(
        degree=curve.degree,
        control_points=curve.control_points.copy(),
        knots=new_knots,
        weights=curve.weights.copy() if curve.weights is not None else None,
    )


def reparametrize_arclength(
    curve: NurbsCurve,
    n: int = 128,
) -> NurbsCurve:
    """Return an *approximate* arc-length-parameterised version of *curve*.

    The returned curve is re-fitted to ``n+1`` points sampled at uniformly
    spaced arc-length fractions of the original, so ``evaluate(t)`` for
    ``t ∈ [0, 1]`` advances along the curve at a (nearly) constant speed
    with respect to Euclidean arc length.

    Algorithm
    ---------
    1. Build a cumulative arc-length table by adaptive 5-point Gauss–Legendre
       quadrature over ``n`` uniform sub-intervals of the original knot domain.
    2. Sample ``n+1`` points at arc-length fractions 0, 1/n, 2/n, …, 1 by
       inverting the table via linear interpolation.
    3. Fit a degree-3 B-spline through the sampled points using chord-length
       parameterisation (standard Piegl–Tiller least-squares fit).

    The resulting curve has domain [0, 1] and preserves the geometry to within
    the chord-length sampling tolerance (approximately O(1/n²)).

    Parameters
    ----------
    curve:
        Input NURBS curve (any degree, any knot domain).
    n:
        Number of uniform arc-length intervals.  Higher values give a closer
        approximation.  Default: 128.

    Returns
    -------
    NurbsCurve
        A new degree-3 B-spline with domain [0, 1] that approximates
        arc-length parameterisation.
    """
    # --- Step 1: build cumulative arc-length table ---
    p = curve.degree
    u0 = float(curve.knots[p])
    u1 = float(curve.knots[-(p + 1)])

    # Gauss–Legendre weights / nodes (5-point rule)
    _GL5_X = np.array([
        -0.9061798459386640,
        -0.5384693101056831,
         0.0,
         0.5384693101056831,
         0.9061798459386640,
    ])
    _GL5_W = np.array([
        0.2369268850561891,
        0.4786286704993665,
        0.5688888888888889,
        0.4786286704993665,
        0.2369268850561891,
    ])

    params = np.linspace(u0, u1, n + 1)
    lengths = np.zeros(n + 1)
    for i in range(n):
        a_i = params[i]
        b_i = params[i + 1]
        mid = 0.5 * (a_i + b_i)
        half = 0.5 * (b_i - a_i)
        nodes = mid + half * _GL5_X
        speed = np.array([
            float(np.linalg.norm(curve_derivative(curve, float(u), order=1)[1]))
            for u in nodes
        ])
        lengths[i + 1] = lengths[i] + half * float(_GL5_W @ speed)

    total = lengths[-1]
    if total < 1e-15:
        # Degenerate (zero-length) curve — return normalized knot form unchanged
        return normalize_knots(curve)

    # --- Step 2: sample points at uniform arc-length fractions ---
    target_lengths = np.linspace(0.0, total, n + 1)
    sample_params = np.interp(target_lengths, lengths, params)

    sample_points = np.array([
        curve.evaluate(float(u)) for u in sample_params
    ])

    # --- Step 3: least-squares B-spline fit over chord-length params ---
    # Chord-length parameterisation of the sample points → t in [0, 1]
    diffs = np.linalg.norm(np.diff(sample_points, axis=0), axis=1)
    chord_total = float(diffs.sum())
    if chord_total < 1e-15:
        return normalize_knots(curve)

    ts = np.zeros(n + 1)
    ts[1:] = np.cumsum(diffs) / chord_total  # already in [0, 1]

    # Build degree-3 clamped knot vector via Piegl–Tiller averaging
    degree = 3
    num_ctrl = max(degree + 1, min(n + 1, 64))

    # Averaging knot placement (P&T §9.2)
    # interior knot j (1-indexed): avg of ts[j..j+degree-1] for j=1..num_ctrl-degree-1
    interior = num_ctrl - degree - 1
    interior_knots: list = []
    if interior > 0:
        for j in range(1, interior + 1):
            interior_knots.append(float(np.mean(ts[j: j + degree])))
    knots_fit = np.array(
        [0.0] * (degree + 1)
        + interior_knots
        + [1.0] * (degree + 1),
        dtype=float,
    )

    # Collocation matrix
    def _bspline_basis(t: float, k: int) -> float:
        """B-spline basis N_{k,degree}(t)."""
        u = float(t)
        d = degree
        K = knots_fit
        m = len(K)
        n_k = m - d - 1  # number of basis functions
        if k < 0 or k >= n_k:
            return 0.0
        # Cox-de Boor recursion
        N = np.zeros(m - 1)
        for ii in range(m - 1):
            N[ii] = 1.0 if K[ii] <= u < K[ii + 1] else 0.0
        # Handle right end
        if u == K[-1]:
            # Clamp: last basis function is 1 at right end
            N[-1] = 1.0 if K[-2] < K[-1] else 0.0
        for r in range(1, d + 1):
            N_new = np.zeros(m - 1 - r)
            for ii in range(m - 1 - r):
                denom1 = K[ii + r] - K[ii]
                denom2 = K[ii + r + 1] - K[ii + 1]
                left = (u - K[ii]) / denom1 * N[ii] if denom1 > 1e-15 else 0.0
                right = (K[ii + r + 1] - u) / denom2 * N[ii + 1] if denom2 > 1e-15 else 0.0
                N_new[ii] = left + right
            N = N_new
        return float(N[k]) if k < len(N) else 0.0

    A = np.zeros((n + 1, num_ctrl))
    for i, t in enumerate(ts):
        for k in range(num_ctrl):
            A[i, k] = _bspline_basis(t, k)

    ctrl, _, _, _ = np.linalg.lstsq(A, sample_points, rcond=None)

    return NurbsCurve(
        degree=degree,
        control_points=ctrl,
        knots=knots_fit,
        weights=None,
    )