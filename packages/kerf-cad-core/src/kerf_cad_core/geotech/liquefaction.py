"""
kerf_cad_core.geotech.liquefaction — Seismic liquefaction triggering analysis.

Pure-Python module; no OCC dependency.

Public functions
----------------
csr_seed_idriss(amax_g, total_stress_kPa, effective_stress_kPa, depth_m, M)
    Cyclic Stress Ratio per Seed & Idriss (1971) with Liao & Whitman (1986)
    stress-reduction factor rd and Idriss (1999) magnitude scaling factor MSF.
    Convention: MSF is applied to CSR (dividing by MSF), so CRR values are at
    M=7.5 equivalent.  FS_L = CRR_7.5 / CSR_corrected.

crr_from_spt(N60, effective_stress_kPa, *, FC, Pa)
    Cyclic Resistance Ratio from SPT (N1)60 per Youd et al. (2001).
    Applies overburden correction CN (Eq. 2) and fines-content correction
    Δ(N1)60 (Youd Eqs. 6a/b/c) to get (N1)60cs, then CRR_7.5 from Eq. (4).
    Returns CRR_7.5 (MSF already applied to CSR at the CSR step).

crr_from_cpt(qc_MPa, effective_stress_kPa, fs_MPa, *, Pa)
    Cyclic Resistance Ratio from CPT per Robertson & Wride (1998).
    Normalises cone tip resistance to qc1N, classifies soil using Ic,
    applies clean-sand correction Kc, returns CRR_7.5.

liquefaction_safety_factor(CSR, CRR, *, design_margin)
    Factor of safety FS_L = CRR / CSR.  Flags liquefaction when FS_L < 1.0
    (or < design_margin, default 1.25).

post_triggering_settlement(CSR, N1_60, layer_thickness_m)
    Post-triggering volumetric strain and settlement estimate for a single
    liquefiable layer using the Tokimatsu & Seed (1987) chart approximation.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Magnitude Scaling Factor (MSF) Convention
-----------------------------------------
CSR is divided by MSF to normalise to M=7.5 (i.e. CSR_M7.5 = CSR / MSF).
CRR_7.5 values from SPT and CPT are already at the M=7.5 reference magnitude.
FS_L = CRR_7.5 / CSR_M7.5.
This follows the convention in Youd et al. (2001), Eq. (3)/(4).

References
----------
Seed, H.B. & Idriss, I.M. (1971). "Simplified procedure for evaluating soil
    liquefaction potential." ASCE J. Soil Mech. Found. Div., 97(9):1249-1273.
Liao, S.C. & Whitman, R.V. (1986). "Overburden correction factors for SPT in
    sand." ASCE J. Geotech. Eng., 112(3):373-377.
Youd, T.L. et al. (2001). "Liquefaction resistance of soils: Summary report
    from the 1996 NCEER and 1998 NCEER/NSF workshops." ASCE J. Geotech.
    Geoenviron. Eng., 127(10):817-833.
Robertson, P.K. & Wride, C.E. (1998). "Evaluating cyclic liquefaction
    potential using the cone penetration test." Can. Geotech. J., 35:442-459.
Tokimatsu, K. & Seed, H.B. (1987). "Evaluation of settlements in sands due to
    earthquake shaking." ASCE J. Geotech. Eng., 113(8):861-878.
Idriss, I.M. (1999). "An update to the Seed-Idriss simplified procedure for
    evaluating liquefaction potential." Proc. TRB Workshop on New Approaches
    to Liquefaction, FHWA-RD-99-165.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _err(reason: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason}


def _ok(data: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    return {"ok": True, **data, "warnings": warnings}


def _rd(depth_m: float) -> float:
    """Stress reduction coefficient rd (Liao & Whitman 1986).

    rd = 1 − 0.00765·z           for z < 9.15 m
    rd = 1.174 − 0.0267·z        for 9.15 m ≤ z < 23 m
    rd = 0.744 − 0.008·z         for 23 m ≤ z ≤ 30 m  (approximate extension)
    Below 30 m the factor is extrapolated linearly (use with caution).
    """
    z = depth_m
    if z < 9.15:
        return 1.0 - 0.00765 * z
    elif z < 23.0:
        return 1.174 - 0.0267 * z
    else:
        # Approximate extension per Robertson & Wride (1998)
        return max(0.5, 0.744 - 0.008 * z)


def _msf(M: float) -> float:
    """Magnitude Scaling Factor per Idriss (1999).

    MSF = 10^2.24 / M^2.56
    Valid range: 5.5 ≤ M ≤ 8.5 (warn outside).
    For M=7.5: MSF = 1.0 exactly (reference earthquake).
    """
    return (10.0 ** 2.24) / (M ** 2.56)


# ---------------------------------------------------------------------------
# 1. Cyclic Stress Ratio (CSR)
# ---------------------------------------------------------------------------

def csr_seed_idriss(
    amax_g: float,
    total_stress_kPa: float,
    effective_stress_kPa: float,
    depth_m: float,
    M: float,
) -> dict[str, Any]:
    """Compute the Cyclic Stress Ratio (CSR) normalised to M=7.5.

    CSR = 0.65 · (amax/g) · (σ/σ') · rd · (1/MSF)

    The MSF division normalises CSR to the M=7.5 reference magnitude so that
    FS_L = CRR_7.5 / CSR_M7.5 (Youd et al. 2001 convention).

    Parameters
    ----------
    amax_g : float
        Peak ground acceleration as a fraction of g (e.g. 0.20 for 0.2g).
    total_stress_kPa : float
        Total vertical stress at the depth of interest (kPa). > 0.
    effective_stress_kPa : float
        Effective vertical stress at the depth of interest (kPa). > 0.
        Must be ≤ total_stress_kPa.
    depth_m : float
        Depth to the liquefiable layer (m). ≥ 0.
    M : float
        Moment magnitude of the design earthquake. Typically 5.5–8.5.

    Returns
    -------
    dict with keys: CSR_raw, rd, MSF, CSR_M7.5, depth_m, warnings.
    """
    warnings: list[str] = []

    # --- validation ---
    if amax_g <= 0.0:
        return _err("amax_g must be > 0")
    if amax_g >= 1.0:
        warnings.append(f"amax_g={amax_g:.3f} ≥ 1.0g is unusually high; verify input")
    if total_stress_kPa <= 0.0:
        return _err("total_stress_kPa must be > 0")
    if effective_stress_kPa <= 0.0:
        return _err("effective_stress_kPa must be > 0")
    if effective_stress_kPa > total_stress_kPa:
        return _err("effective_stress_kPa must be ≤ total_stress_kPa")
    if depth_m < 0.0:
        return _err("depth_m must be ≥ 0")
    if M < 5.0 or M > 9.0:
        return _err("Moment magnitude M must be in [5.0, 9.0]")
    if M < 5.5 or M > 8.5:
        warnings.append(
            f"M={M:.1f} is outside the recommended 5.5–8.5 range for this method"
        )
    if depth_m > 23.0:
        warnings.append(
            f"depth={depth_m:.1f} m > 23 m; rd is an approximation below 23 m"
        )

    rd_val = _rd(depth_m)
    msf_val = _msf(M)

    # Raw CSR (no MSF correction)
    csr_raw = 0.65 * amax_g * (total_stress_kPa / effective_stress_kPa) * rd_val

    # Normalised to M=7.5 by dividing by MSF
    csr_m75 = csr_raw / msf_val

    return _ok(
        {
            "CSR_raw": round(csr_raw, 6),
            "rd": round(rd_val, 6),
            "MSF": round(msf_val, 6),
            "CSR_M7.5": round(csr_m75, 6),
            "depth_m": depth_m,
            "amax_g": amax_g,
            "M": M,
        },
        warnings,
    )


# ---------------------------------------------------------------------------
# 2. CRR from SPT-N (Youd et al. 2001)
# ---------------------------------------------------------------------------

def crr_from_spt(
    N60: float,
    effective_stress_kPa: float,
    *,
    FC: float = 0.0,
    Pa: float = 101.325,
) -> dict[str, Any]:
    """Cyclic Resistance Ratio from SPT N-value (Youd et al. 2001).

    Steps:
      1. Overburden correction: CN = (Pa/σ')^0.5 ≤ 1.7 → (N1)60 = CN × N60
      2. Fines-content correction: Δ(N1)60 per Youd Eqs. (6a/b/c) → (N1)60cs
      3. CRR_7.5 = 1/(34−(N1)60cs) + (N1)60cs/135
                   + 50/(10·(N1)60cs+45)² − 1/200
         Valid for (N1)60cs ≤ 30; beyond that the soil is non-liquefiable.

    Parameters
    ----------
    N60 : float
        Field SPT blow count corrected for energy (60% efficiency). ≥ 0.
    effective_stress_kPa : float
        Effective overburden stress at the test depth (kPa). > 0.
    FC : float, optional
        Fines content (%) passing #200 sieve. Default 0 (clean sand).
    Pa : float, optional
        Atmospheric pressure (kPa). Default 101.325 kPa.

    Returns
    -------
    dict with keys: N60, N1_60, delta_N1_60cs, N1_60cs, CN, CRR_7.5,
                    liquefiable, warnings.
    """
    warnings: list[str] = []

    if N60 < 0.0:
        return _err("N60 must be ≥ 0")
    if effective_stress_kPa <= 0.0:
        return _err("effective_stress_kPa must be > 0")
    if FC < 0.0 or FC > 100.0:
        return _err("FC (fines content) must be in [0, 100] %")
    if Pa <= 0.0:
        return _err("Pa must be > 0")

    # Step 1 — overburden correction
    CN = min((Pa / effective_stress_kPa) ** 0.5, 1.7)
    N1_60 = CN * N60

    # Step 2 — fines-content correction (Youd et al. 2001 Eqs. 6a/b/c)
    if FC < 5.0:
        delta_N = 0.0
    elif FC <= 35.0:
        # Youd Eq. 6b: interpolation
        delta_N = math.exp(1.76 - (190.0 / FC**2))
    else:
        # Youd Eq. 6c: FC > 35%
        delta_N = 5.0

    N1_60cs = N1_60 + delta_N

    if N1_60cs > 30.0:
        # Soil is too dense to liquefy under this framework
        warnings.append(
            f"(N1)60cs = {N1_60cs:.2f} > 30; soil is non-liquefiable "
            "by Youd et al. (2001) — CRR is indeterminate (set to ∞)."
        )
        return _ok(
            {
                "N60": N60,
                "N1_60": round(N1_60, 4),
                "delta_N1_60cs": round(delta_N, 4),
                "N1_60cs": round(N1_60cs, 4),
                "CN": round(CN, 4),
                "CRR_7.5": None,
                "liquefiable": False,
            },
            warnings,
        )

    # Step 3 — CRR_7.5 (Youd et al. 2001 Eq. 4)
    x = N1_60cs
    crr = (
        1.0 / (34.0 - x)
        + x / 135.0
        + 50.0 / (10.0 * x + 45.0) ** 2
        - 1.0 / 200.0
    )

    if FC >= 35.0:
        warnings.append(
            f"FC={FC:.0f}% ≥ 35%; high fines may indicate plastic fines — "
            "consider undrained shear strength approach."
        )
    if N1_60cs < 3.0:
        warnings.append(
            f"(N1)60cs={N1_60cs:.2f} < 3; very loose soil — results are "
            "highly sensitive to test variability."
        )

    return _ok(
        {
            "N60": N60,
            "N1_60": round(N1_60, 4),
            "delta_N1_60cs": round(delta_N, 4),
            "N1_60cs": round(N1_60cs, 4),
            "CN": round(CN, 4),
            "CRR_7.5": round(crr, 6),
            "liquefiable": True,  # means CRR is finite; actual triggering needs FS
        },
        warnings,
    )


# ---------------------------------------------------------------------------
# 3. CRR from CPT-qc (Robertson & Wride 1998)
# ---------------------------------------------------------------------------

def crr_from_cpt(
    qc_MPa: float,
    effective_stress_kPa: float,
    fs_MPa: float,
    *,
    Pa: float = 0.101325,
) -> dict[str, Any]:
    """Cyclic Resistance Ratio from CPT per Robertson & Wride (1998).

    Normalised cone tip resistance:
        qc1N = (qc / Pa) · (Pa / σ'v)^n     (n = 0.5 for clean sand)

    Soil behaviour type index Ic:
        Qt = (qc − σv) / σ'v   [dimensionless, using vertical total stress]
        Fr = (fs / (qc − σv)) × 100   [%]
        Ic = sqrt[(3.47 − log Qt)² + (1.22 + log Fr)²]

    Clean-sand base-case (Ic ≤ 2.6 → likely sand):
        qc1N_cs = Kc · qc1N
        CRR_7.5 from Robertson & Wride Table 1 polynomial.

    For Ic > 2.6 (likely silt/clay), CRR is not defined by this method.

    Parameters
    ----------
    qc_MPa : float
        Measured cone tip resistance (MPa). > 0.
    effective_stress_kPa : float
        Effective vertical stress at the test depth (kPa). > 0.
    fs_MPa : float
        Sleeve friction (MPa). ≥ 0.
    Pa : float, optional
        Atmospheric pressure in MPa (default 0.101325 MPa = 101.325 kPa).

    Returns
    -------
    dict with keys: qc_MPa, qc1N, Ic, Fr_pct, Kc, qc1N_cs,
                    CRR_7.5, liquefiable, sand_like, warnings.
    """
    warnings: list[str] = []

    if qc_MPa <= 0.0:
        return _err("qc_MPa must be > 0")
    if effective_stress_kPa <= 0.0:
        return _err("effective_stress_kPa must be > 0")
    if fs_MPa < 0.0:
        return _err("fs_MPa must be ≥ 0")
    if Pa <= 0.0:
        return _err("Pa must be > 0")

    # Convert effective stress to MPa for consistent units
    sigma_v_eff_MPa = effective_stress_kPa / 1000.0

    # Normalised cone tip resistance (n=0.5 for sand; Robertson & Wride use iterative n)
    # Use simplified n=0.5 consistent with clean-sand assumption for first pass
    qc1N = (qc_MPa / Pa) * (Pa / sigma_v_eff_MPa) ** 0.5

    # Estimate total stress ~ effective + 50 kPa (approximate; user should provide if known)
    # Here we use a conservative approximation: σv_total ≈ σ'v + u
    # Without pore pressure data, assume hydrostatic: use σv_eff as proxy for net stress
    # Robertson & Wride: Qt = (qc - σv_total)/σ'v; approximate σv_total ≈ 1.5·σ'v
    sigma_v_total_MPa = sigma_v_eff_MPa * 1.5  # approximate assumption
    net_tip_MPa = max(qc_MPa - sigma_v_total_MPa, 1e-6)
    Qt = net_tip_MPa / sigma_v_eff_MPa

    if fs_MPa > 0.0 and qc_MPa > sigma_v_total_MPa:
        Fr_pct = (fs_MPa / net_tip_MPa) * 100.0
    else:
        Fr_pct = 0.0
        warnings.append("fs_MPa = 0; Fr defaulted to 0%; Ic may be underestimated")

    # Soil behaviour type index Ic
    log_Qt = math.log10(max(Qt, 1e-6))
    log_Fr = math.log10(max(Fr_pct, 0.001))
    Ic = math.sqrt((3.47 - log_Qt) ** 2 + (1.22 + log_Fr) ** 2)

    sand_like = Ic <= 2.6

    if not sand_like:
        warnings.append(
            f"Ic = {Ic:.3f} > 2.6 suggests silt/clay — Robertson & Wride (1998) "
            "CRR formula is not applicable; use undrained shear strength approach."
        )
        return _ok(
            {
                "qc_MPa": qc_MPa,
                "qc1N": round(qc1N, 4),
                "Ic": round(Ic, 4),
                "Fr_pct": round(Fr_pct, 4),
                "Kc": None,
                "qc1N_cs": None,
                "CRR_7.5": None,
                "liquefiable": None,
                "sand_like": False,
            },
            warnings,
        )

    # Clean-sand correction factor Kc (Robertson & Wride 1998 Eq. 15)
    if Ic <= 1.64:
        Kc = 1.0
    else:
        Ic2 = Ic ** 2
        Ic3 = Ic ** 3
        Ic4 = Ic ** 4
        Kc = -0.403 * Ic4 + 5.581 * Ic3 - 21.63 * Ic2 + 33.75 * Ic - 17.88

    Kc = max(1.0, Kc)  # Kc ≥ 1 for clean sand correction

    qc1N_cs = Kc * qc1N

    # CRR_7.5 (Robertson & Wride 1998 Eq. 14 / Table 1)
    if qc1N_cs >= 160.0:
        warnings.append(
            f"qc1N_cs = {qc1N_cs:.1f} ≥ 160 → dense sand, non-liquefiable by R&W method"
        )
        return _ok(
            {
                "qc_MPa": qc_MPa,
                "qc1N": round(qc1N, 4),
                "Ic": round(Ic, 4),
                "Fr_pct": round(Fr_pct, 4),
                "Kc": round(Kc, 4),
                "qc1N_cs": round(qc1N_cs, 4),
                "CRR_7.5": None,
                "liquefiable": False,
                "sand_like": True,
            },
            warnings,
        )

    # Robertson & Wride (1998) Eq. 14 (clean-sand polynomial)
    x = qc1N_cs / 1000.0  # normalise to same scale as their equation
    # Using the form: CRR = 0.833·(qc1N_cs/1000) + 0.05  for qc1N_cs < 50
    #                        0.5/(1 - 1.13·(qc1N_cs/1000)^3)  for 50 ≤ qc1N_cs < 160
    # (Robertson & Wride 1998, Eq. 14a/14b)
    if qc1N_cs < 50.0:
        crr = 0.833 * x + 0.05
    else:
        crr = 0.5 / (1.0 - 1.13 * x ** 3)

    crr = max(crr, 0.0)

    return _ok(
        {
            "qc_MPa": qc_MPa,
            "qc1N": round(qc1N, 4),
            "Ic": round(Ic, 4),
            "Fr_pct": round(Fr_pct, 4),
            "Kc": round(Kc, 4),
            "qc1N_cs": round(qc1N_cs, 4),
            "CRR_7.5": round(crr, 6),
            "liquefiable": True,
            "sand_like": True,
        },
        warnings,
    )


# ---------------------------------------------------------------------------
# 4. Factor of Safety against Liquefaction
# ---------------------------------------------------------------------------

def liquefaction_safety_factor(
    CSR: float,
    CRR: float,
    *,
    design_margin: float = 1.25,
) -> dict[str, Any]:
    """Factor of safety against liquefaction triggering.

    FS_L = CRR_7.5 / CSR_M7.5

    Liquefaction is triggered when FS_L < 1.0.
    Design often requires FS_L ≥ 1.25 (NCEER workshop recommendation).

    Parameters
    ----------
    CSR : float
        Cyclic Stress Ratio (normalised to M=7.5 via CSR_M7.5). > 0.
    CRR : float
        Cyclic Resistance Ratio (CRR_7.5 from SPT or CPT). > 0.
    design_margin : float, optional
        Design factor of safety threshold (default 1.25 per NCEER).

    Returns
    -------
    dict with keys: FS_L, liquefied, adequate_for_design, design_margin,
                    CSR, CRR, warnings.
    """
    warnings: list[str] = []

    if CSR <= 0.0:
        return _err("CSR must be > 0")
    if CRR <= 0.0:
        return _err("CRR must be > 0")
    if design_margin < 1.0:
        warnings.append(
            f"design_margin={design_margin:.2f} < 1.0 is below minimum safety threshold"
        )

    FS_L = CRR / CSR

    liquefied = FS_L < 1.0
    adequate = FS_L >= design_margin

    if liquefied:
        warnings.append(
            f"FS_L = {FS_L:.3f} < 1.0 — liquefaction is predicted to be TRIGGERED"
        )
    elif not adequate:
        warnings.append(
            f"FS_L = {FS_L:.3f} < design_margin = {design_margin:.2f} — "
            "marginal; consider ground improvement"
        )

    return _ok(
        {
            "FS_L": round(FS_L, 4),
            "liquefied": liquefied,
            "adequate_for_design": adequate,
            "design_margin": design_margin,
            "CSR": CSR,
            "CRR": CRR,
        },
        warnings,
    )


# ---------------------------------------------------------------------------
# 5. Post-triggering settlement (Tokimatsu & Seed 1987)
# ---------------------------------------------------------------------------

# Volumetric strain table (Tokimatsu & Seed 1987, Fig. 5 approximation).
# Keys: (N1_60 bin), Values: list of (CSR_threshold, epsilon_v_pct) pairs
# CSR thresholds are upper bounds; epsilon_v interpolated linearly.
# This is a digitised approximation of the published chart.
_TOKIMATSU_TABLE: list[tuple[float, float, float]] = [
    # (N1_60_max, CSR_max, epsilon_v_pct)
    # Row format: for N1_60 ≤ N1_60_max, at CSR up to CSR_max, use epsilon_v_pct
    # Based on Tokimatsu & Seed (1987) Fig. 5 / Table 1 approximation
    (4.0,  0.10, 3.0),
    (4.0,  0.20, 5.5),
    (4.0,  0.30, 7.5),
    (8.0,  0.10, 1.5),
    (8.0,  0.20, 3.5),
    (8.0,  0.30, 5.5),
    (14.0, 0.10, 0.5),
    (14.0, 0.20, 2.0),
    (14.0, 0.30, 3.5),
    (20.0, 0.10, 0.1),
    (20.0, 0.20, 0.7),
    (20.0, 0.30, 1.5),
    (30.0, 0.10, 0.0),
    (30.0, 0.20, 0.1),
    (30.0, 0.30, 0.3),
]


def _tokimatsu_epsilon_v(CSR: float, N1_60: float) -> float:
    """Volumetric strain (%) from Tokimatsu & Seed (1987) chart approximation.

    Uses bilinear interpolation between the digitised chart entries.
    """
    # Clamp CSR and N1_60 to table bounds
    CSR_clamped = min(max(CSR, 0.0), 0.30)
    N1_clamped = min(max(N1_60, 0.0), 30.0)

    # Find bounding N1_60 rows
    n_rows = [4.0, 8.0, 14.0, 20.0, 30.0]
    csr_cols = [0.10, 0.20, 0.30]
    ev_table = [
        [3.0, 5.5, 7.5],   # N1_60 ≤ 4
        [1.5, 3.5, 5.5],   # N1_60 ≤ 8
        [0.5, 2.0, 3.5],   # N1_60 ≤ 14
        [0.1, 0.7, 1.5],   # N1_60 ≤ 20
        [0.0, 0.1, 0.3],   # N1_60 ≤ 30
    ]

    # Find N1 row interpolation
    if N1_clamped <= n_rows[0]:
        i_low, i_high, t_n = 0, 0, 0.0
    elif N1_clamped >= n_rows[-1]:
        i_low, i_high, t_n = len(n_rows) - 1, len(n_rows) - 1, 0.0
    else:
        for i in range(len(n_rows) - 1):
            if N1_clamped <= n_rows[i + 1]:
                i_low, i_high = i, i + 1
                t_n = (N1_clamped - n_rows[i]) / (n_rows[i + 1] - n_rows[i])
                break

    # Find CSR column interpolation
    CSR_clamped = min(max(CSR_clamped, csr_cols[0]), csr_cols[-1])
    if CSR_clamped <= csr_cols[0]:
        j_low, j_high, t_c = 0, 0, 0.0
    elif CSR_clamped >= csr_cols[-1]:
        j_low, j_high, t_c = len(csr_cols) - 1, len(csr_cols) - 1, 0.0
    else:
        for j in range(len(csr_cols) - 1):
            if CSR_clamped <= csr_cols[j + 1]:
                j_low, j_high = j, j + 1
                t_c = (CSR_clamped - csr_cols[j]) / (csr_cols[j + 1] - csr_cols[j])
                break

    # Bilinear interpolation
    ev_ll = ev_table[i_low][j_low]
    ev_lh = ev_table[i_low][j_high]
    ev_hl = ev_table[i_high][j_low]
    ev_hh = ev_table[i_high][j_high]

    ev_low = ev_ll + t_c * (ev_lh - ev_ll)
    ev_high = ev_hl + t_c * (ev_hh - ev_hl)
    return ev_low + t_n * (ev_high - ev_low)


def post_triggering_settlement(
    CSR: float,
    N1_60: float,
    layer_thickness_m: float,
) -> dict[str, Any]:
    """Estimate post-triggering volumetric settlement (Tokimatsu & Seed 1987).

    For a liquefied layer, volumetric strain ε_v is estimated from the
    (CSR, (N1)60) pair using a digitised approximation of the Tokimatsu &
    Seed (1987) chart (Fig. 5).  Settlement = ε_v × H.

    Parameters
    ----------
    CSR : float
        Cyclic Stress Ratio (CSR_M7.5, the M=7.5-normalised value). > 0.
    N1_60 : float
        Overburden-corrected SPT blow count. ≥ 0.
    layer_thickness_m : float
        Thickness of the liquefiable layer (m). > 0.

    Returns
    -------
    dict with keys: epsilon_v_pct, settlement_m, settlement_mm, warnings.
    """
    warnings: list[str] = []

    if CSR <= 0.0:
        return _err("CSR must be > 0")
    if N1_60 < 0.0:
        return _err("N1_60 must be ≥ 0")
    if layer_thickness_m <= 0.0:
        return _err("layer_thickness_m must be > 0")

    if N1_60 > 30.0:
        warnings.append(
            f"N1_60={N1_60:.1f} > 30 — soil likely non-liquefiable; "
            "settlement estimate set to 0."
        )
        return _ok(
            {
                "epsilon_v_pct": 0.0,
                "settlement_m": 0.0,
                "settlement_mm": 0.0,
            },
            warnings,
        )

    if CSR > 0.30:
        warnings.append(
            f"CSR={CSR:.3f} > 0.30 — extrapolating beyond Tokimatsu & Seed chart range"
        )

    epsilon_v = _tokimatsu_epsilon_v(CSR, N1_60)
    settlement_m = (epsilon_v / 100.0) * layer_thickness_m
    settlement_mm = settlement_m * 1000.0

    if settlement_mm > 300.0:
        warnings.append(
            f"Estimated settlement = {settlement_mm:.0f} mm > 300 mm — "
            "severe; ground improvement strongly recommended"
        )

    return _ok(
        {
            "epsilon_v_pct": round(epsilon_v, 4),
            "settlement_m": round(settlement_m, 6),
            "settlement_mm": round(settlement_mm, 3),
        },
        warnings,
    )
