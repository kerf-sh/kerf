"""kerf_partsgen.kernel — the parametric geometry surface generators compose.

Generators MUST NOT freehand a mesh.  They build solids by composing this
facade, which mirrors Kerf's own parametric feature vocabulary:

    sketch (closed 2D profile)  →  pad / revolve
    primitives                  →  box, cylinder, hex_prism
    booleans                    →  union, cut, intersect
    dress-up                    →  fillet_edges, chamfer_edges

It is backed by the **same OpenCASCADE (OCCT) kernel** Kerf uses for B-rep
work.  Production Kerf binds OCCT through ``pythonocc-core``
(``kerf_cad_core.occ_helpers``); the contributor / CI toolchain binds the
*same* kernel through ``cadquery`` (which wraps ``OCP``).  Either binding
satisfies this module — we probe at import time and degrade cleanly
(``KERNEL_BACKEND == "none"``) so a contributor with no kernel can still run
``enumerate`` and get a deterministic ``FAIL`` per variant rather than a
crash, and the markdown / author tests stay hermetic.

A built part is exported to **STEP** — the exact solid interchange Kerf's
``import_step`` RPC tool already consumes — so an enumerated part drops
straight into the Workshop with no lossy mesh round-trip.
"""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Sequence

# ── Kernel availability gate (mirrors kerf_cad_core.occ_helpers._OCC_AVAILABLE)

KERNEL_BACKEND = "none"
_cq: Any = None

try:  # cadquery (OCP / OpenCASCADE) — the contributor + CI binding
    import cadquery as _cadquery

    _cq = _cadquery
    KERNEL_BACKEND = "cadquery"
except Exception:  # pragma: no cover - exercised only where cadquery absent
    _cq = None

KERNEL_AVAILABLE = KERNEL_BACKEND != "none"


class KernelUnavailable(RuntimeError):
    """Raised when a geometry op is attempted with no OCCT binding present."""


def _require_kernel() -> None:
    if not KERNEL_AVAILABLE:
        raise KernelUnavailable(
            "No OCCT kernel binding available. Install the parts toolchain: "
            "pip install -e 'packages/kerf-partsgen[kernel]' "
            "(cadquery), or run inside a Kerf compute env with pythonocc-core."
        )


# ── Solid wrapper ──────────────────────────────────────────────────────────


@dataclass
class GeneratedPart:
    """One built solid plus the kernel-measured facts the gate checks against.

    ``solid`` is an opaque kernel handle (cadquery ``Workplane``).  The
    verification gate never trusts a generator's declared numbers blindly —
    it re-measures ``volume_mm3`` / ``bbox_mm`` straight off the kernel.
    """

    solid: Any
    is_valid: bool
    volume_mm3: float
    bbox_mm: tuple[float, float, float]

    def export_step(self, path: str) -> None:
        _require_kernel()
        from cadquery import exporters

        exporters.export(self.solid, path)

    def export_stl(self, path: str) -> None:
        _require_kernel()
        from cadquery import exporters

        exporters.export(self.solid, path)


def _finish(wp: Any) -> GeneratedPart:
    """Measure a cadquery Workplane the way the gate will and box it up."""
    _require_kernel()
    try:
        shape = wp.val()
        valid = bool(shape.isValid())
        vol = float(shape.Volume())
        bb = shape.BoundingBox()
        bbox = (float(bb.xlen), float(bb.ylen), float(bb.zlen))
    except Exception as exc:  # kernel error → invalid solid (gate FAILs it)
        return GeneratedPart(solid=wp, is_valid=False, volume_mm3=0.0,
                             bbox_mm=(0.0, 0.0, 0.0))
    return GeneratedPart(solid=wp, is_valid=valid, volume_mm3=vol,
                         bbox_mm=bbox)


# ── Primitives (centred at origin, mm) ─────────────────────────────────────


def box(length: float, width: float, height: float) -> GeneratedPart:
    """Axis-aligned box, centred on the origin."""
    _require_kernel()
    wp = _cq.Workplane("XY").box(length, width, height)
    return _finish(wp)


def cylinder(radius: float, height: float) -> GeneratedPart:
    """Z-axis cylinder, centred on the origin."""
    _require_kernel()
    wp = _cq.Workplane("XY").cylinder(height, radius)
    return _finish(wp)


def hex_prism(across_flats: float, height: float) -> GeneratedPart:
    """Regular hexagonal prism specified by width across flats (mm).

    This is the canonical fastener-head / nut primitive — ``across_flats``
    is the wrench size every fastener standard tabulates.
    """
    _require_kernel()
    circum_r = (across_flats / 2.0) / math.cos(math.pi / 6.0)
    wp = (
        _cq.Workplane("XY")
        .polygon(6, circum_r * 2.0)
        .extrude(height)
        .translate((0, 0, -height / 2.0))
    )
    return _finish(wp)


# ── Sketch → pad / revolve (mirrors Kerf's .feature pad / revolve) ─────────


def sketch_circle(diameter: float):
    """Start a circular sketch on XY. Returns a builder for .pad()/.revolve()."""
    _require_kernel()
    return _SketchBuilder(_cq.Workplane("XY").circle(diameter / 2.0))


def sketch_polygon(points: Sequence[tuple[float, float]]):
    """Start a closed-polyline sketch on XY (list of (x, y) mm)."""
    _require_kernel()
    wp = _cq.Workplane("XY").polyline(list(points)).close()
    return _SketchBuilder(wp)


def sketch_regular_polygon(n_sides: int, across_flats: float):
    """Start a regular n-gon sketch sized by width across flats (mm)."""
    _require_kernel()
    circum_d = (across_flats / math.cos(math.pi / n_sides))
    return _SketchBuilder(_cq.Workplane("XY").polygon(n_sides, circum_d))


class _SketchBuilder:
    def __init__(self, wp: Any) -> None:
        self._wp = wp

    def pad(self, distance: float) -> GeneratedPart:
        """Extrude the sketch ``distance`` mm along +Z (Kerf 'pad')."""
        return _finish(self._wp.extrude(distance))

    def revolve(self, angle_deg: float = 360.0) -> GeneratedPart:
        """Revolve the sketch about the Y axis (Kerf 'revolve')."""
        return _finish(self._wp.revolve(angle_deg))


# ── Booleans + dress-up (operate on GeneratedPart) ─────────────────────────


def union(a: GeneratedPart, b: GeneratedPart) -> GeneratedPart:
    return _finish(a.solid.union(b.solid))


def cut(a: GeneratedPart, b: GeneratedPart) -> GeneratedPart:
    return _finish(a.solid.cut(b.solid))


def intersect(a: GeneratedPart, b: GeneratedPart) -> GeneratedPart:
    return _finish(a.solid.intersect(b.solid))


def translate(p: GeneratedPart, dx: float, dy: float, dz: float) -> GeneratedPart:
    return _finish(p.solid.translate((dx, dy, dz)))


def chamfer_top_edge(p: GeneratedPart, length: float) -> GeneratedPart:
    """Chamfer the highest +Z circular edge (used for screw-point lead-in)."""
    try:
        wp = p.solid.faces(">Z").edges().chamfer(length)
        return _finish(wp)
    except Exception:
        return p  # dressing failure must not crash enumerate; keep base solid


def make_dir_tmp_step(p: GeneratedPart) -> str:
    """Export to a throwaway STEP file (used by the gate's watertight probe)."""
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    p.export_step(path)
    return path
