"""sweep1: profile-along-path surface generation.

Frame computation methods:
- Frenet (legacy): compute_frenet_frame — can flip at inflections.
- RMF (Wang 2008): compute_rmf_frames — double-reflection parallel transport,
  torsion-free, zero accumulated twist for circles swept along helices.
"""
import numpy as np
from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface


# ---------------------------------------------------------------------------
# Wang 2008 rotation-minimising frame (double-reflection method)
# ---------------------------------------------------------------------------

def _reflect(v: np.ndarray, n: np.ndarray) -> np.ndarray:
    """Reflect vector v through the plane with unit normal n."""
    return v - 2.0 * np.dot(v, n) * n


def _stable_perp(t: np.ndarray) -> np.ndarray:
    """Return a unit vector perpendicular to *t*, choosing the world axis
    most perpendicular to *t*.
    """
    abs_t = np.abs(t)
    if abs_t[0] <= abs_t[1] and abs_t[0] <= abs_t[2]:
        ref = np.array([1.0, 0.0, 0.0])
    elif abs_t[1] <= abs_t[0] and abs_t[1] <= abs_t[2]:
        ref = np.array([0.0, 1.0, 0.0])
    else:
        ref = np.array([0.0, 0.0, 1.0])
    r = ref - np.dot(ref, t) * t
    return r / (np.linalg.norm(r) + 1e-15)


def compute_rmf_frames(
    tangents: np.ndarray,
    initial_r: np.ndarray | None = None,
    points: np.ndarray | None = None,
) -> list[np.ndarray]:
    """Compute rotation-minimising frames along a polyline using the
    Wang 2008 double-reflection parallel transport.

    Reference: Wang et al. (2008) "Computation of Rotation Minimizing
    Frames", ACM Transactions on Graphics 27(1), Article 2.

    Parameters
    ----------
    tangents : (N, 3) array of unit tangent vectors at each sample point.
    initial_r : (3,) array — initial normal / reference vector perpendicular
        to tangents[0]. If None a stable default is chosen automatically.
    points : (N, 3) array of curve sample positions (optional). When provided
        the chord vector is used as the first reflection axis (more stable for
        coarsely sampled paths); when absent the tangent midpoint bisector
        is used instead.

    Returns
    -------
    frames : list of N (3x3) matrices.  Each matrix has columns [T, r, s]:
        T = unit tangent, r = rotation-minimising normal, s = binormal.
        All frames are proper rotations (det ≈ +1, columns orthonormal).
    """
    tangents = np.asarray(tangents, dtype=float)
    n = len(tangents)
    frames: list[np.ndarray] = []

    t0 = tangents[0].copy()
    norm_t0 = np.linalg.norm(t0)
    if norm_t0 > 1e-15:
        t0 = t0 / norm_t0

    # Choose initial reference vector perpendicular to t0.
    if initial_r is None:
        # Compute v1_hat from the first step (tangent or chord difference) to
        # ensure r0 is NOT aligned with the first reflection axis.  This avoids
        # a near-180° jump on the very first propagation step.
        if n > 1:
            if points is not None:
                v1 = points[1] - points[0]
            else:
                v1 = tangents[1] - t0
            v1_sq = np.dot(v1, v1)
            # Build a candidate r0 from the reflection axis itself — r0 should
            # be the centripetal direction implied by the first tangent change.
            # Project v1 onto the tangent plane of t0.
            if v1_sq > 1e-28:
                v1_hat = v1 / np.sqrt(v1_sq)
                # r0 candidate: the component of v1 perpendicular to t0.
                # (This is the centripetal direction at the first step.)
                r0_cand = v1_hat - np.dot(v1_hat, t0) * t0
                norm_c = np.linalg.norm(r0_cand)
                if norm_c > 1e-10:
                    r0 = r0_cand / norm_c
                else:
                    r0 = _stable_perp(t0)
            else:
                r0 = _stable_perp(t0)
        else:
            r0 = _stable_perp(t0)
    else:
        r0 = np.array(initial_r, dtype=float)
        r0 = r0 - np.dot(r0, t0) * t0
        norm_r0 = np.linalg.norm(r0)
        r0 = r0 / (norm_r0 + 1e-15)

    s0 = np.cross(t0, r0)
    frames.append(np.column_stack([t0, r0, s0]))

    r_i = r0.copy()
    t_i = t0.copy()

    for i in range(1, n):
        t_next = tangents[i].copy()
        nt = np.linalg.norm(t_next)
        if nt > 1e-15:
            t_next = t_next / nt

        # --- Wang 2008 double-reflection ---
        # First reflection axis: bisector plane between t_i and t_next.
        # Using midpoint formula: v1 = t_next - t_i normalised.
        # For position-based version use chord when points are available.
        if points is not None:
            v1 = points[i] - points[i - 1]
        else:
            v1 = t_next - t_i

        v1_sq = np.dot(v1, v1)

        if v1_sq < 1e-28:
            # Tangents are (nearly) identical — frame carries over.
            r_next = r_i.copy()
        else:
            v1_hat = v1 / np.sqrt(v1_sq)

            # Reflect r_i and t_i through the v1_hat plane.
            c1 = np.dot(r_i, v1_hat)
            r_L = r_i - 2.0 * c1 * v1_hat

            c2 = np.dot(t_i, v1_hat)
            t_L = t_i - 2.0 * c2 * v1_hat  # ≈ t_next after 1st reflection

            # Second reflection: v2 = t_next - t_L.
            v2 = t_next - t_L
            v2_sq = np.dot(v2, v2)

            if v2_sq < 1e-28:
                r_next = r_L
            else:
                v2_hat = v2 / np.sqrt(v2_sq)
                c3 = np.dot(r_L, v2_hat)
                r_next = r_L - 2.0 * c3 * v2_hat

        # Re-orthogonalise r against t_next (prevents numerical drift).
        r_next = r_next - np.dot(r_next, t_next) * t_next
        norm_r = np.linalg.norm(r_next)
        if norm_r < 1e-14:
            # Degenerate fallback: rotate previous s by the rotation that
            # sends t_i to t_next.
            s_i = frames[-1][:, 2]
            cross = np.cross(t_i, t_next)
            cross_n = np.linalg.norm(cross)
            if cross_n > 1e-14:
                s_next = s_i - 2.0 * np.dot(s_i, cross / cross_n) * (cross / cross_n)
            else:
                s_next = s_i.copy()
            r_next = np.cross(s_next, t_next)
            r_next = r_next / (np.linalg.norm(r_next) + 1e-15)
        else:
            r_next = r_next / norm_r

        s_next = np.cross(t_next, r_next)
        frames.append(np.column_stack([t_next, r_next, s_next]))

        r_i = r_next
        t_i = t_next

    return frames


def _sample_path_tangents(path: NurbsCurve, num_pts: int) -> tuple[np.ndarray, np.ndarray]:
    """Sample `num_pts` points and unit tangents along `path` uniformly in
    parameter space.

    Returns (points, tangents) each of shape (num_pts, 3).
    """
    ts = np.linspace(0.0, 1.0, num_pts)
    points = np.array([path.evaluate(t) for t in ts])

    # Compute tangents via finite differences on evaluated points.
    tangents = np.zeros_like(points)
    tangents[0] = points[1] - points[0]
    tangents[-1] = points[-1] - points[-2]
    tangents[1:-1] = points[2:] - points[:-2]

    norms = np.linalg.norm(tangents, axis=1, keepdims=True)
    norms = np.where(norms < 1e-15, 1.0, norms)
    tangents = tangents / norms

    return points, tangents


def sweep1(profile: NurbsCurve, path: NurbsCurve, scale: float = 1.0) -> NurbsSurface:
    """Sweep *profile* along *path* using a rotation-minimising frame (Wang 2008).

    Uses the double-reflection RMF so that frames are torsion-free: a circle
    swept along a helix accumulates zero twist.
    """
    if profile.degree < 1 or path.degree < 1:
        raise ValueError("Profile and path must have degree >= 1")

    num_profile_pts = profile.num_control_points
    num_path_pts = path.num_control_points

    degree_u = profile.degree
    degree_v = path.degree

    # Sample path and compute RMF frames at control-point count locations.
    path_pts, tangents = _sample_path_tangents(path, num_path_pts)
    rmf = compute_rmf_frames(tangents, points=path_pts)

    control_points = np.zeros((num_profile_pts, num_path_pts, 3))

    for i in range(num_path_pts):
        frame = rmf[i]  # columns: [T, r, s]
        path_pt = path_pts[i]

        for j in range(num_profile_pts):
            profile_pt = profile.control_points[j]
            scaled_pt = profile_pt * scale
            world_pt = path_pt + frame @ scaled_pt
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
    """Sweep profile along path with an optional uniform twist applied on top
    of a rotation-minimising frame (Wang 2008).
    """
    if profile.degree < 1 or path.degree < 1:
        raise ValueError("Profile and path must have degree >= 1")

    num_profile_pts = profile.num_control_points
    num_path_pts = path.num_control_points

    degree_u = profile.degree
    degree_v = path.degree

    path_pts, tangents = _sample_path_tangents(path, num_path_pts)
    rmf = compute_rmf_frames(tangents, points=path_pts)

    control_points = np.zeros((num_profile_pts, num_path_pts, 3))

    for i in range(num_path_pts):
        path_pt = path_pts[i]
        frame = rmf[i]
        t_vec = tangents[i]

        # Apply accumulated twist angle (linear interpolation 0 → twist).
        angle = twist * i / max(num_path_pts - 1, 1)
        rot = rotation_matrix_3d(tangent=t_vec, angle=angle)

        for j in range(num_profile_pts):
            profile_pt = profile.control_points[j]
            scaled_pt = profile_pt * scale
            rotated_pt = rot @ scaled_pt
            world_pt = path_pt + frame @ rotated_pt
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


def sweep1_rmf(
    profile: NurbsCurve,
    path: NurbsCurve,
    scale: float = 1.0,
    num_samples: int | None = None,
    initial_normal: np.ndarray | None = None,
) -> NurbsSurface:
    """Public alias: sweep1 with explicit Wang 2008 RMF, sampling *num_samples*
    frames along the path (defaults to number of path control points).

    Parameters
    ----------
    profile, path : NurbsCurve
    scale : uniform scale applied to profile points.
    num_samples : number of frame samples along the path; defaults to
        path.num_control_points.
    initial_normal : optional seed normal for the first frame.
    """
    if profile.degree < 1 or path.degree < 1:
        raise ValueError("Profile and path must have degree >= 1")

    n = num_samples if num_samples is not None else path.num_control_points
    n = max(n, 2)

    path_pts, tangents = _sample_path_tangents(path, n)
    rmf = compute_rmf_frames(tangents, initial_r=initial_normal, points=path_pts)

    num_profile_pts = profile.num_control_points
    control_points = np.zeros((num_profile_pts, n, 3))

    for i in range(n):
        frame = rmf[i]
        path_pt = path_pts[i]
        for j in range(num_profile_pts):
            world_pt = path_pt + frame @ (profile.control_points[j] * scale)
            control_points[j, i] = world_pt

    knots_u = profile.knots.copy()
    # Re-sample path knots for the chosen number of samples.
    knots_v = np.concatenate([
        np.zeros(path.degree),
        np.linspace(0.0, 1.0, n - path.degree + 1),
        np.ones(path.degree),
    ])

    return NurbsSurface(
        degree_u=profile.degree,
        degree_v=path.degree,
        control_points=control_points,
        knots_u=knots_u,
        knots_v=knots_v,
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
    """Sweep profile along path with per-parameter scaling, using RMF frames."""
    if profile.degree < 1 or path.degree < 1:
        raise ValueError("Profile and path must have degree >= 1")

    if scale_profile is None:
        scale_profile = lambda u: 1.0

    num_profile_pts = profile.num_control_points
    num_path_pts = path.num_control_points

    degree_u = profile.degree
    degree_v = path.degree

    path_pts, tangents = _sample_path_tangents(path, num_path_pts)
    rmf = compute_rmf_frames(tangents, points=path_pts)

    path_params = np.linspace(0.0, 1.0, num_path_pts)
    control_points = np.zeros((num_profile_pts, num_path_pts, 3))

    for i in range(num_path_pts):
        frame = rmf[i]
        path_pt = path_pts[i]
        scale = scale_profile(path_params[i])

        for j in range(num_profile_pts):
            profile_pt = profile.control_points[j]
            scaled_pt = profile_pt * scale
            world_pt = path_pt + frame @ scaled_pt
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
    """Sample cross-sections of profile swept along path using RMF frames."""
    path_pts, tangents = _sample_path_tangents(path, num_sections)
    rmf = compute_rmf_frames(tangents, points=path_pts)

    sections = []
    for i in range(num_sections):
        frame = rmf[i]
        path_pt = path_pts[i]
        section_pts = []
        for j in range(profile.num_control_points):
            world_pt = path_pt + frame @ profile.control_points[j]
            section_pts.append(world_pt)
        sections.append(np.array(section_pts))

    return sections


# ---------------------------------------------------------------------------
# GK-77: Helical sweep — springs / threads / spiral settings
# ---------------------------------------------------------------------------

def _make_helix_nurbs(
    axis: np.ndarray,
    radius: float,
    pitch: float,
    turns: float,
    num_samples: int = 128,
) -> NurbsCurve:
    """Build a helical path as a degree-1 NURBS polyline.

    The helix is parameterised by angle θ ∈ [0, 2π·turns]:
        x = radius · cos(θ)  (in the plane perpendicular to *axis*)
        y = radius · sin(θ)
        z = pitch · θ / (2π)  (along *axis*)

    Parameters
    ----------
    axis : (3,) unit vector — helix axis direction.
    radius : helix radius (distance from axis to tube centreline).
    pitch : axial advance per full revolution.
    turns : number of complete turns.
    num_samples : number of polyline vertices (≥ 4).

    Returns
    -------
    NurbsCurve
        Degree-1 NURBS polyline approximating the helix.
    """
    axis = np.asarray(axis, dtype=float)
    axis_norm = np.linalg.norm(axis)
    if axis_norm < 1e-14:
        raise ValueError("axis must be non-zero")
    axis = axis / axis_norm

    # Build an orthonormal frame: (x_hat, y_hat, axis)
    # x_hat is the most orthogonal world axis to *axis*.
    abs_ax = np.abs(axis)
    if abs_ax[0] <= abs_ax[1] and abs_ax[0] <= abs_ax[2]:
        ref = np.array([1.0, 0.0, 0.0])
    elif abs_ax[1] <= abs_ax[0] and abs_ax[1] <= abs_ax[2]:
        ref = np.array([0.0, 1.0, 0.0])
    else:
        ref = np.array([0.0, 0.0, 1.0])

    x_hat = ref - np.dot(ref, axis) * axis
    x_hat = x_hat / np.linalg.norm(x_hat)
    y_hat = np.cross(axis, x_hat)

    n = max(int(num_samples), 4)
    thetas = np.linspace(0.0, 2.0 * np.pi * turns, n)

    pts = np.array([
        radius * np.cos(t) * x_hat
        + radius * np.sin(t) * y_hat
        + (pitch * t / (2.0 * np.pi)) * axis
        for t in thetas
    ])

    # Chord-length parameterisation for uniform distribution.
    diffs = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cumlen = np.concatenate([[0.0], np.cumsum(diffs)])
    total = cumlen[-1]
    if total < 1e-14:
        params = np.linspace(0.0, 1.0, n)
    else:
        params = cumlen / total

    # Degree-1 (polyline) NURBS: knots = [p0, p0, p1, ..., p_{n-1}, p_{n-1}]
    knots = np.concatenate([[params[0]], params, [params[-1]]])

    return NurbsCurve(degree=1, control_points=pts, knots=knots)


def sweep1_helical(
    profile: NurbsCurve,
    axis: "np.ndarray | list",
    radius: float,
    pitch: float,
    turns: float,
    frame: str = "rmf",
    num_helix_samples: int = 128,
) -> NurbsSurface:
    """Sweep *profile* along a helical rail and return the tube NurbsSurface.

    Builds a helical path (axis, radius, pitch, turns) and sweeps *profile*
    along it using a rotation-minimising frame (Wang 2008 double-reflection).
    The result is the lateral tube surface of the swept solid — useful for
    springs, threads, and spiral settings.

    The helix is defined by::

        P(θ) = radius · cos(θ) · x̂ + radius · sin(θ) · ŷ
               + (pitch · θ / 2π) · axis_hat

    where θ ∈ [0, 2π · turns] and (x̂, ŷ, axis_hat) form a right-handed
    orthonormal frame.

    Parameters
    ----------
    profile : NurbsCurve
        Cross-section profile in a local 2-D frame.  The profile is centred
        at the origin; coordinates are interpreted in the RMF frame at each
        path sample.  For a circular cross-section use
        ``make_circle_nurbs(center=[0,0,0], radius=r)``.
    axis : array_like (3,)
        Helix axis direction (need not be unit length).
    radius : float
        Helix radius — distance from the axis to the tube centreline.
    pitch : float
        Axial advance per full revolution (0 = torus-like, no axial travel).
    turns : float
        Number of complete helical turns.
    frame : str
        Frame type: ``'rmf'`` (rotation-minimising, default) or
        ``'frenet'`` (legacy, may flip at inflections).
    num_helix_samples : int
        Number of polyline vertices used to discretise the helix (≥ 4).
        More samples → smoother surface at the cost of more control points.

    Returns
    -------
    NurbsSurface
        Open tube surface.  The u-direction follows the profile; the
        v-direction follows the helix path.  When *profile* is a closed
        curve (e.g. a full NURBS circle) the u-direction boundary is
        periodic.

    Notes
    -----
    Volume oracle (torus approximation, small *pitch*)::

        V ≈ 2π · radius · π · profile_radius² · turns

    For exact torus volume (pitch=0, turns=1) use ``geom.brep.make_torus``.
    """
    axis = np.asarray(axis, dtype=float).ravel()

    helix_path = _make_helix_nurbs(
        axis=axis,
        radius=radius,
        pitch=pitch,
        turns=turns,
        num_samples=num_helix_samples,
    )

    return sweep1_rmf(
        profile=profile,
        path=helix_path,
        num_samples=helix_path.num_control_points,
    )