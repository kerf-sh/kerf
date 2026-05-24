"""
kerf_cad_core.fatigue.life — general fatigue-life analysis (pure Python).

Implements eight public functions:

  sn_cycles(sigma_a, Sf_prime, b)
      Stress-life (Basquin) S-N:  N = (sigma_a / Sf_prime)^(1/b)

  endurance_limit(Se_prime, *, ka, kb, kc, kd, ke, kf)
      Modified endurance limit with Marin factors:  Se = ka·kb·kc·kd·ke·kf·Se_prime

  strain_life_cycles(eps_a, E, Sf_prime, b, eps_f_prime, c, *, two_N_bracket)
      Strain-life (Coffin-Manson-Basquin ε-N):  solve eps_a = Sf'/E·(2N)^b + eps_f'·(2N)^c

  neuber_notch(S_nom, e_nom, Kf, E)
      Neuber notch correction (hyperbola):  sigma_local · eps_local = Kf² · S_nom · e_nom
      Returns (sigma_local, eps_local) for elasto-plastic notch root.

  mean_stress_correction(sigma_a, sigma_m, Se, Sut, Sy, *, method)
      Mean-stress corrected equivalent alternating amplitude using one of:
      "goodman", "gerber", "soderberg", "morrow", "swt"

  miner_damage(cycles, stress_amplitudes, Sf_prime, b)
      Palmgren-Miner linear cumulative damage rule:  D = Σ(n_i / N_i)
      Returns damage ratio; warns if D >= 1.

  rainflow_count(history)
      ASTM E1049 four-point rainflow cycle counting algorithm.
      Returns list of (range, mean, count) tuples.

  fatigue_life(sigma_a, Se, Sf_prime, b, Sut, *, safety_factor)
      Combined safety factor and life prediction.
      Flags infinite-life vs finite-life; warns if damage exceeds endurance.

All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Warnings are issued via the standard `warnings` module
and also collected into the result dict's "warnings" list.

Units
-----
  stress          — Pascals (Pa)
  strain          — dimensionless (m/m)
  modulus (E)     — Pascals (Pa)
  cycles (N)      — dimensionless count of reversals/2 (full cycles)
  reversals (2N)  — dimensionless (used in ε-N equations)

References
----------
Shigley's Mechanical Engineering Design, 10th ed., §§ 6-7 to 6-16
Dowling, N.E. "Mechanical Behavior of Materials", 4th ed., Ch. 9-14
ASTM E1049-85(2017) — Standard Practices for Cycle Counting in Fatigue Analysis
Norton, R.L. "Machine Design", 5th ed., Ch. 6

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_negative(name: str, value: Any) -> str | None:
    """Return an error string if *value* is not a finite negative number (for Basquin b)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v >= 0:
        return f"{name} must be < 0 (Basquin exponent), got {v}"
    return None


def _warn_and_collect(msg: str, category: type = UserWarning) -> str:
    """Issue a warning via the warnings module and return the message string."""
    warnings.warn(msg, category, stacklevel=4)
    return msg


# ---------------------------------------------------------------------------
# 1. sn_cycles — Basquin stress-life
# ---------------------------------------------------------------------------

def sn_cycles(
    sigma_a: float,
    Sf_prime: float,
    b: float,
) -> dict:
    """
    Basquin S-N stress-life: number of cycles to failure for a given
    completely-reversed stress amplitude.

    The Basquin power-law relationship (Shigley §6-7):

        sigma_a = Sf' · (2N)^b

    Solved for reversals 2N and then N (full cycles):

        2N = (sigma_a / Sf')^(1/b)
        N  = 2N / 2

    Parameters
    ----------
    sigma_a : float
        Alternating stress amplitude (Pa).  Must be > 0.
    Sf_prime : float
        Fatigue strength coefficient (Pa).  Must be > 0.
        Typical steel: Sf' ≈ 1.06 · Sut  (Dowling empirical).
    b : float
        Basquin exponent (dimensionless).  Must be < 0.
        Typical steel: b ≈ −0.085 (Dowling), range [−0.05, −0.12].

    Returns
    -------
    dict
        ok            : True
        N_cycles      : predicted full cycles to failure
        two_N         : reversals to failure (2N)
        sigma_a_Pa    : stress amplitude used (Pa)
        Sf_prime_Pa   : fatigue strength coefficient used (Pa)
        b             : Basquin exponent used
        infinite_life : True if N_cycles > 1e7 (conventional run-out)
        warnings      : list of warning strings

    Notes
    -----
    When sigma_a >= Sf' the formula gives N <= 0.5 (single reversal limit);
    this is physically the quasi-static rupture regime — a warning is issued.
    """
    err = _guard_positive("sigma_a", sigma_a)
    if err:
        return _err(err)
    err = _guard_positive("Sf_prime", Sf_prime)
    if err:
        return _err(err)
    err = _guard_negative("b", b)
    if err:
        return _err(err)

    sa = float(sigma_a)
    Sf = float(Sf_prime)
    b_val = float(b)

    warn_list: list[str] = []

    # 2N = (sigma_a / Sf')^(1/b)
    ratio = sa / Sf
    exponent = 1.0 / b_val  # b < 0, so exponent < 0 → 2N = ratio^exponent

    if ratio <= 0:
        return _err("sigma_a / Sf_prime ratio must be positive")

    two_N = ratio ** exponent
    N = two_N / 2.0

    if sa >= Sf:
        msg = (
            f"sn_cycles: sigma_a={sa:.3g} Pa >= Sf'={Sf:.3g} Pa; "
            "result N < 1 — quasi-static rupture regime, not fatigue."
        )
        warn_list.append(_warn_and_collect(msg))

    infinite_life = N > 1e7

    return {
        "ok": True,
        "N_cycles": N,
        "two_N": two_N,
        "sigma_a_Pa": sa,
        "Sf_prime_Pa": Sf,
        "b": b_val,
        "infinite_life": infinite_life,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 2. endurance_limit — Marin factors
# ---------------------------------------------------------------------------

def endurance_limit(
    Se_prime: float,
    *,
    ka: float = 1.0,
    kb: float = 1.0,
    kc: float = 1.0,
    kd: float = 1.0,
    ke: float = 1.0,
    kf: float = 1.0,
) -> dict:
    """
    Modified endurance limit using Marin surface/size/load/temperature/
    reliability/miscellaneous factors (Shigley §6-9 to §6-14).

    Se = ka · kb · kc · kd · ke · kf · Se'

    Parameters
    ----------
    Se_prime : float
        Rotating-beam endurance limit of the test specimen (Pa).  Must be > 0.
        Empirical approximation (Shigley §6-8):
          Se' ≈ 0.5 · Sut   for Sut ≤ 1400 MPa (steel)
          Se' ≈ 700 MPa     for Sut > 1400 MPa (steel)
    ka : float
        Surface factor (default 1.0 — polished specimen).
        Shigley Eq. 6-19: ka = a · Sut^b  (tabulated a, b by finish).
    kb : float
        Size factor (default 1.0 — specimen diameter 7.62 mm).
        Shigley Eq. 6-20/6-21.
    kc : float
        Load factor (default 1.0 — bending):
          1.0 = bending, 0.85 = axial, 0.59 = torsion (Shigley §6-14).
    kd : float
        Temperature factor (default 1.0 — ambient).
    ke : float
        Reliability factor (default 1.0 — 50% reliability).
        Shigley Table 6-6: ke = 0.702 for 99.9% reliability.
    kf : float
        Miscellaneous factor (default 1.0).

    Returns
    -------
    dict
        ok          : True
        Se_Pa       : modified endurance limit (Pa)
        Se_prime_Pa : rotating-beam endurance limit used (Pa)
        ka, kb, kc, kd, ke, kf : Marin factors used
        product_k   : combined Marin product ka·kb·kc·kd·ke·kf
        warnings    : list of warning strings
    """
    err = _guard_positive("Se_prime", Se_prime)
    if err:
        return _err(err)

    factors = {"ka": ka, "kb": kb, "kc": kc, "kd": kd, "ke": ke, "kf": kf}
    for name, val in factors.items():
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    warn_list: list[str] = []
    product_k = float(ka) * float(kb) * float(kc) * float(kd) * float(ke) * float(kf)
    Se = product_k * float(Se_prime)

    if Se <= 0:
        msg = (
            f"endurance_limit: computed Se={Se:.3g} Pa <= 0 after Marin factors; "
            "check that all Marin factors are physically reasonable."
        )
        warn_list.append(_warn_and_collect(msg))

    return {
        "ok": True,
        "Se_Pa": Se,
        "Se_prime_Pa": float(Se_prime),
        "ka": float(ka),
        "kb": float(kb),
        "kc": float(kc),
        "kd": float(kd),
        "ke": float(ke),
        "kf": float(kf),
        "product_k": product_k,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 3. strain_life_cycles — Coffin-Manson-Basquin ε-N
# ---------------------------------------------------------------------------

def strain_life_cycles(
    eps_a: float,
    E: float,
    Sf_prime: float,
    b: float,
    eps_f_prime: float,
    c: float,
    *,
    two_N_bracket: tuple[float, float] = (1.0, 2e9),
) -> dict:
    """
    Strain-life (Coffin-Manson-Basquin) equation — solve for reversals 2N.

    The total strain amplitude is the sum of elastic and plastic parts
    (Dowling §12.4 / Shigley §6-7):

        eps_a = (Sf' / E) · (2N)^b + eps_f' · (2N)^c

    This is solved numerically (bisection) since it is transcendental.

    Parameters
    ----------
    eps_a : float
        Total strain amplitude (m/m, dimensionless).  Must be > 0.
    E : float
        Young's modulus (Pa).  Must be > 0.  Steel ≈ 200e9 Pa.
    Sf_prime : float
        Fatigue strength coefficient (Pa).  Must be > 0.
        Typical steel: Sf' ≈ 1.06 · Sut.
    b : float
        Elastic fatigue exponent (Basquin, dimensionless).  Must be < 0.
        Typical steel: b ≈ −0.085.
    eps_f_prime : float
        Fatigue ductility coefficient (m/m).  Must be > 0.
        Typical steel: eps_f' ≈ 0.58 · (%RA / 100)^0.6.
    c : float
        Plastic fatigue exponent (Coffin-Manson, dimensionless).  Must be < 0.
        Typical steel: c ≈ −0.58.
    two_N_bracket : tuple[float, float]
        (lo, hi) bracket for bisection (reversals).  Default (1, 2e9).
        hi should exceed the maximum expected life.

    Returns
    -------
    dict
        ok              : True
        N_cycles        : predicted full cycles to failure (= 2N / 2)
        two_N           : reversals to failure
        eps_a_elastic   : elastic strain amplitude component at 2N
        eps_a_plastic   : plastic strain amplitude component at 2N
        eps_a_total     : total = elastic + plastic (≈ eps_a input)
        E_Pa            : Young's modulus used
        Sf_prime_Pa     : fatigue strength coefficient used
        b               : elastic exponent used
        eps_f_prime     : fatigue ductility coefficient used
        c               : plastic exponent used
        infinite_life   : True if N_cycles > 1e7
        warnings        : list of warning strings
    """
    err = _guard_positive("eps_a", eps_a)
    if err:
        return _err(err)
    err = _guard_positive("E", E)
    if err:
        return _err(err)
    err = _guard_positive("Sf_prime", Sf_prime)
    if err:
        return _err(err)
    err = _guard_negative("b", b)
    if err:
        return _err(err)
    err = _guard_positive("eps_f_prime", eps_f_prime)
    if err:
        return _err(err)
    err = _guard_negative("c", c)
    if err:
        return _err(err)

    warn_list: list[str] = []

    ea = float(eps_a)
    E_val = float(E)
    Sf = float(Sf_prime)
    b_val = float(b)
    ef = float(eps_f_prime)
    c_val = float(c)

    lo, hi = float(two_N_bracket[0]), float(two_N_bracket[1])
    if lo <= 0 or hi <= lo:
        return _err("two_N_bracket must be (lo, hi) with 0 < lo < hi")

    def _f(two_N: float) -> float:
        return (Sf / E_val) * (two_N ** b_val) + ef * (two_N ** c_val) - ea

    f_lo = _f(lo)
    f_hi = _f(hi)

    # If f_lo < 0 the entire bracket is at lives beyond our range (very low eps_a)
    # → effectively infinite life
    if f_lo < 0:
        msg = (
            f"strain_life_cycles: eps_a={ea:.3g} is below the curve value at "
            f"2N={lo:.3g}; predicting infinite life (> {hi/2:.3g} cycles)."
        )
        warn_list.append(_warn_and_collect(msg))
        return {
            "ok": True,
            "N_cycles": float("inf"),
            "two_N": float("inf"),
            "eps_a_elastic": (Sf / E_val) * (hi ** b_val),
            "eps_a_plastic": ef * (hi ** c_val),
            "eps_a_total": ea,
            "E_Pa": E_val,
            "Sf_prime_Pa": Sf,
            "b": b_val,
            "eps_f_prime": ef,
            "c": c_val,
            "infinite_life": True,
            "warnings": warn_list,
        }

    # If f_hi > 0 the bracket doesn't reach the root on the right
    if f_hi > 0:
        msg = (
            f"strain_life_cycles: eps_a={ea:.3g} is very high; 2N root lies "
            f"below bracket lo={lo:.3g}; clamping to 2N=1.0 reversals."
        )
        warn_list.append(_warn_and_collect(msg))
        two_N_val = 1.0
    else:
        # Bisection — converge to 1 part in 1e-10
        for _ in range(200):
            mid = (lo + hi) / 2.0
            fm = _f(mid)
            if abs(fm) < 1e-20 or (hi - lo) / max(abs(lo), 1.0) < 1e-12:
                break
            if fm * f_lo > 0:
                lo, f_lo = mid, fm
            else:
                hi = mid
        two_N_val = (lo + hi) / 2.0

    N = two_N_val / 2.0
    eps_el = (Sf / E_val) * (two_N_val ** b_val)
    eps_pl = ef * (two_N_val ** c_val)

    infinite_life = N > 1e7

    return {
        "ok": True,
        "N_cycles": N,
        "two_N": two_N_val,
        "eps_a_elastic": eps_el,
        "eps_a_plastic": eps_pl,
        "eps_a_total": eps_el + eps_pl,
        "E_Pa": E_val,
        "Sf_prime_Pa": Sf,
        "b": b_val,
        "eps_f_prime": ef,
        "c": c_val,
        "infinite_life": infinite_life,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 4. neuber_notch — Neuber hyperbola correction
# ---------------------------------------------------------------------------

def neuber_notch(
    S_nom: float,
    e_nom: float,
    Kf: float,
    E: float,
) -> dict:
    """
    Neuber notch correction for elasto-plastic stress and strain at a notch root.

    Neuber's rule (Neuber 1961, Dowling §5.3):

        sigma_local · eps_local = Kf² · S_nom · e_nom

    Combined with the elastic relationship e_nom = S_nom / E and Ramberg-Osgood
    or, for linear behaviour at the notch, sigma_local = E · eps_local:

    For elastic behaviour at the notch root:
        sigma_local = Kf · S_nom
        eps_local   = Kf · e_nom = Kf · S_nom / E

    For the general case where we only know S_nom (nominal) and want the
    notch root stress-strain product without a cyclic curve:

        (sigma_local) · (eps_local) = C   where C = Kf² · S_nom · (S_nom / E)

    This function returns the Neuber hyperbola constant C and the elastic
    notch-tip values, which are the upper bound for the notch root stress.

    Parameters
    ----------
    S_nom : float
        Nominal stress amplitude (Pa).  Must be > 0.
    e_nom : float
        Nominal strain amplitude (m/m).  Must be > 0.
        For elastic nominal: e_nom = S_nom / E.
    Kf : float
        Fatigue stress concentration factor (>= 1.0).  Must be > 0.
    E : float
        Young's modulus (Pa).  Must be > 0.

    Returns
    -------
    dict
        ok                   : True
        neuber_C             : Kf² · S_nom · e_nom (Pa, the Neuber product)
        sigma_local_elastic  : Kf · S_nom (Pa) — elastic estimate
        eps_local_elastic    : Kf · e_nom  — elastic estimate
        Kf_squared           : Kf²
        S_nom_Pa             : nominal stress used (Pa)
        e_nom                : nominal strain used
        E_Pa                 : Young's modulus used
        plasticity_flag      : True if sigma_local_elastic > E·e_nom·1.05
                               (notch stress ≫ elastic limit — result is approximate)
        warnings             : list of warning strings
    """
    err = _guard_positive("S_nom", S_nom)
    if err:
        return _err(err)
    err = _guard_positive("e_nom", e_nom)
    if err:
        return _err(err)
    err = _guard_positive("Kf", Kf)
    if err:
        return _err(err)
    err = _guard_positive("E", E)
    if err:
        return _err(err)

    warn_list: list[str] = []
    S = float(S_nom)
    e = float(e_nom)
    kf = float(Kf)
    E_val = float(E)

    C = (kf ** 2) * S * e
    sigma_el = kf * S
    eps_el = kf * e

    # Plasticity flag: if the elastic notch stress exceeds ~5% above E·e_nom
    # the linear estimate is less accurate
    plasticity_flag = sigma_el > E_val * e * 1.05

    if plasticity_flag:
        msg = (
            f"neuber_notch: sigma_local_elastic={sigma_el:.3g} Pa is significantly "
            "above the elastic bound E·e_nom; use Neuber's rule with a cyclic "
            "stress-strain curve for accurate elasto-plastic notch root stress."
        )
        warn_list.append(_warn_and_collect(msg))

    return {
        "ok": True,
        "neuber_C": C,
        "sigma_local_elastic": sigma_el,
        "eps_local_elastic": eps_el,
        "Kf_squared": kf ** 2,
        "S_nom_Pa": S,
        "e_nom": e,
        "E_Pa": E_val,
        "plasticity_flag": plasticity_flag,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 5. mean_stress_correction
# ---------------------------------------------------------------------------

_MEAN_STRESS_METHODS = frozenset(["goodman", "gerber", "soderberg", "morrow", "swt"])


def mean_stress_correction(
    sigma_a: float,
    sigma_m: float,
    Se: float,
    Sut: float,
    Sy: float,
    *,
    method: str = "goodman",
    Sf_prime: float | None = None,
) -> dict:
    """
    Mean-stress corrected equivalent fully-reversed alternating amplitude.

    Each method maps (sigma_a, sigma_m) to an equivalent amplitude sigma_ar
    such that  sigma_ar / Se = 1  at the failure boundary.

    Methods supported (Shigley §6-12; Dowling §9.6):

      "goodman"   — modified Goodman (linear):
                      sigma_a / Se + sigma_m / Sut = 1/n
                      sigma_ar = sigma_a / (1 - sigma_m / Sut)

      "gerber"    — Gerber parabolic (less conservative):
                      sigma_a / Se + (sigma_m / Sut)² = 1/n
                      sigma_ar = sigma_a / (1 - (sigma_m / Sut)²)

      "soderberg" — Soderberg (most conservative, uses Sy):
                      sigma_a / Se + sigma_m / Sy = 1/n
                      sigma_ar = sigma_a / (1 - sigma_m / Sy)

      "morrow"    — Morrow (elastic line uses Sf'):
                      sigma_a / Se + sigma_m / Sf_prime = 1/n
                      sigma_ar = sigma_a / (1 - sigma_m / Sf_prime)
                      Requires Sf_prime parameter.

      "swt"       — Smith-Watson-Topper (SWT):
                      sigma_max · sigma_a = sigma_ar²   (N.E. Dowling)
                      sigma_ar = √(sigma_max · sigma_a)
                      where sigma_max = sigma_a + sigma_m

    Parameters
    ----------
    sigma_a : float
        Alternating stress amplitude (Pa).  Must be >= 0.
    sigma_m : float
        Mean stress (Pa).  May be negative (compressive mean is beneficial).
    Se : float
        Modified endurance limit (Pa).  Must be > 0.
    Sut : float
        Ultimate tensile strength (Pa).  Must be > 0.
    Sy : float
        Yield strength (Pa).  Must be > 0.
    method : str
        One of: "goodman", "gerber", "soderberg", "morrow", "swt".
        Default: "goodman".
    Sf_prime : float | None
        Fatigue strength coefficient (Pa).  Required only for method="morrow".

    Returns
    -------
    dict
        ok           : True
        sigma_ar_Pa  : equivalent fully-reversed stress amplitude (Pa)
        method       : correction method used
        safety_factor: Se / sigma_ar  (fatigue safety factor; > 1 = safe)
        fatigue_ok   : True if sigma_ar <= Se
        sigma_a_Pa   : alternating amplitude used (Pa)
        sigma_m_Pa   : mean stress used (Pa)
        Se_Pa        : endurance limit used (Pa)
        Sut_Pa       : Sut used (Pa)
        Sy_Pa        : Sy used (Pa)
        warnings     : list of warning strings
    """
    err = _guard_nonneg("sigma_a", sigma_a)
    if err:
        return _err(err)
    # sigma_m may be negative (compressive) — no range check beyond finite
    try:
        sigma_m_f = float(sigma_m)
    except (TypeError, ValueError):
        return _err(f"sigma_m must be a number, got {sigma_m!r}")
    if not math.isfinite(sigma_m_f):
        return _err(f"sigma_m must be finite, got {sigma_m_f}")

    err = _guard_positive("Se", Se)
    if err:
        return _err(err)
    err = _guard_positive("Sut", Sut)
    if err:
        return _err(err)
    err = _guard_positive("Sy", Sy)
    if err:
        return _err(err)

    meth = str(method).strip().lower()
    if meth not in _MEAN_STRESS_METHODS:
        return _err(
            f"Unknown method {method!r}. Supported: {sorted(_MEAN_STRESS_METHODS)}."
        )

    sa = float(sigma_a)
    sm = sigma_m_f
    Se_v = float(Se)
    Sut_v = float(Sut)
    Sy_v = float(Sy)
    warn_list: list[str] = []

    # --- Compute sigma_ar ---

    if meth == "goodman":
        denom = 1.0 - sm / Sut_v
        if denom <= 0:
            msg = (
                f"mean_stress_correction (goodman): sigma_m={sm:.3g} >= Sut={Sut_v:.3g}; "
                "infinite damage — result is unbounded."
            )
            warn_list.append(_warn_and_collect(msg))
            return {
                "ok": True,
                "sigma_ar_Pa": float("inf"),
                "method": "goodman",
                "safety_factor": 0.0,
                "fatigue_ok": False,
                "sigma_a_Pa": sa,
                "sigma_m_Pa": sm,
                "Se_Pa": Se_v,
                "Sut_Pa": Sut_v,
                "Sy_Pa": Sy_v,
                "warnings": warn_list,
            }
        sigma_ar = sa / denom

    elif meth == "gerber":
        ratio_sq = (sm / Sut_v) ** 2
        denom = 1.0 - ratio_sq
        if denom <= 0:
            msg = (
                f"mean_stress_correction (gerber): sigma_m={sm:.3g} >= Sut={Sut_v:.3g}; "
                "result unbounded."
            )
            warn_list.append(_warn_and_collect(msg))
            return {
                "ok": True,
                "sigma_ar_Pa": float("inf"),
                "method": "gerber",
                "safety_factor": 0.0,
                "fatigue_ok": False,
                "sigma_a_Pa": sa,
                "sigma_m_Pa": sm,
                "Se_Pa": Se_v,
                "Sut_Pa": Sut_v,
                "Sy_Pa": Sy_v,
                "warnings": warn_list,
            }
        sigma_ar = sa / denom

    elif meth == "soderberg":
        denom = 1.0 - sm / Sy_v
        if denom <= 0:
            msg = (
                f"mean_stress_correction (soderberg): sigma_m={sm:.3g} >= Sy={Sy_v:.3g}; "
                "result unbounded."
            )
            warn_list.append(_warn_and_collect(msg))
            return {
                "ok": True,
                "sigma_ar_Pa": float("inf"),
                "method": "soderberg",
                "safety_factor": 0.0,
                "fatigue_ok": False,
                "sigma_a_Pa": sa,
                "sigma_m_Pa": sm,
                "Se_Pa": Se_v,
                "Sut_Pa": Sut_v,
                "Sy_Pa": Sy_v,
                "warnings": warn_list,
            }
        sigma_ar = sa / denom

    elif meth == "morrow":
        if Sf_prime is None:
            return _err("method='morrow' requires Sf_prime parameter.")
        err = _guard_positive("Sf_prime", Sf_prime)
        if err:
            return _err(err)
        Sf_v = float(Sf_prime)
        denom = 1.0 - sm / Sf_v
        if denom <= 0:
            msg = (
                f"mean_stress_correction (morrow): sigma_m={sm:.3g} >= Sf'={Sf_v:.3g}; "
                "result unbounded."
            )
            warn_list.append(_warn_and_collect(msg))
            return {
                "ok": True,
                "sigma_ar_Pa": float("inf"),
                "method": "morrow",
                "safety_factor": 0.0,
                "fatigue_ok": False,
                "sigma_a_Pa": sa,
                "sigma_m_Pa": sm,
                "Se_Pa": Se_v,
                "Sut_Pa": Sut_v,
                "Sy_Pa": Sy_v,
                "warnings": warn_list,
            }
        sigma_ar = sa / denom

    else:  # swt
        sigma_max = sa + sm
        if sigma_max <= 0:
            # Compressive max stress → beneficial, SWT gives 0
            sigma_ar = 0.0
        else:
            sigma_ar = math.sqrt(sigma_max * sa)

    fatigue_ok = sigma_ar <= Se_v
    safety_factor = Se_v / sigma_ar if sigma_ar > 0 else float("inf")

    if not fatigue_ok:
        msg = (
            f"mean_stress_correction ({meth}): sigma_ar={sigma_ar:.3g} Pa > "
            f"Se={Se_v:.3g} Pa — fatigue failure predicted."
        )
        warn_list.append(_warn_and_collect(msg))

    return {
        "ok": True,
        "sigma_ar_Pa": sigma_ar,
        "method": meth,
        "safety_factor": safety_factor,
        "fatigue_ok": fatigue_ok,
        "sigma_a_Pa": sa,
        "sigma_m_Pa": sm,
        "Se_Pa": Se_v,
        "Sut_Pa": Sut_v,
        "Sy_Pa": Sy_v,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 6. miner_damage — Palmgren-Miner cumulative damage
# ---------------------------------------------------------------------------

def miner_damage(
    cycles: list[float],
    stress_amplitudes: list[float],
    Sf_prime: float,
    b: float,
) -> dict:
    """
    Palmgren-Miner linear cumulative damage rule.

    Given a load spectrum of (n_i, sigma_a_i) pairs, compute the total
    damage fraction D = Σ(n_i / N_i), where N_i is the S-N life at sigma_a_i.

    Failure criterion: D >= 1.0  (Shigley §6-8; Dowling §12.5).

    Parameters
    ----------
    cycles : list[float]
        Applied cycles per block for each stress level.  All must be >= 0.
    stress_amplitudes : list[float]
        Alternating stress amplitude for each block (Pa).  All must be > 0.
        Must have the same length as cycles.
    Sf_prime : float
        Fatigue strength coefficient (Pa).  Must be > 0.
    b : float
        Basquin exponent.  Must be < 0.

    Returns
    -------
    dict
        ok              : True
        D               : total Miner damage (dimensionless)
        damage_exceeded : True if D >= 1.0
        remaining_life  : 1.0 - D  (may be negative if D > 1)
        n_blocks        : number of stress blocks
        block_damage    : list of individual d_i = n_i / N_i
        N_i             : list of S-N lives per block (Pa)
        warnings        : list of warning strings
    """
    if not hasattr(cycles, "__len__"):
        return _err("cycles must be a list")
    if not hasattr(stress_amplitudes, "__len__"):
        return _err("stress_amplitudes must be a list")
    if len(cycles) != len(stress_amplitudes):
        return _err(
            f"cycles (len={len(cycles)}) and stress_amplitudes "
            f"(len={len(stress_amplitudes)}) must have equal length."
        )
    if len(cycles) == 0:
        return _err("cycles and stress_amplitudes must not be empty.")

    err = _guard_positive("Sf_prime", Sf_prime)
    if err:
        return _err(err)
    err = _guard_negative("b", b)
    if err:
        return _err(err)

    warn_list: list[str] = []
    Sf = float(Sf_prime)
    b_val = float(b)

    block_damage: list[float] = []
    N_i_list: list[float] = []

    for i, (n_i, sa_i) in enumerate(zip(cycles, stress_amplitudes)):
        err = _guard_nonneg(f"cycles[{i}]", n_i)
        if err:
            return _err(err)
        err = _guard_positive(f"stress_amplitudes[{i}]", sa_i)
        if err:
            return _err(err)

        # S-N life at this amplitude
        ratio = float(sa_i) / Sf
        two_N_i = ratio ** (1.0 / b_val)
        N_i = two_N_i / 2.0
        N_i_list.append(N_i)

        d_i = float(n_i) / N_i if N_i > 0 else float("inf")
        block_damage.append(d_i)

    D = sum(block_damage)
    damage_exceeded = D >= 1.0

    if damage_exceeded:
        msg = (
            f"miner_damage: total damage D={D:.4f} >= 1.0 — "
            "cumulative fatigue failure criterion exceeded."
        )
        warn_list.append(_warn_and_collect(msg))

    return {
        "ok": True,
        "D": D,
        "damage_exceeded": damage_exceeded,
        "remaining_life": 1.0 - D,
        "n_blocks": len(cycles),
        "block_damage": block_damage,
        "N_i": N_i_list,
        "warnings": warn_list,
    }


# ---------------------------------------------------------------------------
# 7. rainflow_count — ASTM E1049-85 four-point rainflow algorithm
# ---------------------------------------------------------------------------

def rainflow_count(history: list[float]) -> dict:
    """
    ASTM E1049-85(2017) rainflow cycle counting (four-point algorithm).

    Counts fatigue cycles from a stress/strain time history using the
    ASTM E1049-85 §5.4.4 four-point stack-based algorithm.  The history is
    first reduced to its turning points (peaks and valleys) before counting.

    Algorithm outline (ASTM E1049-85 §5.4.4; Dowling §9.9):
      1. Reduce history to turning points (peaks and valleys).
      2. Process turning points into a stack.  Whenever the stack holds at
         least four points (A, B, C, D, oldest→newest), form the ranges
           Y = |B − C|   (interior candidate cycle)
           X = |C − D|   (most-recent range)
         If X >= Y the interior range Y is a closed full cycle: count it
         (count=1.0, mean=(B+C)/2) and remove the two interior points B and
         C, keeping A and D so the outer envelope can close future cycles.
         Repeat until no further cycle can be closed.
      3. Remaining stack entries form residual half-cycles (count=0.5 each).

    Parameters
    ----------
    history : list[float]
        Ordered stress or strain values (any units — output ranges have
        same units as input).  Must have at least 2 elements.

    Returns
    -------
    dict
        ok       : True
        cycles   : list of {"range": r, "mean": m, "count": c} dicts
                   c is 0.5 (half-cycle) or 1.0 (full cycle).
        n_cycles : total cycle count (sum of counts; half-cycles = 0.5)
        n_points : number of turning points extracted from history
        peak_range: maximum cycle range in the count
        warnings : list of warning strings
    """
    if not hasattr(history, "__len__") and not hasattr(history, "__iter__"):
        return _err("history must be an iterable of numbers")

    try:
        pts = [float(v) for v in history]
    except (TypeError, ValueError) as exc:
        return _err(f"history contains non-numeric value: {exc}")

    if len(pts) < 2:
        return _err("history must contain at least 2 data points")

    warn_list: list[str] = []

    # --- Step 1: Extract turning points (peaks and valleys) ---
    tp = _extract_turning_points(pts)

    if len(tp) < 2:
        return {
            "ok": True,
            "cycles": [],
            "n_cycles": 0.0,
            "n_points": len(tp),
            "peak_range": 0.0,
            "warnings": warn_list,
        }

    # --- Steps 2+3: Three-point stack algorithm ---
    cycles_raw = _rainflow_three_point(tp)

    # Accumulate (range, mean) → total count
    from collections import defaultdict as _dd
    acc: dict[tuple[float, float], float] = _dd(float)
    for r, m, c in cycles_raw:
        if r > 0:
            key = (round(r, 12), round(m, 12))
            acc[key] += c

    cycles_out = [{"range": k[0], "mean": k[1], "count": v} for k, v in acc.items()]
    cycles_out.sort(key=lambda x: -x["range"])  # largest range first

    n_cycles = sum(c["count"] for c in cycles_out)
    peak_range = max((c["range"] for c in cycles_out), default=0.0)

    return {
        "ok": True,
        "cycles": cycles_out,
        "n_cycles": n_cycles,
        "n_points": len(tp),
        "peak_range": peak_range,
        "warnings": warn_list,
    }


def _extract_turning_points(pts: list[float]) -> list[float]:
    """Reduce a history to its turning points (peaks and valleys).

    Keeps the first and last points unconditionally.  An interior point
    is kept if it is a local maximum or minimum relative to its neighbours.
    Monotone runs and flat segments are collapsed.
    """
    if len(pts) <= 2:
        return list(pts)
    tp = [pts[0]]
    for i in range(1, len(pts) - 1):
        prev, cur, nxt = pts[i - 1], pts[i], pts[i + 1]
        if (cur > prev and cur > nxt) or (cur < prev and cur < nxt):
            tp.append(cur)
    tp.append(pts[-1])
    return tp


def _rainflow_three_point(tp: list[float]) -> list[tuple[float, float, float]]:
    """
    ASTM E1049-85(2017) §5.4.4 four-point rainflow cycle-counting algorithm.

    The history (already reduced to turning points) is fed point-by-point onto
    a stack.  Whenever the stack holds at least four points the algorithm
    examines the two most-recent ranges:

        Y = |B − C|   (range formed by the second-and-third newest points)
        X = |C − D|   (range formed by the two newest points)

    where the top four stack entries are A, B, C, D.  If ``X >= Y`` the inner
    range Y is a *closed* full cycle: it is counted (count = 1.0) and the two
    interior points B and C are removed from the stack so the outer points can
    pair with future turning points.  Otherwise no cycle can yet be closed and
    the next turning point is read.

    After the history is exhausted the points remaining on the stack form the
    residual reversals; each consecutive pair is counted as a half cycle
    (count = 0.5).  This is exactly the standard ASTM E1049 treatment and
    matches the reference implementation in Dowling §9.9 and the canonical
    ASTM E1049-85 worked example.

    Returns a list of (range, mean, count) tuples.

    References
    ----------
    ASTM E1049-85(2017) §5.4.4 (four-point method)
    Dowling, N.E. "Mechanical Behavior of Materials", 4th ed., §9.9
    Amzallag et al. (1994) Int. J. Fatigue 16(4):287-293.
    """
    stack: list[float] = []
    cycles: list[tuple[float, float, float]] = []

    for x in tp:
        stack.append(x)
        # Close every full cycle that the new point makes possible.
        while len(stack) >= 4:
            # Top four points (oldest → newest): A, B, C, D
            _A, B, C, D = stack[-4], stack[-3], stack[-2], stack[-1]
            Y = abs(B - C)   # candidate (interior) cycle range
            X = abs(C - D)   # most-recent range
            if X >= Y and Y > 0:
                # Inner range Y is fully enclosed → one closed full cycle.
                cycles.append((Y, (B + C) / 2.0, 1.0))
                # Remove the two interior points B and C; keep A and D so the
                # outer envelope can continue to close future cycles.
                del stack[-3]   # remove B
                del stack[-2]   # remove C (index -2 after B removed)
            else:
                break   # nothing closable until the next turning point

    # Residual reversals: each consecutive remaining pair is a half cycle.
    for i in range(len(stack) - 1):
        R = abs(stack[i + 1] - stack[i])
        mean = (stack[i] + stack[i + 1]) / 2.0
        if R > 0:
            cycles.append((R, mean, 0.5))

    return cycles


# ---------------------------------------------------------------------------
# 8. fatigue_life — combined summary
# ---------------------------------------------------------------------------

def fatigue_life(
    sigma_a: float,
    Se: float,
    Sf_prime: float,
    b: float,
    Sut: float,
    *,
    safety_factor: float = 1.0,
) -> dict:
    """
    Combined fatigue safety factor and life prediction.

    Given a stress amplitude sigma_a (fully reversed, mean=0), computes:
      - Fatigue safety factor:  n_f = Se / sigma_a
      - Adjusted amplitude with safety factor: sigma_a_design = sigma_a * safety_factor
      - Predicted S-N life (Basquin) for sigma_a_design
      - Finite-life vs infinite-life flag (infinite if N > 1e7)

    Parameters
    ----------
    sigma_a : float
        Applied stress amplitude (Pa).  Must be > 0.
    Se : float
        Modified endurance limit (Pa).  Must be > 0.
    Sf_prime : float
        Fatigue strength coefficient (Pa).  Must be > 0.
    b : float
        Basquin exponent.  Must be < 0.
    Sut : float
        Ultimate tensile strength (Pa).  Must be > 0.
    safety_factor : float
        Design safety factor applied to sigma_a before life computation.
        Default 1.0 (use sigma_a as-is).

    Returns
    -------
    dict
        ok                 : True
        n_fatigue          : Se / sigma_a  (safety factor against endurance)
        sigma_a_Pa         : applied stress amplitude (Pa)
        sigma_a_design_Pa  : sigma_a * safety_factor (Pa) used for N prediction
        N_predicted        : Basquin cycles at sigma_a_design
        infinite_life      : True if sigma_a_design <= Se (endurance regime)
        Se_Pa              : endurance limit used
        Sf_prime_Pa        : Sf' used
        b                  : Basquin exponent used
        Sut_Pa             : Sut used
        safety_factor      : safety factor applied
        warnings           : list of warning strings
    """
    err = _guard_positive("sigma_a", sigma_a)
    if err:
        return _err(err)
    err = _guard_positive("Se", Se)
    if err:
        return _err(err)
    err = _guard_positive("Sf_prime", Sf_prime)
    if err:
        return _err(err)
    err = _guard_negative("b", b)
    if err:
        return _err(err)
    err = _guard_positive("Sut", Sut)
    if err:
        return _err(err)
    err = _guard_positive("safety_factor", safety_factor)
    if err:
        return _err(err)

    warn_list: list[str] = []
    sa = float(sigma_a)
    Se_v = float(Se)
    Sf = float(Sf_prime)
    b_val = float(b)
    Sut_v = float(Sut)
    sf = float(safety_factor)

    n_f = Se_v / sa
    sa_design = sa * sf

    # Infinite-life if design amplitude is at or below the endurance limit
    if sa_design <= Se_v:
        infinite_life = True
        N_predicted = float("inf")
    else:
        infinite_life = False
        sn_result = sn_cycles(sa_design, Sf, b_val)
        if not sn_result["ok"]:
            return _err(f"S-N life calculation failed: {sn_result['reason']}")
        N_predicted = sn_result["N_cycles"]
        warn_list.extend(sn_result.get("warnings", []))

    if n_f < 1.0:
        msg = (
            f"fatigue_life: n_fatigue={n_f:.3f} < 1.0 — "
            "applied stress amplitude exceeds the endurance limit; "
            "finite-life failure predicted."
        )
        warn_list.append(_warn_and_collect(msg))

    if sa_design > Sut_v:
        msg = (
            f"fatigue_life: sigma_a_design={sa_design:.3g} Pa > "
            f"Sut={Sut_v:.3g} Pa — static overload."
        )
        warn_list.append(_warn_and_collect(msg))

    return {
        "ok": True,
        "n_fatigue": n_f,
        "sigma_a_Pa": sa,
        "sigma_a_design_Pa": sa_design,
        "N_predicted": N_predicted,
        "infinite_life": infinite_life,
        "Se_Pa": Se_v,
        "Sf_prime_Pa": Sf,
        "b": b_val,
        "Sut_Pa": Sut_v,
        "safety_factor": sf,
        "warnings": warn_list,
    }
