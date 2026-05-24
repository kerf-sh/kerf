"""
kerf_bim.walls — Full parametric compound-wall model (T-111).

Promotes the basic wall primitive to a fully parametric compound-layered
wall matching Revit's ``Basic Wall`` + ``Compound Wall`` types.

Wall anatomy
------------
A compound wall is a stack of ordered material layers, each with a
thickness and a function code (see :class:`LayerFunction`).  The total
wall thickness is the sum of layer thicknesses.

IFC mapping
-----------
:func:`wall_to_ifc_dict` converts a :class:`CompoundWall` into the dict
schema accepted by :mod:`kerf_bim.export_ifc.writer`.  Compound-layer
data is embedded as ``wall_type`` and ``layers`` keys (informational;
the exporter renders the geometry using total thickness).

Reference
---------
Autodesk Revit 2024 — Wall Types and Structure documentation.
ISO 16739-1:2018 (IFC4) — ``IfcWall``, ``IfcWallType``, ``IfcMaterialLayerSet``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Tuple

__all__ = [
    "LayerFunction",
    "WallLayer",
    "CompoundWall",
    "WallInstance",
    "WallValidationError",
    "WallLayerGeometry",
    "make_compound_wall",
    "make_wall_instance",
    "wall_to_ifc_dict",
    "wall_layer_faces",
    # Preset factory
    "PRESET_WALLS",
]

# ---------------------------------------------------------------------------
# Layer function codes (Revit convention)
# ---------------------------------------------------------------------------

LayerFunction = Literal[
    "structure",      # main structural layer
    "substrate",      # sheathing / deck
    "thermal",        # insulation
    "finish1",        # primary finish (exterior face)
    "finish2",        # secondary finish (interior face)
    "membrane",       # moisture / vapour barrier
    "air_gap",        # ventilated cavity
]

VALID_LAYER_FUNCTIONS = frozenset({
    "structure", "substrate", "thermal",
    "finish1", "finish2", "membrane", "air_gap",
})


class WallValidationError(ValueError):
    """Raised when a compound wall configuration is invalid."""


# ---------------------------------------------------------------------------
# WallLayer
# ---------------------------------------------------------------------------

@dataclass
class WallLayer:
    """A single material layer within a compound wall cross-section.

    Parameters
    ----------
    material:
        Material identifier (key into ``kerf_bim.materials_catalogue.CATALOGUE``).
    thickness:
        Layer thickness in **mm**.  Must be > 0 for all functions except
        ``air_gap`` (which may be 0 when not modelled).
    function:
        Functional role of this layer — one of :data:`LayerFunction`.
    """
    material: str
    thickness: float     # mm
    function: LayerFunction = "finish1"

    def __post_init__(self) -> None:
        if self.function not in VALID_LAYER_FUNCTIONS:
            raise WallValidationError(
                f"Unknown layer function '{self.function}'; "
                f"allowed: {sorted(VALID_LAYER_FUNCTIONS)}"
            )
        if self.thickness < 0:
            raise WallValidationError(
                f"Layer thickness must be ≥ 0 mm, got {self.thickness}"
            )


# ---------------------------------------------------------------------------
# CompoundWall (the type/definition)
# ---------------------------------------------------------------------------

@dataclass
class CompoundWall:
    """A compound-wall type definition — an ordered stack of layers.

    The stack runs from the exterior face (index 0) to the interior face
    (index -1), matching Revit's convention.

    Attributes
    ----------
    name:
        Wall type name (e.g. ``"Ext - Brick Veneer 350"``).
    layers:
        Ordered list of :class:`WallLayer` objects.  At least one layer
        with ``function == "structure"`` is required.
    exterior_material:
        Optional override for the exterior face finish material id.
    description:
        Free-text description.
    """
    name: str
    layers: List[WallLayer]
    exterior_material: Optional[str] = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise WallValidationError("CompoundWall name must be non-empty")
        if not self.layers:
            raise WallValidationError("CompoundWall must have at least one layer")
        if not any(lay.function == "structure" for lay in self.layers):
            raise WallValidationError(
                f"CompoundWall '{self.name}' must have at least one 'structure' layer"
            )

    @property
    def total_thickness(self) -> float:
        """Total wall thickness in mm (sum of all layer thicknesses)."""
        return sum(lay.thickness for lay in self.layers)

    @property
    def structure_thickness(self) -> float:
        """Combined thickness of all structural layers (mm)."""
        return sum(lay.thickness for lay in self.layers if lay.function == "structure")

    @property
    def thermal_resistance(self) -> Optional[float]:
        """Approximate thermal resistance R [m²·K/W] from layer thicknesses.

        Uses material keys to look up conductivity from the BIM material
        catalogue.  Returns ``None`` when catalogue data is unavailable.
        """
        try:
            from kerf_bim.materials_catalogue import CATALOGUE
        except ImportError:
            return None
        r = 0.0
        for lay in self.layers:
            mat = CATALOGUE.get(lay.material)
            if mat and mat.thermal:
                lam = mat.thermal.thermal_conductivity  # W/(m·K)
                r += (lay.thickness / 1000.0) / lam     # mm → m
            # Skip layers with unknown materials
        return r if r > 0 else None

    def layer_summary(self) -> List[dict]:
        """Return a list of layer dicts for serialisation / display."""
        return [
            {
                "function": lay.function,
                "material": lay.material,
                "thickness_mm": lay.thickness,
            }
            for lay in self.layers
        ]


# ---------------------------------------------------------------------------
# WallInstance (a placed wall segment)
# ---------------------------------------------------------------------------

@dataclass
class WallInstance:
    """A placed wall segment instance.

    Parameters
    ----------
    wall_type:
        The :class:`CompoundWall` type.
    start:
        Start point ``[x, y]`` in mm (plan coordinates).
    end:
        End point ``[x, y]`` in mm.
    height:
        Wall height in mm (floor-to-top distance).
    level:
        Level name this wall belongs to.
    name:
        Optional override name for this instance.
    base_offset:
        Offset of wall base from level elevation (mm).  Default 0.
    top_offset:
        Offset of wall top from the nominal height (mm).  Default 0.
    """
    wall_type: CompoundWall
    start: List[float]       # [x, y] mm
    end: List[float]         # [x, y] mm
    height: float            # mm
    level: str = "L1"
    name: str = ""
    base_offset: float = 0.0
    top_offset: float = 0.0

    def __post_init__(self) -> None:
        if len(self.start) < 2 or len(self.end) < 2:
            raise WallValidationError("start and end must each have at least 2 coordinates [x, y]")
        if self.height <= 0:
            raise WallValidationError(f"Wall height must be > 0 mm, got {self.height}")

    @property
    def length(self) -> float:
        """Horizontal length of the wall in mm."""
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        return math.sqrt(dx * dx + dy * dy)

    @property
    def thickness(self) -> float:
        """Total wall thickness from the type (mm)."""
        return self.wall_type.total_thickness

    @property
    def effective_height(self) -> float:
        """Effective wall height considering offsets (mm)."""
        return self.height + self.top_offset - self.base_offset


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def make_compound_wall(
    name: str,
    layers: List[Tuple[str, float, LayerFunction]],
    description: str = "",
) -> CompoundWall:
    """Create a :class:`CompoundWall` from a list of ``(material, thickness, function)`` tuples.

    Example::

        wall = make_compound_wall("Brick Veneer 350", [
            ("brick_clay",         110.0, "structure"),
            ("air_gap",             50.0, "air_gap"),
            ("insulation_rockwool", 90.0, "thermal"),
            ("board_drywall_gypsum", 13.0, "finish2"),
        ])
    """
    wall_layers = [WallLayer(material=m, thickness=t, function=f) for m, t, f in layers]
    return CompoundWall(name=name, layers=wall_layers, description=description)


def make_wall_instance(
    wall_type: CompoundWall,
    start: List[float],
    end: List[float],
    height: float,
    level: str = "L1",
    name: str = "",
    base_offset: float = 0.0,
    top_offset: float = 0.0,
) -> WallInstance:
    """Create a :class:`WallInstance` from a :class:`CompoundWall` type."""
    return WallInstance(
        wall_type=wall_type,
        start=list(start),
        end=list(end),
        height=height,
        level=level,
        name=name or f"Wall ({wall_type.name})",
        base_offset=base_offset,
        top_offset=top_offset,
    )


# ---------------------------------------------------------------------------
# Per-layer face geometry (GK-P31)
# ---------------------------------------------------------------------------

@dataclass
class WallLayerGeometry:
    """Per-layer face geometry for a :class:`WallInstance`.

    Each layer is represented as a rectangular face extruded along the wall's
    plan length.  The face is defined by four 3-D corner points:

    Attributes
    ----------
    layer:
        The :class:`WallLayer` this geometry belongs to.
    layer_index:
        Index of the layer in the compound wall (0 = exterior).
    outer_offset:
        Signed perpendicular offset of the outer face from the wall
        centreline (mm), positive toward exterior.
    inner_offset:
        Signed perpendicular offset of the inner face from the wall
        centreline (mm).
    corners:
        Four 3-D corner points of the layer face (mm), ordered:
        ``[base_outer_start, base_outer_end,
           top_outer_end,    top_outer_start]`` (CCW from outside).
    """
    layer: "WallLayer"
    layer_index: int
    outer_offset: float
    inner_offset: float
    corners: List[Tuple[float, float, float]]


def wall_layer_faces(instance: "WallInstance") -> List[WallLayerGeometry]:
    """Compute per-layer face geometry for a :class:`WallInstance`.

    The wall is offset symmetrically about its centreline by default.
    Each layer runs from the exterior face to the interior face; layer [0]
    is the exterior-most layer.

    The wall plan axis (start → end) defines the *length* direction.
    The perpendicular to that axis (rotated 90° CCW in the XY plane) is the
    *thickness* direction, with positive values toward the exterior side.

    Half the total thickness extends on each side of the centreline.

    Parameters
    ----------
    instance:
        A placed :class:`WallInstance`.

    Returns
    -------
    List of :class:`WallLayerGeometry`, one per layer, ordered exterior-first.
    """
    import numpy as np

    sx, sy = float(instance.start[0]), float(instance.start[1])
    ex, ey = float(instance.end[0]),   float(instance.end[1])
    height = instance.effective_height
    base_z  = float(instance.base_offset)

    # Axis direction and perpendicular (thickness direction)
    dx, dy = ex - sx, ey - sy
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-10:
        return []  # degenerate wall (zero length)
    ux, uy = dx / length, dy / length  # unit tangent
    # Perpendicular: rotate 90° CCW → "exterior" side
    px, py = -uy, ux

    # Cumulative offsets from the exterior face
    # Half-thickness offset: exterior face is at +half_thickness, interior at -half_thickness
    half_t = instance.thickness / 2.0

    # Exterior face offset from centreline (positive)
    cumul = 0.0  # accumulated from exterior inward
    result: List[WallLayerGeometry] = []

    for idx, layer in enumerate(instance.wall_type.layers):
        outer_mm = half_t - cumul
        inner_mm = outer_mm - layer.thickness
        cumul += layer.thickness

        # Corner points:  outer face (outer_mm from CL) and inner face (inner_mm from CL)
        # Ordered CCW from exterior: base-start, base-end, top-end, top-start
        def pt(ax, ay, off, z) -> Tuple[float, float, float]:
            return (ax + off * px, ay + off * py, z)

        corners = [
            pt(sx, sy, outer_mm, base_z),               # 0 base outer start
            pt(ex, ey, outer_mm, base_z),               # 1 base outer end
            pt(ex, ey, outer_mm, base_z + height),      # 2 top  outer end
            pt(sx, sy, outer_mm, base_z + height),      # 3 top  outer start
            pt(sx, sy, inner_mm, base_z),               # 4 base inner start
            pt(ex, ey, inner_mm, base_z),               # 5 base inner end
            pt(ex, ey, inner_mm, base_z + height),      # 6 top  inner end
            pt(sx, sy, inner_mm, base_z + height),      # 7 top  inner start
        ]

        result.append(WallLayerGeometry(
            layer=layer,
            layer_index=idx,
            outer_offset=outer_mm,
            inner_offset=inner_mm,
            corners=corners,
        ))

    return result


# ---------------------------------------------------------------------------
# IFC dict serialisation
# ---------------------------------------------------------------------------

def wall_to_ifc_dict(instance: WallInstance) -> dict:
    """Convert a :class:`WallInstance` to the dict format for the IFC exporter.

    The returned dict is compatible with the ``walls`` list in the model
    dict accepted by :func:`kerf_bim.export_ifc.writer.export_ifc`.

    Extra keys (``wall_type``, ``layers``, ``layer_faces``) carry layer
    metadata and per-layer face geometry for section fills and IFC
    material-layer-set export.
    """
    layer_geom = wall_layer_faces(instance)
    layer_faces_out = []
    for lg in layer_geom:
        layer_faces_out.append({
            "layer_index":    lg.layer_index,
            "material":       lg.layer.material,
            "function":       lg.layer.function,
            "thickness_mm":   lg.layer.thickness,
            "outer_offset_mm": lg.outer_offset,
            "inner_offset_mm": lg.inner_offset,
            "corners":        [list(c) for c in lg.corners],
        })
    return {
        "from":       [instance.start[0], instance.start[1]],
        "to":         [instance.end[0],   instance.end[1]],
        "height":     instance.effective_height,
        "thickness":  instance.thickness,
        "level":      instance.level,
        "name":       instance.name,
        # Informational compound-wall metadata
        "wall_type":  instance.wall_type.name,
        "layers":     instance.wall_type.layer_summary(),
        # Per-layer face geometry (GK-P31)
        "layer_faces": layer_faces_out,
    }


# ---------------------------------------------------------------------------
# Preset compound-wall library
# ---------------------------------------------------------------------------

def _preset_walls() -> dict[str, CompoundWall]:
    """Build the preset compound-wall type dictionary."""
    walls: dict[str, CompoundWall] = {}

    def add(w: CompoundWall) -> None:
        walls[w.name] = w

    # Single-wythe brick
    add(make_compound_wall(
        "Ext - Single Brick 230",
        [
            ("brick_clay",          230.0, "structure"),
            ("plaster_lime",         15.0, "finish2"),
        ],
        description="Single-wythe clay brick + lime plaster interior finish.",
    ))

    # Brick veneer with cavity insulation
    add(make_compound_wall(
        "Ext - Brick Veneer Cavity 350",
        [
            ("brick_clay",           102.5, "finish1"),
            ("air_gap",               50.0, "air_gap"),
            ("insulation_rockwool",   90.0, "thermal"),
            ("masonry_cmu_concrete", 100.0, "structure"),
            ("plaster_lime",          12.5, "finish2"),
        ],
        description="Brick veneer + 50 mm cavity + rockwool insulation + CMU backup + lime plaster.",
    ))

    # Lightweight stud partition (steel stud acts as structure)
    add(make_compound_wall(
        "Int - Steel Stud 98",
        [
            ("board_drywall_gypsum",  12.5, "finish1"),
            ("insulation_fiberglass_batt", 63.0, "structure"),
            ("board_drywall_gypsum",  12.5, "finish2"),
        ],
        description="Steel-stud partition: double drywall + fiberglass batt (stud cavity modelled as structure layer).",
    ))

    # Tilt-up concrete
    add(make_compound_wall(
        "Ext - Tilt-Up Concrete 200",
        [
            ("concrete_reinforced",  200.0, "structure"),
            ("board_drywall_gypsum",  13.0, "finish2"),
        ],
        description="Tilt-up reinforced-concrete panel + gypsum board interior.",
    ))

    # AAC block
    add(make_compound_wall(
        "Int - AAC Block 200",
        [
            ("masonry_aac_block",    200.0, "structure"),
            ("plaster_cement",        10.0, "finish1"),
            ("plaster_cement",        10.0, "finish2"),
        ],
        description="AAC block wall + cement plaster both faces.",
    ))

    # High-performance exterior (EIFS / XPS composite)
    add(make_compound_wall(
        "Ext - RC Composite EIFS 350",
        [
            ("concrete_reinforced",  200.0, "structure"),
            ("insulation_xps",        80.0, "thermal"),
            ("board_cement_fibre",    15.0, "substrate"),
            ("plaster_cement",        10.0, "finish1"),
            ("plaster_gypsum_finish", 13.0, "finish2"),
        ],
        description="RC shear wall + XPS + cement-board substrate + EIFS cladding.",
    ))

    return walls


PRESET_WALLS: dict[str, CompoundWall] = _preset_walls()
