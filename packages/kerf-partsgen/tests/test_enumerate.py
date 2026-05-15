"""Hermetic tests for the enumeration loop + verification gate.

No network, no LLM. Geometry tests skip cleanly when no OCCT kernel binding
is installed (mirrors the kerf-cad-core `_OCC_AVAILABLE` skip convention).
"""

import os

import pytest

from kerf_partsgen import kernel
from kerf_partsgen.enumerate import enumerate_family, summarize
from kerf_partsgen.loader import load_family
from kerf_partsgen.spec import VariantResult
from kerf_partsgen.verify import verify_variant

_SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "sample_generators")
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)

needs_kernel = pytest.mark.skipif(
    not kernel.KERNEL_AVAILABLE,
    reason="no OCCT kernel binding (cadquery/pythonocc) installed",
)


def test_loader_validates_contract(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("FAMILY = {'family_id': 'x'}\nSIZES = []\n")
    with pytest.raises(ValueError):
        load_family("bad", str(tmp_path))


def test_sample_generators_satisfy_contract():
    g = load_family("sample_block", _SAMPLE_DIR)
    assert g.family_id == "sample_block"
    assert len(g.sizes) == 3
    assert callable(g.build)


@needs_kernel
def test_good_sample_enumerates_all_pass(tmp_path):
    fr = enumerate_family(
        "sample_block", str(tmp_path), gen_dir=_SAMPLE_DIR, domain="mechanical"
    )
    assert fr.error == ""
    assert fr.passed == 3
    assert fr.failed == 0
    # artifacts land ONLY under .parts-out/, never a tracked path
    for v in fr.variants:
        assert os.path.isfile(os.path.join(v.artifact_dir, "meta.json"))
        assert os.path.isfile(os.path.join(v.artifact_dir, "part.step"))
        assert ".parts-out" in v.artifact_dir


@needs_kernel
def test_bad_sample_is_rejected_by_the_gate(tmp_path):
    """A deliberately mis-declared variant MUST FAIL — a green check is
    measured geometry, never an LLM reply."""
    fr = enumerate_family(
        "sample_bad_block", str(tmp_path), gen_dir=_SAMPLE_DIR,
        domain="mechanical",
    )
    assert fr.passed == 0
    assert fr.failed == 1
    v = fr.variants[0]
    assert v.status == "FAIL"
    assert any("bbox" in r or "volume" in r for r in v.reasons)
    # FAIL still emits a result artifact (but no STEP for a failed solid)
    assert os.path.isfile(os.path.join(v.artifact_dir, "RESULT"))
    assert not os.path.isfile(os.path.join(v.artifact_dir, "part.step"))


@needs_kernel
def test_reference_generators_enumerate_clean(tmp_path):
    """The two committed reference generators genuinely build + pass."""
    for fam in ("iso_7089_flat_washer", "iso_4017_hex_head_bolt"):
        fr = enumerate_family(fam, str(tmp_path), domain="mechanical")
        assert fr.error == "", fr.error
        assert fr.failed == 0, [
            (v.size, v.reasons) for v in fr.variants if v.status == "FAIL"
        ]
        assert fr.passed == len(fr.variants) >= 10


def test_gate_flags_invalid_solid_without_kernel():
    """Gate logic is pure: a non-valid GeneratedPart FAILs regardless of
    kernel availability (keeps this assertion hermetic everywhere)."""
    fake = kernel.GeneratedPart(
        solid=None, is_valid=False, volume_mm3=0.0, bbox_mm=(0.0, 0.0, 0.0)
    )
    res = verify_variant(
        "fam", "S", {"expect": {"bbox_mm": [1, 1, 1], "volume_mm3": 1.0}}, fake
    )
    assert isinstance(res, VariantResult)
    assert res.status == "FAIL"
    assert any("invalid" in r or "non-positive" in r for r in res.reasons)


def test_summarize_is_stringy():
    out = summarize([])
    assert "enumerate" in out


def test_missing_generator_is_a_clean_error_not_a_crash(tmp_path):
    fr = enumerate_family(
        "does_not_exist", str(tmp_path), gen_dir=str(tmp_path),
        domain="mechanical",
    )
    assert fr.error and "author" in fr.error
    assert fr.variants == []


def test_enumerate_without_kernel_degrades_to_fail(tmp_path, monkeypatch):
    """A contributor with no OCCT binding still gets a deterministic FAIL
    per variant — never an unhandled crash. We simulate "no kernel" by
    forcing every kernel op to raise KernelUnavailable."""
    monkeypatch.setattr(kernel, "KERNEL_AVAILABLE", False)

    def _boom(*_a, **_k):
        raise kernel.KernelUnavailable("simulated: no OCCT binding")

    monkeypatch.setattr(kernel, "box", _boom)
    fr = enumerate_family(
        "sample_block", str(tmp_path), gen_dir=_SAMPLE_DIR,
        domain="mechanical",
    )
    assert fr.error == ""
    assert fr.passed == 0
    assert fr.failed == 3
    assert all(v.status == "FAIL" for v in fr.variants)
    assert any("kernel unavailable" in r.lower()
               for v in fr.variants for r in v.reasons)
    # still emits a RESULT artifact under .parts-out/ for each variant
    for v in fr.variants:
        assert os.path.isfile(os.path.join(v.artifact_dir, "RESULT"))
