"""
kerf_electronics.photonics.fibre_link — full fibre-optic link analysis.

Physics models
--------------
1. Fibre parameter table (ITU-T G.652/G.651)
   SMF-28: MFD ≈ 10.4 µm @ 1550 nm, α = 0.20 dB/km @ 1550 / 0.35 @ 1310,
           D = 17 ps/(nm·km) @ 1550, S = 0.090 ps/(nm²·km), zero-disp λ₀ ≈ 1310 nm.
   MMF OM4: core 50 µm, α = 2.3 dB/km @ 850, BW·L = 4700 MHz·km (EMB).

2. Mode-overlap coupling — Marcuse (1977) Gaussian-beam formula:
       η_overlap = [2·w₁·w₂/(w₁²+w₂²)]²  (MFD mismatch only)
   Lateral offset (Gaussian):
       η_offset = exp(-d²/(w₁²+w₂²)/2)
   Angular tilt (Gaussian, paraxial):
       η_tilt   = exp(-(π·n_core·w_avg·θ/λ)²)
   Total coupling efficiency:
       η = η_overlap · η_offset · η_tilt

3. Splice / connector loss:
       Fusion splice:      typ 0.05 dB (IEC 61300-3-4)
       Mechanical splice:  typ 0.10 dB
       SC/LC/FC connector: typ 0.20–0.50 dB (IEC 61300-3-34)

4. Dispersion penalty:
       Chromatic: Δτ_CD = |D| · Δλ · L   [ps]
       ISI BER penalty ≈ 1 dB if Δτ_CD ≈ 0.7 / bit_rate
   Modal (MMF):
       BW_modal = BW_per_km / sqrt(L)  [GHz, using concatenation rule]

5. Link budget:
       Power margin = Tx − Rx_sens − fibre_loss − connector_loss − splice_loss
                      − dispersion_penalty − splitter_excess_loss − ageing_margin
   Fibre loss = α · L  (wavelength-dependent from table)

6. Splitter excess loss:
       Ideal 1×N splitter: 10·log10(N)  splitting loss
       Excess loss (glass polish / coupler): 0.5–1.5 dB typ
       Total insertion loss = 10·log10(N) + excess_loss_dB

LLM tools
---------
  photonics_fibre_coupling     — Marcuse overlap + offset + tilt
  photonics_link_budget        — full end-to-end link margin
  photonics_dispersion_penalty — CD + modal BW penalty

Author: imranparuk
"""
from __future__ import annotations

import json
import math
import warnings
from typing import Any, Dict, Optional

from kerf_electronics._compat import ToolSpec, err_payload, ok_payload, register

# ── Physical constants ────────────────────────────────────────────────────────
_C_MPS = 2.99792458e8   # speed of light [m/s]

# ── Fibre parameter table ─────────────────────────────────────────────────────
#   keyed by canonical name; values are dicts with ITU-T parameters.
FIBRE_TABLE: Dict[str, Dict[str, Any]] = {
    "SMF-28": {
        "description": "Corning SMF-28 / ITU-T G.652.D single-mode fibre",
        "type": "SMF",
        "core_diameter_um": 8.2,
        "cladding_diameter_um": 125.0,
        "mfd_1550_um": 10.4,    # mode-field diameter @ 1550 nm [µm]
        "mfd_1310_um": 9.2,     # mode-field diameter @ 1310 nm [µm]
        "na": 0.14,
        "attenuation_1550_db_per_km": 0.20,
        "attenuation_1310_db_per_km": 0.35,
        "attenuation_850_db_per_km": None,  # SMF not rated at 850 nm
        "dispersion_1550_ps_per_nm_km": 17.0,   # chromatic D
        "dispersion_slope_ps_per_nm2_km": 0.090,
        "zero_disp_wavelength_nm": 1310.0,
        "polarisation_mode_dispersion_ps_per_sqrt_km": 0.04,  # PMD
        "n_core": 1.4682,
        "bandwidth_mhz_km": None,   # single-mode: dispersion limited, not BW×km
        "itu_standard": "G.652.D",
    },
    "SMF-28e+": {
        "description": "Corning SMF-28e+ extended-wavelength SMF / ITU-T G.657.A1",
        "type": "SMF",
        "core_diameter_um": 8.2,
        "cladding_diameter_um": 125.0,
        "mfd_1550_um": 10.4,
        "mfd_1310_um": 9.2,
        "na": 0.14,
        "attenuation_1550_db_per_km": 0.20,
        "attenuation_1310_db_per_km": 0.35,
        "attenuation_850_db_per_km": None,
        "dispersion_1550_ps_per_nm_km": 17.0,
        "dispersion_slope_ps_per_nm2_km": 0.090,
        "zero_disp_wavelength_nm": 1310.0,
        "polarisation_mode_dispersion_ps_per_sqrt_km": 0.04,
        "n_core": 1.4682,
        "bandwidth_mhz_km": None,
        "itu_standard": "G.657.A1",
    },
    "MMF-OM4": {
        "description": "50/125 µm graded-index MMF OM4 / ISO 11801",
        "type": "MMF",
        "core_diameter_um": 50.0,
        "cladding_diameter_um": 125.0,
        "mfd_1550_um": None,    # MFD not applicable for large-core MMF
        "mfd_1310_um": None,
        "na": 0.20,
        "attenuation_1550_db_per_km": 1.0,   # typical for OM4 at 1550 nm
        "attenuation_1310_db_per_km": 1.5,
        "attenuation_850_db_per_km": 2.3,    # primary rating wavelength
        "dispersion_1550_ps_per_nm_km": None,  # modal-dominated
        "dispersion_slope_ps_per_nm2_km": None,
        "zero_disp_wavelength_nm": None,
        "polarisation_mode_dispersion_ps_per_sqrt_km": None,
        "n_core": 1.4800,
        "bandwidth_mhz_km": 4700.0,   # EMB (effective modal bandwidth) @ 850 nm
        "bandwidth_mhz_km_1310": 500.0,
        "itu_standard": "ISO 11801 OM4",
    },
    "MMF-OM3": {
        "description": "50/125 µm graded-index MMF OM3 / ISO 11801",
        "type": "MMF",
        "core_diameter_um": 50.0,
        "cladding_diameter_um": 125.0,
        "mfd_1550_um": None,
        "mfd_1310_um": None,
        "na": 0.20,
        "attenuation_1550_db_per_km": 1.0,
        "attenuation_1310_db_per_km": 1.5,
        "attenuation_850_db_per_km": 2.5,
        "dispersion_1550_ps_per_nm_km": None,
        "dispersion_slope_ps_per_nm2_km": None,
        "zero_disp_wavelength_nm": None,
        "polarisation_mode_dispersion_ps_per_sqrt_km": None,
        "n_core": 1.4800,
        "bandwidth_mhz_km": 2000.0,  # EMB @ 850 nm
        "bandwidth_mhz_km_1310": 500.0,
        "itu_standard": "ISO 11801 OM3",
    },
    "DSF": {
        "description": "Dispersion-shifted single-mode fibre / ITU-T G.653",
        "type": "SMF",
        "core_diameter_um": 8.0,
        "cladding_diameter_um": 125.0,
        "mfd_1550_um": 8.0,
        "mfd_1310_um": None,
        "na": 0.14,
        "attenuation_1550_db_per_km": 0.22,
        "attenuation_1310_db_per_km": 0.40,
        "attenuation_850_db_per_km": None,
        "dispersion_1550_ps_per_nm_km": 0.0,  # zero-dispersion at 1550
        "dispersion_slope_ps_per_nm2_km": 0.070,
        "zero_disp_wavelength_nm": 1550.0,
        "polarisation_mode_dispersion_ps_per_sqrt_km": 0.05,
        "n_core": 1.4682,
        "bandwidth_mhz_km": None,
        "itu_standard": "G.653",
    },
    "NZDSF": {
        "description": "Non-zero dispersion-shifted SMF / ITU-T G.655",
        "type": "SMF",
        "core_diameter_um": 8.5,
        "cladding_diameter_um": 125.0,
        "mfd_1550_um": 9.0,
        "mfd_1310_um": None,
        "na": 0.14,
        "attenuation_1550_db_per_km": 0.22,
        "attenuation_1310_db_per_km": None,
        "attenuation_850_db_per_km": None,
        "dispersion_1550_ps_per_nm_km": 3.5,   # small but non-zero
        "dispersion_slope_ps_per_nm2_km": 0.060,
        "zero_disp_wavelength_nm": 1500.0,
        "polarisation_mode_dispersion_ps_per_sqrt_km": 0.05,
        "n_core": 1.4682,
        "bandwidth_mhz_km": None,
        "itu_standard": "G.655",
    },
}

# ── Splice / connector loss defaults (dB) ────────────────────────────────────
SPLICE_LOSS_DB = {
    "fusion":      0.05,   # IEC 61300-3-4, typical fusion splice
    "mechanical":  0.10,   # mechanical splice, e.g. Fibrlok
    "connector":   0.30,   # generic LC/SC/FC UPC (range 0.2–0.5)
    "connector_apc": 0.20, # angled-PC, lower back-reflection + loss
}


# ═══════════════════════════════════════════════════════════════════════════════
# Core physics functions
# ═══════════════════════════════════════════════════════════════════════════════

def mode_overlap_coupling(
    mfd1_um: float,
    mfd2_um: float,
    lateral_offset_um: float = 0.0,
    angular_mrad: float = 0.0,
    lambda_nm: float = 1550.0,
    n_core: float = 1.468,
) -> Dict[str, Any]:
    """
    Marcuse (1977) Gaussian-beam mode-coupling efficiency.

    Models:
      η_overlap: MFD mismatch (Gaussian overlap integral)
      η_offset:  lateral displacement d along a transverse axis
      η_tilt:    angular misalignment θ (paraxial, Gaussian propagation)
      η_total = η_overlap · η_offset · η_tilt

    Parameters
    ----------
    mfd1_um        : mode-field diameter of fibre 1 [µm]
    mfd2_um        : mode-field diameter of fibre 2 [µm]
    lateral_offset_um : lateral offset d [µm]
    angular_mrad   : angular tilt θ [mrad]
    lambda_nm      : wavelength [nm]
    n_core         : core refractive index (for tilt penalty)

    Returns
    -------
    dict with: ok, eta_overlap, eta_offset, eta_tilt, eta_total,
               coupling_loss_db, eta_overlap_db, eta_offset_db, eta_tilt_db
    """
    if mfd1_um <= 0 or mfd2_um <= 0:
        return {"ok": False, "reason": "MFD values must be positive", "code": "BAD_ARGS"}
    if lateral_offset_um < 0:
        return {"ok": False, "reason": "lateral_offset_um must be >= 0", "code": "BAD_ARGS"}
    if angular_mrad < 0:
        return {"ok": False, "reason": "angular_mrad must be >= 0", "code": "BAD_ARGS"}
    if lambda_nm <= 0:
        return {"ok": False, "reason": "lambda_nm must be positive", "code": "BAD_ARGS"}

    # mode-field radii (Gaussian beam waists w = MFD/2)
    w1 = mfd1_um / 2.0
    w2 = mfd2_um / 2.0

    # Marcuse Gaussian overlap (Eq. 2 in Marcuse 1977, BSTJ 56(5)):
    #   η_overlap = [2·w₁·w₂/(w₁²+w₂²)]²
    eta_overlap = (2.0 * w1 * w2 / (w1**2 + w2**2)) ** 2

    # Lateral offset: η_offset = exp(-d² / ((w₁²+w₂²)/2))
    # Derivation: overlap integral of two offset Gaussians
    d = lateral_offset_um
    if d == 0.0:
        eta_offset = 1.0
    else:
        eta_offset = math.exp(-(d**2) / ((w1**2 + w2**2) / 2.0))

    # Angular tilt: η_tilt = exp(-(π·n·w_avg·θ/λ)²)
    # θ in radians, λ in µm
    theta_rad = angular_mrad * 1e-3
    lambda_um = lambda_nm * 1e-3
    w_avg = 0.5 * (w1 + w2)
    if theta_rad == 0.0:
        eta_tilt = 1.0
    else:
        exponent = (math.pi * n_core * w_avg * theta_rad / lambda_um) ** 2
        eta_tilt = math.exp(-exponent)

    eta_total = eta_overlap * eta_offset * eta_tilt
    eta_total = max(eta_total, 1e-15)   # guard against underflow

    def _db(eta):
        return -10.0 * math.log10(max(eta, 1e-15))

    return {
        "ok": True,
        "eta_overlap": eta_overlap,
        "eta_offset": eta_offset,
        "eta_tilt": eta_tilt,
        "eta_total": eta_total,
        "eta_overlap_db": _db(eta_overlap),
        "eta_offset_db": _db(eta_offset),
        "eta_tilt_db": _db(eta_tilt),
        "coupling_loss_db": _db(eta_total),
        "mfd1_um": mfd1_um,
        "mfd2_um": mfd2_um,
        "lateral_offset_um": lateral_offset_um,
        "angular_mrad": angular_mrad,
        "lambda_nm": lambda_nm,
    }


def dispersion_penalty(
    fibre_type: str,
    length_km: float,
    bit_rate_gbps: float,
    wavelength_nm: float = 1550.0,
    source_linewidth_nm: float = 0.1,
    pmd_enabled: bool = True,
) -> Dict[str, Any]:
    """
    Chromatic dispersion + PMD + modal bandwidth penalty.

    Chromatic:
        Δτ_CD = |D(λ)| · Δλ · L            [ps]
        Rule of thumb ISI: if Δτ_CD > 0.7·T_bit → >1 dB penalty
        Approximate power penalty (Agrawal 2002, Ch. 2):
            P_CD_dB ≈ 10·log10(1 + (π²·D²·Δλ²·L²·B²)/(2·ln2))
            (simplified to linear ISI penalty for moderate dispersion)

    PMD (first-order only, Gaussian statistics):
        Δτ_PMD = PMD_coeff · sqrt(L)        [ps]
        Penalty ≈ 1 dB when Δτ_PMD > 0.1·T_bit

    Modal (MMF only):
        BW_modal = BW_per_km / sqrt(L)      [GHz]   (EMB concat. rule)
        Bandwidth limit: f_3dB ≈ BW_modal / 1 GHz

    Parameters
    ----------
    fibre_type        : key in FIBRE_TABLE
    length_km         : fibre span [km]
    bit_rate_gbps     : signalling rate [Gbps]
    wavelength_nm     : operating wavelength [nm]
    source_linewidth_nm : laser linewidth Δλ [nm] (FWHM)
    pmd_enabled       : include PMD penalty

    Returns
    -------
    dict with all penalty components and pass/fail flags
    """
    if fibre_type not in FIBRE_TABLE:
        known = ", ".join(FIBRE_TABLE.keys())
        return {
            "ok": False,
            "reason": f"Unknown fibre_type '{fibre_type}'. Known: {known}",
            "code": "BAD_ARGS",
        }
    if length_km <= 0:
        return {"ok": False, "reason": "length_km must be > 0", "code": "BAD_ARGS"}
    if bit_rate_gbps <= 0:
        return {"ok": False, "reason": "bit_rate_gbps must be > 0", "code": "BAD_ARGS"}

    fp = FIBRE_TABLE[fibre_type]
    T_bit_ps = 1e12 / (bit_rate_gbps * 1e9)   # bit period [ps]
    warns = []

    # ── Chromatic dispersion ──────────────────────────────────────────────────
    D = fp.get("dispersion_1550_ps_per_nm_km")
    if D is None and fp["type"] == "MMF":
        # Modal-dominated; CD is secondary for MMF at 850 nm
        D = 0.0
        warns.append("Chromatic dispersion not rated for MMF at this wavelength; "
                     "modal bandwidth dominates.")
    elif D is not None:
        # Interpolate if wavelength differs from 1550 nm using D slope
        D_slope = fp.get("dispersion_slope_ps_per_nm2_km", 0.0)
        lambda_0 = fp.get("zero_disp_wavelength_nm", 1310.0)
        if D_slope and lambda_0:
            # Sellmeier-like: D(λ) = D_slope · (λ - λ₀)
            D = D_slope * (wavelength_nm - lambda_0)
        # else use the table value for 1550 nm directly

    delta_tau_cd_ps = abs(D or 0.0) * source_linewidth_nm * length_km
    t_ratio_cd = delta_tau_cd_ps / T_bit_ps if T_bit_ps > 0 else 0.0

    # Approximate CD power penalty (Agrawal simplified)
    # P_penalty = 5·log10(1/(1 - (4·Δτ²·B²/0.5)²))  (2-dB penalty criterion)
    # Simpler industry rule: 1 dB @ Δτ_CD ≈ 0.5·T_bit
    if t_ratio_cd < 1e-9:
        cd_penalty_db = 0.0
    else:
        # Use: penalty ≈ -5·log10(1 - (Δτ_CD·B)²) for NRZ OOK (Agrawal 2012, §2.4)
        B_per_s = bit_rate_gbps * 1e9
        arg = (delta_tau_cd_ps * 1e-12 * B_per_s) ** 2
        arg = min(arg, 0.999)   # clamp to avoid log singularity
        cd_penalty_db = -5.0 * math.log10(max(1.0 - arg, 1e-9))

    cd_ok = delta_tau_cd_ps < 0.7 * T_bit_ps

    # ── PMD penalty ───────────────────────────────────────────────────────────
    pmd_coeff = fp.get("polarisation_mode_dispersion_ps_per_sqrt_km")
    delta_tau_pmd_ps: Optional[float] = None
    pmd_penalty_db = 0.0
    pmd_ok = True
    if pmd_enabled and pmd_coeff is not None:
        delta_tau_pmd_ps = pmd_coeff * math.sqrt(length_km)
        # 1 dB penalty budget threshold: Δτ_PMD > 0.1·T_bit
        pmd_ok = delta_tau_pmd_ps < 0.1 * T_bit_ps
        # Penalty (Menyuk 2003): ~ 0.5 dB per 0.1·T fraction
        pmd_ratio = delta_tau_pmd_ps / T_bit_ps
        pmd_penalty_db = 10.0 * pmd_ratio * 2.0   # rough: 1 dB / 5% T

    # ── Modal bandwidth (MMF only) ────────────────────────────────────────────
    bw_modal_ghz: Optional[float] = None
    modal_ok = True
    modal_penalty_db = 0.0
    bw_km = fp.get("bandwidth_mhz_km")
    if bw_km is not None:
        # EMB concatenation rule: BW_modal = BW_per_km / sqrt(L)
        bw_modal_mhz = bw_km / math.sqrt(length_km)
        bw_modal_ghz = bw_modal_mhz / 1e3
        # 3dB rolloff: signal BW ≈ 0.7·bit_rate for NRZ
        required_bw_ghz = 0.7 * bit_rate_gbps
        modal_ok = bw_modal_ghz >= required_bw_ghz
        if not modal_ok:
            deficit = required_bw_ghz / max(bw_modal_ghz, 1e-9)
            modal_penalty_db = 10.0 * math.log10(deficit)
            warns.append(
                f"Modal BW {bw_modal_ghz:.2f} GHz < required {required_bw_ghz:.2f} GHz "
                f"for {bit_rate_gbps} Gbps at {length_km} km."
            )

    total_dispersion_penalty_db = cd_penalty_db + pmd_penalty_db + modal_penalty_db

    if not cd_ok:
        warns.append(
            f"CD: Δτ_CD = {delta_tau_cd_ps:.1f} ps ≥ 0.7·T_bit "
            f"({0.7*T_bit_ps:.1f} ps) → ISI risk."
        )
    if pmd_enabled and not pmd_ok and delta_tau_pmd_ps is not None:
        warns.append(
            f"PMD: Δτ_PMD = {delta_tau_pmd_ps:.2f} ps ≥ 0.1·T_bit "
            f"({0.1*T_bit_ps:.2f} ps) → PMD penalty risk."
        )

    for w in warns:
        warnings.warn(w, UserWarning, stacklevel=2)

    return {
        "ok": True,
        "fibre_type": fibre_type,
        "length_km": length_km,
        "bit_rate_gbps": bit_rate_gbps,
        "wavelength_nm": wavelength_nm,
        "source_linewidth_nm": source_linewidth_nm,
        # Chromatic
        "D_ps_per_nm_km": D,
        "delta_tau_cd_ps": delta_tau_cd_ps,
        "cd_penalty_db": cd_penalty_db,
        "cd_ok": cd_ok,
        # PMD
        "pmd_coeff_ps_per_sqrt_km": pmd_coeff,
        "delta_tau_pmd_ps": delta_tau_pmd_ps,
        "pmd_penalty_db": pmd_penalty_db,
        "pmd_ok": pmd_ok,
        # Modal
        "bw_modal_ghz": bw_modal_ghz,
        "modal_penalty_db": modal_penalty_db,
        "modal_ok": modal_ok,
        # Total
        "total_dispersion_penalty_db": total_dispersion_penalty_db,
        "T_bit_ps": T_bit_ps,
        "warnings": warns,
    }


def splitter_loss(n_outputs: int, excess_loss_db: float = 0.7) -> Dict[str, Any]:
    """
    Optical splitter / coupler insertion loss.

    Ideal 1×N splitting loss: L_split = 10·log10(N)  [dB]
    Total insertion loss     : L_total = L_split + excess_loss_db

    Parameters
    ----------
    n_outputs     : number of output ports (N ≥ 2)
    excess_loss_db: additional excess loss [dB] (default 0.7 dB — typical PLC)

    Returns
    -------
    dict with splitting_loss_db, total_loss_db
    """
    if n_outputs < 2:
        return {"ok": False, "reason": "n_outputs must be >= 2", "code": "BAD_ARGS"}
    if excess_loss_db < 0:
        return {"ok": False, "reason": "excess_loss_db must be >= 0", "code": "BAD_ARGS"}

    split_loss = 10.0 * math.log10(n_outputs)
    total_loss = split_loss + excess_loss_db

    return {
        "ok": True,
        "n_outputs": n_outputs,
        "splitting_loss_db": split_loss,
        "excess_loss_db": excess_loss_db,
        "total_insertion_loss_db": total_loss,
    }


def _attenuation_at_wavelength(fp: Dict[str, Any], wavelength_nm: float) -> Optional[float]:
    """Interpolate/select fibre attenuation for a given wavelength."""
    # Exact window matches
    if abs(wavelength_nm - 1550) < 10 and fp.get("attenuation_1550_db_per_km") is not None:
        return fp["attenuation_1550_db_per_km"]
    if abs(wavelength_nm - 1310) < 10 and fp.get("attenuation_1310_db_per_km") is not None:
        return fp["attenuation_1310_db_per_km"]
    if abs(wavelength_nm - 850) < 20 and fp.get("attenuation_850_db_per_km") is not None:
        return fp["attenuation_850_db_per_km"]
    # Fall back to closest rated wavelength
    options = []
    if fp.get("attenuation_1550_db_per_km") is not None:
        options.append((abs(wavelength_nm - 1550), fp["attenuation_1550_db_per_km"]))
    if fp.get("attenuation_1310_db_per_km") is not None:
        options.append((abs(wavelength_nm - 1310), fp["attenuation_1310_db_per_km"]))
    if fp.get("attenuation_850_db_per_km") is not None:
        options.append((abs(wavelength_nm - 850), fp["attenuation_850_db_per_km"]))
    if options:
        return min(options, key=lambda x: x[0])[1]
    return None


def optical_link_budget(
    tx_dbm: float,
    rx_sens_dbm: float,
    fibre_type: str,
    length_km: float,
    n_connectors: int = 2,
    n_splices: int = 0,
    bit_rate_gbps: float = 10.0,
    wavelength_nm: float = 1550.0,
    source_linewidth_nm: float = 0.1,
    connector_loss_db: float = 0.30,
    splice_loss_db: float = 0.05,
    n_splitter_outputs: int = 0,
    splitter_excess_loss_db: float = 0.7,
    ageing_margin_db: float = 3.0,
    include_dispersion_penalty: bool = True,
    pmd_enabled: bool = True,
    margin_threshold_db: float = 0.0,
) -> Dict[str, Any]:
    """
    Full end-to-end optical link power budget.

    Budget equation:
        margin = Tx_dBm − Rx_sens_dBm
                 − fibre_loss_db
                 − connector_loss_db
                 − splice_loss_db
                 − splitter_loss_db    (if n_splitter_outputs > 0)
                 − dispersion_penalty_db
                 − ageing_margin_db

    Parameters
    ----------
    tx_dbm                 : transmit power [dBm]
    rx_sens_dbm            : receiver sensitivity (min detectable power) [dBm]
    fibre_type             : key in FIBRE_TABLE (e.g. 'SMF-28', 'MMF-OM4')
    length_km              : fibre span length [km]
    n_connectors           : total number of connector mated pairs
    n_splices              : total number of splices (fusion)
    bit_rate_gbps          : line rate [Gbps]
    wavelength_nm          : operating wavelength [nm]
    source_linewidth_nm    : laser linewidth Δλ [nm]
    connector_loss_db      : per-connector insertion loss [dB]
    splice_loss_db         : per-splice insertion loss [dB]
    n_splitter_outputs     : number of splitter output ports (0 = no splitter)
    splitter_excess_loss_db: PLC/FBT excess loss beyond ideal splitting [dB]
    ageing_margin_db       : ageing + repair margin [dB] (default 3.0)
    include_dispersion_penalty : add dispersion ISI penalty to budget
    pmd_enabled            : include PMD penalty
    margin_threshold_db    : minimum acceptable margin [dB] (default 0.0)

    Returns
    -------
    dict with full breakdown and pass/fail flags
    """
    if fibre_type not in FIBRE_TABLE:
        known = ", ".join(FIBRE_TABLE.keys())
        return {
            "ok": False,
            "reason": f"Unknown fibre_type '{fibre_type}'. Known: {known}",
            "code": "BAD_ARGS",
        }
    if length_km <= 0:
        return {"ok": False, "reason": "length_km must be > 0", "code": "BAD_ARGS"}
    if bit_rate_gbps <= 0:
        return {"ok": False, "reason": "bit_rate_gbps must be > 0", "code": "BAD_ARGS"}
    if n_connectors < 0:
        return {"ok": False, "reason": "n_connectors must be >= 0", "code": "BAD_ARGS"}
    if n_splices < 0:
        return {"ok": False, "reason": "n_splices must be >= 0", "code": "BAD_ARGS"}

    fp = FIBRE_TABLE[fibre_type]
    warns = []

    # ── Fibre attenuation ─────────────────────────────────────────────────────
    alpha = _attenuation_at_wavelength(fp, wavelength_nm)
    if alpha is None:
        return {
            "ok": False,
            "reason": f"No attenuation data for {fibre_type} at {wavelength_nm} nm",
            "code": "BAD_ARGS",
        }
    if fp["type"] == "SMF" and abs(wavelength_nm - 850) < 30:
        warns.append(f"{fibre_type} is a single-mode fibre — operation at 850 nm is "
                     "non-standard and attenuation is very high.")

    fibre_loss_db = alpha * length_km

    # ── Connector and splice losses ───────────────────────────────────────────
    total_connector_loss_db = n_connectors * connector_loss_db
    total_splice_loss_db = n_splices * splice_loss_db

    # ── Splitter loss ─────────────────────────────────────────────────────────
    splitter_total_db = 0.0
    splitter_breakdown: Optional[Dict[str, Any]] = None
    if n_splitter_outputs >= 2:
        s = splitter_loss(n_splitter_outputs, splitter_excess_loss_db)
        if not s["ok"]:
            return s
        splitter_total_db = s["total_insertion_loss_db"]
        splitter_breakdown = s

    # ── Dispersion penalty ────────────────────────────────────────────────────
    disp_penalty_db = 0.0
    disp_result: Optional[Dict[str, Any]] = None
    if include_dispersion_penalty:
        disp_result = dispersion_penalty(
            fibre_type=fibre_type,
            length_km=length_km,
            bit_rate_gbps=bit_rate_gbps,
            wavelength_nm=wavelength_nm,
            source_linewidth_nm=source_linewidth_nm,
            pmd_enabled=pmd_enabled,
        )
        if disp_result.get("ok"):
            disp_penalty_db = disp_result["total_dispersion_penalty_db"]
            warns.extend(disp_result.get("warnings", []))
        else:
            warns.append(f"Dispersion calc failed: {disp_result.get('reason')}")

    # ── Power budget ──────────────────────────────────────────────────────────
    total_loss_db = (
        fibre_loss_db
        + total_connector_loss_db
        + total_splice_loss_db
        + splitter_total_db
        + disp_penalty_db
        + ageing_margin_db
    )
    max_allowable_loss_db = tx_dbm - rx_sens_dbm
    margin_db = max_allowable_loss_db - total_loss_db
    link_ok = margin_db >= margin_threshold_db

    if not link_ok:
        warns.append(
            f"Link margin {margin_db:.2f} dB < threshold {margin_threshold_db:.2f} dB. "
            "Check transmit power, receiver sensitivity, or span length."
        )

    for w in warns:
        warnings.warn(w, UserWarning, stacklevel=2)

    return {
        "ok": True,
        "link_ok": link_ok,
        "margin_db": margin_db,
        # Inputs
        "tx_dbm": tx_dbm,
        "rx_sens_dbm": rx_sens_dbm,
        "fibre_type": fibre_type,
        "fibre_description": fp["description"],
        "length_km": length_km,
        "wavelength_nm": wavelength_nm,
        "bit_rate_gbps": bit_rate_gbps,
        # Loss breakdown [dB]
        "alpha_db_per_km": alpha,
        "fibre_loss_db": fibre_loss_db,
        "connector_loss_db_per": connector_loss_db,
        "n_connectors": n_connectors,
        "total_connector_loss_db": total_connector_loss_db,
        "splice_loss_db_per": splice_loss_db,
        "n_splices": n_splices,
        "total_splice_loss_db": total_splice_loss_db,
        "splitter_loss_db": splitter_total_db,
        "splitter_breakdown": splitter_breakdown,
        "dispersion_penalty_db": disp_penalty_db,
        "ageing_margin_db": ageing_margin_db,
        "total_loss_db": total_loss_db,
        "max_allowable_loss_db": max_allowable_loss_db,
        # Dispersion detail
        "dispersion_detail": disp_result,
        "warnings": warns,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LLM tool: photonics_fibre_coupling
# ═══════════════════════════════════════════════════════════════════════════════

_FIBRE_COUP_SPEC = ToolSpec(
    name="photonics_fibre_coupling",
    description=(
        "Marcuse (1977) fibre-to-fibre mode-coupling efficiency.\n\n"
        "Accounts for MFD mismatch, lateral offset, and angular misalignment.\n\n"
        "η_overlap = [2·w₁·w₂/(w₁²+w₂²)]²\n"
        "η_offset  = exp(-d²/((w₁²+w₂²)/2))\n"
        "η_tilt    = exp(-(π·n·w_avg·θ/λ)²)\n"
        "η_total   = η_overlap · η_offset · η_tilt\n\n"
        "Typical values:\n"
        "  SMF-28 fusion (same fibre): η ≈ 1.0, loss < 0.05 dB\n"
        "  5 µm lateral offset, 10 µm MFD: η ≈ 0.46, loss ≈ 3.4 dB\n\n"
        "Input: { mfd1_um, mfd2_um, lateral_offset_um?, angular_mrad?, "
        "lambda_nm?, n_core? }\n"
        "Returns: { ok, eta_total, coupling_loss_db, eta_overlap, "
        "eta_offset, eta_tilt, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "mfd1_um": {
                "type": "number",
                "description": "Mode-field diameter of fibre 1 [µm] (e.g. 10.4 for SMF-28).",
            },
            "mfd2_um": {
                "type": "number",
                "description": "Mode-field diameter of fibre 2 [µm].",
            },
            "lateral_offset_um": {
                "type": "number",
                "description": "Lateral transverse offset [µm] (default 0).",
            },
            "angular_mrad": {
                "type": "number",
                "description": "Angular tilt misalignment [mrad] (default 0).",
            },
            "lambda_nm": {
                "type": "number",
                "description": "Operating wavelength [nm] (default 1550).",
            },
            "n_core": {
                "type": "number",
                "description": "Core refractive index (default 1.468 for silica @ 1550).",
            },
        },
        "required": ["mfd1_um", "mfd2_um"],
    },
)


@register(_FIBRE_COUP_SPEC, write=False)
async def photonics_fibre_coupling(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = mode_overlap_coupling(
        mfd1_um=a.get("mfd1_um"),
        mfd2_um=a.get("mfd2_um"),
        lateral_offset_um=a.get("lateral_offset_um", 0.0),
        angular_mrad=a.get("angular_mrad", 0.0),
        lambda_nm=a.get("lambda_nm", 1550.0),
        n_core=a.get("n_core", 1.468),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown"), result.get("code", "ERROR"))
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# LLM tool: photonics_link_budget
# ═══════════════════════════════════════════════════════════════════════════════

_LINK_BUDGET_SPEC = ToolSpec(
    name="photonics_link_budget",
    description=(
        "Full optical link power budget with dispersion penalty.\n\n"
        "margin = Tx − Rx_sens − fibre_loss − connector_loss\n"
        "         − splice_loss − splitter_loss − dispersion_penalty\n"
        "         − ageing_margin\n\n"
        "Fibre types: SMF-28, SMF-28e+, MMF-OM4, MMF-OM3, DSF, NZDSF\n\n"
        "Validation case:\n"
        "  SMF-28 @ 1550 nm, 40 km, 2 connectors + 2 fusion splices,\n"
        "  Tx=0 dBm, Rx_sens=-28 dBm, 10 Gbps → margin ≈ 10 dB\n\n"
        "Input: { tx_dbm, rx_sens_dbm, fibre_type, length_km, "
        "n_connectors?, n_splices?, bit_rate_gbps?, wavelength_nm?, "
        "connector_loss_db?, splice_loss_db?, n_splitter_outputs?, "
        "ageing_margin_db?, include_dispersion_penalty? }\n"
        "Returns: { ok, link_ok, margin_db, fibre_loss_db, "
        "total_connector_loss_db, total_splice_loss_db, dispersion_penalty_db, "
        "total_loss_db, max_allowable_loss_db, dispersion_detail, ... }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tx_dbm": {
                "type": "number",
                "description": "Transmit power [dBm].",
            },
            "rx_sens_dbm": {
                "type": "number",
                "description": "Receiver sensitivity (minimum detectable power) [dBm].",
            },
            "fibre_type": {
                "type": "string",
                "description": "Fibre type: 'SMF-28', 'SMF-28e+', 'MMF-OM4', 'MMF-OM3', 'DSF', 'NZDSF'.",
            },
            "length_km": {
                "type": "number",
                "description": "Fibre span length [km].",
            },
            "n_connectors": {
                "type": "integer",
                "description": "Number of connector mated pairs (default 2).",
            },
            "n_splices": {
                "type": "integer",
                "description": "Number of fusion splices (default 0).",
            },
            "bit_rate_gbps": {
                "type": "number",
                "description": "Line bit rate [Gbps] (default 10).",
            },
            "wavelength_nm": {
                "type": "number",
                "description": "Operating wavelength [nm] (default 1550).",
            },
            "source_linewidth_nm": {
                "type": "number",
                "description": "Laser linewidth Δλ [nm] FWHM (default 0.1).",
            },
            "connector_loss_db": {
                "type": "number",
                "description": "Per-connector insertion loss [dB] (default 0.30).",
            },
            "splice_loss_db": {
                "type": "number",
                "description": "Per-splice insertion loss [dB] (default 0.05).",
            },
            "n_splitter_outputs": {
                "type": "integer",
                "description": "Splitter output ports; 0 = no splitter (default 0).",
            },
            "splitter_excess_loss_db": {
                "type": "number",
                "description": "Splitter excess loss beyond ideal splitting [dB] (default 0.7).",
            },
            "ageing_margin_db": {
                "type": "number",
                "description": "Ageing + repair margin [dB] (default 3.0).",
            },
            "include_dispersion_penalty": {
                "type": "boolean",
                "description": "Include CD/PMD/modal dispersion penalty (default true).",
            },
            "margin_threshold_db": {
                "type": "number",
                "description": "Minimum acceptable margin [dB] (default 0.0).",
            },
        },
        "required": ["tx_dbm", "rx_sens_dbm", "fibre_type", "length_km"],
    },
)


@register(_LINK_BUDGET_SPEC, write=False)
async def photonics_link_budget(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = optical_link_budget(
        tx_dbm=a.get("tx_dbm"),
        rx_sens_dbm=a.get("rx_sens_dbm"),
        fibre_type=a.get("fibre_type"),
        length_km=a.get("length_km"),
        n_connectors=a.get("n_connectors", 2),
        n_splices=a.get("n_splices", 0),
        bit_rate_gbps=a.get("bit_rate_gbps", 10.0),
        wavelength_nm=a.get("wavelength_nm", 1550.0),
        source_linewidth_nm=a.get("source_linewidth_nm", 0.1),
        connector_loss_db=a.get("connector_loss_db", 0.30),
        splice_loss_db=a.get("splice_loss_db", 0.05),
        n_splitter_outputs=a.get("n_splitter_outputs", 0),
        splitter_excess_loss_db=a.get("splitter_excess_loss_db", 0.7),
        ageing_margin_db=a.get("ageing_margin_db", 3.0),
        include_dispersion_penalty=a.get("include_dispersion_penalty", True),
        pmd_enabled=a.get("pmd_enabled", True),
        margin_threshold_db=a.get("margin_threshold_db", 0.0),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown"), result.get("code", "ERROR"))
    return ok_payload(result)


# ═══════════════════════════════════════════════════════════════════════════════
# LLM tool: photonics_dispersion_penalty
# ═══════════════════════════════════════════════════════════════════════════════

_DISP_SPEC = ToolSpec(
    name="photonics_dispersion_penalty",
    description=(
        "Chromatic dispersion, PMD, and modal bandwidth penalty for a fibre link.\n\n"
        "Chromatic: Δτ_CD = |D| · Δλ · L   [ps]\n"
        "PMD:       Δτ_PMD = PMD_coeff · √L  [ps]\n"
        "Modal BW:  BW = BW_per_km / √L      [GHz] (EMB concatenation rule)\n\n"
        "Fibre types: SMF-28, SMF-28e+, MMF-OM4, MMF-OM3, DSF, NZDSF\n\n"
        "Input: { fibre_type, length_km, bit_rate_gbps, wavelength_nm?, "
        "source_linewidth_nm?, pmd_enabled? }\n"
        "Returns: { ok, delta_tau_cd_ps, cd_penalty_db, cd_ok, "
        "delta_tau_pmd_ps, pmd_penalty_db, pmd_ok, "
        "bw_modal_ghz, modal_penalty_db, modal_ok, "
        "total_dispersion_penalty_db }"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "fibre_type": {
                "type": "string",
                "description": "Fibre type: 'SMF-28', 'MMF-OM4', etc.",
            },
            "length_km": {
                "type": "number",
                "description": "Fibre span length [km].",
            },
            "bit_rate_gbps": {
                "type": "number",
                "description": "Line bit rate [Gbps].",
            },
            "wavelength_nm": {
                "type": "number",
                "description": "Operating wavelength [nm] (default 1550).",
            },
            "source_linewidth_nm": {
                "type": "number",
                "description": "Laser linewidth Δλ [nm] FWHM (default 0.1).",
            },
            "pmd_enabled": {
                "type": "boolean",
                "description": "Include PMD penalty (default true).",
            },
        },
        "required": ["fibre_type", "length_km", "bit_rate_gbps"],
    },
)


@register(_DISP_SPEC, write=False)
async def photonics_dispersion_penalty(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    result = dispersion_penalty(
        fibre_type=a.get("fibre_type"),
        length_km=a.get("length_km"),
        bit_rate_gbps=a.get("bit_rate_gbps"),
        wavelength_nm=a.get("wavelength_nm", 1550.0),
        source_linewidth_nm=a.get("source_linewidth_nm", 0.1),
        pmd_enabled=a.get("pmd_enabled", True),
    )
    if not result.get("ok"):
        return err_payload(result.get("reason", "unknown"), result.get("code", "ERROR"))
    return ok_payload(result)


# ── TOOLS export ──────────────────────────────────────────────────────────────

TOOLS = [
    (_FIBRE_COUP_SPEC.name,  _FIBRE_COUP_SPEC,  photonics_fibre_coupling),
    (_LINK_BUDGET_SPEC.name, _LINK_BUDGET_SPEC, photonics_link_budget),
    (_DISP_SPEC.name,        _DISP_SPEC,        photonics_dispersion_penalty),
]
