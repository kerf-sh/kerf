"""Parity tests: lattice.gyroid / lattice.schwarz_p field values must match
frep.sdf_gyroid / frep.sdf_schwarz_p at every sampled point.

Both modules now delegate to kerf_cad_core.geom.tpms shared field functions.
These tests confirm that the refactor preserved numerical identity (within 1e-12).
"""
from __future__ import annotations

import pytest

from kerf_cad_core.geom.lattice import gyroid as lattice_gyroid, schwarz_p as lattice_schwarz_p
from kerf_cad_core.frep.sdf import sdf_gyroid, sdf_schwarz_p


# Sample points that are well away from trivially-symmetric positions
_SAMPLE_POINTS = [
    (0.1, 0.2, 0.3),
    (1.57, 0.9, 2.1),
    (-0.5, 1.1, -0.7),
    (3.3, -2.2, 0.8),
    (0.0, 0.0, 0.0),
    (5.0, 5.0, 5.0),
]

_PERIOD = 10.0  # cell_size / period shared value
_TOLS = 1e-12


class TestGyroidParity:
    """lattice.gyroid field == frep.sdf_gyroid field (iso=0) at all sample points."""

    def setup_method(self):
        self.lattice_f = lattice_gyroid(cell_size=_PERIOD, thickness=0.5)["f"]
        self.frep_f = sdf_gyroid(period=_PERIOD, iso=0.0)

    @pytest.mark.parametrize("x,y,z", _SAMPLE_POINTS)
    def test_field_parity(self, x, y, z):
        lattice_val = self.lattice_f(x, y, z)
        frep_val = self.frep_f(x, y, z)
        assert abs(lattice_val - frep_val) < _TOLS, (
            f"Gyroid field mismatch at ({x},{y},{z}): "
            f"lattice={lattice_val}, frep={frep_val}"
        )


class TestSchwarzPParity:
    """lattice.schwarz_p field == frep.sdf_schwarz_p field (iso=0) at all sample points."""

    def setup_method(self):
        self.lattice_f = lattice_schwarz_p(cell_size=_PERIOD, thickness=0.5)["f"]
        self.frep_f = sdf_schwarz_p(period=_PERIOD, iso=0.0)

    @pytest.mark.parametrize("x,y,z", _SAMPLE_POINTS)
    def test_field_parity(self, x, y, z):
        lattice_val = self.lattice_f(x, y, z)
        frep_val = self.frep_f(x, y, z)
        assert abs(lattice_val - frep_val) < _TOLS, (
            f"Schwarz-P field mismatch at ({x},{y},{z}): "
            f"lattice={lattice_val}, frep={frep_val}"
        )
