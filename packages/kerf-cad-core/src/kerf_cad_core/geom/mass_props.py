"""Mass properties (volume, centroid) for a closed B-rep Body.

Algorithm
---------
Uses the divergence theorem (Gauss's theorem) to convert volume integrals
into surface integrals over the Body's boundary faces::

    Volume  = (1/3) ∬_∂Ω  r · n  dA
    Cx · V  = (1/2) ∬_∂Ω  x² · n_x  dA
    Cy · V  = (1/2) ∬_∂Ω  y² · n_y  dA
    Cz · V  = (1/2) ∬_∂Ω  z² · n_z  dA

where **n** is the *outward* surface normal and dA is the area element.

**Planar faces** are handled by the 2-D Green's theorem, reducing each
surface integral to a 1-D line integral around the face boundary.
GL quadrature on each coedge makes this exact for polynomial+trigonometric
integrands (box, tetra: exact to machine eps; cylinder caps with circular
boundary: exponentially converging).

**Curved faces** (Cylinder lateral, Sphere, Torus) are handled by
Gauss–Legendre quadrature on the natural parametric domain (u, v).

Hermetic: depends only on numpy (already required by geom/brep.py) and the
standard library.  No OCCT, no external C extensions.
"""

from __future__ import annotations

import math
from typing import Dict

import numpy as np

from kerf_cad_core.geom.brep import (
    Body,
    Face,
    Plane,
    CylinderSurface,
    SphereSurface,
    TorusSurface,
)

# ---------------------------------------------------------------------------
# Gauss–Legendre quadrature nodes and weights, cached
# ---------------------------------------------------------------------------

_GL_CACHE: Dict[int, tuple] = {}


def _gl(n: int):
    """Gauss–Legendre nodes and weights on [-1, 1] (cached)."""
    if n not in _GL_CACHE:
        from numpy.polynomial.legendre import leggauss
        _GL_CACHE[n] = leggauss(n)
    return _GL_CACHE[n]


# ---------------------------------------------------------------------------
# Finite-difference surface element (for curved non-planar faces)
# ---------------------------------------------------------------------------

_FD_H = 1e-6  # finite-difference step size


def _surface_element(surface, u: float, v: float):
    """Return (point, area-weighted normal N) at parametric (u, v).

    N = ∂r/∂u × ∂r/∂v  (magnitude = area element dA, direction = parametric
    normal — caller applies ``face.orientation`` sign).
    """
    p = np.asarray(surface.evaluate(u, v), dtype=float)
    pu = np.asarray(surface.evaluate(u + _FD_H, v), dtype=float)
    pv = np.asarray(surface.evaluate(u, v + _FD_H), dtype=float)
    du = (pu - p) / _FD_H
    dv = (pv - p) / _FD_H
    return p, np.cross(du, dv)


# ---------------------------------------------------------------------------
# 2-D Gauss integration over a rectangular parametric domain
# ---------------------------------------------------------------------------

def _gauss_integrate_2d(surface, u_lo, u_hi, v_lo, v_hi, orient: float, n: int):
    """Integrate divergence-theorem integrands over [u_lo,u_hi]×[v_lo,v_hi].

    Returns (dV, dMx, dMy, dMz) where:
        dV  = (1/3) ∬ r · N_eff  du dv
        dMi = (1/2) ∬ i² · N_eff_i  du dv   (i ∈ {x,y,z})
    and N_eff = orient * (∂r/∂u × ∂r/∂v).
    """
    xi, wi = _gl(n)
    u_mid, u_h = 0.5 * (u_lo + u_hi), 0.5 * (u_hi - u_lo)
    v_mid, v_h = 0.5 * (v_lo + v_hi), 0.5 * (v_hi - v_lo)
    us = u_mid + u_h * xi
    vs = v_mid + v_h * xi

    dV = dMx = dMy = dMz = 0.0
    for i in range(n):
        for j in range(n):
            p, N = _surface_element(surface, us[i], vs[j])
            Neff = orient * N
            w = wi[i] * wi[j] * u_h * v_h
            x, y, z = p
            nx, ny, nz = Neff
            dV  += (x*nx + y*ny + z*nz) * w
            dMx += x*x*nx * w
            dMy += y*y*ny * w
            dMz += z*z*nz * w

    return dV / 3.0, dMx / 2.0, dMy / 2.0, dMz / 2.0


# ---------------------------------------------------------------------------
# Planar face: exact boundary-integral via Green's theorem
# ---------------------------------------------------------------------------
# For a planar face with constant outward normal **n** = (nx, ny, nz) and
# a local 2-D orthonormal frame  e1, e2  (so that n = e1 × e2 and the
# surface is r = origin + u·e1 + v·e2), the divergence-theorem integrands
# reduce to line integrals around the face boundary ∂F.
#
# Key relations (Green's theorem in local (u,v)):
#
#   area             = (1/2) ∮  (−v du + u dv)
#   ∬ u dA           = (1/2) ∮  u² dv
#   ∬ v dA           = −(1/2) ∮  v² du
#   ∬ u² dA          = (1/3) ∮  u³ dv
#   ∬ v² dA          = −(1/3) ∮  v³ du
#   ∬ uv dA          = (1/2) ∮  u²v dv
#
# With  x = ox + u·e1x + v·e2x  (and similarly for y, z):
#   ∬ x dA = ox·A + e1x·∬u dA + e2x·∬v dA
#   ∬ x² dA = ox²·A + 2·ox·e1x·∬u dA + 2·ox·e2x·∬v dA
#            + e1x²·∬u² dA + 2·e1x·e2x·∬uv dA + e2x²·∬v² dA
#
# Volume contribution (n ⊥ e1, n ⊥ e2, so n·r = n·origin everywhere):
#   dV = (1/3) · (n·origin) · area
#
# These line integrals are computed by GL quadrature on each coedge;
# the tangent dr/dt is approximated by finite-difference.
# ---------------------------------------------------------------------------

_FD_H_CURVE = 1e-7  # step for curve tangent FD (used only as fallback)


def _curve_tangent(curve, t: float) -> np.ndarray:
    """Return dr/dt of a curve at parameter t.

    Uses the analytic ``derivative(t)`` method when available (``Line3``,
    ``NurbsCurve``), otherwise falls back to finite-difference.
    """
    if hasattr(curve, "derivative"):
        return np.asarray(curve.derivative(t, order=1), dtype=float)
    p0 = np.asarray(curve.evaluate(t), dtype=float)
    p1 = np.asarray(curve.evaluate(t + _FD_H_CURVE), dtype=float)
    return (p1 - p0) / _FD_H_CURVE


def _planar_face_integrals(face: Face, n_hat: np.ndarray, quad_order: int):
    """Exact mass-properties integrals for a planar face via Green's theorem.

    Returns (dV, dMx, dMy, dMz).
    """
    surface = face.surface  # must be a Plane
    origin = surface.origin   # r0 of the plane
    # Build an orthonormal frame (e1, e2) in the plane.  The Plane surface
    # stores x_axis and y_axis which may not be orthogonal (they come from
    # vertex differences).  We construct e1 = unit(x_axis) and
    # e2 = n × e1, which is guaranteed to be orthogonal to e1 and in-plane.
    e1 = np.asarray(surface.x_axis, dtype=float)
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(n_hat, e1)
    e2 = e2 / np.linalg.norm(e2)

    ox, oy, oz = origin
    e1x, e1y, e1z = e1
    e2x, e2y, e2z = e2

    # Line-integral accumulators (Green's theorem in (u,v))
    A = 0.0     # area             = (1/2) ∮ -v du + u dv
    Iu  = 0.0   # ∬ u dA           = (1/2) ∮ u² dv
    Iv  = 0.0   # ∬ v dA           = -(1/2) ∮ v² du
    Iuu = 0.0   # ∬ u² dA          = (1/3) ∮ u³ dv
    Ivv = 0.0   # ∬ v² dA          = -(1/3) ∮ v³ du
    Iuv = 0.0   # ∬ uv dA          = (1/2) ∮ u²v dv

    xi, wi = _gl(quad_order)
    outer = face.outer_loop()
    if outer is None:
        return 0.0, 0.0, 0.0, 0.0

    for ce in outer.coedges:
        edge = ce.edge
        t0 = edge.t0 if ce.orientation else edge.t1
        t1 = edge.t1 if ce.orientation else edge.t0
        t_mid = 0.5 * (t0 + t1)
        t_half = 0.5 * (t1 - t0)

        for k in range(quad_order):
            t = t_mid + t_half * xi[k]
            wk = wi[k] * t_half

            p = np.asarray(edge.curve.evaluate(t), dtype=float)
            dp = _curve_tangent(edge.curve, t)

            # Local coordinates
            d = p - origin
            u = float(np.dot(d, e1))
            v = float(np.dot(d, e2))
            du_dt = float(np.dot(dp, e1))
            dv_dt = float(np.dot(dp, e2))

            # Accumulate Green's-theorem contributions weighted by wk
            A   += 0.5 * (-v * du_dt + u * dv_dt) * wk
            Iu  += 0.5 * u * u * dv_dt * wk
            Iv  += -0.5 * v * v * du_dt * wk
            Iuu += (1.0/3.0) * u * u * u * dv_dt * wk
            Ivv += -(1.0/3.0) * v * v * v * du_dt * wk
            Iuv += 0.5 * u * u * v * dv_dt * wk

    # Volume: dV = (1/3) * (n · origin) * area
    n_dot_origin = float(np.dot(n_hat, origin))
    dV = n_dot_origin * A / 3.0

    # Centroid numerators: (1/2) * n_c * ∬ c² dA  for c ∈ {x, y, z}
    #
    # ∬ x² dA = ox²*A + 2*ox*e1x*Iu + 2*ox*e2x*Iv + e1x²*Iuu + 2*e1x*e2x*Iuv + e2x²*Ivv
    Ix2 = ox*ox*A + 2.0*ox*e1x*Iu + 2.0*ox*e2x*Iv + e1x*e1x*Iuu + 2.0*e1x*e2x*Iuv + e2x*e2x*Ivv
    Iy2 = oy*oy*A + 2.0*oy*e1y*Iu + 2.0*oy*e2y*Iv + e1y*e1y*Iuu + 2.0*e1y*e2y*Iuv + e2y*e2y*Ivv
    Iz2 = oz*oz*A + 2.0*oz*e1z*Iu + 2.0*oz*e2z*Iv + e1z*e1z*Iuu + 2.0*e1z*e2z*Iuv + e2z*e2z*Ivv

    nx, ny, nz = n_hat
    dMx = 0.5 * nx * Ix2
    dMy = 0.5 * ny * Iy2
    dMz = 0.5 * nz * Iz2

    return dV, dMx, dMy, dMz


# ---------------------------------------------------------------------------
# CylinderSurface v-bounds inferred from topology
# ---------------------------------------------------------------------------

def _cylinder_v_bounds(face: Face, surface: CylinderSurface) -> tuple:
    """Height range [v_lo, v_hi] of the cylinder lateral face from its loop."""
    outer = face.outer_loop()
    if outer is None:
        return 0.0, 1.0
    vs = [float(np.dot(surface.axis, np.asarray(ce.start_point(), dtype=float) - surface.center))
          for ce in outer.coedges]
    return (min(vs), max(vs)) if vs else (0.0, 1.0)


# ---------------------------------------------------------------------------
# Per-face dispatch
# ---------------------------------------------------------------------------

def _face_contribution(face: Face, quad_order: int):
    """Return (dV, dMx, dMy, dMz) for one face."""
    surface = face.surface
    orient = 1.0 if face.orientation else -1.0

    if isinstance(surface, Plane):
        n_hat = np.asarray(surface.normal(0.0, 0.0), dtype=float) * orient
        return _planar_face_integrals(face, n_hat, quad_order)

    if isinstance(surface, CylinderSurface):
        v_lo, v_hi = _cylinder_v_bounds(face, surface)
        return _gauss_integrate_2d(surface, 0.0, 2.0*math.pi, v_lo, v_hi, orient, quad_order)

    if isinstance(surface, SphereSurface):
        return _gauss_integrate_2d(
            surface, 0.0, 2.0*math.pi, -math.pi/2.0, math.pi/2.0, orient, quad_order
        )

    if isinstance(surface, TorusSurface):
        return _gauss_integrate_2d(
            surface, 0.0, 2.0*math.pi, 0.0, 2.0*math.pi, orient, quad_order
        )

    # Generic: NurbsSurface or unknown — read knot extents
    try:
        from kerf_cad_core.geom.nurbs import NurbsSurface
        if isinstance(surface, NurbsSurface):
            d = surface.degree_u
            u_lo = float(surface.knots_u[d])
            u_hi = float(surface.knots_u[-(d + 1)])
            d = surface.degree_v
            v_lo = float(surface.knots_v[d])
            v_hi = float(surface.knots_v[-(d + 1)])
            return _gauss_integrate_2d(surface, u_lo, u_hi, v_lo, v_hi, orient, quad_order)
    except Exception:
        pass

    return 0.0, 0.0, 0.0, 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def body_mass_props(body: Body, quad_order: int = 20) -> dict:
    """Compute volume and centroid of a closed solid *body*.

    Parameters
    ----------
    body:
        A closed (watertight) :class:`~kerf_cad_core.geom.brep.Body`.  All
        solids and free shells are included.
    quad_order:
        Number of Gauss–Legendre points per parametric direction (for curved
        faces) and per coedge (for planar faces).  Default 20 gives relative
        error < 1e-8 for smooth analytic primitives.

    Returns
    -------
    dict with keys:
        ``"volume"``   – total volume (positive for outward normals).
        ``"centroid"`` – numpy array ``[cx, cy, cz]``.

    Algorithm
    ---------
    Divergence theorem::

        V = (1/3) ∬_∂Ω  r · n  dA
        C = (1/(2V)) * (∬_∂Ω x²n_x dA,  ∬_∂Ω y²n_y dA,  ∬_∂Ω z²n_z dA)

    Planar faces use Green's theorem (boundary line integrals, exact for
    polynomial + trigonometric boundary curves).  Curved faces use 2-D
    Gauss–Legendre quadrature on the natural parametric domain.
    """
    dV_tot = dMx_tot = dMy_tot = dMz_tot = 0.0

    for face in body.all_faces():
        dV, dMx, dMy, dMz = _face_contribution(face, quad_order)
        dV_tot  += dV
        dMx_tot += dMx
        dMy_tot += dMy
        dMz_tot += dMz

    volume = dV_tot
    if abs(volume) < 1e-30:
        centroid = np.zeros(3)
    else:
        centroid = np.array([dMx_tot / volume, dMy_tot / volume, dMz_tot / volume])

    return {"volume": volume, "centroid": centroid}
