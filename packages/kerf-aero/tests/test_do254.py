"""Tests for DO-254 certification artefact templates.

Verifies that:
- All supported document types are generated without error
- Required sections per RTCA DO-254 structure are present
- project_meta substitution fills placeholder fields
- hardware_type substitution works correctly
- Unknown doc_type raises ValueError
"""
import pytest

from kerf_aero.cert.do254.templates import (
    generate_template,
    SUPPORTED_DOC_TYPES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROJECT_META = {
    "project_name": "FPGAFlightController",
    "hardware_type": "FPGA",
    "dal": "B",
    "aircraft_type": "Rotorcraft",
    "applicant": "Kerf Silicon GmbH",
    "version": "1.0",
    "date": "2026-05-19",
    "author": "A. Johnson",
    "der": "DER-67890",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_heading(md: str, heading: str) -> bool:
    """Return True if *heading* appears as a Markdown heading in *md*."""
    for line in md.splitlines():
        stripped = line.lstrip("#").strip()
        if heading.lower() in stripped.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Generic contract tests — run for every doc type
# ---------------------------------------------------------------------------

class TestAllDocTypesGenerate:
    @pytest.mark.parametrize("doc_type", SUPPORTED_DOC_TYPES)
    def test_returns_string(self, doc_type):
        result = generate_template(doc_type, PROJECT_META)
        assert isinstance(result, str)
        assert len(result) > 200

    @pytest.mark.parametrize("doc_type", SUPPORTED_DOC_TYPES)
    def test_contains_project_name(self, doc_type):
        result = generate_template(doc_type, PROJECT_META)
        assert "FPGAFlightController" in result

    @pytest.mark.parametrize("doc_type", SUPPORTED_DOC_TYPES)
    def test_contains_hardware_type(self, doc_type):
        result = generate_template(doc_type, PROJECT_META)
        assert "FPGA" in result

    @pytest.mark.parametrize("doc_type", SUPPORTED_DOC_TYPES)
    def test_contains_dal(self, doc_type):
        result = generate_template(doc_type, PROJECT_META)
        assert "B" in result

    @pytest.mark.parametrize("doc_type", SUPPORTED_DOC_TYPES)
    def test_fill_in_without_meta(self, doc_type):
        """Without project_meta the document must still render with [FILL IN]."""
        result = generate_template(doc_type)
        assert "[FILL IN]" in result

    @pytest.mark.parametrize("doc_type", SUPPORTED_DOC_TYPES)
    def test_meta_reduces_fill_in_count(self, doc_type):
        """Providing meta should reduce the [FILL IN] count."""
        no_meta = generate_template(doc_type)
        with_meta = generate_template(doc_type, PROJECT_META)
        assert with_meta.count("[FILL IN]") < no_meta.count("[FILL IN]")

    @pytest.mark.parametrize("doc_type", SUPPORTED_DOC_TYPES)
    def test_case_insensitive_lookup(self, doc_type):
        lower = generate_template(doc_type.lower(), PROJECT_META)
        upper = generate_template(doc_type.upper(), PROJECT_META)
        assert lower == upper

    def test_unknown_doc_type_raises(self):
        with pytest.raises(ValueError, match="Unknown DO-254 doc_type"):
            generate_template("UNKNOWN_DOC", PROJECT_META)


# ---------------------------------------------------------------------------
# PHAC — Plan for Hardware Aspects of Certification
# ---------------------------------------------------------------------------

class TestPHAC:
    @pytest.fixture
    def doc(self):
        return generate_template("PHAC", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Plan for Hardware Aspects of Certification" in doc

    def test_system_overview_section(self, doc):
        assert _has_heading(doc, "System Overview")

    def test_hardware_overview_section(self, doc):
        assert "Hardware Overview" in doc

    def test_hardware_function_section(self, doc):
        assert "Hardware Function" in doc

    def test_certification_basis_section(self, doc):
        assert _has_heading(doc, "Certification Basis")

    def test_dal_section(self, doc):
        assert "Design Assurance Level" in doc

    def test_hardware_life_cycle_section(self, doc):
        assert "Hardware Life-Cycle" in doc or "Life-Cycle" in doc

    def test_development_environment_section(self, doc):
        assert "Development Environment" in doc

    def test_requirements_section(self, doc):
        assert "Hardware Requirements" in doc or "Requirements" in doc

    def test_stage_of_involvement_section(self, doc):
        assert "Stage of Involvement" in doc

    def test_life_cycle_data_section(self, doc):
        assert "Life-Cycle Data" in doc or "Hardware Life-Cycle Data" in doc

    def test_tool_assessment_section(self, doc):
        assert "Tool Assessment" in doc or "Tool" in doc

    def test_hardware_type_in_doc(self, doc):
        assert "FPGA" in doc

    def test_do254_disclaimer(self, doc):
        assert "DO-254" in doc


# ---------------------------------------------------------------------------
# HDP — Hardware Development Plan
# ---------------------------------------------------------------------------

class TestHDP:
    @pytest.fixture
    def doc(self):
        return generate_template("HDP", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Hardware Development Plan" in doc

    def test_introduction_section(self, doc):
        assert _has_heading(doc, "Introduction")

    def test_development_environment_section(self, doc):
        assert "Development Environment" in doc

    def test_hdl_coding_standards_section(self, doc):
        assert "HDL" in doc or "Coding Standards" in doc

    def test_eda_toolchain_section(self, doc):
        assert "EDA" in doc or "Toolchain" in doc

    def test_target_device_section(self, doc):
        assert "Target Device" in doc or "Target" in doc

    def test_requirements_process_section(self, doc):
        assert "Requirements" in doc

    def test_derived_requirements_section(self, doc):
        assert "Derived" in doc

    def test_conceptual_design_section(self, doc):
        assert "Conceptual Design" in doc

    def test_detailed_design_section(self, doc):
        assert "Detailed Design" in doc

    def test_rtl_design_section(self, doc):
        assert "RTL" in doc

    def test_synthesis_section(self, doc):
        assert "Synthesis" in doc

    def test_integration_section(self, doc):
        assert "Integration" in doc

    def test_traceability_section(self, doc):
        assert "Traceability" in doc


# ---------------------------------------------------------------------------
# HVVP — Hardware Verification and Validation Plan
# ---------------------------------------------------------------------------

class TestHVVP:
    @pytest.fixture
    def doc(self):
        return generate_template("HVVP", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Hardware Verification and Validation Plan" in doc

    def test_verification_environment_section(self, doc):
        assert "Verification Environment" in doc

    def test_simulation_environment_section(self, doc):
        assert "Simulation" in doc

    def test_hardware_requirements_verification(self, doc):
        assert "Hardware Requirements" in doc or "Verification of Hardware" in doc

    def test_requirements_review_section(self, doc):
        assert "Review" in doc

    def test_functional_simulation_tests(self, doc):
        assert "Simulation" in doc or "Functional" in doc

    def test_requirements_coverage_section(self, doc):
        assert "Coverage" in doc

    def test_hardware_design_verification(self, doc):
        assert "Design" in doc

    def test_rtl_reviews_section(self, doc):
        assert "RTL" in doc

    def test_timing_analysis_section(self, doc):
        assert "Timing" in doc

    def test_elemental_analysis_section(self, doc):
        # DAL A/B requires elemental analysis
        assert "Elemental Analysis" in doc

    def test_validation_section(self, doc):
        assert _has_heading(doc, "Validation")

    def test_independence_section(self, doc):
        assert "Independence" in doc

    def test_formal_verification_mentioned(self, doc):
        assert "Formal" in doc or "formal" in doc


# ---------------------------------------------------------------------------
# HPAP — Hardware Process Assurance Plan
# ---------------------------------------------------------------------------

class TestHPAP:
    @pytest.fixture
    def doc(self):
        return generate_template("HPAP", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Hardware Process Assurance Plan" in doc

    def test_introduction_section(self, doc):
        assert _has_heading(doc, "Introduction")

    def test_hpa_organisation_section(self, doc):
        assert "Organisation" in doc or "Organization" in doc

    def test_independence_section(self, doc):
        assert "Independence" in doc

    def test_process_assurance_activities_section(self, doc):
        assert "Process Assurance" in doc

    def test_plan_compliance_reviews(self, doc):
        assert "Compliance" in doc

    def test_transition_criteria_section(self, doc):
        assert "Transition" in doc

    def test_conformity_review_section(self, doc):
        assert "Conformity" in doc or "Configuration Audit" in doc

    def test_fca_section(self, doc):
        assert "FCA" in doc or "Functional Configuration" in doc

    def test_pca_section(self, doc):
        assert "PCA" in doc or "Physical Configuration" in doc

    def test_non_conformance_section(self, doc):
        assert "Non-Conformance" in doc or "Nonconformance" in doc

    def test_hpa_records_section(self, doc):
        assert "Records" in doc


# ---------------------------------------------------------------------------
# Meta substitution edge-cases
# ---------------------------------------------------------------------------

class TestMetaSubstitution:
    def test_partial_meta_substitutes_provided_keys(self):
        meta = {"project_name": "ASICCore", "hardware_type": "ASIC", "dal": "A"}
        doc = generate_template("PHAC", meta)
        assert "ASICCore" in doc
        assert "ASIC" in doc
        assert "[FILL IN]" in doc  # remaining fields

    def test_empty_meta_produces_fill_in_hardware_type(self):
        doc = generate_template("HDP", {})
        assert "[FILL IN]" in doc

    def test_none_meta_treated_as_empty(self):
        doc = generate_template("HVVP", None)
        assert "[FILL IN]" in doc

    def test_applicant_substituted(self):
        meta = {"applicant": "Kerf Silicon GmbH"}
        doc = generate_template("PHAC", meta)
        assert "Kerf Silicon GmbH" in doc

    def test_der_substituted(self):
        meta = {"der": "DER-99999"}
        doc = generate_template("HPAP", meta)
        assert "DER-99999" in doc

    def test_hardware_type_pcb_substituted(self):
        meta = {"hardware_type": "PCB", "project_name": "PowerBoard"}
        doc = generate_template("HDP", meta)
        assert "PCB" in doc

    def test_all_four_doc_types_in_supported(self):
        expected = {"PHAC", "HDP", "HVVP", "HPAP"}
        assert expected == set(SUPPORTED_DOC_TYPES)
