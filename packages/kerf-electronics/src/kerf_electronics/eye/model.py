"""
Eye-diagram and jitter-budget estimator for PCB high-speed serial channels.

This module provides first-order statistical eye estimates from a channel model
described by insertion loss, channel length, bit rate, rise time, and
reflections/ISI.  It also provides a jitter budget decomposition and eye-mask
pass/fail check.

Physical background and formula references
------------------------------------------
1. Eye height / vertical closure
   --------------------------------
   The received signal swing is attenuated by frequency-dependent insertion loss.
   At Nyquist frequency fN = bit_rate / 2 the loss (dB) is:

       loss_dB = loss_db_per_inch * length_inch

   The linear voltage ratio (0–1):

       att = 10^(-loss_dB / 20)       [voltage, not power]

   Ideal eye height for a unit-amplitude signal:

       eye_height_ideal = 2 * att      (peak-to-peak of NRZ eye opening,
                                        normalised to [-1, +1] swing)

   ISI and reflection reduce the eye vertically.  A simplified first-order
   model (after Johnson & Graham, "High-Speed Signal Propagation", Prentice
   Hall 2003, §3.7) lumps ISI into a fractional penalty:

       isi_penalty = isi_fraction * eye_height_ideal  (0 ≤ isi_fraction < 1)

   Reflections produce a voltage noise floor estimated from the Z0 mismatch
   reflection coefficient Γ (if supplied) as:

       refl_noise = |Γ| * att          (first bounce, worst-case polarity)

   Vertical eye closure (VEC) = fraction of ideal height that is closed:

       eye_height = eye_height_ideal - isi_penalty - refl_noise
       VEC = 1 - eye_height / (2 * att)   when eye_height_ideal > 0

2. Eye width / horizontal closure
   ---------------------------------
   The rise time at the receiver is broadened by the channel bandwidth.
   Channel bandwidth:

       f_3dB ≈ 0.35 / t_rise_input_s   (Gaussian channel approximation)

   But we use the simpler relation: the received rise time combines the
   transmitter rise time and the channel response:

       t_rise_rx = sqrt(t_rise_tx^2 + t_rise_channel^2)

   where t_rise_channel (10–90%) for a first-order RC model is approximated as:

       t_rise_channel = 0.35 / BW_channel

   and BW_channel = 0.35 / (loss_dB / (20 * length_inch)) ... simplified:
   we model the channel as a single-pole low-pass with:

       BW_channel_hz ≈ 0.35 / (loss_dB * length_inch * 1e-9 + 1e-12)
                       (rough: 1 dB/inch loss degrades BW as ~ 0.35/loss_s)

   For a cleaner first-order model we compute an effective channel time
   constant τ from the loss and use:

       t_rise_rx = sqrt(t_rise_tx^2 + (2.2 * tau)^2)

   where tau = length_inch * loss_db_per_inch / (2 * pi * bit_rate / 2)
             = loss_dB / (pi * bit_rate)

   Eye width in UI (unit interval, UI = 1 / bit_rate):

       UI = 1 / bit_rate
       rise_fraction = t_rise_rx / UI       (fraction of UI consumed by rise)
       eye_width_UI = 1 - rise_fraction      (open region, capped to [0,1])

   Horizontal eye closure (HEC):

       HEC = 1 - eye_width_UI

   Reference: Eric Bogatin, "Signal Integrity Simplified", Prentice Hall
   2004, §7 (eye-diagram basics); Johnson & Graham, op. cit., §3.4.

3. Jitter budget decomposition
   ------------------------------
   Total jitter (Tj) at a specified BER is decomposed as:

       Tj = Dj + 2 * Rj * Q(BER)

   where:
     Dj   = deterministic jitter (bounded, peak-to-peak, seconds or UI)
     Rj   = random jitter (one-sigma, Gaussian, seconds or UI)
     Q(BER) = erfinv(1 - 2*BER) * sqrt(2)   [the Q-factor for the BER tail]

   The factor of 2 arises because at a given eye crossing there are two
   Gaussian tails (one from each eye edge); the total BER is the sum of
   the two tail probabilities, each equal to BER/2 — so each tail has
   Q = erfinv(1 - BER) * sqrt(2).  For BER ≪ 0.5 this simplifies to:

       Q(BER) ≈ erfinv(1 - 2*BER) * sqrt(2)

   Reference: Mike Peng Li, "Jitter, Noise, and Signal Integrity at
   High-Speed", Prentice Hall 2007, §2.3 (eq. 2-6).

4. Eye-mask check
   ---------------
   A rectangular mask is defined by:

       mask = { "height": <fraction>, "width_ui": <fraction>,
                "voffset": <fraction>? }   (all in normalised units)

   The eye passes if:

       eye_height >= mask["height"]  AND  eye_width_ui >= mask["width_ui"]

   An optional vertical offset ("voffset") shifts the mask centre; the check
   becomes eye_height - |voffset| >= mask["height"].

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Constant
# ──────────────────────────────────────────────────────────────────────────────

_SQRT2 = math.sqrt(2.0)


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _validate_positive(val: Any, name: str) -> tuple[float | None, str | None]:
    """Return (float_value, None) or (None, error_string)."""
    if val is None:
        return None, f"{name} is required"
    if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
        return None, f"{name} must be a finite number, got {val!r}"
    if val <= 0:
        return None, f"{name} must be positive, got {val!r}"
    return float(val), None


def _validate_non_negative(val: Any, name: str, default: float | None = None) -> tuple[float | None, str | None]:
    """Return (float_value, None) allowing zero; use default if val is None."""
    if val is None:
        if default is not None:
            return float(default), None
        return None, f"{name} is required"
    if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
        return None, f"{name} must be a finite number, got {val!r}"
    if val < 0:
        return None, f"{name} must be >= 0, got {val!r}"
    return float(val), None


def _q_factor(ber: float) -> float:
    """
    Q-factor for a given bit-error ratio (BER).

    Uses the erfinv approximation:
        Q(BER) = sqrt(2) * erfinv(1 - 2*BER)

    For BER in (0, 0.5) this is positive; at BER=0.5 Q=0.
    Falls back to 0.0 for out-of-range inputs.

    Reference: Li, "Jitter, Noise, and Signal Integrity at High-Speed",
    Prentice Hall 2007, §2.3.
    """
    if ber <= 0.0 or ber >= 0.5:
        return 0.0
    # erfinv via Newton iteration — stdlib math.erf is available, erfinv is not.
    # Use the rational approximation from Abramowitz & Stegun 26.2.17.
    p = 1.0 - 2.0 * ber          # target for erfinv; in (0, 1)
    return _erfinv_approx(p) * _SQRT2


def _erfinv_approx(p: float) -> float:
    """
    Rational approximation of erfinv(p) for p in (-1, 1).

    Algorithm: Peter J. Acklam's rational approximation.
    Reference: https://web.archive.org/web/20151030215612/http://home.online.no/~pjacklam/notes/invnorm/
    (adapted for erfinv via erfinv(p) = Phi_inv((p+1)/2) / sqrt(2)
     where Phi_inv is the standard normal quantile).
    """
    # Convert erfinv(p) = Phi^{-1}((p+1)/2) / sqrt(2)
    # where Phi^{-1} is the probit function.
    pp = (p + 1.0) / 2.0
    return _probit(pp) / _SQRT2


def _probit(p: float) -> float:
    """
    Rational approximation of the probit function (inverse normal CDF).

    Acklam (2010) rational approximation; max error < 1.15e-9 for p in
    (1e-16, 1-1e-16).

    Reference: https://web.archive.org/web/20151030215612/
    http://home.online.no/~pjacklam/notes/invnorm/
    """
    # Coefficients
    A = [-3.969683028665376e+01,  2.209460984245205e+02,
         -2.759285104469687e+02,  1.383577518672690e+02,
         -3.066479806614716e+01,  2.506628277459239e+00]
    B = [-5.447609879822406e+01,  1.615858368580409e+02,
         -1.556989798598866e+02,  6.680131188771972e+01,
         -1.328068155288572e+01]
    C = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
          4.374664141464968e+00,  2.938163982698783e+00]
    D = [7.784695709041462e-03,  3.224671290700398e-01,
         2.445134137142996e+00,  3.754408661907416e+00]

    p_low  = 0.02425
    p_high = 1.0 - p_low

    if p_low <= p <= p_high:
        q = p - 0.5
        r = q * q
        num = ((((A[0]*r+A[1])*r+A[2])*r+A[3])*r+A[4])*r+A[5]
        den = (((B[0]*r+B[1])*r+B[2])*r+B[3])*r+B[4]
        return q * num / (den * 1.0 + 1.0)  # den is degree 4; add 1 constant term
    elif 0.0 < p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        num = ((((C[0]*q+C[1])*q+C[2])*q+C[3])*q+C[4])*q+C[5]
        den =  (((D[0]*q+D[1])*q+D[2])*q+D[3])*q+1.0
        return num / den
    elif p_high < p < 1.0:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        num = ((((C[0]*q+C[1])*q+C[2])*q+C[3])*q+C[4])*q+C[5]
        den =  (((D[0]*q+D[1])*q+D[2])*q+D[3])*q+1.0
        return -(num / den)
    else:
        return float("inf") if p >= 1.0 else float("-inf")


# ──────────────────────────────────────────────────────────────────────────────
# Public: eye estimator
# ──────────────────────────────────────────────────────────────────────────────

def eye_estimate(
    loss_db_per_inch: float,
    length_inch: float,
    bit_rate_bps: float,
    rise_time_tx_s: float,
    isi_fraction: float = 0.05,
    reflection_gamma: float = 0.0,
) -> dict:
    """
    First-order statistical eye estimate for a lossy serial channel.

    Parameters
    ----------
    loss_db_per_inch : float
        Channel insertion loss at Nyquist frequency [dB/inch].
        Typical FR4 values: 0.3–0.8 dB/inch at 5 GHz.
    length_inch : float
        Channel (trace) length [inches].
    bit_rate_bps : float
        Signalling bit rate [bits/second], e.g. 10e9 for 10 Gbps.
    rise_time_tx_s : float
        Transmitter 10–90% rise time [seconds], e.g. 50e-12 for 50 ps.
    isi_fraction : float, optional
        Fractional ISI penalty relative to ideal eye height (0–0.5).
        Default: 0.05 (5%).  Use 0 for an ideal channel with no ISI.
    reflection_gamma : float, optional
        Magnitude of the dominant reflection coefficient |Γ| (0–1).
        Default: 0.0 (no reflections).  Obtain from the SI Z0-mismatch
        helper: Γ = (Z_load - Z0) / (Z_load + Z0).

    Returns
    -------
    dict with keys:
        ok            : bool
        eye_height    : float  — normalised vertical opening (0–2); ideal=2·att
        eye_width_ui  : float  — eye opening in UI (0–1)
        vec           : float  — vertical eye closure fraction (0–1)
        hec           : float  — horizontal eye closure fraction (0–1)
        loss_db       : float  — total insertion loss [dB]
        attenuation   : float  — linear voltage attenuation (0–1)
        t_rise_rx_ps  : float  — received 10–90% rise time [ps]
        ui_ps         : float  — unit interval [ps]
        details       : dict   — intermediate quantities for transparency
        error         : str    — present only when ok=False

    Physical basis: see module docstring (Johnson & Graham 2003 §3.4, §3.7;
    Bogatin 2004 §7).
    """
    # Validate inputs
    ldi, err = _validate_positive(loss_db_per_inch, "loss_db_per_inch")
    if err:
        return {"ok": False, "reason": err}
    li, err = _validate_positive(length_inch, "length_inch")
    if err:
        return {"ok": False, "reason": err}
    br, err = _validate_positive(bit_rate_bps, "bit_rate_bps")
    if err:
        return {"ok": False, "reason": err}
    rt, err = _validate_positive(rise_time_tx_s, "rise_time_tx_s")
    if err:
        return {"ok": False, "reason": err}

    isi_frac, err = _validate_non_negative(isi_fraction, "isi_fraction", default=0.05)
    if err:
        return {"ok": False, "reason": err}
    if isi_frac >= 1.0:
        return {"ok": False, "reason": "isi_fraction must be < 1.0"}

    gamma, err = _validate_non_negative(reflection_gamma, "reflection_gamma", default=0.0)
    if err:
        return {"ok": False, "reason": err}
    if gamma > 1.0:
        return {"ok": False, "reason": "reflection_gamma must be <= 1.0"}

    # ── Vertical eye ────────────────────────────────────────────────────────
    loss_db = ldi * li                          # total insertion loss [dB]
    att = 10.0 ** (-loss_db / 20.0)            # voltage attenuation

    eye_height_ideal = 2.0 * att               # normalised NRZ swing
    isi_penalty   = isi_frac * eye_height_ideal
    refl_noise    = gamma * att                 # first-bounce worst-case

    eye_height = eye_height_ideal - isi_penalty - refl_noise
    eye_height = max(0.0, eye_height)

    vec = 1.0 - (eye_height / eye_height_ideal) if eye_height_ideal > 0 else 1.0

    # ── Horizontal eye ──────────────────────────────────────────────────────
    ui_s = 1.0 / br                             # unit interval [s]
    ui_ps = ui_s * 1e12                         # [ps]

    # Channel time constant from loss model:
    #   tau = loss_dB / (pi * bit_rate) — derived from Nyquist loss bandwidth
    tau = loss_db / (math.pi * br)
    t_rise_ch = 2.2 * tau                       # 10-90% rise for first-order RC

    t_rise_rx = math.sqrt(rt ** 2 + t_rise_ch ** 2)
    t_rise_rx_ps = t_rise_rx * 1e12

    rise_fraction = t_rise_rx / ui_s
    eye_width_ui = max(0.0, 1.0 - rise_fraction)
    hec = 1.0 - eye_width_ui

    return {
        "ok": True,
        "eye_height": round(eye_height, 6),
        "eye_width_ui": round(eye_width_ui, 6),
        "vec": round(vec, 6),
        "hec": round(hec, 6),
        "loss_db": round(loss_db, 4),
        "attenuation": round(att, 6),
        "t_rise_rx_ps": round(t_rise_rx_ps, 4),
        "ui_ps": round(ui_ps, 4),
        "details": {
            "eye_height_ideal": round(eye_height_ideal, 6),
            "isi_penalty": round(isi_penalty, 6),
            "refl_noise": round(refl_noise, 6),
            "t_rise_tx_ps": round(rt * 1e12, 4),
            "t_rise_ch_ps": round(t_rise_ch * 1e12, 4),
            "rise_fraction": round(rise_fraction, 6),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Public: jitter budget
# ──────────────────────────────────────────────────────────────────────────────

def jitter_budget(
    rj_s: float,
    dj_s: float,
    ber: float = 1e-12,
) -> dict:
    """
    Jitter budget decomposition: Tj = Dj + 2 * Rj * Q(BER).

    Parameters
    ----------
    rj_s  : float — random jitter, 1-sigma [seconds or any consistent unit]
    dj_s  : float — deterministic jitter, peak-to-peak [same unit as rj_s]
    ber   : float — target bit-error ratio (default: 1e-12)

    Returns
    -------
    dict with keys:
        ok      : bool
        tj_s    : float — total jitter peak-to-peak (same unit as inputs)
        rj_s    : float — random jitter 1-sigma (echo)
        dj_s    : float — deterministic jitter pp (echo)
        q       : float — Q-factor for the requested BER
        ber     : float — target BER (echo)
        formula : str

    Reference: Li, "Jitter, Noise, and Signal Integrity at High-Speed",
    Prentice Hall 2007, §2.3, eq. 2-6.
    """
    rj, err = _validate_positive(rj_s, "rj_s")
    if err:
        return {"ok": False, "reason": err}
    dj, err = _validate_non_negative(dj_s, "dj_s", default=0.0)
    if err:
        return {"ok": False, "reason": err}

    if ber is None or not isinstance(ber, (int, float)) or ber <= 0.0 or ber >= 0.5:
        return {"ok": False, "reason": "ber must be in (0, 0.5)"}

    q = _q_factor(float(ber))
    tj = dj + 2.0 * rj * q

    return {
        "ok": True,
        "tj_s": tj,
        "rj_s": rj,
        "dj_s": dj,
        "q": round(q, 6),
        "ber": ber,
        "formula": "Tj = Dj + 2*Rj*Q(BER)  [Li 2007 §2.3]",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Public: eye-mask check
# ──────────────────────────────────────────────────────────────────────────────

def eye_mask_check(eye: dict, mask: dict) -> dict:
    """
    Check whether a computed eye diagram passes a rectangular eye mask.

    Parameters
    ----------
    eye  : dict — result from eye_estimate() containing at least
                  'eye_height' and 'eye_width_ui'
    mask : dict — mask definition with keys:
                  'height'    : float — minimum required eye height (same normalisation as eye_height)
                  'width_ui'  : float — minimum required eye width [UI]
                  'voffset'   : float, optional — vertical offset of mask centre
                                (default 0.0); reduces effective eye height by |voffset|

    Returns
    -------
    dict with keys:
        ok         : bool
        pass_      : bool — True if eye passes the mask
        margin_height : float — eye_height - mask_height (positive = margin)
        margin_width_ui : float — eye_width_ui - mask_width_ui (positive = margin)
        eye_height : float — echo
        eye_width_ui : float — echo
        mask       : dict  — echo of the mask used
        reason     : str   — present only when ok=False
    """
    if not isinstance(eye, dict):
        return {"ok": False, "reason": "eye must be a dict from eye_estimate()"}
    if not isinstance(mask, dict):
        return {"ok": False, "reason": "mask must be a dict"}

    if not eye.get("ok", False):
        return {"ok": False, "reason": f"eye is not valid: {eye.get('reason', 'unknown')}"}

    eh = eye.get("eye_height")
    ew = eye.get("eye_width_ui")
    if eh is None or ew is None:
        return {"ok": False, "reason": "eye dict missing 'eye_height' or 'eye_width_ui'"}

    mask_h = mask.get("height")
    mask_w = mask.get("width_ui")
    if mask_h is None:
        return {"ok": False, "reason": "mask missing 'height'"}
    if mask_w is None:
        return {"ok": False, "reason": "mask missing 'width_ui'"}

    if not isinstance(mask_h, (int, float)) or mask_h < 0:
        return {"ok": False, "reason": "mask 'height' must be >= 0"}
    if not isinstance(mask_w, (int, float)) or mask_w < 0:
        return {"ok": False, "reason": "mask 'width_ui' must be >= 0"}

    voffset = float(mask.get("voffset", 0.0))
    effective_eye_h = float(eh) - abs(voffset)

    margin_h = effective_eye_h - float(mask_h)
    margin_w = float(ew) - float(mask_w)

    passed = (margin_h >= 0.0) and (margin_w >= 0.0)

    return {
        "ok": True,
        "pass_": passed,
        "margin_height": round(margin_h, 6),
        "margin_width_ui": round(margin_w, 6),
        "eye_height": round(float(eh), 6),
        "eye_width_ui": round(float(ew), 6),
        "mask": {
            "height": float(mask_h),
            "width_ui": float(mask_w),
            "voffset": voffset,
        },
    }
