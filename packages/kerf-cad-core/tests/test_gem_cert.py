"""
Tests for kerf_cad_core.jewelry.gem_cert.

All tests are pure-Python — no database, no network, no OCC.

Coverage (>= 25 hermetic tests):
  - GIA cert# format: 10-digit numeric accepted
  - GIA cert# format: <10-digit fails
  - GIA cert# format: >10-digit fails
  - GIA cert# format: letters fail
  - IGI cert# format: 9-digit and 10-digit accepted
  - AGS cert# format: digits-only accepted, AGS-prefix accepted
  - AGS cut grade 0-10 range accepted
  - AGS cut grade 11 rejected
  - AGS cut grade negative rejected
  - Valid color grades D–Z accepted
  - Invalid color grade rejected
  - Fancy color descriptor accepted
  - Valid clarity grades accepted (FL, VVS1, SI2, I3)
  - Invalid clarity grade rejected
  - Lab-grown origin with GIA accepted
  - Lab-grown origin with EGL rejected (consistency check)
  - Origin 'treated' accepted
  - Unknown origin rejected
  - Invalid polish grade rejected
  - Invalid symmetry grade rejected
  - Invalid fluorescence grade rejected
  - weight_carat <= 0 rejected
  - dimensions_mm invalid entry rejected
  - Valid cert passes with no issues
  - attach_to_gemstone annotates the dict
  - traceability_chain multi-stone lists each stone's cert
  - traceability_chain counts certified vs uncertified
  - traceability_chain counts lab-grown / natural
  - report_summary produces expected fields
  - validate_cert returns empty list for fully-valid cert
  - LLM tool: cert_validate success path
  - LLM tool: cert_validate bad lab
  - LLM tool: cert_attach success path
  - LLM tool: cert_traceability success path
  - LLM tool: cert_report success path
  - PDF URL format check (valid URL accepted)
  - PDF URL bad format rejected
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from kerf_cad_core.jewelry.gem_cert import (
    CertificateRef,
    validate_cert,
    attach_to_gemstone,
    traceability_chain,
    report_summary,
    run_jewelry_gem_cert_validate,
    run_jewelry_gem_cert_attach,
    run_jewelry_gem_cert_traceability,
    run_jewelry_gem_cert_report,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def make_ctx():
    from kerf_core.utils.context import ProjectCtx

    class FakePool:
        def fetchone(self, *a, **kw):
            return None
        def execute(self, *a, **kw):
            pass

    return ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _ok(raw: str) -> dict:
    d = json.loads(raw)
    # ok_payload returns the value directly; err_payload returns {"error":..,"code":..}
    assert "error" not in d, f"expected success payload, got error: {d}"
    return d


def _err(raw: str) -> dict:
    d = json.loads(raw)
    assert "error" in d, f"expected error payload, got: {d}"
    return d


def make_valid_gia_cert(**overrides) -> CertificateRef:
    defaults = dict(
        lab="GIA",
        cert_number="1234567890",
        date_issued="2023-06-01",
        weight_carat=1.02,
        cut="Excellent",
        color_grade="E",
        clarity_grade="VS1",
        dimensions_mm={"length": 6.45, "width": 6.42, "depth": 3.98},
        polish="Excellent",
        symmetry="Very Good",
        fluorescence="None",
        origin="natural",
        comments="None detected",
        plot_diagram_url="https://www.gia.edu/plot/1234567890.pdf",
        cert_pdf_url="https://www.gia.edu/report/1234567890.pdf",
    )
    defaults.update(overrides)
    return CertificateRef(**defaults)


# ---------------------------------------------------------------------------
# Cert-number format tests
# ---------------------------------------------------------------------------

def test_gia_cert_number_10_digit_valid():
    ref = make_valid_gia_cert(cert_number="1234567890")
    assert validate_cert(ref) == []


def test_gia_cert_number_9_digit_rejected():
    ref = make_valid_gia_cert(cert_number="123456789")
    issues = validate_cert(ref)
    assert any("GIA" in i for i in issues)


def test_gia_cert_number_11_digit_rejected():
    ref = make_valid_gia_cert(cert_number="12345678901")
    issues = validate_cert(ref)
    assert any("GIA" in i for i in issues)


def test_gia_cert_number_with_letters_rejected():
    ref = make_valid_gia_cert(cert_number="123456789X")
    issues = validate_cert(ref)
    assert any("GIA" in i for i in issues)


def test_igi_cert_number_9_digit_accepted():
    ref = CertificateRef(lab="IGI", cert_number="123456789")
    issues = validate_cert(ref)
    cert_num_issues = [i for i in issues if "IGI" in i or "cert_number" in i]
    assert not cert_num_issues


def test_igi_cert_number_10_digit_accepted():
    ref = CertificateRef(lab="IGI", cert_number="1234567890")
    issues = validate_cert(ref)
    cert_num_issues = [i for i in issues if "IGI" in i or "cert_number" in i]
    assert not cert_num_issues


def test_ags_cert_number_digits_only_accepted():
    ref = CertificateRef(lab="AGS", cert_number="1234567", cut=0, origin="natural")
    issues = validate_cert(ref)
    cert_num_issues = [i for i in issues if "cert_number" in i]
    assert not cert_num_issues


def test_ags_cert_number_with_prefix_accepted():
    ref = CertificateRef(lab="AGS", cert_number="AGS 1234567", cut=0, origin="natural")
    issues = validate_cert(ref)
    cert_num_issues = [i for i in issues if "cert_number" in i]
    assert not cert_num_issues


# ---------------------------------------------------------------------------
# AGS numeric cut grade
# ---------------------------------------------------------------------------

def test_ags_cut_grade_zero_ideal():
    ref = CertificateRef(lab="AGS", cert_number="1234567", cut=0, origin="natural")
    issues = validate_cert(ref)
    cut_issues = [i for i in issues if "cut" in i.lower()]
    assert not cut_issues


def test_ags_cut_grade_ten_accepted():
    ref = CertificateRef(lab="AGS", cert_number="1234567", cut=10, origin="natural")
    issues = validate_cert(ref)
    cut_issues = [i for i in issues if "cut" in i.lower()]
    assert not cut_issues


def test_ags_cut_grade_eleven_rejected():
    ref = CertificateRef(lab="AGS", cert_number="1234567", cut=11, origin="natural")
    issues = validate_cert(ref)
    assert any("cut" in i.lower() for i in issues)


def test_ags_cut_grade_negative_rejected():
    ref = CertificateRef(lab="AGS", cert_number="1234567", cut=-1, origin="natural")
    issues = validate_cert(ref)
    assert any("cut" in i.lower() for i in issues)


# ---------------------------------------------------------------------------
# Color grade
# ---------------------------------------------------------------------------

def test_valid_color_d_accepted():
    ref = make_valid_gia_cert(color_grade="D")
    assert validate_cert(ref) == []


def test_valid_color_z_accepted():
    ref = make_valid_gia_cert(color_grade="Z")
    assert validate_cert(ref) == []


def test_invalid_color_grade_rejected():
    ref = make_valid_gia_cert(color_grade="AA")
    issues = validate_cert(ref)
    assert any("color_grade" in i.lower() for i in issues)


def test_fancy_color_descriptor_accepted():
    ref = make_valid_gia_cert(color_grade="Fancy Vivid Yellow")
    assert validate_cert(ref) == []


# ---------------------------------------------------------------------------
# Clarity grade
# ---------------------------------------------------------------------------

def test_clarity_fl_accepted():
    ref = make_valid_gia_cert(clarity_grade="FL")
    assert validate_cert(ref) == []


def test_clarity_i3_accepted():
    ref = make_valid_gia_cert(clarity_grade="I3")
    assert validate_cert(ref) == []


def test_clarity_vvs1_accepted():
    ref = make_valid_gia_cert(clarity_grade="VVS1")
    assert validate_cert(ref) == []


def test_clarity_invalid_rejected():
    ref = make_valid_gia_cert(clarity_grade="VVVS1")
    issues = validate_cert(ref)
    assert any("clarity_grade" in i for i in issues)


# ---------------------------------------------------------------------------
# Origin consistency
# ---------------------------------------------------------------------------

def test_lab_grown_with_gia_accepted():
    ref = make_valid_gia_cert(origin="lab_grown")
    issues = validate_cert(ref)
    # Should not have a lab-consistency issue for GIA + lab_grown
    consistency_issues = [i for i in issues if "lab-grown" in i.lower() and "not known" in i.lower()]
    assert not consistency_issues


def test_lab_grown_with_igi_accepted():
    ref = CertificateRef(lab="IGI", cert_number="123456789", origin="lab_grown")
    issues = validate_cert(ref)
    consistency_issues = [i for i in issues if "not known" in i.lower()]
    assert not consistency_issues


def test_lab_grown_with_egl_rejected():
    ref = CertificateRef(lab="EGL", cert_number="US12345678", origin="lab_grown")
    issues = validate_cert(ref)
    assert any("not known" in i.lower() for i in issues)


def test_origin_treated_accepted():
    ref = make_valid_gia_cert(origin="treated")
    assert validate_cert(ref) == []


def test_origin_unknown_rejected():
    ref = make_valid_gia_cert(origin="mined_jupiter")
    issues = validate_cert(ref)
    assert any("origin" in i for i in issues)


# ---------------------------------------------------------------------------
# Polish / symmetry / fluorescence
# ---------------------------------------------------------------------------

def test_invalid_polish_rejected():
    ref = make_valid_gia_cert(polish="Outstanding")
    issues = validate_cert(ref)
    assert any("polish" in i for i in issues)


def test_invalid_symmetry_rejected():
    ref = make_valid_gia_cert(symmetry="Perfect")
    issues = validate_cert(ref)
    assert any("symmetry" in i for i in issues)


def test_invalid_fluorescence_rejected():
    ref = make_valid_gia_cert(fluorescence="Extreme")
    issues = validate_cert(ref)
    assert any("fluorescence" in i for i in issues)


# ---------------------------------------------------------------------------
# weight_carat
# ---------------------------------------------------------------------------

def test_weight_zero_rejected():
    ref = make_valid_gia_cert(weight_carat=0.0)
    issues = validate_cert(ref)
    assert any("weight_carat" in i for i in issues)


def test_weight_negative_rejected():
    ref = make_valid_gia_cert(weight_carat=-0.5)
    issues = validate_cert(ref)
    assert any("weight_carat" in i for i in issues)


# ---------------------------------------------------------------------------
# dimensions_mm
# ---------------------------------------------------------------------------

def test_dimensions_invalid_depth_rejected():
    ref = make_valid_gia_cert(dimensions_mm={"length": 6.45, "width": 6.42, "depth": -1.0})
    issues = validate_cert(ref)
    assert any("depth" in i for i in issues)


# ---------------------------------------------------------------------------
# URL format
# ---------------------------------------------------------------------------

def test_cert_pdf_url_valid():
    ref = make_valid_gia_cert(cert_pdf_url="https://example.com/cert.pdf")
    assert validate_cert(ref) == []


def test_cert_pdf_url_invalid():
    ref = make_valid_gia_cert(cert_pdf_url="not a url!!!")
    issues = validate_cert(ref)
    assert any("cert_pdf_url" in i for i in issues)


def test_plot_diagram_url_valid():
    ref = make_valid_gia_cert(plot_diagram_url="https://gia.edu/plot/1234567890.png")
    assert validate_cert(ref) == []


def test_plot_diagram_url_invalid():
    ref = make_valid_gia_cert(plot_diagram_url="bad url here")
    issues = validate_cert(ref)
    assert any("plot_diagram_url" in i for i in issues)


# ---------------------------------------------------------------------------
# Fully valid cert passes with no issues
# ---------------------------------------------------------------------------

def test_fully_valid_cert_no_issues():
    ref = make_valid_gia_cert()
    assert validate_cert(ref) == []


# ---------------------------------------------------------------------------
# attach_to_gemstone
# ---------------------------------------------------------------------------

def test_attach_to_gemstone_adds_cert_key():
    gem = {"cut": "round_brilliant", "diameter_mm": 6.5, "carat": 1.0}
    ref = make_valid_gia_cert()
    result = attach_to_gemstone(gem, ref)
    assert "cert" in result
    assert result["cert"]["lab"] == "GIA"
    assert result["cert"]["cert_number"] == "1234567890"


def test_attach_to_gemstone_preserves_existing_keys():
    gem = {"cut": "princess", "diameter_mm": 5.5, "material": "diamond"}
    ref = make_valid_gia_cert()
    result = attach_to_gemstone(gem, ref)
    assert result["cut"] == "princess"
    assert result["material"] == "diamond"


def test_attach_to_gemstone_non_dict_returns_unchanged():
    result = attach_to_gemstone("not-a-dict", make_valid_gia_cert())
    assert result == "not-a-dict"


# ---------------------------------------------------------------------------
# traceability_chain
# ---------------------------------------------------------------------------

def test_traceability_multi_stone_lists_each_cert():
    ref1 = make_valid_gia_cert(cert_number="1111111111", origin="natural")
    ref2 = make_valid_gia_cert(cert_number="2222222222", origin="lab_grown")
    stone1 = attach_to_gemstone({"id": "s1", "cut": "round_brilliant"}, ref1)
    stone2 = attach_to_gemstone({"id": "s2", "cut": "princess"}, ref2)
    piece = {"id": "ring-001", "stones": [stone1, stone2]}

    manifest = traceability_chain(piece)
    assert manifest["stone_count"] == 2
    assert len(manifest["stones"]) == 2
    assert manifest["stones"][0]["cert_number"] == "1111111111"
    assert manifest["stones"][1]["cert_number"] == "2222222222"


def test_traceability_certified_vs_uncertified_counts():
    ref = make_valid_gia_cert()
    stone_with_cert = attach_to_gemstone({"cut": "oval"}, ref)
    stone_no_cert = {"cut": "pear"}
    piece = {"stones": [stone_with_cert, stone_no_cert]}

    manifest = traceability_chain(piece)
    assert manifest["certified_count"] == 1
    assert manifest["uncertified_count"] == 1


def test_traceability_counts_lab_grown_and_natural():
    ref_natural = make_valid_gia_cert(cert_number="1111111111", origin="natural")
    ref_lab = make_valid_gia_cert(cert_number="2222222222", origin="lab_grown")
    ref_treated = make_valid_gia_cert(cert_number="3333333333", origin="treated")
    stone1 = attach_to_gemstone({"cut": "round_brilliant"}, ref_natural)
    stone2 = attach_to_gemstone({"cut": "princess"}, ref_lab)
    stone3 = attach_to_gemstone({"cut": "emerald"}, ref_treated)
    piece = {"stones": [stone1, stone2, stone3]}

    manifest = traceability_chain(piece)
    assert manifest["natural_count"] == 1
    assert manifest["lab_grown_count"] == 1
    assert manifest["treated_count"] == 1


def test_traceability_single_stone_via_top_level_cert():
    ref = make_valid_gia_cert()
    piece = attach_to_gemstone({"cut": "round_brilliant"}, ref)

    manifest = traceability_chain(piece)
    assert manifest["stone_count"] == 1
    assert manifest["certified_count"] == 1
    assert manifest["stones"][0]["cert_number"] == "1234567890"


# ---------------------------------------------------------------------------
# report_summary
# ---------------------------------------------------------------------------

def test_report_summary_contains_lab_and_number():
    ref = make_valid_gia_cert()
    summary = report_summary(ref)
    assert "GIA" in summary
    assert "1234567890" in summary


def test_report_summary_contains_weight():
    ref = make_valid_gia_cert(weight_carat=1.02)
    summary = report_summary(ref)
    assert "1.02" in summary


def test_report_summary_contains_color_and_clarity():
    ref = make_valid_gia_cert(color_grade="E", clarity_grade="VS1")
    summary = report_summary(ref)
    assert "E" in summary
    assert "VS1" in summary


def test_report_summary_contains_origin_label():
    ref = make_valid_gia_cert(origin="lab_grown")
    summary = report_summary(ref)
    assert "Lab-Grown" in summary


def test_report_summary_minimal_fields():
    ref = CertificateRef(lab="HRD", cert_number="12345678")
    summary = report_summary(ref)
    assert "HRD" in summary
    assert "12345678" in summary


# ---------------------------------------------------------------------------
# LLM tools
# ---------------------------------------------------------------------------

def test_llm_cert_validate_success():
    ctx = make_ctx()
    data = _ok(_run(run_jewelry_gem_cert_validate(ctx, json.dumps({
        "lab": "GIA",
        "cert_number": "1234567890",
        "color_grade": "E",
        "clarity_grade": "VS1",
        "cut": "Excellent",
        "origin": "natural",
    }).encode())))
    assert data["valid"] is True
    assert data["issues"] == []


def test_llm_cert_validate_bad_cert_number():
    ctx = make_ctx()
    data = _ok(_run(run_jewelry_gem_cert_validate(ctx, json.dumps({
        "lab": "GIA",
        "cert_number": "ABC123",
    }).encode())))
    assert data["valid"] is False
    assert len(data["issues"]) >= 1


def test_llm_cert_validate_missing_lab():
    ctx = make_ctx()
    resp = _run(run_jewelry_gem_cert_validate(ctx, json.dumps({
        "cert_number": "1234567890",
    }).encode()))
    d = json.loads(resp)
    assert "error" in d


def test_llm_cert_attach_success():
    ctx = make_ctx()
    gemstone = {"cut": "round_brilliant", "diameter_mm": 6.5}
    data = _ok(_run(run_jewelry_gem_cert_attach(ctx, json.dumps({
        "gemstone": gemstone,
        "lab": "GIA",
        "cert_number": "1234567890",
        "color_grade": "F",
        "clarity_grade": "VS2",
        "origin": "natural",
    }).encode())))
    assert "cert" in data["gemstone"]
    assert data["gemstone"]["cert"]["cert_number"] == "1234567890"
    assert data["cert_valid"] is True


def test_llm_cert_traceability_success():
    ctx = make_ctx()
    stones = [
        {"id": "s1", "cert": {"lab": "GIA", "cert_number": "1111111111", "origin": "natural"}},
        {"id": "s2", "cert": {"lab": "IGI", "cert_number": "123456789",  "origin": "lab_grown"}},
        {"id": "s3"},
    ]
    data = _ok(_run(run_jewelry_gem_cert_traceability(ctx, json.dumps({
        "piece": {"id": "ring-1", "stones": stones},
    }).encode())))
    assert data["stone_count"] == 3
    assert data["certified_count"] == 2
    assert data["uncertified_count"] == 1
    assert data["natural_count"] == 1
    assert data["lab_grown_count"] == 1


def test_llm_cert_report_success():
    ctx = make_ctx()
    data = _ok(_run(run_jewelry_gem_cert_report(ctx, json.dumps({
        "lab": "GIA",
        "cert_number": "1234567890",
        "weight_carat": 1.05,
        "color_grade": "D",
        "clarity_grade": "FL",
        "cut": "Excellent",
        "origin": "natural",
    }).encode())))
    assert "GIA" in data["summary"]
    assert "1234567890" in data["summary"]
    assert "1.05" in data["summary"]
    assert "FL" in data["summary"]
