"""
AISC 360-22 Full Member Design Checks — Chapters E (Compression), F (Flexure), H (Combined).

Sections supported
------------------
W  — doubly-symmetric wide-flange (I-shape)
C  — standard channel
HSS_rect  — rectangular hollow structural section
HSS_round — round HSS
Pipe      — standard/extra-strong pipe
Angle     — single equal/unequal leg angle

Chapter E — Compression (E3, E7)
Chapter F — Flexure per section type (F2, F3, F6, F7, F8, F10)
Chapter H — Combined (H1-1a/b, H2)

All units: US customary — kips, inches, ksi.

Resistance factors / safety factors
-------------------------------------
φc = 0.90  (LRFD compression)
Ωc = 1.67  (ASD compression)
φb = 0.90  (LRFD flexure)
Ωb = 1.67  (ASD flexure)

References
----------
AISC 360-22 Specification for Structural Steel Buildings
AISC Steel Construction Manual, 16th ed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Optional

# ---------------------------------------------------------------------------
# Safety factors
# ---------------------------------------------------------------------------
PHI_C = 0.90
OMEGA_C = 1.67
PHI_B = 0.90
OMEGA_B = 1.67
E_STEEL = 29_000.0   # ksi
G_STEEL = 11_200.0   # ksi


# ===========================================================================
# Section dataclasses
# ===========================================================================

@dataclass
class WShape:
    """
    Doubly-symmetric wide-flange (W-shape) section properties.

    All in inches / ksi units.  Carry enough properties for Chapters E, F, H.
    """
    designation: str
    A: float         # Gross area (in²)
    d: float         # Total depth (in)
    bf: float        # Flange width (in)
    tf: float        # Flange thickness (in)
    tw: float        # Web thickness (in)
    Ix: float        # Moment of inertia, strong axis (in⁴)
    Sx: float        # Elastic section modulus, strong axis (in³)
    Zx: float        # Plastic section modulus, strong axis (in³)
    Iy: float        # Moment of inertia, weak axis (in⁴)
    Sy: float        # Elastic section modulus, weak axis (in³)
    Zy: float        # Plastic section modulus, weak axis (in³)
    rx: float        # Radius of gyration, strong axis (in)
    ry: float        # Radius of gyration, weak axis (in)
    J: float         # Torsional constant (in⁴)
    Cw: float        # Warping constant (in⁶)
    rts: float = 0.0 # Effective radius of gyration F2-7 (in); computed if 0
    ho: float = 0.0  # Distance between flange centroids ≈ d-tf (in); computed if 0

    section_type: str = "W"

    def __post_init__(self):
        if self.ho == 0.0:
            self.ho = self.d - self.tf
        if self.rts == 0.0 and self.Iy > 0 and self.Cw > 0 and self.Sx > 0:
            self.rts = math.sqrt(math.sqrt(self.Iy * self.Cw) / self.Sx)

    @property
    def h_tw(self) -> float:
        """Clear web height / web thickness."""
        h = self.d - 2.0 * self.tf
        return h / self.tw

    @property
    def bf_2tf(self) -> float:
        """Flange width / (2 × flange thickness) — half-width slenderness."""
        return self.bf / (2.0 * self.tf)


@dataclass
class CChannel:
    """Standard C-channel section properties."""
    designation: str
    A: float
    d: float         # depth
    bf: float        # flange width
    tf: float        # flange thickness
    tw: float        # web thickness
    Ix: float
    Sx: float
    Zx: float
    Iy: float
    Sy: float        # Sy at toe of flange (min)
    Zy: float
    rx: float
    ry: float
    J: float
    Cw: float
    eo: float = 0.0  # shear-center offset from centroid (in); used for LTB

    section_type: str = "C"

    @property
    def ho(self) -> float:
        return self.d - self.tf

    @property
    def h_tw(self) -> float:
        h = self.d - 2.0 * self.tf
        return h / self.tw

    @property
    def bf_tf(self) -> float:
        return self.bf / self.tf


@dataclass
class HSSRect:
    """Rectangular / square HSS section properties."""
    designation: str
    A: float
    H: float         # overall height (longer dimension) (in)
    B: float         # overall width (shorter dimension) (in)
    tdes: float      # design wall thickness (in) = 0.93 × t_nom
    Ix: float
    Sx: float
    Zx: float
    Iy: float
    Sy: float
    Zy: float
    rx: float
    ry: float
    J: float

    section_type: str = "HSS_rect"

    @property
    def h_t(self) -> float:
        """Flat web height / tdes (AISC Table B4.1a/b)."""
        return (self.H - 3.0 * self.tdes) / self.tdes

    @property
    def b_t(self) -> float:
        return (self.B - 3.0 * self.tdes) / self.tdes


@dataclass
class HSSRound:
    """Round HSS section properties."""
    designation: str
    A: float
    OD: float        # outside diameter (in)
    tdes: float      # design wall thickness (in)
    Ix: float        # = Iy for round
    Sx: float
    Zx: float
    rx: float        # = ry
    J: float         # = 2 × Ix

    section_type: str = "HSS_round"

    @property
    def Iy(self) -> float:
        return self.Ix

    @property
    def ry(self) -> float:
        return self.rx

    @property
    def D_t(self) -> float:
        return self.OD / self.tdes


@dataclass
class Pipe:
    """Standard / extra-strong pipe section properties."""
    designation: str   # e.g. "PIPE3STD", "PIPE4XS"
    A: float
    OD: float
    tdes: float
    Ix: float
    Sx: float
    Zx: float
    rx: float
    J: float

    section_type: str = "Pipe"

    @property
    def Iy(self) -> float:
        return self.Ix

    @property
    def ry(self) -> float:
        return self.rx

    @property
    def D_t(self) -> float:
        return self.OD / self.tdes


@dataclass
class Angle:
    """Single equal / unequal leg angle section properties."""
    designation: str   # e.g. "L4X4X1/2"
    A: float
    leg_a: float       # longer leg (in)
    leg_b: float       # shorter leg (in)
    t: float           # thickness (in)
    Ix: float          # axis parallel to longer leg
    Sx: float
    Zx: float
    Iy: float
    Sy: float
    Zy: float
    rx: float
    ry: float
    Iw: float = 0.0    # minimum I (about weak principal axis)
    rw: float = 0.0    # minimum r
    J: float = 0.0
    # shear-center / geometric eccentricities (used for LTB per F10)
    xbar: float = 0.0
    ybar: float = 0.0

    section_type: str = "Angle"

    @property
    def b_t(self) -> float:
        return max(self.leg_a, self.leg_b) / self.t


# ===========================================================================
# Section catalogues
# ===========================================================================

# --- W-shapes (20 shapes) — AISC 16th ed. Part 1 tables ---
# Tuple: (A, d, bf, tf, tw, Ix, Sx, Zx, Iy, Sy, Zy, rx, ry, J, Cw)

_W_DATA: dict[str, tuple] = {
    "W8X31":   (9.13,  8.00,  7.995, 0.435, 0.285, 110,  27.5,  30.4,  37.1, 9.27, 14.1, 3.47, 2.02, 0.536, 530),
    "W10X33":  (9.71,  9.73,  7.960, 0.435, 0.290, 170,  35.0,  38.8,  36.6, 9.20, 14.0, 4.19, 1.94, 0.583, 791),
    "W12X40":  (11.7,  11.94, 8.005, 0.515, 0.295, 307,  51.5,  57.5,  44.1, 11.0, 16.8, 5.13, 1.93, 0.810, 1480),
    "W12X50":  (14.6,  12.19, 8.077, 0.641, 0.371, 394,  64.7,  72.4,  56.3, 13.9, 21.3, 5.18, 1.96, 1.71,  1880),
    "W14X48":  (14.1,  13.79, 8.031, 0.595, 0.340, 485,  70.3,  78.4,  51.4, 12.8, 19.6, 5.85, 1.91, 1.45,  2240),
    "W14X82":  (24.0,  14.31, 10.130,0.855, 0.510, 882,  123,   139,   148,  29.3, 44.8, 6.05, 2.48, 5.07,  7440),
    "W14X90":  (26.5,  14.02, 14.520,0.710, 0.440,999,   143,   157,   362,  49.9, 75.6, 6.14, 3.70, 4.06, 16000),
    "W16X36":  (10.6,  15.86, 6.985, 0.428, 0.295, 448,  56.5,  64.0,  24.5, 7.00, 10.8, 6.51, 1.52, 0.545, 1460),
    "W16X50":  (14.7,  16.26, 7.073, 0.628, 0.380, 659,  81.0,  92.0,  37.2, 10.5, 16.3, 6.68, 1.59, 1.52,  2170),
    "W18X35":  (10.3,  17.70, 6.000, 0.425, 0.300, 510,  57.6,  66.5,  15.3, 5.12, 7.86, 7.04, 1.22, 0.506, 1140),
    "W18X50":  (14.7,  17.99, 7.495, 0.570, 0.355, 800,  88.9, 101.0,  40.1, 10.7, 16.6, 7.38, 1.65, 1.24,  3050),
    "W18X76":  (22.3,  18.21, 11.035,0.680, 0.425,1330, 146,   163,   152,  27.6, 43.1, 7.73, 2.61, 2.68,  9430),
    "W21X50":  (14.7,  20.83, 6.530, 0.535, 0.380, 984,  94.5, 110.0,  24.9, 7.64, 11.7, 8.18, 1.30, 1.14,  2110),
    "W21X68":  (20.0,  21.13, 8.270, 0.685, 0.430,1480, 140,   160,    70.6, 17.1, 26.2, 8.60, 1.80, 2.45,  6060),
    "W24X55":  (16.2,  23.57, 7.005, 0.505, 0.395,1350, 114,   131,    29.1, 8.30, 12.8, 9.11, 1.34, 1.18,  3160),
    "W24X76":  (22.4,  23.92, 8.990, 0.680, 0.440,2100, 176,   200,    82.5, 18.4, 28.6, 9.69, 1.92, 2.68,  9430),
    "W27X84":  (24.8,  26.71, 9.960, 0.640, 0.460,2850, 213,   244,   106,  21.2, 32.8, 10.7, 2.07, 2.81, 17600),
    "W30X90":  (26.3,  29.53,10.400, 0.610, 0.470,3610, 245,   283,   115,  22.1, 34.7, 11.7, 2.09, 2.84, 22700),
    "W33X130": (38.3,  33.09,11.510, 0.855, 0.580,6710, 406,   467,   218,  37.9, 58.4, 13.2, 2.39, 9.24, 59500),
    "W36X135": (39.7,  35.55,11.950, 0.790, 0.600,7800, 439,   509,   225,  37.7, 58.7, 14.0, 2.38, 7.79, 65100),
}


def w_shape(designation: str) -> WShape:
    key = designation.upper().replace(" ", "")
    if key not in _W_DATA:
        raise KeyError(f"W-shape '{designation}' not in built-in table.")
    (A, d, bf, tf, tw, Ix, Sx, Zx, Iy, Sy, Zy, rx, ry, J, Cw) = _W_DATA[key]
    return WShape(
        designation=key, A=A, d=d, bf=bf, tf=tf, tw=tw,
        Ix=Ix, Sx=Sx, Zx=Zx, Iy=Iy, Sy=Sy, Zy=Zy,
        rx=rx, ry=ry, J=J, Cw=Cw,
    )


# --- HSS Rectangular (10 shapes) ---
# Tuple: (A, H, B, tdes, Ix, Sx, Zx, Iy, Sy, Zy, rx, ry, J)
_HSS_RECT_DATA: dict[str, tuple] = {
    "HSS4X4X1/4":   (3.37,  4.0,  4.0, 0.233, 8.22, 4.11,  5.17, 8.22,  4.11,  5.17, 1.56, 1.56, 13.5),
    "HSS4X4X3/8":   (4.78,  4.0,  4.0, 0.349,10.7,  5.35,  6.87,10.7,   5.35,  6.87, 1.50, 1.50, 17.8),
    "HSS5X5X1/4":   (4.30,  5.0,  5.0, 0.233,17.0,  6.80,  8.53,17.0,   6.80,  8.53, 1.99, 1.99, 27.7),
    "HSS5X5X5/16":  (5.26,  5.0,  5.0, 0.291,20.3,  8.10, 10.2, 20.3,   8.10, 10.2,  1.96, 1.96, 33.2),
    "HSS6X4X3/16":  (3.39,  6.0,  4.0, 0.174,18.5,  6.16,  7.73, 9.24,  4.62,  5.64, 2.34, 1.65, 20.4),
    "HSS6X6X1/4":   (5.24,  6.0,  6.0, 0.233,31.1,  10.4, 12.9, 31.1,  10.4,  12.9,  2.44, 2.44, 50.7),
    "HSS6X6X3/8":   (7.58,  6.0,  6.0, 0.349,42.6,  14.2, 17.9, 42.6,  14.2,  17.9,  2.37, 2.37, 70.1),
    "HSS8X6X5/16":  (7.58,  8.0,  6.0, 0.291,74.5,  18.6, 23.2, 46.4,  15.5,  18.9,  3.13, 2.47, 93.6),
    "HSS8X8X3/8":   (10.4,  8.0,  8.0, 0.349,105,   26.3, 32.8,105,    26.3,  32.8,  3.18, 3.18, 173),
    "HSS10X8X3/8":  (12.1, 10.0,  8.0, 0.349,192,   38.3, 47.3,130,    32.4,  39.5,  3.98, 3.27, 268),
}


def hss_rect(designation: str) -> HSSRect:
    key = designation.upper().replace(" ", "")
    if key not in _HSS_RECT_DATA:
        raise KeyError(f"HSS_rect '{designation}' not in built-in table.")
    A, H, B, tdes, Ix, Sx, Zx, Iy, Sy, Zy, rx, ry, J = _HSS_RECT_DATA[key]
    return HSSRect(
        designation=key, A=A, H=H, B=B, tdes=tdes,
        Ix=Ix, Sx=Sx, Zx=Zx, Iy=Iy, Sy=Sy, Zy=Zy,
        rx=rx, ry=ry, J=J,
    )


# --- HSS Round (5 shapes) ---
# Tuple: (A, OD, tdes, Ix, Sx, Zx, rx, J)
_HSS_ROUND_DATA: dict[str, tuple] = {
    "HSS3.500X0.216": (2.23, 3.500, 0.201, 3.02, 1.72, 2.28, 1.16, 6.04),
    "HSS4.000X0.237": (2.76, 4.000, 0.220, 5.02, 2.51, 3.32, 1.35, 10.0),
    "HSS4.500X0.237": (3.14, 4.500, 0.220, 7.29, 3.24, 4.27, 1.52, 14.6),
    "HSS5.000X0.250": (3.67, 5.000, 0.233,11.3,  4.53, 5.96, 1.76, 22.7),
    "HSS6.000X0.250": (4.44, 6.000, 0.233,19.5,  6.50, 8.53, 2.10, 39.1),
}


def hss_round(designation: str) -> HSSRound:
    key = designation.upper().replace(" ", "")
    if key not in _HSS_ROUND_DATA:
        raise KeyError(f"HSS_round '{designation}' not in built-in table.")
    A, OD, tdes, Ix, Sx, Zx, rx, J = _HSS_ROUND_DATA[key]
    return HSSRound(designation=key, A=A, OD=OD, tdes=tdes,
                    Ix=Ix, Sx=Sx, Zx=Zx, rx=rx, J=J)


# --- Pipes (5 shapes) ---
# Tuple: (A, OD, tdes, Ix, Sx, Zx, rx, J)
_PIPE_DATA: dict[str, tuple] = {
    "PIPE2STD":   (1.07, 2.375, 0.154,  0.666, 0.561, 0.780, 0.787, 1.33),
    "PIPE3STD":   (2.23, 3.500, 0.216,  3.02,  1.72,  2.28,  1.16,  6.04),
    "PIPE4STD":   (3.17, 4.500, 0.237,  7.23,  3.21,  4.31,  1.51,  14.5),
    "PIPE4XS":    (3.68, 4.500, 0.281,  8.14,  3.62,  4.90,  1.49,  16.3),
    "PIPE6STD":   (5.58, 6.625, 0.280, 28.1,   8.50, 11.4,   2.25,  56.3),
}


def pipe(designation: str) -> Pipe:
    key = designation.upper().replace(" ", "")
    if key not in _PIPE_DATA:
        raise KeyError(f"Pipe '{designation}' not in built-in table.")
    A, OD, tdes, Ix, Sx, Zx, rx, J = _PIPE_DATA[key]
    return Pipe(designation=key, A=A, OD=OD, tdes=tdes,
                Ix=Ix, Sx=Sx, Zx=Zx, rx=rx, J=J)


# --- Angles (5 shapes) ---
# Tuple: (A, leg_a, leg_b, t, Ix, Sx, Zx, Iy, Sy, Zy, rx, ry, J)
_ANGLE_DATA: dict[str, tuple] = {
    "L3X3X1/4":  (1.44, 3.0, 3.0, 0.250, 1.24, 0.577, 0.975, 1.24, 0.577, 0.975, 0.930, 0.930, 0.031),
    "L3X3X3/8":  (2.09, 3.0, 3.0, 0.375, 1.76, 0.833, 1.42,  1.76, 0.833, 1.42,  0.918, 0.918, 0.098),
    "L4X4X1/4":  (1.94, 4.0, 4.0, 0.250, 2.91, 1.00,  1.67,  2.91, 1.00,  1.67,  1.22,  1.22,  0.055),
    "L4X4X1/2":  (3.75, 4.0, 4.0, 0.500, 5.56, 1.97,  3.38,  5.56, 1.97,  3.38,  1.22,  1.22,  0.396),
    "L6X4X3/8":  (3.61, 6.0, 4.0, 0.375,13.4,  3.03,  5.17,  4.90, 1.72,  2.77,  1.93,  1.17,  0.169),
}


def angle(designation: str) -> Angle:
    key = designation.upper().replace(" ", "")
    if key not in _ANGLE_DATA:
        raise KeyError(f"Angle '{designation}' not in built-in table.")
    A, la, lb, t, Ix, Sx, Zx, Iy, Sy, Zy, rx, ry, J = _ANGLE_DATA[key]
    return Angle(designation=key, A=A, leg_a=la, leg_b=lb, t=t,
                 Ix=Ix, Sx=Sx, Zx=Zx, Iy=Iy, Sy=Sy, Zy=Zy,
                 rx=rx, ry=ry, J=J)


# ---------------------------------------------------------------------------
# Channels (5 shapes)
# ---------------------------------------------------------------------------
# Tuple: (A, d, bf, tf, tw, Ix, Sx, Zx, Iy, Sy, Zy, rx, ry, J, Cw, eo)
_C_DATA: dict[str, tuple] = {
    "C6X10.5": (3.09, 6.00, 2.034, 0.343, 0.314, 15.2, 5.06, 6.16, 0.866, 0.642, 1.49, 2.22, 0.529, 0.0560, 7.49,  0.838),
    "C8X11.5": (3.38, 8.00, 2.260, 0.390, 0.220, 32.6, 8.14, 9.55, 1.32,  0.781, 1.88, 3.11, 0.625, 0.0625, 27.1,  0.969),
    "C10X20":  (5.88,10.00, 2.739, 0.436, 0.379, 78.9,15.8, 18.7,  2.81,  1.32,  3.14, 3.66, 0.692, 0.220,  108,   1.07),
    "C12X20.7":(6.09,12.00, 2.942, 0.501, 0.282,129,  21.5, 25.7,  3.88,  1.73,  4.12, 4.61, 0.799, 0.233,  227,   1.17),
    "C15X33.9":(9.96,15.00, 3.400, 0.650, 0.400,315,  42.0, 50.4,  8.13,  3.11,  7.24, 5.62, 0.904, 0.904,  890,   1.41),
}


def c_channel(designation: str) -> CChannel:
    key = designation.upper().replace(" ", "")
    if key not in _C_DATA:
        raise KeyError(f"Channel '{designation}' not in built-in table.")
    A, d, bf, tf, tw, Ix, Sx, Zx, Iy, Sy, Zy, rx, ry, J, Cw, eo = _C_DATA[key]
    return CChannel(designation=key, A=A, d=d, bf=bf, tf=tf, tw=tw,
                    Ix=Ix, Sx=Sx, Zx=Zx, Iy=Iy, Sy=Sy, Zy=Zy,
                    rx=rx, ry=ry, J=J, Cw=Cw, eo=eo)


# ===========================================================================
# Chapter E — Compression
# ===========================================================================

def _lambda_r_flange_unstiffened(E: float, Fy: float) -> float:
    """AISC Table B4.1a case 1 — unstiffened element (flange of W/C): λr = 0.56√(E/Fy)."""
    return 0.56 * math.sqrt(E / Fy)


def _lambda_r_web_stiffened(E: float, Fy: float) -> float:
    """AISC Table B4.1a case 5 — stiffened element (web in uniform compression): λr = 1.49√(E/Fy)."""
    return 1.49 * math.sqrt(E / Fy)


def _Qs_flange(lambda_f: float, E: float, Fy: float) -> float:
    """
    AISC E7.1 — Qs for unstiffened slender flanges (W, C).
    λ = b/t = bf/(2tf)  for W, bf/tf for C.
    """
    lr = _lambda_r_flange_unstiffened(E, Fy)
    if lambda_f <= lr:
        return 1.0
    elif lambda_f <= 1.03 * math.sqrt(E / Fy):
        # E7-7: Qs = 1.415 - 0.74 λ √(Fy/E)
        return 1.415 - 0.74 * lambda_f * math.sqrt(Fy / E)
    else:
        # E7-8: Qs = 0.69 E / (Fy λ²)
        return 0.69 * E / (Fy * lambda_f ** 2)


def _Qa_web(A: float, Aeff: float) -> float:
    """AISC E7.2 — Qa = Aeff / A for stiffened elements (web in compression)."""
    return min(Aeff / A, 1.0)


def _aeff_web(tw: float, h: float, E: float, Fy: float) -> float:
    """
    AISC E7.2 — effective area of slender web under uniform compression.
    f is taken as Fy (conservative per E7.2).
    be = 1.92·t·√(E/f)·[1 - 0.34/(λ·√(f/E))] ≤ b
    """
    lambda_w = h / tw
    lr = _lambda_r_web_stiffened(E, Fy)
    if lambda_w <= lr:
        return h * tw  # not slender
    f = Fy
    be = 1.92 * tw * math.sqrt(E / f) * (1.0 - 0.34 / (lambda_w * math.sqrt(f / E)))
    be = max(0.0, min(be, h))
    return be * tw


@dataclass
class CompressionResult:
    ok: bool
    reason: str = ""
    Fcr: float = 0.0          # ksi
    Pn: float = 0.0           # kips
    phi_Pn: float = 0.0       # kips (LRFD)
    Pn_over_Omega: float = 0.0  # kips (ASD)
    KL_r: float = 0.0
    Fe: float = 0.0
    Q: float = 1.0
    governing_axis: str = ""


def aisc_compression(
    section,
    Lc: float,        # effective length about strong axis (ft) for Lcx
    Lcy: float = 0.0, # effective length about weak axis (ft); 0 → same as Lc
    *,
    K: float = 1.0,   # kept for API symmetry but Lc should already include K
    E: float = E_STEEL,
    Fy: float = 50.0,
) -> CompressionResult:
    """
    AISC 360-22 Chapter E compression capacity.

    Parameters
    ----------
    section : WShape | CChannel | HSSRect | HSSRound | Pipe | Angle
    Lc : float
        Effective length KL about strong axis (ft). Usually K × unbraced length.
    Lcy : float
        Effective length KL about weak axis (ft). If 0, uses Lc.
    E, Fy : float
        Material properties (ksi).

    Returns
    -------
    CompressionResult
    """
    res = CompressionResult(ok=False)
    if Lcy == 0.0:
        Lcy = Lc

    Lc_in = Lc * 12.0
    Lcy_in = Lcy * 12.0

    # Radii of gyration
    if isinstance(section, WShape):
        rx, ry = section.rx, section.ry
        A = section.A
    elif isinstance(section, CChannel):
        rx, ry = section.rx, section.ry
        A = section.A
    elif isinstance(section, (HSSRect, HSSRound, Pipe)):
        rx = section.rx
        ry = getattr(section, "ry", section.rx)
        A = section.A
    elif isinstance(section, Angle):
        rx, ry = section.rx, section.ry
        A = section.A
    else:
        res.reason = f"Unsupported section type: {type(section)}"
        return res

    KL_r_x = Lc_in / rx
    KL_r_y = Lcy_in / ry
    KL_r = max(KL_r_x, KL_r_y)  # governing slenderness
    res.KL_r = KL_r
    res.governing_axis = "x" if KL_r_x >= KL_r_y else "y"

    # Elastic buckling stress
    Fe = math.pi ** 2 * E / KL_r ** 2
    res.Fe = Fe

    # Slender-element reduction Q = Qs × Qa  (E7)
    # Simplified: only W and C get flange+web slenderness; others treated as compact.
    Q = 1.0
    if isinstance(section, WShape):
        lambda_f = section.bf_2tf
        Qs = _Qs_flange(lambda_f, E, Fy)
        h = section.d - 2.0 * section.tf
        Aeff_web = _aeff_web(section.tw, h, E, Fy)
        Atotal_web = h * section.tw
        Qa = 1.0 if Atotal_web <= 0 else min((A - Atotal_web + Aeff_web) / A, 1.0)
        Q = Qs * Qa
    elif isinstance(section, CChannel):
        # Unstiffened flange: b = bf, t = tf; use bf/tf per Table B4.1a
        lambda_f = section.bf_tf
        Qs = _Qs_flange(lambda_f, E, Fy)
        Q = Qs   # web of C under compression: not critical for most channels
    elif isinstance(section, HSSRect):
        # Stiffened walls: Qa based on be  (E7.2)
        # Strong axis compression: both walls are stiffened; use larger h_t
        h_t = max(section.h_t, section.b_t)
        lr_stiff = _lambda_r_web_stiffened(E, Fy)
        if h_t > lr_stiff:
            # Effective width for the slender wall
            be = 1.92 * section.tdes * math.sqrt(E / Fy) * (
                1.0 - 0.34 / (h_t * math.sqrt(Fy / E))
            )
            be = min(be, max(section.H, section.B) - 3.0 * section.tdes)
            # Approximate: reduce area for two slender walls
            b_actual = max(section.H, section.B) - 3.0 * section.tdes
            delta_A = 2.0 * (b_actual - be) * section.tdes
            Qa = max((A - delta_A) / A, 0.0)
            Q = Qa
    elif isinstance(section, (HSSRound, Pipe)):
        # E7.2c for round HSS / pipe
        D_t = section.D_t
        lam1 = 0.11 * E / Fy
        lam2 = 0.45 * E / Fy
        if D_t <= lam1:
            Q = 1.0
        elif D_t <= lam2:
            Q = 0.038 * E / (Fy * D_t) + 2.0 / 3.0
        else:
            # Very slender — beyond practical range; use 0.038 formula clipped
            Q = 0.038 * E / (Fy * D_t) + 2.0 / 3.0
    res.Q = Q

    # Critical stress — E3 with Q modification (E7 replaces Fy with Q·Fy)
    QFy = Q * Fy
    limit = 4.71 * math.sqrt(E / QFy)
    if KL_r <= limit:
        # E3-2: Fcr = Q × 0.658^(QFy/Fe) × Fy
        Fcr = Q * (0.658 ** (QFy / Fe)) * Fy
    else:
        # E3-3: Fcr = 0.877 × Fe
        Fcr = 0.877 * Fe

    res.Fcr = Fcr
    res.Pn = Fcr * A
    res.phi_Pn = PHI_C * res.Pn
    res.Pn_over_Omega = res.Pn / OMEGA_C
    res.ok = True
    return res


# ===========================================================================
# Chapter F — Flexure
# ===========================================================================

@dataclass
class FlexureResult:
    ok: bool
    reason: str = ""
    Mn: float = 0.0         # kip-in
    phi_Mn: float = 0.0     # kip-in (LRFD)
    Mn_over_Omega: float = 0.0
    phi_Mn_kip_ft: float = 0.0
    Mp: float = 0.0
    Lp: float = 0.0         # in
    Lr: float = 0.0         # in
    ltb_zone: str = ""
    flange_slenderness: str = ""  # compact/noncompact/slender
    web_slenderness: str = ""


def _w_shape_flexure(
    sec: WShape,
    Lb: float,   # in
    Cb: float,
    E: float,
    Fy: float,
) -> FlexureResult:
    """AISC F2/F3 — doubly-symmetric compact/noncompact W-shape, strong axis."""
    res = FlexureResult(ok=False)

    # --- Compactness limits Table B4.1b ---
    lam_pf = 0.38 * math.sqrt(E / Fy)   # flange compact
    lam_rf = 1.00 * math.sqrt(E / Fy)   # flange noncompact limit
    lam_pw = 3.76 * math.sqrt(E / Fy)   # web compact
    lam_rw = 5.70 * math.sqrt(E / Fy)   # web noncompact

    lam_f = sec.bf_2tf
    lam_w = sec.h_tw

    if lam_f <= lam_pf:
        res.flange_slenderness = "compact"
    elif lam_f <= lam_rf:
        res.flange_slenderness = "noncompact"
    else:
        res.flange_slenderness = "slender"

    if lam_w <= lam_pw:
        res.web_slenderness = "compact"
    elif lam_w <= lam_rw:
        res.web_slenderness = "noncompact"
    else:
        res.web_slenderness = "slender"

    Mp = Fy * sec.Zx
    res.Mp = Mp

    # --- LTB limits (F2-5, F2-6) ---
    c = 1.0  # doubly-symmetric
    Lp = 1.76 * sec.ry * math.sqrt(E / Fy)
    res.Lp = Lp

    rts = sec.rts
    Lr = 1.95 * rts * (E / (0.7 * Fy)) * math.sqrt(
        sec.J * c / (sec.Sx * sec.ho) + math.sqrt(
            (sec.J * c / (sec.Sx * sec.ho)) ** 2 + 6.76 * (0.7 * Fy / E) ** 2
        )
    )
    res.Lr = Lr

    # --- LTB capacity (F2) ---
    if Lb <= Lp:
        res.ltb_zone = "plastic"
        Mn_ltb = Mp
    elif Lb <= Lr:
        res.ltb_zone = "inelastic"
        Mn_ltb = Cb * (Mp - (Mp - 0.7 * Fy * sec.Sx) * (Lb - Lp) / (Lr - Lp))
        Mn_ltb = min(Mn_ltb, Mp)
    else:
        res.ltb_zone = "elastic"
        Lb_rts = Lb / rts
        Fcr = (Cb * math.pi ** 2 * E / Lb_rts ** 2) * math.sqrt(
            1.0 + 0.078 * sec.J * c / (sec.Sx * sec.ho) * Lb_rts ** 2
        )
        Mn_ltb = min(Fcr * sec.Sx, Mp)

    # --- Flange local buckling (F3) for noncompact/slender flange ---
    if res.flange_slenderness == "compact":
        Mn_flb = Mp
    elif res.flange_slenderness == "noncompact":
        # F3-1
        Mn_flb = Mp - (Mp - 0.7 * Fy * sec.Sx) * (lam_f - lam_pf) / (lam_rf - lam_pf)
    else:
        # F3-2 — slender flange; simplified (kc per F3-2 ~ 0.35 to 0.76)
        kc = max(0.35, min(4.0 / math.sqrt(lam_w), 0.76))
        Mn_flb = 0.9 * E * kc * sec.Sx / lam_f ** 2

    # Mn = min of LTB and FLB
    Mn = min(Mn_ltb, Mn_flb, Mp)

    res.Mn = Mn
    res.phi_Mn = PHI_B * Mn
    res.Mn_over_Omega = Mn / OMEGA_B
    res.phi_Mn_kip_ft = res.phi_Mn / 12.0
    res.ok = True
    return res


def _channel_flexure(
    sec: CChannel,
    Lb: float,
    Cb: float,
    E: float,
    Fy: float,
) -> FlexureResult:
    """AISC F6 — channel (C-shape) strong-axis flexure (simplified)."""
    res = FlexureResult(ok=False)

    Mp = Fy * sec.Zx
    res.Mp = Mp

    # Compactness
    lam_pf = 0.38 * math.sqrt(E / Fy)
    lam_rf = 1.00 * math.sqrt(E / Fy)
    lam_f = sec.bf_tf  # for channels: b/t = bf/tf
    res.flange_slenderness = (
        "compact" if lam_f <= lam_pf else
        "noncompact" if lam_f <= lam_rf else "slender"
    )

    # LTB: for channels use simplified Lp/Lr similar to W but with c factor
    # AISC F6 uses the same Lp and Lr formulas as F2 with c per F2-8b
    # c = (ho/2) × sqrt(Iy/Cw)  for channels (F2-8b)
    if sec.Cw > 0 and sec.Iy > 0 and sec.ho > 0:
        c = sec.ho / 2.0 * math.sqrt(sec.Iy / sec.Cw)
    else:
        c = 1.0

    Lp = 1.76 * sec.ry * math.sqrt(E / Fy)
    res.Lp = Lp

    rts_c = math.sqrt(math.sqrt(sec.Iy * sec.Cw) / sec.Sx) if sec.Cw > 0 else sec.ry
    Lr = 1.95 * rts_c * (E / (0.7 * Fy)) * math.sqrt(
        sec.J * c / (sec.Sx * sec.ho) + math.sqrt(
            (sec.J * c / (sec.Sx * sec.ho)) ** 2 + 6.76 * (0.7 * Fy / E) ** 2
        )
    )
    res.Lr = Lr

    if Lb <= Lp:
        res.ltb_zone = "plastic"
        Mn = Mp
    elif Lb <= Lr:
        res.ltb_zone = "inelastic"
        Mn = Cb * (Mp - (Mp - 0.7 * Fy * sec.Sx) * (Lb - Lp) / (Lr - Lp))
        Mn = min(Mn, Mp)
    else:
        res.ltb_zone = "elastic"
        Lb_rts = Lb / rts_c
        Fcr = (Cb * math.pi ** 2 * E / Lb_rts ** 2) * math.sqrt(
            1.0 + 0.078 * sec.J * c / (sec.Sx * sec.ho) * Lb_rts ** 2
        )
        Mn = min(Fcr * sec.Sx, Mp)

    res.Mn = Mn
    res.phi_Mn = PHI_B * Mn
    res.Mn_over_Omega = Mn / OMEGA_B
    res.phi_Mn_kip_ft = res.phi_Mn / 12.0
    res.ok = True
    return res


def _hss_rect_flexure(
    sec: HSSRect,
    Lb: float,
    Cb: float,
    E: float,
    Fy: float,
) -> FlexureResult:
    """AISC F7 — rectangular HSS flexure."""
    res = FlexureResult(ok=False)

    # F7 — compactness limits
    lam_p_flange = 1.12 * math.sqrt(E / Fy)   # top/bottom flange (compression)
    lam_r_flange = 1.40 * math.sqrt(E / Fy)
    lam_p_web    = 2.42 * math.sqrt(E / Fy)
    lam_r_web    = 5.70 * math.sqrt(E / Fy)

    b_t  = sec.b_t   # width/tdes for top flange
    h_t  = sec.h_t   # depth/tdes for web

    res.flange_slenderness = (
        "compact" if b_t <= lam_p_flange else
        "noncompact" if b_t <= lam_r_flange else "slender"
    )
    res.web_slenderness = (
        "compact" if h_t <= lam_p_web else
        "noncompact" if h_t <= lam_r_web else "slender"
    )

    Mp = min(Fy * sec.Zx, 1.6 * Fy * sec.Sx)
    res.Mp = Mp

    # LTB for rectangular HSS — F7.4 simplified: Lp = 0.13 E ry J/(Mp), Lr = 2 E ry J/(0.7 Fy Sx)
    # Per AISC F7-4/5 with J ≈ 2*tdes*(H-tdes)^2*(B-tdes)^2 / (H+B-2*tdes) (thin-wall approx):
    ry = sec.ry
    Lp = 0.13 * E * ry * sec.J / Mp
    Lr = 2.0 * E * ry * sec.J / (0.7 * Fy * sec.Sx)
    res.Lp = Lp * 12.0  # convert ft to in if in ft? No — these are already in inches
    # Actually F7-4/5: Lp and Lr come out in inches if E, ry, J, Mp, Sx are in inch units
    res.Lp = Lp
    res.Lr = Lr

    if Lb <= Lp:
        res.ltb_zone = "plastic"
        Mn_ltb = Mp
    elif Lb <= Lr:
        res.ltb_zone = "inelastic"
        Mn_ltb = Cb * (Mp - (Mp - 0.7 * Fy * sec.Sx) * (Lb - Lp) / (Lr - Lp))
        Mn_ltb = min(Mn_ltb, Mp)
    else:
        res.ltb_zone = "elastic"
        Fcr = Cb * 2.0 * E * ry * sec.J / (Lb * sec.Sx)
        Mn_ltb = min(Fcr * sec.Sx, Mp)

    # Flange local buckling (F7.2)
    if res.flange_slenderness == "compact":
        Mn_flb = Mp
    elif res.flange_slenderness == "noncompact":
        Mn_flb = Mp - (Mp - Fy * sec.Sx) * (3.57 * b_t * math.sqrt(Fy / E) - 4.0)
        Mn_flb = min(Mn_flb, Mp)
    else:
        # F7-7 — slender compression flange
        be = 1.92 * sec.tdes * math.sqrt(E / Fy) * (
            1.0 - 0.34 / (b_t * math.sqrt(Fy / E))
        )
        be = min(be, sec.B - 3.0 * sec.tdes)
        # Effective Seff ≈ reduce Sx by lost area contribution (simplified)
        delta_A = (sec.B - 3.0 * sec.tdes - be) * sec.tdes
        y_c = sec.H / 2.0
        Seff = sec.Sx - delta_A * y_c / (sec.H / 2.0)
        Mn_flb = Fy * max(Seff, sec.Sx * 0.5)

    Mn = min(Mn_ltb, Mn_flb, Mp)
    res.Mn = Mn
    res.phi_Mn = PHI_B * Mn
    res.Mn_over_Omega = Mn / OMEGA_B
    res.phi_Mn_kip_ft = res.phi_Mn / 12.0
    res.ok = True
    return res


def _hss_round_or_pipe_flexure(
    sec,   # HSSRound | Pipe
    E: float,
    Fy: float,
) -> FlexureResult:
    """AISC F8 — round HSS / pipe flexure. LTB does not apply for closed sections."""
    res = FlexureResult(ok=False)
    D_t = sec.D_t

    Mp = Fy * sec.Zx
    res.Mp = Mp
    res.ltb_zone = "N/A"
    res.Lp = 0.0
    res.Lr = 0.0

    # F8.2 — local buckling limits
    lam1 = 0.07 * E / Fy    # compact
    lam2 = 0.31 * E / Fy    # noncompact limit

    if D_t <= lam1:
        res.flange_slenderness = "compact"
        Mn = Mp
    elif D_t <= lam2:
        res.flange_slenderness = "noncompact"
        Mn = (0.021 * E / D_t + Fy) * sec.Sx
        Mn = min(Mn, Mp)
    else:
        res.flange_slenderness = "slender"
        Fcr = 0.33 * E / D_t
        Mn = min(Fcr * sec.Sx, Mp)

    res.Mn = Mn
    res.phi_Mn = PHI_B * Mn
    res.Mn_over_Omega = Mn / OMEGA_B
    res.phi_Mn_kip_ft = res.phi_Mn / 12.0
    res.ok = True
    return res


def _angle_flexure(
    sec: Angle,
    Lb: float,
    Cb: float,
    E: float,
    Fy: float,
) -> FlexureResult:
    """
    AISC F10 — single-angle flexure (major geometric axis, bending causing
    compression in long leg tip).

    Simplified: LTB per F10-2 using My = Fy × Sx (elastic limit), with
    local buckling per F10.3.  Does not handle biaxial / skewed bending.
    """
    res = FlexureResult(ok=False)

    My = Fy * sec.Sx   # elastic moment
    res.Mp = min(1.5 * My, Fy * sec.Zx)
    Mp = res.Mp

    # F10.3 — local buckling
    lam_r = 0.54 * math.sqrt(E / Fy)
    b_t = sec.b_t

    if b_t <= lam_r:
        res.flange_slenderness = "compact"
        Mn_lb = Mp
    else:
        # F10-6 / F10-7 slender leg
        res.flange_slenderness = "slender"
        Fcr_lb = 0.71 * E / b_t ** 2
        Mn_lb = min(Fcr_lb * sec.Sx, My)

    # F10.2 — LTB
    # Me = minor-axis bending elastic LTB — use F10-3/4 with β factors (simplified)
    # For equal-leg angle: βw = 0  →  Me = 0.46 Cb E t² Lb / L per AISC User Note
    # Using simplified F10-4 form for equal leg:
    ry = sec.ry
    Lp = 1.76 * ry * math.sqrt(E / Fy)
    res.Lp = Lp
    Lr = 1.76 * ry * math.sqrt(E / (0.7 * Fy))  # approximate Lr ~ Lp * sqrt(1/0.7)
    res.Lr = Lr

    t = sec.t
    b_leg = max(sec.leg_a, sec.leg_b)
    # Me per F10-3 (for major-axis bending, equal-leg, conservative βw=0):
    Me = 0.66 * Cb * E * b_leg * t ** 3 / Lb if Lb > 0 else 1e12

    if Me >= 1.5 * My:
        res.ltb_zone = "plastic"
        Mn_ltb = Mp
    elif Me >= My:
        res.ltb_zone = "inelastic"
        Mn_ltb = (1.92 - 1.17 * math.sqrt(My / Me)) * My
        Mn_ltb = min(Mn_ltb, 1.5 * My)
    else:
        res.ltb_zone = "elastic"
        Mn_ltb = 0.92 * Me

    Mn = min(Mn_ltb, Mn_lb)
    res.Mn = Mn
    res.phi_Mn = PHI_B * Mn
    res.Mn_over_Omega = Mn / OMEGA_B
    res.phi_Mn_kip_ft = res.phi_Mn / 12.0
    res.ok = True
    return res


def aisc_flexure(
    section,
    Lb_ft: float = 0.0,
    *,
    Cb: float = 1.0,
    E: float = E_STEEL,
    Fy: float = 50.0,
    axis: str = "x",   # strong axis; weak axis NYI for W (returns Mpy)
) -> FlexureResult:
    """
    AISC 360-22 Chapter F flexure capacity, dispatched by section type.

    Parameters
    ----------
    section
        Any supported section dataclass or string designation for a W-shape.
    Lb_ft : float
        Laterally unbraced length (ft). For closed sections (HSS_round, Pipe)
        this parameter is ignored (LTB does not govern).
    Cb : float
        LTB modification factor (1.0 = conservative).
    axis : str
        'x' = strong axis (default). 'y' = weak axis for W-shape returns Mpy.

    Returns
    -------
    FlexureResult
    """
    if isinstance(section, str):
        # Assume W-shape by default
        section = w_shape(section)

    Lb = Lb_ft * 12.0  # ft → in

    if isinstance(section, WShape):
        if axis == "y":
            # F6 weak axis for W: no LTB; Mn = min(Mp_y, ...) = Fy*Zy ≤ 1.6*Fy*Sy
            Mp_y = min(Fy * section.Zy, 1.6 * Fy * section.Sy)
            res = FlexureResult(ok=True, Mn=Mp_y, ltb_zone="N/A",
                                flange_slenderness="compact")
            res.Mp = Mp_y
            res.phi_Mn = PHI_B * Mp_y
            res.Mn_over_Omega = Mp_y / OMEGA_B
            res.phi_Mn_kip_ft = res.phi_Mn / 12.0
            return res
        return _w_shape_flexure(section, Lb, Cb, E, Fy)

    if isinstance(section, CChannel):
        return _channel_flexure(section, Lb, Cb, E, Fy)

    if isinstance(section, HSSRect):
        return _hss_rect_flexure(section, Lb, Cb, E, Fy)

    if isinstance(section, (HSSRound, Pipe)):
        return _hss_round_or_pipe_flexure(section, E, Fy)

    if isinstance(section, Angle):
        return _angle_flexure(section, Lb, Cb, E, Fy)

    res = FlexureResult(ok=False)
    res.reason = f"Unsupported section type: {type(section)}"
    return res


# ===========================================================================
# Chapter H — Combined Loading
# ===========================================================================

@dataclass
class CombinedResult:
    ok: bool
    reason: str = ""
    Pn_avail: float = 0.0    # φcPn (LRFD) kips
    Mnx_avail: float = 0.0   # φbMnx (LRFD) kip-in
    Mny_avail: float = 0.0   # φbMny (LRFD) kip-in
    ratio_H1: float = 0.0
    ratio_H1_case: str = ""  # 'H1-1a' or 'H1-1b'
    governing: str = ""      # 'compression' | 'flexure_x' | 'flexure_y' | 'combined'
    interaction_ok: bool = False


@dataclass
class DemandSet:
    """Applied factored demands (LRFD) for a member."""
    Pu: float = 0.0   # Factored axial compression demand (kips); tension positive → set 0
    Mux: float = 0.0  # Factored moment about strong axis (kip-in)
    Muy: float = 0.0  # Factored moment about weak axis (kip-in)


def aisc_combined(
    section,
    demand: DemandSet,
    Lc: float,
    Lcy: float = 0.0,
    Lb_ft: float = 0.0,
    *,
    Cb: float = 1.0,
    E: float = E_STEEL,
    Fy: float = 50.0,
) -> CombinedResult:
    """
    AISC 360-22 Chapter H combined axial + flexure interaction.

    Runs Chapter E compression, Chapter F strong-axis flexure, Chapter F
    weak-axis flexure, then evaluates H1-1a/H1-1b interaction.

    Parameters
    ----------
    section
        Any supported section.
    demand : DemandSet
        LRFD factored demands.
    Lc, Lcy : float
        Effective column lengths KL (ft), strong and weak axis.
    Lb_ft : float
        Unbraced length for LTB (ft).
    Cb : float
        LTB modification factor.

    Returns
    -------
    CombinedResult
    """
    res = CombinedResult(ok=False)

    comp_res = aisc_compression(section, Lc, Lcy, E=E, Fy=Fy)
    if not comp_res.ok:
        res.reason = f"Compression check failed: {comp_res.reason}"
        return res

    flex_x = aisc_flexure(section, Lb_ft, Cb=Cb, E=E, Fy=Fy, axis="x")
    if not flex_x.ok:
        res.reason = f"Strong-axis flexure failed: {flex_x.reason}"
        return res

    flex_y = aisc_flexure(section, Lb_ft, Cb=Cb, E=E, Fy=Fy, axis="y")
    if not flex_y.ok:
        res.reason = f"Weak-axis flexure failed: {flex_y.reason}"
        return res

    Pc = comp_res.phi_Pn
    Mcx = flex_x.phi_Mn
    Mcy = flex_y.phi_Mn

    res.Pn_avail = Pc
    res.Mnx_avail = Mcx
    res.Mny_avail = Mcy

    Pu = demand.Pu
    Mux = demand.Mux
    Muy = demand.Muy

    if Pc <= 0 or Mcx <= 0:
        res.reason = "Zero capacity — check section inputs."
        return res

    Mr_ratio = (Mux / Mcx if Mcx > 0 else 0.0) + (Muy / Mcy if Mcy > 0 else 0.0)

    if Pu / Pc >= 0.2:
        # H1-1a
        ratio = Pu / Pc + (8.0 / 9.0) * Mr_ratio
        res.ratio_H1_case = "H1-1a"
    else:
        # H1-1b
        ratio = Pu / (2.0 * Pc) + Mr_ratio
        res.ratio_H1_case = "H1-1b"

    res.ratio_H1 = ratio
    res.interaction_ok = ratio <= 1.0

    # Governing action
    Pu_ratio = Pu / Pc
    if Pu_ratio > abs(Mux / Mcx if Mcx > 0 else 0) and Pu_ratio > abs(Muy / Mcy if Mcy > 0 else 0):
        res.governing = "compression"
    elif abs(Mux / Mcx if Mcx > 0 else 0) >= abs(Muy / Mcy if Mcy > 0 else 0):
        res.governing = "flexure_x"
    else:
        res.governing = "flexure_y"

    res.ok = True
    return res


# ===========================================================================
# Full member-design check
# ===========================================================================

@dataclass
class MemberCheckResult:
    ok: bool
    reason: str = ""
    Pn_avail: float = 0.0      # φcPn kips
    Mnx_avail: float = 0.0     # φbMnx kip-in
    Mny_avail: float = 0.0     # φbMny kip-in
    ratio_H1: float = 0.0
    interaction_ok: bool = False
    governing: str = ""        # which check governs
    compression: Optional[CompressionResult] = None
    flexure_x: Optional[FlexureResult] = None
    flexure_y: Optional[FlexureResult] = None
    combined: Optional[CombinedResult] = None


def aisc_member_check(
    section,
    demand: DemandSet,
    *,
    Lc: float = 0.0,
    Lcy: float = 0.0,
    Lb_ft: float = 0.0,
    Cb: float = 1.0,
    E: float = E_STEEL,
    Fy: float = 50.0,
) -> MemberCheckResult:
    """
    AISC 360-22 full member design check: Chapters E + F + H.

    Parameters
    ----------
    section
        Any supported section dataclass or string W-shape designation.
    demand : DemandSet
        LRFD factored demands (Pu, Mux, Muy).
    Lc, Lcy : float
        Effective column lengths (ft) for strong/weak axis.
    Lb_ft : float
        Laterally unbraced length for LTB (ft).
    Cb : float
        LTB modification factor.
    E, Fy : float
        Material properties (ksi).

    Returns
    -------
    MemberCheckResult
        Includes availability of Pn, Mnx, Mny; H1 ratio; and all sub-results.
    """
    if isinstance(section, str):
        section = w_shape(section)

    res = MemberCheckResult(ok=False)

    # Chapter E
    comp = aisc_compression(section, Lc, Lcy, E=E, Fy=Fy)
    res.compression = comp
    if not comp.ok:
        res.reason = f"Compression: {comp.reason}"
        return res

    # Chapter F strong axis
    fx = aisc_flexure(section, Lb_ft, Cb=Cb, E=E, Fy=Fy, axis="x")
    res.flexure_x = fx
    if not fx.ok:
        res.reason = f"Strong-axis flexure: {fx.reason}"
        return res

    # Chapter F weak axis
    fy_res = aisc_flexure(section, Lb_ft, Cb=Cb, E=E, Fy=Fy, axis="y")
    res.flexure_y = fy_res
    if not fy_res.ok:
        res.reason = f"Weak-axis flexure: {fy_res.reason}"
        return res

    # Chapter H
    comb = aisc_combined(
        section, demand, Lc, Lcy, Lb_ft,
        Cb=Cb, E=E, Fy=Fy,
    )
    res.combined = comb
    if not comb.ok:
        res.reason = f"Combined: {comb.reason}"
        return res

    res.Pn_avail = comb.Pn_avail
    res.Mnx_avail = comb.Mnx_avail
    res.Mny_avail = comb.Mny_avail
    res.ratio_H1 = comb.ratio_H1
    res.interaction_ok = comb.interaction_ok
    res.governing = comb.governing
    res.ok = True
    return res


# ===========================================================================
# LLM tool wrappers
# ===========================================================================

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_structural._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx

import json as _json


# ---------------------------------------------------------------------------
# aisc_compression
# ---------------------------------------------------------------------------

aisc_compression_spec = ToolSpec(
    name="aisc_compression",
    description=(
        "AISC 360-22 Chapter E — axial compression capacity for W, C, HSS, pipe, "
        "or angle sections. Returns Fcr, φcPn (LRFD), Pn/Ωc (ASD)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "designation": {"type": "string", "description": "AISC designation e.g. 'W14X90', 'HSS6X6X3/8'"},
            "section_type": {"type": "string", "description": "One of: W, C, HSS_rect, HSS_round, Pipe, Angle"},
            "Lc_ft": {"type": "number", "description": "Effective length KL about strong axis (ft)"},
            "Lcy_ft": {"type": "number", "description": "Effective length about weak axis (ft); 0 = same as Lc"},
            "Fy": {"type": "number", "description": "Yield strength (ksi), default 50"},
            "E": {"type": "number", "description": "Elastic modulus (ksi), default 29000"},
        },
        "required": ["designation", "section_type", "Lc_ft"],
    },
)


def _lookup_section(designation: str, section_type: str):
    stype = section_type.lower()
    if stype == "w":
        return w_shape(designation)
    elif stype == "c":
        return c_channel(designation)
    elif stype == "hss_rect":
        return hss_rect(designation)
    elif stype == "hss_round":
        return hss_round(designation)
    elif stype in ("pipe",):
        return pipe(designation)
    elif stype == "angle":
        return angle(designation)
    else:
        raise ValueError(f"Unknown section_type '{section_type}'. Use W/C/HSS_rect/HSS_round/Pipe/Angle.")


@register(aisc_compression_spec, write=False)
async def run_aisc_compression(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = _json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    try:
        sec = _lookup_section(a["designation"], a["section_type"])
        res = aisc_compression(
            sec,
            Lc=float(a["Lc_ft"]),
            Lcy=float(a.get("Lcy_ft", 0.0)),
            Fy=float(a.get("Fy", 50.0)),
            E=float(a.get("E", E_STEEL)),
        )
    except (KeyError, ValueError) as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(str(exc), "INTERNAL")
    if not res.ok:
        return err_payload(res.reason, "DESIGN_FAIL")
    return ok_payload({
        "ok": True,
        "designation": a["designation"],
        "KL_r": round(res.KL_r, 2),
        "Fe_ksi": round(res.Fe, 2),
        "Fcr_ksi": round(res.Fcr, 2),
        "Q": round(res.Q, 4),
        "Pn_kips": round(res.Pn, 2),
        "phi_Pn_kips": round(res.phi_Pn, 2),
        "Pn_over_Omega_kips": round(res.Pn_over_Omega, 2),
        "governing_axis": res.governing_axis,
    })


# ---------------------------------------------------------------------------
# aisc_flexure
# ---------------------------------------------------------------------------

aisc_flexure_spec = ToolSpec(
    name="aisc_flexure",
    description=(
        "AISC 360-22 Chapter F — flexural capacity for W, C, HSS (rect/round), "
        "pipe, or angle sections. Returns Mn, φbMn (LRFD), Mn/Ωb (ASD)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "designation": {"type": "string"},
            "section_type": {"type": "string", "description": "W/C/HSS_rect/HSS_round/Pipe/Angle"},
            "Lb_ft": {"type": "number", "description": "Unbraced length (ft)"},
            "Cb": {"type": "number", "description": "LTB factor, default 1.0"},
            "Fy": {"type": "number", "description": "Yield strength (ksi), default 50"},
            "axis": {"type": "string", "description": "'x' or 'y', default 'x'"},
        },
        "required": ["designation", "section_type", "Lb_ft"],
    },
)


@register(aisc_flexure_spec, write=False)
async def run_aisc_flexure(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = _json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    try:
        sec = _lookup_section(a["designation"], a["section_type"])
        res = aisc_flexure(
            sec,
            Lb_ft=float(a["Lb_ft"]),
            Cb=float(a.get("Cb", 1.0)),
            Fy=float(a.get("Fy", 50.0)),
            axis=a.get("axis", "x"),
        )
    except (KeyError, ValueError) as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(str(exc), "INTERNAL")
    if not res.ok:
        return err_payload(res.reason, "DESIGN_FAIL")
    return ok_payload({
        "ok": True,
        "designation": a["designation"],
        "Mn_kip_in": round(res.Mn, 2),
        "phi_Mn_kip_ft": round(res.phi_Mn_kip_ft, 2),
        "Mn_over_Omega_kip_ft": round(res.Mn_over_Omega / 12.0, 2),
        "Mp_kip_in": round(res.Mp, 2),
        "Lp_ft": round(res.Lp / 12.0, 3),
        "Lr_ft": round(res.Lr / 12.0, 3),
        "ltb_zone": res.ltb_zone,
        "flange_slenderness": res.flange_slenderness,
        "web_slenderness": res.web_slenderness,
    })


# ---------------------------------------------------------------------------
# aisc_combined
# ---------------------------------------------------------------------------

aisc_combined_spec = ToolSpec(
    name="aisc_combined",
    description=(
        "AISC 360-22 Chapter H — combined axial + flexure interaction ratio (H1-1a/b). "
        "Pass LRFD demands: Pu (kips), Mux/Muy (kip-in)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "designation": {"type": "string"},
            "section_type": {"type": "string"},
            "Lc_ft": {"type": "number", "description": "Effective column length, strong axis (ft)"},
            "Lcy_ft": {"type": "number"},
            "Lb_ft": {"type": "number", "description": "Unbraced length for LTB (ft)"},
            "Pu": {"type": "number", "description": "Factored axial compression (kips)"},
            "Mux": {"type": "number", "description": "Factored strong-axis moment (kip-in)"},
            "Muy": {"type": "number", "description": "Factored weak-axis moment (kip-in)"},
            "Cb": {"type": "number", "description": "LTB factor"},
            "Fy": {"type": "number"},
        },
        "required": ["designation", "section_type", "Lc_ft", "Lb_ft", "Pu", "Mux"],
    },
)


@register(aisc_combined_spec, write=False)
async def run_aisc_combined(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = _json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    try:
        sec = _lookup_section(a["designation"], a["section_type"])
        demand = DemandSet(
            Pu=float(a.get("Pu", 0.0)),
            Mux=float(a.get("Mux", 0.0)),
            Muy=float(a.get("Muy", 0.0)),
        )
        res = aisc_combined(
            sec, demand,
            Lc=float(a["Lc_ft"]),
            Lcy=float(a.get("Lcy_ft", 0.0)),
            Lb_ft=float(a["Lb_ft"]),
            Cb=float(a.get("Cb", 1.0)),
            Fy=float(a.get("Fy", 50.0)),
        )
    except (KeyError, ValueError) as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(str(exc), "INTERNAL")
    if not res.ok:
        return err_payload(res.reason, "DESIGN_FAIL")
    return ok_payload({
        "ok": True,
        "phi_Pn_kips": round(res.Pn_avail, 2),
        "phi_Mnx_kip_ft": round(res.Mnx_avail / 12.0, 2),
        "phi_Mny_kip_ft": round(res.Mny_avail / 12.0, 2),
        "ratio_H1": round(res.ratio_H1, 4),
        "H1_case": res.ratio_H1_case,
        "interaction_ok": res.interaction_ok,
        "governing": res.governing,
    })


# ---------------------------------------------------------------------------
# aisc_member_check
# ---------------------------------------------------------------------------

aisc_member_check_spec = ToolSpec(
    name="aisc_member_check",
    description=(
        "AISC 360-22 full member design (E + F + H): given section and LRFD demands, "
        "returns compression capacity, strong/weak flexure capacity, H1 interaction ratio."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "designation": {"type": "string"},
            "section_type": {"type": "string"},
            "Lc_ft": {"type": "number"},
            "Lcy_ft": {"type": "number"},
            "Lb_ft": {"type": "number"},
            "Pu": {"type": "number"},
            "Mux_kip_ft": {"type": "number", "description": "Strong-axis moment demand (kip-ft)"},
            "Muy_kip_ft": {"type": "number", "description": "Weak-axis moment demand (kip-ft)"},
            "Cb": {"type": "number"},
            "Fy": {"type": "number"},
        },
        "required": ["designation", "section_type", "Lc_ft", "Lb_ft"],
    },
)


@register(aisc_member_check_spec, write=False)
async def run_aisc_member_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = _json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")
    try:
        sec = _lookup_section(a["designation"], a["section_type"])
        demand = DemandSet(
            Pu=float(a.get("Pu", 0.0)),
            Mux=float(a.get("Mux_kip_ft", 0.0)) * 12.0,
            Muy=float(a.get("Muy_kip_ft", 0.0)) * 12.0,
        )
        res = aisc_member_check(
            sec, demand,
            Lc=float(a["Lc_ft"]),
            Lcy=float(a.get("Lcy_ft", 0.0)),
            Lb_ft=float(a["Lb_ft"]),
            Cb=float(a.get("Cb", 1.0)),
            Fy=float(a.get("Fy", 50.0)),
        )
    except (KeyError, ValueError) as exc:
        return err_payload(str(exc), "BAD_ARGS")
    except Exception as exc:
        return err_payload(str(exc), "INTERNAL")
    if not res.ok:
        return err_payload(res.reason, "DESIGN_FAIL")
    return ok_payload({
        "ok": True,
        "designation": a["designation"],
        "phi_Pn_kips": round(res.Pn_avail, 2),
        "phi_Mnx_kip_ft": round(res.Mnx_avail / 12.0, 2),
        "phi_Mny_kip_ft": round(res.Mny_avail / 12.0, 2),
        "ratio_H1": round(res.ratio_H1, 4),
        "interaction_ok": res.interaction_ok,
        "governing": res.governing,
        "KL_r": round(res.compression.KL_r, 2),
        "Fcr_ksi": round(res.compression.Fcr, 2),
        "ltb_zone": res.flexure_x.ltb_zone,
        "flange_slenderness": res.flexure_x.flange_slenderness,
    })
