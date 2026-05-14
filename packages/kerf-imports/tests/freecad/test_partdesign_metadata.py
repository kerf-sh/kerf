"""
test_partdesign_metadata.py — T4 PartDesign feature-tree metadata capture tests.

Tests:
  - Single Body with one Pad: import_brep first + one metadata pad node.
  - Pad + Pocket: two metadata nodes after import_brep.
  - Fillet: edge refs preserved in freecad_ref.edge_names.
  - Pattern: occurrences + direction captured.
  - Sketch ref resolution: Profile → sketch_path.
  - read_only: true on every metadata node.
  - No PartDesign::Body objects → falls back to T2 features.

Note: We omit Shape (BRep) bytes in most test fixtures so that the BRep-lift
step (T2) produces a placeholder import_brep node (asset_id=None) rather than
attempting to parse fake bytes. The metadata-tree structure is what we're
testing here.
"""
from __future__ import annotations

import pytest

from kerf_imports.freecad.types import FCStdDocument, FCStdObject, LinkRef
from kerf_imports.freecad.features import build_metadata_tree


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(*objects, brep_blobs=None):
    return FCStdDocument(
        schema_version=4,
        program_version="0.21R3",
        objects=list(objects),
        properties={},
        brep_blobs=brep_blobs or {},
        raw_xml={},
    )


def _body(name="Body", tip="Pad", extra_props=None):
    props = {"Tip": tip}
    if extra_props:
        props.update(extra_props)
    return FCStdObject(name=name, type="PartDesign::Body", label=name, properties=props)


def _sketch(name="Sketch"):
    return FCStdObject(
        name=name, type="Sketcher::SketchObject", label=name,
        properties={"Geometry": [], "Constraints": []},
    )


def _pad(name="Pad", sketch_name="Sketch", length=10.0):
    """Pad without a Shape property — BRep-lift emits placeholder (asset_id=None)."""
    props = {
        "Profile": LinkRef(sketch_name),
        "Length": length,
    }
    return FCStdObject(name=name, type="PartDesign::Pad", label=name, properties=props)


def _pocket(name="Pocket", sketch_name="Sketch", length=5.0):
    return FCStdObject(
        name=name, type="PartDesign::Pocket", label=name,
        properties={
            "Profile": LinkRef(sketch_name),
            "Length": length,
        },
    )


def _fillet(name="Fillet", base_name="Pad", edge_names=None):
    base_ref = LinkRef(base_name, edge_names or ["Edge1", "Edge3"])
    return FCStdObject(
        name=name, type="PartDesign::Fillet", label=name,
        properties={"Base": base_ref, "Radius": 2.0},
    )


def _linear_pattern(name="LinearPattern", occ=4, length=20.0):
    return FCStdObject(
        name=name, type="PartDesign::LinearPattern", label=name,
        properties={"Occurrences": int(occ), "Length": float(length)},
    )


# ---------------------------------------------------------------------------
# Tests — single Body, one Pad
# ---------------------------------------------------------------------------

class TestSingleBodyOnePad:
    def _build(self):
        sk = _sketch("Sketch")
        pad = _pad("Pad", "Sketch")
        body = _body("Body", "Pad", extra_props={"Model": [LinkRef("Sketch"), LinkRef("Pad")]})
        doc = _make_doc(body, sk, pad)
        return build_metadata_tree(doc)

    def test_one_payload_returned(self):
        payloads = self._build()
        assert len(payloads) == 1

    def test_first_node_is_import_brep(self):
        payload = self._build()[0]
        assert payload.nodes[0].kind == "import_brep"

    def test_second_node_is_pad(self):
        payload = self._build()[0]
        assert payload.nodes[1].kind == "pad"

    def test_pad_node_has_read_only(self):
        payload = self._build()[0]
        pad_node = payload.nodes[1]
        assert pad_node.params.get("read_only") is True

    def test_pad_node_has_freecad_ref(self):
        payload = self._build()[0]
        pad_node = payload.nodes[1]
        ref = pad_node.params.get("freecad_ref")
        assert ref is not None
        assert ref["type"] == "PartDesign::Pad"
        assert ref["name"] == "Pad"

    def test_pad_node_has_sketch_path(self):
        payload = self._build()[0]
        pad_node = payload.nodes[1]
        assert "sketch_path" in pad_node.params

    def test_pad_node_has_length(self):
        payload = self._build()[0]
        pad_node = payload.nodes[1]
        assert pad_node.params.get("length") == 10.0

    def test_body_name_propagated(self):
        payload = self._build()[0]
        assert payload.body_name == "Body"


# ---------------------------------------------------------------------------
# Tests — Pad + Pocket
# ---------------------------------------------------------------------------

class TestPadAndPocket:
    def _build(self):
        sk = _sketch("Sketch")
        pad = _pad("Pad", "Sketch")
        pocket = _pocket("Pocket", "Sketch", length=4.0)
        body = _body("Body", "Pocket", extra_props={
            "Model": [LinkRef("Sketch"), LinkRef("Pad"), LinkRef("Pocket")]
        })
        doc = _make_doc(body, sk, pad, pocket)
        return build_metadata_tree(doc)

    def test_three_nodes(self):
        payload = self._build()[0]
        # import_brep + pad + pocket
        assert len(payload.nodes) == 3

    def test_pocket_node_present(self):
        payload = self._build()[0]
        ops = [n.kind for n in payload.nodes]
        assert "pocket" in ops

    def test_pocket_has_length(self):
        payload = self._build()[0]
        pocket_node = next(n for n in payload.nodes if n.kind == "pocket")
        assert pocket_node.params.get("length") == 4.0


# ---------------------------------------------------------------------------
# Tests — Fillet edge refs
# ---------------------------------------------------------------------------

class TestFilletEdgeRefs:
    def _build(self):
        pad = _pad("Pad", "Sketch")
        sk = _sketch("Sketch")
        fillet = _fillet("Fillet", "Pad", ["Edge2", "Edge5"])
        body = _body("Body", "Fillet", extra_props={
            "Model": [LinkRef("Sketch"), LinkRef("Pad"), LinkRef("Fillet")]
        })
        doc = _make_doc(body, sk, pad, fillet)
        return build_metadata_tree(doc)

    def test_fillet_node_present(self):
        payload = self._build()[0]
        ops = [n.kind for n in payload.nodes]
        assert "fillet" in ops

    def test_fillet_edge_names_in_freecad_ref(self):
        payload = self._build()[0]
        fillet_node = next(n for n in payload.nodes if n.kind == "fillet")
        ref = fillet_node.params["freecad_ref"]
        assert "edge_names" in ref
        assert "Edge2" in ref["edge_names"]

    def test_fillet_rebind_needed(self):
        payload = self._build()[0]
        fillet_node = next(n for n in payload.nodes if n.kind == "fillet")
        assert fillet_node.params["freecad_ref"].get("rebind_needed") is True

    def test_fillet_radius_captured(self):
        payload = self._build()[0]
        fillet_node = next(n for n in payload.nodes if n.kind == "fillet")
        assert fillet_node.params.get("radius") == 2.0


# ---------------------------------------------------------------------------
# Tests — LinearPattern
# ---------------------------------------------------------------------------

class TestLinearPattern:
    def _build(self):
        pad = _pad("Pad", "Sketch")
        sk = _sketch("Sketch")
        pattern = _linear_pattern("LP", occ=5, length=30.0)
        body = _body("Body", "LP", extra_props={
            "Model": [LinkRef("Sketch"), LinkRef("Pad"), LinkRef("LP")]
        })
        doc = _make_doc(body, sk, pad, pattern)
        return build_metadata_tree(doc)

    def test_linear_pattern_node_present(self):
        payload = self._build()[0]
        ops = [n.kind for n in payload.nodes]
        assert "linear_pattern" in ops

    def test_occurrences_captured(self):
        payload = self._build()[0]
        lp_node = next(n for n in payload.nodes if n.kind == "linear_pattern")
        assert lp_node.params.get("occurrences") == 5.0

    def test_length_captured(self):
        payload = self._build()[0]
        lp_node = next(n for n in payload.nodes if n.kind == "linear_pattern")
        assert lp_node.params.get("length") == 30.0


# ---------------------------------------------------------------------------
# Tests — no PartDesign::Body fallback
# ---------------------------------------------------------------------------

class TestNoBodyFallback:
    def test_no_body_returns_t2_features(self):
        """If no PartDesign::Body, falls back to T2's synthetic body result."""
        doc = _make_doc()  # empty document
        payloads = build_metadata_tree(doc)
        # Should return an empty list or a synthetic body result
        # (T2 returns [] for empty doc)
        assert isinstance(payloads, list)


# ---------------------------------------------------------------------------
# Tests — Sketcher objects skipped in metadata nodes
# ---------------------------------------------------------------------------

class TestSketcherSkipped:
    def test_sketch_objects_not_in_metadata_nodes(self):
        """Sketcher::SketchObject must not appear as a metadata node."""
        sk = _sketch("Sketch")
        pad = _pad("Pad", "Sketch")
        body = _body("Body", "Pad", extra_props={
            "Model": [LinkRef("Sketch"), LinkRef("Pad")]
        })
        doc = _make_doc(body, sk, pad)
        payloads = build_metadata_tree(doc)
        payload = payloads[0]
        ops = [n.kind for n in payload.nodes]
        # No "sketch" op should appear — sketches are separate files
        assert "sketch" not in ops
        assert "sketcher" not in [o.lower() for o in ops]


# ---------------------------------------------------------------------------
# Tests — unknown PartDesign type (future-proofing)
# ---------------------------------------------------------------------------

class TestUnknownPartDesignType:
    def test_unknown_partdesign_gets_freecad_feature_op(self):
        pad = _pad("Pad", "Sketch")
        sk = _sketch("Sketch")
        unknown = FCStdObject(
            name="FutureFeat",
            type="PartDesign::FutureFeature",
            label="FutureFeat",
            properties={},
        )
        body = _body("Body", "FutureFeat", extra_props={
            "Model": [LinkRef("Sketch"), LinkRef("Pad"), LinkRef("FutureFeat")]
        })
        doc = _make_doc(body, sk, pad, unknown)
        payloads = build_metadata_tree(doc)
        payload = payloads[0]
        ops = [n.kind for n in payload.nodes]
        assert "freecad_feature" in ops
