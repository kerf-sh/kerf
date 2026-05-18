"""LEF (Library Exchange Format) AST dataclasses.

Represents the parsed structure of a LEF file:
  - LefLibrary: top-level container
  - Macro:       standard-cell abstract (footprint)
  - Pin:         signal/supply pin within a macro
  - Port:        geometric shapes for a pin on specific layers
  - Shape:       RECT or POLYGON geometry
  - LefLayer:    technology layer definition
  - LefVia:      via definition
  - LefSite:     placement site definition
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Shape:
    """A single geometry shape: RECT or POLYGON."""
    kind: str  # "RECT" or "POLYGON"
    coords: List[float]
    line: int = 0  # source line number


@dataclass
class Port:
    """A PORT inside a PIN — geometry on a named layer."""
    layer: str
    shapes: List[Shape] = field(default_factory=list)
    line: int = 0


@dataclass
class Pin:
    """A PIN definition inside a MACRO."""
    name: str
    direction: Optional[str] = None   # INPUT / OUTPUT / INOUT / FEEDTHRU / POWER / GROUND
    use: Optional[str] = None          # SIGNAL / POWER / GROUND / CLOCK / ANALOG / SCAN / RESET
    antenna_gate_area: Optional[float] = None
    ports: List[Port] = field(default_factory=list)
    line: int = 0


@dataclass
class Obstruction:
    """OBS block inside a MACRO (keep-out layers)."""
    layer: str
    shapes: List[Shape] = field(default_factory=list)
    line: int = 0


@dataclass
class Macro:
    """MACRO block — standard-cell abstract."""
    name: str
    macro_class: Optional[str] = None   # CORE / PAD / BLOCK / RING / ENDCAP …
    size_x: float = 0.0
    size_y: float = 0.0
    origin_x: float = 0.0
    origin_y: float = 0.0
    symmetry: Optional[str] = None
    site: Optional[str] = None
    pins: List[Pin] = field(default_factory=list)
    obstructions: List[Obstruction] = field(default_factory=list)
    line: int = 0


@dataclass
class LefLayer:
    """LAYER block — technology layer descriptor."""
    name: str
    layer_type: Optional[str] = None  # ROUTING / CUT / MASTERSLICE / OVERLAP
    pitch: Optional[float] = None
    width: Optional[float] = None
    spacing: Optional[float] = None
    direction: Optional[str] = None   # HORIZONTAL / VERTICAL
    line: int = 0


@dataclass
class LefVia:
    """VIA block definition."""
    name: str
    layer_shapes: List[Tuple[str, List[Shape]]] = field(default_factory=list)
    line: int = 0


@dataclass
class LefSite:
    """SITE block definition."""
    name: str
    site_class: Optional[str] = None  # CORE / PAD
    symmetry: Optional[str] = None
    size_x: float = 0.0
    size_y: float = 0.0
    line: int = 0


@dataclass
class LefLibrary:
    """Top-level container produced by the LEF parser."""
    version: Optional[str] = None
    bus_bit_chars: Optional[str] = None
    divider_char: Optional[str] = None
    layers: List[LefLayer] = field(default_factory=list)
    vias: List[LefVia] = field(default_factory=list)
    sites: List[LefSite] = field(default_factory=list)
    macros: List[Macro] = field(default_factory=list)
