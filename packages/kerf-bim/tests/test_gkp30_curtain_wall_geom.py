"""Tests for GK-P30 — Curtain-wall geometry: mullion B-rep + panel solids.

DoD: curtain_wall_geometry emits mullion solids + panel solids from grid.
"""
from __future__ import annotations
import pytest

pytest.importorskip("kerf_cad_core", reason="kerf_cad_core not available")

from kerf_bim.curtain_wall_geom import CurtainWallGeom, curtain_wall_geometry


def _default_doc(n_u=4, n_v=3, mull_size=50, panel_kind="glass") -> dict:
    return {
        "version": 1,
        "name": "Test CW",
        "height_mm": 3000.0,
        "u_divisions": [{"type": "count", "value": n_u}],
        "v_divisions": [{"type": "count", "value": n_v}],
        "panel_type":   {"kind": panel_kind},
        "mullion_type": {"profile": "square", "size_mm": mull_size},
    }


class TestCurtainWallGeomBasics:
    def test_returns_geom_object(self):
        doc = _default_doc()
        geom = curtain_wall_geometry(doc, [0, 0], [5000, 0])
        assert isinstance(geom, CurtainWallGeom)

    def test_u_v_count(self):
        geom = curtain_wall_geometry(_default_doc(n_u=4, n_v=3), [0, 0], [5000, 0])
        assert geom.u_count == 4
        assert geom.v_count == 3

    def test_mullion_count_vertical_plus_horizontal(self):
        """(n_u+1) vertical + (n_v+1) horizontal = 5+4 = 9 for 4×3 grid."""
        geom = curtain_wall_geometry(_default_doc(n_u=4, n_v=3), [0, 0], [5000, 0])
        expected = (4 + 1) + (3 + 1)
        assert geom.mullion_count == expected, (
            f"Expected {expected} mullion bodies, got {geom.mullion_count}"
        )

    def test_mullion_bodies_not_empty(self):
        geom = curtain_wall_geometry(_default_doc(), [0, 0], [6000, 0])
        assert len(geom.mullion_bodies) > 0

    def test_mullion_bodies_are_valid_brep(self):
        geom = curtain_wall_geometry(_default_doc(n_u=2, n_v=2), [0, 0], [3000, 0])
        from kerf_cad_core.geom.brep import Body
        for body in geom.mullion_bodies:
            assert isinstance(body, Body)
            assert len(body.solids) == 1
            shell = body.solids[0].shells[0]
            assert len(shell.faces) == 6, "Box should have 6 faces"


class TestPanelGeometry:
    def test_glass_panels_non_empty(self):
        geom = curtain_wall_geometry(_default_doc(panel_kind="glass"), [0, 0], [5000, 0])
        assert geom.panel_count > 0

    def test_panel_count_matches_grid(self):
        """Glass panels: at most n_u × n_v (may be fewer if cells too small)."""
        geom = curtain_wall_geometry(_default_doc(n_u=4, n_v=3, panel_kind="glass"),
                                      [0, 0], [6000, 0])
        assert geom.panel_count <= 4 * 3
        assert geom.panel_count > 0

    def test_opening_panels_empty(self):
        """Opening panels → no panel bodies emitted."""
        geom = curtain_wall_geometry(_default_doc(panel_kind="opening"), [0, 0], [5000, 0])
        assert geom.panel_count == 0

    def test_panel_bodies_are_valid_brep(self):
        geom = curtain_wall_geometry(_default_doc(n_u=2, n_v=2, panel_kind="glass"),
                                      [0, 0], [5000, 0])
        from kerf_cad_core.geom.brep import Body
        for body in geom.panel_bodies:
            assert isinstance(body, Body)
            assert len(body.solids) == 1

    def test_solid_panels_non_empty(self):
        geom = curtain_wall_geometry(_default_doc(panel_kind="solid"), [0, 0], [5000, 0])
        assert geom.panel_count > 0


class TestCurtainWallDegenerateCases:
    def test_zero_length_returns_empty(self):
        geom = curtain_wall_geometry(_default_doc(), [0, 0], [0, 0])
        assert geom.mullion_count == 0
        assert geom.panel_count == 0

    def test_diagonal_wall(self):
        """Curtain wall on a diagonal base curve."""
        geom = curtain_wall_geometry(_default_doc(n_u=3, n_v=2),
                                      [0, 0], [3000, 4000])  # 5000mm diagonal
        assert geom.mullion_count == (3 + 1) + (2 + 1)

    def test_spacing_type_divisions(self):
        doc = {
            "version": 1,
            "name": "Test",
            "height_mm": 3000.0,
            "u_divisions": [{"type": "spacing", "value": 1000}],
            "v_divisions": [{"type": "spacing", "value": 1000}],
            "panel_type": {"kind": "glass"},
            "mullion_type": {"profile": "square", "size_mm": 50},
        }
        geom = curtain_wall_geometry(doc, [0, 0], [5000, 0])
        assert geom.mullion_count > 0
        assert geom.u_count > 0
