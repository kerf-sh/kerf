"""
kerf_cad_core.jewelry.enamel
============================

Enameling process planner for jewelry.

Supports five classic enamel techniques:

  cloisonné    — wires form cells; coloured enamel fills each cell
  champlevé    — recesses carved/etched into metal; enamel fills recesses
  plique-à-jour — open-frame cells, no metal backing; translucent windows
  basse-taille — engraved/engine-turned metal under translucent enamel
  grisaille    — monochromatic painting on dark enamel with white enamel paste

## Cloisonné

Wire-cell layout from a 2D region partition (list of cell polygon perimeters
and areas).  Total cloisonné wire length = Σ perimeters, with shared edges
counted once (caller supplies shared-edge list).  Enamel volume per colour =
Σ(area × depth) for all cells of that colour.

## Champlevé

Recess depth and area → metal volume removed + enamel fill volume.
Metal-removed volume = recess_area × recess_depth.

## Firing schedule

  counter-enamel  — required for most techniques unless piece < 1 mm thick or
                    fine silver / copper; doubles total enamel mass
  coats           — thin coats preferred; determined by total depth
                    1 coat: depth ≤ COAT_DEPTH_MM
                    n coats = ceil(depth / COAT_DEPTH_MM)
  kiln temperature band — by enamel type:
                    soft   1380–1430 °F
                    medium 1430–1500 °F
                    hard   1500–1560 °F
  time per coat   — 2 min for soft, 2.5 min for medium, 3 min for hard
  total firings   — coats × (2 if counter_enamel_required else 1)

## Enamel density

  ~2.5 g/cm³ (vitreous enamel / glass frit).

## Metal compatibility

  fine_silver  — ideal, no firescale
  copper       — traditional base, good expansion match
  gold alloys  — good
  sterling_925 — firescale risk (copper content oxidises during firing)
  brass/bronze — possible but significant firescale and expansion mismatch
  palladium / platinum — generally compatible, high cost
  titanium     — NOT compatible (oxide layer prevents enamel adhesion)

## Cost model

  enamel_cost  = Σ colour_mass_g × enamel_price_per_g
  labour_cost  = labour_hours × labour_rate_per_hour
  subtotal     = enamel_cost + labour_cost
  total        = subtotal × (1 + markup_pct / 100)

## Error policy

  Never raises.  Errors returned in-band as {"ok": False, "reason": ...}.
"""

from __future__ import annotations

import math
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Enamel density: vitreous glass frit, g/cm³
ENAMEL_DENSITY_G_CM3: float = 2.5

# Volume unit: 1 cm³ = 1000 mm³
MM3_PER_CM3: float = 1000.0

# Max single-coat depth in mm (industry convention: ~0.3 mm per coat)
COAT_DEPTH_MM: float = 0.3

# Wastage fraction added to calculated enamel mass (default 15 %)
DEFAULT_WASTAGE_PCT: float = 15.0

# Valid technique names
TECHNIQUES: frozenset[str] = frozenset(
    ["cloisonne", "champleve", "plique_a_jour", "basse_taille", "grisaille"]
)

# Enamel hardness classifications and kiln temperature bands (°F)
ENAMEL_KILN_TEMP_BANDS: dict[str, tuple[int, int]] = {
    "soft":   (1380, 1430),
    "medium": (1430, 1500),
    "hard":   (1500, 1560),
}

# Time per coat (minutes) by enamel type
COAT_TIME_MINUTES: dict[str, float] = {
    "soft":   2.0,
    "medium": 2.5,
    "hard":   3.0,
}

# Metals with firescale risk during enameling firing
_FIRESCALE_RISK: frozenset[str] = frozenset(
    ["sterling_925", "brass", "bronze"]
)

# Metals incompatible with enameling
_INCOMPATIBLE_METALS: frozenset[str] = frozenset(["titanium"])

# Metals that require counter-enamel by default (all unless overridden)
# Counter-enamel NOT required for: very thin pieces (< 1 mm) — caller specifies.
_DEFAULT_COUNTER_ENAMEL = True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fail(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _require_positive(value, name: str) -> Optional[str]:
    """Return error string if value is not a positive number, else None."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number"
    if f <= 0:
        return f"{name} must be positive, got {f}"
    return None


def _require_non_negative(value, name: str) -> Optional[str]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number"
    if f < 0:
        return f"{name} must be >= 0, got {f}"
    return None


def _coats_for_depth(depth_mm: float) -> int:
    """Number of enamel coats required for a given total depth (mm)."""
    if depth_mm <= 0:
        return 0
    return math.ceil(depth_mm / COAT_DEPTH_MM)


# ---------------------------------------------------------------------------
# Metal compatibility check
# ---------------------------------------------------------------------------

def metal_enamel_compatibility(metal_key: str) -> dict:
    """
    Check whether a metal is compatible with enameling.

    Parameters
    ----------
    metal_key : str
        Alloy key (e.g. "fine_silver", "sterling_925", "copper").

    Returns
    -------
    dict:
        ok               — bool; False if metal is incompatible
        reason           — error description when ok=False
        metal_key        — normalised key
        compatible       — bool (always present)
        firescale_risk   — bool: True if sterling/brass/bronze
        notes            — explanatory string
    """
    key = str(metal_key).strip().lower()

    if key in _INCOMPATIBLE_METALS:
        return {
            "ok": False,
            "reason": (
                f"'{key}' is not compatible with enameling: "
                f"oxide layer prevents adhesion."
            ),
            "metal_key": key,
            "compatible": False,
            "firescale_risk": False,
            "notes": "Titanium oxide (TiO₂) prevents enamel bonding.",
        }

    firescale = key in _FIRESCALE_RISK

    if key == "fine_silver":
        notes = "Fine silver is ideal for enameling: no firescale, good thermal expansion."
    elif key == "copper":
        notes = "Copper is the traditional enameling base; good thermal expansion match."
    elif key.startswith("gold") or "k_" in key or key in (
        "24k_yellow", "22k_yellow", "22k_rose", "22k_white",
        "18k_yellow", "18k_white", "18k_rose",
        "14k_yellow", "14k_white", "14k_rose",
        "10k_yellow", "10k_white", "10k_rose",
    ):
        notes = "Gold alloys are compatible; higher karat preferred to reduce firescale risk."
    elif firescale:
        notes = (
            f"'{key}' poses a firescale risk during firing due to copper content. "
            "Use depletion gilding, investment, or anti-firescale flux to mitigate."
        )
    elif key.startswith("platinum") or key.startswith("palladium"):
        notes = "Platinum-group metals are compatible but uncommon; high cost."
    elif key == "argentium_935":
        notes = "Argentium silver reduces firescale vs sterling due to germanium content."
    else:
        notes = f"'{key}' compatibility not fully characterised; proceed with caution."

    return {
        "ok": True,
        "reason": None,
        "metal_key": key,
        "compatible": True,
        "firescale_risk": firescale,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Firing schedule
# ---------------------------------------------------------------------------

def firing_schedule(
    total_depth_mm: float,
    enamel_type: str = "medium",
    counter_enamel_required: bool = True,
) -> dict:
    """
    Compute the firing schedule for an enameled piece.

    Parameters
    ----------
    total_depth_mm : float
        Total enamel fill depth in mm (maximum recess / cell depth).
    enamel_type : str
        "soft", "medium", or "hard".  Default "medium".
    counter_enamel_required : bool
        Whether a counter-enamel backing coat is needed.  Default True.
        Counter-enamel doubles total enamel mass consumption but prevents
        warping; required for pieces > ~1 mm thick.

    Returns
    -------
    dict:
        ok                      — bool
        reason                  — error string if ok=False
        enamel_type             — normalised type used
        coats                   — number of face coats
        counter_enamel_required — as supplied
        total_firings           — coats (+ 1 counter if required)
        kiln_temp_min_f         — lower bound of temperature band (°F)
        kiln_temp_max_f         — upper bound (°F)
        time_per_coat_min       — minutes per firing
        total_time_min          — total kiln time (minutes)
    """
    err = _require_positive(total_depth_mm, "total_depth_mm")
    if err:
        return _fail(err)

    etype = str(enamel_type).strip().lower()
    if etype not in ENAMEL_KILN_TEMP_BANDS:
        return _fail(
            f"Unknown enamel_type '{enamel_type}'. "
            f"Valid: {sorted(ENAMEL_KILN_TEMP_BANDS)}"
        )

    coats = _coats_for_depth(float(total_depth_mm))
    temp_min, temp_max = ENAMEL_KILN_TEMP_BANDS[etype]
    time_per_coat = COAT_TIME_MINUTES[etype]

    # Counter-enamel adds 1 extra firing cycle
    total_firings = coats + (1 if counter_enamel_required else 0)
    total_time = total_firings * time_per_coat

    return {
        "ok": True,
        "reason": None,
        "enamel_type": etype,
        "coats": coats,
        "counter_enamel_required": counter_enamel_required,
        "total_firings": total_firings,
        "kiln_temp_min_f": temp_min,
        "kiln_temp_max_f": temp_max,
        "time_per_coat_min": time_per_coat,
        "total_time_min": total_time,
    }


# ---------------------------------------------------------------------------
# Cloisonné wire-cell layout
# ---------------------------------------------------------------------------

def cloisonne_layout(
    cells: list[dict],
    shared_edges: Optional[list[float]] = None,
) -> dict:
    """
    Compute total cloisonné wire length and enamel volumes from cell geometry.

    Parameters
    ----------
    cells : list[dict]
        Each cell dict:
            perimeter_mm : float  — full perimeter of the cell (mm)
            area_mm2     : float  — cell area (mm²)
            depth_mm     : float  — enamel fill depth (mm)
            colour       : str    — colour label (for grouping volumes)
    shared_edges : list[float], optional
        Lengths of shared edges between cells (mm).  Each shared edge is
        subtracted once from the total wire length because it is shared by
        two adjacent cells and only one wire segment is needed.
        Pass [] or None to skip shared-edge deduction.

    Returns
    -------
    dict:
        ok                   — bool
        reason               — error string if ok=False
        cell_count           — number of cells
        total_perimeter_mm   — Σ cell perimeters (before shared-edge deduction)
        shared_edge_total_mm — sum of shared edge lengths
        wire_length_mm       — total_perimeter_mm − shared_edge_total_mm
        cell_details         — list of per-cell dicts:
                               {colour, perimeter_mm, area_mm2, depth_mm,
                                enamel_volume_mm3, enamel_mass_g}
        colour_volumes       — dict of colour → total enamel volume (mm³)
        colour_masses        — dict of colour → total enamel mass (g)
        total_enamel_volume_mm3 — Σ area·depth for all cells
        total_enamel_mass_g  — mass at ENAMEL_DENSITY_G_CM3
    """
    if not isinstance(cells, list) or len(cells) == 0:
        return _fail("cells must be a non-empty list")

    cell_details: list[dict] = []
    total_perimeter = 0.0
    total_enamel_volume = 0.0
    colour_volumes: dict[str, float] = {}
    colour_masses: dict[str, float] = {}

    for i, cell in enumerate(cells):
        if not isinstance(cell, dict):
            return _fail(f"cells[{i}] must be a dict")

        err = _require_positive(cell.get("perimeter_mm"), f"cells[{i}].perimeter_mm")
        if err:
            return _fail(err)
        err = _require_positive(cell.get("area_mm2"), f"cells[{i}].area_mm2")
        if err:
            return _fail(err)
        err = _require_positive(cell.get("depth_mm"), f"cells[{i}].depth_mm")
        if err:
            return _fail(err)

        perim = float(cell["perimeter_mm"])
        area = float(cell["area_mm2"])
        depth = float(cell["depth_mm"])
        colour = str(cell.get("colour", "default")).strip().lower()

        vol_mm3 = area * depth
        mass_g = (vol_mm3 / MM3_PER_CM3) * ENAMEL_DENSITY_G_CM3

        total_perimeter += perim
        total_enamel_volume += vol_mm3

        colour_volumes[colour] = colour_volumes.get(colour, 0.0) + vol_mm3
        colour_masses[colour] = colour_masses.get(colour, 0.0) + mass_g

        cell_details.append({
            "colour": colour,
            "perimeter_mm": perim,
            "area_mm2": area,
            "depth_mm": depth,
            "enamel_volume_mm3": vol_mm3,
            "enamel_mass_g": mass_g,
        })

    # Shared-edge deduction
    if shared_edges is None:
        shared_edges = []
    shared_total = 0.0
    for j, edge_len in enumerate(shared_edges):
        err = _require_non_negative(edge_len, f"shared_edges[{j}]")
        if err:
            return _fail(err)
        shared_total += float(edge_len)

    wire_length = total_perimeter - shared_total
    total_enamel_mass = (total_enamel_volume / MM3_PER_CM3) * ENAMEL_DENSITY_G_CM3

    return {
        "ok": True,
        "reason": None,
        "cell_count": len(cells),
        "total_perimeter_mm": total_perimeter,
        "shared_edge_total_mm": shared_total,
        "wire_length_mm": wire_length,
        "cell_details": cell_details,
        "colour_volumes": colour_volumes,
        "colour_masses": colour_masses,
        "total_enamel_volume_mm3": total_enamel_volume,
        "total_enamel_mass_g": total_enamel_mass,
    }


# ---------------------------------------------------------------------------
# Champlevé recess calculator
# ---------------------------------------------------------------------------

def champleve_recess(
    recesses: list[dict],
) -> dict:
    """
    Compute metal removed and enamel fill volumes for champlevé recesses.

    Parameters
    ----------
    recesses : list[dict]
        Each recess dict:
            area_mm2  : float — recess surface area (mm²)
            depth_mm  : float — recess depth (mm)
            colour    : str   — colour label (optional, default "default")

    Returns
    -------
    dict:
        ok                       — bool
        reason                   — error string if ok=False
        recess_count             — number of recesses
        recess_details           — list of per-recess dicts:
                                   {colour, area_mm2, depth_mm,
                                    metal_removed_mm3, enamel_volume_mm3,
                                    enamel_mass_g}
        colour_volumes           — dict of colour → total enamel volume (mm³)
        colour_masses            — dict of colour → total enamel mass (g)
        total_metal_removed_mm3  — total metal volume removed (mm³)
        total_enamel_volume_mm3  — total enamel fill volume (mm³)
        total_enamel_mass_g      — total enamel mass (g)
    """
    if not isinstance(recesses, list) or len(recesses) == 0:
        return _fail("recesses must be a non-empty list")

    recess_details: list[dict] = []
    colour_volumes: dict[str, float] = {}
    colour_masses: dict[str, float] = {}
    total_metal_removed = 0.0
    total_enamel_volume = 0.0

    for i, rec in enumerate(recesses):
        if not isinstance(rec, dict):
            return _fail(f"recesses[{i}] must be a dict")

        err = _require_positive(rec.get("area_mm2"), f"recesses[{i}].area_mm2")
        if err:
            return _fail(err)
        err = _require_positive(rec.get("depth_mm"), f"recesses[{i}].depth_mm")
        if err:
            return _fail(err)

        area = float(rec["area_mm2"])
        depth = float(rec["depth_mm"])
        colour = str(rec.get("colour", "default")).strip().lower()

        # Champlevé: metal removed = recess volume = area × depth
        metal_removed = area * depth
        enamel_vol = area * depth  # recess is filled with enamel
        enamel_mass = (enamel_vol / MM3_PER_CM3) * ENAMEL_DENSITY_G_CM3

        total_metal_removed += metal_removed
        total_enamel_volume += enamel_vol

        colour_volumes[colour] = colour_volumes.get(colour, 0.0) + enamel_vol
        colour_masses[colour] = colour_masses.get(colour, 0.0) + enamel_mass

        recess_details.append({
            "colour": colour,
            "area_mm2": area,
            "depth_mm": depth,
            "metal_removed_mm3": metal_removed,
            "enamel_volume_mm3": enamel_vol,
            "enamel_mass_g": enamel_mass,
        })

    total_enamel_mass = (total_enamel_volume / MM3_PER_CM3) * ENAMEL_DENSITY_G_CM3

    return {
        "ok": True,
        "reason": None,
        "recess_count": len(recesses),
        "recess_details": recess_details,
        "colour_volumes": colour_volumes,
        "colour_masses": colour_masses,
        "total_metal_removed_mm3": total_metal_removed,
        "total_enamel_volume_mm3": total_enamel_volume,
        "total_enamel_mass_g": total_enamel_mass,
    }


# ---------------------------------------------------------------------------
# Enamel mass with wastage
# ---------------------------------------------------------------------------

def enamel_mass_with_wastage(
    enamel_volume_mm3: float,
    counter_enamel_required: bool = True,
    wastage_pct: float = DEFAULT_WASTAGE_PCT,
) -> dict:
    """
    Compute enamel mass including counter-enamel and wastage.

    Counter-enamel is applied to the back of the piece to prevent warping.
    Its mass equals the face-enamel mass (same total volume applied to the
    back surface at equal thickness).

    Parameters
    ----------
    enamel_volume_mm3 : float
        Face enamel volume in mm³.
    counter_enamel_required : bool
        If True, counter-enamel mass equals face-enamel mass (total × 2).
    wastage_pct : float
        Percentage of extra enamel to account for handling/firing loss.
        Default 15 %.

    Returns
    -------
    dict:
        ok                       — bool
        reason                   — error string if ok=False
        face_enamel_volume_mm3   — input volume
        counter_enamel_required  — as supplied
        counter_enamel_volume_mm3 — 0 or face volume
        total_volume_mm3         — face + counter
        face_enamel_mass_g       — face mass at ENAMEL_DENSITY_G_CM3
        counter_enamel_mass_g    — counter mass
        net_mass_g               — total before wastage
        wastage_pct              — wastage fraction used
        wastage_g                — extra grams for wastage
        total_mass_g             — net + wastage
    """
    err = _require_positive(enamel_volume_mm3, "enamel_volume_mm3")
    if err:
        return _fail(err)
    err = _require_non_negative(wastage_pct, "wastage_pct")
    if err:
        return _fail(err)

    face_mass = (float(enamel_volume_mm3) / MM3_PER_CM3) * ENAMEL_DENSITY_G_CM3
    counter_vol = float(enamel_volume_mm3) if counter_enamel_required else 0.0
    counter_mass = (counter_vol / MM3_PER_CM3) * ENAMEL_DENSITY_G_CM3
    net_mass = face_mass + counter_mass
    wastage_g = net_mass * float(wastage_pct) / 100.0
    total_mass = net_mass + wastage_g

    return {
        "ok": True,
        "reason": None,
        "face_enamel_volume_mm3": float(enamel_volume_mm3),
        "counter_enamel_required": counter_enamel_required,
        "counter_enamel_volume_mm3": counter_vol,
        "total_volume_mm3": float(enamel_volume_mm3) + counter_vol,
        "face_enamel_mass_g": face_mass,
        "counter_enamel_mass_g": counter_mass,
        "net_mass_g": net_mass,
        "wastage_pct": float(wastage_pct),
        "wastage_g": wastage_g,
        "total_mass_g": total_mass,
    }


# ---------------------------------------------------------------------------
# Cost estimator
# ---------------------------------------------------------------------------

def enamel_cost_estimate(
    enamel_mass_g: float,
    enamel_price_per_g: float,
    labour_hours: float = 0.0,
    labour_rate_per_hour: float = 0.0,
    markup_pct: float = 0.0,
) -> dict:
    """
    Compute itemised enamel process cost.

    Parameters
    ----------
    enamel_mass_g : float
        Total enamel mass to purchase (g) — use total_mass_g from
        enamel_mass_with_wastage, or sum of colour masses.
    enamel_price_per_g : float
        Enamel price per gram (USD or your currency).
    labour_hours : float
        Bench hours for the enameling work.
    labour_rate_per_hour : float
        Hourly bench rate.
    markup_pct : float
        Markup on subtotal (e.g. 20 = 20 %). Default 0.

    Returns
    -------
    dict:
        ok                   — bool
        reason               — error string if ok=False
        enamel_mass_g        — input
        enamel_price_per_g   — input
        enamel_cost          — enamel_mass_g × enamel_price_per_g
        labour_hours         — input
        labour_rate_per_hour — input
        labour_cost          — labour_hours × labour_rate_per_hour
        subtotal             — enamel_cost + labour_cost
        markup_pct           — input
        markup_amount        — subtotal × markup_pct / 100
        total_cost           — subtotal + markup_amount
    """
    err = _require_non_negative(enamel_mass_g, "enamel_mass_g")
    if err:
        return _fail(err)
    err = _require_non_negative(enamel_price_per_g, "enamel_price_per_g")
    if err:
        return _fail(err)
    err = _require_non_negative(labour_hours, "labour_hours")
    if err:
        return _fail(err)
    err = _require_non_negative(labour_rate_per_hour, "labour_rate_per_hour")
    if err:
        return _fail(err)
    err = _require_non_negative(markup_pct, "markup_pct")
    if err:
        return _fail(err)

    enamel_c = float(enamel_mass_g) * float(enamel_price_per_g)
    labour_c = float(labour_hours) * float(labour_rate_per_hour)
    subtotal = enamel_c + labour_c
    markup_amount = subtotal * float(markup_pct) / 100.0
    total = subtotal + markup_amount

    return {
        "ok": True,
        "reason": None,
        "enamel_mass_g": float(enamel_mass_g),
        "enamel_price_per_g": float(enamel_price_per_g),
        "enamel_cost": enamel_c,
        "labour_hours": float(labour_hours),
        "labour_rate_per_hour": float(labour_rate_per_hour),
        "labour_cost": labour_c,
        "subtotal": subtotal,
        "markup_pct": float(markup_pct),
        "markup_amount": markup_amount,
        "total_cost": total,
    }


# ---------------------------------------------------------------------------
# Full enamel process planner
# ---------------------------------------------------------------------------

def plan_enamel(
    technique: str,
    metal_key: str,
    # cloisonné inputs
    cells: Optional[list[dict]] = None,
    shared_edges: Optional[list[float]] = None,
    # champlevé inputs
    recesses: Optional[list[dict]] = None,
    # common enamel parameters
    enamel_type: str = "medium",
    counter_enamel_required: bool = _DEFAULT_COUNTER_ENAMEL,
    wastage_pct: float = DEFAULT_WASTAGE_PCT,
    # cost parameters
    enamel_price_per_g: float = 0.0,
    labour_hours: float = 0.0,
    labour_rate_per_hour: float = 0.0,
    markup_pct: float = 0.0,
) -> dict:
    """
    Full enameling process plan combining technique geometry, firing schedule,
    metal compatibility, mass calculation, and cost estimate.

    Parameters
    ----------
    technique : str
        One of: "cloisonne", "champleve", "plique_a_jour", "basse_taille",
        "grisaille".
    metal_key : str
        Base metal alloy key (e.g. "fine_silver", "sterling_925", "copper").
    cells : list[dict], optional
        Required for "cloisonne".  See cloisonne_layout().
    shared_edges : list[float], optional
        Shared edge lengths for cloisonné (mm).
    recesses : list[dict], optional
        Required for "champleve".  See champleve_recess().
    enamel_type : str
        "soft", "medium", or "hard".  Default "medium".
    counter_enamel_required : bool
        Whether counter-enamel backing is applied.  Default True.
    wastage_pct : float
        Wastage percentage for enamel purchasing estimate.  Default 15 %.
    enamel_price_per_g : float
        Enamel cost per gram for cost estimate.  Default 0.
    labour_hours : float
        Bench hours for enameling labour.  Default 0.
    labour_rate_per_hour : float
        Hourly bench rate.  Default 0.
    markup_pct : float
        Markup percentage on subtotal.  Default 0.

    Returns
    -------
    dict:
        ok                    — bool
        reason                — error string if ok=False
        technique             — normalised technique name
        metal_compatibility   — result of metal_enamel_compatibility()
        geometry              — cloisonné layout or champlevé recess dict
                                (None for plique_a_jour / basse_taille /
                                grisaille — caller provides enamel_volume_mm3
                                separately via enamel_mass_with_wastage)
        firing_schedule       — result of firing_schedule()
        mass                  — result of enamel_mass_with_wastage()
        cost                  — result of enamel_cost_estimate()
    """
    technique_key = str(technique).strip().lower().replace("-", "_")

    if technique_key not in TECHNIQUES:
        return _fail(
            f"Unknown technique '{technique}'. "
            f"Valid: {sorted(TECHNIQUES)}"
        )

    # Metal compatibility
    compat = metal_enamel_compatibility(metal_key)
    if not compat["ok"]:
        return {
            "ok": False,
            "reason": compat["reason"],
            "technique": technique_key,
            "metal_compatibility": compat,
            "geometry": None,
            "firing_schedule": None,
            "mass": None,
            "cost": None,
        }

    # Geometry phase
    geometry: Optional[dict] = None
    enamel_volume_mm3: float = 0.0
    max_depth_mm: float = 0.0

    if technique_key == "cloisonne":
        if not cells:
            return _fail("cells is required for cloisonne technique")
        geometry = cloisonne_layout(cells, shared_edges)
        if not geometry["ok"]:
            return {
                "ok": False,
                "reason": geometry["reason"],
                "technique": technique_key,
                "metal_compatibility": compat,
                "geometry": geometry,
                "firing_schedule": None,
                "mass": None,
                "cost": None,
            }
        enamel_volume_mm3 = geometry["total_enamel_volume_mm3"]
        max_depth_mm = max(c["depth_mm"] for c in geometry["cell_details"])

    elif technique_key == "champleve":
        if not recesses:
            return _fail("recesses is required for champleve technique")
        geometry = champleve_recess(recesses)
        if not geometry["ok"]:
            return {
                "ok": False,
                "reason": geometry["reason"],
                "technique": technique_key,
                "metal_compatibility": compat,
                "geometry": geometry,
                "firing_schedule": None,
                "mass": None,
                "cost": None,
            }
        enamel_volume_mm3 = geometry["total_enamel_volume_mm3"]
        max_depth_mm = max(r["depth_mm"] for r in geometry["recess_details"])

    else:
        # plique_a_jour, basse_taille, grisaille — no geometry required here;
        # use minimal placeholder firing schedule based on a default 0.5 mm depth
        max_depth_mm = 0.5
        enamel_volume_mm3 = 0.0  # caller to supply separately

    # Firing schedule
    if max_depth_mm <= 0:
        max_depth_mm = 0.5  # fallback for techniques without geometry

    sched = firing_schedule(max_depth_mm, enamel_type, counter_enamel_required)
    if not sched["ok"]:
        return {
            "ok": False,
            "reason": sched["reason"],
            "technique": technique_key,
            "metal_compatibility": compat,
            "geometry": geometry,
            "firing_schedule": sched,
            "mass": None,
            "cost": None,
        }

    # Mass (only meaningful for cloisonné and champlevé where we know volume)
    mass: Optional[dict] = None
    if enamel_volume_mm3 > 0:
        mass = enamel_mass_with_wastage(
            enamel_volume_mm3,
            counter_enamel_required=counter_enamel_required,
            wastage_pct=wastage_pct,
        )
    else:
        # Return a placeholder structure so callers can still see the schema
        mass = {
            "ok": True,
            "reason": None,
            "face_enamel_volume_mm3": 0.0,
            "counter_enamel_required": counter_enamel_required,
            "counter_enamel_volume_mm3": 0.0,
            "total_volume_mm3": 0.0,
            "face_enamel_mass_g": 0.0,
            "counter_enamel_mass_g": 0.0,
            "net_mass_g": 0.0,
            "wastage_pct": float(wastage_pct),
            "wastage_g": 0.0,
            "total_mass_g": 0.0,
        }

    # Cost
    purchase_mass = mass["total_mass_g"] if mass else 0.0
    cost = enamel_cost_estimate(
        enamel_mass_g=purchase_mass,
        enamel_price_per_g=enamel_price_per_g,
        labour_hours=labour_hours,
        labour_rate_per_hour=labour_rate_per_hour,
        markup_pct=markup_pct,
    )

    return {
        "ok": True,
        "reason": None,
        "technique": technique_key,
        "metal_compatibility": compat,
        "geometry": geometry,
        "firing_schedule": sched,
        "mass": mass,
        "cost": cost,
    }


# ---------------------------------------------------------------------------
# LLM tool registration
# ---------------------------------------------------------------------------

try:
    import json as _json
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx  # noqa: F401

    _enamel_tool_spec = ToolSpec(
        name="jewelry_enamel",
        description=(
            "Enameling process planner for jewelry.\n"
            "\n"
            "Techniques: cloisonné (wire-cell), champlevé (carved recess),\n"
            "plique-à-jour (open cells), basse-taille (engraved ground),\n"
            "grisaille (monochromatic painting).\n"
            "\n"
            "Returns:\n"
            "  - metal compatibility check (firescale risk for sterling)\n"
            "  - cloisonné: total wire length, cell areas, enamel volume per colour\n"
            "  - champlevé: metal removed + enamel fill volume per recess\n"
            "  - firing schedule: coats, kiln temp band, time, total firings\n"
            "  - enamel mass per colour with counter-enamel and wastage\n"
            "  - itemised cost (enamel g·$/g + labour + markup)\n"
            "\n"
            "Technique keys: cloisonne, champleve, plique_a_jour, basse_taille, grisaille\n"
            "Enamel types: soft (1380–1430 °F), medium (1430–1500 °F), hard (1500–1560 °F)"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "technique": {
                    "type": "string",
                    "description": (
                        "Enamel technique: cloisonne, champleve, plique_a_jour, "
                        "basse_taille, grisaille."
                    ),
                },
                "metal_key": {
                    "type": "string",
                    "description": (
                        "Base metal alloy key e.g. 'fine_silver', 'sterling_925', "
                        "'copper', '18k_yellow'."
                    ),
                },
                "cells": {
                    "type": "array",
                    "description": (
                        "Cloisonné cell list (required for cloisonne). "
                        "Each: {perimeter_mm, area_mm2, depth_mm, colour}."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "perimeter_mm": {"type": "number"},
                            "area_mm2":     {"type": "number"},
                            "depth_mm":     {"type": "number"},
                            "colour":       {"type": "string"},
                        },
                        "required": ["perimeter_mm", "area_mm2", "depth_mm"],
                    },
                },
                "shared_edges": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": (
                        "Lengths of shared cell-boundary segments (mm). "
                        "Each shared edge is counted once and subtracted from total wire length."
                    ),
                },
                "recesses": {
                    "type": "array",
                    "description": (
                        "Champlevé recess list (required for champleve). "
                        "Each: {area_mm2, depth_mm, colour}."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "area_mm2": {"type": "number"},
                            "depth_mm": {"type": "number"},
                            "colour":   {"type": "string"},
                        },
                        "required": ["area_mm2", "depth_mm"],
                    },
                },
                "enamel_type": {
                    "type": "string",
                    "description": "soft | medium | hard. Default medium.",
                },
                "counter_enamel_required": {
                    "type": "boolean",
                    "description": "Apply counter-enamel backing. Default true.",
                },
                "wastage_pct": {
                    "type": "number",
                    "description": "Wastage % on enamel mass. Default 15.",
                },
                "enamel_price_per_g": {
                    "type": "number",
                    "description": "Enamel cost per gram (your currency). Default 0.",
                },
                "labour_hours": {
                    "type": "number",
                    "description": "Bench hours for enameling. Default 0.",
                },
                "labour_rate_per_hour": {
                    "type": "number",
                    "description": "Hourly bench rate. Default 0.",
                },
                "markup_pct": {
                    "type": "number",
                    "description": "Markup % on subtotal. Default 0.",
                },
            },
            "required": ["technique", "metal_key"],
        },
    )

    @register(_enamel_tool_spec, write=False)
    async def run_jewelry_enamel(ctx: "ProjectCtx", args: bytes) -> str:
        """LLM tool: jewelry_enamel."""
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

        technique = a.get("technique")
        if not technique:
            return err_payload("technique is required", "BAD_ARGS")

        metal_key = a.get("metal_key")
        if not metal_key:
            return err_payload("metal_key is required", "BAD_ARGS")

        result = plan_enamel(
            technique=technique,
            metal_key=metal_key,
            cells=a.get("cells"),
            shared_edges=a.get("shared_edges"),
            recesses=a.get("recesses"),
            enamel_type=str(a.get("enamel_type", "medium")),
            counter_enamel_required=bool(a.get("counter_enamel_required", True)),
            wastage_pct=float(a.get("wastage_pct", DEFAULT_WASTAGE_PCT)),
            enamel_price_per_g=float(a.get("enamel_price_per_g", 0.0)),
            labour_hours=float(a.get("labour_hours", 0.0)),
            labour_rate_per_hour=float(a.get("labour_rate_per_hour", 0.0)),
            markup_pct=float(a.get("markup_pct", 0.0)),
        )

        if not result["ok"]:
            return err_payload(result["reason"], "BAD_ARGS")

        return ok_payload(result)

    _TOOL_REGISTERED = True

except ImportError:
    _TOOL_REGISTERED = False
