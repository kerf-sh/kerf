"""
tests/test_rules_engine.py — pytest suite for kerf_rules engine.

Coverage
--------
1.  AISC column slenderness — violating model produces exactly one AISC-360-E3-1
    violation citing the correct standard and clause.
2.  AISC column slenderness — compliant model produces zero violations.
3.  AISC rule does NOT fire on a non-column element type.
4.  AISC rule does NOT fire when required properties are missing.
5.  EC2 reinforcement spacing — violating beam produces a violation.
6.  EC2 reinforcement spacing — compliant beam produces zero violations.
7.  ASME B18 fastener grade — missing grade string triggers not_in error.
8.  ASME B18 thread engagement — violation when ratio < 1.0.
9.  ASME B18 thread engagement — compliant when ratio ≥ 1.0.
10. Mixed project — only the violating elements are cited.
11. Empty project — zero violations.
12. Multiple violations in one project — all are returned.
13. Violation.as_dict() contains expected keys.
14. validate_against_rules() LLM tool surface — violating project returns ok=False.
15. validate_against_rules() LLM tool surface — compliant project returns ok=True.
16. RulePack from inline YAML dict (no file I/O needed).
17. RulesEngine OO wrapper returns same results as evaluate().
18. EC2 column min steel — violation when As/Ac < 0.002.
19. EC2 column max steel — violation when As/Ac > 0.04.
20. AISC bolt spacing — violation when s/d < 2.67.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from kerf_rules.dsl import Rule, RulePack, WhenClause, ThenClause, load_rule_file, load_rule_pack
from kerf_rules.engine import evaluate, RulesEngine, Violation
from kerf_rules.tools.validate_against_rules import validate_against_rules

# ---------------------------------------------------------------------------
# Paths to built-in rule files
# ---------------------------------------------------------------------------

_RULES_DIR = Path(__file__).parent.parent / "rules"
_AISC_DIR = _RULES_DIR / "aisc"
_EC2_DIR = _RULES_DIR / "eurocode2"
_ASME_DIR = _RULES_DIR / "asme_b18"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _aisc_pack() -> RulePack:
    return load_rule_pack(_AISC_DIR, name="aisc")


def _ec2_pack() -> RulePack:
    return load_rule_pack(_EC2_DIR, name="eurocode2")


def _asme_pack() -> RulePack:
    return load_rule_pack(_ASME_DIR, name="asme_b18")


def _column(kl_r: float, **extra: Any) -> dict[str, Any]:
    """Build a steel_column element with effective_length / radius_of_gyration yielding Kl/r."""
    return {
        "id": "col-1",
        "element_type": "steel_column",
        "effective_length_mm": kl_r * 100.0,  # rg fixed at 100 mm
        "radius_of_gyration_mm": 100.0,
        **extra,
    }


def _project(*elements: dict[str, Any]) -> dict[str, Any]:
    return {"name": "test", "elements": list(elements)}


# ---------------------------------------------------------------------------
# Test 1 — violating AISC column produces violation citing rule + clause
# ---------------------------------------------------------------------------

class TestAISCColumnSlendernessViolation:
    """Kl/r = 250 — should trigger AISC-360-E3-1."""

    def test_violation_produced(self):
        pack = _aisc_pack()
        project = _project(_column(kl_r=250))
        viols = evaluate(project, pack)
        rule_ids = [v.rule_id for v in viols]
        assert "AISC-360-E3-1" in rule_ids, f"Expected AISC-360-E3-1 in violations; got {rule_ids}"

    def test_standard_cited(self):
        pack = _aisc_pack()
        viols = evaluate(_project(_column(kl_r=250)), pack)
        v = next(v for v in viols if v.rule_id == "AISC-360-E3-1")
        assert "AISC" in v.standard

    def test_clause_cited(self):
        pack = _aisc_pack()
        viols = evaluate(_project(_column(kl_r=250)), pack)
        v = next(v for v in viols if v.rule_id == "AISC-360-E3-1")
        assert "E3" in v.clause or "E3.1" in v.clause

    def test_severity_is_error(self):
        pack = _aisc_pack()
        viols = evaluate(_project(_column(kl_r=250)), pack)
        v = next(v for v in viols if v.rule_id == "AISC-360-E3-1")
        assert v.severity == "error"

    def test_value_is_ratio(self):
        pack = _aisc_pack()
        viols = evaluate(_project(_column(kl_r=250)), pack)
        v = next(v for v in viols if v.rule_id == "AISC-360-E3-1")
        assert v.value is not None
        assert abs(v.value - 250.0) < 0.5, f"Expected value ≈ 250; got {v.value}"


# ---------------------------------------------------------------------------
# Test 2 — compliant AISC column produces zero violations for E3-1
# ---------------------------------------------------------------------------

class TestAISCColumnSlendernessCompliant:
    """Kl/r = 150 — must produce no AISC-360-E3-1 violation."""

    def test_no_violation(self):
        pack = _aisc_pack()
        viols = evaluate(_project(_column(kl_r=150)), pack)
        e3_viols = [v for v in viols if v.rule_id == "AISC-360-E3-1"]
        assert e3_viols == [], f"Unexpected E3-1 violations: {e3_viols}"


# ---------------------------------------------------------------------------
# Test 3 — rule does NOT fire on wrong element type
# ---------------------------------------------------------------------------

class TestAISCRuleIgnoresNonColumn:
    def test_non_column_not_checked(self):
        pack = _aisc_pack()
        elem = {
            "id": "beam-1",
            "element_type": "steel_beam",  # wrong type
            "effective_length_mm": 25000,
            "radius_of_gyration_mm": 100,
        }
        viols = evaluate(_project(elem), pack)
        e3_viols = [v for v in viols if v.rule_id == "AISC-360-E3-1"]
        assert e3_viols == []


# ---------------------------------------------------------------------------
# Test 4 — rule does NOT fire when required properties missing
# ---------------------------------------------------------------------------

class TestAISCRuleSkipsIfMissingProperties:
    def test_missing_rg_skips(self):
        pack = _aisc_pack()
        elem = {
            "id": "col-2",
            "element_type": "steel_column",
            "effective_length_mm": 25000,
            # radius_of_gyration_mm deliberately absent
        }
        viols = evaluate(_project(elem), pack)
        e3_viols = [v for v in viols if v.rule_id == "AISC-360-E3-1"]
        assert e3_viols == []


# ---------------------------------------------------------------------------
# Test 5 — EC2 reinforcement spacing violation
# ---------------------------------------------------------------------------

class TestEC2SpacingViolation:
    """Clear bar spacing 15 mm < 20 mm minimum — EC2-9.2.1-1."""

    def test_violation_produced(self):
        pack = _ec2_pack()
        elem = {
            "id": "beam-rc-1",
            "element_type": "rc_beam",
            "clear_bar_spacing_mm": 15.0,
            "bar_diameter_mm": 16.0,
        }
        viols = evaluate(_project(elem), pack)
        rule_ids = [v.rule_id for v in viols]
        assert "EC2-9.2.1-1" in rule_ids, f"Expected EC2-9.2.1-1; got {rule_ids}"


# ---------------------------------------------------------------------------
# Test 6 — EC2 reinforcement spacing compliant
# ---------------------------------------------------------------------------

class TestEC2SpacingCompliant:
    """Clear bar spacing 25 mm ≥ 20 mm — no EC2-9.2.1-1 violation."""

    def test_no_violation(self):
        pack = _ec2_pack()
        elem = {
            "id": "beam-rc-2",
            "element_type": "rc_beam",
            "clear_bar_spacing_mm": 25.0,
            "bar_diameter_mm": 16.0,
        }
        viols = evaluate(_project(elem), pack)
        ec2_viols = [v for v in viols if v.rule_id == "EC2-9.2.1-1"]
        assert ec2_viols == []


# ---------------------------------------------------------------------------
# Test 7 — ASME B18 missing grade string
# ---------------------------------------------------------------------------

class TestASMEMissingGrade:
    """Hex bolt with empty grade string triggers not_in violation."""

    def test_missing_grade_violation(self):
        pack = _asme_pack()
        elem = {
            "id": "bolt-1",
            "element_type": "hex_bolt",
            "nominal_diameter_mm": 12.0,
            "grade": "",
        }
        viols = evaluate(_project(elem), pack)
        rule_ids = [v.rule_id for v in viols]
        assert "ASME-B18-2.1-1" in rule_ids, f"Expected ASME-B18-2.1-1; got {rule_ids}"


# ---------------------------------------------------------------------------
# Test 8 — ASME B18 thread engagement violation
# ---------------------------------------------------------------------------

class TestASMEThreadEngagementViolation:
    """Thread engagement / d = 0.8 < 1.0 — violation."""

    def test_violation(self):
        pack = _asme_pack()
        elem = {
            "id": "bolt-te-1",
            "element_type": "threaded_fastener",
            "nominal_diameter_mm": 10.0,
            "thread_engagement_mm": 8.0,   # ratio = 0.8 < 1.0
        }
        viols = evaluate(_project(elem), pack)
        rule_ids = [v.rule_id for v in viols]
        assert "ASME-B18-2.1-4" in rule_ids, f"Expected ASME-B18-2.1-4; got {rule_ids}"


# ---------------------------------------------------------------------------
# Test 9 — ASME B18 thread engagement compliant
# ---------------------------------------------------------------------------

class TestASMEThreadEngagementCompliant:
    def test_compliant(self):
        pack = _asme_pack()
        elem = {
            "id": "bolt-te-2",
            "element_type": "threaded_fastener",
            "nominal_diameter_mm": 10.0,
            "thread_engagement_mm": 12.0,  # ratio = 1.2 ≥ 1.0
        }
        viols = evaluate(_project(elem), pack)
        te_viols = [v for v in viols if v.rule_id == "ASME-B18-2.1-4"]
        assert te_viols == []


# ---------------------------------------------------------------------------
# Test 10 — Mixed project, only violating elements are cited
# ---------------------------------------------------------------------------

class TestMixedProject:
    def test_only_violating_cited(self):
        aisc = _aisc_pack()
        bad_col = _column(kl_r=250)
        bad_col["id"] = "bad-col"
        good_col = _column(kl_r=150)
        good_col["id"] = "good-col"
        project = _project(bad_col, good_col)
        viols = evaluate(project, aisc)
        violating_ids = {v.element_id for v in viols if v.rule_id == "AISC-360-E3-1"}
        assert "bad-col" in violating_ids
        assert "good-col" not in violating_ids


# ---------------------------------------------------------------------------
# Test 11 — Empty project
# ---------------------------------------------------------------------------

class TestEmptyProject:
    def test_zero_violations(self):
        pack = _aisc_pack()
        viols = evaluate({"name": "empty", "elements": []}, pack)
        assert viols == []


# ---------------------------------------------------------------------------
# Test 12 — Multiple violations from one project
# ---------------------------------------------------------------------------

class TestMultipleViolations:
    def test_multiple_violations_returned(self):
        """A column with Kl/r=250 and web h/tw=70 should trigger two AISC rules."""
        pack = _aisc_pack()
        elem = {
            "id": "problem-col",
            "element_type": "steel_column",
            "effective_length_mm": 25000,
            "radius_of_gyration_mm": 100,
            "web_height_mm": 350,
            "web_thickness_mm": 5,   # h/tw = 70 > 63.4
        }
        viols = evaluate(_project(elem), pack)
        rule_ids = [v.rule_id for v in viols]
        assert "AISC-360-E3-1" in rule_ids
        assert "AISC-360-E3-2" in rule_ids


# ---------------------------------------------------------------------------
# Test 13 — Violation.as_dict() keys
# ---------------------------------------------------------------------------

class TestViolationDict:
    def test_required_keys(self):
        pack = _aisc_pack()
        viols = evaluate(_project(_column(kl_r=250)), pack)
        assert viols, "Expected at least one violation"
        d = viols[0].as_dict()
        for key in ("rule_id", "standard", "clause", "element_id", "severity", "message", "value", "description"):
            assert key in d, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Test 14 — LLM tool validate_against_rules — violating project
# ---------------------------------------------------------------------------

class TestLLMToolViolating:
    def test_ok_false(self):
        project = _project(_column(kl_r=250))
        result = validate_against_rules(project, "aisc")
        assert result["ok"] is False

    def test_violations_present(self):
        project = _project(_column(kl_r=250))
        result = validate_against_rules(project, "aisc")
        assert result["violation_count"] > 0
        assert len(result["violations"]) == result["violation_count"]

    def test_rule_pack_name(self):
        project = _project(_column(kl_r=250))
        result = validate_against_rules(project, "aisc")
        assert result["rule_pack_name"] == "aisc"


# ---------------------------------------------------------------------------
# Test 15 — LLM tool validate_against_rules — compliant project
# ---------------------------------------------------------------------------

class TestLLMToolCompliant:
    def test_ok_true(self):
        # A steel_beam element — won't match steel_column rules
        elem = {
            "id": "beam-ok",
            "element_type": "steel_beam",
            "unbraced_length_mm": 2000,
            "plastic_moment_length_mm": 5000,
            "web_height_mm": 200,
            "web_thickness_mm": 10,  # h/tw = 20, well within limit
        }
        project = _project(elem)
        result = validate_against_rules(project, "aisc")
        # beams only trigger beam rules; h/tw = 20 << 63.4 so no violations
        assert result["ok"] is True
        assert result["violation_count"] == 0


# ---------------------------------------------------------------------------
# Test 16 — RulePack from inline dict (no file I/O)
# ---------------------------------------------------------------------------

class TestInlinePack:
    def test_inline_rule_pack(self):
        rule = Rule(
            id="TEST-1",
            standard="Test Standard v1",
            clause="1.1",
            description="Diameter must not exceed 100 mm",
            domain="test",
            when=WhenClause(element_type=["test_part"], has_properties=["diameter_mm"]),
            then=ThenClause(
                check="le",
                expr="diameter_mm",
                limit=100.0,
                severity="error",
                message="TEST-1 — part {id}: diameter {value:.1f} mm > 100 mm",
            ),
        )
        pack = RulePack(name="test-pack", rules=[rule])

        # violating
        elem_bad = {"id": "p1", "element_type": "test_part", "diameter_mm": 150.0}
        viols = evaluate({"elements": [elem_bad]}, pack)
        assert len(viols) == 1
        assert viols[0].rule_id == "TEST-1"

        # compliant
        elem_ok = {"id": "p2", "element_type": "test_part", "diameter_mm": 80.0}
        viols = evaluate({"elements": [elem_ok]}, pack)
        assert viols == []


# ---------------------------------------------------------------------------
# Test 17 — RulesEngine OO wrapper
# ---------------------------------------------------------------------------

class TestRulesEngineOO:
    def test_oo_matches_functional(self):
        pack = _aisc_pack()
        project = _project(_column(kl_r=250))
        engine = RulesEngine(pack)
        oo_viols = engine.run(project)
        fn_viols = evaluate(project, pack)
        assert [v.rule_id for v in oo_viols] == [v.rule_id for v in fn_viols]

    def test_rule_count(self):
        pack = _aisc_pack()
        engine = RulesEngine(pack)
        assert engine.rule_count == len(pack.rules)


# ---------------------------------------------------------------------------
# Test 18 — EC2 column min steel violation
# ---------------------------------------------------------------------------

class TestEC2ColumnMinSteel:
    def test_min_steel_violation(self):
        pack = _ec2_pack()
        elem = {
            "id": "rc-col-1",
            "element_type": "rc_column",
            "longitudinal_steel_mm2": 400,    # As
            "gross_area_mm2": 300_000,          # Ac = 500×600
            # 400/300000 = 0.00133 < 0.002
        }
        viols = evaluate(_project(elem), pack)
        rule_ids = [v.rule_id for v in viols]
        assert "EC2-9.5.2-1" in rule_ids, f"Expected EC2-9.5.2-1; got {rule_ids}"


# ---------------------------------------------------------------------------
# Test 19 — EC2 column max steel violation
# ---------------------------------------------------------------------------

class TestEC2ColumnMaxSteel:
    def test_max_steel_violation(self):
        pack = _ec2_pack()
        elem = {
            "id": "rc-col-2",
            "element_type": "rc_column",
            "longitudinal_steel_mm2": 15000,   # 15000/300000 = 0.05 > 0.04
            "gross_area_mm2": 300_000,
        }
        viols = evaluate(_project(elem), pack)
        rule_ids = [v.rule_id for v in viols]
        assert "EC2-9.5.2-2" in rule_ids, f"Expected EC2-9.5.2-2; got {rule_ids}"


# ---------------------------------------------------------------------------
# Test 20 — AISC bolt spacing violation
# ---------------------------------------------------------------------------

class TestAISCBoltSpacingViolation:
    def test_bolt_spacing_violation(self):
        pack = _aisc_pack()
        elem = {
            "id": "bg-1",
            "element_type": "bolt_group",
            "bolt_spacing_mm": 20.0,
            "bolt_diameter_mm": 20.0,   # s/d = 1.0 < 2.67
            "edge_distance_mm": 40.0,
            "plate_thickness_mm": 10.0,
        }
        viols = evaluate(_project(elem), pack)
        rule_ids = [v.rule_id for v in viols]
        assert "AISC-360-J3-1" in rule_ids, f"Expected AISC-360-J3-1; got {rule_ids}"
