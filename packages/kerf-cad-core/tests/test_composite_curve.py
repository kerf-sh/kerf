"""
test_composite_curve.py
=======================
Hermetic analytic-oracle tests for GK-100: composite curve (poly-NURBS chain
with G0/G1/G2 continuity tags + join/split).

Oracles:
  - Two collinear line segments joined end-to-end → single G1 composite with
    correct total_length.
  - split_composite at index 1 recovers the original two segments.
  - A pair of segments with a positional gap → G0 tag.
  - Proper __all__ export through geom/__init__.py.

No OCC, no network, no database.  All oracles are closed-form.
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from kerf_cad_core.geom.nurbs import NurbsCurve
from kerf_cad_core.geom.curve_toolkit import composite_curve, split_composite, curve_length


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line_curve(p0, p1):
    """Return a degree-1 NurbsCurve that is a straight line from p0 to p1."""
    cp = np.array([p0, p1], dtype=float)
    knots = np.array([0.0, 0.0, 1.0, 1.0], dtype=float)
    return NurbsCurve(degree=1, control_points=cp, knots=knots)


# ---------------------------------------------------------------------------
# GK-100 tests
# ---------------------------------------------------------------------------

class TestCompositeCurveCollinear:
    """Two collinear segments joined end-to-end."""

    def setup_method(self):
        # Segment A: (0,0,0) → (3,0,0),  length = 3
        # Segment B: (3,0,0) → (7,0,0),  length = 4
        self.seg_a = _line_curve([0.0, 0.0, 0.0], [3.0, 0.0, 0.0])
        self.seg_b = _line_curve([3.0, 0.0, 0.0], [7.0, 0.0, 0.0])
        self.comp = composite_curve([self.seg_a, self.seg_b])

    def test_returns_dict_with_expected_keys(self):
        assert "segments" in self.comp
        assert "continuity_tags" in self.comp
        assert "total_length" in self.comp

    def test_segment_count(self):
        assert len(self.comp["segments"]) == 2

    def test_continuity_tag_count(self):
        """One junction → one tag."""
        assert len(self.comp["continuity_tags"]) == 1

    def test_tag_is_g1(self):
        """Collinear segments share position and tangent direction → at least G1."""
        tag = self.comp["continuity_tags"][0]
        assert tag in ("G1", "G2"), f"expected G1 or G2, got {tag!r}"

    def test_total_length_exact(self):
        """Total length must be 3 + 4 = 7 (analytic oracle)."""
        assert self.comp["total_length"] == pytest.approx(7.0, abs=1e-6)

    def test_individual_lengths_sum_correctly(self):
        la = curve_length(self.seg_a)
        lb = curve_length(self.seg_b)
        assert la == pytest.approx(3.0, abs=1e-6)
        assert lb == pytest.approx(4.0, abs=1e-6)
        assert la + lb == pytest.approx(self.comp["total_length"], abs=1e-9)


class TestSplitCompositeReturnsOriginals:
    """split_composite at index 1 of a two-segment composite returns the originals."""

    def setup_method(self):
        self.seg_a = _line_curve([0.0, 0.0, 0.0], [3.0, 0.0, 0.0])
        self.seg_b = _line_curve([3.0, 0.0, 0.0], [7.0, 0.0, 0.0])
        self.comp = composite_curve([self.seg_a, self.seg_b])

    def test_split_returns_list_of_two(self):
        parts = split_composite(self.comp, 1)
        assert isinstance(parts, list)
        assert len(parts) == 2

    def test_left_part_has_first_segment(self):
        parts = split_composite(self.comp, 1)
        left = parts[0]
        assert len(left["segments"]) == 1
        # Control points must match seg_a
        np.testing.assert_allclose(
            left["segments"][0].control_points,
            self.seg_a.control_points,
        )

    def test_right_part_has_second_segment(self):
        parts = split_composite(self.comp, 1)
        right = parts[1]
        assert len(right["segments"]) == 1
        np.testing.assert_allclose(
            right["segments"][0].control_points,
            self.seg_b.control_points,
        )

    def test_left_length_oracle(self):
        parts = split_composite(self.comp, 1)
        assert parts[0]["total_length"] == pytest.approx(3.0, abs=1e-6)

    def test_right_length_oracle(self):
        parts = split_composite(self.comp, 1)
        assert parts[1]["total_length"] == pytest.approx(4.0, abs=1e-6)

    def test_lengths_sum_to_original(self):
        parts = split_composite(self.comp, 1)
        total = parts[0]["total_length"] + parts[1]["total_length"]
        assert total == pytest.approx(self.comp["total_length"], abs=1e-9)

    def test_left_continuity_tags_empty(self):
        """Single-segment composite has no junctions."""
        parts = split_composite(self.comp, 1)
        assert parts[0]["continuity_tags"] == []

    def test_right_continuity_tags_empty(self):
        parts = split_composite(self.comp, 1)
        assert parts[1]["continuity_tags"] == []

    def test_invalid_index_raises(self):
        with pytest.raises(ValueError):
            split_composite(self.comp, 0)
        with pytest.raises(ValueError):
            split_composite(self.comp, 2)


class TestCompositeCurveG0Gap:
    """Two segments with a positional gap at the junction → G0 tag."""

    def test_gap_gives_g0(self):
        seg_a = _line_curve([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        # seg_b starts at a different point — gap
        seg_b = _line_curve([2.0, 0.0, 0.0], [3.0, 0.0, 0.0])
        comp = composite_curve([seg_a, seg_b])
        assert comp["continuity_tags"][0] == "G0"


class TestCompositeCurveThreeSegments:
    """Three collinear segments → two G1 tags, total_length = sum of three."""

    def test_three_segments(self):
        seg_a = _line_curve([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        seg_b = _line_curve([1.0, 0.0, 0.0], [3.0, 0.0, 0.0])
        seg_c = _line_curve([3.0, 0.0, 0.0], [6.0, 0.0, 0.0])
        comp = composite_curve([seg_a, seg_b, seg_c])
        assert len(comp["continuity_tags"]) == 2
        for tag in comp["continuity_tags"]:
            assert tag in ("G1", "G2")
        assert comp["total_length"] == pytest.approx(6.0, abs=1e-6)

    def test_split_three_segments_at_index_2(self):
        seg_a = _line_curve([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        seg_b = _line_curve([1.0, 0.0, 0.0], [3.0, 0.0, 0.0])
        seg_c = _line_curve([3.0, 0.0, 0.0], [6.0, 0.0, 0.0])
        comp = composite_curve([seg_a, seg_b, seg_c])
        parts = split_composite(comp, 2)
        # Left: [seg_a, seg_b], right: [seg_c]
        assert len(parts[0]["segments"]) == 2
        assert len(parts[1]["segments"]) == 1
        assert parts[0]["total_length"] == pytest.approx(3.0, abs=1e-6)
        assert parts[1]["total_length"] == pytest.approx(3.0, abs=1e-6)
        assert len(parts[0]["continuity_tags"]) == 1


class TestCompositeCurveExport:
    """Verify the symbols are exported from geom/__init__.py __all__."""

    def test_exported_via_init(self):
        from kerf_cad_core.geom import composite_curve as cc, split_composite as sc
        assert callable(cc)
        assert callable(sc)

    def test_in_all(self):
        import kerf_cad_core.geom as geom
        assert "composite_curve" in geom.__all__
        assert "split_composite" in geom.__all__


class TestCompositeCurveSingleSegment:
    """Single segment → empty continuity_tags, length = segment length."""

    def test_single_segment(self):
        seg = _line_curve([0.0, 0.0, 0.0], [5.0, 0.0, 0.0])
        comp = composite_curve([seg])
        assert len(comp["segments"]) == 1
        assert comp["continuity_tags"] == []
        assert comp["total_length"] == pytest.approx(5.0, abs=1e-6)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            composite_curve([])
