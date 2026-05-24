"""GK-P47 wiring test: isophote_analysis ToolSpec, match_srf G3, loft guide_curves."""
from __future__ import annotations

import json
import pathlib
import uuid

import pytest

_WORKTREE = pathlib.Path(__file__).parents[3]
_FEATURE_VIEW = _WORKTREE / "src" / "components" / "FeatureView.jsx"


def _fv() -> str:
    return _FEATURE_VIEW.read_text(encoding="utf-8")


def _registered(name: str) -> bool:
    from kerf_chat.tools.registry import Registry  # type: ignore
    return any(t.spec.name == name for t in Registry)


# FeatureView
def test_isophote_analysis_in_feature_view():
    assert "isophote_analysis" in _fv()


# ToolSpec registration
def test_isophote_analysis_toolspec_registered():
    try:
        import kerf_cad_core.surfacing  # noqa: F401 — triggers @register
        assert _registered("feature_isophote_analysis")
    except ImportError:
        pytest.skip("kerf_chat not importable")


def test_match_srf_g3_in_toolspec_enum():
    """match_surface_edge_tool continuity enum must include G3."""
    try:
        from kerf_cad_core.geom.match_srf import _match_srf_spec  # type: ignore
    except ImportError:
        pytest.skip("match_srf not importable")
    cont_prop = _match_srf_spec.input_schema["properties"]["continuity"]
    assert "G3" in cont_prop["enum"], "G3 missing from match_surface_edge_tool continuity enum"


def test_feature_loft_guide_curves_in_toolspec():
    """feature_loft ToolSpec must advertise guide_curve_paths."""
    try:
        from kerf_cad_core.feature_loft import feature_loft_spec  # type: ignore
    except ImportError:
        pytest.skip("feature_loft not importable")
    props = feature_loft_spec.input_schema["properties"]
    assert "guide_curve_paths" in props, "guide_curve_paths missing from feature_loft schema"


def test_isophote_analysis_schema():
    try:
        import kerf_cad_core.surfacing as m  # noqa: F401
    except ImportError:
        pytest.skip("surfacing not importable")
    try:
        from kerf_chat.tools.registry import Registry  # type: ignore
    except ImportError:
        pytest.skip("kerf_chat not importable")
    matching = [t for t in Registry if t.spec.name == "feature_isophote_analysis"]
    if not matching:
        pytest.skip("feature_isophote_analysis not registered")
    spec = matching[0].spec
    schema = spec.input_schema
    assert "target_id" in schema.get("required", [])
    assert "file_id" in schema.get("required", [])


def test_isophote_analysis_dispatch_bad_args():
    """feature_isophote_analysis returns BAD_ARGS when file_id is missing."""
    try:
        import asyncio
        from kerf_cad_core.surfacing import run_feature_isophote_analysis
    except ImportError:
        pytest.skip("surfacing not importable")

    class _FakePool:
        def fetchone(self, *a, **kw): return None

    class _FakeCtx:
        pool = _FakePool()
        project_id = uuid.uuid4()

    result = asyncio.get_event_loop().run_until_complete(
        run_feature_isophote_analysis(
            _FakeCtx(),
            json.dumps({"target_id": "sweep-1"}).encode(),
        )
    )
    payload = json.loads(result)
    assert payload.get("code") == "BAD_ARGS"
