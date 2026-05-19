"""Tests for the DAL classifier and artefact list utilities.

Verifies:
- All five severity categories map to the correct DAL letter
- Case-insensitivity and variant spellings
- Invalid severity raises ValueError
- DAL descriptions are returned correctly
- DO-178C and DO-254 artefact lists meet minimum counts per standard
- DAL E produces the exempt message
"""
import pytest

from kerf_aero.cert.dal_classifier import (
    classify_dal,
    dal_description,
    required_artefacts_do178c,
    required_artefacts_do254,
)


# ---------------------------------------------------------------------------
# classify_dal — mapping correctness
# ---------------------------------------------------------------------------

class TestClassifyDAL:
    @pytest.mark.parametrize("severity,expected_dal", [
        ("catastrophic", "A"),
        ("hazardous", "B"),
        ("major", "C"),
        ("minor", "D"),
        ("no_effect", "E"),
    ])
    def test_canonical_severities(self, severity, expected_dal):
        assert classify_dal(severity) == expected_dal

    def test_case_insensitive_upper(self):
        assert classify_dal("CATASTROPHIC") == "A"
        assert classify_dal("HAZARDOUS") == "B"
        assert classify_dal("MAJOR") == "C"
        assert classify_dal("MINOR") == "D"
        assert classify_dal("NO_EFFECT") == "E"

    def test_case_insensitive_mixed(self):
        assert classify_dal("Catastrophic") == "A"
        assert classify_dal("Hazardous") == "B"
        assert classify_dal("Major") == "C"
        assert classify_dal("Minor") == "D"

    def test_no_effect_variants(self):
        assert classify_dal("no_effect") == "E"
        assert classify_dal("no effect") == "E"
        assert classify_dal("no-effect") == "E"
        assert classify_dal("NO EFFECT") == "E"
        assert classify_dal("No-Effect") == "E"

    def test_leading_trailing_whitespace_ignored(self):
        assert classify_dal("  catastrophic  ") == "A"
        assert classify_dal("\tminor\n") == "D"

    def test_unknown_severity_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown severity"):
            classify_dal("trivial")

    def test_unknown_severity_message_contains_input(self):
        with pytest.raises(ValueError, match="bogus"):
            classify_dal("bogus")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            classify_dal("")

    def test_return_type_is_str(self):
        result = classify_dal("catastrophic")
        assert isinstance(result, str)
        assert len(result) == 1

    def test_all_unique_outputs(self):
        sevs = ["catastrophic", "hazardous", "major", "minor", "no_effect"]
        results = [classify_dal(s) for s in sevs]
        assert len(set(results)) == 5


# ---------------------------------------------------------------------------
# dal_description
# ---------------------------------------------------------------------------

class TestDalDescription:
    @pytest.mark.parametrize("dal,keyword", [
        ("A", "Catastrophic"),
        ("B", "Hazardous"),
        ("C", "Major"),
        ("D", "Minor"),
        ("E", "No Effect"),
    ])
    def test_description_contains_keyword(self, dal, keyword):
        desc = dal_description(dal)
        assert keyword in desc

    def test_case_insensitive(self):
        assert dal_description("a") == dal_description("A")
        assert dal_description("b") == dal_description("B")

    def test_invalid_dal_raises(self):
        with pytest.raises(ValueError, match="Invalid DAL"):
            dal_description("F")

    def test_invalid_dal_number_raises(self):
        with pytest.raises(ValueError):
            dal_description("1")

    def test_returns_string(self):
        assert isinstance(dal_description("A"), str)


# ---------------------------------------------------------------------------
# required_artefacts_do178c
# ---------------------------------------------------------------------------

class TestRequiredArtefactsDO178C:
    def test_dal_a_minimum_count(self):
        artefacts = required_artefacts_do178c("A")
        assert len(artefacts) >= 20, (
            f"DAL A should require ≥ 20 artefacts, got {len(artefacts)}"
        )

    def test_dal_b_minimum_count(self):
        artefacts = required_artefacts_do178c("B")
        assert len(artefacts) >= 20, (
            f"DAL B should require ≥ 20 artefacts, got {len(artefacts)}"
        )

    def test_dal_a_has_mcdc(self):
        artefacts = required_artefacts_do178c("A")
        combined = " ".join(artefacts).lower()
        assert "mc/dc" in combined or "mcdc" in combined, (
            "DAL A must include MC/DC structural coverage"
        )

    def test_dal_b_no_mcdc(self):
        artefacts = required_artefacts_do178c("B")
        combined = " ".join(artefacts).lower()
        assert "mc/dc" not in combined, (
            "DAL B should NOT include MC/DC coverage"
        )

    def test_dal_b_has_decision_coverage(self):
        artefacts = required_artefacts_do178c("B")
        combined = " ".join(artefacts).lower()
        assert "decision" in combined, (
            "DAL B must include decision coverage"
        )

    def test_dal_c_has_statement_only(self):
        artefacts = required_artefacts_do178c("C")
        combined = " ".join(artefacts).lower()
        assert "statement" in combined
        assert "mc/dc" not in combined
        assert "decision" not in combined

    def test_dal_d_no_structural_coverage(self):
        artefacts = required_artefacts_do178c("D")
        combined = " ".join(artefacts).lower()
        assert "structural coverage" not in combined

    def test_dal_e_returns_exempt(self):
        artefacts = required_artefacts_do178c("E")
        assert len(artefacts) == 1
        assert "E" in artefacts[0] or "exempt" in artefacts[0].lower() or "No " in artefacts[0]

    def test_all_levels_include_psac(self):
        for dal in ("A", "B", "C", "D"):
            artefacts = required_artefacts_do178c(dal)
            combined = " ".join(artefacts)
            assert "PSAC" in combined, f"DAL {dal} should include PSAC"

    def test_all_levels_include_sas(self):
        for dal in ("A", "B", "C", "D"):
            artefacts = required_artefacts_do178c(dal)
            combined = " ".join(artefacts)
            assert "SAS" in combined, f"DAL {dal} should include SAS"

    def test_all_levels_include_hlr(self):
        for dal in ("A", "B", "C", "D"):
            artefacts = required_artefacts_do178c(dal)
            combined = " ".join(artefacts)
            assert "HLR" in combined or "High-Level Requirements" in combined

    def test_invalid_dal_raises(self):
        with pytest.raises(ValueError, match="Invalid DAL"):
            required_artefacts_do178c("F")

    def test_returns_list_of_strings(self):
        artefacts = required_artefacts_do178c("B")
        assert isinstance(artefacts, list)
        assert all(isinstance(a, str) for a in artefacts)

    def test_case_insensitive(self):
        assert required_artefacts_do178c("a") == required_artefacts_do178c("A")
        assert required_artefacts_do178c("b") == required_artefacts_do178c("B")

    def test_dal_a_superset_of_dal_b_structure(self):
        """DAL A list should have more items than DAL B (MC/DC adds one item)."""
        a_count = len(required_artefacts_do178c("A"))
        b_count = len(required_artefacts_do178c("B"))
        assert a_count > b_count, (
            f"DAL A ({a_count}) should have more artefacts than DAL B ({b_count})"
        )


# ---------------------------------------------------------------------------
# required_artefacts_do254
# ---------------------------------------------------------------------------

class TestRequiredArtefactsDO254:
    def test_dal_a_minimum_count(self):
        artefacts = required_artefacts_do254("A")
        assert len(artefacts) >= 15, (
            f"DAL A should require ≥ 15 artefacts, got {len(artefacts)}"
        )

    def test_dal_b_minimum_count(self):
        artefacts = required_artefacts_do254("B")
        assert len(artefacts) >= 15, (
            f"DAL B should require ≥ 15 artefacts, got {len(artefacts)}"
        )

    def test_dal_a_has_elemental_analysis(self):
        artefacts = required_artefacts_do254("A")
        combined = " ".join(artefacts).lower()
        assert "elemental" in combined, (
            "DAL A must require elemental analysis"
        )

    def test_dal_b_has_elemental_analysis(self):
        artefacts = required_artefacts_do254("B")
        combined = " ".join(artefacts).lower()
        assert "elemental" in combined, (
            "DAL B must require elemental analysis"
        )

    def test_dal_c_no_elemental_analysis(self):
        artefacts = required_artefacts_do254("C")
        combined = " ".join(artefacts).lower()
        assert "elemental" not in combined, (
            "DAL C should NOT require elemental analysis"
        )

    def test_all_levels_include_phac(self):
        for dal in ("A", "B", "C", "D"):
            artefacts = required_artefacts_do254(dal)
            combined = " ".join(artefacts)
            assert "PHAC" in combined, f"DAL {dal} should include PHAC"

    def test_all_levels_include_hdp(self):
        for dal in ("A", "B", "C", "D"):
            artefacts = required_artefacts_do254(dal)
            combined = " ".join(artefacts)
            assert "HDP" in combined, f"DAL {dal} should include HDP"

    def test_all_levels_include_hvvp(self):
        for dal in ("A", "B", "C", "D"):
            artefacts = required_artefacts_do254(dal)
            combined = " ".join(artefacts)
            assert "HVVP" in combined, f"DAL {dal} should include HVVP"

    def test_all_levels_include_hpap(self):
        for dal in ("A", "B", "C", "D"):
            artefacts = required_artefacts_do254(dal)
            combined = " ".join(artefacts)
            assert "HPAP" in combined, f"DAL {dal} should include HPAP"

    def test_all_levels_include_has(self):
        for dal in ("A", "B", "C", "D"):
            artefacts = required_artefacts_do254(dal)
            combined = " ".join(artefacts)
            assert "HAS" in combined, f"DAL {dal} should include HAS"

    def test_all_levels_include_hdl_source(self):
        for dal in ("A", "B", "C", "D"):
            artefacts = required_artefacts_do254(dal)
            combined = " ".join(artefacts)
            assert "HDL" in combined or "VHDL" in combined.upper() or "Design Data" in combined

    def test_dal_e_returns_exempt(self):
        artefacts = required_artefacts_do254("E")
        assert len(artefacts) == 1
        assert "E" in artefacts[0] or "No " in artefacts[0]

    def test_invalid_dal_raises(self):
        with pytest.raises(ValueError, match="Invalid DAL"):
            required_artefacts_do254("G")

    def test_returns_list_of_strings(self):
        artefacts = required_artefacts_do254("B")
        assert isinstance(artefacts, list)
        assert all(isinstance(a, str) for a in artefacts)

    def test_case_insensitive(self):
        assert required_artefacts_do254("a") == required_artefacts_do254("A")

    def test_dal_a_superset_of_dal_c(self):
        """DAL A has elemental analysis items; DAL C does not."""
        a_count = len(required_artefacts_do254("A"))
        c_count = len(required_artefacts_do254("C"))
        assert a_count > c_count
