"""GK-115 — Hermetic oracle tests for the lattice unit-cell library.

Oracles (from spec):
1. Gyroid implicit is periodic: f(x + cell_size, y, z) approx f(x, y, z).
2. Octet truss has exactly 36 struts per cell.
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.geom.lattice import gyroid, schwarz_p, octet_truss, kelvin_cell
from kerf_cad_core.geom import (
    gyroid as geom_gyroid,
    schwarz_p as geom_schwarz_p,
    octet_truss as geom_octet_truss,
    kelvin_cell as geom_kelvin_cell,
)


# ---------------------------------------------------------------------------
# Gyroid
# ---------------------------------------------------------------------------

class TestGyroid:
    def test_returns_dict_with_expected_keys(self):
        g = gyroid(cell_size=10.0, thickness=0.5)
        assert set(g.keys()) >= {"f", "cell_size", "thickness", "kind"}

    def test_kind(self):
        assert gyroid(10.0, 0.5)["kind"] == "tpms"

    def test_cell_size_stored(self):
        g = gyroid(7.0, 0.3)
        assert g["cell_size"] == pytest.approx(7.0)

    def test_thickness_stored(self):
        g = gyroid(7.0, 0.3)
        assert g["thickness"] == pytest.approx(0.3)

    def test_f_is_callable(self):
        g = gyroid(10.0, 0.5)
        assert callable(g["f"])

    def test_f_returns_float(self):
        g = gyroid(10.0, 0.5)
        result = g["f"](1.0, 2.0, 3.0)
        assert isinstance(result, float)

    # Oracle: periodicity -- f(x + L, y, z) approx f(x, y, z)
    @pytest.mark.parametrize("L", [5.0, 10.0, 20.0])
    def test_periodic_x(self, L):
        g = gyroid(cell_size=L, thickness=0.5)
        f = g["f"]
        for x, y, z in [(1.1, 2.3, 0.7), (0.5, 0.5, 0.5), (3.0, -1.0, 2.0)]:
            assert f(x, y, z) == pytest.approx(f(x + L, y, z), abs=1e-10)

    @pytest.mark.parametrize("L", [5.0, 10.0])
    def test_periodic_y(self, L):
        g = gyroid(cell_size=L, thickness=0.5)
        f = g["f"]
        for x, y, z in [(1.1, 2.3, 0.7), (2.0, 0.1, 1.5)]:
            assert f(x, y, z) == pytest.approx(f(x, y + L, z), abs=1e-10)

    @pytest.mark.parametrize("L", [5.0, 10.0])
    def test_periodic_z(self, L):
        g = gyroid(cell_size=L, thickness=0.5)
        f = g["f"]
        for x, y, z in [(1.1, 2.3, 0.7), (2.0, 0.1, 1.5)]:
            assert f(x, y, z) == pytest.approx(f(x, y, z + L), abs=1e-10)

    def test_invalid_cell_size(self):
        with pytest.raises(ValueError):
            gyroid(0.0, 0.5)

    def test_invalid_thickness(self):
        with pytest.raises(ValueError):
            gyroid(10.0, -1.0)

    def test_re_exported_from_geom(self):
        g = geom_gyroid(10.0, 0.5)
        assert g["kind"] == "tpms"


# ---------------------------------------------------------------------------
# Schwarz-P
# ---------------------------------------------------------------------------

class TestSchwarzP:
    def test_returns_dict_with_expected_keys(self):
        s = schwarz_p(cell_size=10.0, thickness=0.5)
        assert set(s.keys()) >= {"f", "cell_size", "thickness", "kind"}

    def test_kind(self):
        assert schwarz_p(10.0, 0.5)["kind"] == "tpms"

    def test_f_is_callable(self):
        s = schwarz_p(10.0, 0.5)
        assert callable(s["f"])

    # Schwarz-P is also periodic
    @pytest.mark.parametrize("L", [8.0, 12.0])
    def test_periodic_x(self, L):
        s = schwarz_p(cell_size=L, thickness=0.5)
        f = s["f"]
        for x, y, z in [(1.0, 2.0, 0.5), (3.5, 1.5, 2.5)]:
            assert f(x, y, z) == pytest.approx(f(x + L, y, z), abs=1e-10)

    def test_known_value_at_origin(self):
        # At (0,0,0): cos(0)+cos(0)+cos(0) = 3.0
        s = schwarz_p(cell_size=10.0, thickness=0.5)
        assert s["f"](0.0, 0.0, 0.0) == pytest.approx(3.0, abs=1e-10)

    def test_invalid_cell_size(self):
        with pytest.raises(ValueError):
            schwarz_p(-1.0, 0.5)

    def test_re_exported_from_geom(self):
        s = geom_schwarz_p(10.0, 0.5)
        assert s["kind"] == "tpms"


# ---------------------------------------------------------------------------
# Octet truss
# ---------------------------------------------------------------------------

class TestOctetTruss:
    def test_returns_dict_with_expected_keys(self):
        ot = octet_truss(cell_size=10.0, strut_radius=0.3)
        assert set(ot.keys()) >= {"struts", "nodes", "cell_size", "strut_radius", "kind"}

    def test_kind(self):
        assert octet_truss(10.0, 0.3)["kind"] == "strut"

    # Oracle: exactly 36 struts per cell
    @pytest.mark.parametrize("L", [5.0, 10.0, 20.0])
    def test_strut_count_is_36(self, L):
        ot = octet_truss(cell_size=L, strut_radius=0.3)
        assert len(ot["struts"]) == 36

    def test_struts_are_tuples_of_two_points(self):
        ot = octet_truss(10.0, 0.3)
        for strut in ot["struts"]:
            assert len(strut) == 2
            assert len(strut[0]) == 3
            assert len(strut[1]) == 3

    def test_no_duplicate_struts(self):
        ot = octet_truss(10.0, 0.3)
        canonical = set()
        for a, b in ot["struts"]:
            canonical.add((a, b) if a <= b else (b, a))
        assert len(canonical) == 36

    def test_strut_endpoints_within_cell(self):
        L = 10.0
        ot = octet_truss(L, 0.3)
        tol = 1e-9
        for a, b in ot["struts"]:
            for pt in (a, b):
                assert -tol <= pt[0] <= L + tol
                assert -tol <= pt[1] <= L + tol
                assert -tol <= pt[2] <= L + tol

    def test_node_count(self):
        ot = octet_truss(10.0, 0.3)
        # 8 corners + 6 face centres = 14
        assert len(ot["nodes"]) == 14

    def test_cell_size_stored(self):
        ot = octet_truss(7.5, 0.2)
        assert ot["cell_size"] == pytest.approx(7.5)

    def test_strut_radius_stored(self):
        ot = octet_truss(7.5, 0.2)
        assert ot["strut_radius"] == pytest.approx(0.2)

    def test_invalid_cell_size(self):
        with pytest.raises(ValueError):
            octet_truss(0.0, 0.3)

    def test_invalid_strut_radius(self):
        with pytest.raises(ValueError):
            octet_truss(10.0, 0.0)

    def test_re_exported_from_geom(self):
        ot = geom_octet_truss(10.0, 0.3)
        assert len(ot["struts"]) == 36


# ---------------------------------------------------------------------------
# Kelvin cell
# ---------------------------------------------------------------------------

class TestKelvinCell:
    def test_returns_dict_with_expected_keys(self):
        kc = kelvin_cell(cell_size=10.0, strut_radius=0.3)
        assert set(kc.keys()) >= {"struts", "nodes", "cell_size", "strut_radius", "kind"}

    def test_kind(self):
        assert kelvin_cell(10.0, 0.3)["kind"] == "strut"

    def test_node_count(self):
        # Truncated octahedron has 24 vertices
        kc = kelvin_cell(10.0, 0.3)
        assert len(kc["nodes"]) == 24

    def test_strut_count(self):
        # Truncated octahedron has 36 edges
        kc = kelvin_cell(10.0, 0.3)
        assert len(kc["struts"]) == 36

    def test_struts_are_tuples_of_two_points(self):
        kc = kelvin_cell(10.0, 0.3)
        for strut in kc["struts"]:
            assert len(strut) == 2
            assert len(strut[0]) == 3
            assert len(strut[1]) == 3

    def test_no_duplicate_struts(self):
        kc = kelvin_cell(10.0, 0.3)
        canonical = set()
        for a, b in kc["struts"]:
            canonical.add((a, b) if a <= b else (b, a))
        assert len(canonical) == len(kc["struts"])

    def test_cell_size_stored(self):
        kc = kelvin_cell(8.0, 0.25)
        assert kc["cell_size"] == pytest.approx(8.0)

    def test_strut_radius_stored(self):
        kc = kelvin_cell(8.0, 0.25)
        assert kc["strut_radius"] == pytest.approx(0.25)

    def test_invalid_cell_size(self):
        with pytest.raises(ValueError):
            kelvin_cell(-5.0, 0.3)

    def test_invalid_strut_radius(self):
        with pytest.raises(ValueError):
            kelvin_cell(10.0, -1.0)

    def test_re_exported_from_geom(self):
        kc = geom_kelvin_cell(10.0, 0.3)
        assert kc["kind"] == "strut"

    def test_all_strut_lengths_equal(self):
        """All Kelvin-cell struts should have the same length (uniform edges)."""
        kc = kelvin_cell(10.0, 0.3)
        lengths = []
        for (x0, y0, z0), (x1, y1, z1) in kc["struts"]:
            d = math.sqrt((x1-x0)**2 + (y1-y0)**2 + (z1-z0)**2)
            lengths.append(d)
        assert len(lengths) > 0
        # All lengths equal within tolerance
        for d in lengths:
            assert d == pytest.approx(lengths[0], rel=1e-6)
