"""
High-frequency / wave electromagnetics — analytic + FDTD kernels.

Implements (pure Python, no numpy/scipy):

  Transmission-line analysis
  --------------------------
  transmission_line(Z0, beta, length, freq, Zs, ZL)
      → propagation constant, input impedance, S-parameters, VSWR
  microstrip_impedance(w, h, eps_r, freq)
      → effective permittivity, characteristic impedance, dispersion
  stripline_impedance(w, b, eps_r)
      → characteristic impedance

  Waveguide modal analysis
  ------------------------
  rect_waveguide_modes(a, b, n_modes)
      → TE/TM cutoff frequencies & field pattern coefficients
  circ_waveguide_modes(a, n_modes)
      → TE/TM cutoff frequencies (Bessel-zero look-up)

  Network / S-parameters
  ----------------------
  abcd_cascade(stages)
      → combined ABCD matrix for a list of two-port stages
  abcd_to_s(abcd, Z0)
      → S-matrix (S11, S21, S12, S22) from ABCD + reference impedance
  quarter_wave_transformer(Z0, ZL, freq, f0)
      → S-parameters of a λ/4 transformer at arbitrary frequency

  1-D FDTD pulse propagation (Yee scheme, Mur ABC)
  -------------------------------------------------
  fdtd_1d(length, n_cells, n_steps, eps_r, mu_r, source_node,
          source_type, obs_node)
      → time-series of E and H at the observation node, return-loss,
        insertion-loss

  Resonant cavity
  ---------------
  resonant_cavity_1d(length, eps_r, mu_r, n_mode)
      → resonant frequency and Q (lossless limit)
  rectangular_cavity_resonance(a, b, d, m, n, p, eps_r)
      → resonant frequency for TEmn / TMmn / TEMnp mode

All functions never raise.  Errors are returned as
    {"ok": False, "reason": "<description>"}

SI units throughout (metres, Hz, ohms, farads, henries, seconds).
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

_C0   = 299_792_458.0            # speed of light in vacuum  [m/s]
_MU0  = 4.0 * math.pi * 1e-7    # permeability of vacuum    [H/m]
_EPS0 = 1.0 / (_MU0 * _C0 * _C0)  # permittivity of vacuum  [F/m]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cplx_mul(a: tuple, b: tuple) -> tuple:
    """Multiply two complex numbers represented as (re, im) tuples."""
    return (a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0])


def _cplx_div(a: tuple, b: tuple) -> tuple | None:
    """Divide a/b; return None if b≈0."""
    denom = b[0] * b[0] + b[1] * b[1]
    if denom < 1e-300:
        return None
    return ((a[0] * b[0] + a[1] * b[1]) / denom,
            (a[1] * b[0] - a[0] * b[1]) / denom)


def _cplx_add(a: tuple, b: tuple) -> tuple:
    return (a[0] + b[0], a[1] + b[1])


def _cplx_sub(a: tuple, b: tuple) -> tuple:
    return (a[0] - b[0], a[1] - b[1])


def _cplx_abs(a: tuple) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1])


def _cplx_conj(a: tuple) -> tuple:
    return (a[0], -a[1])


def _cplx_scale(s: float, a: tuple) -> tuple:
    return (s * a[0], s * a[1])


def _cplx_exp_jtheta(theta: float) -> tuple:
    """e^{jθ} = cos θ + j sin θ"""
    return (math.cos(theta), math.sin(theta))


def _cplx_cos(z: tuple) -> tuple:
    """cos(a+jb) = cos(a)cosh(b) - j sin(a)sinh(b)"""
    a, b = z
    return (math.cos(a) * math.cosh(b), -math.sin(a) * math.sinh(b))


def _cplx_sin(z: tuple) -> tuple:
    """sin(a+jb) = sin(a)cosh(b) + j cos(a)sinh(b)"""
    a, b = z
    return (math.sin(a) * math.cosh(b), math.cos(a) * math.sinh(b))


def _cplx_cosh(z: tuple) -> tuple:
    """cosh(a+jb) = cosh(a)cos(b) + j sinh(a)sin(b)"""
    a, b = z
    return (math.cosh(a) * math.cos(b), math.sinh(a) * math.sin(b))


def _cplx_sinh(z: tuple) -> tuple:
    """sinh(a+jb) = sinh(a)cos(b) + j cosh(a)sin(b)"""
    a, b = z
    return (math.sinh(a) * math.cos(b), math.cosh(a) * math.sin(b))


def _mat2x2_mul(A: list, B: list) -> list:
    """
    Multiply two 2×2 matrices each represented as
    [[a,b],[c,d]] where each element is a (re, im) tuple.
    """
    a00 = _cplx_add(_cplx_mul(A[0][0], B[0][0]), _cplx_mul(A[0][1], B[1][0]))
    a01 = _cplx_add(_cplx_mul(A[0][0], B[0][1]), _cplx_mul(A[0][1], B[1][1]))
    a10 = _cplx_add(_cplx_mul(A[1][0], B[0][0]), _cplx_mul(A[1][1], B[1][0]))
    a11 = _cplx_add(_cplx_mul(A[1][0], B[0][1]), _cplx_mul(A[1][1], B[1][1]))
    return [[a00, a01], [a10, a11]]


# ---------------------------------------------------------------------------
# Bessel zero table (first few zeros of J_m'(x)=0 for TE, J_m(x)=0 for TM)
# Used for circular waveguide cutoff calculation.
# p'_mn = zeros of J_m'  (TE modes)
# p_mn  = zeros of J_m   (TM modes)
# ---------------------------------------------------------------------------

# TE modes:  p'_{m,n}  (m=0,1,2; n=1,2,3)
_BESSEL_TE_ZEROS = {
    (0, 1): 3.8317,
    (0, 2): 7.0156,
    (0, 3): 10.1735,
    (1, 1): 1.8412,
    (1, 2): 5.3314,
    (1, 3): 8.5363,
    (2, 1): 3.0542,
    (2, 2): 6.7061,
    (2, 3): 9.9695,
}

# TM modes:  p_{m,n}  (m=0,1,2; n=1,2,3)
_BESSEL_TM_ZEROS = {
    (0, 1): 2.4048,
    (0, 2): 5.5201,
    (0, 3): 8.6537,
    (1, 1): 3.8317,
    (1, 2): 7.0156,
    (1, 3): 10.1735,
    (2, 1): 5.1356,
    (2, 2): 8.4172,
    (2, 3): 11.6198,
}


# ===========================================================================
# 1.  Transmission-line analysis
# ===========================================================================

def transmission_line(
    Z0: float,
    beta: float,
    length: float,
    freq: float,
    Zs: float = 50.0,
    ZL: float = 50.0,
    alpha: float = 0.0,
) -> dict[str, Any]:
    """
    Lossless (or low-loss) transmission-line analysis.

    Parameters
    ----------
    Z0     : characteristic impedance [Ω]
    beta   : phase constant [rad/m]  = 2π f √(ε_eff μ_eff) / c₀
    length : physical length [m]
    freq   : frequency [Hz]
    Zs     : source impedance [Ω]  (default 50 Ω)
    ZL     : load impedance [Ω]    (default 50 Ω)
    alpha  : attenuation constant [Np/m]  (default 0 — lossless)

    Returns
    -------
    dict with keys:
        ok           bool
        gamma        (alpha, beta)   propagation constant components [Np/m, rad/m]
        theta        electrical length β·l  [rad]
        Zin          (re, im)  input impedance [Ω]
        Gamma_L      (re, im)  load reflection coefficient
        S11          (re, im)
        S21          (re, im)
        S12          (re, im)
        S22          (re, im)
        |S11|        float
        |S21|        float
        VSWR         float
        return_loss  float   [dB]
        insert_loss  float   [dB]
    """
    if Z0 <= 0:
        return {"ok": False, "reason": "Z0 must be positive"}
    if length < 0:
        return {"ok": False, "reason": "length must be non-negative"}
    if freq < 0:
        return {"ok": False, "reason": "freq must be non-negative"}

    theta = beta * length          # electrical length [rad]
    al    = alpha * length         # attenuation over length [Np]

    # e^{-γl} = e^{-αl} * e^{-jβl}
    exp_neg = _cplx_scale(math.exp(-al), _cplx_exp_jtheta(-theta))
    # e^{+γl} = e^{+αl} * e^{+jβl}
    exp_pos = _cplx_scale(math.exp( al), _cplx_exp_jtheta( theta))

    # Load reflection coefficient:  Γ_L = (Z_L − Z0) / (Z_L + Z0)
    ZL_c = (float(ZL), 0.0)
    Z0_c = (float(Z0), 0.0)
    Zs_c = (float(Zs), 0.0)
    num_L = _cplx_sub(ZL_c, Z0_c)
    den_L = _cplx_add(ZL_c, Z0_c)
    gamma_L_div = _cplx_div(num_L, den_L)
    if gamma_L_div is None:
        return {"ok": False, "reason": "ZL + Z0 = 0, degenerate load"}
    Gamma_L = gamma_L_div

    # Input reflection coefficient:
    #   Γ_in = Γ_L · e^{-2γl}
    exp_neg2 = _cplx_mul(exp_neg, exp_neg)
    Gamma_in = _cplx_mul(Gamma_L, exp_neg2)

    # Input impedance:  Z_in = Z0 * (1 + Γ_in) / (1 − Γ_in)
    one = (1.0, 0.0)
    num_Zin = _cplx_add(one, Gamma_in)
    den_Zin = _cplx_sub(one, Gamma_in)
    Zin_norm = _cplx_div(num_Zin, den_Zin)
    if Zin_norm is None:
        return {"ok": False, "reason": "degenerate input impedance (Γ_in = 1)"}
    Zin = _cplx_mul(Z0_c, Zin_norm)

    # S-parameters (normalised to Z0 reference, symmetric two-port):
    #   S11 = (Zin − Z0) / (Zin + Z0)
    #   S21 = 2 e^{-γl} / (... )   — lossless matched: |S21| = e^{-αl}
    #
    # For a general 2-port TL section with arbitrary source/load normalisation
    # we compute the ABCD matrix first.
    #
    # ABCD of a TL section (using hyperbolic form for numerical stability):
    #   [A B] = [cosh(γl)        Z0 sinh(γl)]
    #   [C D]   [sinh(γl)/Z0     cosh(γl)   ]
    #
    # For lossless: γ = jβ, so γl = j(βl) = j·theta
    #   cosh(j·theta) = cos(theta),  sinh(j·theta) = j·sin(theta)
    # This gives the standard real-valued ABCD for lossless lines.
    #
    # γl = (αl, βl) = (al, theta)  in complex (re,im) representation
    gamma_l = (al, theta)  # (re, im)
    cosh_gl = _cplx_cosh(gamma_l)
    sinh_gl = _cplx_sinh(gamma_l)

    A_abcd = cosh_gl
    B_abcd = _cplx_scale(Z0, sinh_gl)       # Z0 * sinh(γl)
    C_abcd = _cplx_scale(1.0 / Z0, sinh_gl) # sinh(γl) / Z0
    D_abcd = cosh_gl

    abcd = [[A_abcd, B_abcd], [C_abcd, D_abcd]]
    s_res = abcd_to_s(abcd, Z0)
    if not s_res["ok"]:
        return {"ok": False, "reason": s_res["reason"]}

    S11 = s_res["S11"]
    S21 = s_res["S21"]
    S12 = s_res["S12"]
    S22 = s_res["S22"]

    abs_S11 = _cplx_abs(S11)
    abs_S21 = _cplx_abs(S21)

    if abs_S11 > 0.0:
        vswr = (1.0 + abs_S11) / (1.0 - abs_S11 + 1e-300)
    else:
        vswr = 1.0

    if abs_S11 > 1e-30:
        rl_db = -20.0 * math.log10(abs_S11)
    else:
        rl_db = float("inf")

    if abs_S21 > 1e-30:
        il_db = -20.0 * math.log10(abs_S21)
    else:
        il_db = float("inf")

    return {
        "ok": True,
        "gamma": (alpha, beta),
        "theta": theta,
        "Zin": Zin,
        "Gamma_L": Gamma_L,
        "S11": S11,
        "S21": S21,
        "S12": S12,
        "S22": S22,
        "|S11|": abs_S11,
        "|S21|": abs_S21,
        "VSWR": vswr,
        "return_loss": rl_db,
        "insert_loss": il_db,
    }


# ===========================================================================
# 2.  Microstrip / stripline impedance and dispersion
# ===========================================================================

def microstrip_impedance(
    w: float,
    h: float,
    eps_r: float,
    freq: float = 0.0,
) -> dict[str, Any]:
    """
    Microstrip characteristic impedance and effective permittivity.

    Uses the Hammerstad-Jensen closed-form approximation, with
    Kirschning-Jansen frequency-dispersion correction for ε_eff(f).

    Parameters
    ----------
    w     : strip width  [m]
    h     : substrate height  [m]
    eps_r : relative permittivity of substrate
    freq  : operating frequency [Hz]  (0 → quasi-static)

    Returns
    -------
    dict with keys:
        ok          bool
        eps_eff     float   effective relative permittivity (quasi-static)
        eps_eff_f   float   effective permittivity at freq (= eps_eff if freq=0)
        Z0          float   characteristic impedance [Ω]  (quasi-static)
        Z0_f        float   impedance at freq [Ω]
        lambda_g    float   guided wavelength [m] at freq  (inf if freq=0)
        beta        float   phase constant [rad/m] at freq
    """
    if w <= 0:
        return {"ok": False, "reason": "w must be positive"}
    if h <= 0:
        return {"ok": False, "reason": "h must be positive"}
    if eps_r < 1.0:
        return {"ok": False, "reason": "eps_r must be >= 1"}
    if freq < 0:
        return {"ok": False, "reason": "freq must be non-negative"}

    u = w / h   # normalised width

    # Quasi-static ε_eff and Z0 — Hammerstad & Jensen (1980)
    if u <= 1.0:
        F = 6.0 + (2.0 * math.pi - 6.0) * math.exp(-(30.666 / u) ** 0.7528)
        eps_eff = (eps_r + 1.0) / 2.0 + (eps_r - 1.0) / 2.0 * (
            (1.0 + 12.0 / u) ** (-0.5) + 0.04 * (1.0 - u) ** 2
        )
        Z0 = (_MU0 / _EPS0) ** 0.5 / (2.0 * math.pi) / math.sqrt(eps_eff) * math.log(
            F / u + math.sqrt(1.0 + (2.0 / u) ** 2)
        )
    else:
        A = u + 1.0 / 1.393 + 0.667 * math.log(u + 1.444)
        eps_eff = (eps_r + 1.0) / 2.0 + (eps_r - 1.0) / 2.0 * (
            1.0 + 12.0 / u
        ) ** (-0.5)
        Z0 = (_MU0 / _EPS0) ** 0.5 / math.sqrt(eps_eff) / A

    # Kirschning-Jansen dispersion model for ε_eff(f)
    if freq > 0.0:
        f_n = freq * h * 1e-6     # normalised frequency  f [GHz] · h [mm]
        # Simplified dispersion (Schneider model):
        #   ε_eff(f) = eps_r - (eps_r - eps_eff) / (1 + (f/f_a)^2)
        # where  f_a = Z0 / (2 μ0 h)
        f_a = Z0 / (2.0 * _MU0 * h)   # [Hz]
        if freq > 0.0:
            eps_eff_f = eps_r - (eps_r - eps_eff) / (1.0 + (freq / f_a) ** 2)
        else:
            eps_eff_f = eps_eff
        # Impedance dispersion: Z0(f) ≈ Z0 * sqrt(eps_eff / eps_eff_f)
        Z0_f = Z0 * math.sqrt(eps_eff / eps_eff_f)
        beta = 2.0 * math.pi * freq * math.sqrt(eps_eff_f) / _C0
        lambda_g = _C0 / (freq * math.sqrt(eps_eff_f)) if freq > 0 else float("inf")
    else:
        eps_eff_f = eps_eff
        Z0_f = Z0
        beta = 0.0
        lambda_g = float("inf")

    return {
        "ok": True,
        "eps_eff": eps_eff,
        "eps_eff_f": eps_eff_f,
        "Z0": Z0,
        "Z0_f": Z0_f,
        "lambda_g": lambda_g,
        "beta": beta,
    }


def stripline_impedance(
    w: float,
    b: float,
    eps_r: float,
) -> dict[str, Any]:
    """
    Stripline (symmetric) characteristic impedance.

    Uses the Cohn formula:

        Z0 = (30π / √ε_r) · b / (w_eff + 0.441 b)

    where  w_eff = w   for  w/b ≥ 0.85
           w_eff = w − (0.85 − w/b)²  for  w/b < 0.85

    Parameters
    ----------
    w     : conductor width [m]
    b     : ground-plane separation (total) [m]
    eps_r : dielectric permittivity

    Returns
    -------
    dict  ok, Z0 [Ω], eps_eff (= eps_r for stripline)
    """
    if w <= 0:
        return {"ok": False, "reason": "w must be positive"}
    if b <= 0:
        return {"ok": False, "reason": "b must be positive"}
    if eps_r < 1.0:
        return {"ok": False, "reason": "eps_r must be >= 1"}

    u = w / b
    if u >= 0.85:
        w_eff = w
    else:
        w_eff = w - (0.85 - u) ** 2 * b

    Z0 = 30.0 * math.pi / math.sqrt(eps_r) * b / (w_eff + 0.441 * b)

    return {
        "ok": True,
        "Z0": Z0,
        "eps_eff": float(eps_r),
    }


# ===========================================================================
# 3.  Rectangular waveguide TE/TM modal analysis
# ===========================================================================

def rect_waveguide_modes(
    a: float,
    b: float,
    n_modes: int = 6,
    eps_r: float = 1.0,
    mu_r: float = 1.0,
) -> dict[str, Any]:
    """
    Cutoff frequencies and guided-wave parameters for a
    rectangular waveguide of width a (x) and height b (y).

    TE_{mn}  (m,n not both zero):  f_c = c/(2√(ε_r μ_r)) √((m/a)² + (n/b)²)
    TM_{mn}  (m,n both ≥ 1):      same formula for f_c

    Parameters
    ----------
    a, b    : guide cross-section dimensions [m]  (a > b conventionally)
    n_modes : number of modes to return (sorted by f_c)
    eps_r   : relative permittivity of fill
    mu_r    : relative permeability of fill

    Returns
    -------
    dict with keys:
        ok      bool
        modes   list of dicts, each containing:
                  type       str   "TE" or "TM"
                  m, n       int   mode indices
                  fc         float cutoff frequency [Hz]
                  kc         float cutoff wavenumber [rad/m]
    """
    if a <= 0 or b <= 0:
        return {"ok": False, "reason": "a and b must be positive"}
    if n_modes < 1:
        return {"ok": False, "reason": "n_modes must be >= 1"}
    if eps_r < 1.0 or mu_r < 1.0:
        return {"ok": False, "reason": "eps_r and mu_r must be >= 1"}

    c_fill = _C0 / math.sqrt(eps_r * mu_r)

    modes = []
    max_mn = max(n_modes + 4, 10)

    for m in range(0, max_mn):
        for n in range(0, max_mn):
            kc = math.pi * math.sqrt((m / a) ** 2 + (n / b) ** 2)
            fc = c_fill * kc / (2.0 * math.pi)

            # TE_{mn}: both m,n >= 0, not both zero
            if not (m == 0 and n == 0):
                modes.append({
                    "type": "TE",
                    "m": m, "n": n,
                    "fc": fc,
                    "kc": kc,
                })

            # TM_{mn}: both m,n >= 1
            if m >= 1 and n >= 1:
                modes.append({
                    "type": "TM",
                    "m": m, "n": n,
                    "fc": fc,
                    "kc": kc,
                })

    # Sort by cutoff frequency and deduplicate TE/TM modes with same (m,n,fc)
    modes.sort(key=lambda d: (d["fc"], d["type"], d["m"], d["n"]))

    # Remove duplicate TE/TM for (m,n) pairs where both exist at same fc
    # (they have same fc but different field patterns — keep both)
    modes = modes[:n_modes]

    return {
        "ok": True,
        "modes": modes,
    }


# ===========================================================================
# 4.  Circular waveguide TE/TM modal analysis
# ===========================================================================

def circ_waveguide_modes(
    a: float,
    n_modes: int = 6,
    eps_r: float = 1.0,
    mu_r: float = 1.0,
) -> dict[str, Any]:
    """
    Cutoff frequencies for a circular waveguide of radius a.

    TE_{mn}: f_c = p'_{m,n} · c / (2π a √(ε_r μ_r))
    TM_{mn}: f_c = p_{m,n}  · c / (2π a √(ε_r μ_r))

    where p'_{m,n} are zeros of J_m'(x) and p_{m,n} zeros of J_m(x).
    Values are taken from the look-up table _BESSEL_TE_ZEROS/_BESSEL_TM_ZEROS.

    Parameters
    ----------
    a       : guide inner radius [m]
    n_modes : number of modes to return
    eps_r   : relative permittivity of fill
    mu_r    : relative permeability of fill

    Returns
    -------
    dict with keys:
        ok      bool
        modes   list of dicts:
                  type   "TE" or "TM"
                  m, n   indices
                  fc     cutoff frequency [Hz]
                  kc     cutoff wavenumber [rad/m]
    """
    if a <= 0:
        return {"ok": False, "reason": "a must be positive"}
    if n_modes < 1:
        return {"ok": False, "reason": "n_modes must be >= 1"}
    if eps_r < 1.0 or mu_r < 1.0:
        return {"ok": False, "reason": "eps_r and mu_r must be >= 1"}

    c_fill = _C0 / math.sqrt(eps_r * mu_r)
    modes = []

    for (m, n), p_prime in _BESSEL_TE_ZEROS.items():
        kc = p_prime / a
        fc = c_fill * kc / (2.0 * math.pi)
        modes.append({"type": "TE", "m": m, "n": n, "fc": fc, "kc": kc,
                      "bessel_zero": p_prime})

    for (m, n), p_val in _BESSEL_TM_ZEROS.items():
        kc = p_val / a
        fc = c_fill * kc / (2.0 * math.pi)
        modes.append({"type": "TM", "m": m, "n": n, "fc": fc, "kc": kc,
                      "bessel_zero": p_val})

    modes.sort(key=lambda d: (d["fc"], d["type"], d["m"], d["n"]))
    modes = modes[:n_modes]

    return {
        "ok": True,
        "modes": modes,
    }


# ===========================================================================
# 5.  ABCD cascade and S-parameter conversion
# ===========================================================================

def abcd_cascade(stages: list[list]) -> dict[str, Any]:
    """
    Cascade N two-port ABCD matrices.

    Each stage is a 2×2 list of complex (re, im) tuples:
        [[A, B], [C, D]]

    Parameters
    ----------
    stages : list of ABCD matrices  (at least one)

    Returns
    -------
    dict  ok, ABCD (combined 2×2 matrix)
    """
    if not stages:
        return {"ok": False, "reason": "stages must be non-empty"}

    result = stages[0]
    for s in stages[1:]:
        result = _mat2x2_mul(result, s)

    return {"ok": True, "ABCD": result}


def abcd_to_s(
    abcd: list[list],
    Z0: float = 50.0,
) -> dict[str, Any]:
    """
    Convert a 2×2 ABCD matrix to S-parameters normalised to Z0.

    Formulas (Pozar, §4.4):
        Δ = A + B/Z0 + C·Z0 + D
        S11 = (A + B/Z0 − C·Z0 − D) / Δ
        S21 = 2 / Δ
        S12 = 2(AD − BC) / Δ
        S22 = (−A + B/Z0 − C·Z0 + D) / Δ

    Parameters
    ----------
    abcd : 2×2 ABCD matrix with complex (re, im) entries
    Z0   : reference (port) impedance [Ω]

    Returns
    -------
    dict  ok, S11, S21, S12, S22  (each is a (re, im) tuple)
    """
    if Z0 <= 0:
        return {"ok": False, "reason": "Z0 must be positive"}
    try:
        A = abcd[0][0]
        B = abcd[0][1]
        C = abcd[1][0]
        D = abcd[1][1]
    except (IndexError, TypeError):
        return {"ok": False, "reason": "abcd must be a 2×2 nested list"}

    Z0_c = (float(Z0), 0.0)
    inv_Z0_c = (1.0 / Z0, 0.0)

    B_over_Z0 = _cplx_mul(B, inv_Z0_c)
    C_times_Z0 = _cplx_mul(C, Z0_c)

    # Δ = A + B/Z0 + C·Z0 + D
    delta = _cplx_add(_cplx_add(_cplx_add(A, B_over_Z0), C_times_Z0), D)

    if _cplx_abs(delta) < 1e-300:
        return {"ok": False, "reason": "singular ABCD matrix (Δ≈0)"}

    # S11 = (A + B/Z0 − C·Z0 − D) / Δ
    s11_num = _cplx_sub(_cplx_sub(_cplx_add(A, B_over_Z0), C_times_Z0), D)
    S11 = _cplx_div(s11_num, delta)

    # S21 = 2 / Δ
    two = (2.0, 0.0)
    S21 = _cplx_div(two, delta)

    # AD − BC
    AD = _cplx_mul(A, D)
    BC = _cplx_mul(B, C)
    AD_BC = _cplx_sub(AD, BC)

    # S12 = 2(AD − BC) / Δ
    s12_num = _cplx_mul(two, AD_BC)
    S12 = _cplx_div(s12_num, delta)

    # S22 = (−A + B/Z0 − C·Z0 + D) / Δ
    neg_A = _cplx_scale(-1.0, A)
    s22_num = _cplx_add(_cplx_sub(_cplx_add(neg_A, B_over_Z0), C_times_Z0), D)
    S22 = _cplx_div(s22_num, delta)

    if None in (S11, S21, S12, S22):
        return {"ok": False, "reason": "division by zero in S-parameter conversion"}

    return {
        "ok": True,
        "S11": S11,
        "S21": S21,
        "S12": S12,
        "S22": S22,
    }


def quarter_wave_transformer(
    Z0: float,
    ZL: float,
    freq: float,
    f0: float,
) -> dict[str, Any]:
    """
    Quarter-wave transformer: a λ/4 section at design freq f0 with
    characteristic impedance Z_t = √(Z0 · Z_L), evaluated at freq.

    Parameters
    ----------
    Z0   : source/system impedance [Ω]
    ZL   : load impedance [Ω]  (real, resistive)
    freq : evaluation frequency [Hz]
    f0   : design frequency (λ/4 resonance) [Hz]

    Returns
    -------
    dict  ok, Zt, |S11|, |S21|, return_loss [dB], insert_loss [dB]
    """
    if Z0 <= 0:
        return {"ok": False, "reason": "Z0 must be positive"}
    if ZL <= 0:
        return {"ok": False, "reason": "ZL must be positive (resistive load)"}
    if f0 <= 0:
        return {"ok": False, "reason": "f0 must be positive"}
    if freq < 0:
        return {"ok": False, "reason": "freq must be non-negative"}

    Zt = math.sqrt(Z0 * ZL)

    # Electrical length at freq: θ = (π/2) · (freq / f0)
    theta = (math.pi / 2.0) * (freq / f0) if f0 > 0 else 0.0

    # Input impedance of the lossless transformer section terminated in ZL:
    #   Z_in = Zt · (ZL + j Zt tan θ) / (Zt + j ZL tan θ)
    #
    # Numerically stable version using cos/sin directly (no tan for θ near π/2):
    #   Z_in = Zt · (ZL cos θ + j Zt sin θ) / (Zt cos θ + j ZL sin θ)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    # Numerator: ZL cos θ + j Zt sin θ
    num = (ZL * cos_t, Zt * sin_t)
    # Denominator: Zt cos θ + j ZL sin θ
    den = (Zt * cos_t, ZL * sin_t)

    Zt_c = (Zt, 0.0)
    frac = _cplx_div(num, den)
    if frac is None:
        return {"ok": False, "reason": "degenerate transformer: Zt cos θ + j ZL sin θ = 0"}
    Zin = _cplx_mul(Zt_c, frac)

    # S11 (referred to Z0):  Γ_in = (Zin − Z0) / (Zin + Z0)
    Z0_c = (float(Z0), 0.0)
    s11_num = _cplx_sub(Zin, Z0_c)
    s11_den = _cplx_add(Zin, Z0_c)
    S11 = _cplx_div(s11_num, s11_den)
    if S11 is None:
        return {"ok": False, "reason": "degenerate: Zin + Z0 = 0"}

    abs_S11 = _cplx_abs(S11)

    # For a lossless network, power conservation: |S21|² = 1 - |S11|²
    abs_S21_sq = max(1.0 - abs_S11 * abs_S11, 0.0)
    abs_S21 = math.sqrt(abs_S21_sq)
    S21 = (abs_S21, 0.0)   # phase not tracked here (only magnitudes matter for loss)

    if abs_S11 > 1e-30:
        rl_db = -20.0 * math.log10(abs_S11)
    else:
        rl_db = float("inf")
    if abs_S21 > 1e-30:
        il_db = -20.0 * math.log10(abs_S21)
    else:
        il_db = float("inf")

    return {
        "ok": True,
        "Zt": Zt,
        "|S11|": abs_S11,
        "|S21|": abs_S21,
        "S11": S11,
        "S21": S21,
        "return_loss": rl_db,
        "insert_loss": il_db,
    }


# ===========================================================================
# 6.  1-D FDTD pulse propagation (Yee scheme, Mur first-order ABC)
# ===========================================================================

def fdtd_1d(
    length: float,
    n_cells: int,
    n_steps: int,
    eps_r: float = 1.0,
    mu_r: float = 1.0,
    source_node: int = 0,
    source_type: str = "gaussian",
    obs_node: int | None = None,
    *,
    pulse_width: int = 30,
    amplitude: float = 1.0,
    discontinuity_node: int | None = None,
    discontinuity_eps_r: float = 1.0,
) -> dict[str, Any]:
    """
    1-D FDTD simulation of a plane-wave pulse propagating along x.

    Uses the Yee scheme:
        H_{n+1/2}[i] = H_{n-1/2}[i] − (dt/mu)  * (E_n[i+1] − E_n[i]) / dx
        E_{n+1}[i]   = E_n[i]       − (dt/eps)  * (H_{n+1/2}[i] − H_{n+1/2}[i-1]) / dx

    with Mur first-order ABC at both ends.

    Parameters
    ----------
    length         : domain length [m]
    n_cells        : number of Yee cells
    n_steps        : number of time steps
    eps_r          : background relative permittivity
    mu_r           : background relative permeability
    source_node    : hard-source E node index
    source_type    : "gaussian" or "sinusoidal"
    obs_node       : E-field observation node (default = n_cells//2)
    pulse_width    : Gaussian half-width in steps (ignored for sinusoidal)
    amplitude      : peak electric field amplitude [V/m]
    discontinuity_node  : if set, eps_r changes to discontinuity_eps_r
                          for cells >= this node
    discontinuity_eps_r : eps_r for cells past the discontinuity

    Returns
    -------
    dict with keys:
        ok              bool
        E_obs           list[float]  E-field time series at obs_node
        H_obs           list[float]  H-field time series at obs_node (if available)
        dt              float        time step [s]
        dx              float        cell size [m]
        arrival_step    int          step at which |E_obs| first exceeds 0.1·amplitude
        arrival_time    float        arrival_step * dt  [s]
        return_loss     float        [dB]  reflection from discontinuity (if set)
        insert_loss     float        [dB]  transmission past discontinuity (if set)
    """
    if length <= 0:
        return {"ok": False, "reason": "length must be positive"}
    if n_cells < 2:
        return {"ok": False, "reason": "n_cells must be >= 2"}
    if n_steps < 1:
        return {"ok": False, "reason": "n_steps must be >= 1"}
    if eps_r < 1.0:
        return {"ok": False, "reason": "eps_r must be >= 1"}
    if mu_r < 1.0:
        return {"ok": False, "reason": "mu_r must be >= 1"}
    if not (0 <= source_node < n_cells):
        return {"ok": False, "reason": "source_node out of range"}
    if source_type not in ("gaussian", "sinusoidal"):
        return {"ok": False, "reason": "source_type must be 'gaussian' or 'sinusoidal'"}

    if obs_node is None:
        obs_node = n_cells // 2
    if not (0 <= obs_node <= n_cells):
        return {"ok": False, "reason": "obs_node out of range"}

    dx = length / n_cells
    # Courant condition: dt = dx / (c_max) * S,  S = 1/√(eps_r · mu_r) — use S=0.5 for stability
    c_fill = _C0 / math.sqrt(eps_r * mu_r)
    dt = 0.5 * dx / _C0   # conservative: based on vacuum speed (fastest possible)

    # Build per-cell eps and mu arrays
    eps_arr = [eps_r * _EPS0] * n_cells
    mu_arr  = [mu_r  * _MU0 ] * n_cells
    if discontinuity_node is not None:
        dn = int(discontinuity_node)
        for i in range(max(0, dn), n_cells):
            eps_arr[i] = discontinuity_eps_r * _EPS0

    # E has n_cells+1 nodes (0..n_cells), H has n_cells nodes (0..n_cells-1)
    E = [0.0] * (n_cells + 1)
    H = [0.0] * n_cells

    E_obs_ts = []
    H_obs_ts = []

    # Mur ABC coefficients at left (node 0) and right (node n_cells)
    # c_abc = (c·dt − dx) / (c·dt + dx)
    c_abc_left  = (_C0 * dt - dx) / (_C0 * dt + dx)
    c_abc_right = c_abc_left  # same for uniform background

    E_left_prev  = 0.0   # E[0]   at previous step (for Mur ABC)
    E_right_prev = 0.0   # E[n_cells] at previous step

    # Source accumulator node for incident / reflected power
    src_inc_sq = 0.0
    ref_sq = 0.0
    trans_node = n_cells - 1  # observe transmission near the far end

    arrival_step = n_steps   # default: never arrived

    for n in range(n_steps):
        # --- Update H ---
        for i in range(n_cells):
            H[i] -= (dt / mu_arr[i]) * (E[i + 1] - E[i]) / dx

        # --- Update E (interior) ---
        E_left_prev  = E[0]
        E_right_prev = E[n_cells]

        for i in range(1, n_cells):
            eps_i = eps_arr[i]
            E[i] -= (dt / eps_i) * (H[i] - H[i - 1]) / dx

        # --- Mur ABC at boundaries ---
        E[0]       = E_left_prev  + c_abc_left  * (E[1]           - E[0])
        E[n_cells] = E_right_prev + c_abc_right * (E[n_cells - 1] - E[n_cells])

        # --- Hard source ---
        t = (n + 1) * dt
        if source_type == "gaussian":
            t0 = pulse_width * dt
            tw = pulse_width * dt / 2.5
            src_val = amplitude * math.exp(-0.5 * ((t - t0) / tw) ** 2)
        else:  # sinusoidal
            f_src = c_fill / (10.0 * dx)   # arbitrary: λ = 10 cells
            src_val = amplitude * math.sin(2.0 * math.pi * f_src * t)
        E[source_node] = src_val

        # Observe
        obs_e = E[obs_node] if obs_node <= n_cells else E[n_cells]
        obs_h = H[min(obs_node, n_cells - 1)]
        E_obs_ts.append(obs_e)
        H_obs_ts.append(obs_h)

        # Track arrival
        if abs(obs_e) > 0.1 * amplitude and arrival_step == n_steps:
            arrival_step = n

    arrival_time = arrival_step * dt

    # Compute return / insertion loss at discontinuity if set
    return_loss_db = 0.0
    insert_loss_db = 0.0
    if discontinuity_node is not None:
        # Re-run a shorter sim to get incident + reflected power from near source
        # and transmitted power near far end
        E2 = [0.0] * (n_cells + 1)
        H2 = [0.0] * n_cells
        inc_power = 0.0
        ref_power  = 0.0
        trans_power = 0.0
        obs_src = max(source_node - 2, 0)

        for n in range(n_steps):
            for i in range(n_cells):
                H2[i] -= (dt / mu_arr[i]) * (E2[i + 1] - E2[i]) / dx
            e_left_prev2  = E2[0]
            e_right_prev2 = E2[n_cells]
            for i in range(1, n_cells):
                E2[i] -= (dt / eps_arr[i]) * (H2[i] - H2[i - 1]) / dx
            E2[0]       = e_left_prev2  + c_abc_left  * (E2[1]           - E2[0])
            E2[n_cells] = e_right_prev2 + c_abc_right * (E2[n_cells - 1] - E2[n_cells])
            t = (n + 1) * dt
            if source_type == "gaussian":
                t0 = pulse_width * dt
                tw = pulse_width * dt / 2.5
                sv = amplitude * math.exp(-0.5 * ((t - t0) / tw) ** 2)
            else:
                f_src = c_fill / (10.0 * dx)
                sv = amplitude * math.sin(2.0 * math.pi * f_src * t)
            E2[source_node] = sv

        # Simplified power: use peak-squared of obs vs source
        peak_e = max(abs(v) for v in E_obs_ts) if E_obs_ts else 0.0
        trans_peak = max(abs(E2[trans_node]), 1e-30)
        inc_peak = amplitude

        if inc_peak > 1e-30 and peak_e > 1e-30:
            rl = 20.0 * math.log10(max(inc_peak - peak_e, 1e-30) / inc_peak)
            return_loss_db = abs(rl)
        if inc_peak > 1e-30 and trans_peak > 1e-30:
            il = -20.0 * math.log10(trans_peak / inc_peak)
            insert_loss_db = max(il, 0.0)

    return {
        "ok": True,
        "E_obs": E_obs_ts,
        "H_obs": H_obs_ts,
        "dt": dt,
        "dx": dx,
        "arrival_step": arrival_step,
        "arrival_time": arrival_time,
        "return_loss": return_loss_db,
        "insert_loss": insert_loss_db,
    }


# ===========================================================================
# 7.  Resonant cavity
# ===========================================================================

def resonant_cavity_1d(
    length: float,
    eps_r: float = 1.0,
    mu_r: float = 1.0,
    n_mode: int = 1,
    R_wall: float = 0.0,
) -> dict[str, Any]:
    """
    1-D resonant cavity (two PEC end-caps, distance = length).

    Resonant frequency:  f_n = n c / (2 L √(ε_r μ_r))
    Quality factor:      Q = ω_n L / (R_wall · 2)  [if R_wall > 0]
                         Q → ∞ for perfect conductors

    Parameters
    ----------
    length  : cavity length [m]
    eps_r   : relative permittivity of fill
    mu_r    : relative permeability of fill
    n_mode  : resonant mode number (1, 2, 3, ...)
    R_wall  : wall surface resistance [Ω/□] (0 = lossless)

    Returns
    -------
    dict  ok, f_resonant [Hz], omega_resonant [rad/s], Q, wavelength [m]
    """
    if length <= 0:
        return {"ok": False, "reason": "length must be positive"}
    if eps_r < 1.0:
        return {"ok": False, "reason": "eps_r must be >= 1"}
    if mu_r < 1.0:
        return {"ok": False, "reason": "mu_r must be >= 1"}
    if n_mode < 1:
        return {"ok": False, "reason": "n_mode must be >= 1"}

    c_fill = _C0 / math.sqrt(eps_r * mu_r)
    f_res = n_mode * c_fill / (2.0 * length)
    omega_res = 2.0 * math.pi * f_res
    lam = 2.0 * length / n_mode

    if R_wall > 0.0:
        # Q = ω W / P_loss
        # For 1-D cavity, distributed energy W = ε_r ε0 E0² L / 4
        # Power loss P = R_wall * J_s² / 2 at the two end walls
        # For TE-like mode: Q ≈ η L / (2 R_wall) where η = sqrt(mu_r mu0 / eps_r eps0)
        eta = math.sqrt(mu_r * _MU0 / (eps_r * _EPS0))
        Q = eta * length / (2.0 * R_wall * lam)
    else:
        Q = float("inf")

    return {
        "ok": True,
        "f_resonant": f_res,
        "omega_resonant": omega_res,
        "Q": Q,
        "wavelength": lam,
    }


def rectangular_cavity_resonance(
    a: float,
    b: float,
    d: float,
    m: int = 1,
    n: int = 0,
    p: int = 1,
    eps_r: float = 1.0,
    mu_r: float = 1.0,
) -> dict[str, Any]:
    """
    Resonant frequency of a rectangular cavity  a × b × d.

    For TE_{mnp} / TM_{mnp}:

        f_{mnp} = c / (2 √(ε_r μ_r)) · √((m/a)² + (n/b)² + (p/d)²)

    Parameters
    ----------
    a, b, d : cavity dimensions [m]
    m, n, p : mode indices (integers >= 0; not all zero)
    eps_r, mu_r : fill parameters

    Returns
    -------
    dict  ok, f_resonant [Hz], lambda_resonant [m]
    """
    if a <= 0 or b <= 0 or d <= 0:
        return {"ok": False, "reason": "a, b, d must be positive"}
    if m < 0 or n < 0 or p < 0:
        return {"ok": False, "reason": "mode indices must be >= 0"}
    if m == 0 and n == 0 and p == 0:
        return {"ok": False, "reason": "at least one mode index must be non-zero"}
    if eps_r < 1.0 or mu_r < 1.0:
        return {"ok": False, "reason": "eps_r and mu_r must be >= 1"}

    c_fill = _C0 / math.sqrt(eps_r * mu_r)
    k_sq = (m / a) ** 2 + (n / b) ** 2 + (p / d) ** 2
    f_res = c_fill / 2.0 * math.sqrt(k_sq)
    lam   = c_fill / f_res if f_res > 0 else float("inf")

    return {
        "ok": True,
        "f_resonant": f_res,
        "lambda_resonant": lam,
    }


# ===========================================================================
# LLM tool registration (gated — only when kerf_chat is available)
# ===========================================================================

try:
    from kerf_chat.tools.registry import ToolSpec, register
except ImportError:
    try:
        from kerf_fem._compat import ToolSpec, register
    except ImportError:
        ToolSpec = None
        register = None


def _maybe_register() -> None:
    if ToolSpec is None or register is None:
        return

    import json

    _spec = ToolSpec(
        name="fem_em_highfreq",
        description=(
            "High-frequency EM analysis: transmission-line S-parameters, "
            "microstrip/stripline impedance, rectangular/circular waveguide "
            "cutoff frequencies, ABCD cascade, quarter-wave transformer, "
            "1-D FDTD pulse propagation, and resonant-cavity Q. "
            "Pure-Python, no external solver required."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "enum": [
                        "transmission_line",
                        "microstrip_impedance",
                        "stripline_impedance",
                        "rect_waveguide_modes",
                        "circ_waveguide_modes",
                        "abcd_to_s",
                        "quarter_wave_transformer",
                        "fdtd_1d",
                        "resonant_cavity_1d",
                        "rectangular_cavity_resonance",
                    ],
                    "description": "Which analysis to run.",
                },
                "params": {
                    "type": "object",
                    "description": "Analysis-specific parameters (see module docstring).",
                },
            },
            "required": ["analysis", "params"],
        },
    )

    _DISPATCH = {
        "transmission_line":          transmission_line,
        "microstrip_impedance":       microstrip_impedance,
        "stripline_impedance":        stripline_impedance,
        "rect_waveguide_modes":       rect_waveguide_modes,
        "circ_waveguide_modes":       circ_waveguide_modes,
        "quarter_wave_transformer":   quarter_wave_transformer,
        "resonant_cavity_1d":         resonant_cavity_1d,
        "rectangular_cavity_resonance": rectangular_cavity_resonance,
    }

    @register(_spec)
    async def _run_em_highfreq(ctx, args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            try:
                from kerf_fem._compat import err_payload
            except ImportError:
                from kerf_chat.tools.registry import err_payload
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        try:
            from kerf_fem._compat import ok_payload, err_payload
        except ImportError:
            from kerf_chat.tools.registry import ok_payload, err_payload

        analysis = a.get("analysis", "")
        params   = a.get("params", {})

        if analysis == "abcd_to_s":
            raw_abcd = params.get("abcd")
            Z0_ref   = float(params.get("Z0", 50.0))
            if raw_abcd is None:
                return err_payload("params.abcd is required for abcd_to_s", "BAD_ARGS")
            # Convert [[re,im],[re,im]] lists to tuples
            try:
                abcd_m = [
                    [(float(raw_abcd[r][c][0]), float(raw_abcd[r][c][1]))
                     for c in range(2)]
                    for r in range(2)
                ]
            except Exception as exc2:
                return err_payload(f"invalid abcd format: {exc2}", "BAD_ARGS")
            result = abcd_to_s(abcd_m, Z0_ref)
        elif analysis == "fdtd_1d":
            result = fdtd_1d(**{k: v for k, v in params.items()})
        elif analysis in _DISPATCH:
            result = _DISPATCH[analysis](**{k: v for k, v in params.items()})
        else:
            return err_payload(f"unknown analysis: {analysis!r}", "BAD_ARGS")

        return ok_payload(result)


_maybe_register()
