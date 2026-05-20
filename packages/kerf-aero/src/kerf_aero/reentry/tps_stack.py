"""
kerf_aero.reentry.tps_stack — Multi-layer TPS stack composition.

A TPS stack is an ordered list of layers from outermost (heat-shield face,
index 0) to innermost (structural wall, index -1).  Each layer has a
material, a thickness, and optionally a spatially-resolved node count for
finite-difference discretisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from kerf_aero.reentry.materials import MaterialProperties, PICA, LI_900, AL_2024


@dataclass
class StackLayer:
    """Single layer in the TPS stack.

    Parameters
    ----------
    material : MaterialProperties
        Material of this layer.
    thickness : float
        Layer thickness [m].
    n_nodes : int
        Number of finite-difference nodes within this layer (minimum 2).
    """

    material: MaterialProperties
    thickness: float          # m
    n_nodes: int = 10

    def __post_init__(self) -> None:
        if self.thickness <= 0:
            raise ValueError(f"Layer thickness must be > 0, got {self.thickness}")
        if self.n_nodes < 2:
            raise ValueError(f"n_nodes must be >= 2, got {self.n_nodes}")

    @property
    def dx(self) -> float:
        """Node spacing [m]."""
        return self.thickness / (self.n_nodes - 1)


@dataclass
class TPSStack:
    """Ordered multi-layer TPS stack.

    Layers are stored outermost-first (index 0 = ablative surface layer).

    Parameters
    ----------
    layers : list[StackLayer]
        Ordered layers, outermost first.
    """

    layers: list[StackLayer] = field(default_factory=list)

    def add_layer(self, layer: StackLayer) -> "TPSStack":
        """Append a layer and return self (fluent API)."""
        self.layers.append(layer)
        return self

    @property
    def total_thickness(self) -> float:
        """Total stack thickness [m]."""
        return sum(lay.thickness for lay in self.layers)

    @property
    def total_nodes(self) -> int:
        """Total number of FD nodes across all layers.

        Adjacent layers share a boundary node, so nodes are stitched with
        -1 per interface.
        """
        if not self.layers:
            return 0
        return sum(lay.n_nodes for lay in self.layers) - (len(self.layers) - 1)

    def layer_node_slices(self) -> list[tuple[int, int]]:
        """Return (start, end) inclusive node indices for each layer."""
        slices: list[tuple[int, int]] = []
        offset = 0
        for i, lay in enumerate(self.layers):
            start = offset
            end = offset + lay.n_nodes - 1
            slices.append((start, end))
            offset = end        # next layer starts at the same index (shared node)
        return slices

    def node_positions(self) -> list[float]:
        """Return absolute depth position [m] for every node, from surface."""
        positions: list[float] = []
        depth = 0.0
        for i, lay in enumerate(self.layers):
            start = 0 if i == 0 else 1   # skip shared node except for first layer
            for j in range(start, lay.n_nodes):
                positions.append(depth + j * lay.dx)
            depth += lay.thickness
        return positions

    def node_materials(self) -> list[MaterialProperties]:
        """Return the material for every node."""
        mats: list[MaterialProperties] = []
        for i, lay in enumerate(self.layers):
            start = 0 if i == 0 else 1
            for _ in range(start, lay.n_nodes):
                mats.append(lay.material)
        return mats


# ---------------------------------------------------------------------------
# Factory: Stardust SRC-like PICA-X stack
# ---------------------------------------------------------------------------

def stardust_pica_stack(
    pica_thickness: float = 0.060,
    li900_thickness: float = 0.020,
    al_thickness: float = 0.005,
    n_pica: int = 20,
    n_li900: int = 10,
    n_al: int = 5,
) -> TPSStack:
    """Return a Stardust SRC representative TPS stack.

    Stack (outermost → innermost):
    1. PICA ablator        — primary heat shield
    2. LI-900 silica tile  — secondary insulator
    3. Al-2024 substrate   — structural wall

    Parameters
    ----------
    pica_thickness : float
        PICA layer thickness [m], default 60 mm.
    li900_thickness : float
        LI-900 layer thickness [m], default 20 mm.
    al_thickness : float
        Aluminum structural layer thickness [m], default 5 mm.
    n_pica, n_li900, n_al : int
        Node counts per layer.
    """
    stack = TPSStack()
    stack.add_layer(StackLayer(PICA, pica_thickness, n_pica))
    stack.add_layer(StackLayer(LI_900, li900_thickness, n_li900))
    stack.add_layer(StackLayer(AL_2024, al_thickness, n_al))
    return stack
