"""
kerf_marine.hydrostatics — Displacement and hydrostatic properties.

Computes the classical hydrostatic table from a hull offsets table:

  displacement  Δ     = ρ · g · ∇  (tonnes, with g absorbed)
  volume        ∇     = L·B·T for box  (m³)
  LCB                 = longitudinal centre of buoyancy (m from aft)
  KB                  = vertical centre of buoyancy above keel (m)
  BM                  = metacentric radius  = I_L / ∇  (m)
                        (I_L = second moment of waterplane area about
                         transverse axis through B)
  GM                  = KM − KG  (m, positive = stable)
  TPC                 = tonnes per centimetre immersion
  MCT1cm             = moment to change trim 1 cm  (t·m/cm)

Box-barge analytic checks (DoD oracles)
----------------------------------------
  ∇           = L·B·T                      (exact)
  KB          = T/2                         (exact)
  BM          = B² / (12·T)                (exact, transverse)
  TPC         = ρ · A_wp / 100             (A_wp = L·B)
  MCT1cm      = ρ · A_wp · GML / (100·L)  (GML ≈ BML for small KG)

All lengths in metres, mass in metric tonnes (1 tonne = 1000 kg).
Sea-water density default: 1.025 t/m³.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from kerf_marine.sections import (
    OffsetTable,
    SectionSlice,
    integrate_sections,
    _trapz,
    _simpson,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RHO_SW = 1.025   # sea-water density, t/m³
RHO_FW = 1.000   # fresh-water density, t/m³


# ---------------------------------------------------------------------------
# Hydrostatic result container
# ---------------------------------------------------------------------------

@dataclass
class HydrostaticTable:
    """
    Hydrostatic properties at one draft.

    All in SI / naval-architecture conventional units.
    """
    draft: float              # m — waterline draft
    volume: float             # m³ — displacement volume
    displacement: float       # t — displacement mass (= rho * volume)
    lcb: float                # m — LCB from aft perpendicular
    kb: float                 # m — KB above keel
    bm_transverse: float      # m — transverse metacentric radius BM
    bm_longitudinal: float    # m — longitudinal metacentric radius BML
    km: float                 # m — KM = KB + BM_transverse
    waterplane_area: float    # m² — area of waterplane
    tpc: float                # t/cm — tonnes per centimetre immersion
    mct1cm: float             # t·m/cm — moment to change trim 1 cm
    lcf: float                # m — longitudinal centre of flotation from aft
    rho: float                # t/m³ — water density used

    def as_dict(self) -> dict:
        return {
            "draft_m": round(self.draft, 4),
            "volume_m3": round(self.volume, 6),
            "displacement_t": round(self.displacement, 4),
            "lcb_m": round(self.lcb, 4),
            "kb_m": round(self.kb, 4),
            "bm_transverse_m": round(self.bm_transverse, 6),
            "bm_longitudinal_m": round(self.bm_longitudinal, 6),
            "km_m": round(self.km, 4),
            "waterplane_area_m2": round(self.waterplane_area, 4),
            "tpc": round(self.tpc, 4),
            "mct1cm": round(self.mct1cm, 4),
            "lcf_m": round(self.lcf, 4),
            "rho_t_m3": self.rho,
        }


# ---------------------------------------------------------------------------
# Core hydrostatics computation
# ---------------------------------------------------------------------------

def compute_hydrostatics(
    table: OffsetTable,
    draft: float,
    *,
    rho: float = RHO_SW,
    kg: float = 0.0,
    method: str = "simpson",
) -> HydrostaticTable:
    """
    Compute the full hydrostatic table for a hull at a given draft.

    Parameters
    ----------
    table  : OffsetTable with rows up to (or beyond) draft
    draft  : waterline draft (m)
    rho    : water density (t/m³), default 1.025 (sea water)
    kg     : vertical centre of gravity above keel (m); used for GM only
    method : integration method 'simpson' (default) or 'trapz'

    Algorithm
    ---------
    1. Clip all waterlines in the table to [0, draft].
    2. Integrate each transverse section to get area(x) and z-centroid(x).
    3. Integrate section areas along the hull length for volume and LCB / KB.
    4. Integrate waterplane half-breadths for waterplane area, I_L, LCF.
    5. Derive BM, KM, TPC, MCT1cm.

    For a box barge this reproduces the analytic DoD oracles to floating-point
    precision (no fudge factors).
    """
    integrate = _simpson if method == "simpson" else _trapz

    # ------------------------------------------------------------------
    # Step 1 — filter & clip sections to draft
    # ------------------------------------------------------------------
    from kerf_marine.sections import OffsetRow, integrate_section, SectionSlice

    # Build a clipped table: keep only rows with waterline <= draft
    clipped_rows: list[OffsetRow] = [
        r for r in table.rows if r.waterline <= draft + 1e-10
    ]
    if not clipped_rows:
        raise ValueError("No offset rows at or below the specified draft")

    clipped = OffsetTable(rows=clipped_rows)
    stations = clipped.stations()

    if len(stations) < 2:
        raise ValueError("Need at least 2 stations to integrate hull volume")

    # ------------------------------------------------------------------
    # Step 2 — integrate each transverse section
    # ------------------------------------------------------------------
    slices: list[SectionSlice] = []
    for stn in stations:
        zs, ys = clipped.half_breadths_at_station(stn)
        if len(zs) < 2:
            # Degenerate section — treat as zero area
            sl = SectionSlice(
                station=stn, area=0.0, centroid_z=0.0,
                first_moment_z=0.0, second_moment_z=0.0,
                waterplane_half_breadth=0.0,
            )
        else:
            # Ensure we include the exact draft waterline
            if zs[-1] < draft - 1e-10:
                # Extrapolate last half-breadth to draft (flat extension)
                zs = zs + [draft]
                ys = ys + [ys[-1]]
            sl = integrate_section(zs, ys, method=method)
            sl.station = stn
        slices.append(sl)

    xs = [sl.station for sl in slices]
    areas = [sl.area for sl in slices]
    fm_zs = [sl.first_moment_z for sl in slices]

    # ------------------------------------------------------------------
    # Step 3 — integrate along length for volume, LCB, KB
    # ------------------------------------------------------------------
    volume = integrate(xs, areas)
    if volume <= 0.0:
        raise ValueError("Displacement volume is zero — check offset table")

    # LCB — first moment about aft (x=0): ∫ A(x)·x dx / volume
    ax = [areas[i] * xs[i] for i in range(len(xs))]
    lcb = integrate(xs, ax) / volume

    # KB — first moment about keel: ∫ fm_z(x) dx / volume
    kb = integrate(xs, fm_zs) / volume

    # ------------------------------------------------------------------
    # Step 4 — waterplane geometry for BM, waterplane area, TPC, LCF
    # ------------------------------------------------------------------
    # Half-breadth at the draft waterline at each station
    wp_halves = [sl.waterplane_half_breadth for sl in slices]
    wp_full = [2.0 * h for h in wp_halves]   # full breadths

    # Waterplane area
    waterplane_area = integrate(xs, wp_full)

    # Longitudinal centre of flotation LCF = ∫ b(x)·x dx / A_wp
    bx = [wp_full[i] * xs[i] for i in range(len(xs))]
    lcf = integrate(xs, bx) / waterplane_area if waterplane_area > 0 else 0.0

    # Transverse second moment of waterplane area about centreline:
    # I_T = ∫ (2/3) · b_half³ dx  (where b_half is the half-breadth)
    # For BM_T = I_T / ∇
    i_t_integrand = [(2.0 / 3.0) * (wp_halves[i] ** 3) for i in range(len(xs))]
    i_t = integrate(xs, i_t_integrand)
    bm_transverse = i_t / volume

    # Longitudinal second moment of waterplane area about LCF:
    # I_L = ∫ b(x)·(x - LCF)² dx  (2nd moment of a strip width b(x))
    i_l_integrand = [wp_full[i] * ((xs[i] - lcf) ** 2) for i in range(len(xs))]
    i_l = integrate(xs, i_l_integrand)
    bm_longitudinal = i_l / volume

    # ------------------------------------------------------------------
    # Step 5 — derived quantities
    # ------------------------------------------------------------------
    displacement = rho * volume
    km = kb + bm_transverse

    # TPC: mass added per 1 cm increase in draft = rho * A_wp * 0.01
    tpc = rho * waterplane_area * 0.01

    # MCT1cm: moment to change trim 1 cm
    # MCT1 = displacement * GML / (100 * L)
    # where GML = KML - KG, KML = KB + BML
    gm_l = kb + bm_longitudinal - kg
    hull_length = xs[-1] - xs[0]
    mct1cm = (displacement * gm_l) / (100.0 * hull_length) if hull_length > 0 else 0.0

    return HydrostaticTable(
        draft=draft,
        volume=volume,
        displacement=displacement,
        lcb=lcb,
        kb=kb,
        bm_transverse=bm_transverse,
        bm_longitudinal=bm_longitudinal,
        km=km,
        waterplane_area=waterplane_area,
        tpc=tpc,
        mct1cm=mct1cm,
        lcf=lcf,
        rho=rho,
    )


# ---------------------------------------------------------------------------
# Convenience: build hydrostatic table across a range of drafts
# ---------------------------------------------------------------------------

def hydrostatic_curve(
    table: OffsetTable,
    drafts: Sequence[float],
    *,
    rho: float = RHO_SW,
    kg: float = 0.0,
    method: str = "simpson",
) -> list[HydrostaticTable]:
    """
    Compute hydrostatics at multiple drafts.

    Returns a list of HydrostaticTable objects, one per draft, sorted by
    ascending draft.  Useful for plotting hydrostatic curves.
    """
    results = []
    for d in sorted(drafts):
        try:
            ht = compute_hydrostatics(table, d, rho=rho, kg=kg, method=method)
            results.append(ht)
        except ValueError:
            pass
    return results


# ---------------------------------------------------------------------------
# Box-barge analytic helper (for testing / calibration)
# ---------------------------------------------------------------------------

def box_barge_hydrostatics(
    length: float,
    beam: float,
    draft: float,
    *,
    rho: float = RHO_SW,
    kg: float = 0.0,
) -> HydrostaticTable:
    """
    Analytic hydrostatics for a rectangular box barge.

    Verifies the DoD oracles:
      ∇ = L·B·T   (displacement volume)
      KB = T/2
      BM = B²/(12T)  (transverse)

    Parameters
    ----------
    length : m — length between perpendiculars
    beam   : m — full beam
    draft  : m — even-keel draft
    rho    : t/m³ — water density
    kg     : m — KG for GM calculation
    """
    volume = length * beam * draft
    displacement = rho * volume
    kb = draft / 2.0
    bm_transverse = (beam ** 2) / (12.0 * draft)
    bm_longitudinal = (length ** 2) / (12.0 * draft)
    km = kb + bm_transverse
    waterplane_area = length * beam
    tpc = rho * waterplane_area * 0.01
    gm_l = kb + bm_longitudinal - kg
    mct1cm = (displacement * gm_l) / (100.0 * length)
    lcb = length / 2.0
    lcf = length / 2.0

    return HydrostaticTable(
        draft=draft,
        volume=volume,
        displacement=displacement,
        lcb=lcb,
        kb=kb,
        bm_transverse=bm_transverse,
        bm_longitudinal=bm_longitudinal,
        km=km,
        waterplane_area=waterplane_area,
        tpc=tpc,
        mct1cm=mct1cm,
        lcf=lcf,
        rho=rho,
    )
