"""
Tests for kerf_silicon.drc — Design Rule Check engine.

All polygon coordinates are in nanometres (nm).

Covers:
- Spacing violation (shapes 100 nm apart vs 140 nm rule)
- Width violation (shape narrower than minimum)
- Enclosure violation (nwell must enclose diff by >= 180 nm — tight fixture)
- Clean fixture produces zero violations
- Density rule: empty layer fails min-density check
"""

from __future__ import annotations

import pytest

from kerf_silicon.drc import check, DrcReport
from kerf_silicon.drc.rules import (
    DensityRule,
    EnclosureRule,
    SpacingRule,
    WidthRule,
    SKY130_RULES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rect(layer: str, x0: float, y0: float, x1: float, y1: float) -> dict:
    """Return a rectangular shape dict (coordinates in nm)."""
    return {
        "layer": layer,
        "polygon": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
    }


# ---------------------------------------------------------------------------
# 1. Spacing violation
# Two met1 shapes 100 nm apart; rule requires >= 140 nm → 1 violation
# ---------------------------------------------------------------------------

class TestSpacingViolation:
    def _rules(self):
        return [SpacingRule(rule_name="met1.spacing_test", layer="met1", min_nm=140)]

    def test_shapes_100nm_apart_triggers_violation(self):
        layout = [
            rect("met1", 0, 0, 500, 500),
            rect("met1", 600, 0, 1100, 500),  # gap = 100 nm
        ]
        report = check(layout, self._rules())
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.rule_name == "met1.spacing_test"
        assert v.layer == "met1"
        assert "100" in v.description or "met1" in v.description

    def test_shapes_exactly_at_min_spacing_passes(self):
        layout = [
            rect("met1", 0, 0, 500, 500),
            rect("met1", 640, 0, 1140, 500),  # gap = 140 nm
        ]
        report = check(layout, self._rules())
        assert report.violations == []

    def test_shapes_well_apart_passes(self):
        layout = [
            rect("met1", 0, 0, 500, 500),
            rect("met1", 1000, 0, 1500, 500),  # gap = 500 nm
        ]
        report = check(layout, self._rules())
        assert report.violations == []

    def test_single_shape_no_spacing_violation(self):
        layout = [rect("met1", 0, 0, 500, 500)]
        report = check(layout, self._rules())
        assert report.violations == []


# ---------------------------------------------------------------------------
# 2. Width violation
# met1 min width = 140 nm; shape 100 nm wide → violation
# ---------------------------------------------------------------------------

class TestWidthViolation:
    def _rules(self):
        return [WidthRule(rule_name="met1.width_test", layer="met1", min_nm=140)]

    def test_shape_100nm_wide_triggers_violation(self):
        layout = [rect("met1", 0, 0, 100, 1000)]  # width = 100 nm
        report = check(layout, self._rules())
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.rule_name == "met1.width_test"

    def test_shape_at_min_width_passes(self):
        layout = [rect("met1", 0, 0, 140, 1000)]  # width = 140 nm exactly
        report = check(layout, self._rules())
        assert report.violations == []

    def test_shape_above_min_width_passes(self):
        layout = [rect("met1", 0, 0, 500, 500)]  # width = 500 nm
        report = check(layout, self._rules())
        assert report.violations == []


# ---------------------------------------------------------------------------
# 3. Enclosure violation
# nwell must enclose diff by >= 180 nm; tight fixture triggers the rule
# ---------------------------------------------------------------------------

class TestEnclosureViolation:
    def _rules(self):
        return [
            EnclosureRule(
                rule_name="nwell.enc.diff_test",
                outer_layer="nwell",
                inner_layer="diff",
                enc_nm=180,
            )
        ]

    def test_tight_enclosure_triggers_violation(self):
        # nwell: 0..1000 x 0..1000
        # diff:  50..950 x 50..950  → enclosure = 50 nm, below 180 nm
        layout = [
            rect("nwell", 0, 0, 1000, 1000),
            rect("diff", 50, 50, 950, 950),
        ]
        report = check(layout, self._rules())
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.rule_name == "nwell.enc.diff_test"
        assert v.layer == "diff"

    def test_adequate_enclosure_passes(self):
        # nwell: 0..2000 x 0..2000
        # diff:  200..1800 x 200..1800  → enclosure = 200 nm >= 180 nm
        layout = [
            rect("nwell", 0, 0, 2000, 2000),
            rect("diff", 200, 200, 1800, 1800),
        ]
        report = check(layout, self._rules())
        assert report.violations == []

    def test_diff_with_no_nwell_triggers_violation(self):
        layout = [rect("diff", 0, 0, 500, 500)]  # no nwell at all
        report = check(layout, self._rules())
        assert len(report.violations) == 1


# ---------------------------------------------------------------------------
# 4. Known-good fixture — zero violations
# ---------------------------------------------------------------------------

class TestKnownGoodFixture:
    def test_well_spaced_met1_shapes_pass_all_rules(self):
        """
        Two met1 shapes that satisfy all relevant SKY130 width + spacing rules.
        Shape width = 500 nm (>= 140), spacing = 500 nm (>= 140).
        """
        rules = [
            WidthRule(rule_name="met1.1", layer="met1", min_nm=140),
            SpacingRule(rule_name="met1.2", layer="met1", min_nm=140),
        ]
        layout = [
            rect("met1", 0, 0, 500, 500),
            rect("met1", 1000, 0, 1500, 500),
        ]
        report = check(layout, rules)
        assert report.violations == []
        assert report.passed_rules == 2

    def test_empty_layout_no_violations_on_width_spacing(self):
        rules = [
            WidthRule(rule_name="met1.1", layer="met1", min_nm=140),
            SpacingRule(rule_name="met1.2", layer="met1", min_nm=140),
        ]
        report = check([], rules)
        assert report.violations == []

    def test_properly_enclosed_diff_passes(self):
        rules = [
            EnclosureRule(
                rule_name="nwell.enc.diff",
                outer_layer="nwell",
                inner_layer="diff",
                enc_nm=180,
            )
        ]
        layout = [
            rect("nwell", 0, 0, 3000, 3000),
            rect("diff", 200, 200, 2800, 2800),  # margin = 200 nm >= 180 nm
        ]
        report = check(layout, rules)
        assert report.violations == []


# ---------------------------------------------------------------------------
# 5. Density rule — empty layer fails min-density check
# ---------------------------------------------------------------------------

class TestDensityViolation:
    def _density_rule(self, min_pct: float = 20.0, max_pct: float = 80.0):
        return DensityRule(
            rule_name="met1.dens_test",
            layer="met1",
            min_pct=min_pct,
            max_pct=max_pct,
            tile_nm=1000.0,  # small tile so a tiny shape can exceed max
        )

    def test_empty_layer_fails_min_density(self):
        """No met1 shapes at all → density = 0 % < 20 % min → violation."""
        # Provide another layer so the engine has something for the bounding box
        layout = [rect("poly", 0, 0, 1000, 1000)]
        rule = self._density_rule(min_pct=20.0)
        report = check(layout, [rule])
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.rule_name == "met1.dens_test"
        assert "below minimum" in v.description

    def test_fully_empty_layout_fails_min_density(self):
        """Completely empty layout; no shapes at all → 0 % < 20 %."""
        rule = self._density_rule(min_pct=20.0)
        report = check([], [rule])
        assert len(report.violations) == 1
        assert "below minimum" in report.violations[0].description

    def test_adequate_density_passes(self):
        """
        A met1 shape that covers ~25 % of the tile area → passes 20 % min rule.
        Tile = 1000 x 1000 nm = 1e6 nm².
        Shape = 500 x 500 nm = 2.5e5 nm² → 25 %.
        """
        rule = self._density_rule(min_pct=20.0, max_pct=80.0)
        layout = [rect("met1", 0, 0, 500, 500)]
        report = check(layout, [rule])
        assert report.violations == []

    def test_excessive_density_triggers_max_violation(self):
        """
        met1 fills the tile completely → 100 % > 80 % → violation.
        tile_nm = 1000, shape = 1000 x 1000 = 100 %.
        """
        rule = self._density_rule(min_pct=20.0, max_pct=80.0)
        layout = [rect("met1", 0, 0, 1000, 1000)]
        report = check(layout, [rule])
        assert len(report.violations) == 1
        assert "above maximum" in report.violations[0].description


# ---------------------------------------------------------------------------
# 6. DrcReport structure
# ---------------------------------------------------------------------------

class TestDrcReport:
    def test_to_dict_contains_expected_keys(self):
        rules = [SpacingRule(rule_name="met1.2", layer="met1", min_nm=140)]
        layout = [
            rect("met1", 0, 0, 500, 500),
            rect("met1", 600, 0, 1100, 500),  # 100 nm gap → violation
        ]
        report = check(layout, rules)
        d = report.to_dict()
        assert "violations" in d
        assert "passed_rules" in d
        assert "violation_count" in d
        assert d["violation_count"] == len(report.violations)

    def test_passed_rules_increments_on_pass(self):
        rules = [
            SpacingRule(rule_name="met1.pass", layer="met1", min_nm=50),
        ]
        layout = [
            rect("met1", 0, 0, 500, 500),
            rect("met1", 600, 0, 1100, 500),  # 100 nm > 50 nm min → passes
        ]
        report = check(layout, rules)
        assert report.violations == []
        assert report.passed_rules == 1


# ---------------------------------------------------------------------------
# 7. SKY130 pre-baked rules sanity check
# ---------------------------------------------------------------------------

class TestSKY130Rules:
    def test_sky130_rules_list_has_minimum_count(self):
        assert len(SKY130_RULES) >= 15

    def test_sky130_rules_include_all_families(self):
        from kerf_silicon.drc.rules import RuleFamily
        families = {r.family for r in SKY130_RULES}
        assert RuleFamily.WIDTH in families
        assert RuleFamily.SPACING in families
        assert RuleFamily.ENCLOSURE in families
        assert RuleFamily.DENSITY in families
        assert RuleFamily.OVERLAP in families

    def test_clean_layout_passes_relevant_sky130_rules(self):
        """
        A met1 shape that is 500 nm wide and the only shape on its layer
        should pass both met1.1 (width >= 140) and met1.2 (spacing — only 1 shape).
        Density may legitimately fail (skipped here).
        """
        from kerf_silicon.drc.rules import SKY130_RULES, RuleFamily
        layout = [rect("met1", 0, 0, 500, 500)]
        # Only width + spacing rules for met1 (exclude density)
        met1_geom_rules = [
            r for r in SKY130_RULES
            if getattr(r, "layer", None) == "met1"
            and r.family in (RuleFamily.WIDTH, RuleFamily.SPACING)
        ]
        report = check(layout, met1_geom_rules)
        assert report.violations == []
