"""
Tests for kerf_cad_core.jewelry.ring

Pure-Python section (always runs):
  - ring_size_to_diameter: US, UK/AU, EU, JP forward lookup
  - ring_diameter_to_size: round-trip inverse
  - compute_shank_params: profile/shoulder validation, geometry output
  - LLM tool runners: jewelry_ring_size_to_diameter, jewelry_create_ring_shank
    (using in-memory fake pool/ctx, same pattern as test_feature_sweep1_mode.py)

OCC-gated section:
  - Skipped cleanly when pythonocc absent (checks _OCC_AVAILABLE flag).
  - When OCC present: validates that a ring_shank node can be evaluated by
    the worker (structural smoke test only — full sweep tested in occtWorker
    JS tests).
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.jewelry.ring import (
    _UK_AU_SIZES,
    _JP_SIZES,
    _VALID_PROFILES,
    _VALID_SHOULDER_STYLES,
    _VALID_SYSTEMS,
    _id_mm_to_circumference,
    compute_shank_params,
    jewelry_create_ring_shank_spec,
    jewelry_ring_size_to_diameter_spec,
    ring_diameter_to_size,
    ring_size_to_diameter,
    run_jewelry_create_ring_shank,
    run_jewelry_ring_size_to_diameter,
)

_PI = math.pi


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(initial_content: str = ""):
    """Return (ctx, store, file_id) with an in-memory fake pool."""
    store = {
        "content": initial_content or json.dumps({"version": 1, "features": []}),
        "kind": "feature",
    }
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            return (store["content"], store["kind"])

        def execute(self, query, *args):
            store["content"] = args[0]

    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    except ImportError:
        # Minimal stub when kerf_core is not installed in the test env.
        class ProjectCtx:  # type: ignore[no-redef]
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

    ctx = ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )
    return ctx, store, file_id


def run_tool_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        return json.loads(loop.run_until_complete(coro))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# US ring-size forward lookups
# ---------------------------------------------------------------------------

class TestUSForward:
    def test_us7_approx_17_3mm(self):
        """US 7 should be ≈17.32 mm per the industry formula."""
        d = ring_size_to_diameter("us", 7)
        assert abs(d - 17.3196) < 0.001, f"US 7 expected ≈17.32 mm, got {d}"

    def test_us0_intercept(self):
        """US 0 → exactly intercept value 11.63 mm."""
        d = ring_size_to_diameter("us", 0)
        assert abs(d - 11.63) < 1e-9

    def test_us16_max(self):
        """US 16 → 11.63 + 0.8128×16 = 24.6348 mm."""
        expected = 11.63 + 0.8128 * 16
        d = ring_size_to_diameter("us", 16)
        assert abs(d - expected) < 1e-9

    def test_us_half_size_string(self):
        """US '7½' should equal US 7.5."""
        d_str = ring_size_to_diameter("us", "7½")
        d_float = ring_size_to_diameter("us", 7.5)
        assert abs(d_str - d_float) < 1e-9

    def test_us_half_size_decimal(self):
        d = ring_size_to_diameter("us", 6.5)
        expected = 11.63 + 0.8128 * 6.5
        assert abs(d - expected) < 1e-9

    def test_us_out_of_range_raises(self):
        with pytest.raises(ValueError, match="0–16"):
            ring_size_to_diameter("us", 17)

    def test_us_negative_raises(self):
        with pytest.raises(ValueError, match="0–16"):
            ring_size_to_diameter("us", -0.5)

    def test_us_circumference_us7(self):
        """US 7 circumference should be close to published 54.44 mm."""
        d = ring_size_to_diameter("us", 7)
        c = _id_mm_to_circumference(d)
        assert abs(c - 54.44) < 0.1, f"Circumference for US 7 expected ≈54.44 mm, got {c}"

    def test_us_case_insensitive(self):
        d1 = ring_size_to_diameter("US", 7)
        d2 = ring_size_to_diameter("us", 7)
        assert d1 == d2

    def test_us10_approx_19_76mm(self):
        d = ring_size_to_diameter("us", 10)
        assert abs(d - 19.76) < 0.01


# ---------------------------------------------------------------------------
# UK / AU ring-size forward lookups
# ---------------------------------------------------------------------------

class TestUKAUForward:
    def test_uk_n(self):
        """UK N → circumference 54.4 mm → ID ≈ 17.32 mm."""
        d = ring_size_to_diameter("uk", "N")
        expected = 54.4 / _PI
        assert abs(d - expected) < 0.01

    def test_au_n_same_as_uk(self):
        d_uk = ring_size_to_diameter("uk", "N")
        d_au = ring_size_to_diameter("au", "N")
        assert abs(d_uk - d_au) < 1e-9

    def test_uk_half_size(self):
        d = ring_size_to_diameter("uk", "N½")
        expected = _UK_AU_SIZES["N½"] / _PI
        assert abs(d - expected) < 1e-9

    def test_uk_z_plus_1(self):
        d = ring_size_to_diameter("uk", "Z+1")
        expected = _UK_AU_SIZES["Z+1"] / _PI
        assert abs(d - expected) < 1e-9

    def test_uk_unknown_raises(self):
        with pytest.raises(ValueError):
            ring_size_to_diameter("uk", "ZZZ")

    def test_uk_lowercase_normalised(self):
        """Lowercase 'n' should be accepted and equal 'N'."""
        d_lower = ring_size_to_diameter("uk", "n")
        d_upper = ring_size_to_diameter("uk", "N")
        assert abs(d_lower - d_upper) < 1e-9


# ---------------------------------------------------------------------------
# EU ring-size forward lookups
# ---------------------------------------------------------------------------

class TestEUForward:
    def test_eu_54(self):
        d = ring_size_to_diameter("eu", 54)
        expected = 54.0 / _PI
        assert abs(d - expected) < 1e-9

    def test_eu_out_of_range_low(self):
        with pytest.raises(ValueError, match="41"):
            ring_size_to_diameter("eu", 40)

    def test_eu_out_of_range_high(self):
        with pytest.raises(ValueError, match="76"):
            ring_size_to_diameter("eu", 77)

    def test_eu_string_number(self):
        d = ring_size_to_diameter("eu", "54")
        expected = 54.0 / _PI
        assert abs(d - expected) < 1e-9

    def test_eu_float(self):
        d = ring_size_to_diameter("eu", 54.5)
        expected = 54.5 / _PI
        assert abs(d - expected) < 1e-9


# ---------------------------------------------------------------------------
# JP ring-size forward lookups
# ---------------------------------------------------------------------------

class TestJPForward:
    def test_jp_13(self):
        d = ring_size_to_diameter("jp", 13)
        expected = _JP_SIZES[13] / _PI
        assert abs(d - expected) < 1e-9

    def test_jp_1(self):
        d = ring_size_to_diameter("jp", 1)
        expected = _JP_SIZES[1] / _PI
        assert abs(d - expected) < 1e-9

    def test_jp_30(self):
        d = ring_size_to_diameter("jp", 30)
        expected = _JP_SIZES[30] / _PI
        assert abs(d - expected) < 1e-9

    def test_jp_out_of_range(self):
        with pytest.raises(ValueError, match="1–30"):
            ring_size_to_diameter("jp", 31)

    def test_jp_zero_raises(self):
        with pytest.raises(ValueError, match="1–30"):
            ring_size_to_diameter("jp", 0)


# ---------------------------------------------------------------------------
# Unknown system
# ---------------------------------------------------------------------------

class TestUnknownSystem:
    def test_unknown_system_raises(self):
        with pytest.raises(ValueError, match="Unknown ring-size system"):
            ring_size_to_diameter("cn", 10)


# ---------------------------------------------------------------------------
# Inverse: ring_diameter_to_size
# ---------------------------------------------------------------------------

class TestInverse:
    def test_us_round_trip_us7(self):
        d = ring_size_to_diameter("us", 7)
        back = ring_diameter_to_size("us", d)
        assert back == 7.0

    def test_us_round_trip_us7_5(self):
        d = ring_size_to_diameter("us", 7.5)
        back = ring_diameter_to_size("us", d)
        assert back == 7.5

    def test_us_round_trip_us0(self):
        d = ring_size_to_diameter("us", 0)
        back = ring_diameter_to_size("us", d)
        assert back == 0.0

    def test_uk_round_trip_n(self):
        d = ring_size_to_diameter("uk", "N")
        back = ring_diameter_to_size("uk", d)
        assert back == "N"

    def test_uk_round_trip_z(self):
        d = ring_size_to_diameter("uk", "Z")
        back = ring_diameter_to_size("uk", d)
        assert back == "Z"

    def test_eu_round_trip(self):
        d = ring_size_to_diameter("eu", 54)
        back = ring_diameter_to_size("eu", d)
        # Should round-trip back to 54.0 (nearest 0.5)
        assert abs(back - 54.0) < 0.5

    def test_jp_round_trip(self):
        d = ring_size_to_diameter("jp", 13)
        back = ring_diameter_to_size("jp", d)
        assert back == 13

    def test_inverse_zero_diameter_raises(self):
        with pytest.raises(ValueError, match="positive"):
            ring_diameter_to_size("us", 0)

    def test_inverse_negative_diameter_raises(self):
        with pytest.raises(ValueError, match="positive"):
            ring_diameter_to_size("us", -5.0)

    def test_inverse_unknown_system_raises(self):
        with pytest.raises(ValueError, match="Unknown ring-size system"):
            ring_diameter_to_size("xx", 17.0)


# ---------------------------------------------------------------------------
# compute_shank_params
# ---------------------------------------------------------------------------

class TestComputeShankParams:
    def test_basic_us7(self):
        p = compute_shank_params(7, "us", band_width=4.0, thickness=1.8,
                                  profile="comfort_fit", shoulder_style="plain")
        assert abs(p["inner_diameter_mm"] - 17.32) < 0.01
        assert abs(p["outer_diameter_mm"] - (17.32 + 2 * 1.8)) < 0.01
        assert p["profile"] == "comfort_fit"
        assert p["shoulder_style"] == "plain"

    def test_all_profiles_accepted(self):
        for pr in _VALID_PROFILES:
            p = compute_shank_params(7, "us", profile=pr, shoulder_style="plain")
            assert p["profile"] == pr

    def test_all_shoulder_styles_accepted(self):
        for ss in _VALID_SHOULDER_STYLES:
            p = compute_shank_params(7, "us", profile="flat", shoulder_style=ss)
            assert p["shoulder_style"] == ss

    def test_cathedral_shoulder_hints(self):
        p = compute_shank_params(7, "us", shoulder_style="cathedral")
        h = p["shoulder_hints"]
        assert h["type"] == "cathedral"
        assert h["arch_height_mm"] > 0
        assert h["arch_start_deg"] == 70.0

    def test_split_shank_hints(self):
        p = compute_shank_params(7, "us", shoulder_style="split_shank")
        h = p["shoulder_hints"]
        assert h["type"] == "split_shank"
        assert h["prong_gap_mm"] > 0

    def test_bypass_hints(self):
        p = compute_shank_params(7, "us", shoulder_style="bypass")
        h = p["shoulder_hints"]
        assert h["type"] == "bypass"
        assert h["bypass_offset_mm"] > 0

    def test_tapered_ratio_stored(self):
        p = compute_shank_params(7, "us", profile="tapered", taper_ratio=0.7)
        assert p["taper_ratio"] == 0.7

    def test_invalid_profile_raises(self):
        with pytest.raises(ValueError, match="Unknown profile"):
            compute_shank_params(7, "us", profile="round")

    def test_invalid_shoulder_style_raises(self):
        with pytest.raises(ValueError, match="Unknown shoulder_style"):
            compute_shank_params(7, "us", shoulder_style="prong")

    def test_zero_band_width_raises(self):
        with pytest.raises(ValueError, match="band_width"):
            compute_shank_params(7, "us", band_width=0)

    def test_zero_thickness_raises(self):
        with pytest.raises(ValueError, match="thickness"):
            compute_shank_params(7, "us", thickness=0)

    def test_negative_taper_ratio_raises(self):
        with pytest.raises(ValueError, match="taper_ratio"):
            compute_shank_params(7, "us", taper_ratio=-0.5)

    def test_circumference_formula(self):
        p = compute_shank_params(7, "us")
        # Values are rounded to 4 decimal places in the output; allow rounding error
        assert abs(p["circumference_mm"] - _PI * p["inner_diameter_mm"]) < 1e-3

    def test_uk_size_accepted(self):
        p = compute_shank_params("N", "uk")
        assert p["inner_diameter_mm"] > 0

    def test_size_system_stored(self):
        p = compute_shank_params(7, "us")
        assert p["size_system"] == "us"
        assert p["ring_size"] == 7


# ---------------------------------------------------------------------------
# ToolSpec declarations
# ---------------------------------------------------------------------------

class TestToolSpecs:
    def test_ring_size_spec_name(self):
        assert jewelry_ring_size_to_diameter_spec.name == "jewelry_ring_size_to_diameter"

    def test_ring_size_spec_system_enum(self):
        props = jewelry_ring_size_to_diameter_spec.input_schema["properties"]
        assert "system" in props
        assert set(props["system"]["enum"]) == _VALID_SYSTEMS

    def test_create_shank_spec_name(self):
        assert jewelry_create_ring_shank_spec.name == "jewelry_create_ring_shank"

    def test_create_shank_spec_profile_enum(self):
        props = jewelry_create_ring_shank_spec.input_schema["properties"]
        assert "profile" in props
        assert set(props["profile"]["enum"]) == _VALID_PROFILES

    def test_create_shank_spec_shoulder_enum(self):
        props = jewelry_create_ring_shank_spec.input_schema["properties"]
        assert "shoulder_style" in props
        assert set(props["shoulder_style"]["enum"]) == _VALID_SHOULDER_STYLES

    def test_create_shank_required_fields(self):
        req = set(jewelry_create_ring_shank_spec.input_schema["required"])
        assert "file_id" in req
        assert "ring_size" in req


# ---------------------------------------------------------------------------
# LLM tool runner: jewelry_ring_size_to_diameter
# ---------------------------------------------------------------------------

class TestRingSizeToDiameterTool:
    def _run(self, **kwargs):
        ctx, _, _ = make_ctx()
        return run_tool_sync(
            run_jewelry_ring_size_to_diameter(ctx, json.dumps(kwargs).encode())
        )

    def test_forward_us7(self):
        r = self._run(system="us", size=7)
        assert "error" not in r, f"Unexpected error: {r}"
        assert abs(r["inner_diameter_mm"] - 17.3196) < 0.01

    def test_forward_uk_n(self):
        r = self._run(system="uk", size="N")
        assert "error" not in r
        assert r["inner_diameter_mm"] > 0

    def test_inverse_diameter_us(self):
        r = self._run(system="us", diameter_mm=17.3196)
        assert "error" not in r
        assert "nearest_size" in r

    def test_missing_system(self):
        r = self._run(size=7)
        # system defaults to empty string — should fail validation
        assert "error" in r

    def test_invalid_system(self):
        r = self._run(system="cn", size=7)
        assert "error" in r

    def test_us_out_of_range(self):
        r = self._run(system="us", size=17)
        assert "error" in r

    def test_jp_out_of_range(self):
        r = self._run(system="jp", size=31)
        assert "error" in r


# ---------------------------------------------------------------------------
# LLM tool runner: jewelry_create_ring_shank
# ---------------------------------------------------------------------------

class TestCreateRingShankTool:
    def _run(self, ctx, file_id, **kwargs):
        args = {"file_id": str(file_id), **kwargs}
        return run_tool_sync(
            run_jewelry_create_ring_shank(ctx, json.dumps(args).encode())
        )

    def test_basic_us7_plain(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, system="us")
        assert "error" not in r, f"Unexpected error: {r}"
        assert r.get("op") == "ring_shank"
        # Node should be persisted
        doc = json.loads(store["content"])
        features = doc["features"]
        assert len(features) == 1
        assert features[0]["op"] == "ring_shank"

    def test_node_id_generated(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7)
        assert "error" not in r
        assert r.get("id", "").startswith("ring_shank-")

    def test_explicit_node_id(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, id="myring-1")
        assert "error" not in r
        assert r.get("id") == "myring-1"

    def test_second_node_increments_id(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7)
        r2 = self._run(ctx, fid, ring_size=8)
        assert "error" not in r2
        assert r2.get("id") == "ring_shank-2"

    def test_cathedral_shoulder(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, shoulder_style="cathedral")
        assert "error" not in r
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["shoulder_style"] == "cathedral"
        h = node["shoulder_hints"]
        assert h["type"] == "cathedral"
        assert h["arch_height_mm"] > 0

    def test_all_profiles_accepted(self):
        for pr in _VALID_PROFILES:
            ctx, store, fid = make_ctx()
            r = self._run(ctx, fid, ring_size=7, profile=pr)
            assert "error" not in r, f"Profile {pr!r} raised error: {r}"

    def test_all_shoulder_styles_accepted(self):
        for ss in _VALID_SHOULDER_STYLES:
            ctx, store, fid = make_ctx()
            r = self._run(ctx, fid, ring_size=7, shoulder_style=ss)
            assert "error" not in r, f"Shoulder {ss!r} raised error: {r}"

    def test_invalid_profile_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, profile="round")
        assert "error" in r

    def test_invalid_shoulder_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, shoulder_style="prong")
        assert "error" in r

    def test_invalid_system_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, system="cn")
        assert "error" in r

    def test_zero_band_width_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, band_width=0)
        assert "error" in r

    def test_zero_thickness_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, thickness=0)
        assert "error" in r

    def test_missing_file_id_bad_args(self):
        ctx, store, fid = make_ctx()
        r = run_tool_sync(
            run_jewelry_create_ring_shank(ctx, json.dumps({"ring_size": 7}).encode())
        )
        assert "error" in r

    def test_missing_ring_size_bad_args(self):
        ctx, store, fid = make_ctx()
        r = run_tool_sync(
            run_jewelry_create_ring_shank(
                ctx, json.dumps({"file_id": str(fid)}).encode()
            )
        )
        assert "error" in r

    def test_invalid_file_id_bad_args(self):
        ctx, store, fid = make_ctx()
        r = run_tool_sync(
            run_jewelry_create_ring_shank(
                ctx, json.dumps({"file_id": "not-a-uuid", "ring_size": 7}).encode()
            )
        )
        assert "error" in r

    def test_non_feature_file_not_found(self):
        ctx, store, fid = make_ctx()
        store["kind"] = "sketch"
        r = self._run(ctx, fid, ring_size=7)
        assert "error" in r

    def test_node_contains_geometry(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, band_width=5.0, thickness=2.0)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["band_width_mm"] == 5.0
        assert node["thickness_mm"] == 2.0
        assert abs(node["inner_diameter_mm"] - 17.32) < 0.01

    def test_uk_ring_size(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size="N", system="uk")
        assert "error" not in r

    def test_eu_ring_size(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=54, system="eu")
        assert "error" not in r

    def test_jp_ring_size(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=13, system="jp")
        assert "error" not in r

    def test_tapered_profile_ratio_stored(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, profile="tapered", taper_ratio=0.6)
        doc = json.loads(store["content"])
        assert doc["features"][0]["taper_ratio"] == 0.6

    def test_invalid_json_bad_args(self):
        ctx, _, _ = make_ctx()
        r = run_tool_sync(
            run_jewelry_create_ring_shank(ctx, b"not json!")
        )
        assert "error" in r


# ---------------------------------------------------------------------------
# OCC-gated solid tests
# ---------------------------------------------------------------------------

try:
    from kerf_cad_core.occ_helpers import _OCC_AVAILABLE as _OCC
except ImportError:
    _OCC = False

pytestmark_occ = pytest.mark.skipif(
    not _OCC,
    reason="pythonOCC not installed; install with: conda install -c conda-forge pythonocc-core"
)


@pytestmark_occ
class TestRingShankOCC:
    """Structural smoke tests that require pythonOCC.

    These verify that the ring_shank node parameters are geometrically coherent
    when OCCT is present.  Full sweep evaluation lives in the occtWorker JS tests.
    """

    def test_inner_radius_positive(self):
        """Inner radius must be positive — sanity check for sweep origin."""
        d = ring_size_to_diameter("us", 7)
        r = d / 2.0
        assert r > 0, "Inner radius must be positive for a valid sweep circle."

    def test_outer_gt_inner(self):
        """Outer diameter must exceed inner diameter."""
        p = compute_shank_params(7, "us", thickness=1.8)
        assert p["outer_diameter_mm"] > p["inner_diameter_mm"]

    def test_shank_params_valid_for_sweep(self):
        """Verify shank params include all fields the occtWorker expects."""
        p = compute_shank_params(7, "us", band_width=4.0, thickness=1.8,
                                  profile="comfort_fit", shoulder_style="cathedral")
        required_keys = {
            "inner_diameter_mm",
            "outer_diameter_mm",
            "circumference_mm",
            "band_width_mm",
            "thickness_mm",
            "profile",
            "shoulder_style",
            "shoulder_hints",
        }
        missing = required_keys - set(p.keys())
        assert not missing, f"Missing keys in shank params: {missing}"
