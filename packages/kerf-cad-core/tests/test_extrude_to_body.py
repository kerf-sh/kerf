"""Tests for GK-15: extrude_to_body (capped) from a closed planar curve.

Oracle: extrude a unit square → a box.
- V=8, E=12, F=6 (Euler–Poincaré residual = 0)
- volume = 1.0 (1×1×1) exact to ≤1e-9
- validate_body clean
"""

import math

import numpy as np
import pytest

from kerf_cad_core.geom.brep_build import BuildError, extrude_to_body
from kerf_cad_core.geom.brep import validate_body
from kerf_cad_core.geom.solid_features import extrude_to_body as sf_extrude_to_body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNIT_SQUARE = [
    [0.0, 0.0, 0.0],
    [1.0, 0.0, 0.0],
    [1.0, 1.0, 0.0],
    [0.0, 1.0, 0.0],
]

_Z_DIR = [0.0, 0.0, 1.0]


# ---------------------------------------------------------------------------
# Core B-rep builder tests
# ---------------------------------------------------------------------------


class TestExtrudeToBodyBrepBuilder:
    """Tests against the low-level brep_build.extrude_to_body."""

    def test_unit_square_euler_counts(self):
        """Extruding the unit square must yield V=8, E=12, F=6."""
        body = extrude_to_body(_UNIT_SQUARE, _Z_DIR)
        counts = body.euler_counts()
        assert counts["V"] == 8, f"Expected V=8, got {counts['V']}"
        assert counts["E"] == 12, f"Expected E=12, got {counts['E']}"
        assert counts["F"] == 6, f"Expected F=6, got {counts['F']}"

    def test_unit_square_euler_poincare_residual(self):
        """Euler–Poincaré residual must be 0 for the box topology."""
        body = extrude_to_body(_UNIT_SQUARE, _Z_DIR)
        residual = body.euler_poincare_residual()
        assert residual == 0, f"Euler–Poincaré residual={residual}, expected 0"

    def test_unit_square_validate_body_clean(self):
        """validate_body must return ok=True with no errors."""
        body = extrude_to_body(_UNIT_SQUARE, _Z_DIR)
        result = validate_body(body)
        assert result["ok"] is True, f"validate_body errors: {result['errors']}"

    def test_unit_square_volume(self):
        """Volume of a 1×1×1 box extruded from the unit square = 1.0."""
        # Volume is not directly computed in brep_build; use solid_features.
        result = sf_extrude_to_body(_UNIT_SQUARE, _Z_DIR)
        assert result["ok"] is True, f"solid_features failed: {result.get('reason')}"
        assert abs(result["volume"] - 1.0) <= 1e-9, (
            f"Volume error: {result['volume']} != 1.0"
        )

    def test_unit_square_face_count(self):
        """A 4-sided profile should produce 6 faces (4 sides + 2 caps)."""
        body = extrude_to_body(_UNIT_SQUARE, _Z_DIR)
        counts = body.euler_counts()
        assert counts["F"] == 6

    def test_arbitrary_height(self):
        """Extruding unit square by height=3 → volume=3."""
        result = sf_extrude_to_body(_UNIT_SQUARE, [0.0, 0.0, 3.0])
        assert result["ok"] is True
        assert abs(result["volume"] - 3.0) <= 1e-9

    def test_triangle_extrude(self):
        """A triangular profile → 5 faces (3 sides + 2 caps), V=6, E=9."""
        triangle = [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, math.sqrt(3) / 2, 0.0],
        ]
        body = extrude_to_body(triangle, _Z_DIR)
        counts = body.euler_counts()
        # V-E+F = 6-9+5 = 2 ✓
        assert counts["V"] == 6, f"Expected V=6, got {counts['V']}"
        assert counts["E"] == 9, f"Expected E=9, got {counts['E']}"
        assert counts["F"] == 5, f"Expected F=5, got {counts['F']}"
        result = validate_body(body)
        assert result["ok"] is True, f"validate_body errors: {result['errors']}"

    def test_triangle_volume(self):
        """Equilateral triangle (side=1) extruded by h=1 → volume = sqrt(3)/4."""
        triangle = [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, math.sqrt(3) / 2, 0.0],
        ]
        expected_vol = math.sqrt(3) / 4.0
        result = sf_extrude_to_body(triangle, _Z_DIR)
        assert result["ok"] is True
        assert abs(result["volume"] - expected_vol) <= 1e-9, (
            f"Triangle volume error: {result['volume']} != {expected_vol}"
        )

    def test_pentagon_extrude(self):
        """Pentagon profile → V=10, E=15, F=7, V-E+F=2."""
        pentagon = [
            [math.cos(2 * math.pi * i / 5), math.sin(2 * math.pi * i / 5), 0.0]
            for i in range(5)
        ]
        body = extrude_to_body(pentagon, _Z_DIR)
        counts = body.euler_counts()
        assert counts["V"] == 10
        assert counts["E"] == 15
        assert counts["F"] == 7
        result = validate_body(body)
        assert result["ok"] is True, f"validate_body errors: {result['errors']}"

    def test_non_unit_direction(self):
        """Extrusion along an oblique direction still produces valid body."""
        body = extrude_to_body(_UNIT_SQUARE, [1.0, 0.0, 1.0])
        result = validate_body(body)
        assert result["ok"] is True, f"validate_body errors: {result['errors']}"

    def test_profile_reversed_winding_same_result(self):
        """Reversed polygon winding should produce the same valid body."""
        reversed_square = list(reversed(_UNIT_SQUARE))
        body = extrude_to_body(reversed_square, _Z_DIR)
        result = validate_body(body)
        assert result["ok"] is True, f"validate_body errors: {result['errors']}"
        counts = body.euler_counts()
        assert counts["V"] == 8
        assert counts["E"] == 12
        assert counts["F"] == 6

    def test_error_too_few_vertices(self):
        """Fewer than 3 profile vertices raises BuildError."""
        with pytest.raises(BuildError):
            extrude_to_body([[0, 0, 0], [1, 0, 0]], _Z_DIR)

    def test_error_zero_direction(self):
        """Zero direction vector raises BuildError."""
        with pytest.raises(BuildError):
            extrude_to_body(_UNIT_SQUARE, [0.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# solid_features wrapper tests
# ---------------------------------------------------------------------------


class TestExtrudeToBodySolidFeatures:
    """Tests for the solid_features.extrude_to_body dict-returning wrapper."""

    def test_returns_ok_dict(self):
        """Normal call returns ok=True with expected keys."""
        result = sf_extrude_to_body(_UNIT_SQUARE, _Z_DIR)
        assert result["ok"] is True
        assert "body" in result
        assert "volume" in result
        assert "n_faces" in result
        assert "n_edges" in result
        assert "n_vertices" in result

    def test_topology_counts_in_result(self):
        """n_faces=6, n_edges=12, n_vertices=8 for unit square."""
        result = sf_extrude_to_body(_UNIT_SQUARE, _Z_DIR)
        assert result["n_faces"] == 6
        assert result["n_edges"] == 12
        assert result["n_vertices"] == 8

    def test_volume_unit_square(self):
        """Volume of unit-square extrude = 1.0 (≤1e-9 tolerance)."""
        result = sf_extrude_to_body(_UNIT_SQUARE, _Z_DIR)
        assert abs(result["volume"] - 1.0) <= 1e-9

    def test_body_is_valid_brep(self):
        """The returned body satisfies validate_body."""
        result = sf_extrude_to_body(_UNIT_SQUARE, _Z_DIR)
        body = result["body"]
        assert body is not None
        check = validate_body(body)
        assert check["ok"] is True, f"validate_body errors: {check['errors']}"

    def test_bad_profile_returns_error(self):
        """Too-few vertices returns ok=False, no exception."""
        result = sf_extrude_to_body([[0, 0, 0], [1, 0, 0]], _Z_DIR)
        assert result["ok"] is False
        assert result["body"] is None

    def test_zero_direction_returns_error(self):
        """Zero direction returns ok=False, no exception."""
        result = sf_extrude_to_body(_UNIT_SQUARE, [0.0, 0.0, 0.0])
        assert result["ok"] is False

    def test_geometry_params_present(self):
        """geometry_params contains profile_area, height, direction."""
        result = sf_extrude_to_body(_UNIT_SQUARE, _Z_DIR)
        gp = result["geometry_params"]
        assert "profile_area" in gp
        assert "height" in gp
        assert "direction" in gp
        assert abs(gp["profile_area"] - 1.0) <= 1e-9
        assert abs(gp["height"] - 1.0) <= 1e-9

    def test_rectangle_volume(self):
        """2×3 rectangle extruded by h=4 → volume=24."""
        rect = [
            [0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0],
            [2.0, 3.0, 0.0],
            [0.0, 3.0, 0.0],
        ]
        result = sf_extrude_to_body(rect, [0.0, 0.0, 4.0])
        assert result["ok"] is True
        assert abs(result["volume"] - 24.0) <= 1e-9
