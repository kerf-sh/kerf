"""
kerf_cad_core.jewelry.setter_checklist
=======================================

Bench-jeweller's setter checklist generator.

Given a jewelry piece description with stones and their setting types, this
module produces a sequenced, step-by-step setting checklist suitable for a
working setter at the bench.

Sequencing rules
----------------
The setting order follows industry best practice to minimise risk of damage:

1. Center stone is set first (highest value, most visible; gets the best seat).
2. Three-stone pieces: centre first, then sides in size order (largest side
   first).
3. Accent / shoulder stones next (working outward from centre).
4. Halo stones last (they surround the centre and are set after it is secure).
5. Within a row (channel / pavé) stones are set front-to-back or largest-
   to-smallest.
6. Channel: lay all stones before tapping walls; pavé: drill all seats before
   raising beads.

Setting-style workflows
-----------------------
prong      → seat-check → raise prong tip → trim flush → round with cup bur
             → burnish toward stone.
bezel      → push opposite walls first → work around → rub overlap → polish.
pave       → drill seat → place stone → raise bead with graver → form bead
             with beading tool → bright-cut surround.
channel    → lay stone in seat → tap rail inward → mill walls flush → final
             polish with rubber wheel.
flush      → check depth → press stone → burnish surrounding metal → buff.
tension    → verify spring gap → press stone to seat; no burnishing required.
bar        → check bar spacing → slide stone into seat → tap bar ends.

Public API
----------
    setter_checklist(piece)  ->  list[dict]
        Return ordered list of setting steps.  Each step is a dict:
        {
          "stone_id":          str,
          "setting_type":      str,
          "sequence_rank":     int,       # 1 = first, higher = later
          "role":              str,       # "center", "accent", "halo", "side", "row"
          "instructions":      list[str], # ordered sub-steps
          "recommended_tools": list[str], # gravers, burnishers, etc.
          "time_estimate_min": float,
          "common_pitfalls":   list[str],
          "qc_checkpoints":    list[str],
        }

    tool_inventory(checklist)  ->  dict
        Aggregate every tool referenced across all steps.
        Returns {"tools": sorted list of unique tool names}.

    time_estimate_total(checklist)  ->  dict
        Sum all per-step time estimates.
        Returns {"total_min": float, "total_hr": float}.

Input schema (piece dict)
-------------------------
    {
      "stones": [
        {
          "id":           str,          # unique stone identifier, e.g. "centre_1"
          "setting_type": str,          # prong / bezel / pave / channel / flush /
                                        # tension / bar / bead_grain
          "role":         str,          # center / accent / halo / side / row
          "size_mm":      float,        # girdle diameter (round) or longest axis
          "stone_type":   str,          # diamond / ruby / emerald / sapphire / etc.
          "carat":        float,        # optional; used for pitfall notes
          "position":     str,          # optional; "top", "left", "right", "row_1"…
        },
        ...
      ],
      "piece_type":  str,               # ring / pendant / earrings / brooch / bangle
      "metal":       str,               # optional; 18k_yellow / platinum_950 / etc.
    }

Error convention
----------------
Functions never raise.  On bad input they return
``{"ok": False, "reason": str}`` for the top-level functions, or an error
dict for the LLM tools (err_payload).

LLM tools registered (gated)
-----------------------------
    jewelry_setter_checklist
    jewelry_tool_inventory
    jewelry_time_estimate_total
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

# ---------------------------------------------------------------------------
# Constants – setting type catalogue
# ---------------------------------------------------------------------------

_VALID_SETTING_TYPES = {
    "prong",
    "bezel",
    "pave",
    "channel",
    "flush",
    "tension",
    "bar",
    "bead_grain",
}

_VALID_ROLES = {"center", "accent", "halo", "side", "row"}

# Role → sequence priority (lower = set earlier).
_ROLE_PRIORITY: Dict[str, int] = {
    "center": 1,
    "side":   2,
    "accent": 3,
    "row":    4,
    "halo":   5,
}

# ---------------------------------------------------------------------------
# Per-setting workflow definitions
# ---------------------------------------------------------------------------

# Each workflow is a list of instruction strings.  {size} and {stone} are
# placeholders filled in at generation time.
_WORKFLOWS: Dict[str, List[str]] = {
    "prong": [
        "Seat-check: verify the stone sits level in the bearing ledge with no rocking.",
        "Confirm prong tips protrude {prong_raise_mm} mm above the girdle.",
        "Raise each prong tip with a flat graver, pushing metal over the girdle.",
        "Trim prong tips flush and even with a half-round needle file.",
        "Round prong tips with a {cup_bur_size} cup bur at low RPM.",
        "Burnish each prong tip toward the stone in a circular motion.",
        "Inspect under 10× loupe: all prongs contact the stone; no gaps.",
    ],
    "bezel": [
        "Seat-check: stone drops fully into bezel; girdle below collar top.",
        "Push the bezel wall inward at 12 o'clock with a pusher, then 6 o'clock.",
        "Push 9 o'clock, then 3 o'clock (opposite-wall sequence minimises distortion).",
        "Work around the remaining quarters, pushing at 45° intervals.",
        "Rub the bezel wall down with a burnisher using firm, overlapping strokes.",
        "File any high spots flush with a half-round needle file.",
        "Polish the bezel wall with a rubber wheel (320 grit then 600 grit).",
    ],
    "pave": [
        "Mark seat positions with a scriber or layout fluid.",
        "Drill each seat to {pave_drill_dia} mm with a ball bur, matching stone pavilion depth.",
        "Test-place each stone; girdle should sit {pave_seat_depth} mm below surface.",
        "Place the stone; raise a metal bead from each corner with a flat graver.",
        "Form each bead into a round dome with a {bead_tool_size} beading tool.",
        "Bright-cut the metal surface around each stone with a hart graver.",
        "Inspect under 10× loupe: four beads per stone; no stone movement.",
    ],
    "channel": [
        "Lay all stones in the channel without setting; verify even spacing.",
        "Check rail height: stone tables should sit 0.1–0.2 mm below rail tops.",
        "Starting from the centre stone, tap each rail inward with a channel pusher.",
        "Work alternating sides: left tap, right tap, advance one stone.",
        "Mill rail tops flush with a channel-mill bur.",
        "Finish with a rubber wheel along the rails to remove burr marks.",
        "Inspect: stones secure, no rotation; rail walls parallel.",
    ],
    "flush": [
        "Drill the seat with a ball bur to the stone's girdle diameter.",
        "Deepen the seat until the stone table sits flush with the metal surface.",
        "Place the stone; press firmly with a wooden pusher to seat fully.",
        "Burnish the surrounding metal lip inward over the girdle.",
        "Buff the surrounding area with a felt polishing stick.",
        "Inspect: no reflection gap around the girdle; stone does not spin.",
    ],
    "tension": [
        "Verify the spring gap matches the stone's girdle diameter ±0.05 mm.",
        "Clean the bearing grooves; remove any casting pits with a round graver.",
        "Press the stone firmly into the gap; it should click into the grooves.",
        "Confirm the stone does not rock or spin in any direction.",
        "No beads or prongs to raise; proceed directly to final polish.",
    ],
    "bar": [
        "Check bar spacing equals stone diameter (bars should just touch the girdle).",
        "Slide each stone into position between its two bars.",
        "Tap bar ends inward with a bar pusher to lock the stone.",
        "File any bar-end burrs flush with a needle file.",
        "Inspect: stones immobile; bar tops even; no day-light between bar and stone.",
    ],
    "bead_grain": [
        "Mark bead positions with a scriber.",
        "Drill each seat with a ball bur to stone diameter.",
        "Place the stone; raise metal beads around the girdle with a flat graver.",
        "Form beads with a {bead_tool_size} beading tool.",
        "Bright-cut the surrounding surface.",
        "Inspect: stone immobile; beads evenly spaced and sized.",
    ],
}

# ---------------------------------------------------------------------------
# Tool recommendations per setting type
# ---------------------------------------------------------------------------

_TOOLS: Dict[str, List[str]] = {
    "prong": [
        "flat graver (square, width ~0.5 mm)",
        "half-round needle file",
        "cup bur (diameter matched to prong tip)",
        "burnisher (straight)",
        "setting bur (matched to stone diameter)",
        "10× loupe",
        "plastic pusher (initial seating)",
    ],
    "bezel": [
        "bezel pusher (flat-face, hardened steel)",
        "burnisher (curved)",
        "half-round needle file",
        "rubber polishing wheel (320 grit)",
        "rubber polishing wheel (600 grit)",
        "10× loupe",
    ],
    "pave": [
        "ball bur (diameter = stone girdle diameter)",
        "hart graver (bright-cut)",
        "flat graver (bead raising)",
        "beading tool (size matched to stone)",
        "scriber",
        "layout fluid",
        "10× loupe",
        "setting tweezers",
    ],
    "channel": [
        "channel pusher",
        "channel-mill bur",
        "rubber polishing wheel",
        "half-round needle file",
        "setting bur (calibrated to stone)",
        "10× loupe",
    ],
    "flush": [
        "ball bur (stone diameter)",
        "wooden pusher",
        "burnisher (round-nose)",
        "felt polishing stick",
        "10× loupe",
    ],
    "tension": [
        "round graver",
        "wooden pusher",
        "calipers (0.01 mm resolution)",
        "10× loupe",
    ],
    "bar": [
        "bar pusher",
        "half-round needle file",
        "10× loupe",
    ],
    "bead_grain": [
        "ball bur (stone diameter)",
        "flat graver (bead raising)",
        "beading tool (size matched to stone)",
        "scriber",
        "10× loupe",
    ],
}

# ---------------------------------------------------------------------------
# Time estimates (minutes per stone, nominal)
# ---------------------------------------------------------------------------

_TIME_MIN: Dict[str, float] = {
    "prong":      8.0,
    "bezel":     12.0,
    "pave":       4.0,    # per stone in a pavé cluster
    "channel":    3.0,    # per stone in a channel run
    "flush":      5.0,
    "tension":    6.0,
    "bar":        4.0,
    "bead_grain": 4.0,
}

# Upscale factor for large stones (> 4 mm) — more care needed.
_LARGE_STONE_FACTOR = 1.5

# ---------------------------------------------------------------------------
# Common pitfalls per setting type
# ---------------------------------------------------------------------------

_PITFALLS: Dict[str, List[str]] = {
    "prong": [
        "Prong tip too high → stone rocks; re-check seat depth first.",
        "Over-burnishing a fragile stone (emerald, tanzanite) → corner chip; "
        "use a plastic pre-pusher before metal contact.",
        "Uneven prong heights → loose stone; measure with a loupe before burnishing.",
        "Cup bur too large → flattened prong tip instead of dome.",
    ],
    "bezel": [
        "Pushing one side only → oval distortion of the bezel collar.",
        "Bezel wall too short → stone pops out under pressure.",
        "Burnishing too fast → metal fold lines; use slow, firm overlapping strokes.",
        "Soft alloy (high-karat gold) → bezel creeps; anneal and push again.",
    ],
    "pave": [
        "Drill seat too shallow → stone sits proud; bead cannot cover girdle.",
        "Drill seat too deep → stone sinks; table below surface.",
        "Bead raised off-axis → stone tilts; re-raise and re-form bead.",
        "Adjacent stone too close → graver slips and chips neighbour stone.",
    ],
    "channel": [
        "Uneven rail height → stones rattle in channel.",
        "Tapping one rail too hard → channel bows; set both rails alternately.",
        "Calibrated stone diameter off → gap between adjacent stones.",
        "Milling too aggressive → rail becomes thin; risk of cracking.",
    ],
    "flush": [
        "Seat too wide → stone drops through.",
        "Seat too shallow → table proud; looks raised.",
        "Burnishing with too much force on a brittle stone → chip.",
    ],
    "tension": [
        "Gap too wide → stone falls out.",
        "Gap too narrow → stone cannot seat; risks cracking the shank.",
        "Sharp bearing edges → pressure fracture at girdle; ease edges with a round graver.",
    ],
    "bar": [
        "Bar spacing too wide → stone shifts laterally.",
        "Bar too thin → may crack under tap.",
        "Overtapping → bar leans and traps stone at an angle.",
    ],
    "bead_grain": [
        "Bead raised off-centre → covers pavilion facet not girdle.",
        "Uneven bead sizes → setting looks untidy; use consistent graver angle.",
        "Bright-cutting too deep → removes metal from seat; stone loosens.",
    ],
}

# ---------------------------------------------------------------------------
# QC checkpoints per setting type
# ---------------------------------------------------------------------------

_QC: Dict[str, List[str]] = {
    "prong": [
        "Stone does not rock or spin under fingernail pressure.",
        "All prong tips contact the stone evenly (no day-light under any prong).",
        "Prong tips rounded and polished — no file scratches visible.",
        "Table is parallel to the finger plane (ring pieces).",
    ],
    "bezel": [
        "Bezel wall fully closed — no gap visible at any angle.",
        "Stone does not rattle or rotate inside the bezel.",
        "Bezel wall height even all around (no high or low sections).",
        "Surface polished to pre-polish standard.",
    ],
    "pave": [
        "No stone movement under firm fingernail press from any direction.",
        "All beads rounded and evenly sized under 10× loupe.",
        "Bright-cut lines straight and consistent depth.",
        "No neighbouring stone damaged.",
    ],
    "channel": [
        "No stone movement lengthwise in channel.",
        "Rail tops flush and even across all stones.",
        "No gaps between adjacent stones (calibrated stone spacing).",
        "No burr marks on rail faces.",
    ],
    "flush": [
        "Stone table flush with surrounding metal surface (±0.05 mm).",
        "No rotation of stone in seat.",
        "No chipping at girdle visible under 10× loupe.",
    ],
    "tension": [
        "Stone cannot be dislodged by fingernail from any direction.",
        "Shank not distorted or bowed from pressing operation.",
    ],
    "bar": [
        "Bars upright and parallel — no lean.",
        "Each stone immobile between its bars.",
        "Bar-end faces flat and burr-free.",
    ],
    "bead_grain": [
        "All beads formed and evenly sized.",
        "No stone movement.",
        "Bright-cut surround clean and scratch-free.",
    ],
}

# ---------------------------------------------------------------------------
# Instruction placeholder helpers
# ---------------------------------------------------------------------------

_PRONG_RAISE_TABLE = [
    (0,   3.0,  0.3),
    (3.0, 5.0,  0.4),
    (5.0, 8.0,  0.5),
    (8.0, 99.0, 0.6),
]

_CUP_BUR_TABLE = [
    (0,   2.5,  "0.8 mm"),
    (2.5, 4.0,  "1.0 mm"),
    (4.0, 6.0,  "1.2 mm"),
    (6.0, 99.0, "1.4 mm"),
]

_PAVE_DRILL_TABLE = [
    (0,   2.0, "1.2 mm"),
    (2.0, 3.0, "1.8 mm"),
    (3.0, 4.0, "2.5 mm"),
    (4.0, 99.0, "3.0 mm"),
]

_PAVE_SEAT_DEPTH_TABLE = [
    (0,   2.0, "0.3 mm"),
    (2.0, 3.5, "0.5 mm"),
    (3.5, 99.0, "0.7 mm"),
]

_BEAD_TOOL_TABLE = [
    (0,   2.0, "#2 (0.6 mm)"),
    (2.0, 3.0, "#3 (0.8 mm)"),
    (3.0, 4.5, "#4 (1.0 mm)"),
    (4.5, 99.0, "#5 (1.2 mm)"),
]


def _lookup(table: list, size_mm: float, default: str = "matched") -> str:
    for lo, hi, val in table:
        if lo <= size_mm < hi:
            return val
    return default


def _render_instructions(setting_type: str, size_mm: float) -> List[str]:
    """Return workflow instructions with placeholders filled in."""
    templates = _WORKFLOWS.get(setting_type, ["Set the stone securely."])
    prong_raise = _lookup(_PRONG_RAISE_TABLE, size_mm, "0.4")
    cup_bur = _lookup(_CUP_BUR_TABLE, size_mm, "1.0 mm")
    pave_drill = _lookup(_PAVE_DRILL_TABLE, size_mm, "1.8 mm")
    pave_depth = _lookup(_PAVE_SEAT_DEPTH_TABLE, size_mm, "0.5 mm")
    bead_tool = _lookup(_BEAD_TOOL_TABLE, size_mm, "#3")

    result = []
    for t in templates:
        s = t.replace("{prong_raise_mm}", str(prong_raise))
        s = s.replace("{cup_bur_size}", cup_bur)
        s = s.replace("{pave_drill_dia}", pave_drill)
        s = s.replace("{pave_seat_depth}", pave_depth)
        s = s.replace("{bead_tool_size}", bead_tool)
        result.append(s)
    return result


def _time_for_stone(setting_type: str, size_mm: float) -> float:
    base = _TIME_MIN.get(setting_type, 6.0)
    if size_mm > 4.0:
        base = base * _LARGE_STONE_FACTOR
    return round(base, 1)


def _pitfalls_for_stone(setting_type: str, size_mm: float, stone_type: str, carat: float) -> List[str]:
    base = list(_PITFALLS.get(setting_type, []))
    # Diamond near prong tip for large carats
    if carat >= 1.0 and setting_type == "prong":
        base.append(
            f"Stone is {carat:.2f} ct — diamond near prong tip: risk of chipping; "
            "use a plastic pre-pusher before final metal contact."
        )
    # Brittle coloured stones
    if stone_type in {"emerald", "tanzanite", "opal", "pearl"} and setting_type in {"prong", "channel", "bar"}:
        base.append(
            f"{stone_type.capitalize()} is brittle (hardness ≤ 8 Mohs) — "
            "apply minimal pressure; use padded pusher jaws."
        )
    # Very small stones in pavé
    if size_mm < 1.5 and setting_type in {"pave", "bead_grain"}:
        base.append(
            "Stone diameter < 1.5 mm — work under at least 20× magnification; "
            "tweezers with locking mechanism recommended."
        )
    return base


# ---------------------------------------------------------------------------
# Core public function
# ---------------------------------------------------------------------------

def setter_checklist(piece: Any) -> Any:
    """
    Generate a sequenced setting checklist for a jewelry piece.

    Parameters
    ----------
    piece : dict
        Piece description.  See module docstring for full schema.

    Returns
    -------
    list[dict]
        Ordered list of per-stone setting steps, sorted by sequence_rank.
        Returns ``{"ok": False, "reason": str}`` on invalid input.
    """
    if not isinstance(piece, dict):
        return {"ok": False, "reason": "piece must be a dict"}

    stones = piece.get("stones")
    if not isinstance(stones, list) or len(stones) == 0:
        return {"ok": False, "reason": "piece.stones must be a non-empty list"}

    steps = []
    for idx, stone in enumerate(stones):
        if not isinstance(stone, dict):
            return {"ok": False, "reason": f"stone[{idx}] must be a dict"}

        stone_id = str(stone.get("id", f"stone_{idx + 1}"))
        setting_type = str(stone.get("setting_type", "prong")).lower().strip()
        role = str(stone.get("role", "accent")).lower().strip()
        size_mm = float(stone.get("size_mm", 3.0))
        stone_type = str(stone.get("stone_type", "diamond")).lower().strip()
        carat = float(stone.get("carat", 0.0))
        position = str(stone.get("position", ""))

        if setting_type not in _VALID_SETTING_TYPES:
            setting_type = "prong"  # graceful fallback
        if role not in _VALID_ROLES:
            role = "accent"
        if size_mm <= 0:
            size_mm = 3.0
        if carat < 0:
            carat = 0.0

        priority = _ROLE_PRIORITY.get(role, 3)

        steps.append({
            "_sort_key": (priority, -size_mm, idx),
            "stone_id":          stone_id,
            "setting_type":      setting_type,
            "role":              role,
            "size_mm":           size_mm,
            "stone_type":        stone_type,
            "carat":             carat,
            "position":          position,
        })

    # Sort by (role_priority, size descending, original index)
    steps.sort(key=lambda s: s["_sort_key"])

    checklist = []
    for rank, step in enumerate(steps, start=1):
        setting_type = step["setting_type"]
        size_mm = step["size_mm"]
        stone_type = step["stone_type"]
        carat = step["carat"]

        instructions = _render_instructions(setting_type, size_mm)
        tools = list(_TOOLS.get(setting_type, ["10× loupe"]))
        time_min = _time_for_stone(setting_type, size_mm)
        pitfalls = _pitfalls_for_stone(setting_type, size_mm, stone_type, carat)
        qc = list(_QC.get(setting_type, ["Verify stone is secure."]))

        checklist.append({
            "stone_id":          step["stone_id"],
            "setting_type":      setting_type,
            "sequence_rank":     rank,
            "role":              step["role"],
            "instructions":      instructions,
            "recommended_tools": tools,
            "time_estimate_min": time_min,
            "common_pitfalls":   pitfalls,
            "qc_checkpoints":    qc,
        })

    return checklist


# ---------------------------------------------------------------------------
# Aggregate helpers
# ---------------------------------------------------------------------------

def tool_inventory(checklist: Any) -> Any:
    """
    Aggregate every tool referenced in a checklist into a sorted unique list.

    Parameters
    ----------
    checklist : list[dict]
        The output of setter_checklist().

    Returns
    -------
    dict
        ``{"tools": [str, ...]}``, or ``{"ok": False, "reason": str}``.
    """
    if isinstance(checklist, dict) and not checklist.get("ok", True):
        return checklist
    if not isinstance(checklist, list):
        return {"ok": False, "reason": "checklist must be a list"}

    seen: set = set()
    for step in checklist:
        if not isinstance(step, dict):
            continue
        for tool in step.get("recommended_tools", []):
            seen.add(str(tool))

    return {"tools": sorted(seen)}


def time_estimate_total(checklist: Any) -> Any:
    """
    Sum all per-step time estimates.

    Parameters
    ----------
    checklist : list[dict]
        The output of setter_checklist().

    Returns
    -------
    dict
        ``{"total_min": float, "total_hr": float}``, or error dict.
    """
    if isinstance(checklist, dict) and not checklist.get("ok", True):
        return checklist
    if not isinstance(checklist, list):
        return {"ok": False, "reason": "checklist must be a list"}

    total = 0.0
    for step in checklist:
        if isinstance(step, dict):
            total += float(step.get("time_estimate_min", 0.0))

    return {
        "total_min": round(total, 1),
        "total_hr":  round(total / 60.0, 3),
    }


# ---------------------------------------------------------------------------
# LLM tool specs and runners
# ---------------------------------------------------------------------------

_setter_checklist_spec = ToolSpec(
    name="jewelry_setter_checklist",
    description=(
        "Generate a sequenced, bench-jeweller-friendly setting checklist for a "
        "finished jewelry piece.\n"
        "\n"
        "Returns an ordered list of per-stone setting steps.  Each step includes:\n"
        "  - stone_id and setting_type\n"
        "  - sequence_rank (center first, halo last)\n"
        "  - role (center / side / accent / row / halo)\n"
        "  - instructions — ordered sub-steps for that setting style\n"
        "  - recommended_tools — gravers, burs, burnishers, beading tools, etc.\n"
        "  - time_estimate_min — per-stone time in minutes\n"
        "  - common_pitfalls — risk notes specific to the stone/setting combination\n"
        "  - qc_checkpoints — what to check under the loupe before moving on\n"
        "\n"
        "Setting styles supported:\n"
        "  prong, bezel, pave, channel, flush, tension, bar, bead_grain\n"
        "\n"
        "Sequencing: center stone → sides → accents → row stones → halo stones.\n"
        "Within the same role, larger stones are set before smaller ones.\n"
        "\n"
        "Use jewelry_tool_inventory to get the aggregate tool list, and "
        "jewelry_time_estimate_total to get the overall time budget."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "piece": {
                "type": "object",
                "description": (
                    "Jewelry piece description.  Must contain a 'stones' list where "
                    "each stone has: id (str), setting_type (prong/bezel/pave/channel/"
                    "flush/tension/bar/bead_grain), role (center/accent/halo/side/row), "
                    "size_mm (float), stone_type (diamond/ruby/emerald/…), "
                    "carat (float, optional), position (str, optional)."
                ),
                "properties": {
                    "stones": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of stone descriptors.",
                    },
                    "piece_type": {
                        "type": "string",
                        "description": "ring / pendant / earrings / brooch / bangle.",
                    },
                    "metal": {
                        "type": "string",
                        "description": "Alloy key, e.g. '18k_yellow', 'platinum_950'.",
                    },
                },
                "required": ["stones"],
            },
        },
        "required": ["piece"],
    },
)


@register(_setter_checklist_spec, write=False)
async def run_jewelry_setter_checklist(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    piece = a.get("piece")
    if piece is None:
        return err_payload("piece is required", "BAD_ARGS")

    if not isinstance(piece, dict):
        return err_payload("piece must be a dict", "BAD_ARGS")

    stones = piece.get("stones")
    if not isinstance(stones, list) or len(stones) == 0:
        return err_payload("piece.stones must be a non-empty list", "BAD_ARGS")

    result = setter_checklist(piece)
    if isinstance(result, dict) and not result.get("ok", True):
        return err_payload(result["reason"], "BAD_ARGS")

    return ok_payload({"checklist": result, "step_count": len(result)})


# ---------------------------------------------------------------------------

_tool_inventory_spec = ToolSpec(
    name="jewelry_tool_inventory",
    description=(
        "Aggregate every tool referenced across a setter checklist into a "
        "sorted, deduplicated list.\n"
        "\n"
        "Pass the 'checklist' array returned by jewelry_setter_checklist.  "
        "Returns {'tools': [str, ...]} — the complete tool kit needed to set "
        "the entire piece."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "checklist": {
                "type": "array",
                "items": {"type": "object"},
                "description": "The checklist array from jewelry_setter_checklist.",
            },
        },
        "required": ["checklist"],
    },
)


@register(_tool_inventory_spec, write=False)
async def run_jewelry_tool_inventory(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    checklist = a.get("checklist")
    if checklist is None:
        return err_payload("checklist is required", "BAD_ARGS")

    if not isinstance(checklist, list):
        return err_payload("checklist must be a list", "BAD_ARGS")

    result = tool_inventory(checklist)
    if isinstance(result, dict) and not result.get("ok", True):
        return err_payload(result["reason"], "BAD_ARGS")

    return ok_payload(result)


# ---------------------------------------------------------------------------

_time_estimate_spec = ToolSpec(
    name="jewelry_time_estimate_total",
    description=(
        "Sum all per-stone time estimates from a setter checklist.\n"
        "\n"
        "Returns {'total_min': float, 'total_hr': float}."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "checklist": {
                "type": "array",
                "items": {"type": "object"},
                "description": "The checklist array from jewelry_setter_checklist.",
            },
        },
        "required": ["checklist"],
    },
)


@register(_time_estimate_spec, write=False)
async def run_jewelry_time_estimate_total(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    checklist = a.get("checklist")
    if checklist is None:
        return err_payload("checklist is required", "BAD_ARGS")

    if not isinstance(checklist, list):
        return err_payload("checklist must be a list", "BAD_ARGS")

    result = time_estimate_total(checklist)
    if isinstance(result, dict) and not result.get("ok", True):
        return err_payload(result["reason"], "BAD_ARGS")

    return ok_payload(result)
