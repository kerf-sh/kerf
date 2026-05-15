"""
3D STEP export for CircuitJSON boards (MCAD-ECAD co-design).

Builds a STEP assembly that represents the physical PCB:
  1. Board substrate   — edge_cuts outline (polygon / board rect) extruded to
                         ``board_thickness_mm`` (default 1.6 mm FR4).
  2. Drilled holes     — cylinders subtracted from the substrate using the same
                         hole coordinates as the Excellon writer.
  3. Component bodies  — each placed pcb_component gets a simple parametric
                         box (or the footprint-derived default dimensions) set
                         at its (x, y, z=thickness, rotation) on the board
                         surface.  If the element carries a ``step_model``
                         string attribute (path to a pre-existing STEP), that
                         file is imported instead of synthesising a box.

Output: a STEP AP214 file written via pythonOCC (``OCC.Core.*``).

pythonOCC availability gate
---------------------------
All OCC imports are deferred behind ``_OCC_AVAILABLE``.  Callers should check
that flag or let ``export_board_step`` raise ``RuntimeError`` with a clear
install message — matching the pattern in ``kerf_cad_core.occ_helpers``.

CircuitJSON elements consumed
------------------------------
  pcb_board / board            → board outline (width × height, center_x/y)
  pcb_outline_path             → explicit outline polygon
  pcb_via / pcb_plated_pad     → drilled holes (same extraction as excellon.py)
  pcb_hole / pcb_mounting_hole → drilled holes
  pcb_component                → placed component (x, y, rotation, layer/side)
  source_component             → footprint string used to estimate body size

Units: millimetres throughout; OCC operates in millimetres (STEP exports mm).
"""

from __future__ import annotations

import math
import os
from typing import Any

# ── OCC availability gate ──────────────────────────────────────────────────────

_OCC_AVAILABLE = False

try:
    from OCC.Core.BRepPrimAPI import (
        BRepPrimAPI_MakePrism,
        BRepPrimAPI_MakeCylinder,
        BRepPrimAPI_MakeBox,
    )
    from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCC.Core.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeWire,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_Transform,
    )
    from OCC.Core.gp import (
        gp_Pnt,
        gp_Vec,
        gp_Ax2,
        gp_Dir,
        gp_Trsf,
        gp_Ax1,
    )
    from OCC.Core.TopoDS import TopoDS_Compound
    from OCC.Core.BRep import BRep_Builder
    from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCC.Core.IFSelect import IFSelect_RetDone
    _OCC_AVAILABLE = True
except ImportError:
    pass


# ── board geometry extraction ─────────────────────────────────────────────────

def _board_outline_vertices(circuit_json: list[dict]) -> list[tuple[float, float]]:
    """Return the board outline as a list of (x, y) mm vertices.

    Priority:
      1. pcb_outline_path elements (explicit polygon)
      2. pcb_board / board element (bounding rectangle)
      3. 100×100 mm fallback
    """
    for el in circuit_json:
        if el.get("type") == "pcb_outline_path":
            pts_raw = el.get("route", el.get("points", el.get("vertices", [])))
            verts = [(float(p.get("x", 0)), float(p.get("y", 0))) for p in pts_raw]
            if len(verts) >= 3:
                return verts

    for el in circuit_json:
        if el.get("type") in ("pcb_board", "board"):
            w = float(el.get("width", 0))
            h = float(el.get("height", 0))
            cx = float(el.get("center_x", el.get("x", 0)))
            cy = float(el.get("center_y", el.get("y", 0)))
            if w > 0 and h > 0:
                x0, y0 = cx - w / 2, cy - h / 2
                x1, y1 = cx + w / 2, cy + h / 2
                return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    return [(0, 0), (100, 0), (100, 100), (0, 100)]


def _collect_holes(circuit_json: list[dict]) -> list[tuple[float, float, float]]:
    """Return list of (x_mm, y_mm, diameter_mm) for all drilled holes.

    Mirrors the logic in excellon._collect_hits (both plated and non-plated).
    """
    holes: list[tuple[float, float, float]] = []
    for el in circuit_json:
        t = el.get("type", "")
        if t == "pcb_via":
            x = float(el.get("x", 0.0))
            y = float(el.get("y", 0.0))
            d = float(el.get("hole_diameter", el.get("drill_diameter", el.get("drill", 0.3))))
            if d > 0:
                holes.append((x, y, d))
        elif t in ("pcb_plated_pad", "pcb_pad"):
            x = float(el.get("x", 0.0))
            y = float(el.get("y", 0.0))
            raw = el.get("hole_diameter", el.get("drill_diameter",
                         el.get("drill", el.get("drill_size", 0.0))))
            d = float(raw) if raw is not None else 0.0
            if d > 0:
                holes.append((x, y, d))
        elif t in ("pcb_hole", "pcb_mounting_hole"):
            x = float(el.get("x", 0.0))
            y = float(el.get("y", 0.0))
            d = float(el.get("hole_diameter", el.get("diameter", 3.2)))
            if d > 0:
                holes.append((x, y, d))
    return holes


def _collect_placed_components(circuit_json: list[dict]) -> list[dict]:
    """Return merged dicts for each placed pcb_component.

    Matches pnp._extract_components but adds footprint-bbox estimate.
    """
    source: dict[str, dict] = {}
    for el in circuit_json:
        if el.get("type") == "source_component":
            sid = el.get("source_component_id", el.get("id", ""))
            if sid:
                source[sid] = el

    placed: list[dict] = []
    for el in circuit_json:
        if el.get("type") != "pcb_component":
            continue
        sid = el.get("source_component_id", "")
        src = source.get(sid, {})

        refdes = src.get("name", src.get("refdes", el.get("name", sid or "?")))
        footprint = src.get("footprint", src.get("ftype", el.get("footprint", "")))
        step_model = el.get("step_model", src.get("step_model", ""))

        x = float(el.get("x", 0.0))
        y = float(el.get("y", 0.0))
        rotation_deg = float(el.get("rotation", 0.0))
        layer_attr = el.get("layer", "top_copper")
        side = "bottom" if ("bottom" in layer_attr or el.get("side", "") == "bottom") else "top"

        # Estimate component body dimensions from footprint name
        bw, bh, bz = _estimate_body_size(footprint)

        placed.append({
            "refdes": refdes,
            "footprint": footprint,
            "step_model": step_model,
            "x": x,
            "y": y,
            "rotation_deg": rotation_deg,
            "side": side,
            "body_w": bw,
            "body_h": bh,
            "body_z": bz,
        })
    return placed


# Footprint body size heuristic (width_mm, height_mm, height_z_mm)
_FOOTPRINT_SIZES: dict[str, tuple[float, float, float]] = {
    # Passives (IPC imperial → metric)
    "R_0201": (0.6, 0.3, 0.3),
    "C_0201": (0.6, 0.3, 0.3),
    "R_0402": (1.0, 0.5, 0.35),
    "C_0402": (1.0, 0.5, 0.5),
    "R_0603": (1.6, 0.8, 0.45),
    "C_0603": (1.6, 0.8, 0.8),
    "R_0805": (2.0, 1.25, 0.5),
    "C_0805": (2.0, 1.25, 1.25),
    "R_1206": (3.2, 1.6, 0.55),
    "C_1206": (3.2, 1.6, 1.6),
    # ICs (package families — best-effort)
    "SOT-23": (2.9, 1.6, 1.1),
    "SOT-23-5": (2.9, 1.6, 1.1),
    "SOT-23-6": (2.9, 1.6, 1.1),
    "SOIC-8": (5.0, 4.0, 1.75),
    "SOIC-16": (10.0, 4.0, 1.75),
    "TQFP-32": (9.0, 9.0, 1.2),
    "TQFP-44": (12.0, 12.0, 1.2),
    "TQFP-64": (14.0, 14.0, 1.2),
    "TQFP-100": (16.0, 16.0, 1.2),
    "QFN-16": (4.0, 4.0, 0.9),
    "QFN-32": (5.0, 5.0, 0.9),
    "QFN-48": (7.0, 7.0, 0.9),
    "LGA-16": (4.0, 4.0, 0.8),
    "BGA-64": (8.0, 8.0, 1.2),
    "BGA-100": (10.0, 10.0, 1.2),
    # Connectors (rough)
    "USB-A": (14.0, 6.5, 4.5),
    "USB-C": (9.0, 3.4, 3.1),
    "JST-PH-2": (4.5, 2.0, 6.0),
    # Default fallback defined in function below
}


def _estimate_body_size(footprint: str) -> tuple[float, float, float]:
    """Return (width_mm, length_mm, height_mm) for a component body box.

    Tries an exact match first, then a prefix match (e.g. "SOIC-8_..." → SOIC-8).
    Falls back to a 2.5 × 2.5 × 1.5 mm generic box.
    """
    fp = footprint.strip()
    if fp in _FOOTPRINT_SIZES:
        return _FOOTPRINT_SIZES[fp]
    # Try prefix stripping after first underscore-or-hyphen-delimited token
    for key in sorted(_FOOTPRINT_SIZES, key=len, reverse=True):
        if fp.startswith(key):
            return _FOOTPRINT_SIZES[key]
    return (2.5, 2.5, 1.5)  # generic fallback


# ── OCC geometry builders ─────────────────────────────────────────────────────

def _make_substrate(
    outline_verts: list[tuple[float, float]],
    thickness_mm: float,
) -> "TopoDS_Shape":
    """Extrude the board outline polygon to create the FR4 substrate solid."""
    from OCC.Core.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeWire,
        BRepBuilderAPI_MakeFace,
    )
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCC.Core.gp import gp_Pnt, gp_Vec

    # Ensure polygon is closed (first == last vertex OK to drop here)
    verts = list(outline_verts)
    if verts[0] != verts[-1]:
        verts.append(verts[0])  # close it

    # Build wire from line edges
    wire_builder = BRepBuilderAPI_MakeWire()
    for i in range(len(verts) - 1):
        x1, y1 = verts[i]
        x2, y2 = verts[i + 1]
        if abs(x1 - x2) < 1e-9 and abs(y1 - y2) < 1e-9:
            continue  # degenerate edge, skip
        p1 = gp_Pnt(x1, y1, 0.0)
        p2 = gp_Pnt(x2, y2, 0.0)
        edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
        wire_builder.Add(edge)

    wire = wire_builder.Wire()
    face = BRepBuilderAPI_MakeFace(wire, True).Face()
    prism = BRepPrimAPI_MakePrism(face, gp_Vec(0.0, 0.0, thickness_mm))
    return prism.Shape()


def _subtract_holes(
    substrate,
    holes: list[tuple[float, float, float]],
    thickness_mm: float,
) -> "TopoDS_Shape":
    """Subtract cylindrical drill holes from the substrate."""
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCC.Core.gp import gp_Ax2, gp_Pnt, gp_Dir

    result = substrate
    for (x, y, diameter) in holes:
        radius = diameter / 2.0
        # Place cylinder slightly below z=0 so it cuts all the way through
        ax = gp_Ax2(gp_Pnt(x, y, -0.1), gp_Dir(0, 0, 1))
        cyl = BRepPrimAPI_MakeCylinder(ax, radius, thickness_mm + 0.2).Shape()
        cut = BRepAlgoAPI_Cut(result, cyl)
        cut.Build()
        if cut.IsDone():
            result = cut.Shape()
    return result


def _make_component_box(
    x: float,
    y: float,
    z: float,
    bw: float,
    bh: float,
    bz: float,
    rotation_deg: float,
) -> "TopoDS_Shape":
    """Create a box representing a component body, centered at (x, y, z)."""
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCC.Core.gp import gp_Trsf, gp_Pnt, gp_Vec, gp_Ax1, gp_Dir

    # Box origin at lower-left corner → we'll center it
    box = BRepPrimAPI_MakeBox(
        gp_Pnt(x - bw / 2, y - bh / 2, z),
        bw, bh, bz,
    ).Shape()

    # Apply rotation about z-axis at component origin
    if abs(rotation_deg) > 1e-6:
        trsf = gp_Trsf()
        axis = gp_Ax1(gp_Pnt(x, y, z), gp_Dir(0, 0, 1))
        trsf.SetRotation(axis, math.radians(rotation_deg))
        transformer = BRepBuilderAPI_Transform(box, trsf, True)
        box = transformer.Shape()

    return box


def _import_step_model(step_path: str, x: float, y: float, z: float,
                        rotation_deg: float) -> "TopoDS_Shape | None":
    """Import an external STEP model and place it at the given position."""
    try:
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCC.Core.gp import gp_Trsf, gp_Vec, gp_Ax1, gp_Pnt, gp_Dir

        reader = STEPControl_Reader()
        status = reader.ReadFile(step_path)
        if status != IFSelect_RetDone:
            return None
        reader.TransferRoots()
        shape = reader.OneShape()

        # Translate to (x, y, z)
        trsf = gp_Trsf()
        trsf.SetTranslation(gp_Vec(x, y, z))
        shape = BRepBuilderAPI_Transform(shape, trsf, True).Shape()

        # Rotate about z if needed
        if abs(rotation_deg) > 1e-6:
            rot = gp_Trsf()
            rot.SetRotation(gp_Ax1(gp_Pnt(x, y, z), gp_Dir(0, 0, 1)),
                            math.radians(rotation_deg))
            shape = BRepBuilderAPI_Transform(shape, rot, True).Shape()

        return shape
    except Exception:
        return None


# ── compound builder ─────────────────────────────────────────────────────────

def _build_compound(shapes) -> "TopoDS_Compound":
    """Combine multiple OCC shapes into a single compound."""
    from OCC.Core.TopoDS import TopoDS_Compound
    from OCC.Core.BRep import BRep_Builder

    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for s in shapes:
        builder.Add(compound, s)
    return compound


# ── public API ────────────────────────────────────────────────────────────────

def export_board_step(
    circuit_json: list[dict],
    output_path: str,
    board_thickness_mm: float = 1.6,
    drill_holes: bool = True,
    place_components: bool = True,
) -> dict:
    """Export a 3D STEP assembly for a CircuitJSON PCB board.

    Builds: substrate (edge_cuts extruded to ``board_thickness_mm``), drilled
    holes subtracted from it, and a parametric box body per placed component
    (or the component's ``step_model`` STEP file if provided).

    Args:
        circuit_json: Parsed CircuitJSON array (tscircuit PCB data model).
        output_path: Destination STEP file path (e.g. ``"board.step"``).
        board_thickness_mm: PCB substrate thickness in mm.  Default 1.6 mm.
        drill_holes: Whether to subtract drill holes from the substrate.
        place_components: Whether to add component body solids.

    Returns:
        dict with keys:
          ``output_path``      — the path written
          ``substrate_volume`` — approximate volume (mm³, float)
          ``hole_count``       — number of drill holes applied
          ``component_count``  — number of placed component bodies added
          ``occ_available``    — True (always True here; RuntimeError if not)

    Raises:
        RuntimeError: if pythonOCC is not installed.
        RuntimeError: if the STEP file cannot be written.
    """
    if not _OCC_AVAILABLE:
        raise RuntimeError(
            "pythonOCC not installed — cannot export STEP. "
            "Install with: conda install -c conda-forge pythonocc-core"
        )

    if not isinstance(circuit_json, list):
        circuit_json = []

    # 1. Extract geometry from CircuitJSON
    outline = _board_outline_vertices(circuit_json)
    holes = _collect_holes(circuit_json) if drill_holes else []
    components = _collect_placed_components(circuit_json) if place_components else []

    # 2. Build substrate solid
    substrate = _make_substrate(outline, board_thickness_mm)

    # 3. Subtract holes
    if holes:
        substrate = _subtract_holes(substrate, holes, board_thickness_mm)

    # 4. Build component bodies
    all_shapes = [substrate]
    placed_count = 0

    for comp in components:
        z_offset = board_thickness_mm  # top of board surface

        # Bottom-side components hang below the board
        if comp["side"] == "bottom":
            z_offset = -comp["body_z"]

        # Prefer an explicit STEP model if available and the file exists
        body_shape = None
        if comp["step_model"] and os.path.isfile(comp["step_model"]):
            body_shape = _import_step_model(
                comp["step_model"],
                comp["x"], comp["y"], z_offset,
                comp["rotation_deg"],
            )

        if body_shape is None:
            body_shape = _make_component_box(
                comp["x"], comp["y"], z_offset,
                comp["body_w"], comp["body_h"], comp["body_z"],
                comp["rotation_deg"],
            )

        all_shapes.append(body_shape)
        placed_count += 1

    # 5. Combine into a compound
    assembly = _build_compound(all_shapes)

    # 6. Write STEP file
    from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCC.Core.IFSelect import IFSelect_RetDone

    writer = STEPControl_Writer()
    writer.Transfer(assembly, STEPControl_AsIs)
    status = writer.Write(output_path)

    if status != IFSelect_RetDone:
        raise RuntimeError(
            f"STEPControl_Writer failed writing {output_path!r} (status={status})"
        )

    # Rough substrate volume (bounding-box approximation for the flat board)
    # Full BRep volume calculation requires GProp which is an optional extra dep;
    # approximate as board_area × thickness instead.
    xs = [v[0] for v in outline]
    ys = [v[1] for v in outline]
    approx_area = (max(xs) - min(xs)) * (max(ys) - min(ys))
    approx_volume = approx_area * board_thickness_mm

    return {
        "output_path": output_path,
        "substrate_volume": round(approx_volume, 4),
        "hole_count": len(holes),
        "component_count": placed_count,
        "occ_available": True,
    }
