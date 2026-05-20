"""
test_ap242_reader.py — pytest suite for the AP242 PMI reader.

All tests are offline; they either use the inline STEP fixture string or the
small .stp fixture in tests/fixtures/ap242_pmi_sample.stp.
No kernel (OCC/OCCT) required.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from kerf_imports.ap242_reader import read_ap242_pmi, AP242ReadError

# ─── Inline minimal AP242 fixture ─────────────────────────────────────────────

_MINIMAL_AP242 = """\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('',''),'2;1');
FILE_NAME('test.stp','2024-06-01T12:00:00',('Author'),('Org'),'','kerf','');
FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF { 1 0 10303 442 1 1 4 }'));
ENDSEC;
DATA;
#1=PRODUCT('WidgetBody','Main body of widget',$,(#2));
#10=DRAUGHTING_CALLOUT('callout_1',(#11));
#11=PMI_REPRESENTATION_ITEM('flatness_pmi');
#12=ANNOTATION_OCCURRENCE('flatness note',#10,(#11));
#20=FLATNESS_TOLERANCE('flatness_tol',#21,$,#22);
#21=MEASURE_WITH_UNIT(LENGTH_MEASURE(0.02),#30);
#22=TOLERANCE_VALUE(0.02,0.0);
#30=LENGTH_UNIT(#31);
#31=SI_UNIT($,.MILLI.,.METRE.);
#40=DATUM_FEATURE('datum_face_A',$,#1);
#41=DATUM('A',$,#40);
#50=DIMENSIONAL_SIZE('shaft_diameter',#51,$);
#51=MEASURE_WITH_UNIT(LENGTH_MEASURE(12.5),#30);
#60=NEXT_ASSEMBLY_USAGE_OCCURRENCE('1','','',#1,#1,$);
ENDSEC;
END-ISO-10303-21;
"""

_FIXTURE_PATH = (
    pathlib.Path(__file__).parent / "fixtures" / "ap242_pmi_sample.stp"
)


# ─── Schema / product header ──────────────────────────────────────────────────

def test_schema_parsed():
    result = read_ap242_pmi(_MINIMAL_AP242)
    assert result["ok"] is True
    assert result["schema"] is not None
    assert "AP242" in result["schema"]


def test_product_parsed():
    result = read_ap242_pmi(_MINIMAL_AP242)
    assert result["product"] == "WidgetBody"


def test_non_ap242_schema_produces_warning():
    bad_schema = _MINIMAL_AP242.replace(
        "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF { 1 0 10303 442 1 1 4 }",
        "AP214_AUTOMOTIVE_DESIGN",
    )
    result = read_ap242_pmi(bad_schema)
    assert result["ok"] is True
    assert any("not AP242" in w for w in result["warnings"])


# ─── PMI annotations ─────────────────────────────────────────────────────────

def test_draughting_callout_extracted():
    result = read_ap242_pmi(_MINIMAL_AP242)
    kinds = [a["kind"] for a in result["annotations"]]
    assert "draughting_callout" in kinds


def test_pmi_representation_item_extracted():
    result = read_ap242_pmi(_MINIMAL_AP242)
    kinds = [a["kind"] for a in result["annotations"]]
    assert "pmi_representation_item" in kinds


def test_annotation_occurrence_extracted():
    result = read_ap242_pmi(_MINIMAL_AP242)
    kinds = [a["kind"] for a in result["annotations"]]
    assert "annotation_occurrence" in kinds


def test_annotations_have_id_and_refs():
    result = read_ap242_pmi(_MINIMAL_AP242)
    for ann in result["annotations"]:
        assert "id" in ann
        assert isinstance(ann["id"], int)
        assert isinstance(ann["refs"], list)


# ─── Datum reference frames ───────────────────────────────────────────────────

def test_datum_feature_extracted():
    result = read_ap242_pmi(_MINIMAL_AP242)
    kinds = [d["kind"] for d in result["datums"]]
    assert "datum_feature" in kinds


def test_datum_extracted():
    result = read_ap242_pmi(_MINIMAL_AP242)
    kinds = [d["kind"] for d in result["datums"]]
    assert "datum" in kinds


def test_datum_label_parsed():
    result = read_ap242_pmi(_MINIMAL_AP242)
    datums_with_label = [d for d in result["datums"] if d.get("label")]
    assert len(datums_with_label) >= 1
    labels = [d["label"] for d in datums_with_label]
    assert any(lbl in labels for lbl in ("A", "datum_face_A"))


def test_datum_feature_has_refs():
    result = read_ap242_pmi(_MINIMAL_AP242)
    df = next((d for d in result["datums"] if d["kind"] == "datum_feature"), None)
    assert df is not None
    assert isinstance(df["refs"], list)


# ─── GD&T tolerances ─────────────────────────────────────────────────────────

def test_flatness_tolerance_extracted():
    result = read_ap242_pmi(_MINIMAL_AP242)
    kinds = [t["kind"] for t in result["tolerances"]]
    assert "FLATNESS_TOLERANCE" in kinds


def test_tolerance_has_id_and_kind():
    result = read_ap242_pmi(_MINIMAL_AP242)
    for tol in result["tolerances"]:
        assert isinstance(tol["id"], int)
        assert isinstance(tol["kind"], str)


def test_tolerance_value_entity_extracted():
    result = read_ap242_pmi(_MINIMAL_AP242)
    kinds = [t["kind"] for t in result["tolerances"]]
    assert "TOLERANCE_VALUE" in kinds


# ─── Dimensional sizes ────────────────────────────────────────────────────────

def test_dimensional_size_extracted():
    result = read_ap242_pmi(_MINIMAL_AP242)
    assert len(result["dimensional_sizes"]) >= 1


def test_dimensional_size_has_name():
    result = read_ap242_pmi(_MINIMAL_AP242)
    for ds in result["dimensional_sizes"]:
        assert "name" in ds
        assert "id" in ds


# ─── drawing_annotations flat list ───────────────────────────────────────────

def test_drawing_annotations_non_empty():
    result = read_ap242_pmi(_MINIMAL_AP242)
    assert len(result["drawing_annotations"]) >= 1


def test_drawing_annotations_have_required_keys():
    result = read_ap242_pmi(_MINIMAL_AP242)
    for ann in result["drawing_annotations"]:
        assert "type" in ann
        assert "label" in ann
        assert "id" in ann
        assert "refs" in ann


def test_drawing_annotations_cover_all_entity_types():
    result = read_ap242_pmi(_MINIMAL_AP242)
    types = {a["type"] for a in result["drawing_annotations"]}
    # Should contain at least one PMI, one datum, one tolerance type
    assert len(types) >= 3


# ─── Full fixture file ────────────────────────────────────────────────────────

def test_fixture_file_parseable():
    text = _FIXTURE_PATH.read_text(encoding="utf-8")
    result = read_ap242_pmi(text)
    assert result["ok"] is True


def test_fixture_file_has_datums():
    text = _FIXTURE_PATH.read_text(encoding="utf-8")
    result = read_ap242_pmi(text)
    assert len(result["datums"]) >= 2


def test_fixture_file_has_tolerances():
    text = _FIXTURE_PATH.read_text(encoding="utf-8")
    result = read_ap242_pmi(text)
    tol_kinds = {t["kind"] for t in result["tolerances"]}
    assert "FLATNESS_TOLERANCE" in tol_kinds or "STRAIGHTNESS_TOLERANCE" in tol_kinds


def test_fixture_file_has_pmi_annotations():
    text = _FIXTURE_PATH.read_text(encoding="utf-8")
    result = read_ap242_pmi(text)
    assert len(result["annotations"]) >= 1


def test_fixture_file_drawing_annotations_non_empty():
    text = _FIXTURE_PATH.read_text(encoding="utf-8")
    result = read_ap242_pmi(text)
    assert len(result["drawing_annotations"]) >= 4


def test_fixture_file_product_name():
    text = _FIXTURE_PATH.read_text(encoding="utf-8")
    result = read_ap242_pmi(text)
    assert result["product"] == "BracketA"


# ─── Edge cases ───────────────────────────────────────────────────────────────

def test_empty_data_section():
    minimal = (
        "ISO-10303-21;\nHEADER;\n"
        "FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));\n"
        "ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
    )
    result = read_ap242_pmi(minimal)
    assert result["ok"] is True
    assert result["annotations"] == []
    assert result["datums"] == []
    assert result["tolerances"] == []


def test_no_schema_line():
    no_schema = "DATA;\n#1=PRODUCT('Part',$,$,$);\nENDSEC;"
    result = read_ap242_pmi(no_schema)
    assert result["ok"] is True
    assert result["schema"] is None


def test_multiple_datums_in_fixture():
    text = _FIXTURE_PATH.read_text(encoding="utf-8")
    result = read_ap242_pmi(text)
    # Fixture has datum_feature (#34), datum (#35), datum_target (#37)
    kinds = {d["kind"] for d in result["datums"]}
    assert "datum_feature" in kinds
    assert "datum" in kinds


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
