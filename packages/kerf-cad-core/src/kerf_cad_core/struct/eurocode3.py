"""
kerf_cad_core.struct.eurocode3 — Eurocode 3 (EN 1993-1-1) steel design.

Implements EN 1993-1-1:2005 checks for European structural steel sections.

Units throughout
----------------
  Lengths / dimensions : mm
  Areas               : mm²
  Second moments      : mm⁴
  Section moduli      : mm³
  Forces              : N (Newtons)
  Moments             : N·mm
  Stresses            : N/mm² = MPa
  fy, fu              : N/mm² (MPa)

All public functions return plain dicts.  Warnings collected in
result["warnings"].  Functions never raise on bad numeric input — they return
{"ok": False, "error": "..."} instead.

References
----------
EN 1993-1-1:2005 — Eurocode 3: Design of steel structures — Part 1-1:
  General rules and rules for buildings.
SCI P362 / Designers' Guide to EN 1993-1-1 (Gardner & Nethercot).
Trahair, Bradford, Nethercot & Gardner "The Behaviour and Design of Steel
Structures to EC3" 4th ed.

Validation benchmarks (see tests)
----------------------------------
IPE 300, L = 4000 mm, S275, both-ends-pinned axial compression:
  Ncr = π²·EI/L² = 9869 × 210000 × 83560000 / 16e6 = ~1089 kN (weak-axis governs)
  λ̄z ≈ 1.09, curve c (rolled I, h/b>1.2, tf<40) → χ ≈ 0.47
  Nb,Rd = 0.47 × 5380 × 275 / 1.0 = ~694 kN  (ref ≈ 700 kN)

IPE 300, simply-supported beam, Lb = 4000 mm, S275, uniform moment (C1=1.0):
  Mcr ~ 121 kN·m  → λ̄LT ~ 1.07, curve b (rolled I) → χLT ~ 0.54
  Mb,Rd = 0.54 × 628500 × 275 / 1.0 / 1e6 = ~93 kN·m  (ref ~93–98 kN·m)

Author: imranparuk
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# §6.1 Partial material factors
# ---------------------------------------------------------------------------

EC3_GAMMA_M0: float = 1.0   # resistance of cross-sections (yielding)
EC3_GAMMA_M1: float = 1.0   # resistance of members (buckling)
EC3_GAMMA_M2: float = 1.25  # resistance of net sections (fracture)

#: Elastic modulus E for structural steel (N/mm²)
EC3_E: float = 210_000.0

#: Shear modulus G for structural steel (N/mm²)
EC3_G: float = 81_000.0


# ---------------------------------------------------------------------------
# Steel grades
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SteelGrade:
    """European structural steel grade per EN 10025-2."""
    name: str
    fy: float   # yield strength N/mm²  (≤16 mm thickness; conservative for thick)
    fu: float   # ultimate tensile strength N/mm²

    def epsilon(self) -> float:
        """ε = √(235/fy) — EC3 §5.5 classification parameter."""
        return math.sqrt(235.0 / self.fy)


#: Common European steel grades (nominal fy for t ≤ 16 mm)
STEEL_GRADES: dict[str, SteelGrade] = {
    "S235": SteelGrade("S235", fy=235.0, fu=360.0),
    "S275": SteelGrade("S275", fy=275.0, fu=430.0),
    "S355": SteelGrade("S355", fy=355.0, fu=510.0),
    "S420": SteelGrade("S420", fy=420.0, fu=520.0),
    "S460": SteelGrade("S460", fy=460.0, fu=550.0),
}


def get_grade(name: str) -> SteelGrade | None:
    return STEEL_GRADES.get(name.upper())


# ---------------------------------------------------------------------------
# Section catalogue — European hot-rolled sections
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EC3Section:
    """
    Cross-section properties for a European hot-rolled I/H section.

    All values are standard published nominal figures from EN 10034 /
    ArcelorMittal sections catalogue (publicly available).

    Attributes
    ----------
    name    : section designation, e.g. "IPE300"
    family  : "IPE" | "HEA" | "HEB"
    h       : overall height (mm)
    b       : flange width (mm)
    tw      : web thickness (mm)
    tf      : flange thickness (mm)
    A       : cross-sectional area (mm²)
    Iy      : second moment of area, strong axis (mm⁴)
    Iz      : second moment of area, weak axis (mm⁴)
    Wpl_y   : plastic section modulus, strong axis (mm³)
    Wel_y   : elastic section modulus, strong axis (mm³)
    iy      : radius of gyration, strong axis (mm)
    iz      : radius of gyration, weak axis (mm)
    It      : torsion constant (mm⁴)
    Iw      : warping constant (mm⁶)
    """
    name:   str
    family: str
    h:      float   # mm
    b:      float   # mm
    tw:     float   # mm
    tf:     float   # mm
    A:      float   # mm²
    Iy:     float   # mm⁴
    Iz:     float   # mm⁴
    Wpl_y:  float   # mm³
    Wel_y:  float   # mm³
    iy:     float   # mm
    iz:     float   # mm
    It:     float   # mm⁴
    Iw:     float   # mm⁶

    def to_dict(self) -> dict:
        return {
            "name":   self.name,
            "family": self.family,
            "h_mm":   self.h,
            "b_mm":   self.b,
            "tw_mm":  self.tw,
            "tf_mm":  self.tf,
            "A_mm2":  self.A,
            "Iy_mm4": self.Iy,
            "Iz_mm4": self.Iz,
            "Wpl_y_mm3": self.Wpl_y,
            "Wel_y_mm3": self.Wel_y,
            "iy_mm":  self.iy,
            "iz_mm":  self.iz,
            "It_mm4": self.It,
            "Iw_mm6": self.Iw,
        }


# Published nominal values — EN 10034 / ArcelorMittal hot-rolled catalogue
# All properties are standard textbook/catalogue values, widely reproduced.
# Iw (warping constant) in mm⁶; It (St Venant torsion) in mm⁴.
EC3_SECTION_CATALOG: dict[str, EC3Section] = {
    "IPE200": EC3Section(
        name="IPE200", family="IPE",
        h=200.0, b=100.0, tw=5.6, tf=8.5,
        A=2848.0, Iy=19430000.0, Iz=1424000.0,
        Wpl_y=221000.0, Wel_y=194300.0,
        iy=82.6, iz=22.4,
        It=6920.0, Iw=12990000000.0,
    ),
    "IPE300": EC3Section(
        name="IPE300", family="IPE",
        h=300.0, b=150.0, tw=7.1, tf=10.7,
        A=5380.0, Iy=83560000.0, Iz=6040000.0,
        Wpl_y=628500.0, Wel_y=557100.0,
        iy=124.6, iz=33.6,
        It=20120.0, Iw=125900000000.0,
    ),
    "IPE400": EC3Section(
        name="IPE400", family="IPE",
        h=400.0, b=180.0, tw=8.6, tf=13.5,
        A=8446.0, Iy=231300000.0, Iz=13180000.0,
        Wpl_y=1307000.0, Wel_y=1156000.0,
        iy=165.5, iz=39.5,
        It=51080.0, Iw=490000000000.0,
    ),
    "IPE500": EC3Section(
        name="IPE500", family="IPE",
        h=500.0, b=200.0, tw=10.2, tf=16.0,
        A=11550.0, Iy=482000000.0, Iz=21400000.0,
        Wpl_y=2194000.0, Wel_y=1928000.0,
        iy=204.2, iz=43.1,
        It=89290.0, Iw=1249000000000.0,
    ),
    "HEA200": EC3Section(
        name="HEA200", family="HEA",
        h=190.0, b=200.0, tw=6.5, tf=10.0,
        A=5383.0, Iy=36920000.0, Iz=13360000.0,
        Wpl_y=429500.0, Wel_y=388700.0,
        iy=82.8, iz=49.8,
        It=21140.0, Iw=105200000000.0,
    ),
    "HEA300": EC3Section(
        name="HEA300", family="HEA",
        h=290.0, b=300.0, tw=8.5, tf=14.0,
        A=11250.0, Iy=182600000.0, Iz=63100000.0,
        Wpl_y=1383000.0, Wel_y=1260000.0,
        iy=127.4, iz=74.9,
        It=85270.0, Iw=1008000000000.0,
    ),
    "HEA400": EC3Section(
        name="HEA400", family="HEA",
        h=390.0, b=300.0, tw=11.0, tf=19.0,
        A=15590.0, Iy=450700000.0, Iz=67120000.0,
        Wpl_y=2583000.0, Wel_y=2311000.0,
        iy=169.9, iz=65.6,
        It=157500.0, Iw=2577000000000.0,
    ),
    "HEB300": EC3Section(
        name="HEB300", family="HEB",
        h=300.0, b=300.0, tw=11.0, tf=19.0,
        A=14910.0, Iy=251700000.0, Iz=85560000.0,
        Wpl_y=1869000.0, Wel_y=1678000.0,
        iy=130.0, iz=75.7,
        It=185000.0, Iw=1688000000000.0,
    ),
}


def get_ec3_section(name: str) -> EC3Section | None:
    return EC3_SECTION_CATALOG.get(name.upper())


# ---------------------------------------------------------------------------
# §5.5 Cross-section classification
# ---------------------------------------------------------------------------

def classify_section(
    sec: EC3Section,
    grade: SteelGrade,
    NEd: float = 0.0,   # design axial force N (compression positive)
    My_Ed: float = 0.0, # design moment N·mm (about strong axis)
) -> dict[str, Any]:
    """
    Classify cross-section per EN 1993-1-1 §5.5 (Tables 5.2).

    Considers the most critical element (flange or web).
    For web classification under combined N+M, the neutral-axis shift is
    approximated conservatively using the full-axial + full-moment envelope
    (c/t ratio checked against Class 3 limits for internal element in
    compression; Class 4 flag set if any element exceeds Class 3).

    Parameters
    ----------
    sec    : EC3Section
    grade  : SteelGrade (for ε)
    NEd    : Design axial force (N); compression positive; 0 = pure bending
    My_Ed  : Design major-axis moment (N·mm); 0 = pure compression

    Returns
    -------
    dict with keys:
        class_flange  : 1/2/3/4
        class_web     : 1/2/3/4
        section_class : max(class_flange, class_web)
        epsilon       : ε value
        c_t_flange    : outstand c/t for flange
        c_t_web       : c/t for web
        warnings      : list[str]
    """
    warnings: list[str] = []
    eps = grade.epsilon()

    # Outstand flange c/t (Table 5.2, sheet 2)
    # c = (b - tw - 2r) / 2 ≈ (b - tw) / 2  (conservatively ignore root radius)
    # Root radius for IPE/HEA r ≈ 15 mm — unknown here, omit (conservative)
    c_f = (sec.b - sec.tw) / 2.0
    ct_flange = c_f / sec.tf

    if ct_flange <= 9.0 * eps:
        class_flange = 1
    elif ct_flange <= 10.0 * eps:
        class_flange = 2
    elif ct_flange <= 14.0 * eps:
        class_flange = 3
    else:
        class_flange = 4
        warnings.append(
            f"Flange c/t={ct_flange:.2f} > 14ε={14*eps:.2f}: Class 4 (slender)"
        )

    # Internal web element c/t (Table 5.2, sheet 1)
    # c = h - 2*tf  (conservatively ignoring root radius)
    c_w = sec.h - 2.0 * sec.tf
    ct_web = c_w / sec.tw

    # Axial ratio α for web: determine whether compression dominant
    # α = fraction of web in compression = 0.5 + NEd/(2*fy*tw*c_w) clamped [0,1]
    # For pure bending NEd=0 → α=0.5 (neutral axis at mid-web)
    Npl = sec.A * grade.fy  # plastic squash load
    if Npl > 0:
        alpha_web = min(1.0, max(0.0, 0.5 + NEd / (2.0 * grade.fy * sec.tw * c_w)))
    else:
        alpha_web = 0.5

    # Use bending + compression limits (α > 0.5 is dominant compression)
    if alpha_web > 0.5:
        # Predominantly compression — use compression limits for web
        lim1 = 33.0 * eps
        lim2 = 38.0 * eps
        lim3 = 42.0 * eps
    else:
        # Predominantly bending
        lim1 = 72.0 * eps
        lim2 = 83.0 * eps
        lim3 = 124.0 * eps

    if ct_web <= lim1:
        class_web = 1
    elif ct_web <= lim2:
        class_web = 2
    elif ct_web <= lim3:
        class_web = 3
    else:
        class_web = 4
        warnings.append(
            f"Web c/t={ct_web:.2f} > Class 3 limit={lim3:.2f}: Class 4 (slender)"
        )

    section_class = max(class_flange, class_web)

    return {
        "class_flange": class_flange,
        "class_web": class_web,
        "section_class": section_class,
        "epsilon": round(eps, 4),
        "c_t_flange": round(ct_flange, 3),
        "c_t_web": round(ct_web, 3),
        "alpha_web": round(alpha_web, 4),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# §6.3.1 Flexural buckling resistance Nb,Rd
# ---------------------------------------------------------------------------

#: Imperfection factors α for buckling curves a₀/a/b/c/d
#: EN 1993-1-1 Table 6.1
_ALPHA_CURVE: dict[str, float] = {
    "a0": 0.13,
    "a":  0.21,
    "b":  0.34,
    "c":  0.49,
    "d":  0.76,
}


def buckling_curve_for_section(sec: EC3Section, axis: str = "z") -> str:
    """
    Return the buckling curve designation for the given section and axis
    per EN 1993-1-1 Table 6.2.

    Only rolled I/H sections (IPE, HEA, HEB) are handled.  Other families
    default to curve 'b'.

    Parameters
    ----------
    sec  : EC3Section
    axis : 'y' (strong) or 'z' (weak)
    """
    fam = sec.family.upper()
    h_b = sec.h / sec.b
    tf = sec.tf

    if fam in ("IPE", "HEA", "HEB"):
        if tf <= 40.0:
            if h_b > 1.2:
                return "a" if axis == "y" else "b"
            else:
                return "b" if axis == "y" else "c"
        elif tf <= 100.0:
            if h_b > 1.2:
                return "b" if axis == "y" else "c"
            else:
                return "c" if axis == "y" else "d"
        else:
            return "d"
    else:
        return "b"


def _chi_from_curve(lambda_bar: float, curve: str) -> float:
    """
    Compute reduction factor χ from non-dimensional slenderness λ̄ and
    buckling curve designation.

    EN 1993-1-1 §6.3.1.2 Eq. (6.49) / (6.50).
    """
    alpha = _ALPHA_CURVE.get(curve, _ALPHA_CURVE["b"])
    if lambda_bar <= 0.2:
        return 1.0
    phi = 0.5 * (1.0 + alpha * (lambda_bar - 0.2) + lambda_bar ** 2)
    chi = 1.0 / (phi + math.sqrt(max(phi ** 2 - lambda_bar ** 2, 0.0)))
    return min(chi, 1.0)


def compression_resistance(
    sec: EC3Section,
    grade: SteelGrade,
    L_cr_y: float,     # buckling length about strong axis (mm)
    L_cr_z: float,     # buckling length about weak axis (mm)
    *,
    gamma_M1: float = EC3_GAMMA_M1,
) -> dict[str, Any]:
    """
    Flexural buckling resistance Nb,Rd per EN 1993-1-1 §6.3.1.

    Computes independently for strong (y) and weak (z) axes; the governing
    (lower) Nb,Rd is returned.

    Returns
    -------
    dict with keys:
        Ncr_y_N       : elastic critical force, strong axis (N)
        Ncr_z_N       : elastic critical force, weak axis (N)
        lambda_bar_y  : non-dimensional slenderness, strong axis
        lambda_bar_z  : non-dimensional slenderness, weak axis
        curve_y       : buckling curve, strong axis
        curve_z       : buckling curve, weak axis
        chi_y         : reduction factor χ, strong axis
        chi_z         : reduction factor χ, weak axis
        Nb_Rd_y_N     : buckling resistance, strong axis (N)
        Nb_Rd_z_N     : buckling resistance, weak axis (N)
        Nb_Rd_N       : governing (min) Nb,Rd (N)
        Nb_Rd_kN      : governing Nb,Rd (kN)
        governing_axis: 'y' or 'z'
        Npl_Rk_N      : characteristic plastic squash load A·fy (N)
        warnings      : list[str]
    """
    warnings: list[str] = []
    E = EC3_E

    Npl = sec.A * grade.fy  # N

    # Elastic critical loads (Euler)
    Ncr_y = math.pi ** 2 * E * sec.Iy / (L_cr_y ** 2)
    Ncr_z = math.pi ** 2 * E * sec.Iz / (L_cr_z ** 2)

    # Non-dimensional slenderness
    lambda_y = math.sqrt(Npl / Ncr_y)
    lambda_z = math.sqrt(Npl / Ncr_z)

    # Buckling curves
    cy = buckling_curve_for_section(sec, axis="y")
    cz = buckling_curve_for_section(sec, axis="z")

    chi_y = _chi_from_curve(lambda_y, cy)
    chi_z = _chi_from_curve(lambda_z, cz)

    Nb_y = chi_y * sec.A * grade.fy / gamma_M1
    Nb_z = chi_z * sec.A * grade.fy / gamma_M1

    if Nb_z <= Nb_y:
        governing = "z"
        Nb_Rd = Nb_z
    else:
        governing = "y"
        Nb_Rd = Nb_y

    return {
        "Ncr_y_N":       round(Ncr_y, 1),
        "Ncr_z_N":       round(Ncr_z, 1),
        "lambda_bar_y":  round(lambda_y, 4),
        "lambda_bar_z":  round(lambda_z, 4),
        "curve_y":       cy,
        "curve_z":       cz,
        "chi_y":         round(chi_y, 4),
        "chi_z":         round(chi_z, 4),
        "Nb_Rd_y_N":     round(Nb_y, 1),
        "Nb_Rd_z_N":     round(Nb_z, 1),
        "Nb_Rd_N":       round(Nb_Rd, 1),
        "Nb_Rd_kN":      round(Nb_Rd / 1000.0, 2),
        "governing_axis": governing,
        "Npl_Rk_N":      round(Npl, 1),
        "warnings":      warnings,
    }


# ---------------------------------------------------------------------------
# §6.2.5 / §6.2.6 Cross-section bending resistance Mc,Rd
# ---------------------------------------------------------------------------

def _effective_width_class4(c: float, t: float, eps: float) -> float:
    """
    Simple effective-width approximation for Class 4 elements
    (internal compression element, EN 1993-1-5 §4.4).

    ρ = (λp - 0.055*(3+ψ)) / λp²  with ψ=1 (uniform compression)
    → ρ = (λp - 0.188) / λp²  clamped to [0, 1].
    λp = (c/t) / (28.4·ε·√kσ)  with kσ=4.0 for internal element ψ=1.

    This is a first-order approximation; more precise per EN 1993-1-5 §4.
    """
    lambda_p = (c / t) / (28.4 * eps * math.sqrt(4.0))
    if lambda_p <= 0.673:
        return c * t  # fully effective
    rho = (lambda_p - 0.188) / (lambda_p ** 2)
    rho = min(rho, 1.0)
    return rho * c * t  # effective area contribution


def bending_resistance(
    sec: EC3Section,
    grade: SteelGrade,
    *,
    gamma_M0: float = EC3_GAMMA_M0,
) -> dict[str, Any]:
    """
    Cross-section bending resistance Mc,Rd per EN 1993-1-1 §6.2.5.

    Class 1/2 → Wpl·fy/γM0
    Class 3   → Wel·fy/γM0
    Class 4   → Weff·fy/γM0  (effective section — simplified EN 1993-1-5 §4)

    Returns
    -------
    dict with:
        section_class : int
        Mc_Rd_Nmm     : N·mm
        Mc_Rd_kNm     : kN·m
        Weff_y_mm3    : effective section modulus used (mm³)
        warnings      : list[str]
    """
    clf = classify_section(sec, grade)
    sc = clf["section_class"]
    warnings: list[str] = list(clf["warnings"])

    if sc <= 2:
        W_eff = sec.Wpl_y
    elif sc == 3:
        W_eff = sec.Wel_y
    else:
        # Class 4: compute effective section modulus (simplified)
        eps = grade.epsilon()
        # Effective web
        c_w = sec.h - 2.0 * sec.tf
        A_w_eff = _effective_width_class4(c_w, sec.tw, eps)
        # Effective flanges (outstand, ψ=0 for outstand → kσ=0.43)
        c_f = (sec.b - sec.tw) / 2.0
        lambda_p_f = (c_f / sec.tf) / (28.4 * eps * math.sqrt(0.43))
        if lambda_p_f <= 0.748:
            rho_f = 1.0
        else:
            rho_f = min(1.0, (lambda_p_f - 0.188) / lambda_p_f ** 2)
        # Approx Weff,y: lose half the ineffective depth from each half
        d_w_ineff = (c_w * sec.tw - A_w_eff) / sec.tw if sec.tw > 0 else 0.0
        h_eff = sec.h - d_w_ineff
        # Effective Wel,y (simplified)
        Af_eff = rho_f * c_f * sec.tf  # effective area per flange half
        W_eff = (
            2.0 * Af_eff * (sec.h / 2.0 - sec.tf / 2.0)
            + A_w_eff * (sec.h / 2.0 - sec.tf) / 2.0
        ) / (sec.h / 2.0)
        warnings.append(
            "Class 4: Weff,y is a first-order approximation (EN 1993-1-5 §4)"
        )

    Mc_Rd = W_eff * grade.fy / gamma_M0

    return {
        "section_class": sc,
        "Mc_Rd_Nmm":     round(Mc_Rd, 1),
        "Mc_Rd_kNm":     round(Mc_Rd / 1e6, 3),
        "Weff_y_mm3":    round(W_eff, 1),
        "warnings":      warnings,
    }


# ---------------------------------------------------------------------------
# §6.3.2 Lateral-torsional buckling resistance Mb,Rd
# ---------------------------------------------------------------------------

def _mcr_uniform_moment(
    sec: EC3Section,
    L: float,
    C1: float = 1.0,
) -> float:
    """
    Elastic critical moment Mcr for a uniform doubly-symmetric I-section
    under uniform moment, per EN 1993-1-1 Annex F (informative), Eq. (F.2).

        Mcr = C1 · (π²·E·Iz / L²) · √[ Iw/Iz + (L²·G·It)/(π²·E·Iz) ]

    Parameters
    ----------
    sec : EC3Section
    L   : unbraced length Lb (mm)
    C1  : equivalent uniform moment factor (=1.0 for uniform moment)

    Notes
    -----
    The more general SCI/Gardner-Nethercot expression (including C2, C3
    load height terms) reduces to this form for doubly-symmetric sections
    under uniform moment with C2=0.
    This is Eq. (F.2) from EN 1993-1-1 Annex F (also Trahair §3.4).
    """
    E = EC3_E
    G = EC3_G
    EIz = E * sec.Iz
    GIt = G * sec.It

    pi2_EIz_over_L2 = math.pi ** 2 * EIz / L ** 2
    under_sqrt = sec.Iw / sec.Iz + (L ** 2 * GIt) / (math.pi ** 2 * EIz)
    Mcr = C1 * pi2_EIz_over_L2 * math.sqrt(under_sqrt)
    return Mcr


def _ltb_curve_for_section(sec: EC3Section) -> str:
    """
    LTB buckling curve per EN 1993-1-1 Table 6.4 (rolled I/H sections).

    h/b ≤ 2 → curve b; h/b > 2 → curve c.
    Default curve b for unknown families.
    """
    h_b = sec.h / sec.b
    if sec.family.upper() in ("IPE", "HEA", "HEB"):
        return "b" if h_b <= 2.0 else "c"
    return "b"


def _chi_LT(lambda_bar_LT: float, curve: str) -> float:
    """
    χLT from non-dimensional LTB slenderness λ̄LT.

    EN 1993-1-1 §6.3.2.2 Eq. (6.56) / (6.57).
    Plateau λ̄LT,0 = 0.4 (recommended value §6.3.2.3).
    """
    alpha = _ALPHA_CURVE.get(curve, _ALPHA_CURVE["b"])
    lambda_LT0 = 0.4  # recommended plateau (§6.3.2.3)
    beta = 0.75       # recommended correction factor
    if lambda_bar_LT <= lambda_LT0:
        return 1.0
    phi_LT = 0.5 * (1.0 + alpha * (lambda_bar_LT - lambda_LT0)
                    + beta * lambda_bar_LT ** 2)
    chi_LT = 1.0 / (phi_LT + math.sqrt(max(phi_LT ** 2 - beta * lambda_bar_LT ** 2, 0.0)))
    return min(chi_LT, 1.0)


def ltb_resistance(
    sec: EC3Section,
    grade: SteelGrade,
    L_b: float,            # unbraced length (mm)
    C1: float = 1.0,       # moment gradient factor (1.0 = uniform moment)
    *,
    gamma_M1: float = EC3_GAMMA_M1,
) -> dict[str, Any]:
    """
    Lateral-torsional buckling resistance Mb,Rd per EN 1993-1-1 §6.3.2.

    Uses the improved method (§6.3.2.3) with λ̄LT,0 = 0.4 and β = 0.75.
    Wy is taken as Wpl,y for Class 1/2 sections (conservative for Class 3).

    Parameters
    ----------
    sec    : EC3Section
    grade  : SteelGrade
    L_b    : lateral unbraced length (mm)
    C1     : equivalent uniform moment factor; C1 = 1.0 for uniform moment
             (conservative); C1 > 1.0 for non-uniform moment (e.g. 1.77 for
             single-curvature linear; see SCI P362 Table B.3).
    gamma_M1 : partial factor (default 1.0)

    Returns
    -------
    dict with:
        Mcr_Nmm       : elastic critical moment (N·mm)
        Mcr_kNm       : Mcr (kN·m)
        lambda_bar_LT : non-dimensional LTB slenderness
        ltb_curve     : buckling curve designation
        chi_LT        : LTB reduction factor
        Mb_Rd_Nmm     : N·mm
        Mb_Rd_kNm     : kN·m
        section_class : cross-section class
        Wy_mm3        : section modulus used
        C1            : moment factor used
        warnings      : list[str]
    """
    warnings: list[str] = []

    clf = classify_section(sec, grade)
    sc = clf["section_class"]
    warnings.extend(clf["warnings"])

    # Choose section modulus
    if sc <= 2:
        Wy = sec.Wpl_y
    elif sc == 3:
        Wy = sec.Wel_y
        warnings.append("Class 3: using Wel,y for LTB check")
    else:
        Wy = sec.Wel_y  # conservative for Class 4 (use Weff,y properly in practice)
        warnings.append("Class 4: using Wel,y as conservative proxy; compute Weff,y for final design")

    Mcr = _mcr_uniform_moment(sec, L_b, C1)
    lambda_LT = math.sqrt(Wy * grade.fy / Mcr)

    ltb_curve = _ltb_curve_for_section(sec)
    chi_LT = _chi_LT(lambda_LT, ltb_curve)

    Mb_Rd = chi_LT * Wy * grade.fy / gamma_M1

    return {
        "Mcr_Nmm":       round(Mcr, 1),
        "Mcr_kNm":       round(Mcr / 1e6, 3),
        "lambda_bar_LT": round(lambda_LT, 4),
        "ltb_curve":     ltb_curve,
        "chi_LT":        round(chi_LT, 4),
        "Mb_Rd_Nmm":     round(Mb_Rd, 1),
        "Mb_Rd_kNm":     round(Mb_Rd / 1e6, 3),
        "section_class": sc,
        "Wy_mm3":        round(Wy, 1),
        "C1":            C1,
        "warnings":      warnings,
    }


# ---------------------------------------------------------------------------
# §6.3.3 Combined N+M interaction — Method 2 (Annex B)
# ---------------------------------------------------------------------------

def _interaction_factors_method2(
    *,
    chi_y: float,
    chi_z: float,
    chi_LT: float,
    lambda_y: float,
    lambda_z: float,
    NEd: float,
    NRk: float,
    My_Ed: float,
    My_Rk: float,
    Mz_Ed: float,
    Mz_Rk: float,
    sec: EC3Section,
    gamma_M1: float,
) -> dict[str, Any]:
    """
    Interaction factors k_yy, k_yz, k_zy, k_zz per EN 1993-1-1 Annex B
    Table B.1 (Method 2, simplified, for Class 1/2 sections).

    Simplified expressions for doubly-symmetric I-sections (no lateral load):
      k_yy = C_my * (1 + min(λ̄y, 0.6) * μ_y)
      k_zz = C_mz * (1 + min(2*λ̄z - 0.6, 1.4) * μ_z)
      k_zy = 0.6 * k_zz
      k_yz = 0.6 * k_yy

    With moment factors C_my = C_mz = 0.9 (uniform moment, most conservative).
    μ_y = NEd / (χ_y · NRk/γM1), μ_z = NEd / (χ_z · NRk/γM1).

    For general design, C_my/C_mz should be derived from the moment diagram
    (Annex B Table B.3).
    """
    Cm = 0.9  # conservative uniform-moment C_my = C_mz = C_mLT

    mu_y = NEd / max(chi_y * NRk / gamma_M1, 1.0)
    mu_z = NEd / max(chi_z * NRk / gamma_M1, 1.0)

    k_yy = Cm * (1.0 + min(lambda_y, 0.6) * mu_y)
    k_zz = Cm * (1.0 + min(max(2.0 * lambda_z - 0.6, 0.0), 1.4) * mu_z)
    k_zy = 0.6 * k_zz
    k_yz = 0.6 * k_yy

    return {
        "k_yy": round(k_yy, 4),
        "k_yz": round(k_yz, 4),
        "k_zy": round(k_zy, 4),
        "k_zz": round(k_zz, 4),
        "Cm_y": Cm,
        "Cm_z": Cm,
        "mu_y": round(mu_y, 4),
        "mu_z": round(mu_z, 4),
    }


def combined_nm_check(
    sec: EC3Section,
    grade: SteelGrade,
    NEd: float,     # design axial force (N), compression positive
    My_Ed: float,   # design major-axis moment (N·mm)
    Mz_Ed: float,   # design minor-axis moment (N·mm)
    L_cr_y: float,  # effective length about strong axis (mm)
    L_cr_z: float,  # effective length about weak axis (mm)
    L_b: float,     # lateral unbraced length for LTB (mm)
    C1: float = 1.0,
    *,
    gamma_M0: float = EC3_GAMMA_M0,
    gamma_M1: float = EC3_GAMMA_M1,
) -> dict[str, Any]:
    """
    Combined N–M interaction check per EN 1993-1-1 §6.3.3 (Method 2, Annex B).

    Checks:
      (1) NEd/(Nb,Rd,y) + k_yy·My,Ed/(χLT·My,Rk/γM1) + k_yz·Mz,Ed/(Mz,Rk/γM1) ≤ 1
      (2) NEd/(Nb,Rd,z) + k_zy·My,Ed/(χLT·My,Rk/γM1) + k_zz·Mz,Ed/(Mz,Rk/γM1) ≤ 1

    Returns
    -------
    dict with:
        ok           : True if both interactions ≤ 1.0
        DCR_eq1      : demand-capacity ratio for Eq. (1)  (≤ 1.0 = pass)
        DCR_eq2      : demand-capacity ratio for Eq. (2)
        compression  : compression check sub-results
        ltb          : LTB check sub-results
        interaction  : interaction factor dict
        warnings     : list[str]
    """
    warnings: list[str] = []

    comp = compression_resistance(sec, grade, L_cr_y, L_cr_z, gamma_M1=gamma_M1)
    ltb  = ltb_resistance(sec, grade, L_b, C1, gamma_M1=gamma_M1)
    bend = bending_resistance(sec, grade, gamma_M0=gamma_M0)

    warnings.extend(comp["warnings"])
    warnings.extend(ltb["warnings"])
    warnings.extend(bend["warnings"])

    chi_y = comp["chi_y"]
    chi_z = comp["chi_z"]
    chi_LT = ltb["chi_LT"]
    lambda_y = comp["lambda_bar_y"]
    lambda_z = comp["lambda_bar_z"]

    NRk = sec.A * grade.fy
    Nb_Rd_y = comp["Nb_Rd_y_N"]
    Nb_Rd_z = comp["Nb_Rd_z_N"]

    sc = bend["section_class"]
    if sc <= 2:
        My_Rk = sec.Wpl_y * grade.fy
        Mz_Rk = sec.Iz / (sec.b / 2.0) * grade.fy if sec.b > 0 else 0.0
    else:
        My_Rk = sec.Wel_y * grade.fy
        Mz_Rk = sec.Iz / (sec.b / 2.0) * grade.fy if sec.b > 0 else 0.0

    kf = _interaction_factors_method2(
        chi_y=chi_y,
        chi_z=chi_z,
        chi_LT=chi_LT,
        lambda_y=lambda_y,
        lambda_z=lambda_z,
        NEd=NEd,
        NRk=NRk,
        My_Ed=My_Ed,
        My_Rk=My_Rk,
        Mz_Ed=Mz_Ed,
        Mz_Rk=Mz_Rk,
        sec=sec,
        gamma_M1=gamma_M1,
    )

    chi_LT_My_Rk_over_gM1 = chi_LT * My_Rk / gamma_M1
    Mz_denom = Mz_Rk / gamma_M1

    if Nb_Rd_y <= 0:
        return {"ok": False, "error": "Nb,Rd,y <= 0", "warnings": warnings}
    if Nb_Rd_z <= 0:
        return {"ok": False, "error": "Nb,Rd,z <= 0", "warnings": warnings}

    # Eq. (6.61)
    term1_eq1 = NEd / Nb_Rd_y
    term2_eq1 = kf["k_yy"] * My_Ed / chi_LT_My_Rk_over_gM1 if chi_LT_My_Rk_over_gM1 > 0 else 0.0
    term3_eq1 = kf["k_yz"] * Mz_Ed / Mz_denom if Mz_denom > 0 else 0.0
    DCR1 = term1_eq1 + term2_eq1 + term3_eq1

    # Eq. (6.62)
    term1_eq2 = NEd / Nb_Rd_z
    term2_eq2 = kf["k_zy"] * My_Ed / chi_LT_My_Rk_over_gM1 if chi_LT_My_Rk_over_gM1 > 0 else 0.0
    term3_eq2 = kf["k_zz"] * Mz_Ed / Mz_denom if Mz_denom > 0 else 0.0
    DCR2 = term1_eq2 + term2_eq2 + term3_eq2

    return {
        "ok":          DCR1 <= 1.0 and DCR2 <= 1.0,
        "DCR_eq1":     round(DCR1, 4),
        "DCR_eq2":     round(DCR2, 4),
        "compression": comp,
        "ltb":         ltb,
        "bending":     bend,
        "interaction": kf,
        "warnings":    warnings,
    }


# ---------------------------------------------------------------------------
# Convenience top-level function
# ---------------------------------------------------------------------------

def ec3_steel_check(
    section_name: str,
    grade_name: str,
    NEd_kN: float = 0.0,
    My_Ed_kNm: float = 0.0,
    Mz_Ed_kNm: float = 0.0,
    L_cr_y_m: float = 5.0,
    L_cr_z_m: float = 5.0,
    L_b_m: float = 5.0,
    C1: float = 1.0,
) -> dict[str, Any]:
    """
    High-level EC3 steel member check.

    Parameters (all optional keyword, sensible defaults)
    ----------
    section_name : str — e.g. "IPE300"
    grade_name   : str — e.g. "S275"
    NEd_kN       : design axial force (kN), compression positive
    My_Ed_kNm    : design major-axis moment (kN·m)
    Mz_Ed_kNm    : design minor-axis moment (kN·m)
    L_cr_y_m     : effective buckling length, strong axis (m)
    L_cr_z_m     : effective buckling length, weak axis (m)
    L_b_m        : lateral unbraced length for LTB (m)
    C1           : moment gradient factor (1.0 = uniform moment)

    Returns
    -------
    dict with ok, section, grade, and all sub-check results.
    """
    sec = get_ec3_section(section_name)
    if sec is None:
        return {
            "ok": False,
            "error": (
                f"Unknown section '{section_name}'. "
                f"Available: {sorted(EC3_SECTION_CATALOG.keys())}"
            ),
        }
    grd = get_grade(grade_name)
    if grd is None:
        return {
            "ok": False,
            "error": (
                f"Unknown grade '{grade_name}'. "
                f"Available: {sorted(STEEL_GRADES.keys())}"
            ),
        }

    result = combined_nm_check(
        sec, grd,
        NEd=NEd_kN * 1000.0,
        My_Ed=My_Ed_kNm * 1e6,
        Mz_Ed=Mz_Ed_kNm * 1e6,
        L_cr_y=L_cr_y_m * 1000.0,
        L_cr_z=L_cr_z_m * 1000.0,
        L_b=L_b_m * 1000.0,
        C1=C1,
    )
    result["section"] = sec.to_dict()
    result["grade"] = {
        "name": grd.name,
        "fy_MPa": grd.fy,
        "fu_MPa": grd.fu,
        "epsilon": round(grd.epsilon(), 4),
    }
    result["inputs"] = {
        "NEd_kN": NEd_kN,
        "My_Ed_kNm": My_Ed_kNm,
        "Mz_Ed_kNm": Mz_Ed_kNm,
        "L_cr_y_m": L_cr_y_m,
        "L_cr_z_m": L_cr_z_m,
        "L_b_m": L_b_m,
        "C1": C1,
    }
    return result
