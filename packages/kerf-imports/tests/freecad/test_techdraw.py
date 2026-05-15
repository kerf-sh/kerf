"""
test_techdraw.py — TechDraw → .drawing translator tests.

Exercises translate_drawpage() and the direction → projection mapping.
"""
from __future__ import annotations

import pytest

from kerf_imports.freecad.types import FCStdObject, FCStdDocument
from kerf_imports.freecad.techdraw import translate_drawpage, _direction_to_projection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(objects=None) -> FCStdDocument:
    return FCStdDocument(
        schema_version=4,
        program_version="0.21R3",
        objects=objects or [],
    )


def _make_page(
    name="Page",
    label="Page",
    template="A3_Landscape",
    scale=1.0,
    view_names=None,
) -> FCStdObject:
    from kerf_imports.freecad.types import LinkRef
    views_list = [LinkRef(n) for n in (view_names or [])]
    return FCStdObject(
        name=name,
        type="TechDraw::DrawPage",
        label=label,
        properties={
            "Template": template,
            "Scale": scale,
            "Views": views_list,
        },
    )


def _make_view(
    name="View",
    label="View",
    view_type="TechDraw::DrawViewPart",
    x=70.0,
    y=100.0,
    scale=1.0,
    direction=None,
    source_name=None,
) -> FCStdObject:
    from kerf_imports.freecad.types import LinkRef
    props: dict = {
        "X": x,
        "Y": y,
        "Scale": scale,
    }
    if direction is not None:
        props["Direction"] = direction
    if source_name is not None:
        props["Source"] = [LinkRef(source_name)]
    return FCStdObject(
        name=name,
        type=view_type,
        label=label,
        properties=props,
    )


# ---------------------------------------------------------------------------
# Direction → projection mapping
# ---------------------------------------------------------------------------

class TestDirectionToProjection:
    def test_front_z_positive(self):
        assert _direction_to_projection({"x": 0, "y": 0, "z": 1}) == "front"

    def test_back_z_negative(self):
        assert _direction_to_projection({"x": 0, "y": 0, "z": -1}) == "back"

    def test_top_y_negative(self):
        assert _direction_to_projection({"x": 0, "y": -1, "z": 0}) == "top"

    def test_bottom_y_positive(self):
        assert _direction_to_projection({"x": 0, "y": 1, "z": 0}) == "bottom"

    def test_right_x_positive(self):
        assert _direction_to_projection({"x": 1, "y": 0, "z": 0}) == "right"

    def test_left_x_negative(self):
        assert _direction_to_projection({"x": -1, "y": 0, "z": 0}) == "left"

    def test_none_defaults_to_front(self):
        assert _direction_to_projection(None) == "front"

    def test_zero_vector_defaults_to_front(self):
        assert _direction_to_projection({"x": 0, "y": 0, "z": 0}) == "front"

    def test_iso_direction(self):
        # (1,1,1) normalised is the isometric direction
        result = _direction_to_projection({"x": 1, "y": 1, "z": 1})
        assert result == "iso"

    def test_near_front_snaps(self):
        # Slightly off-axis but closest to front
        result = _direction_to_projection({"x": 0.01, "y": 0.01, "z": 0.99})
        assert result == "front"


# ---------------------------------------------------------------------------
# translate_drawpage — basic structure
# ---------------------------------------------------------------------------

class TestTranslateDrawpageBasic:
    def _simple_page_and_view(self):
        view = _make_view(
            name="View",
            direction={"x": 0, "y": 0, "z": 1},
            source_name="Body",
        )
        page = _make_page(view_names=["View"])
        doc = _make_doc([page, view])
        return page, doc

    def test_returns_dict_with_required_keys(self):
        page, doc = self._simple_page_and_view()
        result = translate_drawpage(page, doc)
        assert "sheets" in result
        assert "freecad_ref" in result
        assert "warnings" in result

    def test_single_sheet_in_sheets(self):
        page, doc = self._simple_page_and_view()
        result = translate_drawpage(page, doc)
        assert len(result["sheets"]) == 1

    def test_sheet_has_required_keys(self):
        page, doc = self._simple_page_and_view()
        sheet = translate_drawpage(page, doc)["sheets"][0]
        assert "id" in sheet
        assert "frame" in sheet
        assert "views" in sheet
        assert "dimensions" in sheet
        assert "annotations" in sheet

    def test_freecad_ref_populated(self):
        page, doc = self._simple_page_and_view()
        ref = translate_drawpage(page, doc)["freecad_ref"]
        assert ref["name"] == "Page"
        assert ref["type"] == "TechDraw::DrawPage"


# ---------------------------------------------------------------------------
# Frame parsing
# ---------------------------------------------------------------------------

class TestFrameParsing:
    def test_a3_landscape(self):
        page = _make_page(template="A3_Landscape")
        doc = _make_doc([page])
        frame = translate_drawpage(page, doc)["sheets"][0]["frame"]
        assert frame["size"] == "A3"
        assert frame["orientation"] == "landscape"

    def test_a4_portrait(self):
        page = _make_page(template="A4_Portrait")
        doc = _make_doc([page])
        frame = translate_drawpage(page, doc)["sheets"][0]["frame"]
        assert frame["size"] == "A4"
        assert frame["orientation"] == "portrait"

    def test_title_from_label(self):
        page = _make_page(label="Main Drawing")
        doc = _make_doc([page])
        frame = translate_drawpage(page, doc)["sheets"][0]["frame"]
        assert frame["title"] == "Main Drawing"

    def test_unknown_template_defaults(self):
        page = _make_page(template="")
        doc = _make_doc([page])
        frame = translate_drawpage(page, doc)["sheets"][0]["frame"]
        # Default to A3 landscape
        assert frame["size"] == "A3"

    def test_scale_label_1_to_1(self):
        page = _make_page(scale=1.0)
        doc = _make_doc([page])
        frame = translate_drawpage(page, doc)["sheets"][0]["frame"]
        assert frame["scale_label"] == "1:1"


# ---------------------------------------------------------------------------
# View extraction
# ---------------------------------------------------------------------------

class TestViewExtraction:
    def test_one_view_translated(self):
        view = _make_view(
            name="FrontView",
            direction={"x": 0, "y": 0, "z": 1},
        )
        page = _make_page(view_names=["FrontView"])
        doc = _make_doc([page, view])
        views = translate_drawpage(page, doc)["sheets"][0]["views"]
        assert len(views) == 1
        v = views[0]
        assert v["projection"] == "front"

    def test_two_views_translated(self):
        v_front = _make_view("V1", direction={"x": 0, "y": 0, "z": 1})
        v_top = _make_view("V2", direction={"x": 0, "y": -1, "z": 0})
        page = _make_page(view_names=["V1", "V2"])
        doc = _make_doc([page, v_front, v_top])
        views = translate_drawpage(page, doc)["sheets"][0]["views"]
        assert len(views) == 2
        projections = {v["projection"] for v in views}
        assert projections == {"front", "top"}

    def test_view_position_extracted(self):
        view = _make_view("V", x=40.0, y=80.0)
        page = _make_page(view_names=["V"])
        doc = _make_doc([page, view])
        v = translate_drawpage(page, doc)["sheets"][0]["views"][0]
        assert v["position"] == [40.0, 80.0]

    def test_view_scale_extracted(self):
        view = _make_view("V", scale=2.0)
        page = _make_page(view_names=["V"])
        doc = _make_doc([page, view])
        v = translate_drawpage(page, doc)["sheets"][0]["views"][0]
        assert v["scale"] == 2.0

    def test_view_source_feature_name(self):
        view = _make_view("V", source_name="Body001")
        page = _make_page(view_names=["V"])
        doc = _make_doc([page, view])
        v = translate_drawpage(page, doc)["sheets"][0]["views"][0]
        assert v["source_feature_name"] == "Body001"

    def test_view_source_file_id_none_initially(self):
        view = _make_view("V", source_name="Body")
        page = _make_page(view_names=["V"])
        doc = _make_doc([page, view])
        v = translate_drawpage(page, doc)["sheets"][0]["views"][0]
        assert v["source_file_id"] is None  # resolved post-import

    def test_view_id_derived_from_name(self):
        view = _make_view("FrontView")
        page = _make_page(view_names=["FrontView"])
        doc = _make_doc([page, view])
        v = translate_drawpage(page, doc)["sheets"][0]["views"][0]
        assert v["id"] == "v-FrontView"

    def test_section_view_flagged(self):
        view = _make_view("Section", view_type="TechDraw::DrawViewSection")
        page = _make_page(view_names=["Section"])
        doc = _make_doc([page, view])
        v = translate_drawpage(page, doc)["sheets"][0]["views"][0]
        assert v.get("is_section") is True

    def test_no_views_when_page_has_empty_list(self):
        page = _make_page(view_names=[])
        doc = _make_doc([page])
        views = translate_drawpage(page, doc)["sheets"][0]["views"]
        # No views in doc that are TechDraw types either
        assert views == []


# ---------------------------------------------------------------------------
# Integration with fixture
# ---------------------------------------------------------------------------

class TestTechDrawFixture:
    @pytest.fixture
    def fixture_path(self):
        import pathlib
        path = pathlib.Path(__file__).parent / "fixtures" / "techdraw_basic.FCStd"
        if not path.exists():
            pytest.skip("techdraw_basic.FCStd fixture not found")
        return path

    def test_fixture_has_drawpage(self, fixture_path):
        from kerf_imports.freecad.parser import parse_fcstd
        doc = parse_fcstd(fixture_path.read_bytes())
        pages = doc.objects_by_type("TechDraw::DrawPage")
        assert len(pages) == 1

    def test_fixture_translate_returns_sheets(self, fixture_path):
        from kerf_imports.freecad.parser import parse_fcstd
        doc = parse_fcstd(fixture_path.read_bytes())
        pages = doc.objects_by_type("TechDraw::DrawPage")
        result = translate_drawpage(pages[0], doc)
        assert len(result["sheets"]) == 1

    def test_fixture_has_two_views(self, fixture_path):
        from kerf_imports.freecad.parser import parse_fcstd
        doc = parse_fcstd(fixture_path.read_bytes())
        pages = doc.objects_by_type("TechDraw::DrawPage")
        result = translate_drawpage(pages[0], doc)
        views = result["sheets"][0]["views"]
        assert len(views) == 2

    def test_fixture_front_and_top_projections(self, fixture_path):
        from kerf_imports.freecad.parser import parse_fcstd
        doc = parse_fcstd(fixture_path.read_bytes())
        pages = doc.objects_by_type("TechDraw::DrawPage")
        views = translate_drawpage(pages[0], doc)["sheets"][0]["views"]
        projections = {v["projection"] for v in views}
        assert "front" in projections
        assert "top" in projections

    def test_fixture_frame_a3_landscape(self, fixture_path):
        from kerf_imports.freecad.parser import parse_fcstd
        doc = parse_fcstd(fixture_path.read_bytes())
        pages = doc.objects_by_type("TechDraw::DrawPage")
        frame = translate_drawpage(pages[0], doc)["sheets"][0]["frame"]
        assert frame["size"] == "A3"
        assert frame["orientation"] == "landscape"
