"""Tests for DO-178C certification artefact templates.

Verifies that:
- All supported document types are generated without error
- Required sections per RTCA DO-178C structure are present
- project_meta substitution fills placeholder fields
- Unknown doc_type raises ValueError
"""
import pytest

from kerf_aero.cert.do178c.templates import (
    generate_template,
    SUPPORTED_DOC_TYPES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROJECT_META = {
    "project_name": "AutopilotFW",
    "dal": "B",
    "aircraft_type": "Fixed-wing UAV",
    "applicant": "Acme Avionics Inc.",
    "version": "1.0",
    "date": "2026-05-19",
    "author": "J. Smith",
    "dqa": "DER-12345",
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
        assert "AutopilotFW" in result

    @pytest.mark.parametrize("doc_type", SUPPORTED_DOC_TYPES)
    def test_contains_dal(self, doc_type):
        result = generate_template(doc_type, PROJECT_META)
        # DAL value should appear (substituted from meta)
        assert "DAL" in result.upper() or "dal" in result.lower()
        assert "B" in result  # the actual DAL letter

    @pytest.mark.parametrize("doc_type", SUPPORTED_DOC_TYPES)
    def test_fill_in_without_meta(self, doc_type):
        """Without project_meta the document must still render with [FILL IN]."""
        result = generate_template(doc_type)
        assert "[FILL IN]" in result

    @pytest.mark.parametrize("doc_type", SUPPORTED_DOC_TYPES)
    def test_meta_reduces_fill_in_count(self, doc_type):
        """Providing meta should reduce (not eliminate) the [FILL IN] count."""
        no_meta = generate_template(doc_type)
        with_meta = generate_template(doc_type, PROJECT_META)
        assert with_meta.count("[FILL IN]") < no_meta.count("[FILL IN]")

    @pytest.mark.parametrize("doc_type", SUPPORTED_DOC_TYPES)
    def test_case_insensitive_lookup(self, doc_type):
        lower = generate_template(doc_type.lower(), PROJECT_META)
        upper = generate_template(doc_type.upper(), PROJECT_META)
        assert lower == upper

    def test_unknown_doc_type_raises(self):
        with pytest.raises(ValueError, match="Unknown DO-178C doc_type"):
            generate_template("UNKNOWN_DOC", PROJECT_META)


# ---------------------------------------------------------------------------
# PSAC — Plan for Software Aspects of Certification
# ---------------------------------------------------------------------------

class TestPSAC:
    @pytest.fixture
    def doc(self):
        return generate_template("PSAC", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Plan for Software Aspects of Certification" in doc

    def test_system_overview_section(self, doc):
        assert _has_heading(doc, "System Overview")

    def test_certification_basis_section(self, doc):
        assert _has_heading(doc, "Certification Basis")

    def test_software_life_cycle_section(self, doc):
        assert _has_heading(doc, "Software Life-Cycle") or "Life-Cycle" in doc

    def test_stage_of_involvement_section(self, doc):
        assert "Stage of Involvement" in doc

    def test_software_life_cycle_data_section(self, doc):
        assert "Software Life-Cycle Data" in doc or "Life-Cycle Data" in doc

    def test_schedule_section(self, doc):
        assert _has_heading(doc, "Schedule")

    def test_tool_qualification_mentioned(self, doc):
        assert "Tool Qualification" in doc or "tool" in doc.lower()

    def test_html_comment_disclaimer(self, doc):
        assert "DO-178C" in doc


# ---------------------------------------------------------------------------
# SDP — Software Development Plan
# ---------------------------------------------------------------------------

class TestSDP:
    @pytest.fixture
    def doc(self):
        return generate_template("SDP", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Software Development Plan" in doc

    def test_introduction_section(self, doc):
        assert _has_heading(doc, "Introduction")

    def test_development_environment_section(self, doc):
        assert "Development Environment" in doc

    def test_requirements_process_section(self, doc):
        assert "Requirements" in doc

    def test_design_process_section(self, doc):
        assert "Design" in doc

    def test_coding_process_section(self, doc):
        assert "Coding" in doc or "Code" in doc

    def test_integration_section(self, doc):
        assert "Integration" in doc

    def test_traceability_section(self, doc):
        assert "Traceability" in doc


# ---------------------------------------------------------------------------
# SVP — Software Verification Plan
# ---------------------------------------------------------------------------

class TestSVP:
    @pytest.fixture
    def doc(self):
        return generate_template("SVP", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Software Verification Plan" in doc

    def test_verification_environment_section(self, doc):
        assert "Verification Environment" in doc

    def test_hlr_verification_section(self, doc):
        assert "High-Level Requirement" in doc or "HLR" in doc

    def test_llr_verification_section(self, doc):
        assert "Low-Level Requirement" in doc or "LLR" in doc

    def test_source_code_verification(self, doc):
        assert "Source Code" in doc

    def test_structural_coverage_section(self, doc):
        assert "Structural Coverage" in doc

    def test_dal_b_coverage_table(self, doc):
        # DAL B requires statement + decision but NOT MC/DC
        assert "Statement" in doc or "Decision" in doc

    def test_independence_section(self, doc):
        assert "Independence" in doc

    def test_regression_section(self, doc):
        assert "Regression" in doc


# ---------------------------------------------------------------------------
# SCMP — Software Configuration Management Plan
# ---------------------------------------------------------------------------

class TestSCMP:
    @pytest.fixture
    def doc(self):
        return generate_template("SCMP", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Software Configuration Management Plan" in doc

    def test_configuration_identification_section(self, doc):
        assert "Configuration Identification" in doc

    def test_baselines_section(self, doc):
        assert "Baseline" in doc

    def test_change_control_section(self, doc):
        assert "Change Control" in doc

    def test_problem_reporting_section(self, doc):
        assert "Problem Report" in doc

    def test_status_accounting_section(self, doc):
        assert "Status Accounting" in doc or "Configuration Status" in doc

    def test_archive_section(self, doc):
        assert "Archive" in doc

    def test_cm_audits_section(self, doc):
        assert "Audit" in doc


# ---------------------------------------------------------------------------
# SQAP — Software Quality Assurance Plan
# ---------------------------------------------------------------------------

class TestSQAP:
    @pytest.fixture
    def doc(self):
        return generate_template("SQAP", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Software Quality Assurance Plan" in doc

    def test_organisation_section(self, doc):
        assert "Organisation" in doc or "Organization" in doc

    def test_qa_activities_section(self, doc):
        assert "QA Activities" in doc or "Quality Assurance" in doc

    def test_plan_compliance_reviews(self, doc):
        assert "Compliance" in doc

    def test_non_conformance_section(self, doc):
        assert "Non-Conformance" in doc or "Nonconformance" in doc

    def test_qa_records_section(self, doc):
        assert "Records" in doc


# ---------------------------------------------------------------------------
# HLR — High-Level Requirements
# ---------------------------------------------------------------------------

class TestHLR:
    @pytest.fixture
    def doc(self):
        return generate_template("HLR", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "High-Level Requirements" in doc

    def test_system_context_section(self, doc):
        assert "System Context" in doc or "System Requirements" in doc

    def test_traceability_table(self, doc):
        assert "HLR ID" in doc or "Traceability" in doc

    def test_functional_requirements_section(self, doc):
        assert "Functional Requirements" in doc or "Functional" in doc

    def test_performance_requirements_section(self, doc):
        assert "Performance" in doc

    def test_safety_requirements_section(self, doc):
        assert "Safety" in doc

    def test_derived_requirements_mentioned(self, doc):
        assert "Derived" in doc


# ---------------------------------------------------------------------------
# LLR — Low-Level Requirements
# ---------------------------------------------------------------------------

class TestLLR:
    @pytest.fixture
    def doc(self):
        return generate_template("LLR", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Low-Level Requirements" in doc

    def test_hlr_traceability_section(self, doc):
        assert "HLR" in doc

    def test_inputs_section(self, doc):
        assert "Inputs" in doc

    def test_outputs_section(self, doc):
        assert "Outputs" in doc

    def test_processing_section(self, doc):
        assert "Processing" in doc

    def test_timing_section(self, doc):
        assert "Timing" in doc

    def test_project_name_in_llr_statement(self, doc):
        assert "AutopilotFW" in doc


# ---------------------------------------------------------------------------
# SDD — Software Design Description
# ---------------------------------------------------------------------------

class TestSDD:
    @pytest.fixture
    def doc(self):
        return generate_template("SDD", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Software Design Description" in doc

    def test_architecture_section(self, doc):
        assert "Architecture" in doc

    def test_module_descriptions_section(self, doc):
        assert "Module" in doc

    def test_data_design_section(self, doc):
        assert "Data Design" in doc

    def test_traceability_section(self, doc):
        assert "Traceability" in doc

    def test_error_handling_mentioned(self, doc):
        assert "Error Handling" in doc or "error" in doc.lower()


# ---------------------------------------------------------------------------
# SVCP — Software Verification Cases and Procedures
# ---------------------------------------------------------------------------

class TestSVCP:
    @pytest.fixture
    def doc(self):
        return generate_template("SVCP", PROJECT_META)

    def test_title_in_doc(self, doc):
        assert "Software Verification Cases and Procedures" in doc

    def test_test_environment_section(self, doc):
        assert "Test Environment" in doc or "Verification Environment" in doc

    def test_hlr_test_section(self, doc):
        assert "High-Level Requirement" in doc or "HLR" in doc

    def test_normal_range_tests(self, doc):
        assert "Normal" in doc or "normal" in doc

    def test_robustness_tests(self, doc):
        assert "Robustness" in doc or "robust" in doc.lower()

    def test_llr_tests_section(self, doc):
        assert "Low-Level Requirement" in doc or "LLR" in doc

    def test_structural_coverage_section(self, doc):
        assert "Structural Coverage" in doc

    def test_regression_suite_section(self, doc):
        assert "Regression" in doc


# ---------------------------------------------------------------------------
# Meta substitution edge-cases
# ---------------------------------------------------------------------------

class TestMetaSubstitution:
    def test_partial_meta_substitutes_provided_keys(self):
        meta = {"project_name": "PartialTest", "dal": "C"}
        doc = generate_template("PSAC", meta)
        assert "PartialTest" in doc
        assert "DAL" in doc.upper()
        # unprovided fields become [FILL IN]
        assert "[FILL IN]" in doc

    def test_empty_meta_all_fill_in(self):
        doc = generate_template("SDP", {})
        assert "[FILL IN]" in doc

    def test_none_meta_treated_as_empty(self):
        doc = generate_template("SVP", None)
        assert "[FILL IN]" in doc

    def test_applicant_substituted(self):
        meta = {"applicant": "Kerf Aerospace LLC"}
        doc = generate_template("PSAC", meta)
        assert "Kerf Aerospace LLC" in doc

    def test_date_substituted(self):
        meta = {"date": "2026-01-15"}
        doc = generate_template("SCMP", meta)
        assert "2026-01-15" in doc

    def test_all_nine_doc_types_in_supported(self):
        expected = {"PSAC", "SDP", "SVP", "SCMP", "SQAP", "HLR", "LLR", "SDD", "SVCP"}
        assert expected == set(SUPPORTED_DOC_TYPES)
