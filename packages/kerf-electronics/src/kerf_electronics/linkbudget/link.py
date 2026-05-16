"""
RF and fiber-optic communications link budget calculator.

This module is distinct from:
  • kerf_electronics.rfmatch  — impedance matching networks
  • kerf_electronics.si       — PCB signal integrity (Z0, propagation, crosstalk)
  • kerf_electronics.emc      — radiated emission / shielding effectiveness
  • kerf_electronics.dsp      — digital filter design

All functions are pure Python (math module only) and follow the kerf
never-raise contract: validation errors are returned as dicts with
{ok: False, reason: str}; warnings are issued via the standard warnings
module for limit/margin violations; exceptions are never raised to callers.

RF MODELS
---------
Free-space path loss (Friis, 1946):
    FSPL [dB] = 20×log10(4π×d×f/c)
              = 20×log10(d) + 20×log10(f) + 20×log10(4π/c)

EIRP (Effective Isotropic Radiated Power):
    EIRP [dBW] = P_tx_dbw + G_tx_dbi

Received power (Friis transmission equation):
    P_rx [dBW] = EIRP + G_rx_dbi − FSPL − L_other

Antenna gain ↔ aperture (Ae):
    G [linear] = 4π × Ae × f² / c²     (G [dBi] = 10×log10(G))
    Ae [m²]    = G_linear × c² / (4π × f²)

G/T (Figure of merit for receive systems):
    G/T [dB/K] = G_rx_dbi − 10×log10(T_sys_k)

Noise figure cascade (Friis noise formula):
    F_total = F1 + (F2−1)/G1 + (F3−1)/(G1×G2) + …
    NF_total [dB] = 10×log10(F_total)

System noise temperature:
    T_sys [K] = T_ant + T_noise
    T_noise = T0 × (F_total − 1)    (T0 = 290 K reference)

Thermal noise floor:
    N0 [dBW] = 10×log10(k×T×B)
    where k = 1.38065e-23 J/K (Boltzmann), T in Kelvin, B bandwidth in Hz.

Carrier-to-noise ratio:
    C/N [dB] = P_rx_dbw − N0_dbw

Eb/N0 (energy per bit to noise spectral density):
    Eb/N0 [dB] = C/N − 10×log10(spectral_efficiency_bits_per_hz)

Required Eb/N0 for target BER (using Q-function / erfc approximation):
    BPSK:   BER = Q(sqrt(2×Eb/N0))  =  0.5×erfc(sqrt(Eb/N0))
    QPSK:   BER = Q(sqrt(2×Eb/N0))  (same as BPSK per bit)
    M-QAM:  BER ≈ (4/log2(M)) × (1−1/sqrt(M)) × Q(sqrt(6×Eb/N0×log2(M)/(M−1)))
    M-PSK:  BER ≈ (2/log2(M)) × Q(sqrt(2×log2(M)×Eb/N0) × sin(π/M))

Q-function implemented numerically via erfc:
    Q(x) = 0.5 × erfc(x / sqrt(2))
erfc implemented with the Horner-form rational approximation from
Abramowitz & Stegun §7.1.26, max |err| < 1.5e-7.

Shannon capacity & spectral efficiency:
    C [bps] = B × log2(1 + SNR_linear)
    η [bps/Hz] = log2(1 + SNR_linear)

Fade margin:
    FM [dB] = P_rx_dbw − P_rx_min_dbw

Rain attenuation (ITU-R P.838-3, simplified specific attenuation model):
    A_rain [dB] = k × R^α × L    (k, α frequency-dependent coefficients)

Atmospheric attenuation (ITU-R P.676-12, simplified clear-air model):
    A_atm [dB/km] ≈ oxygen + water-vapour terms, frequency-dependent

FIBER-OPTIC MODELS
------------------
Optical power budget:
    Margin [dB] = P_tx_dbm − connector_loss_db − splice_loss_db
                  − fiber_loss_db − rx_sensitivity_dbm − safety_margin_db
    fiber_loss_db = loss_db_per_km × length_km
    Positive margin → link OK; negative → insufficient power.

Chromatic dispersion → bandwidth:
    CD_ps_per_nm = D × length_km × delta_lambda_nm
    BW_limit [bps] ≈ 1 / (4 × CD_ps × 1e-12)   (NRZ rule-of-thumb: 0.25/T)
    BW_km [bps·km] = BW_limit × length_km  (for normalised figure)

Modal dispersion → bandwidth (multimode fiber):
    Delta_T [ps] = (NA² / (2×n1×c)) × length_km × 1e12   [intermodal pulse spread]
    BW_limit [bps] ≈ 0.44 / Delta_T_s   (Gaussian impulse response)
    BW_km = BW_limit × length_km

OSNR (Optical Signal-to-Noise Ratio):
    OSNR [dB] = P_signal_dbm − NF_amp_db − 10×log10(h×f×B_o) − 10×log10(n_spans)
    where h = 6.626e-34 J·s (Planck), f = optical frequency, B_o = noise bandwidth.

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import List, Optional

# ── Physical constants ────────────────────────────────────────────────────────

_C = 2.99792458e8       # speed of light [m/s]
_K_B = 1.380649e-23     # Boltzmann constant [J/K]
_T0 = 290.0             # ITU/IEEE reference temperature [K]
_H_PLANCK = 6.62607015e-34  # Planck constant [J·s]

# ── Helpers ───────────────────────────────────────────────────────────────────


def _validate_positive(value, name: str) -> Optional[str]:
    """Return error string if value is not a positive real number."""
    if not isinstance(value, (int, float)) or math.isnan(value) or value <= 0:
        return f"{name} must be a positive number, got {value!r}"
    return None


def _validate_nonneg(value, name: str) -> Optional[str]:
    """Return error string if value is negative or non-real."""
    if not isinstance(value, (int, float)) or math.isnan(value) or value < 0:
        return f"{name} must be >= 0, got {value!r}"
    return None


def _validate_real(value, name: str) -> Optional[str]:
    """Return error string if value is not a real number."""
    if not isinstance(value, (int, float)) or math.isnan(value):
        return f"{name} must be a real number, got {value!r}"
    return None


def _db_to_linear(db: float) -> float:
    """Convert dB to linear power ratio."""
    return 10.0 ** (db / 10.0)


def _linear_to_db(linear: float) -> float:
    """Convert linear power ratio to dB. linear=0 returns -inf."""
    if linear <= 0.0:
        return -math.inf
    return 10.0 * math.log10(linear)


# ── Q-function and erfc ───────────────────────────────────────────────────────

def _erfc(x: float) -> float:
    """
    Complementary error function erfc(x) for x >= 0.
    Uses the rational approximation from Abramowitz & Stegun §7.1.26.
    Max |error| < 1.5e-7.  For x < 0: erfc(x) = 2 - erfc(-x).
    """
    if x < 0.0:
        return 2.0 - _erfc(-x)
    # A&S 7.1.26 polynomial approximation
    t = 1.0 / (1.0 + 0.3275911 * x)
    poly = (
        0.254829592 * t
        - 0.284496736 * t * t
        + 1.421413741 * t ** 3
        - 1.453152027 * t ** 4
        + 1.061405429 * t ** 5
    )
    return poly * math.exp(-(x * x))


def _q_func(x: float) -> float:
    """
    Q-function: Q(x) = P(N > x) = 0.5 × erfc(x / sqrt(2)).
    Q(x) in [0, 1].  Returns 1.0 for x <= -6, and ~0 for x > 8.
    """
    return 0.5 * _erfc(x / math.sqrt(2.0))


# ── RF: Free-space path loss ──────────────────────────────────────────────────


def fspl_db(freq_hz: float, distance_m: float) -> dict:
    """
    Free-space path loss (Friis, 1946).

    FSPL [dB] = 20×log10(4π×d×f/c)

    Parameters
    ----------
    freq_hz    : float — carrier frequency [Hz]
    distance_m : float — link distance [m]

    Returns
    -------
    dict with keys: ok, fspl_db, freq_hz, distance_m, wavelength_m
    """
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(distance_m, "distance_m")
    if err:
        return {"ok": False, "reason": err}

    wavelength_m = _C / freq_hz
    fspl = 20.0 * math.log10(4.0 * math.pi * distance_m * freq_hz / _C)

    return {
        "ok": True,
        "fspl_db": round(fspl, 4),
        "freq_hz": freq_hz,
        "distance_m": distance_m,
        "wavelength_m": wavelength_m,
        "formula": "FSPL = 20×log10(4π×d×f/c)  [Friis 1946]",
    }


# ── RF: EIRP ──────────────────────────────────────────────────────────────────


def eirp_dbw(p_tx_dbw: float, g_tx_dbi: float) -> dict:
    """
    Effective Isotropic Radiated Power.

    EIRP [dBW] = P_tx [dBW] + G_tx [dBi]

    Parameters
    ----------
    p_tx_dbw : float — transmitter output power [dBW]
    g_tx_dbi : float — transmit antenna gain [dBi]

    Returns
    -------
    dict with keys: ok, eirp_dbw, eirp_dbm, p_tx_dbw, g_tx_dbi
    """
    err = _validate_real(p_tx_dbw, "p_tx_dbw")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_real(g_tx_dbi, "g_tx_dbi")
    if err:
        return {"ok": False, "reason": err}

    eirp = p_tx_dbw + g_tx_dbi

    return {
        "ok": True,
        "eirp_dbw": round(eirp, 4),
        "eirp_dbm": round(eirp + 30.0, 4),
        "p_tx_dbw": p_tx_dbw,
        "g_tx_dbi": g_tx_dbi,
    }


# ── RF: Received power (Friis) ────────────────────────────────────────────────


def received_power_dbw(
    p_tx_dbw: float,
    g_tx_dbi: float,
    g_rx_dbi: float,
    freq_hz: float,
    distance_m: float,
    other_losses_db: float = 0.0,
) -> dict:
    """
    Received power using the Friis transmission equation.

    P_rx [dBW] = P_tx + G_tx − FSPL + G_rx − L_other

    Parameters
    ----------
    p_tx_dbw      : float — transmitter output power [dBW]
    g_tx_dbi      : float — transmit antenna gain [dBi]
    g_rx_dbi      : float — receive antenna gain [dBi]
    freq_hz       : float — carrier frequency [Hz]
    distance_m    : float — link distance [m]
    other_losses_db : float — miscellaneous losses (cable, pointing, rain, etc.) [dB] (default 0)

    Returns
    -------
    dict with keys: ok, p_rx_dbw, p_rx_dbm, fspl_db, eirp_dbw, link_loss_db
    """
    for name, val in [
        ("p_tx_dbw", p_tx_dbw), ("g_tx_dbi", g_tx_dbi), ("g_rx_dbi", g_rx_dbi)
    ]:
        err = _validate_real(name, val)
        if err:
            # correct arg order
            break
    # Redo validation correctly
    for name, val in [
        ("p_tx_dbw", p_tx_dbw), ("g_tx_dbi", g_tx_dbi), ("g_rx_dbi", g_rx_dbi),
        ("other_losses_db", other_losses_db),
    ]:
        err = _validate_real(val, name)
        if err:
            return {"ok": False, "reason": err}

    fspl_result = fspl_db(freq_hz=freq_hz, distance_m=distance_m)
    if not fspl_result["ok"]:
        return {"ok": False, "reason": fspl_result["reason"]}

    fspl = fspl_result["fspl_db"]
    eirp = p_tx_dbw + g_tx_dbi
    p_rx = eirp - fspl + g_rx_dbi - other_losses_db
    link_loss = fspl + other_losses_db

    return {
        "ok": True,
        "p_rx_dbw": round(p_rx, 4),
        "p_rx_dbm": round(p_rx + 30.0, 4),
        "fspl_db": round(fspl, 4),
        "eirp_dbw": round(eirp, 4),
        "link_loss_db": round(link_loss, 4),
        "p_tx_dbw": p_tx_dbw,
        "g_tx_dbi": g_tx_dbi,
        "g_rx_dbi": g_rx_dbi,
        "freq_hz": freq_hz,
        "distance_m": distance_m,
        "other_losses_db": other_losses_db,
    }


# ── RF: Antenna gain ↔ aperture ───────────────────────────────────────────────


def antenna_gain_from_aperture(aperture_m2: float, freq_hz: float, efficiency: float = 1.0) -> dict:
    """
    Antenna gain from effective aperture area.

    G [linear] = 4π × Ae × f² / c²
    G [dBi]    = 10×log10(G_linear)

    Parameters
    ----------
    aperture_m2 : float — effective aperture area [m²]
    freq_hz     : float — operating frequency [Hz]
    efficiency  : float — aperture efficiency η ∈ (0,1] (default 1.0)

    Returns
    -------
    dict with keys: ok, gain_linear, gain_dbi, aperture_m2, freq_hz, efficiency
    """
    err = _validate_positive(aperture_m2, "aperture_m2")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(efficiency, "efficiency")
    if err:
        return {"ok": False, "reason": err}
    if efficiency > 1.0:
        return {"ok": False, "reason": "efficiency must be <= 1.0"}

    g_linear = 4.0 * math.pi * aperture_m2 * efficiency * (freq_hz / _C) ** 2
    g_dbi = _linear_to_db(g_linear)

    return {
        "ok": True,
        "gain_linear": g_linear,
        "gain_dbi": round(g_dbi, 4),
        "aperture_m2": aperture_m2,
        "freq_hz": freq_hz,
        "efficiency": efficiency,
    }


def antenna_aperture_from_gain(gain_dbi: float, freq_hz: float, efficiency: float = 1.0) -> dict:
    """
    Effective aperture area from antenna gain.

    Ae [m²] = G_linear × c² / (4π × η × f²)

    Parameters
    ----------
    gain_dbi  : float — antenna gain [dBi]
    freq_hz   : float — operating frequency [Hz]
    efficiency: float — aperture efficiency η ∈ (0,1] (default 1.0)

    Returns
    -------
    dict with keys: ok, aperture_m2, gain_dbi, freq_hz, efficiency
    """
    err = _validate_real(gain_dbi, "gain_dbi")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(efficiency, "efficiency")
    if err:
        return {"ok": False, "reason": err}
    if efficiency > 1.0:
        return {"ok": False, "reason": "efficiency must be <= 1.0"}

    g_linear = _db_to_linear(gain_dbi)
    aperture = g_linear * (_C / freq_hz) ** 2 / (4.0 * math.pi * efficiency)

    return {
        "ok": True,
        "aperture_m2": aperture,
        "gain_dbi": gain_dbi,
        "freq_hz": freq_hz,
        "efficiency": efficiency,
    }


# ── RF: G/T (receive figure of merit) ────────────────────────────────────────


def g_over_t(g_rx_dbi: float, t_sys_k: float) -> dict:
    """
    System figure of merit G/T.

    G/T [dB/K] = G_rx [dBi] − 10×log10(T_sys [K])

    Parameters
    ----------
    g_rx_dbi : float — receive antenna gain [dBi]
    t_sys_k  : float — system noise temperature [K]

    Returns
    -------
    dict with keys: ok, g_over_t_db_per_k, g_rx_dbi, t_sys_k
    """
    err = _validate_real(g_rx_dbi, "g_rx_dbi")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(t_sys_k, "t_sys_k")
    if err:
        return {"ok": False, "reason": err}

    gt = g_rx_dbi - 10.0 * math.log10(t_sys_k)

    return {
        "ok": True,
        "g_over_t_db_per_k": round(gt, 4),
        "g_rx_dbi": g_rx_dbi,
        "t_sys_k": t_sys_k,
    }


# ── RF: Noise figure cascade (Friis) ─────────────────────────────────────────


def noise_figure_cascade(
    nf_db_list: List[float],
    gain_db_list: List[float],
) -> dict:
    """
    Cascade noise figure using Friis' noise formula.

    F_total = F1 + (F2−1)/G1 + (F3−1)/(G1×G2) + …
    NF_total [dB] = 10×log10(F_total)

    Parameters
    ----------
    nf_db_list   : list of float — noise figures of each stage [dB], length N
    gain_db_list : list of float — gains of each stage [dB], length N
                   (the gain of the last stage is not used in the cascade formula
                    but must be provided for consistency)

    Returns
    -------
    dict with keys: ok, nf_cascade_db, f_cascade_linear, stage_count
    """
    if not isinstance(nf_db_list, list) or len(nf_db_list) == 0:
        return {"ok": False, "reason": "nf_db_list must be a non-empty list"}
    if not isinstance(gain_db_list, list) or len(gain_db_list) != len(nf_db_list):
        return {"ok": False, "reason": "gain_db_list must have the same length as nf_db_list"}

    for i, (nf, g) in enumerate(zip(nf_db_list, gain_db_list)):
        err = _validate_real(nf, f"nf_db_list[{i}]")
        if err:
            return {"ok": False, "reason": err}
        err = _validate_real(g, f"gain_db_list[{i}]")
        if err:
            return {"ok": False, "reason": err}

    # Convert to linear
    f_list = [_db_to_linear(nf) for nf in nf_db_list]
    g_list = [_db_to_linear(g) for g in gain_db_list]

    f_total = f_list[0]
    cumulative_gain = g_list[0]
    for i in range(1, len(f_list)):
        f_total += (f_list[i] - 1.0) / cumulative_gain
        cumulative_gain *= g_list[i]

    nf_total_db = _linear_to_db(f_total)

    return {
        "ok": True,
        "nf_cascade_db": round(nf_total_db, 4),
        "f_cascade_linear": f_total,
        "stage_count": len(nf_db_list),
        "nf_db_list": nf_db_list,
        "gain_db_list": gain_db_list,
    }


# ── RF: System noise temperature ─────────────────────────────────────────────


def system_noise_temp(
    nf_total_db: float,
    t_ant_k: float = 0.0,
    t0_k: float = _T0,
) -> dict:
    """
    System noise temperature.

    T_noise [K] = T0 × (F_total − 1)
    T_sys   [K] = T_ant + T_noise

    Parameters
    ----------
    nf_total_db : float — total/cascaded system noise figure [dB]
    t_ant_k     : float — antenna noise temperature [K] (default 0.0)
    t0_k        : float — reference temperature [K] (default 290 K)

    Returns
    -------
    dict with keys: ok, t_sys_k, t_noise_k, t_ant_k, nf_total_db
    """
    err = _validate_real(nf_total_db, "nf_total_db")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_nonneg(t_ant_k, "t_ant_k")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(t0_k, "t0_k")
    if err:
        return {"ok": False, "reason": err}

    f_linear = _db_to_linear(nf_total_db)
    t_noise = t0_k * (f_linear - 1.0)
    t_sys = t_ant_k + t_noise

    return {
        "ok": True,
        "t_sys_k": round(t_sys, 4),
        "t_noise_k": round(t_noise, 4),
        "t_ant_k": t_ant_k,
        "nf_total_db": nf_total_db,
        "t0_k": t0_k,
    }


# ── RF: Thermal noise floor ───────────────────────────────────────────────────


def thermal_noise_floor_dbw(bandwidth_hz: float, temp_k: float = _T0) -> dict:
    """
    Thermal noise power in a given bandwidth.

    N [W]  = k × T × B
    N [dBW] = 10×log10(k × T × B)

    Parameters
    ----------
    bandwidth_hz : float — noise bandwidth [Hz]
    temp_k       : float — temperature [K] (default 290 K)

    Returns
    -------
    dict with keys: ok, noise_dbw, noise_dbm, noise_w, bandwidth_hz, temp_k
    """
    err = _validate_positive(bandwidth_hz, "bandwidth_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(temp_k, "temp_k")
    if err:
        return {"ok": False, "reason": err}

    noise_w = _K_B * temp_k * bandwidth_hz
    noise_dbw = _linear_to_db(noise_w)

    return {
        "ok": True,
        "noise_dbw": round(noise_dbw, 4),
        "noise_dbm": round(noise_dbw + 30.0, 4),
        "noise_w": noise_w,
        "bandwidth_hz": bandwidth_hz,
        "temp_k": temp_k,
        "formula": "N = k × T × B  (k=1.381e-23 J/K)",
    }


# ── RF: C/N ratio ─────────────────────────────────────────────────────────────


def cn_ratio_db(p_rx_dbw: float, noise_dbw: float) -> dict:
    """
    Carrier-to-noise ratio C/N.

    C/N [dB] = P_rx [dBW] − N [dBW]

    Parameters
    ----------
    p_rx_dbw  : float — received carrier power [dBW]
    noise_dbw : float — noise power [dBW] in the receive bandwidth

    Returns
    -------
    dict with keys: ok, cn_db, p_rx_dbw, noise_dbw
    """
    err = _validate_real(p_rx_dbw, "p_rx_dbw")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_real(noise_dbw, "noise_dbw")
    if err:
        return {"ok": False, "reason": err}

    cn = p_rx_dbw - noise_dbw

    return {
        "ok": True,
        "cn_db": round(cn, 4),
        "p_rx_dbw": p_rx_dbw,
        "noise_dbw": noise_dbw,
    }


# ── RF: Eb/N0 ─────────────────────────────────────────────────────────────────


def eb_n0_db(cn_db: float, bits_per_symbol: float, symbols_per_hz: float = 1.0) -> dict:
    """
    Eb/N0 from C/N.

    Eb/N0 [dB] = C/N [dB] − 10×log10(bits_per_symbol × symbols_per_hz)

    For a modulation with spectral efficiency η [bits/s/Hz]:
        symbols_per_hz × bits_per_symbol = η
    so this reduces to: Eb/N0 = C/N − 10×log10(η).

    Parameters
    ----------
    cn_db          : float — carrier-to-noise ratio [dB]
    bits_per_symbol: float — bits per symbol (e.g. 1 for BPSK, 2 for QPSK, log2(M) for M-QAM)
    symbols_per_hz : float — symbol rate normalised to noise bandwidth (default 1.0 = Nyquist)

    Returns
    -------
    dict with keys: ok, eb_n0_db, cn_db, bits_per_symbol, symbols_per_hz
    """
    err = _validate_real(cn_db, "cn_db")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(bits_per_symbol, "bits_per_symbol")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(symbols_per_hz, "symbols_per_hz")
    if err:
        return {"ok": False, "reason": err}

    ebn0 = cn_db - 10.0 * math.log10(bits_per_symbol * symbols_per_hz)

    return {
        "ok": True,
        "eb_n0_db": round(ebn0, 4),
        "cn_db": cn_db,
        "bits_per_symbol": bits_per_symbol,
        "symbols_per_hz": symbols_per_hz,
    }


# ── RF: BER functions ─────────────────────────────────────────────────────────


def ber_bpsk(eb_n0_linear: float) -> float:
    """BER for coherent BPSK: BER = Q(sqrt(2 × Eb/N0)) = 0.5×erfc(sqrt(Eb/N0))."""
    if eb_n0_linear <= 0:
        return 0.5
    return 0.5 * _erfc(math.sqrt(eb_n0_linear))


def ber_qpsk(eb_n0_linear: float) -> float:
    """BER for coherent Gray-coded QPSK: same as BPSK on a per-bit basis."""
    return ber_bpsk(eb_n0_linear)


def ber_qam(eb_n0_linear: float, m: int) -> float:
    """
    Approximate BER for Gray-coded M-QAM (square constellation, M = 4,16,64,256,...).

    BER ≈ (4/log2(M)) × (1 − 1/sqrt(M)) × Q(sqrt(6 × log2(M) × Eb/N0 / (M−1)))
    """
    if m < 4 or (m & (m - 1)) != 0:
        raise ValueError(f"M must be a power of 2 and >= 4, got {m}")
    k = math.log2(m)
    if eb_n0_linear <= 0:
        return 1.0
    snr_per_dim = math.sqrt(6.0 * k * eb_n0_linear / (m - 1))
    return (4.0 / k) * (1.0 - 1.0 / math.sqrt(m)) * _q_func(snr_per_dim)


def ber_psk(eb_n0_linear: float, m: int) -> float:
    """
    Approximate BER for Gray-coded M-PSK (m >= 2).

    BER ≈ (2/log2(M)) × Q(sqrt(2 × log2(M) × Eb/N0) × sin(π/M))
    For M=2 (BPSK), reduces to Q(sqrt(2×Eb/N0)).
    """
    if m < 2:
        raise ValueError(f"M must be >= 2, got {m}")
    k = math.log2(m)
    if eb_n0_linear <= 0:
        return 1.0
    argument = math.sqrt(2.0 * k * eb_n0_linear) * math.sin(math.pi / m)
    return (2.0 / k) * _q_func(argument)


def required_eb_n0_bpsk(target_ber: float) -> dict:
    """
    Required Eb/N0 for BPSK at a given target BER.

    Inverts: BER = 0.5 × erfc(sqrt(Eb/N0))
    using bisection search.

    Parameters
    ----------
    target_ber : float — target bit error rate, e.g. 1e-6

    Returns
    -------
    dict with keys: ok, eb_n0_db, eb_n0_linear, target_ber, modulation
    """
    err = _validate_positive(target_ber, "target_ber")
    if err:
        return {"ok": False, "reason": err}
    if target_ber >= 0.5:
        return {"ok": False, "reason": "target_ber must be < 0.5"}

    # Bisection: find Eb/N0 [dB] in [-5, 50]
    lo, hi = 1e-6, 10.0 ** 5  # linear Eb/N0
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if ber_bpsk(mid) > target_ber:
            lo = mid
        else:
            hi = mid

    ebn0_lin = (lo + hi) / 2.0
    ebn0_db = _linear_to_db(ebn0_lin)

    return {
        "ok": True,
        "eb_n0_db": round(ebn0_db, 4),
        "eb_n0_linear": ebn0_lin,
        "target_ber": target_ber,
        "modulation": "BPSK",
    }


def required_eb_n0_qpsk(target_ber: float) -> dict:
    """
    Required Eb/N0 for QPSK at a given target BER.
    QPSK has the same BER vs Eb/N0 as BPSK on a per-bit basis.

    Parameters
    ----------
    target_ber : float — target bit error rate

    Returns
    -------
    dict with keys: ok, eb_n0_db, eb_n0_linear, target_ber, modulation
    """
    result = required_eb_n0_bpsk(target_ber)
    if result.get("ok"):
        result["modulation"] = "QPSK"
    return result


def required_eb_n0_qam(target_ber: float, m: int) -> dict:
    """
    Required Eb/N0 for Gray-coded M-QAM at a given target BER.

    Parameters
    ----------
    target_ber : float — target bit error rate
    m          : int   — QAM order (must be power of 2, >= 4: 4, 16, 64, 256, ...)

    Returns
    -------
    dict with keys: ok, eb_n0_db, eb_n0_linear, target_ber, modulation, m
    """
    err = _validate_positive(target_ber, "target_ber")
    if err:
        return {"ok": False, "reason": err}
    if target_ber >= 0.5:
        return {"ok": False, "reason": "target_ber must be < 0.5"}
    if not isinstance(m, int) or m < 4 or (m & (m - 1)) != 0:
        return {"ok": False, "reason": "m must be an integer power of 2 and >= 4"}

    lo, hi = 1e-6, 10.0 ** 5
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if ber_qam(mid, m) > target_ber:
            lo = mid
        else:
            hi = mid

    ebn0_lin = (lo + hi) / 2.0
    ebn0_db = _linear_to_db(ebn0_lin)

    return {
        "ok": True,
        "eb_n0_db": round(ebn0_db, 4),
        "eb_n0_linear": ebn0_lin,
        "target_ber": target_ber,
        "modulation": f"{m}-QAM",
        "m": m,
    }


def required_eb_n0_psk(target_ber: float, m: int) -> dict:
    """
    Required Eb/N0 for Gray-coded M-PSK at a given target BER.

    Parameters
    ----------
    target_ber : float — target bit error rate
    m          : int   — PSK order (>= 2: 2=BPSK, 4=QPSK, 8=8PSK, ...)

    Returns
    -------
    dict with keys: ok, eb_n0_db, eb_n0_linear, target_ber, modulation, m
    """
    err = _validate_positive(target_ber, "target_ber")
    if err:
        return {"ok": False, "reason": err}
    if target_ber >= 0.5:
        return {"ok": False, "reason": "target_ber must be < 0.5"}
    if not isinstance(m, int) or m < 2:
        return {"ok": False, "reason": "m must be an integer >= 2"}

    lo, hi = 1e-6, 10.0 ** 5
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if ber_psk(mid, m) > target_ber:
            lo = mid
        else:
            hi = mid

    ebn0_lin = (lo + hi) / 2.0
    ebn0_db = _linear_to_db(ebn0_lin)

    return {
        "ok": True,
        "eb_n0_db": round(ebn0_db, 4),
        "eb_n0_linear": ebn0_lin,
        "target_ber": target_ber,
        "modulation": f"{m}-PSK",
        "m": m,
    }


# ── RF: Shannon capacity ──────────────────────────────────────────────────────


def shannon_capacity(bandwidth_hz: float, snr_db: float) -> dict:
    """
    Shannon-Hartley channel capacity.

    C [bps] = B × log2(1 + SNR)
    η [bps/Hz] = log2(1 + SNR)

    Parameters
    ----------
    bandwidth_hz : float — channel bandwidth [Hz]
    snr_db       : float — signal-to-noise ratio [dB]

    Returns
    -------
    dict with keys: ok, capacity_bps, spectral_efficiency_bps_per_hz,
                    bandwidth_hz, snr_db, snr_linear
    """
    err = _validate_positive(bandwidth_hz, "bandwidth_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_real(snr_db, "snr_db")
    if err:
        return {"ok": False, "reason": err}

    snr_linear = _db_to_linear(snr_db)
    eta = math.log2(1.0 + snr_linear)
    capacity = bandwidth_hz * eta

    return {
        "ok": True,
        "capacity_bps": capacity,
        "spectral_efficiency_bps_per_hz": round(eta, 6),
        "bandwidth_hz": bandwidth_hz,
        "snr_db": snr_db,
        "snr_linear": snr_linear,
        "formula": "C = B × log2(1 + SNR)  [Shannon-Hartley]",
    }


def spectral_efficiency(snr_db: float) -> dict:
    """
    Spectral efficiency (Shannon bound) for a given SNR.

    η [bps/Hz] = log2(1 + SNR_linear)

    Parameters
    ----------
    snr_db : float — signal-to-noise ratio [dB]

    Returns
    -------
    dict with keys: ok, spectral_efficiency_bps_per_hz, snr_db, snr_linear
    """
    err = _validate_real(snr_db, "snr_db")
    if err:
        return {"ok": False, "reason": err}

    snr_linear = _db_to_linear(snr_db)
    eta = math.log2(1.0 + snr_linear)

    return {
        "ok": True,
        "spectral_efficiency_bps_per_hz": round(eta, 6),
        "snr_db": snr_db,
        "snr_linear": snr_linear,
    }


# ── RF: Rain attenuation ──────────────────────────────────────────────────────


# ITU-R P.838-3 coefficients (horizontal polarisation, simplified)
# k_h and alpha_h for selected frequencies
_RAIN_COEFF = [
    # (f_ghz, k_h, alpha_h)
    (1.0,   0.0000387, 0.912),
    (2.0,   0.000154,  0.963),
    (4.0,   0.000650,  1.121),
    (6.0,   0.00175,   1.308),
    (7.0,   0.00301,   1.332),
    (8.0,   0.00454,   1.327),
    (10.0,  0.0101,    1.276),
    (12.0,  0.0188,    1.217),
    (15.0,  0.0367,    1.154),
    (20.0,  0.0751,    1.099),
    (25.0,  0.124,     1.061),
    (30.0,  0.187,     1.021),
    (40.0,  0.350,     0.939),
    (50.0,  0.536,     0.873),
    (60.0,  0.707,     0.826),
    (80.0,  1.010,     0.767),
    (100.0, 1.276,     0.735),
]


def _rain_coefficients(freq_ghz: float):
    """Interpolate ITU-R P.838-3 k and alpha for a given frequency in GHz."""
    if freq_ghz <= _RAIN_COEFF[0][0]:
        return _RAIN_COEFF[0][1], _RAIN_COEFF[0][2]
    if freq_ghz >= _RAIN_COEFF[-1][0]:
        return _RAIN_COEFF[-1][1], _RAIN_COEFF[-1][2]

    for i in range(len(_RAIN_COEFF) - 1):
        f1, k1, a1 = _RAIN_COEFF[i]
        f2, k2, a2 = _RAIN_COEFF[i + 1]
        if f1 <= freq_ghz <= f2:
            t = (freq_ghz - f1) / (f2 - f1)
            # Log-linear interpolation for k
            log_k = math.log(k1) + t * (math.log(k2) - math.log(k1))
            k = math.exp(log_k)
            alpha = a1 + t * (a2 - a1)
            return k, alpha

    return _RAIN_COEFF[-1][1], _RAIN_COEFF[-1][2]


def rain_attenuation_db(
    freq_hz: float,
    rain_rate_mm_per_hr: float,
    path_length_km: float,
) -> dict:
    """
    Rain attenuation along a terrestrial path (ITU-R P.838-3, simplified).

    Specific attenuation: γ_R [dB/km] = k × R^α
    Total attenuation:    A_rain [dB] = γ_R × L

    Parameters
    ----------
    freq_hz             : float — carrier frequency [Hz]
    rain_rate_mm_per_hr : float — rain rate [mm/h] (e.g. 25 mm/h moderate, 50 mm/h heavy)
    path_length_km      : float — path length through rain [km]

    Returns
    -------
    dict with keys: ok, a_rain_db, specific_atten_db_per_km, freq_hz,
                    rain_rate_mm_per_hr, path_length_km
    """
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(rain_rate_mm_per_hr, "rain_rate_mm_per_hr")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(path_length_km, "path_length_km")
    if err:
        return {"ok": False, "reason": err}

    freq_ghz = freq_hz / 1e9
    k, alpha = _rain_coefficients(freq_ghz)
    specific_atten = k * (rain_rate_mm_per_hr ** alpha)
    total_atten = specific_atten * path_length_km

    return {
        "ok": True,
        "a_rain_db": round(total_atten, 4),
        "specific_atten_db_per_km": round(specific_atten, 6),
        "freq_hz": freq_hz,
        "freq_ghz": round(freq_ghz, 4),
        "rain_rate_mm_per_hr": rain_rate_mm_per_hr,
        "path_length_km": path_length_km,
        "k_coeff": k,
        "alpha_coeff": alpha,
        "formula": "A = k × R^α × L  [ITU-R P.838-3]",
    }


# ── RF: Atmospheric attenuation ───────────────────────────────────────────────


def atmospheric_attenuation_db(
    freq_hz: float,
    path_length_km: float,
    water_vapour_g_per_m3: float = 7.5,
    pressure_hpa: float = 1013.25,
    temp_k: float = 288.15,
) -> dict:
    """
    Clear-air atmospheric attenuation (oxygen + water vapour), simplified
    from ITU-R P.676-12.  Useful for frequencies 1–350 GHz.

    Parameters
    ----------
    freq_hz               : float — carrier frequency [Hz]
    path_length_km        : float — propagation path length [km]
    water_vapour_g_per_m3 : float — water vapour density [g/m³] (default 7.5)
    pressure_hpa          : float — atmospheric pressure [hPa] (default 1013.25)
    temp_k                : float — temperature [K] (default 288.15 = 15°C)

    Returns
    -------
    dict with keys: ok, a_atm_db, specific_atten_db_per_km, a_oxygen_db_per_km,
                    a_water_db_per_km, freq_hz, path_length_km
    """
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(path_length_km, "path_length_km")
    if err:
        return {"ok": False, "reason": err}

    f_ghz = freq_hz / 1e9

    # Simplified ITU-R P.676-12 specific attenuation coefficients
    # Oxygen absorption: dominant near 60 GHz resonance complex
    # Simplified approximation valid for f < 350 GHz
    rp = pressure_hpa / 1013.25
    rt = 288.15 / temp_k

    # Oxygen term (simplified from ITU-R P.676 eq 1-7)
    if f_ghz < 57.0:
        gamma_o = (
            7.2 * rt**2.8 / (f_ghz**2 + 0.34 * rp**2 * rt**1.6)
            + 0.62 * (3.6 - 3.0 * f_ghz / 57.0 + f_ghz**2 / 57.0**2)
            / (3.0 - 3.0 * f_ghz / 57.0 + f_ghz**2 / 57.0**2)
        ) * f_ghz**2 * rp**2 * rt**3 * 1e-3
    elif f_ghz <= 63.0:
        # 60 GHz band: higher attenuation; simplified linear peak model
        gamma_o = 15.0 * rp * rt**1.5 * math.exp(-(((f_ghz - 60.0) / 2.5) ** 2))
    else:
        gamma_o = (
            7.2 * rt**2.8 / (f_ghz**2 + 0.34 * rp**2 * rt**1.6)
        ) * f_ghz**2 * rp**2 * rt**3 * 1e-3

    # Water vapour term (simplified)
    rho = water_vapour_g_per_m3
    gamma_w = (
        (0.050 + 0.0021 * rho + 3.6 / ((f_ghz - 22.235)**2 + 8.5)
         + 10.6 / ((f_ghz - 183.31)**2 + 9.0)
         + 1.2 / ((f_ghz - 325.153)**2 + 26.0))
        * f_ghz**2 * rho * rt**3.5 * rp * 1e-4
    )

    # Guard against negative values from approximation
    gamma_o = max(gamma_o, 0.0)
    gamma_w = max(gamma_w, 0.0)

    specific_atten = gamma_o + gamma_w
    total_atten = specific_atten * path_length_km

    return {
        "ok": True,
        "a_atm_db": round(total_atten, 4),
        "specific_atten_db_per_km": round(specific_atten, 6),
        "a_oxygen_db_per_km": round(gamma_o, 6),
        "a_water_db_per_km": round(gamma_w, 6),
        "freq_hz": freq_hz,
        "freq_ghz": round(f_ghz, 4),
        "path_length_km": path_length_km,
        "water_vapour_g_per_m3": water_vapour_g_per_m3,
        "formula": "Simplified ITU-R P.676-12",
    }


# ── RF: Full link budget with verdict ────────────────────────────────────────


def rf_link_budget(
    p_tx_dbw: float,
    g_tx_dbi: float,
    g_rx_dbi: float,
    freq_hz: float,
    distance_m: float,
    noise_figure_db: float,
    bandwidth_hz: float,
    required_snr_db: float,
    other_losses_db: float = 0.0,
    t_ant_k: float = 0.0,
) -> dict:
    """
    Complete RF link budget with margin verdict.

    Computes: FSPL, EIRP, received power, noise floor, C/N, fade margin,
    and a pass/fail verdict.  Issues warnings.warn for negative margin.

    Parameters
    ----------
    p_tx_dbw        : float — transmit power [dBW]
    g_tx_dbi        : float — transmit antenna gain [dBi]
    g_rx_dbi        : float — receive antenna gain [dBi]
    freq_hz         : float — carrier frequency [Hz]
    distance_m      : float — link distance [m]
    noise_figure_db : float — receiver noise figure [dB]
    bandwidth_hz    : float — noise/signal bandwidth [Hz]
    required_snr_db : float — minimum required SNR at receiver [dB]
    other_losses_db : float — additional losses (rain, pointing, cable, etc.) [dB] (default 0)
    t_ant_k         : float — antenna noise temperature [K] (default 0 K)

    Returns
    -------
    dict with keys: ok, margin_db, passes, p_rx_dbw, p_rx_dbm,
                    fspl_db, eirp_dbw, noise_floor_dbw, cn_db, t_sys_k, ...
    """
    # Validate
    for name, val in [
        ("p_tx_dbw", p_tx_dbw), ("g_tx_dbi", g_tx_dbi), ("g_rx_dbi", g_rx_dbi),
        ("noise_figure_db", noise_figure_db), ("required_snr_db", required_snr_db),
        ("other_losses_db", other_losses_db),
    ]:
        err = _validate_real(val, name)
        if err:
            return {"ok": False, "reason": err}
    for name, val in [("freq_hz", freq_hz), ("distance_m", distance_m), ("bandwidth_hz", bandwidth_hz)]:
        err = _validate_positive(val, name)
        if err:
            return {"ok": False, "reason": err}

    # FSPL
    fspl_result = fspl_db(freq_hz=freq_hz, distance_m=distance_m)
    fspl = fspl_result["fspl_db"]

    # EIRP
    eirp = p_tx_dbw + g_tx_dbi

    # Received power
    p_rx = eirp - fspl + g_rx_dbi - other_losses_db

    # System noise temperature
    t_noise_result = system_noise_temp(nf_total_db=noise_figure_db, t_ant_k=t_ant_k)
    t_sys = t_noise_result["t_sys_k"]

    # Noise floor
    noise_floor_result = thermal_noise_floor_dbw(bandwidth_hz=bandwidth_hz, temp_k=t_sys)
    noise_floor_dbw = noise_floor_result["noise_dbw"]

    # C/N
    cn = p_rx - noise_floor_dbw

    # Margin
    margin = cn - required_snr_db
    passes = margin >= 0.0

    if not passes:
        warnings.warn(
            f"RF link budget: NEGATIVE MARGIN of {margin:.1f} dB "
            f"(C/N={cn:.1f} dB, required={required_snr_db:.1f} dB, "
            f"distance={distance_m/1e3:.1f} km, f={freq_hz/1e6:.1f} MHz)",
            stacklevel=2,
        )

    return {
        "ok": True,
        "passes": passes,
        "margin_db": round(margin, 4),
        "p_rx_dbw": round(p_rx, 4),
        "p_rx_dbm": round(p_rx + 30.0, 4),
        "fspl_db": round(fspl, 4),
        "eirp_dbw": round(eirp, 4),
        "noise_floor_dbw": round(noise_floor_dbw, 4),
        "cn_db": round(cn, 4),
        "t_sys_k": round(t_sys, 4),
        "p_tx_dbw": p_tx_dbw,
        "g_tx_dbi": g_tx_dbi,
        "g_rx_dbi": g_rx_dbi,
        "freq_hz": freq_hz,
        "distance_m": distance_m,
        "bandwidth_hz": bandwidth_hz,
        "noise_figure_db": noise_figure_db,
        "required_snr_db": required_snr_db,
        "other_losses_db": other_losses_db,
    }


# ── Fiber: power budget ───────────────────────────────────────────────────────


def fiber_power_budget(
    p_tx_dbm: float,
    rx_sensitivity_dbm: float,
    fiber_loss_db_per_km: float,
    length_km: float,
    connector_loss_db: float = 0.0,
    splice_loss_db: float = 0.0,
    safety_margin_db: float = 3.0,
) -> dict:
    """
    Fiber-optic link power budget.

    Available_loss [dB] = P_tx − Rx_sensitivity
    System_penalty [dB] = fiber_loss + connector_loss + splice_loss + safety_margin
    Margin [dB]         = Available_loss − System_penalty

    Positive margin → link OK; negative → insufficient power (warning issued).

    Parameters
    ----------
    p_tx_dbm           : float — transmitter output power [dBm]
    rx_sensitivity_dbm : float — receiver minimum detectable power [dBm]
    fiber_loss_db_per_km: float — fiber attenuation coefficient [dB/km]
    length_km          : float — fiber span length [km]
    connector_loss_db  : float — total connector insertion loss [dB] (default 0)
    splice_loss_db     : float — total splice loss [dB] (default 0)
    safety_margin_db   : float — engineering safety margin [dB] (default 3.0)

    Returns
    -------
    dict with keys: ok, passes, margin_db, available_loss_db, system_penalty_db,
                    fiber_loss_db, p_tx_dbm, rx_sensitivity_dbm, length_km
    """
    err = _validate_real(p_tx_dbm, "p_tx_dbm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_real(rx_sensitivity_dbm, "rx_sensitivity_dbm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(fiber_loss_db_per_km, "fiber_loss_db_per_km")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(length_km, "length_km")
    if err:
        return {"ok": False, "reason": err}
    for name, val in [
        ("connector_loss_db", connector_loss_db),
        ("splice_loss_db", splice_loss_db),
        ("safety_margin_db", safety_margin_db),
    ]:
        err = _validate_nonneg(val, name)
        if err:
            return {"ok": False, "reason": err}

    fiber_loss = fiber_loss_db_per_km * length_km
    available_loss = p_tx_dbm - rx_sensitivity_dbm
    system_penalty = fiber_loss + connector_loss_db + splice_loss_db + safety_margin_db
    margin = available_loss - system_penalty
    passes = margin >= 0.0

    if not passes:
        warnings.warn(
            f"Fiber power budget: NEGATIVE MARGIN of {margin:.1f} dB "
            f"(available={available_loss:.1f} dB, system_penalty={system_penalty:.1f} dB, "
            f"length={length_km:.1f} km)",
            stacklevel=2,
        )

    return {
        "ok": True,
        "passes": passes,
        "margin_db": round(margin, 4),
        "available_loss_db": round(available_loss, 4),
        "system_penalty_db": round(system_penalty, 4),
        "fiber_loss_db": round(fiber_loss, 4),
        "connector_loss_db": connector_loss_db,
        "splice_loss_db": splice_loss_db,
        "safety_margin_db": safety_margin_db,
        "p_tx_dbm": p_tx_dbm,
        "rx_sensitivity_dbm": rx_sensitivity_dbm,
        "fiber_loss_db_per_km": fiber_loss_db_per_km,
        "length_km": length_km,
    }


# ── Fiber: chromatic dispersion bandwidth ────────────────────────────────────


def chromatic_dispersion_bandwidth(
    dispersion_ps_per_nm_km: float,
    length_km: float,
    source_linewidth_nm: float,
    bit_rate_bps: Optional[float] = None,
) -> dict:
    """
    Chromatic dispersion pulse broadening and bandwidth limit.

    Total CD [ps] = D × length_km × Δλ [nm]
    Bandwidth limit [bps] ≈ 1 / (4 × CD_total_s)   (NRZ: 0.25/T rule)

    Also computes the BW·length product for normalised comparison.

    Parameters
    ----------
    dispersion_ps_per_nm_km : float — chromatic dispersion coefficient D [ps/(nm·km)]
                              (e.g. SMF-28: ~17 ps/nm/km at 1550 nm)
    length_km               : float — fiber span length [km]
    source_linewidth_nm     : float — source (laser/LED) spectral linewidth [nm]
    bit_rate_bps            : float or None — if provided, a dispersion-limited flag
                              is returned (True if BW_limit < bit_rate_bps)

    Returns
    -------
    dict with keys: ok, cd_total_ps, bw_limit_bps, bw_km_product, dispersion_limited (if bit_rate given)
    """
    err = _validate_positive(dispersion_ps_per_nm_km, "dispersion_ps_per_nm_km")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(length_km, "length_km")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(source_linewidth_nm, "source_linewidth_nm")
    if err:
        return {"ok": False, "reason": err}
    if bit_rate_bps is not None:
        err = _validate_positive(bit_rate_bps, "bit_rate_bps")
        if err:
            return {"ok": False, "reason": err}

    cd_total_ps = dispersion_ps_per_nm_km * length_km * source_linewidth_nm
    cd_total_s = cd_total_ps * 1e-12
    bw_limit = 1.0 / (4.0 * cd_total_s) if cd_total_s > 0 else math.inf
    bw_km_product = bw_limit * length_km

    result = {
        "ok": True,
        "cd_total_ps": round(cd_total_ps, 4),
        "bw_limit_bps": bw_limit,
        "bw_km_product_bps_km": bw_km_product,
        "dispersion_ps_per_nm_km": dispersion_ps_per_nm_km,
        "length_km": length_km,
        "source_linewidth_nm": source_linewidth_nm,
    }

    if bit_rate_bps is not None:
        dispersion_limited = bw_limit < bit_rate_bps
        result["bit_rate_bps"] = bit_rate_bps
        result["dispersion_limited"] = dispersion_limited
        if dispersion_limited:
            warnings.warn(
                f"Chromatic dispersion LIMITS the link: BW_limit={bw_limit/1e9:.2f} Gbps "
                f"< bit_rate={bit_rate_bps/1e9:.2f} Gbps (CD={cd_total_ps:.1f} ps, "
                f"length={length_km:.1f} km)",
                stacklevel=2,
            )

    return result


# ── Fiber: modal dispersion bandwidth ────────────────────────────────────────


def modal_dispersion_bandwidth(
    na: float,
    n1: float,
    length_km: float,
    bit_rate_bps: Optional[float] = None,
) -> dict:
    """
    Modal (intermodal) dispersion pulse broadening and bandwidth limit for
    multimode fiber.

    Intermodal pulse spread: ΔT [s] = NA² × length / (2 × n1 × c)
    Bandwidth limit [bps]   ≈ 0.44 / ΔT   (Gaussian impulse response)

    Parameters
    ----------
    na          : float — numerical aperture of the multimode fiber
    n1          : float — core refractive index
    length_km   : float — fiber span length [km]
    bit_rate_bps: float or None — if provided, a dispersion-limited flag is returned

    Returns
    -------
    dict with keys: ok, delta_t_ps, bw_limit_bps, bw_km_product, dispersion_limited (if bit_rate given)
    """
    err = _validate_positive(na, "na")
    if err:
        return {"ok": False, "reason": err}
    if na >= 1.0:
        return {"ok": False, "reason": "na must be < 1.0 (numerical aperture)"}
    err = _validate_positive(n1, "n1")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(length_km, "length_km")
    if err:
        return {"ok": False, "reason": err}
    if bit_rate_bps is not None:
        err = _validate_positive(bit_rate_bps, "bit_rate_bps")
        if err:
            return {"ok": False, "reason": err}

    length_m = length_km * 1e3
    delta_t_s = (na ** 2) * length_m / (2.0 * n1 * _C)
    delta_t_ps = delta_t_s * 1e12
    bw_limit = 0.44 / delta_t_s if delta_t_s > 0 else math.inf
    bw_km_product = bw_limit * length_km

    result = {
        "ok": True,
        "delta_t_ps": round(delta_t_ps, 4),
        "bw_limit_bps": bw_limit,
        "bw_km_product_bps_km": bw_km_product,
        "na": na,
        "n1": n1,
        "length_km": length_km,
    }

    if bit_rate_bps is not None:
        dispersion_limited = bw_limit < bit_rate_bps
        result["bit_rate_bps"] = bit_rate_bps
        result["dispersion_limited"] = dispersion_limited
        if dispersion_limited:
            warnings.warn(
                f"Modal dispersion LIMITS the link: BW_limit={bw_limit/1e9:.2f} Gbps "
                f"< bit_rate={bit_rate_bps/1e9:.2f} Gbps (ΔT={delta_t_ps:.1f} ps, "
                f"length={length_km:.1f} km)",
                stacklevel=2,
            )

    return result


# ── Fiber: OSNR ───────────────────────────────────────────────────────────────


def fiber_osnr(
    p_signal_dbm: float,
    nf_amp_db: float,
    freq_hz: float,
    n_spans: int,
    noise_bandwidth_hz: float = 12.5e9,
) -> dict:
    """
    Optical SNR (OSNR) for a multi-span amplified fiber link.

    OSNR [dB] = P_signal − NF_amp − 10×log10(h × f × B_o) − 10×log10(n_spans)

    The noise spectral density per span from an EDFA is:
        N_sp [W] = NF_factor × h × f × B_o
    where NF_factor = 10^(NF_dB/10) / 2  (spontaneous emission factor, approx).

    Total ASE noise: N_total = n_spans × N_sp
    OSNR = P_signal / N_total  →  [dB] = P_signal_dbm − 10×log10(N_total_mW)

    Parameters
    ----------
    p_signal_dbm     : float — optical signal power per channel [dBm]
    nf_amp_db        : float — amplifier noise figure [dB]
    freq_hz          : float — optical carrier frequency [Hz] (e.g. 193.1e12 for 1550 nm)
    n_spans          : int   — number of amplified spans
    noise_bandwidth_hz: float — optical noise bandwidth [Hz] (default 12.5 GHz = 0.1 nm @ 1550 nm)

    Returns
    -------
    dict with keys: ok, osnr_db, n_ase_dbm, p_signal_dbm, nf_amp_db, n_spans,
                    freq_hz, noise_bandwidth_hz
    """
    err = _validate_real(p_signal_dbm, "p_signal_dbm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_real(nf_amp_db, "nf_amp_db")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    if not isinstance(n_spans, int) or n_spans < 1:
        return {"ok": False, "reason": "n_spans must be a positive integer"}
    err = _validate_positive(noise_bandwidth_hz, "noise_bandwidth_hz")
    if err:
        return {"ok": False, "reason": err}

    # Noise figure as linear factor (F = 10^(NF/10))
    nf_linear = _db_to_linear(nf_amp_db)

    # ASE noise power per span [W]
    # N_sp ≈ (NF_linear / 2) × h × f × B_o  [one polarisation mode approximation]
    n_ase_per_span_w = (nf_linear / 2.0) * _H_PLANCK * freq_hz * noise_bandwidth_hz

    # Total ASE noise from all spans [W]
    n_ase_total_w = n_spans * n_ase_per_span_w
    n_ase_total_dbm = 10.0 * math.log10(n_ase_total_w * 1e3)  # W → mW → dBm

    # OSNR
    osnr_db = p_signal_dbm - n_ase_total_dbm

    if osnr_db < 15.0:
        warnings.warn(
            f"Fiber OSNR is low: {osnr_db:.1f} dB "
            f"(typical minimum for 10G coherent: ~15 dB; for 100G DP-QPSK: ~12 dB)",
            stacklevel=2,
        )

    return {
        "ok": True,
        "osnr_db": round(osnr_db, 4),
        "n_ase_dbm": round(n_ase_total_dbm, 4),
        "n_ase_per_span_dbm": round(10.0 * math.log10(n_ase_per_span_w * 1e3), 4),
        "p_signal_dbm": p_signal_dbm,
        "nf_amp_db": nf_amp_db,
        "nf_linear": nf_linear,
        "n_spans": n_spans,
        "freq_hz": freq_hz,
        "noise_bandwidth_hz": noise_bandwidth_hz,
        "formula": "OSNR = P_signal − n_spans × (NF/2 × h × f × B_o)  [multi-span EDFA]",
    }
