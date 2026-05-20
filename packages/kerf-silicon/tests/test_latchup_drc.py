"""
Tests for kerf_silicon.drc.latchup — latch-up rule checker.

Three fixture scenarios:

1. latchup_violation_tap   — nwell with no tap within 15 µm of centroid →
                             exactly 1 "well_tap" violation citing the exceeded
                             distance and the well centroid.

2. latchup_violation_adjacency — n+ (nsdm) inside nwell sits 0.5 µm from p+
                                 (psdm) outside nwell →  exactly 1 "np_adjacency"
                                 violation citing the measured distance and
                                 the n+/p+ pair.

3. latchup_clean           — nwell with tap within 5 µm AND n+/p+ separated
                             by 3.5 µm across the well boundary → 0 violations.

All polygon coordinates are in micrometres (µm).
"""

from __future__ import annotations

import json
import math
import pathlib

import pytest

from kerf_silicon.drc.latchup import (
    LatchupReport,
    LatchupRules,
    LatchupViolation,
    SKY130_LATCHUP_RULES,
    check_latchup,
)

# ---------------------------------------------------------------------------
# Fixture loader
# ---------------------------------------------------------------------------

_FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "drc"


def _load_fixture(name: str) -> list[dict]:
    """
    Load a layout from a JSON descriptor file.

    The JSON format is:
        {
          "layers": {
            "nwell": [{"polygon": [[x, y], ...]}, ...],
            "tap":   [...],
            ...
          }
        }

    Returns a list of shape dicts compatible with check_latchup():
        [{"layer": "nwell", "polygon": [(x, y), ...]}, ...]
    """
    path = _FIXTURE_DIR / f"{name}.json"
    data = json.loads(path.read_text())
    shapes: list[dict] = []
    for layer_name, polys in data.get("layers", {}).items():
        for entry in polys:
            polygon = [tuple(pt) for pt in entry["polygon"]]
            shapes.append({"layer": layer_name, "polygon": polygon})
    return shapes


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def rect(layer: str, x0: float, y0: float, x1: float, y1: float) -> dict:
    """Return a rectangular shape dict (coordinates in µm)."""
    return {
        "layer": layer,
        "polygon": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
    }


# ---------------------------------------------------------------------------
# 1. Well-tap spacing violation
# ---------------------------------------------------------------------------

class TestWellTapViolation:
    """
    Fixture: 30×30 µm nwell, centroid at (15, 15).
    Nearest tap is 40 µm away from the centroid.
    SKY130 limit = 15 µm → 1 violation.
    """

    def _report(self) -> LatchupReport:
        layout = _load_fixture("latchup_violation_tap")
        return check_latchup(layout)

    def test_exactly_one_violation(self):
        report = self._report()
        assert len(report.violations) == 1, (
            f"Expected 1 violation, got {len(report.violations)}: {report.violations}"
        )

    def test_violation_check_type(self):
        v = self._report().violations[0]
        assert v.check == "well_tap"

    def test_violation_location_near_well_centroid(self):
        """The violation location should be the well centroid (15, 15)."""
        v = self._report().violations[0]
        cx, cy = v.location
        assert abs(cx - 15.0) < 0.5, f"centroid x={cx}, expected ≈ 15"
        assert abs(cy - 15.0) < 0.5, f"centroid y={cy}, expected ≈ 15"

    def test_violation_description_mentions_distance(self):
        v = self._report().violations[0]
        desc = v.description
        # Description should contain "µm" to cite a distance
        assert "µm" in desc, f"description does not mention µm: {desc}"
        # Should mention the exceeded limit
        assert "15" in desc or "limit" in desc.lower(), (
            f"description doesn't mention the 15 µm limit: {desc}"
        )

    def test_violation_description_mentions_well_centroid(self):
        v = self._report().violations[0]
        # Centroid coordinates should appear in the description
        assert "15" in v.description, (
            f"description doesn't cite the well centroid coordinate: {v.description}"
        )

    def test_wells_checked_is_one(self):
        report = self._report()
        assert report.wells_checked == 1

    def test_to_dict_structure(self):
        report = self._report()
        d = report.to_dict()
        assert d["violation_count"] == 1
        assert d["violations"][0]["check"] == "well_tap"


# ---------------------------------------------------------------------------
# 2. n+/p+ adjacency violation
# ---------------------------------------------------------------------------

class TestNpAdjacencyViolation:
    """
    Fixture: nsdm (n+) inside nwell, right edge at x=9.5.
             psdm (p+) outside nwell, left edge at x=10.0.
             Gap = 0.5 µm < SKY130 threshold 0.84 µm → 1 violation.
    """

    def _report(self) -> LatchupReport:
        layout = _load_fixture("latchup_violation_adjacency")
        return check_latchup(layout)

    def test_exactly_one_violation(self):
        report = self._report()
        assert len(report.violations) == 1, (
            f"Expected 1 violation, got {len(report.violations)}: {report.violations}"
        )

    def test_violation_check_type(self):
        v = self._report().violations[0]
        assert v.check == "np_adjacency"

    def test_violation_description_mentions_measured_distance(self):
        v = self._report().violations[0]
        desc = v.description
        assert "µm" in desc, f"description does not mention µm: {desc}"
        # The measured distance is 0.5 µm; confirm it appears
        assert "0.5" in desc or "0.50" in desc, (
            f"description doesn't cite the 0.5 µm measured distance: {desc}"
        )

    def test_violation_description_mentions_layer_names(self):
        v = self._report().violations[0]
        assert "nsdm" in v.description
        assert "psdm" in v.description

    def test_violation_location_in_nsdm_region(self):
        """Location should be near the nsdm centroid inside the nwell."""
        v = self._report().violations[0]
        cx, cy = v.location
        # nsdm polygon: x=6.5..9.5, y=4..6 → centroid ≈ (8.0, 5.0)
        assert 6.0 <= cx <= 10.0, f"nsdm centroid x={cx} out of expected range"
        assert 3.5 <= cy <= 6.5, f"nsdm centroid y={cy} out of expected range"

    def test_np_pairs_checked_nonzero(self):
        report = self._report()
        assert report.np_pairs_checked >= 1

    def test_no_well_tap_violation_in_adjacency_fixture(self):
        """The adjacency fixture has a valid tap, so no well_tap violation."""
        report = self._report()
        tap_viols = [v for v in report.violations if v.check == "well_tap"]
        assert len(tap_viols) == 0, (
            f"Unexpected well_tap violations: {tap_viols}"
        )


# ---------------------------------------------------------------------------
# 3. Clean control fixture — 0 violations
# ---------------------------------------------------------------------------

class TestCleanFixture:
    """
    Fixture: nwell with tap at ~4.24 µm from centroid (< 15 µm limit),
             and nsdm/psdm separated by 3.5 µm (> 0.84 µm limit).
    Expects zero violations.
    """

    def _report(self) -> LatchupReport:
        layout = _load_fixture("latchup_clean")
        return check_latchup(layout)

    def test_no_violations(self):
        report = self._report()
        assert report.violations == [], (
            f"Expected 0 violations in clean fixture, got: {report.violations}"
        )

    def test_wells_checked_is_one(self):
        report = self._report()
        assert report.wells_checked == 1

    def test_np_pairs_checked_nonzero(self):
        report = self._report()
        assert report.np_pairs_checked >= 1

    def test_to_dict_violation_count_zero(self):
        report = self._report()
        assert report.to_dict()["violation_count"] == 0


# ---------------------------------------------------------------------------
# 4. Inline geometry tests (no fixture files)
# ---------------------------------------------------------------------------

class TestInlineWellTapSpacing:
    """Unit tests for well-tap check using hand-built layouts."""

    def test_no_tap_at_all_triggers_violation(self):
        """An nwell with no tap shapes triggers a violation."""
        layout = [rect("nwell", 0, 0, 10, 10)]
        report = check_latchup(layout)
        assert len(report.violations) == 1
        assert report.violations[0].check == "well_tap"

    def test_tap_within_limit_passes(self):
        """Tap at centroid distance 5 µm < 15 µm limit → no violation."""
        layout = [
            rect("nwell", 0, 0, 10, 10),         # centroid (5, 5)
            rect("tap",   4, 4,  6,  6),           # centroid (5, 5) → distance 0
        ]
        report = check_latchup(layout)
        well_tap_viols = [v for v in report.violations if v.check == "well_tap"]
        assert len(well_tap_viols) == 0

    def test_tap_exactly_at_limit_passes(self):
        """Tap whose nearest boundary point is exactly 15 µm from centroid passes."""
        # nwell centroid at (5, 5). Tap right edge at x = 5 + 15 = 20.
        layout = [
            rect("nwell", 0, 0, 10, 10),
            rect("tap",  20, 4,  22,  6),
        ]
        report = check_latchup(layout)
        well_tap_viols = [v for v in report.violations if v.check == "well_tap"]
        assert len(well_tap_viols) == 0, (
            f"Tap at exactly 15 µm should pass; got: {well_tap_viols}"
        )

    def test_tap_just_beyond_limit_triggers_violation(self):
        """Tap just beyond 15 µm triggers a violation."""
        layout = [
            rect("nwell", 0, 0, 10, 10),
            rect("tap",  20.1, 4,  22.1, 6),
        ]
        report = check_latchup(layout)
        well_tap_viols = [v for v in report.violations if v.check == "well_tap"]
        assert len(well_tap_viols) == 1

    def test_custom_max_distance_respected(self):
        """Custom rule with tighter 5 µm limit triggers on a 10 µm tap."""
        rules = LatchupRules(max_tap_distance_um=5.0)
        layout = [
            rect("nwell", 0, 0, 10, 10),   # centroid (5, 5)
            rect("tap",  16, 4, 18, 6),    # left edge at x=16 → distance from centroid = 11 µm
        ]
        report = check_latchup(layout, rules)
        well_tap_viols = [v for v in report.violations if v.check == "well_tap"]
        assert len(well_tap_viols) == 1

    def test_empty_layout_no_violations(self):
        report = check_latchup([])
        assert report.violations == []
        assert report.wells_checked == 0


class TestInlineNpAdjacency:
    """Unit tests for n+/p+ adjacency check using hand-built layouts."""

    def _nwell_with_tap(self):
        """Return a basic nwell + tap layout that passes the well-tap rule."""
        return [
            rect("nwell", 0, 0, 10, 10),
            rect("tap", 0.5, 0.5, 2.5, 2.5),
        ]

    def test_np_closer_than_threshold_across_boundary_triggers(self):
        """
        nsdm inside nwell right edge at x=9.
        psdm outside nwell left edge at x=9.5.
        Gap = 0.5 µm < 0.84 µm → 1 adjacency violation.
        """
        layout = self._nwell_with_tap() + [
            rect("nsdm", 6, 4, 9, 6),       # inside nwell; centroid (7.5, 5)
            rect("psdm", 9.5, 4, 12.5, 6),  # outside nwell; centroid (11, 5)
        ]
        report = check_latchup(layout)
        adj_viols = [v for v in report.violations if v.check == "np_adjacency"]
        assert len(adj_viols) == 1, f"Expected 1 adjacency violation; got: {adj_viols}"

    def test_np_at_min_separation_passes(self):
        """
        nsdm right edge at x=9, psdm left edge at x=9.84.
        Gap = 0.84 µm == threshold → passes (equal is fine).
        """
        layout = self._nwell_with_tap() + [
            rect("nsdm", 6, 4, 9, 6),
            rect("psdm", 9.84, 4, 12.84, 6),
        ]
        report = check_latchup(layout)
        adj_viols = [v for v in report.violations if v.check == "np_adjacency"]
        assert len(adj_viols) == 0

    def test_np_well_separated_passes(self):
        """
        nsdm right edge at x=9, psdm left edge at x=11 → gap 2 µm > 0.84 µm.
        """
        layout = self._nwell_with_tap() + [
            rect("nsdm", 6, 4, 9, 6),
            rect("psdm", 11, 4, 13, 6),
        ]
        report = check_latchup(layout)
        adj_viols = [v for v in report.violations if v.check == "np_adjacency"]
        assert len(adj_viols) == 0

    def test_np_same_side_no_violation(self):
        """
        Both nsdm and psdm inside nwell (same side of boundary).
        Even if close, this is not a latch-up risk scenario → no violation.
        """
        layout = self._nwell_with_tap() + [
            rect("nsdm", 3, 4, 5, 6),    # inside nwell; centroid (4, 5)
            rect("psdm", 5.2, 4, 7, 6),  # also inside nwell (centroid 6.1 < 10); gap 0.2 µm
        ]
        report = check_latchup(layout)
        adj_viols = [v for v in report.violations if v.check == "np_adjacency"]
        assert len(adj_viols) == 0, (
            f"Same-side np should not trigger; got: {adj_viols}"
        )

    def test_no_nsdm_or_psdm_no_adjacency_violations(self):
        """No n+/p+ regions → no adjacency check violations."""
        layout = self._nwell_with_tap()
        report = check_latchup(layout)
        adj_viols = [v for v in report.violations if v.check == "np_adjacency"]
        assert len(adj_viols) == 0


# ---------------------------------------------------------------------------
# 5. LatchupReport structure
# ---------------------------------------------------------------------------

class TestLatchupReportStructure:
    def test_to_dict_keys(self):
        layout = [rect("nwell", 0, 0, 5, 5)]
        report = check_latchup(layout)
        d = report.to_dict()
        assert "violations" in d
        assert "wells_checked" in d
        assert "np_pairs_checked" in d
        assert "violation_count" in d

    def test_has_violations_property(self):
        layout = [rect("nwell", 0, 0, 5, 5)]
        report = check_latchup(layout)
        assert report.has_violations is True

    def test_has_violations_false_when_clean(self):
        layout = [
            rect("nwell", 0, 0, 10, 10),
            rect("tap", 4, 4, 6, 6),
        ]
        report = check_latchup(layout)
        assert report.has_violations is False


# ---------------------------------------------------------------------------
# 6. SKY130 defaults sanity check
# ---------------------------------------------------------------------------

class TestSKY130LatchupDefaults:
    def test_default_rules_exist(self):
        assert SKY130_LATCHUP_RULES is not None

    def test_default_well_tap_distance(self):
        assert SKY130_LATCHUP_RULES.max_tap_distance_um == 15.0

    def test_default_np_separation(self):
        assert SKY130_LATCHUP_RULES.min_np_separation_um == 0.84

    def test_default_layer_names(self):
        r = SKY130_LATCHUP_RULES
        assert r.well_layer == "nwell"
        assert r.tap_layer == "tap"
        assert r.n_plus_layer == "nsdm"
        assert r.p_plus_layer == "psdm"

    def test_none_rules_uses_defaults(self):
        """Passing rules=None should use SKY130 defaults."""
        layout = [rect("nwell", 0, 0, 5, 5)]
        report = check_latchup(layout, rules=None)
        assert len(report.violations) == 1
        assert report.violations[0].check == "well_tap"
