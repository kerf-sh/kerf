"""Hermetic test for the seed/promote step. No network, no LLM.

Asserts the emitted PartDoc matches Kerf's existing seed/publishers shape
and that seeding writes only NEW files into the chosen out dir (never
rewrites a tracked file).
"""

import json
import os

import pytest

from kerf_partsgen import kernel
from kerf_partsgen.seed import part_doc_for_variant, seed_wishlist
from kerf_partsgen.spec import VariantResult

needs_kernel = pytest.mark.skipif(
    not kernel.KERNEL_AVAILABLE,
    reason="no OCCT kernel binding (cadquery/pythonocc) installed",
)


class _Fam:
    family_id = "iso_7089_flat_washer"
    name = "ISO 7089 flat washer"
    standard = "ISO 7089"
    category = "mechanical/washer"


def test_part_doc_matches_publisher_seed_shape():
    v = VariantResult(
        family_id="iso_7089_flat_washer", size="M6", status="PASS",
        measured_bbox_mm=(12.0, 12.0, 1.6), measured_volume_mm3=129.0,
    )
    doc = part_doc_for_variant(
        _Fam(), {"size": "M6", "params": {"outer_d": 12.0}}, v
    )
    # mirrors seed/publishers/parts/*.json (version/name/distributors + meta)
    assert doc["version"] == 1
    assert doc["name"] == "ISO 7089 flat washer M6"
    assert doc["category"] == "mechanical/washer"
    assert doc["visibility"] == "public"
    assert "distributors" in doc and isinstance(doc["distributors"], list)
    geom = doc["metadata"]["geometry"]
    assert geom["generator"].endswith("iso_7089_flat_washer.py")
    assert geom["measured_bbox_mm"] == [12.0, 12.0, 1.6]
    # JSON-serialisable (it gets written verbatim)
    json.dumps(doc)


@needs_kernel
def test_seed_writes_partdocs_for_approved_only(tmp_path):
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    out = tmp_path / "seedout"
    # out_root redirects the enumerate .parts-out tree into tmp so the test
    # never writes into the working copy.
    manifest = seed_wishlist(
        repo_root, domain="mechanical", out_dir=str(out),
        out_root=str(tmp_path),
    )
    # the two committed [x] families → PartDocs written into the out dir
    assert manifest["families"] == 2
    assert len(manifest["written"]) >= 20  # 10 sizes x 2 families
    for path in manifest["written"]:
        assert path.startswith(str(out))
        with open(path) as fh:
            doc = json.load(fh)
        assert doc["version"] == 1 and doc["name"]
    # writing only NEW files into a fresh dir — no tracked file touched
    names = sorted(os.listdir(out))
    assert all(n.endswith(".json") for n in names)
