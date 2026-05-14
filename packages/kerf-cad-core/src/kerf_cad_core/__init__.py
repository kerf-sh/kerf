"""
kerf_cad_core — shared pythonOCC base layer for Kerf CAD compute plugins.

Downstream plugins import the public API from here:

    from kerf_cad_core import _OCC_AVAILABLE, convert_step_to_stl, load_step, mesh_shape, write_stl
"""

from kerf_cad_core.occ_helpers import (
    _OCC_AVAILABLE,
    convert_step_to_stl,
    load_step,
    mesh_shape,
    write_stl,
)

__all__ = [
    "_OCC_AVAILABLE",
    "convert_step_to_stl",
    "load_step",
    "mesh_shape",
    "write_stl",
]
