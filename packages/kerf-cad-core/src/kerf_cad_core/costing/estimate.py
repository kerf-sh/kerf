"""
kerf_cad_core.costing.estimate — parametric manufacturing should-cost models.

Process models
--------------
cnc_cost          CNC machining: material + cycle time × machine-hour-rate
                  + setup amortised over batch + tooling
casting_cost      Sand / investment casting: pattern/tooling amortisation
                  + material + finishing
injection_cost    Injection moulding: mould amortisation + cycle × rate
                  + material + scrap
sheet_metal_cost  Blank material + per-bend time × rate + setup
printing_cost     FDM/SLA/SLS: machine-hour + material + post-processing
assembly_cost     Labour time × rate per station

Generic roll-up
---------------
rollup            Direct material + direct labor + machine + setup/batch
                  + tooling amortisation + overhead% + SG&A% + margin%
                  → unit price; flags negative margin or tiny-batch-dominated
batch_curve       Unit-cost vs. batch-size breakpoints
learning_curve    Wright 80% learning curve — unit cost at cumulative volume
make_vs_buy       Make vs. buy comparison with break-even batch

All functions return a plain dict:
    success → {"ok": True, ...fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "..."}

Functions NEVER raise.  Warnings issued via the "warnings" field, never
via Python warnings.warn().

Units (unless documented otherwise)
-------------------------------------
  costs   — any consistent currency unit (USD, EUR, etc.); caller's choice
  time    — hours
  mass    — kg
  volume  — cm³

References
----------
Boothroyd, Dewhurst & Knight, "Product Design for Manufacture and Assembly",
    3rd ed. (2010)
Harper, C.A. (ed.), "Electronic Packaging and Interconnection Handbook"
Wright, T.P. (1936), "Factors Affecting the Cost of Airplanes", JAS 3(4)

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_fraction(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 0 or v > 1:
        return f"{name} must be in [0, 1], got {v}"
    return None


def _ok(**kwargs) -> dict:
    d = {"ok": True, "warnings": []}
    d.update(kwargs)
    return d


# ---------------------------------------------------------------------------
# 1. CNC machining should-cost
# ---------------------------------------------------------------------------

def cnc_cost(
    material_cost: float,
    cycle_time_hr: float,
    machine_rate_per_hr: float,
    *,
    setup_time_hr: float = 0.5,
    batch_size: int = 1,
    tooling_cost: float = 0.0,
    tooling_life_parts: int = 1000,
    overhead_rate: float = 0.15,
) -> dict:
    """
    CNC machining should-cost per unit.

    Parameters
    ----------
    material_cost : float
        Raw material cost per part (any consistent currency unit). > 0.
    cycle_time_hr : float
        Machine cycle time per part (hours). > 0.
    machine_rate_per_hr : float
        All-in machine-hour rate including operator ($/hr). > 0.
    setup_time_hr : float
        Setup / changeover time per batch run (hours, default 0.5). >= 0.
    batch_size : int
        Number of parts per batch run (default 1). >= 1.
    tooling_cost : float
        Total tooling investment for this job ($/set, default 0). >= 0.
    tooling_life_parts : int
        Tooling life in parts (default 1000). >= 1.
    overhead_rate : float
        Overhead as fraction of direct machine cost (default 0.15). in [0,1].

    Returns
    -------
    dict
        ok, unit_material, unit_machine, unit_setup, unit_tooling,
        unit_overhead, unit_total_cost, warnings
    """
    err = _guard_positive("material_cost", material_cost)
    if err:
        return _err(err)
    err = _guard_positive("cycle_time_hr", cycle_time_hr)
    if err:
        return _err(err)
    err = _guard_positive("machine_rate_per_hr", machine_rate_per_hr)
    if err:
        return _err(err)
    err = _guard_nonneg("setup_time_hr", setup_time_hr)
    if err:
        return _err(err)
    if int(batch_size) < 1:
        return _err("batch_size must be >= 1")
    err = _guard_nonneg("tooling_cost", tooling_cost)
    if err:
        return _err(err)
    if int(tooling_life_parts) < 1:
        return _err("tooling_life_parts must be >= 1")
    err = _guard_fraction("overhead_rate", overhead_rate)
    if err:
        return _err(err)

    n = int(batch_size)
    unit_material = float(material_cost)
    unit_machine = float(cycle_time_hr) * float(machine_rate_per_hr)
    unit_setup = float(setup_time_hr) * float(machine_rate_per_hr) / n
    unit_tooling = float(tooling_cost) / float(tooling_life_parts)
    unit_overhead = (unit_machine + unit_setup) * float(overhead_rate)
    unit_total = unit_material + unit_machine + unit_setup + unit_tooling + unit_overhead

    warnings = []
    if unit_setup > unit_machine:
        warnings.append(
            f"setup dominates: unit_setup ({unit_setup:.4f}) > unit_machine "
            f"({unit_machine:.4f}); consider larger batch."
        )

    result = _ok(
        unit_material=unit_material,
        unit_machine=unit_machine,
        unit_setup=unit_setup,
        unit_tooling=unit_tooling,
        unit_overhead=unit_overhead,
        unit_total_cost=unit_total,
    )
    result["warnings"] = warnings
    return result


# ---------------------------------------------------------------------------
# 2. Casting should-cost (sand / investment)
# ---------------------------------------------------------------------------

def casting_cost(
    material_cost_per_kg: float,
    part_mass_kg: float,
    *,
    yield_fraction: float = 0.70,
    pattern_cost: float = 0.0,
    pattern_life_parts: int = 500,
    finishing_cost_per_part: float = 0.0,
    machine_rate_per_hr: float = 80.0,
    pour_time_hr: float = 0.05,
    batch_size: int = 1,
    overhead_rate: float = 0.20,
) -> dict:
    """
    Sand/investment casting should-cost per unit.

    Parameters
    ----------
    material_cost_per_kg : float
        Alloy cost per kg. > 0.
    part_mass_kg : float
        Net part mass (kg). > 0.
    yield_fraction : float
        Metal yield (ratio of poured mass that ends up in the part, default
        0.70 for sand casting). in (0, 1].
    pattern_cost : float
        Pattern / tooling total cost (default 0). >= 0.
    pattern_life_parts : int
        Pattern life in parts (default 500). >= 1.
    finishing_cost_per_part : float
        Finishing/cleaning/fettling per part (default 0). >= 0.
    machine_rate_per_hr : float
        Pouring/handling machine rate ($/hr, default 80). > 0.
    pour_time_hr : float
        Machine time per part including handling (hr, default 0.05). > 0.
    batch_size : int
        Parts per heat / run (default 1). >= 1.
    overhead_rate : float
        Overhead fraction on direct costs (default 0.20). in [0,1].

    Returns
    -------
    dict
        ok, unit_material, unit_pattern, unit_pour, unit_finishing,
        unit_overhead, unit_total_cost, warnings
    """
    err = _guard_positive("material_cost_per_kg", material_cost_per_kg)
    if err:
        return _err(err)
    err = _guard_positive("part_mass_kg", part_mass_kg)
    if err:
        return _err(err)
    err = _guard_positive("yield_fraction", yield_fraction)
    if err:
        return _err(err)
    if float(yield_fraction) > 1.0:
        return _err("yield_fraction must be <= 1")
    err = _guard_nonneg("pattern_cost", pattern_cost)
    if err:
        return _err(err)
    if int(pattern_life_parts) < 1:
        return _err("pattern_life_parts must be >= 1")
    err = _guard_nonneg("finishing_cost_per_part", finishing_cost_per_part)
    if err:
        return _err(err)
    err = _guard_positive("machine_rate_per_hr", machine_rate_per_hr)
    if err:
        return _err(err)
    err = _guard_positive("pour_time_hr", pour_time_hr)
    if err:
        return _err(err)
    if int(batch_size) < 1:
        return _err("batch_size must be >= 1")
    err = _guard_fraction("overhead_rate", overhead_rate)
    if err:
        return _err(err)

    poured_mass_kg = float(part_mass_kg) / float(yield_fraction)
    unit_material = poured_mass_kg * float(material_cost_per_kg)
    unit_pattern = float(pattern_cost) / float(pattern_life_parts)
    unit_pour = float(pour_time_hr) * float(machine_rate_per_hr)
    unit_finishing = float(finishing_cost_per_part)
    direct = unit_material + unit_pattern + unit_pour + unit_finishing
    unit_overhead = direct * float(overhead_rate)
    unit_total = direct + unit_overhead

    warnings = []
    if int(batch_size) < 10 and float(pattern_cost) > 0:
        warnings.append(
            f"tiny batch ({batch_size} parts) with pattern cost "
            f"{pattern_cost:.2f}; pattern amortisation is high."
        )

    result = _ok(
        poured_mass_kg=poured_mass_kg,
        unit_material=unit_material,
        unit_pattern=unit_pattern,
        unit_pour=unit_pour,
        unit_finishing=unit_finishing,
        unit_overhead=unit_overhead,
        unit_total_cost=unit_total,
    )
    result["warnings"] = warnings
    return result


# ---------------------------------------------------------------------------
# 3. Injection moulding should-cost
# ---------------------------------------------------------------------------

def injection_cost(
    material_cost_per_kg: float,
    shot_mass_kg: float,
    *,
    scrap_rate: float = 0.03,
    cycle_time_hr: float = 0.005,
    machine_rate_per_hr: float = 120.0,
    mould_cost: float = 0.0,
    mould_life_shots: int = 100_000,
    cavities: int = 1,
    batch_size: int = 1,
    overhead_rate: float = 0.15,
) -> dict:
    """
    Injection moulding should-cost per part (single cavity basis).

    Parameters
    ----------
    material_cost_per_kg : float
        Polymer resin cost per kg. > 0.
    shot_mass_kg : float
        Total shot mass per cycle per cavity including runners (kg). > 0.
    scrap_rate : float
        Fraction of parts scrapped (default 0.03 = 3%). in [0, 1).
    cycle_time_hr : float
        Injection cycle time per shot (hr, default 0.005 ≈ 18 s). > 0.
    machine_rate_per_hr : float
        Machine + operator rate ($/hr, default 120). > 0.
    mould_cost : float
        Total mould tooling cost (default 0). >= 0.
    mould_life_shots : int
        Mould life in shots (default 100 000). >= 1.
    cavities : int
        Number of cavities in the mould (default 1). >= 1.
    batch_size : int
        Production run size in parts (default 1). >= 1.
    overhead_rate : float
        Overhead fraction on direct machine cost (default 0.15). in [0,1].

    Returns
    -------
    dict
        ok, unit_material, unit_machine, unit_mould, unit_overhead,
        unit_total_cost, effective_cycle_time_hr, warnings
    """
    err = _guard_positive("material_cost_per_kg", material_cost_per_kg)
    if err:
        return _err(err)
    err = _guard_positive("shot_mass_kg", shot_mass_kg)
    if err:
        return _err(err)
    err = _guard_fraction("scrap_rate", scrap_rate)
    if err:
        return _err(err)
    if float(scrap_rate) >= 1.0:
        return _err("scrap_rate must be < 1")
    err = _guard_positive("cycle_time_hr", cycle_time_hr)
    if err:
        return _err(err)
    err = _guard_positive("machine_rate_per_hr", machine_rate_per_hr)
    if err:
        return _err(err)
    err = _guard_nonneg("mould_cost", mould_cost)
    if err:
        return _err(err)
    if int(mould_life_shots) < 1:
        return _err("mould_life_shots must be >= 1")
    if int(cavities) < 1:
        return _err("cavities must be >= 1")
    if int(batch_size) < 1:
        return _err("batch_size must be >= 1")
    err = _guard_fraction("overhead_rate", overhead_rate)
    if err:
        return _err(err)

    c = int(cavities)
    sr = float(scrap_rate)
    # Cost per good part (adjusted for scrap)
    # Each shot produces c cavities; effective machine time per good part:
    effective_cycle = float(cycle_time_hr) / c / (1.0 - sr)

    unit_material = float(shot_mass_kg) * float(material_cost_per_kg) / (1.0 - sr)
    unit_machine = effective_cycle * float(machine_rate_per_hr)
    unit_mould = float(mould_cost) / float(mould_life_shots) / c
    unit_overhead = unit_machine * float(overhead_rate)
    unit_total = unit_material + unit_machine + unit_mould + unit_overhead

    warnings = []
    if int(batch_size) < 500 and float(mould_cost) > 0:
        warnings.append(
            f"tiny batch ({batch_size} parts) for injection moulding; "
            f"consider casting or machining for low volumes."
        )
    if float(scrap_rate) > 0.10:
        warnings.append(
            f"high scrap rate ({sr:.1%}) inflates material cost significantly."
        )

    result = _ok(
        unit_material=unit_material,
        unit_machine=unit_machine,
        unit_mould=unit_mould,
        unit_overhead=unit_overhead,
        unit_total_cost=unit_total,
        effective_cycle_time_hr=effective_cycle,
    )
    result["warnings"] = warnings
    return result


# ---------------------------------------------------------------------------
# 4. Sheet-metal should-cost
# ---------------------------------------------------------------------------

def sheet_metal_cost(
    blank_area_m2: float,
    material_cost_per_kg: float,
    material_density_kg_m3: float,
    sheet_thickness_m: float,
    *,
    num_bends: int = 0,
    bend_time_hr: float = 0.02,
    press_rate_per_hr: float = 60.0,
    laser_cut_rate_per_hr: float = 80.0,
    cut_perimeter_m: float = 0.0,
    cut_speed_m_per_hr: float = 10.0,
    setup_cost: float = 0.0,
    batch_size: int = 1,
    overhead_rate: float = 0.15,
) -> dict:
    """
    Sheet-metal fabrication should-cost per part.

    Parameters
    ----------
    blank_area_m2 : float
        Developed blank area (m²). > 0.
    material_cost_per_kg : float
        Sheet metal cost per kg. > 0.
    material_density_kg_m3 : float
        Alloy density (kg/m³, e.g. 7850 steel). > 0.
    sheet_thickness_m : float
        Sheet thickness (m). > 0.
    num_bends : int
        Number of bends (default 0). >= 0.
    bend_time_hr : float
        Press-brake time per bend (hr, default 0.02 ≈ 72 s). > 0.
    press_rate_per_hr : float
        Press/brake machine rate ($/hr, default 60). > 0.
    laser_cut_rate_per_hr : float
        Laser/plasma/waterjet cutting rate ($/hr, default 80). > 0.
    cut_perimeter_m : float
        Cut path length (m, default 0 = no laser cut cost). >= 0.
    cut_speed_m_per_hr : float
        Cutting speed (m/hr, default 10). > 0.
    setup_cost : float
        Setup / programming cost per batch (default 0). >= 0.
    batch_size : int
        Parts per run (default 1). >= 1.
    overhead_rate : float
        Overhead fraction on direct cost (default 0.15). in [0,1].

    Returns
    -------
    dict
        ok, blank_mass_kg, unit_material, unit_bending, unit_cutting,
        unit_setup, unit_overhead, unit_total_cost, warnings
    """
    err = _guard_positive("blank_area_m2", blank_area_m2)
    if err:
        return _err(err)
    err = _guard_positive("material_cost_per_kg", material_cost_per_kg)
    if err:
        return _err(err)
    err = _guard_positive("material_density_kg_m3", material_density_kg_m3)
    if err:
        return _err(err)
    err = _guard_positive("sheet_thickness_m", sheet_thickness_m)
    if err:
        return _err(err)
    if int(num_bends) < 0:
        return _err("num_bends must be >= 0")
    err = _guard_positive("bend_time_hr", bend_time_hr)
    if err:
        return _err(err)
    err = _guard_positive("press_rate_per_hr", press_rate_per_hr)
    if err:
        return _err(err)
    err = _guard_positive("laser_cut_rate_per_hr", laser_cut_rate_per_hr)
    if err:
        return _err(err)
    err = _guard_nonneg("cut_perimeter_m", cut_perimeter_m)
    if err:
        return _err(err)
    err = _guard_positive("cut_speed_m_per_hr", cut_speed_m_per_hr)
    if err:
        return _err(err)
    err = _guard_nonneg("setup_cost", setup_cost)
    if err:
        return _err(err)
    if int(batch_size) < 1:
        return _err("batch_size must be >= 1")
    err = _guard_fraction("overhead_rate", overhead_rate)
    if err:
        return _err(err)

    blank_mass_kg = (
        float(blank_area_m2)
        * float(sheet_thickness_m)
        * float(material_density_kg_m3)
    )
    unit_material = blank_mass_kg * float(material_cost_per_kg)
    unit_bending = int(num_bends) * float(bend_time_hr) * float(press_rate_per_hr)

    cut_time_hr = float(cut_perimeter_m) / float(cut_speed_m_per_hr)
    unit_cutting = cut_time_hr * float(laser_cut_rate_per_hr)

    unit_setup = float(setup_cost) / int(batch_size)
    direct = unit_material + unit_bending + unit_cutting + unit_setup
    unit_overhead = direct * float(overhead_rate)
    unit_total = direct + unit_overhead

    warnings = []
    if unit_setup > unit_material and int(batch_size) < 10:
        warnings.append(
            f"setup dominates for batch_size={batch_size}; "
            f"amortised setup ({unit_setup:.4f}) > material ({unit_material:.4f})."
        )

    result = _ok(
        blank_mass_kg=blank_mass_kg,
        unit_material=unit_material,
        unit_bending=unit_bending,
        unit_cutting=unit_cutting,
        unit_setup=unit_setup,
        unit_overhead=unit_overhead,
        unit_total_cost=unit_total,
    )
    result["warnings"] = warnings
    return result


# ---------------------------------------------------------------------------
# 5. 3D printing should-cost
# ---------------------------------------------------------------------------

def printing_cost(
    material_volume_cm3: float,
    material_cost_per_cm3: float,
    build_time_hr: float,
    machine_rate_per_hr: float,
    *,
    support_volume_fraction: float = 0.15,
    post_processing_cost: float = 0.0,
    batch_size: int = 1,
    machine_utilisation: float = 0.80,
    overhead_rate: float = 0.15,
) -> dict:
    """
    3D printing (FDM / SLA / SLS) should-cost per part.

    Parameters
    ----------
    material_volume_cm3 : float
        Part volume (cm³). > 0.
    material_cost_per_cm3 : float
        Material cost per cm³ (filament, resin, powder). > 0.
    build_time_hr : float
        Machine build time for this part alone (hr). > 0.
    machine_rate_per_hr : float
        All-in machine-hour rate ($/hr). > 0.
    support_volume_fraction : float
        Support structure volume as fraction of part volume (default 0.15). in [0,1].
    post_processing_cost : float
        Post-processing (wash, cure, support removal) per part (default 0). >= 0.
    batch_size : int
        Number of parts in this build (default 1 — used to share machine time). >= 1.
    machine_utilisation : float
        Fraction of machine time charged (default 0.80). in (0,1].
    overhead_rate : float
        Overhead fraction on direct machine cost (default 0.15). in [0,1].

    Returns
    -------
    dict
        ok, total_material_volume_cm3, unit_material, unit_machine,
        unit_post, unit_overhead, unit_total_cost, warnings
    """
    err = _guard_positive("material_volume_cm3", material_volume_cm3)
    if err:
        return _err(err)
    err = _guard_positive("material_cost_per_cm3", material_cost_per_cm3)
    if err:
        return _err(err)
    err = _guard_positive("build_time_hr", build_time_hr)
    if err:
        return _err(err)
    err = _guard_positive("machine_rate_per_hr", machine_rate_per_hr)
    if err:
        return _err(err)
    err = _guard_fraction("support_volume_fraction", support_volume_fraction)
    if err:
        return _err(err)
    err = _guard_nonneg("post_processing_cost", post_processing_cost)
    if err:
        return _err(err)
    if int(batch_size) < 1:
        return _err("batch_size must be >= 1")
    err = _guard_positive("machine_utilisation", machine_utilisation)
    if err:
        return _err(err)
    if float(machine_utilisation) > 1.0:
        return _err("machine_utilisation must be <= 1")
    err = _guard_fraction("overhead_rate", overhead_rate)
    if err:
        return _err(err)

    total_vol = float(material_volume_cm3) * (1.0 + float(support_volume_fraction))
    unit_material = total_vol * float(material_cost_per_cm3)

    # Machine time is shared among parts in the build
    shared_machine_time = float(build_time_hr) / int(batch_size)
    unit_machine = shared_machine_time * float(machine_rate_per_hr) * float(machine_utilisation)
    unit_post = float(post_processing_cost)
    unit_overhead = unit_machine * float(overhead_rate)
    unit_total = unit_material + unit_machine + unit_post + unit_overhead

    warnings = []
    if float(support_volume_fraction) > 0.30:
        warnings.append(
            f"high support fraction ({support_volume_fraction:.1%}); "
            f"consider redesign to reduce supports."
        )

    result = _ok(
        total_material_volume_cm3=total_vol,
        unit_material=unit_material,
        unit_machine=unit_machine,
        unit_post=unit_post,
        unit_overhead=unit_overhead,
        unit_total_cost=unit_total,
    )
    result["warnings"] = warnings
    return result


# ---------------------------------------------------------------------------
# 6. Assembly should-cost
# ---------------------------------------------------------------------------

def assembly_cost(
    operations: list[dict],
    *,
    overhead_rate: float = 0.20,
) -> dict:
    """
    Labour-time-based assembly should-cost.

    Parameters
    ----------
    operations : list[dict]
        Each operation dict must contain:
            "time_hr"   : float   — labour time for this operation (hr). > 0.
            "rate_per_hr": float  — labour rate ($/hr). > 0.
            "name"      : str     — (optional) operation name.
    overhead_rate : float
        Overhead fraction on total labour cost (default 0.20). in [0,1].

    Returns
    -------
    dict
        ok, operations_detail (list), total_labour_hr, unit_labour,
        unit_overhead, unit_total_cost, warnings
    """
    if not isinstance(operations, list) or len(operations) == 0:
        return _err("operations must be a non-empty list")

    err = _guard_fraction("overhead_rate", overhead_rate)
    if err:
        return _err(err)

    detail = []
    total_labour = 0.0
    for i, op in enumerate(operations):
        if not isinstance(op, dict):
            return _err(f"operations[{i}] must be a dict")
        t = op.get("time_hr")
        r = op.get("rate_per_hr")
        if t is None:
            return _err(f"operations[{i}] missing 'time_hr'")
        if r is None:
            return _err(f"operations[{i}] missing 'rate_per_hr'")
        e = _guard_positive(f"operations[{i}].time_hr", t)
        if e:
            return _err(e)
        e = _guard_positive(f"operations[{i}].rate_per_hr", r)
        if e:
            return _err(e)
        op_cost = float(t) * float(r)
        total_labour += op_cost
        detail.append({
            "name": op.get("name", f"op_{i}"),
            "time_hr": float(t),
            "rate_per_hr": float(r),
            "cost": op_cost,
        })

    unit_overhead = total_labour * float(overhead_rate)
    unit_total = total_labour + unit_overhead

    warnings = []
    total_hr = sum(d["time_hr"] for d in detail)
    if total_hr > 8.0:
        warnings.append(
            f"total assembly time {total_hr:.2f} hr exceeds one shift; "
            f"consider sub-assembly decomposition."
        )

    result = _ok(
        operations_detail=detail,
        total_labour_hr=total_hr,
        unit_labour=total_labour,
        unit_overhead=unit_overhead,
        unit_total_cost=unit_total,
    )
    result["warnings"] = warnings
    return result


# ---------------------------------------------------------------------------
# 7. Generic direct-cost roll-up
# ---------------------------------------------------------------------------

def rollup(
    direct_material: float,
    direct_labour: float,
    machine_cost: float,
    *,
    setup_cost_per_batch: float = 0.0,
    batch_size: int = 1,
    tooling_amortisation: float = 0.0,
    overhead_rate: float = 0.20,
    sga_rate: float = 0.10,
    margin_rate: float = 0.20,
) -> dict:
    """
    Generic manufacturing cost roll-up to unit price.

    Implements the standard cost waterfall:
        direct material
      + direct labour
      + machine cost
      + setup / batch amortisation
      + tooling amortisation
      = total direct cost
      × (1 + overhead_rate)
      = manufacturing cost
      × (1 + sga_rate)
      = full cost
      ÷ (1 − margin_rate)
      = unit price

    Parameters
    ----------
    direct_material : float   Direct material cost per unit. >= 0.
    direct_labour   : float   Direct labour cost per unit. >= 0.
    machine_cost    : float   Machine cost per unit. >= 0.
    setup_cost_per_batch : float  Total setup cost per batch run. >= 0.
    batch_size      : int     Batch size (default 1). >= 1.
    tooling_amortisation : float  Tooling amortisation per unit. >= 0.
    overhead_rate   : float   Overhead fraction of direct cost. in [0,1].
    sga_rate        : float   SG&A fraction of manufacturing cost. in [0,1].
    margin_rate     : float   Gross margin rate (0.20 = 20%). in [0,1).

    Returns
    -------
    dict
        ok, unit_direct_material, unit_direct_labour, unit_machine,
        unit_setup, unit_tooling, unit_overhead, total_direct_cost,
        manufacturing_cost, full_cost, unit_price, gross_margin,
        margin_rate_actual, warnings
    """
    for name, val in [
        ("direct_material", direct_material),
        ("direct_labour", direct_labour),
        ("machine_cost", machine_cost),
        ("setup_cost_per_batch", setup_cost_per_batch),
        ("tooling_amortisation", tooling_amortisation),
    ]:
        e = _guard_nonneg(name, val)
        if e:
            return _err(e)

    if int(batch_size) < 1:
        return _err("batch_size must be >= 1")
    err = _guard_fraction("overhead_rate", overhead_rate)
    if err:
        return _err(err)
    err = _guard_fraction("sga_rate", sga_rate)
    if err:
        return _err(err)
    err = _guard_fraction("margin_rate", margin_rate)
    if err:
        return _err(err)
    if float(margin_rate) >= 1.0:
        return _err("margin_rate must be < 1")

    unit_setup = float(setup_cost_per_batch) / int(batch_size)
    total_direct = (
        float(direct_material)
        + float(direct_labour)
        + float(machine_cost)
        + unit_setup
        + float(tooling_amortisation)
    )
    manufacturing_cost = total_direct * (1.0 + float(overhead_rate))
    full_cost = manufacturing_cost * (1.0 + float(sga_rate))
    unit_price = full_cost / (1.0 - float(margin_rate))
    gross_margin = unit_price - full_cost
    margin_actual = gross_margin / unit_price if unit_price > 0 else 0.0

    warnings = []
    if unit_setup > total_direct * 0.5 and int(batch_size) < 10:
        warnings.append(
            f"setup/batch cost ({unit_setup:.4f}) dominates ({unit_setup / total_direct:.1%} "
            f"of direct cost); consider larger batch."
        )
    if margin_actual < 0:
        warnings.append(
            "negative gross margin — unit price is below full cost."
        )

    result = _ok(
        unit_direct_material=float(direct_material),
        unit_direct_labour=float(direct_labour),
        unit_machine=float(machine_cost),
        unit_setup=unit_setup,
        unit_tooling=float(tooling_amortisation),
        unit_overhead=total_direct * float(overhead_rate),
        total_direct_cost=total_direct,
        manufacturing_cost=manufacturing_cost,
        full_cost=full_cost,
        unit_price=unit_price,
        gross_margin=gross_margin,
        margin_rate_actual=margin_actual,
    )
    result["warnings"] = warnings
    return result


# ---------------------------------------------------------------------------
# 8. Batch-size cost curve
# ---------------------------------------------------------------------------

def batch_curve(
    fixed_cost_per_run: float,
    variable_cost_per_unit: float,
    batch_sizes: list[int],
) -> dict:
    """
    Unit cost vs. batch-size breakpoints.

    Computes unit cost = variable_cost_per_unit + fixed_cost_per_run / n
    for each n in batch_sizes.

    Parameters
    ----------
    fixed_cost_per_run : float
        Total fixed cost per run (setup, tooling, etc.). >= 0.
    variable_cost_per_unit : float
        Variable cost per unit (material, direct labour, etc.). >= 0.
    batch_sizes : list[int]
        List of batch sizes to evaluate. Each must be >= 1. Must be non-empty.

    Returns
    -------
    dict
        ok, breakpoints (list of {batch_size, unit_cost}),
        min_unit_cost, max_unit_cost, warnings
    """
    err = _guard_nonneg("fixed_cost_per_run", fixed_cost_per_run)
    if err:
        return _err(err)
    err = _guard_nonneg("variable_cost_per_unit", variable_cost_per_unit)
    if err:
        return _err(err)
    if not isinstance(batch_sizes, list) or len(batch_sizes) == 0:
        return _err("batch_sizes must be a non-empty list")

    breakpoints = []
    for n in batch_sizes:
        try:
            n_int = int(n)
        except (TypeError, ValueError):
            return _err(f"batch_sizes contains non-integer value: {n!r}")
        if n_int < 1:
            return _err(f"batch_sizes values must be >= 1, got {n_int}")
        unit_cost = float(variable_cost_per_unit) + float(fixed_cost_per_run) / n_int
        breakpoints.append({"batch_size": n_int, "unit_cost": unit_cost})

    costs = [bp["unit_cost"] for bp in breakpoints]

    warnings = []
    if float(fixed_cost_per_run) == 0.0:
        warnings.append("fixed_cost_per_run is 0; unit cost is constant across batch sizes.")

    result = _ok(
        breakpoints=breakpoints,
        min_unit_cost=min(costs),
        max_unit_cost=max(costs),
    )
    result["warnings"] = warnings
    return result


# ---------------------------------------------------------------------------
# 9. Wright learning curve
# ---------------------------------------------------------------------------

def learning_curve(
    t1: float,
    cumulative_volume: float,
    *,
    learning_rate: float = 0.80,
) -> dict:
    """
    Wright (1936) learning-curve unit cost at cumulative volume.

    The learning-curve law states that each time cumulative production
    doubles, the unit cost (or time) drops to learning_rate × previous value.

    Formula:
        T_n = T_1 × n^b
        where b = log(learning_rate) / log(2)

    Parameters
    ----------
    t1 : float
        Unit cost (or time) at cumulative volume = 1. > 0.
    cumulative_volume : float
        Cumulative units produced (including this unit). > 0.
    learning_rate : float
        Learning rate (default 0.80 = 80% Wright curve). in (0, 1].

    Returns
    -------
    dict
        ok, t1, cumulative_volume, learning_rate, b_exponent, unit_cost,
        cost_reduction_fraction, warnings
    """
    err = _guard_positive("t1", t1)
    if err:
        return _err(err)
    err = _guard_positive("cumulative_volume", cumulative_volume)
    if err:
        return _err(err)
    err = _guard_positive("learning_rate", learning_rate)
    if err:
        return _err(err)
    if float(learning_rate) > 1.0:
        return _err("learning_rate must be <= 1")

    b = math.log(float(learning_rate)) / math.log(2.0)
    unit_cost = float(t1) * (float(cumulative_volume) ** b)
    cost_reduction = 1.0 - unit_cost / float(t1)

    warnings = []
    if float(learning_rate) >= 1.0:
        warnings.append(
            "learning_rate >= 1.0 implies no learning; unit cost never decreases."
        )
    if float(cumulative_volume) < 2.0:
        warnings.append(
            "cumulative_volume < 2; learning curve effect not yet observable."
        )

    result = _ok(
        t1=float(t1),
        cumulative_volume=float(cumulative_volume),
        learning_rate=float(learning_rate),
        b_exponent=b,
        unit_cost=unit_cost,
        cost_reduction_fraction=cost_reduction,
    )
    result["warnings"] = warnings
    return result


# ---------------------------------------------------------------------------
# 10. Make vs. buy comparison
# ---------------------------------------------------------------------------

def make_vs_buy(
    make_unit_cost: float,
    buy_unit_price: float,
    *,
    make_fixed_cost: float = 0.0,
    annual_volume: int = 1,
    make_lead_time_days: float = 14.0,
    buy_lead_time_days: float = 7.0,
) -> dict:
    """
    Make vs. buy comparison with break-even batch size.

    Parameters
    ----------
    make_unit_cost : float
        Variable cost to make one unit in-house. > 0.
    buy_unit_price : float
        Purchase price per unit from supplier. > 0.
    make_fixed_cost : float
        One-time or annual fixed cost of making in-house (tooling, setup,
        training, etc., default 0). >= 0.
    annual_volume : int
        Annual production / purchase volume (units, default 1). >= 1.
    make_lead_time_days : float
        Lead time for in-house production (days, default 14). > 0.
    buy_lead_time_days : float
        Supplier lead time (days, default 7). > 0.

    Returns
    -------
    dict
        ok, make_unit_cost, buy_unit_price, make_fixed_cost,
        annual_volume, make_annual_total, buy_annual_total,
        annual_savings_if_make, breakeven_volume, preferred,
        make_lead_time_days, buy_lead_time_days, warnings
    """
    err = _guard_positive("make_unit_cost", make_unit_cost)
    if err:
        return _err(err)
    err = _guard_positive("buy_unit_price", buy_unit_price)
    if err:
        return _err(err)
    err = _guard_nonneg("make_fixed_cost", make_fixed_cost)
    if err:
        return _err(err)
    if int(annual_volume) < 1:
        return _err("annual_volume must be >= 1")
    err = _guard_positive("make_lead_time_days", make_lead_time_days)
    if err:
        return _err(err)
    err = _guard_positive("buy_lead_time_days", buy_lead_time_days)
    if err:
        return _err(err)

    n = int(annual_volume)
    make_annual = float(make_unit_cost) * n + float(make_fixed_cost)
    buy_annual = float(buy_unit_price) * n
    annual_savings = buy_annual - make_annual  # positive → make saves money

    # Break-even: fixed + make_unit * n == buy * n
    # → fixed = (buy - make) * n_be
    cost_diff = float(buy_unit_price) - float(make_unit_cost)
    if cost_diff > 0:
        breakeven_volume = math.ceil(float(make_fixed_cost) / cost_diff)
    elif cost_diff == 0:
        breakeven_volume = None  # equal variable cost, only fixed matters
    else:
        breakeven_volume = None  # buy is always cheaper on variable basis

    if cost_diff > 0 and n >= breakeven_volume:
        preferred = "make"
    elif float(buy_unit_price) < float(make_unit_cost) + float(make_fixed_cost) / n:
        preferred = "buy"
    else:
        preferred = "buy"

    warnings = []
    if float(make_lead_time_days) > float(buy_lead_time_days) * 2:
        warnings.append(
            f"make lead time ({make_lead_time_days}d) is more than 2× buy lead "
            f"time ({buy_lead_time_days}d); factor inventory risk into decision."
        )
    if make_fixed_cost == 0 and cost_diff <= 0:
        warnings.append(
            "buy_unit_price <= make_unit_cost with no fixed costs: buying is "
            "always at least as cheap."
        )

    result = _ok(
        make_unit_cost=float(make_unit_cost),
        buy_unit_price=float(buy_unit_price),
        make_fixed_cost=float(make_fixed_cost),
        annual_volume=n,
        make_annual_total=make_annual,
        buy_annual_total=buy_annual,
        annual_savings_if_make=annual_savings,
        breakeven_volume=breakeven_volume,
        preferred=preferred,
        make_lead_time_days=float(make_lead_time_days),
        buy_lead_time_days=float(buy_lead_time_days),
    )
    result["warnings"] = warnings
    return result
