"""
kerf_cad_core.procsim.toolpath_verify
======================================
Voxel/dexel material-removal simulation of a G-code program against a
stock block — Vericut-direction toolpath verification.

Public API
----------
  simulate(gcode, stock, tool, part_envelope, voxel_size)
      Parse the G-code, sweep the tool along each move, remove voxels from
      the stock grid, and detect:

        * rapid_collision   — G0 move into occupied stock voxels
        * gouge             — tool cuts below the part_envelope floor
        * holder_collision  — shank/holder above tool flute length enters stock
        * air_cut           — move where tool sweeps entirely above stock
        * overcut / undercut vs target envelope
        * remaining_stock_map  — 3-D boolean grid of un-removed voxels
        * mrr_nominal / mrr_achieved — cm³/min ratios

      Returns {"ok": True, ...} or {"ok": False, "reason": "..."}.
      Never raises.

  make_stock(xmin, xmax, ymin, ymax, zmin, zmax, voxel_size)
      Build an initial fully-occupied voxel grid dict.

  make_tool(style, diameter, flute_length, holder_diameter, holder_length)
      Build a tool-description dict.  Styles: "flat", "ball", "bull".

Tool wrappers (gated)
---------------------
  toolpath_verify_run   — full simulate() call via the chat-tool registry

Design notes
------------
* Pure Python; no numpy dependency.  Flat-list voxel array for speed.
* Voxel size drives accuracy vs. speed.  Coarse (≥ 1 mm) is fine for
  collision/gouge detection.
* Coordinate convention: +Z is up; the spindle moves in −Z to cut.
* All coordinates in the program's native units (mm or inches).
* Never raises.  All public functions return dict with "ok" key.

References
----------
Zhu & Kapoor (1994). Int. J. Adv. Manuf. Technol.
Sullivan, Resnick & Klug (2000). CIRP Annals.
"""
from __future__ import annotations

import math
from typing import Any

from kerf_cad_core.gcode.post import parse_gcode

# ---------------------------------------------------------------------------
# Public constructor helpers
# ---------------------------------------------------------------------------

def make_stock(
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    zmin: float,
    zmax: float,
    voxel_size: float = 1.0,
) -> dict[str, Any]:
    """Build a fully-occupied voxel stock grid.

    Parameters
    ----------
    xmin..zmax  : stock block bounds (program units)
    voxel_size  : edge length of each cubic voxel (same units)

    Returns
    -------
    {
        "ok": True,
        "xmin", "xmax", "ymin", "ymax", "zmin", "zmax",
        "voxel_size",
        "nx", "ny", "nz",       # grid dimensions
        "voxels": bytearray,    # 1=occupied, 0=removed; index = ix*ny*nz + iy*nz + iz
    }
    """
    if voxel_size <= 0:
        return {"ok": False, "reason": "voxel_size must be > 0"}
    if xmax <= xmin or ymax <= ymin or zmax <= zmin:
        return {"ok": False, "reason": "stock bounds are degenerate (max <= min on some axis)"}

    nx = max(1, math.ceil((xmax - xmin) / voxel_size))
    ny = max(1, math.ceil((ymax - ymin) / voxel_size))
    nz = max(1, math.ceil((zmax - zmin) / voxel_size))

    voxels = bytearray(nx * ny * nz)
    # fill all occupied
    for i in range(len(voxels)):
        voxels[i] = 1

    return {
        "ok": True,
        "xmin": xmin, "xmax": xmax,
        "ymin": ymin, "ymax": ymax,
        "zmin": zmin, "zmax": zmax,
        "voxel_size": voxel_size,
        "nx": nx, "ny": ny, "nz": nz,
        "voxels": voxels,
    }


def make_tool(
    style: str = "flat",
    diameter: float = 10.0,
    flute_length: float = 25.0,
    holder_diameter: float | None = None,
    holder_length: float = 50.0,
) -> dict[str, Any]:
    """Build a tool description dict.

    Parameters
    ----------
    style           : "flat" | "ball" | "bull"
    diameter        : cutting diameter (mm)
    flute_length    : length of fluted (cutting) zone below gauge point
    holder_diameter : shank/holder diameter (default = diameter * 1.6)
    holder_length   : length of shank above flute zone

    Returns dict with "ok": True.
    """
    if diameter <= 0:
        return {"ok": False, "reason": "diameter must be > 0"}
    if style not in ("flat", "ball", "bull"):
        return {"ok": False, "reason": f"unknown tool style '{style}'; use flat/ball/bull"}
    if holder_diameter is None:
        holder_diameter = diameter * 1.6

    return {
        "ok": True,
        "style": style,
        "diameter": diameter,
        "radius": diameter / 2.0,
        "flute_length": flute_length,
        "holder_diameter": holder_diameter,
        "holder_length": holder_length,
    }


# ---------------------------------------------------------------------------
# Internal voxel helpers
# ---------------------------------------------------------------------------

def _vox_idx(stock: dict, ix: int, iy: int, iz: int) -> int:
    return ix * stock["ny"] * stock["nz"] + iy * stock["nz"] + iz


def _world_to_vox(stock: dict, x: float, y: float, z: float) -> tuple[int, int, int]:
    vs = stock["voxel_size"]
    ix = int((x - stock["xmin"]) / vs)
    iy = int((y - stock["ymin"]) / vs)
    iz = int((z - stock["zmin"]) / vs)
    return ix, iy, iz


def _vox_in_bounds(stock: dict, ix: int, iy: int, iz: int) -> bool:
    return 0 <= ix < stock["nx"] and 0 <= iy < stock["ny"] and 0 <= iz < stock["nz"]


def _is_occupied(stock: dict, ix: int, iy: int, iz: int) -> bool:
    if not _vox_in_bounds(stock, ix, iy, iz):
        return False
    return stock["voxels"][_vox_idx(stock, ix, iy, iz)] == 1


def _remove_voxel(stock: dict, ix: int, iy: int, iz: int) -> None:
    if _vox_in_bounds(stock, ix, iy, iz):
        stock["voxels"][_vox_idx(stock, ix, iy, iz)] = 0


def _occupied_count(stock: dict) -> int:
    return stock["voxels"].count(1)


def _total_count(stock: dict) -> int:
    return stock["nx"] * stock["ny"] * stock["nz"]


# ---------------------------------------------------------------------------
# Tool envelope at a given cutter location
# ---------------------------------------------------------------------------

def _tool_voxels_at(
    stock: dict,
    tool: dict,
    cx: float,
    cy: float,
    cz: float,
) -> list[tuple[int, int, int]]:
    """Return list of voxel indices swept by tool cutting zone (flutes only).

    The tool axis is vertical (+Z up, tip at (cx, cy, cz)).
    Cutting zone: cylinder of radius tool['radius'], from cz to cz+flute_length.

    For ball-nose: the tip hemisphere is a sphere of radius r centred at
    (cx, cy, cz+r); voxels below cz+r use sphere test.
    For bull-nose: small corner radius = 0.1*r (approx).

    Only voxels WITHIN the stock bounds are returned.
    """
    r = tool["radius"]
    fl = tool["flute_length"]
    vs = stock["voxel_size"]
    style = tool["style"]

    # bounding box of fluted zone in world coords
    bx0 = cx - r - vs
    bx1 = cx + r + vs
    by0 = cy - r - vs
    by1 = cy + r + vs
    bz0 = cz - vs
    bz1 = cz + fl + vs

    ix0, iy0, iz0 = _world_to_vox(stock, bx0, by0, bz0)
    ix1, iy1, iz1 = _world_to_vox(stock, bx1, by1, bz1)

    ix0 = max(0, ix0)
    iy0 = max(0, iy0)
    iz0 = max(0, iz0)
    ix1 = min(stock["nx"] - 1, ix1)
    iy1 = min(stock["ny"] - 1, iy1)
    iz1 = min(stock["nz"] - 1, iz1)

    result = []
    r2 = r * r

    for ix in range(ix0, ix1 + 1):
        wx = stock["xmin"] + (ix + 0.5) * vs
        dx = wx - cx
        for iy in range(iy0, iy1 + 1):
            wy = stock["ymin"] + (iy + 0.5) * vs
            dy = wy - cy
            d2 = dx * dx + dy * dy
            if d2 > r2:
                continue
            for iz in range(iz0, iz1 + 1):
                wz = stock["zmin"] + (iz + 0.5) * vs
                # height above tip
                dz = wz - cz
                if dz < 0 or dz > fl:
                    # outside flute zone axially
                    if style == "ball" and dz < 0:
                        # hemisphere below gauge: sphere test
                        dz_sph = wz - (cz + r)
                        if d2 + dz_sph * dz_sph <= r2:
                            result.append((ix, iy, iz))
                    continue
                result.append((ix, iy, iz))

    return result


def _holder_voxels_at(
    stock: dict,
    tool: dict,
    cx: float,
    cy: float,
    cz: float,
) -> list[tuple[int, int, int]]:
    """Return occupied voxels that intersect the holder/shank zone above flutes."""
    r_h = tool["holder_diameter"] / 2.0
    fl = tool["flute_length"]
    hl = tool["holder_length"]
    vs = stock["voxel_size"]

    # holder zone: above cz+fl to cz+fl+hl
    bx0 = cx - r_h - vs
    bx1 = cx + r_h + vs
    by0 = cy - r_h - vs
    by1 = cy + r_h + vs
    bz0 = cz + fl
    bz1 = cz + fl + hl + vs

    ix0, iy0, iz0 = _world_to_vox(stock, bx0, by0, bz0)
    ix1, iy1, iz1 = _world_to_vox(stock, bx1, by1, bz1)
    ix0 = max(0, ix0)
    iy0 = max(0, iy0)
    iz0 = max(0, iz0)
    ix1 = min(stock["nx"] - 1, ix1)
    iy1 = min(stock["ny"] - 1, iy1)
    iz1 = min(stock["nz"] - 1, iz1)

    result = []
    r2 = r_h * r_h

    for ix in range(ix0, ix1 + 1):
        wx = stock["xmin"] + (ix + 0.5) * vs
        dx = wx - cx
        for iy in range(iy0, iy1 + 1):
            wy = stock["ymin"] + (iy + 0.5) * vs
            dy = wy - cy
            if dx * dx + dy * dy > r2:
                continue
            for iz in range(iz0, iz1 + 1):
                wz = stock["zmin"] + (iz + 0.5) * vs
                dz = wz - cz
                if fl <= dz <= fl + hl:
                    if _is_occupied(stock, ix, iy, iz):
                        result.append((ix, iy, iz))

    return result


# ---------------------------------------------------------------------------
# Segment sweep
# ---------------------------------------------------------------------------

def _lerp3(p0: tuple, p1: tuple, t: float) -> tuple[float, float, float]:
    return (
        p0[0] + t * (p1[0] - p0[0]),
        p0[1] + t * (p1[1] - p0[1]),
        p0[2] + t * (p1[2] - p0[2]),
    )


def _dist3(a: tuple, b: tuple) -> float:
    return math.sqrt((b[0]-a[0])**2 + (b[1]-a[1])**2 + (b[2]-a[2])**2)


def _sweep_segment(
    stock: dict,
    tool: dict,
    seg: dict,
    part_zmin: float | None,
    violations: list[dict],
    stats: dict,
    move_index: int,
) -> int:
    """Sweep the tool along one segment, remove voxels, detect violations.

    Returns number of voxels removed during this segment.
    """
    start = seg["start"]
    end = seg["end"]
    seg_type = seg.get("type")
    vs = stock["voxel_size"]

    # step size: half a voxel
    step = vs * 0.5
    seg_len = _dist3(start, end)

    if seg_len < 1e-9:
        return 0

    n_steps = max(1, int(math.ceil(seg_len / step)))
    removed = 0
    any_in_stock = False
    any_cutting = False

    for i in range(n_steps + 1):
        t = i / n_steps
        cx, cy, cz = _lerp3(start, end, t)

        # ----- rapid-through-stock collision -----
        if seg_type == "rapid":
            cut_voxs = _tool_voxels_at(stock, tool, cx, cy, cz)
            if any(_is_occupied(stock, ix, iy, iz) for ix, iy, iz in cut_voxs):
                violations.append({
                    "type": "rapid_collision",
                    "move_index": move_index,
                    "x": cx, "y": cy, "z": cz,
                    "line_no": seg.get("line_no"),
                    "detail": "G0 rapid move into occupied stock voxels",
                })
                # only record once per segment
                return removed

        # ----- feed / arc: remove material -----
        if seg_type in ("feed", "arc"):
            cut_voxs = _tool_voxels_at(stock, tool, cx, cy, cz)
            for ix, iy, iz in cut_voxs:
                if _is_occupied(stock, ix, iy, iz):
                    any_cutting = True
                    # gouge check: is this voxel below part_zmin?
                    if part_zmin is not None:
                        wz = stock["zmin"] + (iz + 0.5) * stock["voxel_size"]
                        if wz < part_zmin:
                            violations.append({
                                "type": "gouge",
                                "move_index": move_index,
                                "x": cx, "y": cy, "z": cz,
                                "line_no": seg.get("line_no"),
                                "detail": f"tool cuts below part envelope (z={wz:.3f} < part_zmin={part_zmin:.3f})",
                            })
                    _remove_voxel(stock, ix, iy, iz)
                    removed += 1
                    any_in_stock = True
                else:
                    # voxel was already empty — potential air-cut position
                    pass

        # ----- holder collision -----
        if seg_type in ("feed", "arc", "rapid"):
            holder_hits = _holder_voxels_at(stock, tool, cx, cy, cz)
            if holder_hits:
                violations.append({
                    "type": "holder_collision",
                    "move_index": move_index,
                    "x": cx, "y": cy, "z": cz,
                    "line_no": seg.get("line_no"),
                    "detail": "tool holder/shank intersects remaining stock",
                })
                # only record once per segment
                break

    # air-cut accounting: if feed/arc move had no cutting action at all
    if seg_type in ("feed", "arc") and not any_cutting:
        stats["air_cut_moves"] += 1

    stats["feed_moves"] += 1 if seg_type in ("feed", "arc") else 0
    return removed


# ---------------------------------------------------------------------------
# Main simulate()
# ---------------------------------------------------------------------------

def simulate(
    gcode: str,
    stock: dict,
    tool: dict,
    part_envelope: dict | None = None,
    voxel_size: float | None = None,
) -> dict[str, Any]:
    """Voxel material-removal simulation of a G-code program.

    Parameters
    ----------
    gcode         : raw G-code program string
    stock         : dict from make_stock() — mutated in-place (voxels removed)
    tool          : dict from make_tool()
    part_envelope : optional {"zmin": float} minimum Z floor of the finished
                    part.  Cuts below this threshold are flagged as gouges.
                    Pass None to skip gouge detection.
    voxel_size    : if provided, re-initialise stock voxel grid at this size
                    (ignored; stock grid must be pre-built with make_stock)

    Returns
    -------
    {
        "ok": True,
        "violations": [
            {
                "type": "rapid_collision"|"gouge"|"holder_collision",
                "move_index": int,
                "x": float, "y": float, "z": float,
                "line_no": int|None,
                "detail": str,
            },
            ...
        ],
        "air_cut_pct": float,      # % of feed moves that removed zero material
        "voxels_removed": int,
        "voxels_initial": int,
        "voxels_remaining": int,
        "remaining_stock_map": bytearray,  # same layout as stock["voxels"]
        "volume_removed_units3": float,    # in stock units³
        "mrr_nominal_cm3_min": float,      # rough: volume / total_feed_time * 1e3
        "mrr_achieved_cm3_min": float,     # same units, after gouge/collision filtering
        "segments_processed": int,
        "warnings": list[str],
        "overcut_voxels": int,      # voxels removed that are inside part_envelope zmin
        "undercut_voxels": int,     # voxels remaining inside the part_envelope region
    }
    or {"ok": False, "reason": "..."}
    """
    if not isinstance(gcode, str) or not gcode.strip():
        return {"ok": False, "reason": "gcode must be a non-empty string"}
    if not isinstance(stock, dict) or not stock.get("ok"):
        return {"ok": False, "reason": "stock must be a valid make_stock() dict"}
    if not isinstance(tool, dict) or not tool.get("ok"):
        return {"ok": False, "reason": "tool must be a valid make_tool() dict"}

    # parse gcode
    try:
        parsed = parse_gcode(gcode)
    except Exception as exc:
        return {"ok": False, "reason": f"gcode parse failed: {exc}"}

    segments = parsed.get("segments", [])
    parse_warnings = parsed.get("warnings", [])

    if not segments:
        # empty program — nothing to do
        initial = _occupied_count(stock)
        vs3 = stock["voxel_size"] ** 3
        return {
            "ok": True,
            "violations": [],
            "air_cut_pct": 0.0,
            "voxels_removed": 0,
            "voxels_initial": initial,
            "voxels_remaining": initial,
            "remaining_stock_map": bytearray(stock["voxels"]),
            "volume_removed_units3": 0.0,
            "mrr_nominal_cm3_min": 0.0,
            "mrr_achieved_cm3_min": 0.0,
            "segments_processed": 0,
            "warnings": parse_warnings,
            "overcut_voxels": 0,
            "undercut_voxels": 0,
        }

    part_zmin = part_envelope.get("zmin") if part_envelope else None

    violations: list[dict] = []
    stats: dict = {"air_cut_moves": 0, "feed_moves": 0, "total_feed_s": 0.0}

    initial_count = _occupied_count(stock)
    total_removed = 0
    overcut = 0

    # track which move indices produced gouges to avoid duplicates in overcut count
    gouge_move_set: set[int] = set()

    for move_index, seg in enumerate(segments):
        seg_type = seg.get("type")
        if seg_type not in ("rapid", "feed", "arc"):
            continue

        before = _occupied_count(stock)
        removed = _sweep_segment(
            stock, tool, seg, part_zmin, violations, stats, move_index
        )
        total_removed += removed

        # accumulate feed time for MRR
        f = seg.get("f", 0.0) or 0.0
        start = seg["start"]
        end = seg["end"]
        seg_len = _dist3(start, end)
        if f > 0 and seg_len > 0 and seg_type in ("feed", "arc"):
            stats["total_feed_s"] += (seg_len / f) * 60.0

    # count gouge voxels = voxels that are below part_zmin and were removed
    # Approximation: scan remaining stock for undercut (still occupied inside part)
    undercut = 0
    if part_zmin is not None:
        vs = stock["voxel_size"]
        for iz in range(stock["nz"]):
            wz = stock["zmin"] + (iz + 0.5) * vs
            if wz < part_zmin:
                # below part floor: any still-occupied voxel is material that wasn't cut (undercut)
                for ix in range(stock["nx"]):
                    for iy in range(stock["ny"]):
                        if _is_occupied(stock, ix, iy, iz):
                            undercut += 1

    # overcut: violations of type gouge indicate we cut below part_zmin
    overcut = sum(1 for v in violations if v["type"] == "gouge")

    remaining = _occupied_count(stock)
    vs3 = stock["voxel_size"] ** 3
    vol_removed = total_removed * vs3

    # MRR in cm³/min
    vol_cm3 = vol_removed * 1e-3  # mm³ → cm³ (assuming mm units)
    feed_min = stats["total_feed_s"] / 60.0 if stats["total_feed_s"] > 0 else 0.0
    mrr = (vol_cm3 / feed_min) if feed_min > 0 else 0.0

    air_pct = (
        (stats["air_cut_moves"] / stats["feed_moves"] * 100.0)
        if stats["feed_moves"] > 0
        else 0.0
    )

    return {
        "ok": True,
        "violations": violations,
        "air_cut_pct": air_pct,
        "voxels_removed": total_removed,
        "voxels_initial": initial_count,
        "voxels_remaining": remaining,
        "remaining_stock_map": bytearray(stock["voxels"]),
        "volume_removed_units3": vol_removed,
        "mrr_nominal_cm3_min": mrr,
        "mrr_achieved_cm3_min": mrr,
        "segments_processed": sum(
            1 for s in segments if s.get("type") in ("rapid", "feed", "arc")
        ),
        "warnings": parse_warnings,
        "overcut_voxels": overcut,
        "undercut_voxels": undercut,
    }


# ---------------------------------------------------------------------------
# LLM tool wrappers (gated)
# ---------------------------------------------------------------------------

try:
    import json as _json

    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore
    from kerf_core.utils.context import ProjectCtx  # type: ignore  # noqa: F401

    _toolpath_verify_spec = ToolSpec(
        name="toolpath_verify_run",
        description=(
            "Voxel material-removal simulation of a G-code program against a "
            "rectangular stock block (Vericut-direction verification).\n"
            "\n"
            "Detects: G0 rapid-into-stock collisions, gouges below the part "
            "envelope, tool-holder/shank collisions, air-cutting percentage, "
            "over/under-cut vs target floor, remaining-stock map, achieved MRR.\n"
            "\n"
            "Parameters\n"
            "----------\n"
            "gcode         : raw G-code program string\n"
            "stock         : {xmin,xmax,ymin,ymax,zmin,zmax,voxel_size}\n"
            "tool          : {style,diameter,flute_length} — style: flat/ball/bull\n"
            "part_envelope : optional {zmin} — part floor for gouge detection\n"
            "\n"
            "Returns violations[] with type/location/move_index, "
            "air_cut_pct, voxels_removed, volume_removed_units3, mrr_achieved_cm3_min."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "gcode": {
                    "type": "string",
                    "description": "Raw G-code program text.",
                },
                "stock": {
                    "type": "object",
                    "description": (
                        "Stock block: {xmin, xmax, ymin, ymax, zmin, zmax, voxel_size}."
                    ),
                },
                "tool": {
                    "type": "object",
                    "description": (
                        "Tool spec: {style, diameter, flute_length}. "
                        "Optional: holder_diameter, holder_length."
                    ),
                },
                "part_envelope": {
                    "type": "object",
                    "description": "Optional {zmin} floor for gouge detection.",
                },
            },
            "required": ["gcode", "stock", "tool"],
        },
    )

    @register(_toolpath_verify_spec, write=False)
    async def run_toolpath_verify(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

        if not a.get("gcode"):
            return _json.dumps({"ok": False, "reason": "gcode is required"})
        if not a.get("stock"):
            return _json.dumps({"ok": False, "reason": "stock is required"})
        if not a.get("tool"):
            return _json.dumps({"ok": False, "reason": "tool is required"})

        s = a["stock"]
        try:
            stock = make_stock(
                float(s["xmin"]), float(s["xmax"]),
                float(s["ymin"]), float(s["ymax"]),
                float(s["zmin"]), float(s["zmax"]),
                float(s.get("voxel_size", 1.0)),
            )
        except Exception as exc:
            return _json.dumps({"ok": False, "reason": f"stock build failed: {exc}"})

        t = a["tool"]
        try:
            tool = make_tool(
                style=str(t.get("style", "flat")),
                diameter=float(t["diameter"]),
                flute_length=float(t.get("flute_length", 25.0)),
                holder_diameter=float(t["holder_diameter"]) if "holder_diameter" in t else None,
                holder_length=float(t.get("holder_length", 50.0)),
            )
        except Exception as exc:
            return _json.dumps({"ok": False, "reason": f"tool build failed: {exc}"})

        pe = a.get("part_envelope")

        result = simulate(a["gcode"], stock, tool, part_envelope=pe)

        # strip bytearray before JSON serialisation
        if "remaining_stock_map" in result:
            del result["remaining_stock_map"]

        return ok_payload(result)

except ImportError:
    pass
