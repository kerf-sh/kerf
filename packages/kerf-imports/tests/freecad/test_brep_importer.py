"""
test_brep_importer.py — T2 BRep-lift importer tests.

Test plan:
  1. Round-trip: generate a box BRep via BRepPrimAPI_MakeBox + breptools_Write,
     wrap in a synthetic FCStdDocument, call build_feature_tree, assert
     1 feature / 1 import_brep node / asset bytes match.
  2. Multi-Body: 2 bodies → 2 features → 2 distinct asset_ids.
  3. Corrupt blob: raises BRepLiftError, not bare Exception.
"""
from __future__ import annotations

import hashlib
import io
import pytest

# Skip the whole module if neither OCC.Core.* nor OCP.* is installed.
def _check_pythonocc():
    try:
        import OCC.Core.BRepPrimAPI  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import OCP.BRepPrimAPI  # type: ignore[import]  # noqa: F401
        return True
    except ImportError:
        pass
    return False

if not _check_pythonocc():
    pytest.skip(
        "pythonocc-core (OCC.Core.* or OCP.*) not installed",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_occ():
    """Return (BRepTools, BRep_Builder, TopoDS_Shape, BRepPrimAPI_MakeBox).

    Tries OCC.Core.* first (canonical monorepo convention), then OCP.*
    (conda-forge build name on this machine).
    """
    try:
        from OCC.Core.BRepTools import BRepTools
        from OCC.Core.BRep import BRep_Builder
        from OCC.Core.TopoDS import TopoDS_Shape
        from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
        return BRepTools, BRep_Builder, TopoDS_Shape, BRepPrimAPI_MakeBox
    except ImportError:
        pass
    from OCP.BRepTools import BRepTools  # type: ignore[import]
    from OCP.BRep import BRep_Builder  # type: ignore[import]
    from OCP.TopoDS import TopoDS_Shape  # type: ignore[import]
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # type: ignore[import]
    return BRepTools, BRep_Builder, TopoDS_Shape, BRepPrimAPI_MakeBox


def _make_box_brep(dx: float = 10.0, dy: float = 20.0, dz: float = 30.0) -> bytes:
    """Return raw BRep bytes for an axis-aligned box of the given dimensions."""
    BRepTools, _, _, BRepPrimAPI_MakeBox = _import_occ()
    shape = BRepPrimAPI_MakeBox(dx, dy, dz).Shape()
    buf = io.BytesIO()
    BRepTools.Write_s(shape, buf)
    return buf.getvalue()


def _make_fcstd_doc_single(brep_bytes: bytes, body_name: str = "Body"):
    """
    Build a synthetic FCStdDocument with one PartDesign::Body whose Tip
    feature has the given BRep bytes as its Shape property.
    """
    from kerf_imports.freecad.types import FCStdDocument, FCStdObject

    tip_name = f"{body_name}_Pad"
    tip_obj = FCStdObject(
        name=tip_name,
        type="PartDesign::Pad",
        label=tip_name,
        properties={"Shape": brep_bytes},
    )
    body_obj = FCStdObject(
        name=body_name,
        type="PartDesign::Body",
        label=body_name,
        properties={"Tip": tip_name},
    )
    return FCStdDocument(
        schema_version=4,
        program_version="0.21R3",
        objects=[body_obj, tip_obj],
        properties={},
        brep_blobs={},
        raw_xml={},
    )


def _make_fcstd_doc_two_bodies(
    brep1: bytes, brep2: bytes
):
    """Build a synthetic FCStdDocument with two PartDesign::Body objects."""
    from kerf_imports.freecad.types import FCStdDocument, FCStdObject

    pad1_name, pad2_name = "Body_Pad", "Body001_Pad"
    body1_name, body2_name = "Body", "Body001"

    objects = [
        FCStdObject(name=body1_name, type="PartDesign::Body", label="Body",
                    properties={"Tip": pad1_name}),
        FCStdObject(name=pad1_name, type="PartDesign::Pad", label=pad1_name,
                    properties={"Shape": brep1}),
        FCStdObject(name=body2_name, type="PartDesign::Body", label="Body001",
                    properties={"Tip": pad2_name}),
        FCStdObject(name=pad2_name, type="PartDesign::Pad", label=pad2_name,
                    properties={"Shape": brep2}),
    ]
    return FCStdDocument(
        schema_version=4,
        program_version="0.21R3",
        objects=objects,
        properties={},
        brep_blobs={},
        raw_xml={},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLiftBrepBlob:
    """Unit tests for lift_brep_blob()."""

    def test_valid_blob_returns_shape(self):
        from kerf_imports.freecad.brep_importer import lift_brep_blob
        brep = _make_box_brep()
        shape = lift_brep_blob(brep)
        assert not shape.IsNull()

    def test_corrupt_blob_raises_brep_lift_error(self):
        from kerf_imports.freecad.brep_importer import lift_brep_blob, BRepLiftError
        with pytest.raises(BRepLiftError):
            lift_brep_blob(b"this is definitely not a brep file \x00\xff")

    def test_empty_blob_raises_brep_lift_error(self):
        from kerf_imports.freecad.brep_importer import lift_brep_blob, BRepLiftError
        with pytest.raises(BRepLiftError):
            lift_brep_blob(b"")

    def test_raises_brep_lift_error_not_bare_exception(self):
        """BRepLiftError must be the raised type, not RuntimeError or ValueError."""
        from kerf_imports.freecad.brep_importer import lift_brep_blob, BRepLiftError
        exc_type = None
        try:
            lift_brep_blob(b"garbage")
        except Exception as exc:
            exc_type = type(exc)
        assert exc_type is BRepLiftError, (
            f"Expected BRepLiftError, got {exc_type}"
        )


class TestBuildFeatureTreeSingleBody:
    """Round-trip test: one Body → one FeaturePayload with one import_brep node."""

    def test_single_body_one_feature(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree

        brep = _make_box_brep(10, 20, 30)
        doc = _make_fcstd_doc_single(brep)
        result = build_feature_tree(doc)

        assert len(result.features) == 1

    def test_single_body_one_import_brep_node(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree

        brep = _make_box_brep(10, 20, 30)
        doc = _make_fcstd_doc_single(brep)
        result = build_feature_tree(doc)

        feat = result.features[0]
        assert len(feat.nodes) == 1
        assert feat.nodes[0].kind == "import_brep"

    def test_single_body_asset_bytes_match(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree

        brep = _make_box_brep(10, 20, 30)
        doc = _make_fcstd_doc_single(brep)
        result = build_feature_tree(doc)

        node = result.features[0].nodes[0]
        asset_id = node.params["asset_id"]

        assert asset_id is not None, "asset_id should not be None for a valid blob"
        assert asset_id in result.assets
        # The stored bytes should hash to the same sha256 embedded in asset_id
        sha256_in_id = asset_id.removeprefix("brep:")
        actual_sha256 = hashlib.sha256(result.assets[asset_id]).hexdigest()
        assert actual_sha256 == sha256_in_id

    def test_single_body_asset_bytes_equal_original(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree

        brep = _make_box_brep(10, 20, 30)
        doc = _make_fcstd_doc_single(brep)
        result = build_feature_tree(doc)

        node = result.features[0].nodes[0]
        asset_id = node.params["asset_id"]
        assert result.assets[asset_id] == brep

    def test_body_name_and_label_propagated(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree

        brep = _make_box_brep()
        doc = _make_fcstd_doc_single(brep, body_name="MyWidget")
        result = build_feature_tree(doc)

        feat = result.features[0]
        assert feat.body_name == "MyWidget"
        assert feat.body_label == "MyWidget"


class TestBuildFeatureTreeTwoBodies:
    """Multi-Body: 2 bodies → 2 features → 2 distinct asset_ids."""

    def test_two_bodies_two_features(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree

        brep1 = _make_box_brep(10, 10, 10)
        brep2 = _make_box_brep(20, 20, 20)
        doc = _make_fcstd_doc_two_bodies(brep1, brep2)
        result = build_feature_tree(doc)

        assert len(result.features) == 2

    def test_two_bodies_two_import_brep_nodes(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree

        brep1 = _make_box_brep(10, 10, 10)
        brep2 = _make_box_brep(20, 20, 20)
        doc = _make_fcstd_doc_two_bodies(brep1, brep2)
        result = build_feature_tree(doc)

        for feat in result.features:
            assert len(feat.nodes) == 1
            assert feat.nodes[0].kind == "import_brep"

    def test_two_bodies_distinct_asset_ids(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree

        brep1 = _make_box_brep(10, 10, 10)
        brep2 = _make_box_brep(20, 20, 20)  # different dimensions → different blob
        doc = _make_fcstd_doc_two_bodies(brep1, brep2)
        result = build_feature_tree(doc)

        ids = [f.nodes[0].params["asset_id"] for f in result.features]
        assert ids[0] != ids[1], "Two distinct bodies must get distinct asset_ids"

    def test_two_bodies_two_assets(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree

        brep1 = _make_box_brep(10, 10, 10)
        brep2 = _make_box_brep(20, 20, 20)
        doc = _make_fcstd_doc_two_bodies(brep1, brep2)
        result = build_feature_tree(doc)

        assert len(result.assets) == 2

    def test_two_bodies_asset_bytes_correct(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree

        brep1 = _make_box_brep(10, 10, 10)
        brep2 = _make_box_brep(20, 20, 20)
        doc = _make_fcstd_doc_two_bodies(brep1, brep2)
        result = build_feature_tree(doc)

        id1 = result.features[0].nodes[0].params["asset_id"]
        id2 = result.features[1].nodes[0].params["asset_id"]
        assert result.assets[id1] == brep1
        assert result.assets[id2] == brep2


class TestCorruptBlob:
    """Corrupt blob: build_feature_tree raises BRepLiftError (not bare Exception)."""

    def _make_corrupt_doc(self):
        from kerf_imports.freecad.types import FCStdDocument, FCStdObject

        tip_name = "Body_Pad"
        tip_obj = FCStdObject(
            name=tip_name,
            type="PartDesign::Pad",
            label=tip_name,
            properties={"Shape": b"this is corrupt brep data \x00\x01\x02"},
        )
        body_obj = FCStdObject(
            name="Body",
            type="PartDesign::Body",
            label="Body",
            properties={"Tip": tip_name},
        )
        return FCStdDocument(
            schema_version=4,
            program_version="0.21R3",
            objects=[body_obj, tip_obj],
            properties={},
            brep_blobs={},
            raw_xml={},
        )

    def test_corrupt_blob_raises_brep_lift_error(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree, BRepLiftError
        doc = self._make_corrupt_doc()
        with pytest.raises(BRepLiftError):
            build_feature_tree(doc)

    def test_corrupt_blob_not_bare_runtime_error(self):
        from kerf_imports.freecad.brep_importer import build_feature_tree, BRepLiftError
        doc = self._make_corrupt_doc()
        try:
            build_feature_tree(doc)
            assert False, "Should have raised"
        except BRepLiftError:
            pass  # correct
        except RuntimeError as exc:
            pytest.fail(f"Got bare RuntimeError instead of BRepLiftError: {exc}")
        except Exception as exc:
            pytest.fail(f"Got {type(exc).__name__} instead of BRepLiftError: {exc}")
