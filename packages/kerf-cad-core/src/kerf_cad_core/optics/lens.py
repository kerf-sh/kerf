"""
kerf_cad_core.optics.lens — pure-Python geometric optics & lens design formulas.

Implements the following public functions:

  lensmaker(R1, R2, n, d)
      Lensmaker's equation: thin-lens (d=0) and thick-lens focal length.

  thin_lens_imaging(f, s_o)
      Thin-lens / Gaussian imaging: image distance, magnification, image type.

  mirror_imaging(R, s_o)
      Spherical mirror imaging: image distance, magnification, image type.

  two_lens_system(f1, f2, d)
      Two-lens system: effective focal length, principal-plane locations.

  abcd_free_space(d)
      ABCD ray-transfer matrix for free-space propagation.

  abcd_refraction(n1, n2, R)
      ABCD ray-transfer matrix for refraction at a spherical interface.

  abcd_thin_lens(f)
      ABCD ray-transfer matrix for a thin lens.

  abcd_thick_lens(n1, n_lens, n2, R1, R2, d)
      ABCD ray-transfer matrix for a thick lens (two refracting surfaces + gap).

  abcd_mirror(R)
      ABCD ray-transfer matrix for a spherical mirror.

  abcd_system(matrices)
      Cascade (multiply) a list of ABCD matrices into the system matrix.

  fnumber(f, D)
      F-number (f/#) from focal length and entrance-pupil diameter.

  numerical_aperture(n, half_angle_rad)
      Numerical aperture NA = n * sin(theta).

  depth_of_field(f, N, c, s_o)
      Total depth of field (DOF) for a camera lens.

  hyperfocal_distance(f, N, c)
      Hyperfocal distance H.

  airy_spot_radius(wavelength, N)
      Diffraction-limited Airy disk radius (first dark ring).

  snell(n1, theta1_rad, n2)
      Snell's law: transmitted angle. Warns on TIR.

  critical_angle(n1, n2)
      Critical angle for total internal reflection. Warns if n1 <= n2.

  brewster_angle(n1, n2)
      Brewster's angle for zero p-polarisation reflectance.

  prism_deviation(n, apex_rad, theta_i_rad)
      Minimum deviation angle for an equilateral prism.

  chromatic_aberration(f, V)
      Longitudinal chromatic aberration (Abbe number).

  achromat_powers(f_total, V1, V2)
      Crown/flint element powers for an achromatic doublet.

All functions return a plain dict:
    success → {"ok": True, ...computed fields...}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise. Virtual-image / TIR / invalid-index conditions are
flagged via the `warnings` module and reflected in the returned dict.

Units
-----
Lengths  — metres (m) unless noted mm in parameter name.
Angles   — radians unless noted _deg.
Wavelengths — metres (m).

References
----------
Hecht, E. — "Optics", 5th ed. (2017), Chapters 5–6.
Smith, W.J. — "Modern Optical Engineering", 4th ed. (2008).
Born & Wolf — "Principles of Optics", 7th ed. (1999), Chapter 4.

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings
from typing import Any
from kerf_cad_core._guards import _err, _guard_finite, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_index(name: str, value: Any) -> str | None:
    """Return an error string if *value* is not a valid refractive index (>= 1)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 1.0:
        msg = f"{name}={v} is below 1.0; refractive index must be >= 1"
        warnings.warn(msg, UserWarning, stacklevel=3)
        return msg
    return None


# ---------------------------------------------------------------------------
# 1. Lensmaker's equation
# ---------------------------------------------------------------------------

def lensmaker(
    R1: float,
    R2: float,
    n: float,
    d: float = 0.0,
) -> dict:
    """
    Lensmaker's equation for a lens in air (n_medium = 1).

    Thin lens (d=0):
        1/f = (n-1) * (1/R1 - 1/R2)

    Thick lens (d > 0) — exact formula:
        1/f = (n-1) * [1/R1 - 1/R2 + (n-1)*d / (n*R1*R2)]

    Sign convention (Cartesian):
        R > 0  — centre of curvature to the right of surface
        R < 0  — centre of curvature to the left
        R = inf — flat surface (pass math.inf or 1e308)

    Parameters
    ----------
    R1 : float
        Radius of curvature of the first surface (m). Non-zero finite or ±inf.
    R2 : float
        Radius of curvature of the second surface (m). Non-zero finite or ±inf.
    n : float
        Refractive index of lens material (>= 1.0).
    d : float
        Centre thickness of lens (m). 0 for thin-lens approximation.

    Returns
    -------
    dict
        ok        : True
        f_m       : focal length (m); inf if power = 0 (flat/concentric lens)
        power_m   : optical power (m⁻¹ = dioptres)
        lens_type : "converging" / "diverging" / "afocal"
        R1_m, R2_m, n, d_m : inputs echoed
    """
    err = _guard_index("n", n)
    if err:
        return _err(err)
    err = _guard_nonneg("d", d)
    if err:
        return _err(err)

    # Allow R = inf (flat surface); require non-zero
    try:
        R1_f = float(R1)
        R2_f = float(R2)
    except (TypeError, ValueError):
        return _err("R1 and R2 must be numbers")

    if not math.isfinite(R1_f) and R1_f == 0.0:
        return _err("R1 must be non-zero")
    if not math.isfinite(R2_f) and R2_f == 0.0:
        return _err("R2 must be non-zero")
    if math.isfinite(R1_f) and R1_f == 0.0:
        return _err("R1 must be non-zero (use math.inf for flat surface)")
    if math.isfinite(R2_f) and R2_f == 0.0:
        return _err("R2 must be non-zero (use math.inf for flat surface)")

    n_f = float(n)
    d_f = float(d)

    inv_R1 = 1.0 / R1_f if math.isfinite(R1_f) else 0.0
    inv_R2 = 1.0 / R2_f if math.isfinite(R2_f) else 0.0

    if d_f == 0.0:
        # Thin-lens lensmaker
        power = (n_f - 1.0) * (inv_R1 - inv_R2)
    else:
        # Thick-lens lensmaker (Hecht §5.2.3)
        thick_term = (n_f - 1.0) * d_f / (n_f * R1_f * R2_f) if (
            math.isfinite(R1_f) and math.isfinite(R2_f)
        ) else 0.0
        power = (n_f - 1.0) * (inv_R1 - inv_R2 + thick_term)

    if power == 0.0:
        f = math.inf
        lens_type = "afocal"
    else:
        f = 1.0 / power
        lens_type = "converging" if f > 0 else "diverging"

    return {
        "ok": True,
        "f_m": f,
        "power_m": power,
        "lens_type": lens_type,
        "R1_m": R1_f,
        "R2_m": R2_f,
        "n": n_f,
        "d_m": d_f,
    }


# ---------------------------------------------------------------------------
# 2. Thin-lens imaging (Gaussian lens formula)
# ---------------------------------------------------------------------------

def thin_lens_imaging(
    f: float,
    s_o: float,
) -> dict:
    """
    Thin-lens imaging formula (Gaussian form).

    Formula:
        1/s_i = 1/f - 1/s_o      → s_i = f*s_o / (s_o - f)
        m = -s_i / s_o

    Sign convention (real is positive):
        s_o > 0  — real object (to the left of lens)
        s_i > 0  — real image (to the right)
        s_i < 0  — virtual image (same side as object)
        m < 0    — inverted image; |m| > 1 → magnified

    Parameters
    ----------
    f   : float  Focal length (m). May be negative (diverging lens).
    s_o : float  Object distance (m). Must be non-zero.

    Returns
    -------
    dict
        ok           : True
        s_i_m        : image distance (m)
        magnification: lateral magnification m
        image_type   : "real" or "virtual"
        erect        : True if image is upright (m > 0)
        f_m, s_o_m   : inputs echoed
    """
    err = _guard_finite("f", f)
    if err:
        return _err(err)
    err = _guard_finite("s_o", s_o)
    if err:
        return _err(err)

    f_f = float(f)
    so = float(s_o)

    if so == 0.0:
        return _err("s_o must be non-zero")
    if f_f == 0.0:
        return _err("f must be non-zero")

    denom = so - f_f
    if denom == 0.0:
        # Object at focal point — image at infinity
        s_i = math.inf
        m = math.inf
        image_type = "real"
        erect = False
    else:
        s_i = f_f * so / denom
        m = -s_i / so
        image_type = "real" if s_i > 0 else "virtual"
        erect = m > 0

    if image_type == "virtual":
        warnings.warn(
            f"thin_lens_imaging: virtual image at s_i={s_i:.4g} m (s_o={so}, f={f_f})",
            UserWarning,
            stacklevel=2,
        )

    return {
        "ok": True,
        "s_i_m": s_i,
        "magnification": m,
        "image_type": image_type,
        "erect": erect,
        "f_m": f_f,
        "s_o_m": so,
    }


# ---------------------------------------------------------------------------
# 3. Spherical mirror imaging
# ---------------------------------------------------------------------------

def mirror_imaging(
    R: float,
    s_o: float,
) -> dict:
    """
    Spherical mirror imaging formula.

    Mirror focal length: f = R/2

    Formula (using sign convention: distances positive in front of mirror):
        1/s_i + 1/s_o = 2/R = 1/f
        m = -s_i / s_o

    Sign convention:
        R > 0  — concave (converging) mirror
        R < 0  — convex (diverging) mirror
        s_o > 0 — real object
        s_i > 0 — real image (in front of mirror)
        s_i < 0 — virtual image (behind mirror)

    Parameters
    ----------
    R   : float  Radius of curvature (m). Non-zero.
    s_o : float  Object distance (m). Must be non-zero.

    Returns
    -------
    dict
        ok           : True
        s_i_m        : image distance (m)
        magnification: lateral magnification
        f_m          : focal length R/2 (m)
        mirror_type  : "concave" / "convex"
        image_type   : "real" or "virtual"
        erect        : True if upright
        R_m, s_o_m   : inputs echoed
    """
    err = _guard_finite("R", R)
    if err:
        return _err(err)
    err = _guard_finite("s_o", s_o)
    if err:
        return _err(err)

    R_f = float(R)
    so = float(s_o)

    if R_f == 0.0:
        return _err("R must be non-zero")
    if so == 0.0:
        return _err("s_o must be non-zero")

    f = R_f / 2.0
    mirror_type = "concave" if R_f > 0 else "convex"

    denom = 1.0 / f - 1.0 / so
    if denom == 0.0 or not math.isfinite(denom):
        s_i = math.inf
        m = math.inf
        image_type = "real"
        erect = False
    else:
        s_i = 1.0 / denom
        m = -s_i / so
        image_type = "real" if s_i > 0 else "virtual"
        erect = m > 0

    if image_type == "virtual":
        warnings.warn(
            f"mirror_imaging: virtual image at s_i={s_i:.4g} m",
            UserWarning,
            stacklevel=2,
        )

    return {
        "ok": True,
        "s_i_m": s_i,
        "magnification": m,
        "f_m": f,
        "mirror_type": mirror_type,
        "image_type": image_type,
        "erect": erect,
        "R_m": R_f,
        "s_o_m": so,
    }


# ---------------------------------------------------------------------------
# 4. Two-lens system
# ---------------------------------------------------------------------------

def two_lens_system(
    f1: float,
    f2: float,
    d: float,
) -> dict:
    """
    Two thin-lens system: effective focal length and principal-plane positions.

    Effective focal length (Hecht §5.2.4):
        1/f_eff = 1/f1 + 1/f2 - d/(f1*f2)

    Principal-plane separations from respective lenses:
        delta_H  = -f_eff * d / f2     (from L1 to front principal plane H)
        delta_H' =  f_eff * d / f1     (from L2 to rear principal plane H')
        (positive → to the right)

    Parameters
    ----------
    f1 : float  Focal length of first lens (m). Non-zero.
    f2 : float  Focal length of second lens (m). Non-zero.
    d  : float  Separation between the two lenses (m). Non-negative.

    Returns
    -------
    dict
        ok            : True
        f_eff_m       : effective focal length (m)
        power_m       : combined optical power (m⁻¹)
        delta_H_m     : distance from L1 to front principal plane H (m)
        delta_H_prime_m: distance from L2 to rear principal plane H' (m)
        lens_type     : "converging" / "diverging" / "afocal"
        f1_m, f2_m, d_m: inputs echoed
    """
    err = _guard_finite("f1", f1)
    if err:
        return _err(err)
    err = _guard_finite("f2", f2)
    if err:
        return _err(err)
    err = _guard_nonneg("d", d)
    if err:
        return _err(err)

    f1_f = float(f1)
    f2_f = float(f2)
    d_f = float(d)

    if f1_f == 0.0:
        return _err("f1 must be non-zero")
    if f2_f == 0.0:
        return _err("f2 must be non-zero")

    power = 1.0 / f1_f + 1.0 / f2_f - d_f / (f1_f * f2_f)

    if power == 0.0:
        f_eff = math.inf
        lens_type = "afocal"
        delta_H = math.nan
        delta_Hp = math.nan
    else:
        f_eff = 1.0 / power
        lens_type = "converging" if f_eff > 0 else "diverging"
        delta_H = -f_eff * d_f / f2_f
        delta_Hp = f_eff * d_f / f1_f

    return {
        "ok": True,
        "f_eff_m": f_eff,
        "power_m": power,
        "delta_H_m": delta_H,
        "delta_H_prime_m": delta_Hp,
        "lens_type": lens_type,
        "f1_m": f1_f,
        "f2_m": f2_f,
        "d_m": d_f,
    }


# ---------------------------------------------------------------------------
# 5. ABCD ray-transfer matrices
# ---------------------------------------------------------------------------

def abcd_free_space(d: float) -> dict:
    """
    ABCD ray-transfer matrix for free-space propagation (distance d).

    M = [[1, d],
         [0, 1]]

    Parameters
    ----------
    d : float  Propagation distance (m). Must be >= 0.

    Returns
    -------
    dict  ok, A, B, C, D, d_m
    """
    err = _guard_nonneg("d", d)
    if err:
        return _err(err)
    d_f = float(d)
    return {"ok": True, "A": 1.0, "B": d_f, "C": 0.0, "D": 1.0, "d_m": d_f}


def abcd_refraction(n1: float, n2: float, R: float) -> dict:
    """
    ABCD ray-transfer matrix for refraction at a spherical interface.

    M = [[1,        0],
         [-(n2-n1)/(n2*R),  n1/n2]]

    R > 0 — centre of curvature in medium n2 (right)
    R = inf (flat surface) — use math.inf

    Parameters
    ----------
    n1 : float  Refractive index of incident medium (>= 1).
    n2 : float  Refractive index of transmitted medium (>= 1).
    R  : float  Radius of curvature (m). Non-zero or ±inf.

    Returns
    -------
    dict  ok, A, B, C, D, n1, n2, R_m
    """
    for nm, val in [("n1", n1), ("n2", n2)]:
        err = _guard_index(nm, val)
        if err:
            return _err(err)

    try:
        R_f = float(R)
    except (TypeError, ValueError):
        return _err("R must be a number")
    if math.isfinite(R_f) and R_f == 0.0:
        return _err("R must be non-zero (use math.inf for flat surface)")

    n1_f = float(n1)
    n2_f = float(n2)

    C = -(n2_f - n1_f) / (n2_f * R_f) if math.isfinite(R_f) else 0.0

    return {
        "ok": True,
        "A": 1.0,
        "B": 0.0,
        "C": C,
        "D": n1_f / n2_f,
        "n1": n1_f,
        "n2": n2_f,
        "R_m": R_f,
    }


def abcd_thin_lens(f: float) -> dict:
    """
    ABCD ray-transfer matrix for a thin lens of focal length f.

    M = [[1,    0],
         [-1/f, 1]]

    Parameters
    ----------
    f : float  Focal length (m). Non-zero.

    Returns
    -------
    dict  ok, A, B, C, D, f_m
    """
    err = _guard_finite("f", f)
    if err:
        return _err(err)
    f_f = float(f)
    if f_f == 0.0:
        return _err("f must be non-zero")

    return {"ok": True, "A": 1.0, "B": 0.0, "C": -1.0 / f_f, "D": 1.0, "f_m": f_f}


def abcd_thick_lens(
    n1: float,
    n_lens: float,
    n2: float,
    R1: float,
    R2: float,
    d: float,
) -> dict:
    """
    ABCD ray-transfer matrix for a thick lens.

    Computed as M = M_refraction2 @ M_freespace @ M_refraction1.

    Parameters
    ----------
    n1     : float  Refractive index of object-space medium (>= 1).
    n_lens : float  Refractive index of lens material (>= 1).
    n2     : float  Refractive index of image-space medium (>= 1).
    R1     : float  First-surface radius of curvature (m). Non-zero or ±inf.
    R2     : float  Second-surface radius of curvature (m). Non-zero or ±inf.
    d      : float  Centre thickness (m). Must be >= 0.

    Returns
    -------
    dict  ok, A, B, C, D, plus input echoes
    """
    m1 = abcd_refraction(n1, n_lens, R1)
    if not m1["ok"]:
        return m1
    m_gap = abcd_free_space(d)
    if not m_gap["ok"]:
        return m_gap
    m2 = abcd_refraction(n_lens, n2, R2)
    if not m2["ok"]:
        return m2

    # Cascade: result = m2 @ m_gap @ m1
    result = abcd_system([m2, m_gap, m1])
    if not result["ok"]:
        return result

    result.update({
        "n1": float(n1),
        "n_lens": float(n_lens),
        "n2": float(n2),
        "R1_m": float(R1),
        "R2_m": float(R2),
        "d_m": float(d),
    })
    return result


def abcd_mirror(R: float) -> dict:
    """
    ABCD ray-transfer matrix for a spherical mirror.

    In reflection convention (ray continues in same direction after folding):
        M = [[1,    0  ],
             [-2/R, 1  ]]

    R > 0 — concave (converging) mirror.
    R < 0 — convex (diverging) mirror.
    R = inf — flat mirror (returns [[1,0],[0,1]]).

    Parameters
    ----------
    R : float  Radius of curvature (m). Non-zero or ±inf.

    Returns
    -------
    dict  ok, A, B, C, D, R_m
    """
    try:
        R_f = float(R)
    except (TypeError, ValueError):
        return _err("R must be a number")
    if not math.isfinite(R_f):
        # Flat mirror — identity
        return {"ok": True, "A": 1.0, "B": 0.0, "C": 0.0, "D": 1.0, "R_m": R_f}
    if R_f == 0.0:
        return _err("R must be non-zero")

    C = -2.0 / R_f
    return {"ok": True, "A": 1.0, "B": 0.0, "C": C, "D": 1.0, "R_m": R_f}


def abcd_system(matrices: list) -> dict:
    """
    Cascade a list of ABCD matrices into the system matrix.

    The first element in *matrices* is the last optical element encountered
    by the ray (right-to-left multiplication order):
        M_sys = M[0] @ M[1] @ ... @ M[N-1]

    Each element in *matrices* must be a dict with keys A, B, C, D (as
    returned by the abcd_* functions above) or a plain 2×2 list/tuple.

    Parameters
    ----------
    matrices : list  List of ABCD matrix dicts or [[A,B],[C,D]] arrays.

    Returns
    -------
    dict  ok, A, B, C, D
    """
    if not matrices:
        return _err("matrices list must not be empty")

    def _extract(m):
        if isinstance(m, dict):
            try:
                return float(m["A"]), float(m["B"]), float(m["C"]), float(m["D"])
            except KeyError as exc:
                raise ValueError(f"Matrix dict missing key {exc}") from exc
        # Assume 2x2 list/tuple
        try:
            return float(m[0][0]), float(m[0][1]), float(m[1][0]), float(m[1][1])
        except (IndexError, TypeError, KeyError) as exc:
            raise ValueError(f"Cannot extract ABCD from {m!r}: {exc}") from exc

    try:
        A, B, C, D = _extract(matrices[-1])
        for m in reversed(matrices[:-1]):
            a, b, c, d = _extract(m)
            # Matrix multiply: [a,b;c,d] @ [A,B;C,D]
            A_new = a * A + b * C
            B_new = a * B + b * D
            C_new = c * A + d * C
            D_new = c * B + d * D
            A, B, C, D = A_new, B_new, C_new, D_new
    except (ValueError, TypeError) as exc:
        return _err(str(exc))

    return {"ok": True, "A": A, "B": B, "C": C, "D": D}


# ---------------------------------------------------------------------------
# 6. F-number
# ---------------------------------------------------------------------------

def fnumber(f: float, D: float) -> dict:
    """
    F-number (f/#) of a lens.

    N = f / D

    Parameters
    ----------
    f : float  Focal length (m). Must be > 0.
    D : float  Entrance-pupil diameter (m). Must be > 0.

    Returns
    -------
    dict  ok, f_number, f_m, D_m
    """
    err = _guard_positive("f", f)
    if err:
        return _err(err)
    err = _guard_positive("D", D)
    if err:
        return _err(err)

    f_f = float(f)
    D_f = float(D)
    N = f_f / D_f

    return {"ok": True, "f_number": N, "f_m": f_f, "D_m": D_f}


# ---------------------------------------------------------------------------
# 7. Numerical aperture
# ---------------------------------------------------------------------------

def numerical_aperture(n: float, half_angle_rad: float) -> dict:
    """
    Numerical aperture NA = n * sin(theta).

    Parameters
    ----------
    n             : float  Refractive index of the medium (>= 1).
    half_angle_rad: float  Half-angle of the acceptance cone (rad). [0, π/2].

    Returns
    -------
    dict  ok, NA, n, half_angle_rad
    """
    err = _guard_index("n", n)
    if err:
        return _err(err)
    err = _guard_nonneg("half_angle_rad", half_angle_rad)
    if err:
        return _err(err)

    n_f = float(n)
    theta = float(half_angle_rad)

    if theta > math.pi / 2.0:
        return _err("half_angle_rad must be in [0, π/2]")

    NA = n_f * math.sin(theta)

    return {"ok": True, "NA": NA, "n": n_f, "half_angle_rad": theta}


# ---------------------------------------------------------------------------
# 8. Depth of field
# ---------------------------------------------------------------------------

def depth_of_field(
    f: float,
    N: float,
    c: float,
    s_o: float,
) -> dict:
    """
    Total depth of field (DOF) for a camera lens.

    Using the standard formula (Hecht §5.6 / photographic optics):

        H = f² / (N * c)    (hyperfocal distance)

        DOF_near = s_o * (H - f) / (H + s_o - 2f)
        DOF_far  = s_o * (H - f) / (H - s_o)      [inf if s_o >= H]

        DOF_total = DOF_far - DOF_near

    Parameters
    ----------
    f   : float  Focal length (m). Must be > 0.
    N   : float  F-number (f/#). Must be > 0.
    c   : float  Circle of confusion diameter (m). Must be > 0.
    s_o : float  Subject (focus) distance from lens (m). Must be > 0.

    Returns
    -------
    dict
        ok             : True
        DOF_total_m    : total depth of field (m); inf when s_o >= H
        DOF_near_m     : near limit of acceptable focus (m from lens)
        DOF_far_m      : far limit; inf when s_o >= H
        hyperfocal_m   : hyperfocal distance H (m)
        f_m, N, c_m, s_o_m: inputs echoed
    """
    for nm, val in [("f", f), ("N", N), ("c", c), ("s_o", s_o)]:
        err = _guard_positive(nm, val)
        if err:
            return _err(err)

    f_f = float(f)
    N_f = float(N)
    c_f = float(c)
    so = float(s_o)

    H = f_f ** 2 / (N_f * c_f)

    near_denom = H + so - 2.0 * f_f
    if near_denom <= 0.0:
        # Very short subject distance — near limit behind lens
        near = 0.0
    else:
        near = so * (H - f_f) / near_denom

    far_denom = H - so
    if far_denom <= 0.0:
        # Subject beyond hyperfocal — far limit at infinity
        far = math.inf
    else:
        far = so * (H - f_f) / far_denom

    dof_total = far - near if math.isfinite(far) else math.inf

    return {
        "ok": True,
        "DOF_total_m": dof_total,
        "DOF_near_m": near,
        "DOF_far_m": far,
        "hyperfocal_m": H,
        "f_m": f_f,
        "N": N_f,
        "c_m": c_f,
        "s_o_m": so,
    }


# ---------------------------------------------------------------------------
# 9. Hyperfocal distance
# ---------------------------------------------------------------------------

def hyperfocal_distance(f: float, N: float, c: float) -> dict:
    """
    Hyperfocal distance H.

    H = f² / (N * c)

    At focus distance H, everything from H/2 to infinity is acceptably sharp.

    Parameters
    ----------
    f : float  Focal length (m). Must be > 0.
    N : float  F-number. Must be > 0.
    c : float  Circle of confusion (m). Must be > 0.

    Returns
    -------
    dict  ok, H_m, H_over_2_m, f_m, N, c_m
    """
    for nm, val in [("f", f), ("N", N), ("c", c)]:
        err = _guard_positive(nm, val)
        if err:
            return _err(err)

    f_f = float(f)
    N_f = float(N)
    c_f = float(c)

    H = f_f ** 2 / (N_f * c_f)

    return {
        "ok": True,
        "H_m": H,
        "H_over_2_m": H / 2.0,
        "f_m": f_f,
        "N": N_f,
        "c_m": c_f,
    }


# ---------------------------------------------------------------------------
# 10. Airy disk (diffraction-limited spot radius)
# ---------------------------------------------------------------------------

def airy_spot_radius(wavelength: float, N: float) -> dict:
    """
    Diffraction-limited Airy disk radius (radius to first dark ring).

    r_Airy = 1.22 * lambda * N

    This is the radius of the first dark ring of the Airy pattern
    (Born & Wolf §8.5.2), which defines the Rayleigh resolution criterion.

    Parameters
    ----------
    wavelength : float  Wavelength of light (m). Must be > 0.
    N          : float  F-number (f/#). Must be > 0.

    Returns
    -------
    dict  ok, r_airy_m, diameter_m, wavelength_m, N
    """
    err = _guard_positive("wavelength", wavelength)
    if err:
        return _err(err)
    err = _guard_positive("N", N)
    if err:
        return _err(err)

    lam = float(wavelength)
    N_f = float(N)

    r = 1.22 * lam * N_f

    return {
        "ok": True,
        "r_airy_m": r,
        "diameter_m": 2.0 * r,
        "wavelength_m": lam,
        "N": N_f,
    }


# ---------------------------------------------------------------------------
# 11. Snell's law
# ---------------------------------------------------------------------------

def snell(n1: float, theta1_rad: float, n2: float) -> dict:
    """
    Snell's law of refraction: n1 * sin(θ1) = n2 * sin(θ2).

    Warns (via warnings module) and sets tir=True if total internal
    reflection occurs (sin(θ2) > 1).  In that case theta2_rad is set to
    math.nan and the returned dict has tir=True.

    Parameters
    ----------
    n1         : float  Refractive index of incident medium (>= 1).
    theta1_rad : float  Angle of incidence (rad). [0, π/2].
    n2         : float  Refractive index of transmitted medium (>= 1).

    Returns
    -------
    dict
        ok          : True
        theta2_rad  : angle of refraction (rad); nan on TIR
        tir         : True if total internal reflection
        n1, n2, theta1_rad: inputs echoed
    """
    for nm, val in [("n1", n1), ("n2", n2)]:
        err = _guard_index(nm, val)
        if err:
            return _err(err)
    err = _guard_nonneg("theta1_rad", theta1_rad)
    if err:
        return _err(err)

    n1_f = float(n1)
    n2_f = float(n2)
    t1 = float(theta1_rad)

    if t1 > math.pi / 2.0:
        return _err("theta1_rad must be in [0, π/2]")

    sin2 = n1_f * math.sin(t1) / n2_f
    tir = False

    if abs(sin2) > 1.0:
        tir = True
        warnings.warn(
            f"snell: total internal reflection (sin θ2 = {sin2:.4f} > 1); "
            f"n1={n1_f}, n2={n2_f}, θ1={math.degrees(t1):.2f}°",
            UserWarning,
            stacklevel=2,
        )
        theta2 = math.nan
    else:
        theta2 = math.asin(sin2)

    return {
        "ok": True,
        "theta2_rad": theta2,
        "tir": tir,
        "n1": n1_f,
        "n2": n2_f,
        "theta1_rad": t1,
    }


# ---------------------------------------------------------------------------
# 12. Critical angle for TIR
# ---------------------------------------------------------------------------

def critical_angle(n1: float, n2: float) -> dict:
    """
    Critical angle for total internal reflection (TIR).

    θ_c = arcsin(n2 / n1)    [requires n1 > n2]

    Warns (via warnings module) if n1 <= n2 (TIR cannot occur).

    Parameters
    ----------
    n1 : float  Refractive index of denser medium (>= 1). Must be > n2.
    n2 : float  Refractive index of less-dense medium (>= 1).

    Returns
    -------
    dict
        ok               : True
        theta_c_rad      : critical angle (rad); nan if n1 <= n2
        theta_c_deg      : critical angle (degrees); nan if n1 <= n2
        tir_possible     : False if n1 <= n2
        n1, n2
    """
    for nm, val in [("n1", n1), ("n2", n2)]:
        err = _guard_index(nm, val)
        if err:
            return _err(err)

    n1_f = float(n1)
    n2_f = float(n2)

    if n1_f <= n2_f:
        warnings.warn(
            f"critical_angle: n1={n1_f} <= n2={n2_f}; TIR cannot occur",
            UserWarning,
            stacklevel=2,
        )
        return {
            "ok": True,
            "theta_c_rad": math.nan,
            "theta_c_deg": math.nan,
            "tir_possible": False,
            "n1": n1_f,
            "n2": n2_f,
        }

    theta_c = math.asin(n2_f / n1_f)
    return {
        "ok": True,
        "theta_c_rad": theta_c,
        "theta_c_deg": math.degrees(theta_c),
        "tir_possible": True,
        "n1": n1_f,
        "n2": n2_f,
    }


# ---------------------------------------------------------------------------
# 13. Brewster's angle
# ---------------------------------------------------------------------------

def brewster_angle(n1: float, n2: float) -> dict:
    """
    Brewster's angle (polarisation angle).

    θ_B = arctan(n2 / n1)

    At this angle, p-polarised (TM) light is not reflected.

    Parameters
    ----------
    n1 : float  Refractive index of incident medium (>= 1).
    n2 : float  Refractive index of transmitted medium (>= 1).

    Returns
    -------
    dict  ok, theta_B_rad, theta_B_deg, n1, n2
    """
    for nm, val in [("n1", n1), ("n2", n2)]:
        err = _guard_index(nm, val)
        if err:
            return _err(err)

    n1_f = float(n1)
    n2_f = float(n2)

    theta_B = math.atan(n2_f / n1_f)

    return {
        "ok": True,
        "theta_B_rad": theta_B,
        "theta_B_deg": math.degrees(theta_B),
        "n1": n1_f,
        "n2": n2_f,
    }


# ---------------------------------------------------------------------------
# 14. Prism deviation
# ---------------------------------------------------------------------------

def prism_deviation(n: float, apex_rad: float, theta_i_rad: float) -> dict:
    """
    Deviation angle for a ray through a prism.

    For a prism with apex angle A, refractive index n, and angle of incidence
    θ_i, the deviation angle δ is (Hecht §5.4):

        sin(θ_r1) = sin(θ_i) / n         (Snell at first surface)
        θ_r2 = A - θ_r1                  (geometry)
        sin(θ_t2) = n * sin(θ_r2)        (Snell at second surface)
        δ = θ_i + θ_t2 - A

    Warns on TIR at either surface.

    Parameters
    ----------
    n          : float  Refractive index of prism (>= 1).
    apex_rad   : float  Apex angle of prism (rad). (0, π/2].
    theta_i_rad: float  Angle of incidence at first surface (rad). [0, π/2).

    Returns
    -------
    dict
        ok              : True
        delta_rad       : deviation angle (rad); nan on TIR
        delta_deg       : deviation angle (degrees); nan on TIR
        theta_r1_rad    : refraction angle inside prism at surface 1 (rad)
        theta_r2_rad    : angle of incidence at surface 2 (rad)
        theta_t2_rad    : refraction angle exiting prism (rad)
        tir             : True if TIR encountered
        n, apex_rad, theta_i_rad: inputs echoed
    """
    err = _guard_index("n", n)
    if err:
        return _err(err)
    err = _guard_positive("apex_rad", apex_rad)
    if err:
        return _err(err)
    err = _guard_nonneg("theta_i_rad", theta_i_rad)
    if err:
        return _err(err)

    n_f = float(n)
    A = float(apex_rad)
    ti = float(theta_i_rad)

    if A > math.pi / 2.0:
        return _err("apex_rad must be in (0, π/2]")
    if ti >= math.pi / 2.0:
        return _err("theta_i_rad must be in [0, π/2)")

    # Snell at first surface: n_air * sin(ti) = n * sin(tr1)
    sin_tr1 = math.sin(ti) / n_f
    if abs(sin_tr1) > 1.0:
        warnings.warn(
            "prism_deviation: TIR at first surface",
            UserWarning,
            stacklevel=2,
        )
        return {
            "ok": True,
            "delta_rad": math.nan,
            "delta_deg": math.nan,
            "theta_r1_rad": math.nan,
            "theta_r2_rad": math.nan,
            "theta_t2_rad": math.nan,
            "tir": True,
            "n": n_f,
            "apex_rad": A,
            "theta_i_rad": ti,
        }
    tr1 = math.asin(sin_tr1)

    # Geometry
    tr2 = A - tr1

    # Snell at second surface: n * sin(tr2) = n_air * sin(tt2)
    sin_tt2 = n_f * math.sin(tr2)
    if abs(sin_tt2) > 1.0:
        warnings.warn(
            f"prism_deviation: TIR at second surface (sin θ_t2={sin_tt2:.4f})",
            UserWarning,
            stacklevel=2,
        )
        return {
            "ok": True,
            "delta_rad": math.nan,
            "delta_deg": math.nan,
            "theta_r1_rad": tr1,
            "theta_r2_rad": tr2,
            "theta_t2_rad": math.nan,
            "tir": True,
            "n": n_f,
            "apex_rad": A,
            "theta_i_rad": ti,
        }
    tt2 = math.asin(sin_tt2)

    delta = ti + tt2 - A

    return {
        "ok": True,
        "delta_rad": delta,
        "delta_deg": math.degrees(delta),
        "theta_r1_rad": tr1,
        "theta_r2_rad": tr2,
        "theta_t2_rad": tt2,
        "tir": False,
        "n": n_f,
        "apex_rad": A,
        "theta_i_rad": ti,
    }


# ---------------------------------------------------------------------------
# 15. Chromatic aberration (Abbe number)
# ---------------------------------------------------------------------------

def chromatic_aberration(f: float, V: float) -> dict:
    """
    Longitudinal chromatic aberration for a thin lens (Abbe number).

    The longitudinal chromatic aberration (LCA) gives the separation between
    the focal points for blue (F-line) and red (C-line) light:

        LCA = f / V

    where V is the Abbe V-number:
        V = (n_d - 1) / (n_F - n_C)

    Typical values: crown glass V ≈ 64, flint glass V ≈ 36.

    Parameters
    ----------
    f : float  Focal length (m). Non-zero.
    V : float  Abbe V-number. Must be > 0.

    Returns
    -------
    dict  ok, LCA_m, f_m, V
    """
    err = _guard_finite("f", f)
    if err:
        return _err(err)
    err = _guard_positive("V", V)
    if err:
        return _err(err)

    f_f = float(f)
    V_f = float(V)

    if f_f == 0.0:
        return _err("f must be non-zero")

    lca = f_f / V_f

    return {
        "ok": True,
        "LCA_m": lca,
        "f_m": f_f,
        "V": V_f,
    }


# ---------------------------------------------------------------------------
# 16. Achromatic doublet element powers
# ---------------------------------------------------------------------------

def achromat_powers(f_total: float, V1: float, V2: float) -> dict:
    """
    Crown/flint element powers for an achromatic doublet.

    For an achromatic doublet to bring F and C wavelengths to the same focus
    (Smith §7.2 / Hecht §6.3):

        phi1 + phi2 = phi_total    (combined power = 1/f_total)
        phi1/V1 + phi2/V2 = 0      (achromatic condition)

    Solving:
        phi1 = phi_total * V1 / (V1 - V2)
        phi2 = -phi_total * V2 / (V1 - V2)
        f1   = 1 / phi1
        f2   = 1 / phi2

    Note: V1 > V2 is the usual convention (crown V1, flint V2).

    Parameters
    ----------
    f_total : float  Desired combined focal length (m). Non-zero.
    V1      : float  Abbe number of first (crown) element. Must be > 0.
    V2      : float  Abbe number of second (flint) element. Must be > 0.
                     Should differ from V1 (else no solution).

    Returns
    -------
    dict
        ok          : True
        phi1_m      : power of first element (m⁻¹)
        phi2_m      : power of second element (m⁻¹)
        f1_m        : focal length of first element (m)
        f2_m        : focal length of second element (m)
        f_total_m, V1, V2: inputs echoed
    """
    err = _guard_finite("f_total", f_total)
    if err:
        return _err(err)
    err = _guard_positive("V1", V1)
    if err:
        return _err(err)
    err = _guard_positive("V2", V2)
    if err:
        return _err(err)

    f_t = float(f_total)
    V1_f = float(V1)
    V2_f = float(V2)

    if f_t == 0.0:
        return _err("f_total must be non-zero")

    delta_V = V1_f - V2_f
    if delta_V == 0.0:
        return _err("V1 and V2 must differ (no achromatic solution when V1 = V2)")

    phi_total = 1.0 / f_t
    phi1 = phi_total * V1_f / delta_V
    phi2 = -phi_total * V2_f / delta_V

    f1 = 1.0 / phi1 if phi1 != 0.0 else math.inf
    f2 = 1.0 / phi2 if phi2 != 0.0 else math.inf

    return {
        "ok": True,
        "phi1_m": phi1,
        "phi2_m": phi2,
        "f1_m": f1,
        "f2_m": f2,
        "f_total_m": f_t,
        "V1": V1_f,
        "V2": V2_f,
    }
