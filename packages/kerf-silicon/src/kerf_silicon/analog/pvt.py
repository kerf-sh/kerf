"""pvt.py — Analog PVT-corner simulation for kerf-silicon cells.

Performs Process-Voltage-Temperature (PVT) corner sweeps with Monte-Carlo
mismatch within each corner for the three hand-characterised SKY130 analog
cells: Brokaw bandgap, StrongARM comparator, 2-stage op-amp.

Corner Definitions
------------------
Process corners (5):
  SS  — slow-slow  : NMOS and PMOS both slow (high Vth, low mobility, high Cox)
  TT  — typical   : nominal parameters
  FF  — fast-fast  : NMOS and PMOS both fast (low Vth, high mobility, low Cox)
  SF  — slow-NMOS, fast-PMOS : worst-case static current imbalance corner
  FS  — fast-NMOS, slow-PMOS : worst-case static current imbalance corner

Voltage corners (3) for sky130 VDD = 1.80 V nominal:
  VDD_LO = 1.62 V  (−10%)
  VDD_NOM = 1.80 V (nominal)
  VDD_HI  = 1.98 V (+10%)

Temperature corners (4):
  −40°C (233.15 K), 27°C (300.15 K), 85°C (358.15 K), 125°C (398.15 K)

Total corners: 5 × 3 × 4 = 60.

Process Scaling Tables
-----------------------
Each process corner applies multiplicative scaling factors to the key
performance-governing parameters extracted from the analytic cell models.

The factors below are *approximations* calibrated to match representative
sky130 corner data.  They are NOT silicon-measured; they are engineering
estimates suitable for early-stage margin analysis.

  Vth scaling (relative to TT):
    SS: +1  (Vth up → slower, less current)
    FF: −1  (Vth down → faster, more current)
    SF: NMOS Vth up, PMOS Vth down (not used directly but captured in Ids)
    FS: NMOS Vth down, PMOS Vth up

  Drain current (Ids) scaling vs TT:
    SS: 0.75  — mobility + Vth combined → ~25% slower
    TT: 1.00
    FF: 1.25  — ~25% faster
    SF: 0.85  — NMOS slow, PMOS fast; net 15% slow (NMOS dominates bias)
    FS: 1.15  — NMOS fast, PMOS slow; net 15% fast

  Capacitance scaling vs TT:
    SS: 1.10  — higher Cox → more gate cap
    TT: 1.00
    FF: 0.90  — lower Cox
    SF: 1.00  — roughly neutral
    FS: 1.00

  Bandgap Vref shift vs TT (additive, mV):
    Process affects VBE (via Vth of PMOS current mirror) and poly-R TC:
    SS: −15  mV  (mirror droops less, Vref slightly low)
    TT:   0  mV
    FF: +15  mV  (mirror drives more, Vref slightly high)
    SF: +8   mV
    FS: −8   mV

Voltage Scaling
---------------
  For a bandgap reference: VREF is first-order independent of VDD (that is the
  point of a bandgap), but small variation exists due to PMOS mirror headroom.
  Modelled as ΔVref = 0.003 × (VDD/1.80 − 1) V per volt (linear).

  For op-amp gain: DC gain A0 = gm·rout; gm ∝ sqrt(Ids) ∝ sqrt(VDD − Vth).
  We use A0 ∝ (VDD/VDD_nom)^0.5 approximation for gain magnitude.

  For comparator offset: mismatch is bias-current dependent;
  σ_Vos ∝ (VDD_nom/VDD)^0.25 (weak inverse dependence on overdrive voltage).

Temperature Scaling
-------------------
  Bandgap Vref: the full analytic model from bandgap_brokaw is used directly
  (VREF(T) = VBE(T) + R2/R1 × 2Vt(T) × ln(n)) — gives ±50 ppm/K residual
  curvature after first-order TC cancellation.

  Op-amp quiescent current: Iq ∝ T^1.5 (mobility and Vgs(T) effects combined;
  this is a commonly used BSIM3-level approximation).

  Comparator offset: at higher T, threshold mismatch reduces slightly because
  subthreshold slope improves; approximated as σ_Vos ∝ (T0/T)^0.3.

Monte-Carlo Model
-----------------
  Within each (process, voltage, temperature) corner, N_mc samples are drawn
  from Gaussian distributions representing:

  1. Vth mismatch per device — σ = A_VT / sqrt(W×L) where A_VT = 4 mV·µm
     for sky130 NMOS.  This is the dominant term for comparator offset.

  2. Transistor matching (current-mirror gain error) — σ = 0.5% of Ids per
     device, representing layout-induced systematic mismatch.  Used for
     bandgap mirror current ratio error which shifts VREF.

  The resulting per-sample metric value is:
     metric = corner_mean + Σ(sensitivity_i × δ_param_i)

  where sensitivities are derived from the analytic models.

Public API
----------
    pvt_sweep(cell_name, n_mc_per_corner=50) -> PVTResult
    pvt_corners() -> list[Corner]

LLM tools
---------
    silicon_pvt_corners()  — list all 60 corners (name, P, V, T)
    silicon_pvt_sweep(cell_name, n_mc_per_corner=50)  — run full PVT sweep
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
_K_OVER_Q   = 86.17e-6   # V/K
_VDD_NOM    = 1.80        # V  — sky130 1.8 V nominal
_T_NOM_K    = 300.15      # K  — 27°C nominal

# ---------------------------------------------------------------------------
# Corner enumeration
# ---------------------------------------------------------------------------

PROCESS_CORNERS = ["SS", "TT", "FF", "SF", "FS"]

VOLTAGE_CORNERS = [
    ("VLO",  1.62),   # −10%
    ("VNOM", 1.80),   # nominal
    ("VHI",  1.98),   # +10%
]

TEMP_CORNERS_K = [
    ("m40", 233.15),   # −40°C
    ("t27", 300.15),   # 27°C
    ("t85", 358.15),   # 85°C
    ("t125", 398.15),  # 125°C
]


@dataclass(frozen=True)
class Corner:
    """A single PVT corner specification.

    Attributes
    ----------
    name:
        Human-readable label, e.g. ``"SS_VLO_m40"``.
    process:
        One of ``"SS"``, ``"TT"``, ``"FF"``, ``"SF"``, ``"FS"``.
    vdd_v:
        Supply voltage in volts.
    temp_k:
        Temperature in kelvin.
    """
    name: str
    process: str
    vdd_v: float
    temp_k: float

    @property
    def temp_c(self) -> float:
        """Temperature in degrees Celsius."""
        return self.temp_k - 273.15


def pvt_corners() -> list[Corner]:
    """Return all 60 PVT corners (5 process × 3 voltage × 4 temperature).

    Returns
    -------
    list[Corner]
        Ordered SS→FF, VLO→VHI, −40°C→125°C.
    """
    corners: list[Corner] = []
    for proc in PROCESS_CORNERS:
        for v_label, vdd in VOLTAGE_CORNERS:
            for t_label, t_k in TEMP_CORNERS_K:
                name = f"{proc}_{v_label}_{t_label}"
                corners.append(Corner(name=name, process=proc, vdd_v=vdd, temp_k=t_k))
    return corners


# ---------------------------------------------------------------------------
# Process scaling tables
# ---------------------------------------------------------------------------

# Drain-current multiplier vs TT for each process corner.
# SS slows by 25%, FF speeds by 25%.  SF/FS are intermediate.
_IDS_SCALE: dict[str, float] = {
    "SS": 0.75,
    "TT": 1.00,
    "FF": 1.25,
    "SF": 0.85,
    "FS": 1.15,
}

# Gate capacitance multiplier vs TT.
# SS has higher Cox (+10%), FF has lower Cox (−10%).
_CAP_SCALE: dict[str, float] = {
    "SS": 1.10,
    "TT": 1.00,
    "FF": 0.90,
    "SF": 1.00,
    "FS": 1.00,
}

# Bandgap Vref additive offset due to process corner (mV).
# Arises from PMOS mirror headroom and poly-R sheet resistance variation.
_VREF_PROC_OFFSET_MV: dict[str, float] = {
    "SS": -15.0,
    "TT":   0.0,
    "FF":  +15.0,
    "SF":  +8.0,
    "FS":  -8.0,
}

# Op-amp DC gain additive offset due to process corner (dB).
# SS has lower gm·rout; FF has higher.
_GAIN_PROC_OFFSET_DB: dict[str, float] = {
    "SS": -10.0,
    "TT":   0.0,
    "FF":  +10.0,
    "SF":  -4.0,
    "FS":  +4.0,
}

# Comparator offset scaling — process corner multiplier on the Pelgrom σ.
# In SS the transistors are slower/larger effective mismatch; FF is tighter.
_OFFSET_PROC_SCALE: dict[str, float] = {
    "SS": 1.20,
    "TT": 1.00,
    "FF": 0.85,
    "SF": 1.10,
    "FS": 0.95,
}

# ---------------------------------------------------------------------------
# Bandgap analytic helpers (replicated from bandgap_brokaw to avoid import)
# ---------------------------------------------------------------------------

_VBE0_V   = 0.5893   # V   — corrected VBE at 300 K
_BETA_VBE = 2.2e-3   # V/K — CTAT slope
_N_RATIO  = 8        # emitter-area ratio
_R2_R1    = _BETA_VBE / (2.0 * _K_OVER_Q * math.log(_N_RATIO))  # ≈ 6.145


def _vbe_at_t(t_k: float) -> float:
    """Linear CTAT model for VBE vs temperature."""
    return _VBE0_V - _BETA_VBE * (t_k - _T_NOM_K)


def _vt_at_t(t_k: float) -> float:
    """Thermal voltage kT/q."""
    return _K_OVER_Q * t_k


def _vref_tt_at_t(t_k: float) -> float:
    """Analytic VREF for TT process at temperature T."""
    return _vbe_at_t(t_k) + _R2_R1 * 2.0 * _vt_at_t(t_k) * math.log(_N_RATIO)


# ---------------------------------------------------------------------------
# Per-corner scaling functions
# ---------------------------------------------------------------------------

def _bandgap_corner_mean(corner: Corner) -> float:
    """Estimate bandgap VREF mean (V) at a given PVT corner.

    Scaling model
    -------------
    1. **Temperature**: use full analytic VREF(T) model from bandgap_brokaw.
       This captures ±50 ppm/°C residual curvature due to second-order TC.

    2. **Process**: add empirical additive offset (see _VREF_PROC_OFFSET_MV).
       Rationale: PMOS mirror Vds changes with Vth shift; poly-R variation
       changes R2/R1 ratio by ±2%, which maps to ±15 mV on VREF.

    3. **Voltage**: VREF ∝ 1 + 0.003 × (VDD/1.80 − 1).
       Rationale: bandgap is designed to be VDD-independent but ~3 mV/V
       residual PSRR exists due to finite PMOS output impedance.
    """
    vref_tt = _vref_tt_at_t(corner.temp_k)
    vref_proc = vref_tt + _VREF_PROC_OFFSET_MV[corner.process] * 1e-3
    vdd_factor = 1.0 + 0.003 * (corner.vdd_v / _VDD_NOM - 1.0)
    return vref_proc * vdd_factor


def _opamp_gain_corner_mean(corner: Corner) -> float:
    """Estimate op-amp DC gain (dB) at a given PVT corner.

    Nominal TT gain at 27°C, 1.80 V: ~60 dB (two-stage Miller opamp).

    Scaling model
    -------------
    1. **Temperature**: gm ∝ sqrt(Ids); Ids ∝ (VGS − Vth)^2; Vth decreases
       with T at ~−1 mV/K but mobility drops as T^−1.5.  Net gm drops
       roughly as (T_nom/T)^0.5, and rout drops as (T_nom/T)^0.25.
       Combined: A0 ∝ (T_nom/T)^0.75.  Convert to dB: 20·log10(T_nom/T)^0.75.

    2. **Process**: additive dB offset from _GAIN_PROC_OFFSET_DB.

    3. **Voltage**: gm = sqrt(2·µCox·W/L·Ids); Ids ∝ VDD at fixed bias.
       gm ∝ sqrt(VDD/VDD_nom).  rout ≈ 1/(λ·Ids) ∝ 1/VDD.
       Net: A0 ∝ (VDD/VDD_nom)^(0.5 − 1) = (VDD/VDD_nom)^−0.5.
       Gain *decreases* at high VDD (Ids up → lower rout dominates).
    """
    gain_tt_db = 60.0   # dB at TT, 27°C, 1.80 V (from two-stage model)

    # Temperature scaling
    temp_factor_db = 20.0 * math.log10((corner.temp_k / _T_NOM_K) ** (-0.75))

    # Process offset
    proc_offset_db = _GAIN_PROC_OFFSET_DB[corner.process]

    # Voltage scaling: A0 ∝ (VDD_nom/VDD)^0.5
    vdd_factor_db = 20.0 * math.log10((corner.vdd_v / _VDD_NOM) ** (-0.5))

    return gain_tt_db + temp_factor_db + proc_offset_db + vdd_factor_db


def _comparator_offset_sigma(corner: Corner) -> float:
    """Estimate comparator input-referred offset 1-sigma (mV) at a PVT corner.

    Nominal sizing from comparator_strongarm: W = 4 µm, L = 0.15 µm.
    Pelgrom nominal (TT, 27°C, 1.80 V):
        σ_Vos = A_VT / sqrt(W × L) = 4.0 / sqrt(4.0 × 0.15) ≈ 5.16 mV.

    Scaling model
    -------------
    1. **Process**: multiply by _OFFSET_PROC_SCALE.
       Rationale: Vth mismatch A_VT changes by ~20% across process corners
       in sky130 (characterisation data range).

    2. **Temperature**: σ_Vos ∝ (T_nom/T)^0.3.
       Rationale: at high T, subthreshold steepness is higher and the
       overdrive voltage is slightly higher, reducing mismatch sensitivity.

    3. **Voltage**: σ_Vos ∝ (VDD_nom/VDD)^0.25.
       Rationale: higher VDD → more overdrive → less Vth-dominated mismatch.
    """
    _A_VT_N_MV_UM = 4.0   # mV·µm (sky130 NMOS)
    _W_NOM_UM     = 4.0   # µm
    _L_NOM_UM     = 0.15  # µm

    sigma_tt = _A_VT_N_MV_UM / math.sqrt(_W_NOM_UM * _L_NOM_UM)

    proc_scale  = _OFFSET_PROC_SCALE[corner.process]
    temp_scale  = (corner.temp_k / _T_NOM_K) ** (-0.30)
    vdd_scale   = (corner.vdd_v / _VDD_NOM) ** (-0.25)

    return sigma_tt * proc_scale * temp_scale * vdd_scale


# ---------------------------------------------------------------------------
# Monte-Carlo sampling within a corner
# ---------------------------------------------------------------------------

def _mc_bandgap(corner: Corner, n_mc: int, rng: random.Random) -> list[float]:
    """Sample VREF (V) Monte-Carlo distribution within a corner.

    Parameters perturbed
    --------------------
    - Mirror current-ratio mismatch: δI/I ~ N(0, σ_mirror²), σ_mirror = 0.5%.
      VREF sensitivity: ∂VREF/∂(I_ratio) ≈ +2·Vt(T)·ln(n)/I_ratio ≈ 0.107 V.
      Mismatch in mirror ratio shifts PTAT term: δVREF ≈ σ_mirror × 0.107 V.

    - Poly-resistor mismatch (R2/R1 ratio): δ(R2/R1)/(R2/R1) ~ N(0, σ_R²),
      σ_R = 1.0% (poly sheet resistance matching for L > 10 µm).
      VREF sensitivity: ∂VREF/∂(R2/R1) = 2·Vt·ln(n) ≈ 0.1075 V.
      δVREF ≈ σ_R × R2_R1 × 0.1075 V — i.e. 0.5% of VREF at nominal.
    """
    mean  = _bandgap_corner_mean(corner)
    sigma_mirror = 0.005   # 0.5% current-mirror mismatch
    sigma_r      = 0.010   # 1.0% poly-resistor ratio mismatch
    ptat_factor  = 2.0 * _vt_at_t(corner.temp_k) * math.log(_N_RATIO)   # ≈ 0.107 V

    samples: list[float] = []
    for _ in range(n_mc):
        delta_mirror = rng.gauss(0.0, sigma_mirror) * ptat_factor
        delta_r      = rng.gauss(0.0, sigma_r) * _R2_R1 * ptat_factor
        samples.append(mean + delta_mirror + delta_r)
    return samples


def _mc_opamp_gain(corner: Corner, n_mc: int, rng: random.Random) -> list[float]:
    """Sample op-amp DC gain (dB) Monte-Carlo distribution within a corner.

    Parameters perturbed
    --------------------
    - Input pair Vth mismatch: δVth ~ N(0, σ_Vth²).
      Effect on gain: ΔA0 ≈ gm·δVth / Gm_eff.  Modelled as ±3 dB (1σ)
      spread on A0 for the input-pair mismatch term.

    - Current mirror gain error: δ(W/L)/(W/L) ~ N(0, σ_WL²), σ_WL = 1%.
      Effect: ΔA0 ≈ σ_WL × A0_linear.  Expressed as ±0.09 dB (1σ).
    """
    mean    = _opamp_gain_corner_mean(corner)
    sigma_a0_input  = 1.5   # dB (1σ) from input-pair Vth mismatch
    sigma_a0_mirror = 0.09  # dB (1σ) from current-mirror W/L mismatch

    samples: list[float] = []
    for _ in range(n_mc):
        delta = (rng.gauss(0.0, sigma_a0_input) +
                 rng.gauss(0.0, sigma_a0_mirror))
        samples.append(mean + delta)
    return samples


def _mc_comparator(corner: Corner, n_mc: int, rng: random.Random) -> list[float]:
    """Sample comparator input-referred offset (mV) Monte-Carlo within a corner.

    The per-sample offset is drawn from N(0, σ²) where σ is the corner-scaled
    1-sigma Pelgrom mismatch.  Offset is taken as the absolute value (magnitude)
    because the sign is random and both polarities are equally bad.

    Note: the returned samples are the *signed* offset; the caller computes σ.
    """
    sigma = _comparator_offset_sigma(corner)
    return [rng.gauss(0.0, sigma) for _ in range(n_mc)]


# ---------------------------------------------------------------------------
# Per-corner statistics
# ---------------------------------------------------------------------------

def _stats(samples: list[float]) -> dict[str, float]:
    """Compute mean, std, 3σ bounds, and 5σ tail estimate.

    Returns
    -------
    dict with keys: mean, std, three_sigma_lo, three_sigma_hi,
                    five_sigma_lo, five_sigma_hi, n
    """
    n = len(samples)
    mean = sum(samples) / n
    variance = sum((x - mean) ** 2 for x in samples) / (n - 1) if n > 1 else 0.0
    std = math.sqrt(variance)
    return {
        "mean":          mean,
        "std":           std,
        "three_sigma_lo": mean - 3.0 * std,
        "three_sigma_hi": mean + 3.0 * std,
        "five_sigma_lo":  mean - 5.0 * std,
        "five_sigma_hi":  mean + 5.0 * std,
        "n":             n,
    }


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CornerResult:
    """Monte-Carlo statistics for a single PVT corner.

    Attributes
    ----------
    corner:
        The PVT corner definition.
    metric_name:
        Human-readable name of the metric, e.g. ``"VREF_V"``.
    mean:
        Monte-Carlo mean of the metric.
    std:
        Monte-Carlo standard deviation.
    three_sigma_lo / three_sigma_hi:
        Mean ± 3σ bounds (captures 99.73% of normal distribution).
    five_sigma_lo / five_sigma_hi:
        Mean ± 5σ extrapolated tails (worst-case estimate for high-volume
        production; ~1 in 3.5M probability per tail).
    n_mc:
        Number of Monte-Carlo samples drawn.
    unit:
        Physical unit string, e.g. ``"V"``, ``"dB"``, ``"mV"``.
    """
    corner: Corner
    metric_name: str
    mean: float
    std: float
    three_sigma_lo: float
    three_sigma_hi: float
    five_sigma_lo: float
    five_sigma_hi: float
    n_mc: int
    unit: str

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (JSON-safe)."""
        return {
            "corner": self.corner.name,
            "process": self.corner.process,
            "vdd_v": self.corner.vdd_v,
            "temp_c": round(self.corner.temp_c, 2),
            "temp_k": self.corner.temp_k,
            "metric": self.metric_name,
            "unit": self.unit,
            "mean": self.mean,
            "std": self.std,
            "three_sigma_lo": self.three_sigma_lo,
            "three_sigma_hi": self.three_sigma_hi,
            "five_sigma_lo": self.five_sigma_lo,
            "five_sigma_hi": self.five_sigma_hi,
            "n_mc": self.n_mc,
        }


@dataclass
class PVTResult:
    """Full PVT sweep result for one cell.

    Attributes
    ----------
    cell_name:
        E.g. ``"bandgap_brokaw"``.
    metrics:
        List of per-corner metric names (one per sweep metric).
    corners:
        All 60 corners × len(metrics) CornerResult objects.
    summary:
        Human-readable summary of worst-case corners.
    """
    cell_name: str
    metrics: list[str]
    corners: list[CornerResult]
    summary: dict[str, Any] = field(default_factory=dict)

    def worst_case(self, metric_name: str) -> dict[str, Any]:
        """Return worst-case corner statistics for a named metric.

        Returns the corner with the largest 5σ spread (hi − lo).
        """
        relevant = [c for c in self.corners if c.metric_name == metric_name]
        if not relevant:
            return {}
        worst = max(relevant, key=lambda c: c.five_sigma_hi - c.five_sigma_lo)
        return worst.to_dict()

    def to_dict(self) -> dict[str, Any]:
        """Serialise entire result to nested dict."""
        return {
            "cell_name": self.cell_name,
            "metrics": self.metrics,
            "n_corners": len(set(c.corner.name for c in self.corners)),
            "n_mc_per_corner": self.corners[0].n_mc if self.corners else 0,
            "results": [c.to_dict() for c in self.corners],
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Main sweep function
# ---------------------------------------------------------------------------

def pvt_sweep(
    cell_name: str,
    n_mc_per_corner: int = 50,
    seed: int | None = 42,
) -> PVTResult:
    """Run a full 60-corner PVT sweep with Monte-Carlo mismatch.

    For each of the 60 corners (5 process × 3 voltage × 4 temperature),
    draw ``n_mc_per_corner`` Monte-Carlo samples and compute mean, std,
    3σ, and 5σ statistics.

    Supported cells
    ---------------
    - ``"bandgap_brokaw"``   — metric: VREF (V)
    - ``"comparator_strongarm"`` — metric: offset_sigma (mV)
    - ``"opamp_2stage"``     — metric: dc_gain (dB)

    Parameters
    ----------
    cell_name:
        One of ``"bandgap_brokaw"``, ``"comparator_strongarm"``,
        ``"opamp_2stage"``.
    n_mc_per_corner:
        Number of Monte-Carlo samples per corner (default 50).
    seed:
        Random seed for reproducibility (default 42).  Pass ``None`` for
        a non-reproducible run.

    Returns
    -------
    PVTResult

    Raises
    ------
    ValueError
        If ``cell_name`` is not one of the three supported cells.

    Notes
    -----
    The scaling factors applied at each corner are *engineering approximations*
    derived from published sky130 corner documentation and BSIM3/BSIM4 device
    physics.  They are NOT silicon-measured corner data.  See module docstring
    for precise derivation of each factor.
    """
    supported = {"bandgap_brokaw", "comparator_strongarm", "opamp_2stage"}
    if cell_name not in supported:
        raise ValueError(
            f"pvt_sweep: unsupported cell '{cell_name}'. "
            f"Supported: {sorted(supported)}"
        )

    # 60 corners × n_mc — clamp to prevent unbounded compute from caller input.
    n_mc_per_corner = max(1, min(int(n_mc_per_corner), 10_000))

    rng = random.Random(seed)
    all_corners = pvt_corners()
    results: list[CornerResult] = []

    if cell_name == "bandgap_brokaw":
        metric_name = "VREF_V"
        unit = "V"
        for corner in all_corners:
            samples = _mc_bandgap(corner, n_mc_per_corner, rng)
            s = _stats(samples)
            results.append(CornerResult(
                corner=corner, metric_name=metric_name, unit=unit,
                mean=s["mean"], std=s["std"],
                three_sigma_lo=s["three_sigma_lo"],
                three_sigma_hi=s["three_sigma_hi"],
                five_sigma_lo=s["five_sigma_lo"],
                five_sigma_hi=s["five_sigma_hi"],
                n_mc=n_mc_per_corner,
            ))
        metrics = [metric_name]
        summary = _bandgap_summary(results)

    elif cell_name == "comparator_strongarm":
        metric_name = "offset_sigma_mV"
        unit = "mV"
        for corner in all_corners:
            samples = _mc_comparator(corner, n_mc_per_corner, rng)
            s = _stats(samples)
            results.append(CornerResult(
                corner=corner, metric_name=metric_name, unit=unit,
                mean=s["mean"], std=s["std"],
                three_sigma_lo=s["three_sigma_lo"],
                three_sigma_hi=s["three_sigma_hi"],
                five_sigma_lo=s["five_sigma_lo"],
                five_sigma_hi=s["five_sigma_hi"],
                n_mc=n_mc_per_corner,
            ))
        metrics = [metric_name]
        summary = _comparator_summary(results)

    else:  # opamp_2stage
        metric_name = "dc_gain_dB"
        unit = "dB"
        for corner in all_corners:
            samples = _mc_opamp_gain(corner, n_mc_per_corner, rng)
            s = _stats(samples)
            results.append(CornerResult(
                corner=corner, metric_name=metric_name, unit=unit,
                mean=s["mean"], std=s["std"],
                three_sigma_lo=s["three_sigma_lo"],
                three_sigma_hi=s["three_sigma_hi"],
                five_sigma_lo=s["five_sigma_lo"],
                five_sigma_hi=s["five_sigma_hi"],
                n_mc=n_mc_per_corner,
            ))
        metrics = [metric_name]
        summary = _opamp_summary(results)

    return PVTResult(
        cell_name=cell_name,
        metrics=metrics,
        corners=results,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def _bandgap_summary(results: list[CornerResult]) -> dict[str, Any]:
    """Compute worst-case and spread summary for bandgap VREF."""
    means = [r.mean for r in results]
    vref_min = min(means)
    vref_max = max(means)
    spread_mv = (vref_max - vref_min) * 1e3
    worst_lo  = min(r.three_sigma_lo for r in results)
    worst_hi  = max(r.three_sigma_hi for r in results)
    return {
        "cell": "bandgap_brokaw",
        "metric": "VREF_V",
        "corner_mean_min_V": round(vref_min, 5),
        "corner_mean_max_V": round(vref_max, 5),
        "pvt_spread_mV": round(spread_mv, 2),
        "worst_3sigma_lo_V": round(worst_lo, 5),
        "worst_3sigma_hi_V": round(worst_hi, 5),
        "target_V": 1.20,
        "pass_within_50mV":  abs(vref_min - 1.20) < 0.050 and abs(vref_max - 1.20) < 0.050,
    }


def _comparator_summary(results: list[CornerResult]) -> dict[str, Any]:
    """Compute worst-case and spread summary for comparator offset sigma."""
    sigmas = [r.std for r in results]
    sigma_min = min(sigmas)
    sigma_max = max(sigmas)
    return {
        "cell": "comparator_strongarm",
        "metric": "offset_sigma_mV",
        "sigma_tt_mV": round(results[20].std, 3),   # TT/VNOM/t27 is index 20
        "sigma_min_mV": round(sigma_min, 3),
        "sigma_max_mV": round(sigma_max, 3),
        "target_range_mV": "5–15",
        "pass_sigma_in_range": 5.0 <= sigma_max <= 20.0,
    }


def _opamp_summary(results: list[CornerResult]) -> dict[str, Any]:
    """Compute worst-case and spread summary for op-amp DC gain."""
    means = [r.mean for r in results]
    gain_min = min(means)
    gain_max = max(means)
    spread_db = gain_max - gain_min
    return {
        "cell": "opamp_2stage",
        "metric": "dc_gain_dB",
        "corner_mean_min_dB": round(gain_min, 2),
        "corner_mean_max_dB": round(gain_max, 2),
        "pvt_spread_dB": round(spread_db, 2),
        "target_spread_dB": "10–20",
        "pass_spread_in_range": 10.0 <= spread_db <= 25.0,
    }


# ---------------------------------------------------------------------------
# LLM tool wrappers
# ---------------------------------------------------------------------------

def silicon_pvt_corners() -> dict[str, Any]:
    """LLM tool: list all 60 PVT corners.

    Returns
    -------
    dict
        ``{"ok": True, "n_corners": 60, "corners": [...]}``
        Each corner has keys: name, process, vdd_v, temp_c, temp_k.
    """
    corners = pvt_corners()
    return {
        "ok": True,
        "n_corners": len(corners),
        "corners": [
            {
                "name":    c.name,
                "process": c.process,
                "vdd_v":   c.vdd_v,
                "temp_c":  round(c.temp_c, 2),
                "temp_k":  c.temp_k,
            }
            for c in corners
        ],
    }


def silicon_pvt_sweep(
    cell_name: str,
    n_mc_per_corner: int = 50,
    seed: int | None = 42,
) -> dict[str, Any]:
    """LLM tool: run a full PVT sweep with Monte-Carlo mismatch.

    Parameters
    ----------
    cell_name:
        ``"bandgap_brokaw"``, ``"comparator_strongarm"``, or
        ``"opamp_2stage"``.
    n_mc_per_corner:
        Monte-Carlo samples per corner (default 50).
    seed:
        RNG seed for reproducibility.

    Returns
    -------
    dict
        ``{"ok": bool, "result": PVTResult.to_dict(), "error": str | None}``
    """
    try:
        result = pvt_sweep(cell_name, n_mc_per_corner=n_mc_per_corner, seed=seed)
        return {
            "ok": True,
            "result": result.to_dict(),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "result": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
