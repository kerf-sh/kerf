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
    _VALID_ETERNITY_COVERAGES,
    _VALID_ETERNITY_SETTINGS,
    _VALID_SIGNET_FACE_SHAPES,
    _VALID_STACKING_PROFILES,
    _id_mm_to_circumference,
    _validate_width_profile,
    compute_shank_params,
    compute_eternity_band_params,
    compute_signet_ring_params,
    compute_stacking_band_params,
    compute_contoured_band_params,
    jewelry_create_ring_shank_spec,
    jewelry_ring_size_to_diameter_spec,
    jewelry_create_eternity_band_spec,
    jewelry_create_signet_ring_spec,
    jewelry_create_stacking_band_set_spec,
    jewelry_create_contoured_band_spec,
    ring_diameter_to_size,
    ring_size_to_diameter,
    run_jewelry_create_ring_shank,
    run_jewelry_ring_size_to_diameter,
    run_jewelry_create_eternity_band,
    run_jewelry_create_signet_ring,
    run_jewelry_create_stacking_band_set,
    run_jewelry_create_contoured_band,
    EngravingSpec,
    SizingBeadSpec,
    EternityBandSpec,
    SignetRingSpec,
    StackingBandSpec,
    ContouredBandSpec,
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
# v2 profiles: compute_shank_params
# ---------------------------------------------------------------------------

# Complete set for quick loop tests
_V2_PROFILES = ["cigar_band", "bombe", "concave", "square", "hammered", "split_band"]


class TestV2Profiles:
    """Each new profile must produce a valid spec with correct profile_hints."""

    def test_all_v2_profiles_in_valid_set(self):
        for p in _V2_PROFILES:
            assert p in _VALID_PROFILES, f"{p!r} not in _VALID_PROFILES"

    def test_all_v2_profiles_accepted_by_compute(self):
        for p in _V2_PROFILES:
            r = compute_shank_params(7, "us", profile=p)
            assert r["profile"] == p, f"Profile {p!r} not stored correctly"

    def test_v2_profiles_emit_profile_hints(self):
        for p in _V2_PROFILES:
            r = compute_shank_params(7, "us", profile=p)
            assert "profile_hints" in r, f"{p!r} missing profile_hints"
            assert r["profile_hints"]["type"] == p

    # --- cigar_band ---

    def test_cigar_band_bevel_and_flat(self):
        r = compute_shank_params(7, "us", profile="cigar_band", band_width=6.0)
        h = r["profile_hints"]
        assert h["bevel_width_mm"] > 0
        assert h["flat_top_width_mm"] > 0
        # flat_top + 2 * bevel ≈ band_width
        total = h["flat_top_width_mm"] + 2 * h["bevel_width_mm"]
        assert abs(total - 6.0) < 0.01

    def test_cigar_band_custom_bevel_ratio(self):
        r = compute_shank_params(7, "us", profile="cigar_band", band_width=4.0,
                                  cigar_bevel_ratio=0.3)
        h = r["profile_hints"]
        assert abs(h["bevel_width_mm"] - 4.0 * 0.3) < 0.01

    def test_cigar_band_invalid_bevel_ratio(self):
        with pytest.raises(ValueError, match="cigar_bevel_ratio"):
            compute_shank_params(7, "us", profile="cigar_band", cigar_bevel_ratio=0.5)

    def test_cigar_band_zero_bevel_ratio_raises(self):
        with pytest.raises(ValueError, match="cigar_bevel_ratio"):
            compute_shank_params(7, "us", profile="cigar_band", cigar_bevel_ratio=0.0)

    # --- bombe ---

    def test_bombe_dome_height_positive(self):
        r = compute_shank_params(7, "us", profile="bombe", band_width=5.0)
        h = r["profile_hints"]
        assert h["dome_height_mm"] > 0
        assert h["dome_ratio"] == 0.5

    def test_bombe_custom_dome_ratio(self):
        r = compute_shank_params(7, "us", profile="bombe", band_width=4.0,
                                  bombe_dome_ratio=0.8)
        h = r["profile_hints"]
        assert abs(h["dome_ratio"] - 0.8) < 1e-9

    def test_bombe_zero_dome_ratio_raises(self):
        with pytest.raises(ValueError, match="bombe_dome_ratio"):
            compute_shank_params(7, "us", profile="bombe", bombe_dome_ratio=0.0)

    def test_bombe_over_one_dome_ratio_raises(self):
        with pytest.raises(ValueError, match="bombe_dome_ratio"):
            compute_shank_params(7, "us", profile="bombe", bombe_dome_ratio=1.5)

    # --- concave ---

    def test_concave_channel_dims(self):
        r = compute_shank_params(7, "us", profile="concave",
                                  band_width=5.0, thickness=2.0)
        h = r["profile_hints"]
        assert h["channel_depth_mm"] > 0
        assert h["channel_width_mm"] > 0

    def test_concave_depth_ratio_boundary_raises(self):
        with pytest.raises(ValueError, match="concave_depth_ratio"):
            compute_shank_params(7, "us", profile="concave", concave_depth_ratio=0.5)

    def test_concave_zero_depth_ratio_raises(self):
        with pytest.raises(ValueError, match="concave_depth_ratio"):
            compute_shank_params(7, "us", profile="concave", concave_depth_ratio=0.0)

    # --- square ---

    def test_square_hints_corner_radius_zero(self):
        r = compute_shank_params(7, "us", profile="square")
        h = r["profile_hints"]
        assert h["type"] == "square"
        assert h["corner_radius_mm"] == 0.0

    # --- hammered ---

    def test_hammered_default_32_facets(self):
        r = compute_shank_params(7, "us", profile="hammered")
        h = r["profile_hints"]
        assert h["facet_count"] == 32
        assert abs(h["facet_arc_deg"] - 360.0 / 32) < 0.001

    def test_hammered_custom_facet_count(self):
        r = compute_shank_params(7, "us", profile="hammered",
                                  hammered_facet_count=16)
        assert r["profile_hints"]["facet_count"] == 16

    def test_hammered_facet_count_too_low_raises(self):
        with pytest.raises(ValueError, match="hammered_facet_count"):
            compute_shank_params(7, "us", profile="hammered",
                                  hammered_facet_count=3)

    def test_hammered_facet_count_too_high_raises(self):
        with pytest.raises(ValueError, match="hammered_facet_count"):
            compute_shank_params(7, "us", profile="hammered",
                                  hammered_facet_count=200)

    def test_hammered_facet_arc_deg_formula(self):
        r = compute_shank_params(7, "us", profile="hammered",
                                  hammered_facet_count=12)
        assert abs(r["profile_hints"]["facet_arc_deg"] - 30.0) < 0.001

    # --- split_band ---

    def test_split_band_default_gap(self):
        r = compute_shank_params(7, "us", profile="split_band", band_width=4.0)
        h = r["profile_hints"]
        assert h["type"] == "split_band"
        assert h["gap_mm"] == 1.0
        # each rail = (4.0 - 1.0) / 2 = 1.5
        assert abs(h["rail_width_mm"] - 1.5) < 0.01

    def test_split_band_custom_gap(self):
        r = compute_shank_params(7, "us", profile="split_band",
                                  band_width=5.0, split_band_gap_mm=1.5)
        h = r["profile_hints"]
        assert abs(h["gap_mm"] - 1.5) < 1e-9
        assert abs(h["rail_width_mm"] - (5.0 - 1.5) / 2) < 0.01

    def test_split_band_zero_gap_raises(self):
        with pytest.raises(ValueError, match="split_band_gap_mm"):
            compute_shank_params(7, "us", profile="split_band",
                                  split_band_gap_mm=0.0)

    def test_split_band_gap_too_large_raises(self):
        # gap = band_width − 0.5 − epsilon leaves no room for rails
        with pytest.raises(ValueError, match="split_band_gap_mm"):
            compute_shank_params(7, "us", profile="split_band",
                                  band_width=4.0, split_band_gap_mm=3.6)

    def test_original_profiles_no_profile_hints(self):
        """Original profiles must NOT have profile_hints key."""
        for p in ["d_shape", "comfort_fit", "flat", "half_round",
                   "knife_edge", "euro", "tapered"]:
            r = compute_shank_params(7, "us", profile=p)
            assert "profile_hints" not in r, (
                f"Original profile {p!r} should not emit profile_hints"
            )


# ---------------------------------------------------------------------------
# v2 profiles: LLM tool round-trip
# ---------------------------------------------------------------------------

class TestV2ProfilesTool:
    def _run(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_tool_sync(
            run_jewelry_create_ring_shank(ctx, json.dumps(args).encode())
        )

    def test_all_v2_profiles_accepted_by_tool(self):
        for p in _V2_PROFILES:
            ctx, store, fid = make_ctx()
            r = self._run(ctx, fid, ring_size=7, profile=p)
            assert "error" not in r, f"Tool rejected profile {p!r}: {r}"
            assert r["profile"] == p

    def test_hammered_facet_count_via_tool(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, profile="hammered",
                  hammered_facet_count=16)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["profile_hints"]["facet_count"] == 16

    def test_split_band_gap_via_tool(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, profile="split_band",
                  band_width=5.0, split_band_gap_mm=1.2)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert abs(node["profile_hints"]["gap_mm"] - 1.2) < 1e-9

    def test_bombe_dome_ratio_via_tool(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, profile="bombe", bombe_dome_ratio=0.7)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert abs(node["profile_hints"]["dome_ratio"] - 0.7) < 1e-9

    def test_tool_spec_profile_enum_includes_v2(self):
        props = jewelry_create_ring_shank_spec.input_schema["properties"]
        enum_set = set(props["profile"]["enum"])
        for p in _V2_PROFILES:
            assert p in enum_set, f"{p!r} missing from tool spec enum"

    def test_invalid_v2_param_bad_args(self):
        """hammered_facet_count=3 is out of range → BAD_ARGS from tool."""
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, profile="hammered",
                      hammered_facet_count=3)
        assert "error" in r

    def test_split_band_gap_zero_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, profile="split_band",
                      band_width=4.0, split_band_gap_mm=0.0)
        assert "error" in r


# ---------------------------------------------------------------------------
# EngravingSpec
# ---------------------------------------------------------------------------

class TestEngravingSpec:
    def test_defaults(self):
        e = EngravingSpec(text="Hello")
        d = e.to_dict()
        assert d["text"] == "Hello"
        assert d["font_height_mm"] == 1.5
        assert d["depth_mm"] == 0.3
        assert d["position_deg"] == 180.0
        assert d["align"] == "centre"

    def test_custom_values(self):
        e = EngravingSpec(
            text="Always",
            font_height_mm=2.0,
            depth_mm=0.5,
            position_deg=90.0,
            align="left",
        )
        d = e.to_dict()
        assert d["font_height_mm"] == 2.0
        assert d["align"] == "left"

    def test_empty_text_raises(self):
        e = EngravingSpec(text="")
        with pytest.raises(ValueError, match="non-empty"):
            e.validate()

    def test_whitespace_text_raises(self):
        e = EngravingSpec(text="   ")
        with pytest.raises(ValueError, match="non-empty"):
            e.validate()

    def test_text_too_long_raises(self):
        e = EngravingSpec(text="x" * 201)
        with pytest.raises(ValueError, match="200"):
            e.validate()

    def test_zero_font_height_raises(self):
        e = EngravingSpec(text="Hi", font_height_mm=0.0)
        with pytest.raises(ValueError, match="font_height_mm"):
            e.validate()

    def test_negative_font_height_raises(self):
        e = EngravingSpec(text="Hi", font_height_mm=-1.0)
        with pytest.raises(ValueError, match="font_height_mm"):
            e.validate()

    def test_zero_depth_raises(self):
        e = EngravingSpec(text="Hi", depth_mm=0.0)
        with pytest.raises(ValueError, match="depth_mm"):
            e.validate()

    def test_position_out_of_range_raises(self):
        e = EngravingSpec(text="Hi", position_deg=400.0)
        with pytest.raises(ValueError, match="position_deg"):
            e.validate()

    def test_position_negative_raises(self):
        e = EngravingSpec(text="Hi", position_deg=-10.0)
        with pytest.raises(ValueError, match="position_deg"):
            e.validate()

    def test_invalid_align_raises(self):
        e = EngravingSpec(text="Hi", align="justify")
        with pytest.raises(ValueError, match="align"):
            e.validate()

    def test_engraving_in_shank_params(self):
        e = EngravingSpec(text="Love")
        r = compute_shank_params(7, "us", engraving=e)
        assert "engraving" in r
        assert r["engraving"]["text"] == "Love"

    def test_no_engraving_no_key(self):
        r = compute_shank_params(7, "us")
        assert "engraving" not in r


# ---------------------------------------------------------------------------
# Engraving via LLM tool
# ---------------------------------------------------------------------------

class TestEngravingTool:
    def _run(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_tool_sync(
            run_jewelry_create_ring_shank(ctx, json.dumps(args).encode())
        )

    def test_engraving_stored_in_node(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7,
                  engraving={"text": "Forever", "font_height_mm": 2.0, "depth_mm": 0.4})
        doc = json.loads(store["content"])
        eng = doc["features"][0]["engraving"]
        assert eng["text"] == "Forever"
        assert eng["font_height_mm"] == 2.0
        assert eng["depth_mm"] == 0.4

    def test_engraving_default_position(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, engraving={"text": "Hi"})
        doc = json.loads(store["content"])
        eng = doc["features"][0]["engraving"]
        assert eng["position_deg"] == 180.0
        assert eng["align"] == "centre"

    def test_engraving_missing_text_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7,
                      engraving={"font_height_mm": 1.5})
        assert "error" in r

    def test_engraving_not_an_object_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, engraving="not a dict")
        assert "error" in r

    def test_engraving_zero_depth_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7,
                      engraving={"text": "Hi", "depth_mm": 0.0})
        assert "error" in r

    def test_engraving_invalid_align_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7,
                      engraving={"text": "Hi", "align": "center"})
        assert "error" in r


# ---------------------------------------------------------------------------
# SizingBeadSpec
# ---------------------------------------------------------------------------

class TestSizingBeadSpec:
    def test_defaults(self):
        sb = SizingBeadSpec()
        d = sb.to_dict()
        assert d["count"] == 2
        assert d["bead_diameter_mm"] == 1.0
        assert d["bead_height_mm"] == 0.4
        assert d["position_deg"] == 270.0

    def test_custom_values(self):
        sb = SizingBeadSpec(count=4, bead_diameter_mm=1.2, bead_height_mm=0.35,
                             position_deg=90.0)
        d = sb.to_dict()
        assert d["count"] == 4
        assert d["bead_diameter_mm"] == 1.2

    def test_count_zero_raises(self):
        sb = SizingBeadSpec(count=0)
        with pytest.raises(ValueError, match="count"):
            sb.validate()

    def test_count_too_high_raises(self):
        sb = SizingBeadSpec(count=5)
        with pytest.raises(ValueError, match="count"):
            sb.validate()

    def test_zero_bead_diameter_raises(self):
        sb = SizingBeadSpec(bead_diameter_mm=0.0)
        with pytest.raises(ValueError, match="bead_diameter_mm"):
            sb.validate()

    def test_zero_bead_height_raises(self):
        sb = SizingBeadSpec(bead_height_mm=0.0)
        with pytest.raises(ValueError, match="bead_height_mm"):
            sb.validate()

    def test_position_out_of_range_raises(self):
        sb = SizingBeadSpec(position_deg=400.0)
        with pytest.raises(ValueError, match="position_deg"):
            sb.validate()

    def test_height_exceeds_thickness_quarter_raises(self):
        """bead_height ≥ thickness/4 should raise."""
        sb = SizingBeadSpec(bead_height_mm=1.0)
        with pytest.raises(ValueError, match="perforation"):
            sb.validate(band_thickness_mm=3.0)  # threshold = 0.75

    def test_height_just_under_threshold_ok(self):
        sb = SizingBeadSpec(bead_height_mm=0.74)
        sb.validate(band_thickness_mm=3.0)  # 3.0/4 = 0.75 — just under OK

    def test_sizing_beads_in_shank_params(self):
        sb = SizingBeadSpec(count=2, bead_diameter_mm=1.0, bead_height_mm=0.3)
        r = compute_shank_params(7, "us", thickness=2.0, sizing_beads=sb)
        assert "sizing_beads" in r
        assert r["sizing_beads"]["count"] == 2

    def test_no_sizing_beads_no_key(self):
        r = compute_shank_params(7, "us")
        assert "sizing_beads" not in r


# ---------------------------------------------------------------------------
# Sizing beads via LLM tool
# ---------------------------------------------------------------------------

class TestSizingBeadsTool:
    def _run(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_tool_sync(
            run_jewelry_create_ring_shank(ctx, json.dumps(args).encode())
        )

    def test_sizing_beads_stored(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, thickness=2.0,
                  sizing_beads={"count": 2, "bead_diameter_mm": 1.0, "bead_height_mm": 0.3})
        doc = json.loads(store["content"])
        sb = doc["features"][0]["sizing_beads"]
        assert sb["count"] == 2
        assert sb["bead_diameter_mm"] == 1.0

    def test_sizing_beads_invalid_count_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, thickness=2.0,
                      sizing_beads={"count": 5})
        assert "error" in r

    def test_sizing_beads_not_object_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, sizing_beads="two beads")
        assert "error" in r

    def test_sizing_beads_perforation_bad_args(self):
        """bead_height ≥ thickness/4 must error."""
        ctx, _, fid = make_ctx()
        # thickness=2.0 → limit = 0.5 mm; bead_height=1.0 exceeds it
        r = self._run(ctx, fid, ring_size=7, thickness=2.0,
                      sizing_beads={"count": 2, "bead_height_mm": 1.0})
        assert "error" in r


# ---------------------------------------------------------------------------
# Sizing/fit features: comfort_fit_radius, finger_fit_taper, width_profile
# ---------------------------------------------------------------------------

class TestSizingFitFeatures:
    # --- comfort_fit_radius ---

    def test_comfort_fit_radius_stored(self):
        r = compute_shank_params(7, "us", comfort_fit_radius=4.5)
        assert "comfort_fit_radius_mm" in r
        assert r["comfort_fit_radius_mm"] == 4.5

    def test_comfort_fit_radius_not_set_no_key(self):
        r = compute_shank_params(7, "us")
        assert "comfort_fit_radius_mm" not in r

    def test_comfort_fit_radius_zero_raises(self):
        with pytest.raises(ValueError, match="comfort_fit_radius"):
            compute_shank_params(7, "us", comfort_fit_radius=0.0)

    def test_comfort_fit_radius_negative_raises(self):
        with pytest.raises(ValueError, match="comfort_fit_radius"):
            compute_shank_params(7, "us", comfort_fit_radius=-1.0)

    # --- finger_fit_taper ---

    def test_finger_fit_taper_stored(self):
        r = compute_shank_params(7, "us", finger_fit_taper=5.0)
        assert "finger_fit_taper_deg" in r
        assert r["finger_fit_taper_deg"] == 5.0

    def test_finger_fit_taper_zero_not_stored(self):
        """Zero taper (default) should not add the key."""
        r = compute_shank_params(7, "us", finger_fit_taper=0.0)
        assert "finger_fit_taper_deg" not in r

    def test_finger_fit_taper_at_limit(self):
        r = compute_shank_params(7, "us", finger_fit_taper=15.0)
        assert r["finger_fit_taper_deg"] == 15.0

    def test_finger_fit_taper_over_limit_raises(self):
        with pytest.raises(ValueError, match="finger_fit_taper"):
            compute_shank_params(7, "us", finger_fit_taper=16.0)

    def test_finger_fit_taper_negative_raises(self):
        with pytest.raises(ValueError, match="finger_fit_taper"):
            compute_shank_params(7, "us", finger_fit_taper=-1.0)

    # --- width_profile ---

    def test_width_profile_stored(self):
        r = compute_shank_params(7, "us", width_profile=[1.0, 0.85, 0.7])
        assert "width_profile" in r
        assert r["width_profile"] == [1.0, 0.85, 0.7]

    def test_width_profile_not_set_no_key(self):
        r = compute_shank_params(7, "us")
        assert "width_profile" not in r

    def test_width_profile_two_points_min(self):
        r = compute_shank_params(7, "us", width_profile=[1.0, 0.6])
        assert len(r["width_profile"]) == 2

    def test_width_profile_ten_points_max(self):
        curve = [1.0, 0.95, 0.9, 0.85, 0.8, 0.75, 0.7, 0.65, 0.6, 0.55]
        r = compute_shank_params(7, "us", width_profile=curve)
        assert len(r["width_profile"]) == 10

    def test_width_profile_too_few_raises(self):
        with pytest.raises(ValueError, match="2–10"):
            compute_shank_params(7, "us", width_profile=[1.0])

    def test_width_profile_too_many_raises(self):
        with pytest.raises(ValueError, match="2–10"):
            compute_shank_params(7, "us", width_profile=[1.0] * 11)

    def test_width_profile_value_zero_raises(self):
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            compute_shank_params(7, "us", width_profile=[0.0, 0.8])

    def test_width_profile_value_over_one_raises(self):
        with pytest.raises(ValueError, match=r"\(0, 1\]"):
            compute_shank_params(7, "us", width_profile=[1.0, 1.1])

    def test_width_profile_non_numeric_raises(self):
        with pytest.raises(ValueError, match="must be a number"):
            compute_shank_params(7, "us", width_profile=[1.0, "x"])

    def test_width_profile_not_a_list_raises(self):
        with pytest.raises(ValueError, match="2–10"):
            compute_shank_params(7, "us", width_profile="not-a-list")


# ---------------------------------------------------------------------------
# _validate_width_profile (unit tests on the helper)
# ---------------------------------------------------------------------------

class TestValidateWidthProfile:
    def test_valid_curve(self):
        result = _validate_width_profile([1.0, 0.8, 0.6])
        assert result == [1.0, 0.8, 0.6]

    def test_coerces_to_float(self):
        result = _validate_width_profile([1, 1])  # ints
        assert all(isinstance(v, float) for v in result)

    def test_at_max_boundary_passes(self):
        _validate_width_profile([1.0, 1.0])  # exactly 1.0 is valid

    def test_over_max_raises(self):
        with pytest.raises(ValueError):
            _validate_width_profile([1.0, 1.001])

    def test_at_min_boundary_raises(self):
        with pytest.raises(ValueError):
            _validate_width_profile([0.0, 1.0])  # 0.0 not valid (must be > 0)

    def test_empty_list_raises(self):
        with pytest.raises(ValueError):
            _validate_width_profile([])

    def test_single_item_raises(self):
        with pytest.raises(ValueError):
            _validate_width_profile([1.0])


# ---------------------------------------------------------------------------
# Sizing/fit features via LLM tool
# ---------------------------------------------------------------------------

class TestSizingFitTool:
    def _run(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_tool_sync(
            run_jewelry_create_ring_shank(ctx, json.dumps(args).encode())
        )

    def test_comfort_fit_radius_stored(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, comfort_fit_radius=4.5)
        doc = json.loads(store["content"])
        assert doc["features"][0]["comfort_fit_radius_mm"] == 4.5

    def test_comfort_fit_radius_zero_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, comfort_fit_radius=0.0)
        assert "error" in r

    def test_finger_fit_taper_stored(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, finger_fit_taper=7.5)
        doc = json.loads(store["content"])
        assert doc["features"][0]["finger_fit_taper_deg"] == 7.5

    def test_finger_fit_taper_over_limit_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, finger_fit_taper=20.0)
        assert "error" in r

    def test_width_profile_stored(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, width_profile=[1.0, 0.8, 0.6])
        doc = json.loads(store["content"])
        assert doc["features"][0]["width_profile"] == [1.0, 0.8, 0.6]

    def test_width_profile_bad_values_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, width_profile=[0.0, 0.8])
        assert "error" in r

    def test_width_profile_too_few_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, width_profile=[1.0])
        assert "error" in r

    def test_all_v2_fit_features_combined(self):
        """Combined call with engraving + sizing_beads + width_profile."""
        ctx, store, fid = make_ctx()
        r = self._run(
            ctx, fid,
            ring_size=7, system="us",
            band_width=5.0, thickness=2.0,
            profile="hammered", hammered_facet_count=24,
            shoulder_style="cathedral",
            engraving={"text": "Forever", "depth_mm": 0.3},
            sizing_beads={"count": 2, "bead_height_mm": 0.3},
            comfort_fit_radius=4.0,
            finger_fit_taper=3.0,
            width_profile=[1.0, 0.9, 0.8],
        )
        assert "error" not in r, f"Combined call failed: {r}"
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["engraving"]["text"] == "Forever"
        assert node["sizing_beads"]["count"] == 2
        assert node["comfort_fit_radius_mm"] == 4.0
        assert node["finger_fit_taper_deg"] == 3.0
        assert node["width_profile"] == [1.0, 0.9, 0.8]
        assert node["profile_hints"]["facet_count"] == 24


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


# ===========================================================================
# v3 Eternity Band
# ===========================================================================

class TestEternityBandSpec:
    """Unit tests for EternityBandSpec dataclass."""

    def test_defaults_valid(self):
        spec = EternityBandSpec(ring_size=7)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["coverage"] == "full"
        assert d["coverage_deg"] == 360.0
        assert d["setting_style"] == "channel"
        assert d["stone_diameter_mm"] == 2.0
        assert d["stone_count_auto"] is True

    def test_auto_stone_count_full(self):
        """Full coverage: stone count ≈ circumference / pitch."""
        id_mm = ring_size_to_diameter("us", 7)
        spec = EternityBandSpec(ring_size=7, stone_diameter_mm=2.0, stone_spacing_mm=0.1)
        count = spec.auto_stone_count(id_mm)
        pitch = 2.0 + 0.1
        arc_length = _PI * id_mm
        expected = max(1, round(arc_length / pitch))
        assert count == expected

    def test_auto_stone_count_half(self):
        """Half coverage arc is π × r (half of full circle)."""
        id_mm = ring_size_to_diameter("us", 7)
        spec = EternityBandSpec(ring_size=7, stone_diameter_mm=2.0,
                                coverage="half", stone_spacing_mm=0.0)
        full_spec = EternityBandSpec(ring_size=7, stone_diameter_mm=2.0,
                                     coverage="full", stone_spacing_mm=0.0)
        half_count = spec.auto_stone_count(id_mm)
        full_count = full_spec.auto_stone_count(id_mm)
        # half coverage should give roughly half as many stones
        assert half_count <= full_count

    def test_auto_stone_count_three_quarter(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = EternityBandSpec(ring_size=7, stone_diameter_mm=2.0,
                                coverage="three_quarter", stone_spacing_mm=0.1)
        count = spec.auto_stone_count(id_mm)
        pitch = 2.1
        arc_length = _PI * id_mm * 0.75
        expected = max(1, round(arc_length / pitch))
        assert count == expected

    def test_explicit_stone_count_stored(self):
        spec = EternityBandSpec(ring_size=7, stone_diameter_mm=2.0, stone_count=18)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["stone_count"] == 18
        assert d["stone_count_auto"] is False

    def test_band_width_auto_from_stone_diameter(self):
        """Default band_width = stone_diameter + 0.6."""
        spec = EternityBandSpec(ring_size=7, stone_diameter_mm=2.5)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert abs(d["band_width_mm"] - (2.5 + 0.6)) < 0.01

    def test_band_width_explicit(self):
        spec = EternityBandSpec(ring_size=7, stone_diameter_mm=2.0, band_width_mm=5.0)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["band_width_mm"] == 5.0

    def test_invalid_stone_diameter_raises(self):
        spec = EternityBandSpec(ring_size=7, stone_diameter_mm=0.0)
        with pytest.raises(ValueError, match="stone_diameter_mm"):
            spec.validate(ring_size_to_diameter("us", 7))

    def test_invalid_coverage_raises(self):
        spec = EternityBandSpec(ring_size=7, coverage="quarter")
        with pytest.raises(ValueError, match="coverage"):
            spec.validate(ring_size_to_diameter("us", 7))

    def test_invalid_setting_style_raises(self):
        spec = EternityBandSpec(ring_size=7, setting_style="bezel")
        with pytest.raises(ValueError, match="setting_style"):
            spec.validate(ring_size_to_diameter("us", 7))

    def test_band_width_less_than_stone_raises(self):
        spec = EternityBandSpec(ring_size=7, stone_diameter_mm=3.0, band_width_mm=2.0)
        with pytest.raises(ValueError, match="band_width_mm"):
            spec.validate(ring_size_to_diameter("us", 7))

    def test_zero_thickness_raises(self):
        spec = EternityBandSpec(ring_size=7, thickness_mm=0.0)
        with pytest.raises(ValueError, match="thickness_mm"):
            spec.validate(ring_size_to_diameter("us", 7))

    def test_negative_spacing_raises(self):
        spec = EternityBandSpec(ring_size=7, stone_spacing_mm=-0.1)
        with pytest.raises(ValueError, match="stone_spacing_mm"):
            spec.validate(ring_size_to_diameter("us", 7))

    def test_stone_count_zero_raises(self):
        spec = EternityBandSpec(ring_size=7, stone_count=0)
        with pytest.raises(ValueError, match="stone_count"):
            spec.validate(ring_size_to_diameter("us", 7))

    def test_arc_length_in_dict(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = EternityBandSpec(ring_size=7, coverage="half")
        d = spec.to_dict(id_mm)
        expected_arc = _PI * id_mm * 0.5
        assert abs(d["arc_length_mm"] - expected_arc) < 0.01

    def test_all_coverages_valid(self):
        id_mm = ring_size_to_diameter("us", 7)
        for cov in _VALID_ETERNITY_COVERAGES:
            spec = EternityBandSpec(ring_size=7, coverage=cov)
            d = spec.to_dict(id_mm)
            assert d["coverage"] == cov

    def test_all_setting_styles_valid(self):
        id_mm = ring_size_to_diameter("us", 7)
        for ss in _VALID_ETERNITY_SETTINGS:
            spec = EternityBandSpec(ring_size=7, setting_style=ss)
            d = spec.to_dict(id_mm)
            assert d["setting_style"] == ss


class TestComputeEternityBandParams:
    def test_basic_us7_full(self):
        p = compute_eternity_band_params(7, "us")
        assert abs(p["inner_diameter_mm"] - 17.32) < 0.01
        assert p["coverage"] == "full"
        assert p["stone_count"] >= 1
        assert p["stone_count_auto"] is True

    def test_explicit_stone_count(self):
        p = compute_eternity_band_params(7, "us", stone_count=20)
        assert p["stone_count"] == 20
        assert p["stone_count_auto"] is False

    def test_outer_diameter_formula(self):
        p = compute_eternity_band_params(7, "us", thickness_mm=1.2)
        assert abs(p["outer_diameter_mm"] - (p["inner_diameter_mm"] + 2 * 1.2)) < 0.001

    def test_circumference_formula(self):
        p = compute_eternity_band_params(7, "us")
        assert abs(p["circumference_mm"] - _PI * p["inner_diameter_mm"]) < 1e-3

    def test_uk_size(self):
        p = compute_eternity_band_params("N", "uk")
        assert p["inner_diameter_mm"] > 0

    def test_invalid_coverage_raises(self):
        with pytest.raises(ValueError, match="coverage"):
            compute_eternity_band_params(7, "us", coverage="none")

    def test_invalid_setting_style_raises(self):
        with pytest.raises(ValueError, match="setting_style"):
            compute_eternity_band_params(7, "us", setting_style="bar")

    def test_pave_setting_stored(self):
        p = compute_eternity_band_params(7, "us", setting_style="pave")
        assert p["setting_style"] == "pave"

    def test_size_system_stored(self):
        p = compute_eternity_band_params(7, "us")
        assert p["size_system"] == "us"
        assert p["ring_size"] == 7

    def test_stone_pitch_is_diam_plus_spacing(self):
        p = compute_eternity_band_params(7, "us", stone_diameter_mm=2.0,
                                          stone_spacing_mm=0.2)
        assert abs(p["stone_pitch_mm"] - 2.2) < 0.001


class TestEternityBandTool:
    def _run(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_tool_sync(
            run_jewelry_create_eternity_band(ctx, json.dumps(args).encode())
        )

    def test_basic_accepted(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7)
        assert "error" not in r, f"Unexpected error: {r}"
        assert r["op"] == "eternity_band"
        doc = json.loads(store["content"])
        assert doc["features"][0]["op"] == "eternity_band"

    def test_node_id_generated(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7)
        assert r["id"].startswith("eternity_band-")

    def test_explicit_node_id(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, id="eter-custom")
        assert r["id"] == "eter-custom"

    def test_all_coverages_accepted(self):
        for cov in _VALID_ETERNITY_COVERAGES:
            ctx, store, fid = make_ctx()
            r = self._run(ctx, fid, ring_size=7, coverage=cov)
            assert "error" not in r, f"Coverage {cov!r}: {r}"

    def test_all_setting_styles_accepted(self):
        for ss in _VALID_ETERNITY_SETTINGS:
            ctx, store, fid = make_ctx()
            r = self._run(ctx, fid, ring_size=7, setting_style=ss)
            assert "error" not in r, f"Setting {ss!r}: {r}"

    def test_explicit_stone_count_stored(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, stone_count=15)
        doc = json.loads(store["content"])
        assert doc["features"][0]["stone_count"] == 15

    def test_auto_stone_count_positive(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7)
        assert r["stone_count"] >= 1

    def test_invalid_coverage_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, coverage="quarter")
        assert "error" in r

    def test_invalid_setting_style_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, setting_style="bezel")
        assert "error" in r

    def test_missing_file_id_bad_args(self):
        ctx, _, _ = make_ctx()
        r = run_tool_sync(
            run_jewelry_create_eternity_band(
                ctx, json.dumps({"ring_size": 7}).encode()
            )
        )
        assert "error" in r

    def test_missing_ring_size_bad_args(self):
        ctx, _, fid = make_ctx()
        r = run_tool_sync(
            run_jewelry_create_eternity_band(
                ctx, json.dumps({"file_id": str(fid)}).encode()
            )
        )
        assert "error" in r

    def test_invalid_file_id_bad_args(self):
        ctx, _, _ = make_ctx()
        r = run_tool_sync(
            run_jewelry_create_eternity_band(
                ctx, json.dumps({"file_id": "not-uuid", "ring_size": 7}).encode()
            )
        )
        assert "error" in r

    def test_non_feature_file_not_found(self):
        ctx, store, fid = make_ctx()
        store["kind"] = "sketch"
        r = self._run(ctx, fid, ring_size=7)
        assert "error" in r

    def test_band_width_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, stone_diameter_mm=2.0)
        assert r["band_width_mm"] >= 2.0

    def test_second_node_increments_id(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7)
        r2 = self._run(ctx, fid, ring_size=8)
        assert r2["id"] == "eternity_band-2"

    def test_spec_required_fields(self):
        req = set(jewelry_create_eternity_band_spec.input_schema["required"])
        assert "file_id" in req
        assert "ring_size" in req

    def test_spec_coverage_enum(self):
        props = jewelry_create_eternity_band_spec.input_schema["properties"]
        assert set(props["coverage"]["enum"]) == _VALID_ETERNITY_COVERAGES

    def test_spec_setting_style_enum(self):
        props = jewelry_create_eternity_band_spec.input_schema["properties"]
        assert set(props["setting_style"]["enum"]) == _VALID_ETERNITY_SETTINGS

    def test_stone_count_math_correct_full(self):
        """Full-coverage stone count must equal auto_stone_count result."""
        id_mm = ring_size_to_diameter("us", 7)
        spec = EternityBandSpec(ring_size=7, stone_diameter_mm=2.0, stone_spacing_mm=0.1)
        expected = spec.auto_stone_count(id_mm)
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, stone_diameter_mm=2.0, stone_spacing_mm=0.1)
        assert r["stone_count"] == expected


# ===========================================================================
# v3 Signet Ring
# ===========================================================================

class TestSignetRingSpec:
    def test_defaults_valid(self):
        spec = SignetRingSpec(ring_size=7)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["face_shape"] == "oval"
        assert d["face_length_mm"] == 12.0
        assert d["face_width_mm"] == 10.0
        assert d["face_height_mm"] == 3.0
        assert d["intaglio_depth_mm"] == 0.0
        assert "engraving" not in d

    def test_all_face_shapes_valid(self):
        id_mm = ring_size_to_diameter("us", 7)
        for shape in _VALID_SIGNET_FACE_SHAPES:
            spec = SignetRingSpec(ring_size=7, face_shape=shape)
            d = spec.to_dict(id_mm)
            assert d["face_shape"] == shape

    def test_face_area_flat(self):
        spec = SignetRingSpec(ring_size=7, face_shape="flat",
                              face_length_mm=10.0, face_width_mm=8.0)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert abs(d["face_area_mm2"] - 80.0) < 0.01

    def test_face_area_oval(self):
        spec = SignetRingSpec(ring_size=7, face_shape="oval",
                              face_length_mm=10.0, face_width_mm=8.0)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        expected = _PI * 5.0 * 4.0
        assert abs(d["face_area_mm2"] - expected) < 0.01

    def test_face_area_cushion(self):
        spec = SignetRingSpec(ring_size=7, face_shape="cushion",
                              face_length_mm=10.0, face_width_mm=8.0)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        expected = 10.0 * 8.0 * 0.9
        assert abs(d["face_area_mm2"] - expected) < 0.01

    def test_intaglio_depth_stored(self):
        spec = SignetRingSpec(ring_size=7, intaglio_depth_mm=0.5, face_height_mm=3.0)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["intaglio_depth_mm"] == 0.5

    def test_engraving_stored(self):
        eng = EngravingSpec(text="WM")
        spec = SignetRingSpec(ring_size=7, engraving=eng)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert "engraving" in d
        assert d["engraving"]["text"] == "WM"

    def test_invalid_face_shape_raises(self):
        spec = SignetRingSpec(ring_size=7, face_shape="round")
        with pytest.raises(ValueError, match="face_shape"):
            spec.validate()

    def test_zero_face_length_raises(self):
        spec = SignetRingSpec(ring_size=7, face_length_mm=0.0)
        with pytest.raises(ValueError, match="face_length_mm"):
            spec.validate()

    def test_zero_face_width_raises(self):
        spec = SignetRingSpec(ring_size=7, face_width_mm=0.0)
        with pytest.raises(ValueError, match="face_width_mm"):
            spec.validate()

    def test_zero_face_height_raises(self):
        spec = SignetRingSpec(ring_size=7, face_height_mm=0.0)
        with pytest.raises(ValueError, match="face_height_mm"):
            spec.validate()

    def test_negative_intaglio_raises(self):
        spec = SignetRingSpec(ring_size=7, intaglio_depth_mm=-0.1)
        with pytest.raises(ValueError, match="intaglio_depth_mm"):
            spec.validate()

    def test_intaglio_exceeds_height_raises(self):
        spec = SignetRingSpec(ring_size=7, intaglio_depth_mm=3.0, face_height_mm=3.0)
        with pytest.raises(ValueError, match="intaglio_depth_mm"):
            spec.validate()

    def test_invalid_shoulder_style_raises(self):
        spec = SignetRingSpec(ring_size=7, shoulder_style="prong")
        with pytest.raises(ValueError, match="shoulder_style"):
            spec.validate()

    def test_shoulder_hints_in_compute(self):
        p = compute_signet_ring_params(7, "us", shoulder_style="cathedral")
        assert "shoulder_hints" in p
        assert p["shoulder_hints"]["type"] == "cathedral"


class TestComputeSignetRingParams:
    def test_basic_us7(self):
        p = compute_signet_ring_params(7, "us")
        assert abs(p["inner_diameter_mm"] - 17.32) < 0.01
        assert p["face_shape"] == "oval"

    def test_outer_diameter(self):
        p = compute_signet_ring_params(7, "us", thickness_mm=1.8)
        assert abs(p["outer_diameter_mm"] - (p["inner_diameter_mm"] + 2 * 1.8)) < 0.001

    def test_face_dims_stored(self):
        p = compute_signet_ring_params(7, "us", face_length_mm=14.0, face_width_mm=12.0,
                                       face_height_mm=4.0)
        assert p["face_length_mm"] == 14.0
        assert p["face_width_mm"] == 12.0
        assert p["face_height_mm"] == 4.0

    def test_all_face_shapes_accepted(self):
        for shape in _VALID_SIGNET_FACE_SHAPES:
            p = compute_signet_ring_params(7, "us", face_shape=shape)
            assert p["face_shape"] == shape

    def test_all_shoulder_styles_accepted(self):
        for ss in _VALID_SHOULDER_STYLES:
            p = compute_signet_ring_params(7, "us", shoulder_style=ss)
            assert p["shoulder_hints"]["type"] == ss

    def test_intaglio_stored(self):
        p = compute_signet_ring_params(7, "us", intaglio_depth_mm=0.8, face_height_mm=3.0)
        assert p["intaglio_depth_mm"] == 0.8

    def test_size_system_stored(self):
        p = compute_signet_ring_params(7, "us")
        assert p["size_system"] == "us"


class TestSignetRingTool:
    def _run(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_tool_sync(
            run_jewelry_create_signet_ring(ctx, json.dumps(args).encode())
        )

    def test_basic_accepted(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7)
        assert "error" not in r, f"Unexpected error: {r}"
        assert r["op"] == "signet_ring"

    def test_node_id_generated(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7)
        assert r["id"].startswith("signet_ring-")

    def test_all_face_shapes_accepted(self):
        for shape in _VALID_SIGNET_FACE_SHAPES:
            ctx, store, fid = make_ctx()
            r = self._run(ctx, fid, ring_size=7, face_shape=shape)
            assert "error" not in r, f"Face shape {shape!r}: {r}"

    def test_engraving_stored(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, engraving={"text": "WM", "depth_mm": 0.3})
        doc = json.loads(store["content"])
        assert doc["features"][0]["engraving"]["text"] == "WM"

    def test_intaglio_depth_stored(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, intaglio_depth_mm=0.5, face_height_mm=4.0)
        doc = json.loads(store["content"])
        assert doc["features"][0]["intaglio_depth_mm"] == 0.5

    def test_invalid_face_shape_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, face_shape="round")
        assert "error" in r

    def test_invalid_shoulder_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, shoulder_style="prong")
        assert "error" in r

    def test_intaglio_exceeds_height_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, intaglio_depth_mm=5.0, face_height_mm=3.0)
        assert "error" in r

    def test_missing_ring_size_bad_args(self):
        ctx, _, fid = make_ctx()
        r = run_tool_sync(
            run_jewelry_create_signet_ring(
                ctx, json.dumps({"file_id": str(fid)}).encode()
            )
        )
        assert "error" in r

    def test_non_feature_file_not_found(self):
        ctx, store, fid = make_ctx()
        store["kind"] = "sketch"
        r = self._run(ctx, fid, ring_size=7)
        assert "error" in r

    def test_spec_required_fields(self):
        req = set(jewelry_create_signet_ring_spec.input_schema["required"])
        assert "file_id" in req
        assert "ring_size" in req

    def test_spec_face_shape_enum(self):
        props = jewelry_create_signet_ring_spec.input_schema["properties"]
        assert set(props["face_shape"]["enum"]) == _VALID_SIGNET_FACE_SHAPES

    def test_node_contains_face_dims(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, face_length_mm=14.0, face_width_mm=11.0,
                  face_height_mm=4.0)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["face_length_mm"] == 14.0
        assert node["face_width_mm"] == 11.0
        assert node["face_height_mm"] == 4.0


# ===========================================================================
# v3 Stacking Band Set
# ===========================================================================

class TestStackingBandSpec:
    def test_defaults_valid(self):
        spec = StackingBandSpec(ring_size=7)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["band_count"] == 3
        assert d["band_width_mm"] == 2.0
        assert d["thickness_mm"] == 1.4
        assert d["profile"] == "flat"
        assert d["include_wishbone"] is False

    def test_band_list_length(self):
        spec = StackingBandSpec(ring_size=7, band_count=4)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert len(d["bands"]) == 4

    def test_band_offsets_correct(self):
        """Each band offset = index × (band_width + gap)."""
        spec = StackingBandSpec(ring_size=7, band_count=3,
                                band_width_mm=2.0, nest_gap_mm=0.2)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        pitch = 2.2
        for i, b in enumerate(d["bands"]):
            assert abs(b["offset_mm"] - i * pitch) < 0.001

    def test_total_span_formula(self):
        spec = StackingBandSpec(ring_size=7, band_count=3,
                                band_width_mm=2.0, nest_gap_mm=0.1)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        expected = 2.1 * 3 - 0.1
        assert abs(d["total_span_mm"] - expected) < 0.001

    def test_wishbone_stored(self):
        spec = StackingBandSpec(ring_size=7, include_wishbone=True,
                                wishbone_notch_depth_mm=0.9, thickness_mm=1.8)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["include_wishbone"] is True
        assert d["wishbone_notch_depth_mm"] == 0.9

    def test_wishbone_not_set_no_key(self):
        spec = StackingBandSpec(ring_size=7)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert "wishbone_notch_depth_mm" not in d

    def test_solitaire_node_id_stored(self):
        spec = StackingBandSpec(ring_size=7, solitaire_node_id="ring_shank-1")
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["solitaire_node_id"] == "ring_shank-1"

    def test_per_band_profiles_stored(self):
        profiles = ["flat", "half_round", "knife_edge"]
        spec = StackingBandSpec(ring_size=7, band_count=3, per_band_profiles=profiles)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["per_band_profiles"] == profiles
        for i, b in enumerate(d["bands"]):
            assert b["profile"] == profiles[i]

    def test_invalid_band_count_zero_raises(self):
        spec = StackingBandSpec(ring_size=7, band_count=0)
        with pytest.raises(ValueError, match="band_count"):
            spec.validate()

    def test_invalid_band_count_over_raises(self):
        spec = StackingBandSpec(ring_size=7, band_count=9)
        with pytest.raises(ValueError, match="band_count"):
            spec.validate()

    def test_zero_band_width_raises(self):
        spec = StackingBandSpec(ring_size=7, band_width_mm=0.0)
        with pytest.raises(ValueError, match="band_width_mm"):
            spec.validate()

    def test_zero_thickness_raises(self):
        spec = StackingBandSpec(ring_size=7, thickness_mm=0.0)
        with pytest.raises(ValueError, match="thickness_mm"):
            spec.validate()

    def test_invalid_profile_raises(self):
        spec = StackingBandSpec(ring_size=7, profile="bombe")
        with pytest.raises(ValueError, match="profile"):
            spec.validate()

    def test_negative_gap_raises(self):
        spec = StackingBandSpec(ring_size=7, nest_gap_mm=-0.1)
        with pytest.raises(ValueError, match="nest_gap_mm"):
            spec.validate()

    def test_wishbone_zero_notch_depth_raises(self):
        spec = StackingBandSpec(ring_size=7, include_wishbone=True,
                                wishbone_notch_depth_mm=0.0)
        with pytest.raises(ValueError, match="wishbone_notch_depth_mm"):
            spec.validate()

    def test_wishbone_notch_exceeds_thickness_raises(self):
        spec = StackingBandSpec(ring_size=7, include_wishbone=True,
                                thickness_mm=1.4, wishbone_notch_depth_mm=1.5)
        with pytest.raises(ValueError, match="wishbone_notch_depth_mm"):
            spec.validate()

    def test_per_band_profiles_wrong_length_raises(self):
        spec = StackingBandSpec(ring_size=7, band_count=3,
                                per_band_profiles=["flat", "half_round"])
        with pytest.raises(ValueError, match="per_band_profiles"):
            spec.validate()

    def test_per_band_profiles_invalid_profile_raises(self):
        spec = StackingBandSpec(ring_size=7, band_count=2,
                                per_band_profiles=["flat", "bombe"])
        with pytest.raises(ValueError, match="per_band_profiles"):
            spec.validate()

    def test_all_valid_profiles_accepted(self):
        id_mm = ring_size_to_diameter("us", 7)
        for p in _VALID_STACKING_PROFILES:
            spec = StackingBandSpec(ring_size=7, profile=p)
            d = spec.to_dict(id_mm)
            assert d["profile"] == p


class TestComputeStackingBandParams:
    def test_basic_us7(self):
        p = compute_stacking_band_params(7, "us")
        assert abs(p["inner_diameter_mm"] - 17.32) < 0.01
        assert p["band_count"] == 3

    def test_band_count_stored(self):
        p = compute_stacking_band_params(7, "us", band_count=5)
        assert p["band_count"] == 5
        assert len(p["bands"]) == 5

    def test_total_span_correct(self):
        p = compute_stacking_band_params(7, "us", band_count=3,
                                          band_width_mm=2.0, nest_gap_mm=0.1)
        expected = 2.1 * 3 - 0.1
        assert abs(p["total_span_mm"] - expected) < 0.001

    def test_wishbone_included(self):
        p = compute_stacking_band_params(7, "us", include_wishbone=True,
                                          thickness_mm=1.8,
                                          wishbone_notch_depth_mm=0.8)
        assert p["include_wishbone"] is True
        assert p["wishbone_notch_depth_mm"] == 0.8

    def test_outer_diameter(self):
        p = compute_stacking_band_params(7, "us", thickness_mm=1.4)
        assert abs(p["outer_diameter_mm"] - (p["inner_diameter_mm"] + 2 * 1.4)) < 0.001

    def test_size_system_stored(self):
        p = compute_stacking_band_params(7, "us")
        assert p["size_system"] == "us"


class TestStackingBandTool:
    def _run(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_tool_sync(
            run_jewelry_create_stacking_band_set(ctx, json.dumps(args).encode())
        )

    def test_basic_accepted(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7)
        assert "error" not in r, f"Unexpected error: {r}"
        assert r["op"] == "stacking_band_set"

    def test_node_id_generated(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7)
        assert r["id"].startswith("stacking_band_set-")

    def test_band_count_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, band_count=5)
        assert r["band_count"] == 5

    def test_total_span_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, band_count=3,
                      band_width_mm=2.0, nest_gap_mm=0.1)
        expected = 2.1 * 3 - 0.1
        assert abs(r["total_span_mm"] - expected) < 0.001

    def test_wishbone_stored(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, include_wishbone=True,
                  thickness_mm=1.8, wishbone_notch_depth_mm=0.8)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["include_wishbone"] is True
        assert node["wishbone_notch_depth_mm"] == 0.8

    def test_solitaire_node_id_stored(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, solitaire_node_id="ring_shank-1")
        doc = json.loads(store["content"])
        assert doc["features"][0]["solitaire_node_id"] == "ring_shank-1"

    def test_invalid_profile_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, profile="bombe")
        assert "error" in r

    def test_band_count_over_limit_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, band_count=9)
        assert "error" in r

    def test_band_count_zero_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, band_count=0)
        assert "error" in r

    def test_missing_ring_size_bad_args(self):
        ctx, _, fid = make_ctx()
        r = run_tool_sync(
            run_jewelry_create_stacking_band_set(
                ctx, json.dumps({"file_id": str(fid)}).encode()
            )
        )
        assert "error" in r

    def test_non_feature_file_not_found(self):
        ctx, store, fid = make_ctx()
        store["kind"] = "sketch"
        r = self._run(ctx, fid, ring_size=7)
        assert "error" in r

    def test_spec_required_fields(self):
        req = set(jewelry_create_stacking_band_set_spec.input_schema["required"])
        assert "file_id" in req
        assert "ring_size" in req

    def test_spec_profile_enum_subset_valid(self):
        props = jewelry_create_stacking_band_set_spec.input_schema["properties"]
        enum_set = set(props["profile"]["enum"])
        assert enum_set == _VALID_STACKING_PROFILES

    def test_all_valid_profiles_accepted_by_tool(self):
        for p in _VALID_STACKING_PROFILES:
            ctx, store, fid = make_ctx()
            r = self._run(ctx, fid, ring_size=7, profile=p)
            assert "error" not in r, f"Profile {p!r}: {r}"

    def test_bands_array_in_node(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, band_count=4)
        doc = json.loads(store["content"])
        bands = doc["features"][0]["bands"]
        assert len(bands) == 4
        for i, b in enumerate(bands):
            assert b["index"] == i


# ===========================================================================
# v3 Contoured Band
# ===========================================================================

class TestContouredBandSpec:
    def test_defaults_valid(self):
        spec = ContouredBandSpec(ring_size=7)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["notch_depth_mm"] == 1.2
        assert d["notch_width_mm"] == 3.0
        assert d["match_radius_mm"] == 10.5
        assert d["contour_style"] == "curved"
        assert d["profile"] == "flat"

    def test_contour_hints_in_dict(self):
        spec = ContouredBandSpec(ring_size=7)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        ch = d["contour_hints"]
        assert ch["type"] == "curved"
        assert ch["notch_depth_mm"] == 1.2
        assert ch["match_radius_mm"] == 10.5
        assert ch["notch_half_angle_deg"] > 0

    def test_notch_half_angle_formula(self):
        """notch_half_angle_deg = asin(notch_width/2 / match_radius)."""
        notch_width = 4.0
        match_radius = 10.5
        spec = ContouredBandSpec(ring_size=7, notch_width_mm=notch_width,
                                 match_radius_mm=match_radius,
                                 band_width_mm=5.0)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        expected = math.degrees(math.asin(notch_width / 2.0 / match_radius))
        assert abs(d["contour_hints"]["notch_half_angle_deg"] - expected) < 0.001

    def test_notched_style(self):
        spec = ContouredBandSpec(ring_size=7, contour_style="notched")
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["contour_style"] == "notched"
        assert d["contour_hints"]["type"] == "notched"

    def test_engagement_ring_node_id_stored(self):
        spec = ContouredBandSpec(ring_size=7, engagement_ring_node_id="ring_shank-1")
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert d["engagement_ring_node_id"] == "ring_shank-1"

    def test_no_engagement_node_no_key(self):
        spec = ContouredBandSpec(ring_size=7)
        id_mm = ring_size_to_diameter("us", 7)
        d = spec.to_dict(id_mm)
        assert "engagement_ring_node_id" not in d

    def test_zero_notch_depth_raises(self):
        spec = ContouredBandSpec(ring_size=7, notch_depth_mm=0.0)
        with pytest.raises(ValueError, match="notch_depth_mm"):
            spec.validate()

    def test_zero_notch_width_raises(self):
        spec = ContouredBandSpec(ring_size=7, notch_width_mm=0.0)
        with pytest.raises(ValueError, match="notch_width_mm"):
            spec.validate()

    def test_notch_width_exceeds_band_width_raises(self):
        spec = ContouredBandSpec(ring_size=7, notch_width_mm=5.0, band_width_mm=3.5)
        with pytest.raises(ValueError, match="notch_width_mm"):
            spec.validate()

    def test_zero_match_radius_raises(self):
        spec = ContouredBandSpec(ring_size=7, match_radius_mm=0.0)
        with pytest.raises(ValueError, match="match_radius_mm"):
            spec.validate()

    def test_invalid_contour_style_raises(self):
        spec = ContouredBandSpec(ring_size=7, contour_style="v_notch")
        with pytest.raises(ValueError, match="contour_style"):
            spec.validate()

    def test_zero_band_width_raises(self):
        spec = ContouredBandSpec(ring_size=7, band_width_mm=0.0)
        with pytest.raises(ValueError, match="band_width_mm"):
            spec.validate()

    def test_zero_thickness_raises(self):
        spec = ContouredBandSpec(ring_size=7, thickness_mm=0.0)
        with pytest.raises(ValueError, match="thickness_mm"):
            spec.validate()

    def test_notch_depth_exceeds_thickness_raises(self):
        spec = ContouredBandSpec(ring_size=7, notch_depth_mm=2.0, thickness_mm=1.6)
        with pytest.raises(ValueError, match="notch_depth_mm"):
            spec.validate()

    def test_invalid_base_profile_raises(self):
        spec = ContouredBandSpec(ring_size=7, profile="hammered")
        with pytest.raises(ValueError, match="profile"):
            spec.validate()

    def test_invalid_shoulder_style_raises(self):
        spec = ContouredBandSpec(ring_size=7, shoulder_style="prong")
        with pytest.raises(ValueError, match="shoulder_style"):
            spec.validate()


class TestComputeContouredBandParams:
    def test_basic_us7(self):
        p = compute_contoured_band_params(7, "us")
        assert abs(p["inner_diameter_mm"] - 17.32) < 0.01
        assert p["contour_style"] == "curved"

    def test_outer_diameter(self):
        p = compute_contoured_band_params(7, "us", thickness_mm=1.6)
        assert abs(p["outer_diameter_mm"] - (p["inner_diameter_mm"] + 2 * 1.6)) < 0.001

    def test_contour_hints_present(self):
        p = compute_contoured_band_params(7, "us")
        assert "contour_hints" in p
        ch = p["contour_hints"]
        assert ch["type"] == "curved"
        assert ch["notch_half_angle_deg"] > 0

    def test_all_contour_styles(self):
        for style in ["curved", "notched"]:
            p = compute_contoured_band_params(7, "us", contour_style=style)
            assert p["contour_style"] == style

    def test_all_base_profiles_accepted(self):
        for pr in ["flat", "half_round", "comfort_fit", "d_shape", "euro"]:
            p = compute_contoured_band_params(7, "us", profile=pr)
            assert p["profile"] == pr

    def test_shoulder_hints_present(self):
        p = compute_contoured_band_params(7, "us", shoulder_style="cathedral")
        assert "shoulder_hints" in p
        assert p["shoulder_hints"]["type"] == "cathedral"

    def test_notched_style_stored(self):
        p = compute_contoured_band_params(7, "us", contour_style="notched")
        assert p["contour_hints"]["type"] == "notched"

    def test_size_system_stored(self):
        p = compute_contoured_band_params(7, "us")
        assert p["size_system"] == "us"


class TestContouredBandTool:
    def _run(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), **kwargs}
        return run_tool_sync(
            run_jewelry_create_contoured_band(ctx, json.dumps(args).encode())
        )

    def test_basic_accepted(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7)
        assert "error" not in r, f"Unexpected error: {r}"
        assert r["op"] == "contoured_band"

    def test_node_id_generated(self):
        ctx, store, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7)
        assert r["id"].startswith("contoured_band-")

    def test_all_contour_styles_accepted(self):
        for style in ["curved", "notched"]:
            ctx, store, fid = make_ctx()
            r = self._run(ctx, fid, ring_size=7, contour_style=style)
            assert "error" not in r, f"Style {style!r}: {r}"

    def test_all_base_profiles_accepted(self):
        for pr in ["flat", "half_round", "comfort_fit", "d_shape", "euro"]:
            ctx, store, fid = make_ctx()
            r = self._run(ctx, fid, ring_size=7, profile=pr)
            assert "error" not in r, f"Profile {pr!r}: {r}"

    def test_engagement_ring_node_id_stored(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7, engagement_ring_node_id="ring_shank-1")
        doc = json.loads(store["content"])
        assert doc["features"][0]["engagement_ring_node_id"] == "ring_shank-1"

    def test_contour_hints_in_node(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7)
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert "contour_hints" in node
        assert node["contour_hints"]["notch_half_angle_deg"] > 0

    def test_invalid_contour_style_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, contour_style="v_notch")
        assert "error" in r

    def test_invalid_profile_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, profile="hammered")
        assert "error" in r

    def test_notch_exceeds_thickness_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, notch_depth_mm=3.0, thickness_mm=1.6)
        assert "error" in r

    def test_notch_width_exceeds_band_width_bad_args(self):
        ctx, _, fid = make_ctx()
        r = self._run(ctx, fid, ring_size=7, notch_width_mm=5.0, band_width_mm=3.5)
        assert "error" in r

    def test_missing_ring_size_bad_args(self):
        ctx, _, fid = make_ctx()
        r = run_tool_sync(
            run_jewelry_create_contoured_band(
                ctx, json.dumps({"file_id": str(fid)}).encode()
            )
        )
        assert "error" in r

    def test_non_feature_file_not_found(self):
        ctx, store, fid = make_ctx()
        store["kind"] = "sketch"
        r = self._run(ctx, fid, ring_size=7)
        assert "error" in r

    def test_second_node_increments_id(self):
        ctx, store, fid = make_ctx()
        self._run(ctx, fid, ring_size=7)
        r2 = self._run(ctx, fid, ring_size=7)
        assert r2["id"] == "contoured_band-2"

    def test_spec_required_fields(self):
        req = set(jewelry_create_contoured_band_spec.input_schema["required"])
        assert "file_id" in req
        assert "ring_size" in req

    def test_spec_contour_style_enum(self):
        props = jewelry_create_contoured_band_spec.input_schema["properties"]
        assert set(props["contour_style"]["enum"]) == {"curved", "notched"}


# ===========================================================================
# v3 Cross-type tests
# ===========================================================================

class TestV3NodeIdIsolation:
    """Verify that each v3 op type gets its own ID sequence."""

    def test_different_op_ids_dont_collide(self):
        """eternity_band and signet_ring each start at -1."""
        ctx, store, fid = make_ctx()
        args_e = {"file_id": str(fid), "ring_size": 7}
        run_tool_sync(run_jewelry_create_eternity_band(ctx, json.dumps(args_e).encode()))
        args_s = {"file_id": str(fid), "ring_size": 7}
        run_tool_sync(run_jewelry_create_signet_ring(ctx, json.dumps(args_s).encode()))
        doc = json.loads(store["content"])
        ids = [f["id"] for f in doc["features"]]
        assert "eternity_band-1" in ids
        assert "signet_ring-1" in ids

    def test_mixed_v2_v3_ids_independent(self):
        """ring_shank and eternity_band have independent sequences."""
        ctx, store, fid = make_ctx()
        r1 = run_tool_sync(run_jewelry_create_ring_shank(
            ctx, json.dumps({"file_id": str(fid), "ring_size": 7}).encode()
        ))
        r2 = run_tool_sync(run_jewelry_create_eternity_band(
            ctx, json.dumps({"file_id": str(fid), "ring_size": 7}).encode()
        ))
        assert r1["id"] == "ring_shank-1"
        assert r2["id"] == "eternity_band-1"


class TestV3SizeSystems:
    """All v3 tools accept all ring-size systems."""

    def _check_tool(self, runner, ctx, fid, ring_size, system, **kwargs):
        args = {"file_id": str(fid), "ring_size": ring_size, "system": system, **kwargs}
        return run_tool_sync(runner(ctx, json.dumps(args).encode()))

    def test_eternity_uk_size(self):
        ctx, store, fid = make_ctx()
        r = self._check_tool(run_jewelry_create_eternity_band, ctx, fid, "N", "uk")
        assert "error" not in r

    def test_signet_eu_size(self):
        ctx, store, fid = make_ctx()
        r = self._check_tool(run_jewelry_create_signet_ring, ctx, fid, 54, "eu")
        assert "error" not in r

    def test_stacking_jp_size(self):
        ctx, store, fid = make_ctx()
        r = self._check_tool(run_jewelry_create_stacking_band_set, ctx, fid, 13, "jp")
        assert "error" not in r

    def test_contoured_au_size(self):
        ctx, store, fid = make_ctx()
        r = self._check_tool(run_jewelry_create_contoured_band, ctx, fid, "P", "au")
        assert "error" not in r


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


# ===========================================================================
# v4 Composite / Style Ring Builders
# ===========================================================================

from kerf_cad_core.jewelry.ring import (
    # v4 specs
    SolitaireRingSpec,
    MensBandSpec,
    WeddingSetSpec,
    CocktailRingSpec,
    BypassRingSpec,
    # v4 compute functions
    compute_solitaire_ring_params,
    compute_mens_band_params,
    compute_wedding_set_params,
    compute_cocktail_ring_params,
    compute_bypass_ring_params,
    # v4 tool specs and runners
    jewelry_create_solitaire_ring_spec,
    jewelry_create_mens_band_spec,
    jewelry_create_wedding_set_spec,
    jewelry_create_cocktail_ring_spec,
    jewelry_create_bypass_ring_spec,
    run_jewelry_create_solitaire_ring,
    run_jewelry_create_mens_band,
    run_jewelry_create_wedding_set,
    run_jewelry_create_cocktail_ring,
    run_jewelry_create_bypass_ring,
    # v4 constants
    _VALID_MENS_PROFILES,
    _VALID_MENS_SURFACE_HINTS,
    _VALID_COCKTAIL_MOUNT_STYLES,
    _VALID_BYPASS_CROSS_STYLES,
)


# ---------------------------------------------------------------------------
# TestSolitaireRing — spec, compute, tool runner
# ---------------------------------------------------------------------------

class TestSolitaireRingSpec:

    def test_defaults_validate(self):
        spec = SolitaireRingSpec(ring_size=7, system="us")
        spec.validate()

    def test_to_dict_has_required_keys(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = SolitaireRingSpec(ring_size=7, system="us")
        d = spec.to_dict(id_mm)
        for key in ("inner_diameter_mm", "outer_diameter_mm", "shank",
                    "head_height_mm", "center_stone_diameter_mm",
                    "attach_points", "composite_ops"):
            assert key in d, f"Missing key: {key}"

    def test_attach_point_schema(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = SolitaireRingSpec(ring_size=7, system="us",
                                 head_height_mm=6.0,
                                 center_stone_diameter_mm=7.0)
        d = spec.to_dict(id_mm)
        ap = d["attach_points"][0]
        assert ap["type"] == "circular_seat"
        assert ap["position_deg"] == 0.0
        assert abs(ap["height_mm"] - 6.0) < 1e-6
        assert abs(ap["diameter_mm"] - 7.0) < 1e-6
        assert ap["normal"] == [0, 0, 1]

    def test_invalid_profile_raises(self):
        with pytest.raises(ValueError, match="shank_profile"):
            SolitaireRingSpec(ring_size=7, shank_profile="nope").validate()

    def test_invalid_shoulder_raises(self):
        with pytest.raises(ValueError, match="shoulder_style"):
            SolitaireRingSpec(ring_size=7, shoulder_style="crown").validate()

    def test_negative_band_width_raises(self):
        with pytest.raises(ValueError, match="band_width_mm"):
            SolitaireRingSpec(ring_size=7, band_width_mm=-1.0).validate()

    def test_zero_thickness_raises(self):
        with pytest.raises(ValueError, match="thickness_mm"):
            SolitaireRingSpec(ring_size=7, thickness_mm=0).validate()

    def test_zero_head_height_raises(self):
        with pytest.raises(ValueError, match="head_height_mm"):
            SolitaireRingSpec(ring_size=7, head_height_mm=0).validate()

    def test_zero_stone_diameter_raises(self):
        with pytest.raises(ValueError, match="center_stone_diameter_mm"):
            SolitaireRingSpec(ring_size=7, center_stone_diameter_mm=0).validate()

    def test_taper_ratio_zero_raises(self):
        with pytest.raises(ValueError, match="taper_ratio"):
            SolitaireRingSpec(ring_size=7, taper_ratio=0).validate()

    def test_taper_ratio_over_one_raises(self):
        with pytest.raises(ValueError, match="taper_ratio"):
            SolitaireRingSpec(ring_size=7, taper_ratio=1.5).validate()


class TestComputeSolitaireRing:

    def test_basic_us7(self):
        p = compute_solitaire_ring_params(7, "us")
        assert p["inner_diameter_mm"] > 0
        assert p["outer_diameter_mm"] > p["inner_diameter_mm"]
        assert len(p["attach_points"]) == 1
        assert p["attach_points"][0]["type"] == "circular_seat"

    def test_composite_ops_present(self):
        p = compute_solitaire_ring_params(7)
        assert "ring_shank" in p["composite_ops"]
        assert "setting_mount" in p["composite_ops"]

    def test_shank_sub_dict_present(self):
        p = compute_solitaire_ring_params(7)
        assert "shank" in p
        assert "inner_diameter_mm" in p["shank"]

    def test_cathedral_shoulder_default(self):
        p = compute_solitaire_ring_params(7)
        assert p["shank"]["shoulder_style"] == "cathedral"

    def test_size_system_stored(self):
        p = compute_solitaire_ring_params("N", system="uk")
        assert p["size_system"] == "uk"

    def test_circumference_present(self):
        p = compute_solitaire_ring_params(7)
        assert "circumference_mm" in p

    def test_invalid_ring_size_raises(self):
        with pytest.raises(ValueError):
            compute_solitaire_ring_params(99, "us")

    def test_head_height_stored_in_attach_point(self):
        p = compute_solitaire_ring_params(7, head_height_mm=7.5)
        assert abs(p["attach_points"][0]["height_mm"] - 7.5) < 1e-4

    def test_stone_diam_stored_in_attach_point(self):
        p = compute_solitaire_ring_params(7, center_stone_diameter_mm=8.0)
        assert abs(p["attach_points"][0]["diameter_mm"] - 8.0) < 1e-4


class TestRunJewelryCreateSolitaireRing:

    def _call(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), "ring_size": 7, **kwargs}
        return run_tool_sync(run_jewelry_create_solitaire_ring(
            ctx, json.dumps(args).encode()
        ))

    def test_basic_success(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "error" not in r
        assert r["op"] == "solitaire_ring"
        assert r["id"] == "solitaire_ring-1"

    def test_node_appended_to_doc(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        ops = [f["op"] for f in doc["features"]]
        assert "solitaire_ring" in ops

    def test_attach_points_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "attach_points" in r
        assert len(r["attach_points"]) == 1
        assert r["attach_points"][0]["type"] == "circular_seat"

    def test_missing_file_id_returns_bad_args(self):
        ctx, store, fid = make_ctx()
        r = run_tool_sync(run_jewelry_create_solitaire_ring(
            ctx, json.dumps({"ring_size": 7}).encode()
        ))
        assert r.get("code") == "BAD_ARGS"

    def test_missing_ring_size_returns_bad_args(self):
        ctx, store, fid = make_ctx()
        r = run_tool_sync(run_jewelry_create_solitaire_ring(
            ctx, json.dumps({"file_id": str(fid)}).encode()
        ))
        assert r.get("code") == "BAD_ARGS"

    def test_invalid_profile_returns_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, shank_profile="nope")
        assert r.get("code") == "BAD_ARGS"

    def test_bad_taper_ratio_returns_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, taper_ratio=2.0)
        assert r.get("code") == "BAD_ARGS"

    def test_spec_has_required_fields(self):
        props = jewelry_create_solitaire_ring_spec.input_schema["properties"]
        assert "file_id" in props
        assert "ring_size" in props
        assert "shank_profile" in props
        assert "head_height_mm" in props
        assert "center_stone_diameter_mm" in props

    def test_sequential_ids(self):
        ctx, store, fid = make_ctx()
        r1 = self._call(ctx, fid)
        r2 = self._call(ctx, fid)
        assert r1["id"] == "solitaire_ring-1"
        assert r2["id"] == "solitaire_ring-2"

    def test_uk_size_accepted(self):
        ctx, store, fid = make_ctx()
        args = {"file_id": str(fid), "ring_size": "N", "system": "uk"}
        r = run_tool_sync(run_jewelry_create_solitaire_ring(
            ctx, json.dumps(args).encode()
        ))
        assert "error" not in r


# ---------------------------------------------------------------------------
# TestMensBand — spec, compute, tool runner
# ---------------------------------------------------------------------------

class TestMensBandSpec:

    def test_defaults_validate(self):
        spec = MensBandSpec(ring_size=10, system="us")
        spec.validate()

    def test_invalid_profile_raises(self):
        with pytest.raises(ValueError, match="mens_band.profile"):
            MensBandSpec(ring_size=10, profile="knife_edge").validate()

    def test_zero_band_width_raises(self):
        with pytest.raises(ValueError, match="band_width_mm"):
            MensBandSpec(ring_size=10, band_width_mm=0).validate()

    def test_zero_thickness_raises(self):
        with pytest.raises(ValueError, match="thickness_mm"):
            MensBandSpec(ring_size=10, thickness_mm=0).validate()

    def test_zero_taper_ratio_raises(self):
        with pytest.raises(ValueError, match="taper_ratio"):
            MensBandSpec(ring_size=10, taper_ratio=0).validate()

    def test_groove_too_deep_raises(self):
        with pytest.raises(ValueError, match="groove_depth_mm"):
            MensBandSpec(ring_size=10, thickness_mm=2.0,
                          groove_depth_mm=1.1).validate()

    def test_groove_width_zero_when_groove_set_raises(self):
        with pytest.raises(ValueError, match="groove_width_mm"):
            MensBandSpec(ring_size=10, thickness_mm=2.0,
                          groove_depth_mm=0.5, groove_width_mm=0).validate()

    def test_groove_wider_than_band_raises(self):
        with pytest.raises(ValueError, match="groove_width_mm"):
            MensBandSpec(ring_size=10, band_width_mm=5.0,
                          thickness_mm=2.0, groove_depth_mm=0.5,
                          groove_width_mm=6.0).validate()

    def test_invalid_surface_finish_raises(self):
        with pytest.raises(ValueError, match="surface_finish"):
            MensBandSpec(ring_size=10, surface_finish="velvet").validate()

    def test_milgrain_zero_bead_raises(self):
        with pytest.raises(ValueError, match="milgrain_bead_diameter_mm"):
            MensBandSpec(ring_size=10, milgrain_edges=True,
                          milgrain_bead_diameter_mm=0).validate()

    def test_hammered_facet_count_bounds(self):
        with pytest.raises(ValueError, match="hammered_facet_count"):
            MensBandSpec(ring_size=10, hammered_facet_count=2).validate()

    def test_to_dict_no_groove(self):
        id_mm = ring_size_to_diameter("us", 10)
        spec = MensBandSpec(ring_size=10)
        d = spec.to_dict(id_mm)
        assert "groove_hint" not in d
        assert "milgrain_hint" not in d

    def test_to_dict_with_groove(self):
        id_mm = ring_size_to_diameter("us", 10)
        spec = MensBandSpec(ring_size=10, groove_depth_mm=0.5,
                             groove_width_mm=2.0, thickness_mm=2.5,
                             band_width_mm=8.0)
        d = spec.to_dict(id_mm)
        assert "groove_hint" in d
        g = d["groove_hint"]
        assert g["type"] == "centre_groove"
        assert abs(g["depth_mm"] - 0.5) < 1e-4
        assert abs(g["width_mm"] - 2.0) < 1e-4

    def test_to_dict_with_milgrain(self):
        id_mm = ring_size_to_diameter("us", 10)
        spec = MensBandSpec(ring_size=10, milgrain_edges=True,
                             milgrain_bead_diameter_mm=0.4)
        d = spec.to_dict(id_mm)
        assert "milgrain_hint" in d
        m = d["milgrain_hint"]
        assert m["type"] == "milgrain_edge"
        assert abs(m["bead_diameter_mm"] - 0.4) < 1e-4
        assert "top" in m["edges"] and "bottom" in m["edges"]

    def test_hammered_surface_hint(self):
        id_mm = ring_size_to_diameter("us", 10)
        spec = MensBandSpec(ring_size=10, surface_finish="hammered",
                             hammered_facet_count=24)
        d = spec.to_dict(id_mm)
        assert "surface_hint" in d
        sh = d["surface_hint"]
        assert sh["type"] == "hammered"
        assert sh["facet_count"] == 24

    def test_matte_surface_hint(self):
        id_mm = ring_size_to_diameter("us", 10)
        spec = MensBandSpec(ring_size=10, surface_finish="matte")
        d = spec.to_dict(id_mm)
        assert d.get("surface_hint", {}).get("type") == "matte"

    def test_polished_no_surface_hint(self):
        id_mm = ring_size_to_diameter("us", 10)
        spec = MensBandSpec(ring_size=10, surface_finish="polished")
        d = spec.to_dict(id_mm)
        assert "surface_hint" not in d


class TestComputeMensBand:

    def test_basic_us10(self):
        p = compute_mens_band_params(10, "us")
        assert p["inner_diameter_mm"] > 0
        assert p["outer_diameter_mm"] > p["inner_diameter_mm"]
        assert "band_width_mm" in p
        assert p["band_width_mm"] == 8.0

    def test_groove_hint_propagated(self):
        p = compute_mens_band_params(
            10, groove_depth_mm=0.5, groove_width_mm=2.0,
            band_width_mm=8.0, thickness_mm=2.5,
        )
        assert "groove_hint" in p

    def test_milgrain_hint_propagated(self):
        p = compute_mens_band_params(10, milgrain_edges=True)
        assert "milgrain_hint" in p

    def test_invalid_profile_raises(self):
        with pytest.raises(ValueError):
            compute_mens_band_params(10, profile="knife_edge")

    def test_jp_size_accepted(self):
        p = compute_mens_band_params(15, system="jp")
        assert p["size_system"] == "jp"


class TestRunJewelryCreateMensBand:

    def _call(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), "ring_size": 10, **kwargs}
        return run_tool_sync(run_jewelry_create_mens_band(
            ctx, json.dumps(args).encode()
        ))

    def test_basic_success(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "error" not in r
        assert r["op"] == "mens_band"
        assert r["id"] == "mens_band-1"

    def test_node_in_doc(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        assert any(f["op"] == "mens_band" for f in doc["features"])

    def test_with_groove(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, groove_depth_mm=0.5, groove_width_mm=2.0,
                       thickness_mm=2.5, band_width_mm=8.0)
        assert "error" not in r
        doc = json.loads(store["content"])
        node = next(f for f in doc["features"] if f["op"] == "mens_band")
        assert "groove_hint" in node

    def test_with_milgrain(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, milgrain_edges=True)
        assert "error" not in r
        doc = json.loads(store["content"])
        node = next(f for f in doc["features"] if f["op"] == "mens_band")
        assert "milgrain_hint" in node

    def test_invalid_profile_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, profile="knife_edge")
        assert r.get("code") == "BAD_ARGS"

    def test_invalid_surface_finish_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, surface_finish="velvet")
        assert r.get("code") == "BAD_ARGS"

    def test_missing_file_id_bad_args(self):
        ctx, store, fid = make_ctx()
        r = run_tool_sync(run_jewelry_create_mens_band(
            ctx, json.dumps({"ring_size": 10}).encode()
        ))
        assert r.get("code") == "BAD_ARGS"

    def test_spec_required_fields(self):
        req = jewelry_create_mens_band_spec.input_schema.get("required", [])
        assert "file_id" in req
        assert "ring_size" in req

    def test_profile_enum_in_spec(self):
        props = jewelry_create_mens_band_spec.input_schema["properties"]
        allowed = set(props["profile"]["enum"])
        assert "comfort_fit" in allowed
        assert "euro" in allowed
        assert "knife_edge" not in allowed  # knife_edge not in mens profiles

    def test_surface_finish_enum_in_spec(self):
        props = jewelry_create_mens_band_spec.input_schema["properties"]
        allowed = set(props["surface_finish"]["enum"])
        assert allowed == _VALID_MENS_SURFACE_HINTS


# ---------------------------------------------------------------------------
# TestWeddingSet — spec, compute, tool runner
# ---------------------------------------------------------------------------

class TestWeddingSetSpec:

    def test_defaults_validate(self):
        spec = WeddingSetSpec(ring_size=7, system="us")
        spec.validate()

    def test_invalid_eng_profile_raises(self):
        with pytest.raises(ValueError, match="eng_profile"):
            WeddingSetSpec(ring_size=7, eng_profile="nope").validate()

    def test_invalid_band_profile_raises(self):
        with pytest.raises(ValueError, match="band_profile"):
            WeddingSetSpec(ring_size=7, band_profile="hammered").validate()

    def test_invalid_contour_style_raises(self):
        with pytest.raises(ValueError, match="contour_style"):
            WeddingSetSpec(ring_size=7, contour_style="diagonal").validate()

    def test_notch_depth_too_large_raises(self):
        with pytest.raises(ValueError, match="notch_depth_mm"):
            WeddingSetSpec(ring_size=7, notch_depth_mm=2.0,
                            band_thickness_mm=1.6).validate()

    def test_notch_width_too_large_raises(self):
        with pytest.raises(ValueError, match="notch_width_mm"):
            WeddingSetSpec(ring_size=7, notch_width_mm=5.0,
                            band_width_mm=3.0).validate()

    def test_to_dict_has_both_rings(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = WeddingSetSpec(ring_size=7)
        d = spec.to_dict(id_mm)
        assert "engagement_ring" in d
        assert "wedding_band" in d

    def test_engagement_ring_op_is_ring_shank(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = WeddingSetSpec(ring_size=7)
        d = spec.to_dict(id_mm)
        assert d["engagement_ring"]["op"] == "ring_shank"

    def test_wedding_band_op_is_contoured_band(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = WeddingSetSpec(ring_size=7)
        d = spec.to_dict(id_mm)
        assert d["wedding_band"]["op"] == "contoured_band"

    def test_match_radius_equals_eng_outer_radius(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = WeddingSetSpec(ring_size=7, eng_thickness_mm=1.6)
        d = spec.to_dict(id_mm)
        expected_radius = (id_mm + 2 * 1.6) / 2.0
        assert abs(d["match_radius_mm"] - expected_radius) < 1e-3

    def test_contour_hints_present(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = WeddingSetSpec(ring_size=7)
        d = spec.to_dict(id_mm)
        assert "contour_hints" in d["wedding_band"]
        assert "notch_half_angle_deg" in d["wedding_band"]["contour_hints"]

    def test_composite_ops(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = WeddingSetSpec(ring_size=7)
        d = spec.to_dict(id_mm)
        assert "ring_shank" in d["composite_ops"]
        assert "contoured_band" in d["composite_ops"]


class TestComputeWeddingSet:

    def test_basic_us7(self):
        p = compute_wedding_set_params(7, "us")
        assert p["inner_diameter_mm"] > 0
        assert "engagement_ring" in p
        assert "wedding_band" in p

    def test_match_radius_positive(self):
        p = compute_wedding_set_params(7)
        assert p["match_radius_mm"] > 0

    def test_eu_size_accepted(self):
        p = compute_wedding_set_params(54, system="eu")
        assert p["size_system"] == "eu"

    def test_invalid_ring_size_raises(self):
        with pytest.raises(ValueError):
            compute_wedding_set_params(99, "us")

    def test_circumference_present(self):
        p = compute_wedding_set_params(7)
        assert "circumference_mm" in p


class TestRunJewelryCreateWeddingSet:

    def _call(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), "ring_size": 7, **kwargs}
        return run_tool_sync(run_jewelry_create_wedding_set(
            ctx, json.dumps(args).encode()
        ))

    def test_basic_success(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "error" not in r
        assert r["op"] == "wedding_set"
        assert r["id"] == "wedding_set-1"

    def test_node_in_doc(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        assert any(f["op"] == "wedding_set" for f in doc["features"])

    def test_match_radius_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "match_radius_mm" in r

    def test_invalid_eng_profile_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, eng_profile="nope")
        assert r.get("code") == "BAD_ARGS"

    def test_invalid_band_profile_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, band_profile="hammered")
        assert r.get("code") == "BAD_ARGS"

    def test_notch_depth_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, notch_depth_mm=2.0, band_thickness_mm=1.6)
        assert r.get("code") == "BAD_ARGS"

    def test_missing_file_id_bad_args(self):
        ctx, store, fid = make_ctx()
        r = run_tool_sync(run_jewelry_create_wedding_set(
            ctx, json.dumps({"ring_size": 7}).encode()
        ))
        assert r.get("code") == "BAD_ARGS"

    def test_spec_required_fields(self):
        req = jewelry_create_wedding_set_spec.input_schema.get("required", [])
        assert "file_id" in req
        assert "ring_size" in req

    def test_spec_band_profile_enum(self):
        props = jewelry_create_wedding_set_spec.input_schema["properties"]
        allowed = set(props["band_profile"]["enum"])
        assert "flat" in allowed
        assert "hammered" not in allowed

    def test_contour_style_enum(self):
        props = jewelry_create_wedding_set_spec.input_schema["properties"]
        assert set(props["contour_style"]["enum"]) == {"curved", "notched"}


# ---------------------------------------------------------------------------
# TestCocktailRing — spec, compute, tool runner
# ---------------------------------------------------------------------------

class TestCocktailRingSpec:

    def test_defaults_validate(self):
        spec = CocktailRingSpec(ring_size=7, system="us")
        spec.validate()

    def test_invalid_profile_raises(self):
        with pytest.raises(ValueError, match="shank_profile"):
            CocktailRingSpec(ring_size=7, shank_profile="nope").validate()

    def test_invalid_mount_style_raises(self):
        with pytest.raises(ValueError, match="mount_style"):
            CocktailRingSpec(ring_size=7, mount_style="pyramid").validate()

    def test_zero_mount_diameter_raises(self):
        with pytest.raises(ValueError, match="mount_diameter_mm"):
            CocktailRingSpec(ring_size=7, mount_diameter_mm=0).validate()

    def test_zero_mount_height_raises(self):
        with pytest.raises(ValueError, match="mount_height_mm"):
            CocktailRingSpec(ring_size=7, mount_height_mm=0).validate()

    def test_stone_larger_than_mount_raises(self):
        with pytest.raises(ValueError, match="stone_diameter_mm"):
            CocktailRingSpec(ring_size=7, stone_diameter_mm=20.0,
                              mount_diameter_mm=18.0).validate()

    def test_taper_over_one_raises(self):
        with pytest.raises(ValueError, match="taper_ratio"):
            CocktailRingSpec(ring_size=7, taper_ratio=1.5).validate()

    def test_attach_point_schema(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = CocktailRingSpec(ring_size=7, mount_height_mm=9.0,
                                stone_diameter_mm=12.0,
                                mount_diameter_mm=16.0,
                                mount_style="cluster")
        d = spec.to_dict(id_mm)
        ap = d["attach_points"][0]
        assert ap["type"] == "circular_seat"
        assert ap["mount_style"] == "cluster"
        assert abs(ap["height_mm"] - 9.0) < 1e-4
        assert abs(ap["diameter_mm"] - 12.0) < 1e-4
        assert abs(ap["mount_diameter_mm"] - 16.0) < 1e-4
        assert ap["normal"] == [0, 0, 1]

    def test_composite_ops(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = CocktailRingSpec(ring_size=7)
        d = spec.to_dict(id_mm)
        assert "ring_shank" in d["composite_ops"]
        assert "mount_platform" in d["composite_ops"]


class TestComputeCocktailRing:

    def test_basic_us7(self):
        p = compute_cocktail_ring_params(7, "us")
        assert p["inner_diameter_mm"] > 0
        assert p["outer_diameter_mm"] > p["inner_diameter_mm"]
        assert len(p["attach_points"]) == 1

    def test_default_mount_style(self):
        p = compute_cocktail_ring_params(7)
        assert p["mount_style"] == "dome"

    def test_default_taper_ratio(self):
        p = compute_cocktail_ring_params(7)
        assert abs(p["taper_ratio"] - 0.7) < 1e-6

    def test_size_system_stored(self):
        p = compute_cocktail_ring_params("Z", system="uk")
        assert p["size_system"] == "uk"

    def test_invalid_ring_size_raises(self):
        with pytest.raises(ValueError):
            compute_cocktail_ring_params(99, "us")


class TestRunJewelryCreateCocktailRing:

    def _call(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), "ring_size": 7, **kwargs}
        return run_tool_sync(run_jewelry_create_cocktail_ring(
            ctx, json.dumps(args).encode()
        ))

    def test_basic_success(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "error" not in r
        assert r["op"] == "cocktail_ring"
        assert r["id"] == "cocktail_ring-1"

    def test_node_in_doc(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        assert any(f["op"] == "cocktail_ring" for f in doc["features"])

    def test_attach_points_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "attach_points" in r
        assert len(r["attach_points"]) == 1

    def test_invalid_mount_style_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, mount_style="pyramid")
        assert r.get("code") == "BAD_ARGS"

    def test_stone_too_big_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, stone_diameter_mm=25.0, mount_diameter_mm=18.0)
        assert r.get("code") == "BAD_ARGS"

    def test_missing_file_id_bad_args(self):
        ctx, store, fid = make_ctx()
        r = run_tool_sync(run_jewelry_create_cocktail_ring(
            ctx, json.dumps({"ring_size": 7}).encode()
        ))
        assert r.get("code") == "BAD_ARGS"

    def test_mount_style_enum_in_spec(self):
        props = jewelry_create_cocktail_ring_spec.input_schema["properties"]
        assert set(props["mount_style"]["enum"]) == _VALID_COCKTAIL_MOUNT_STYLES

    def test_sequential_ids(self):
        ctx, store, fid = make_ctx()
        r1 = self._call(ctx, fid)
        r2 = self._call(ctx, fid)
        assert r1["id"] == "cocktail_ring-1"
        assert r2["id"] == "cocktail_ring-2"


# ---------------------------------------------------------------------------
# TestBypassRing — spec, compute, tool runner
# ---------------------------------------------------------------------------

class TestBypassRingSpec:

    def test_defaults_validate(self):
        spec = BypassRingSpec(ring_size=7, system="us")
        spec.validate()

    def test_invalid_cross_style_raises(self):
        with pytest.raises(ValueError, match="cross_style"):
            BypassRingSpec(ring_size=7, cross_style="parallel").validate()

    def test_invalid_profile_raises(self):
        with pytest.raises(ValueError, match="bypass.profile"):
            BypassRingSpec(ring_size=7, profile="nope").validate()

    def test_zero_band_width_raises(self):
        with pytest.raises(ValueError, match="band_width_mm"):
            BypassRingSpec(ring_size=7, band_width_mm=0).validate()

    def test_zero_thickness_raises(self):
        with pytest.raises(ValueError, match="thickness_mm"):
            BypassRingSpec(ring_size=7, thickness_mm=0).validate()

    def test_zero_bypass_offset_raises(self):
        with pytest.raises(ValueError, match="bypass_offset_mm"):
            BypassRingSpec(ring_size=7, bypass_offset_mm=0).validate()

    def test_overlap_deg_out_of_range_raises(self):
        with pytest.raises(ValueError, match="overlap_deg"):
            BypassRingSpec(ring_size=7, overlap_deg=100).validate()

    def test_zero_stone_a_diameter_raises(self):
        with pytest.raises(ValueError, match="stone_a_diameter_mm"):
            BypassRingSpec(ring_size=7, stone_a_diameter_mm=0).validate()

    def test_zero_stone_b_diameter_raises(self):
        with pytest.raises(ValueError, match="stone_b_diameter_mm"):
            BypassRingSpec(ring_size=7, stone_b_diameter_mm=0).validate()

    def test_zero_mount_height_raises(self):
        with pytest.raises(ValueError, match="mount_height_mm"):
            BypassRingSpec(ring_size=7, mount_height_mm=0).validate()

    def test_crossover_attach_points_schema(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = BypassRingSpec(ring_size=7, cross_style="crossover",
                               bypass_offset_mm=4.0, overlap_deg=20.0,
                               stone_a_diameter_mm=6.0, stone_b_diameter_mm=5.0,
                               mount_height_mm=4.5)
        d = spec.to_dict(id_mm)
        aps = d["attach_points"]
        assert len(aps) == 2
        for ap in aps:
            assert ap["type"] == "circular_seat"
            assert "arm" in ap
            assert ap["normal"] == [0, 0, 1]
        a_ap = next(ap for ap in aps if ap["arm"] == "A")
        b_ap = next(ap for ap in aps if ap["arm"] == "B")
        assert a_ap["lateral_offset_mm"] > 0
        assert b_ap["lateral_offset_mm"] < 0
        assert abs(a_ap["diameter_mm"] - 6.0) < 1e-4
        assert abs(b_ap["diameter_mm"] - 5.0) < 1e-4

    def test_toi_et_moi_attach_type(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = BypassRingSpec(ring_size=7, cross_style="toi_et_moi")
        d = spec.to_dict(id_mm)
        for ap in d["attach_points"]:
            assert ap["type"] == "toi_et_moi"

    def test_composite_ops(self):
        id_mm = ring_size_to_diameter("us", 7)
        spec = BypassRingSpec(ring_size=7)
        d = spec.to_dict(id_mm)
        assert "bypass_arm_a" in d["composite_ops"]
        assert "bypass_arm_b" in d["composite_ops"]


class TestComputeBypassRing:

    def test_basic_us7_crossover(self):
        p = compute_bypass_ring_params(7, "us")
        assert p["inner_diameter_mm"] > 0
        assert p["outer_diameter_mm"] > p["inner_diameter_mm"]
        assert len(p["attach_points"]) == 2

    def test_toi_et_moi(self):
        p = compute_bypass_ring_params(7, cross_style="toi_et_moi")
        for ap in p["attach_points"]:
            assert ap["type"] == "toi_et_moi"

    def test_asymmetric_stones(self):
        p = compute_bypass_ring_params(7,
                                       stone_a_diameter_mm=8.0,
                                       stone_b_diameter_mm=5.0)
        a_ap = next(ap for ap in p["attach_points"] if ap["arm"] == "A")
        b_ap = next(ap for ap in p["attach_points"] if ap["arm"] == "B")
        assert abs(a_ap["diameter_mm"] - 8.0) < 1e-4
        assert abs(b_ap["diameter_mm"] - 5.0) < 1e-4

    def test_size_system_stored(self):
        p = compute_bypass_ring_params(20, system="jp")
        assert p["size_system"] == "jp"

    def test_invalid_ring_size_raises(self):
        with pytest.raises(ValueError):
            compute_bypass_ring_params(99, "us")


class TestRunJewelryCreateBypassRing:

    def _call(self, ctx, fid, **kwargs):
        args = {"file_id": str(fid), "ring_size": 7, **kwargs}
        return run_tool_sync(run_jewelry_create_bypass_ring(
            ctx, json.dumps(args).encode()
        ))

    def test_basic_success(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "error" not in r
        assert r["op"] == "bypass_ring"
        assert r["id"] == "bypass_ring-1"

    def test_node_in_doc(self):
        ctx, store, fid = make_ctx()
        self._call(ctx, fid)
        doc = json.loads(store["content"])
        assert any(f["op"] == "bypass_ring" for f in doc["features"])

    def test_two_attach_points_in_response(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid)
        assert "attach_points" in r
        assert len(r["attach_points"]) == 2

    def test_toi_et_moi_style(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, cross_style="toi_et_moi")
        assert "error" not in r
        for ap in r["attach_points"]:
            assert ap["type"] == "toi_et_moi"

    def test_invalid_cross_style_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, cross_style="parallel")
        assert r.get("code") == "BAD_ARGS"

    def test_invalid_profile_bad_args(self):
        ctx, store, fid = make_ctx()
        r = self._call(ctx, fid, profile="nope")
        assert r.get("code") == "BAD_ARGS"

    def test_missing_file_id_bad_args(self):
        ctx, store, fid = make_ctx()
        r = run_tool_sync(run_jewelry_create_bypass_ring(
            ctx, json.dumps({"ring_size": 7}).encode()
        ))
        assert r.get("code") == "BAD_ARGS"

    def test_cross_style_enum_in_spec(self):
        props = jewelry_create_bypass_ring_spec.input_schema["properties"]
        assert set(props["cross_style"]["enum"]) == _VALID_BYPASS_CROSS_STYLES

    def test_sequential_ids(self):
        ctx, store, fid = make_ctx()
        r1 = self._call(ctx, fid)
        r2 = self._call(ctx, fid)
        assert r1["id"] == "bypass_ring-1"
        assert r2["id"] == "bypass_ring-2"

    def test_uk_size_accepted(self):
        ctx, store, fid = make_ctx()
        args = {"file_id": str(fid), "ring_size": "M", "system": "uk"}
        r = run_tool_sync(run_jewelry_create_bypass_ring(
            ctx, json.dumps(args).encode()
        ))
        assert "error" not in r


# ---------------------------------------------------------------------------
# TestV4NodeIdIsolation — v4 ops get independent ID sequences
# ---------------------------------------------------------------------------

class TestV4NodeIdIsolation:

    def test_all_v4_ops_independent(self):
        ctx, store, fid = make_ctx()
        run_tool_sync(run_jewelry_create_solitaire_ring(
            ctx, json.dumps({"file_id": str(fid), "ring_size": 7}).encode()
        ))
        run_tool_sync(run_jewelry_create_mens_band(
            ctx, json.dumps({"file_id": str(fid), "ring_size": 7}).encode()
        ))
        run_tool_sync(run_jewelry_create_wedding_set(
            ctx, json.dumps({"file_id": str(fid), "ring_size": 7}).encode()
        ))
        run_tool_sync(run_jewelry_create_cocktail_ring(
            ctx, json.dumps({"file_id": str(fid), "ring_size": 7}).encode()
        ))
        run_tool_sync(run_jewelry_create_bypass_ring(
            ctx, json.dumps({"file_id": str(fid), "ring_size": 7}).encode()
        ))
        doc = json.loads(store["content"])
        ids = [f["id"] for f in doc["features"]]
        assert "solitaire_ring-1" in ids
        assert "mens_band-1" in ids
        assert "wedding_set-1" in ids
        assert "cocktail_ring-1" in ids
        assert "bypass_ring-1" in ids

    def test_v4_does_not_collide_with_v3(self):
        ctx, store, fid = make_ctx()
        run_tool_sync(run_jewelry_create_eternity_band(
            ctx, json.dumps({"file_id": str(fid), "ring_size": 7}).encode()
        ))
        run_tool_sync(run_jewelry_create_solitaire_ring(
            ctx, json.dumps({"file_id": str(fid), "ring_size": 7}).encode()
        ))
        doc = json.loads(store["content"])
        ids = [f["id"] for f in doc["features"]]
        assert "eternity_band-1" in ids
        assert "solitaire_ring-1" in ids

    def test_v4_second_instance_increments(self):
        ctx, store, fid = make_ctx()
        r1 = run_tool_sync(run_jewelry_create_wedding_set(
            ctx, json.dumps({"file_id": str(fid), "ring_size": 7}).encode()
        ))
        r2 = run_tool_sync(run_jewelry_create_wedding_set(
            ctx, json.dumps({"file_id": str(fid), "ring_size": 7}).encode()
        ))
        assert r1["id"] == "wedding_set-1"
        assert r2["id"] == "wedding_set-2"


# ---------------------------------------------------------------------------
# TestV4SizeSystems — all v4 tools accept all ring-size systems
# ---------------------------------------------------------------------------

class TestV4SizeSystems:

    def _check(self, runner, ctx, fid, ring_size, system, **kwargs):
        args = {"file_id": str(fid), "ring_size": ring_size, "system": system, **kwargs}
        return run_tool_sync(runner(ctx, json.dumps(args).encode()))

    def test_solitaire_uk(self):
        ctx, store, fid = make_ctx()
        r = self._check(run_jewelry_create_solitaire_ring, ctx, fid, "N", "uk")
        assert "error" not in r

    def test_mens_eu(self):
        ctx, store, fid = make_ctx()
        r = self._check(run_jewelry_create_mens_band, ctx, fid, 54, "eu")
        assert "error" not in r

    def test_wedding_set_jp(self):
        ctx, store, fid = make_ctx()
        r = self._check(run_jewelry_create_wedding_set, ctx, fid, 13, "jp")
        assert "error" not in r

    def test_cocktail_au(self):
        ctx, store, fid = make_ctx()
        r = self._check(run_jewelry_create_cocktail_ring, ctx, fid, "P", "au")
        assert "error" not in r

    def test_bypass_us(self):
        ctx, store, fid = make_ctx()
        r = self._check(run_jewelry_create_bypass_ring, ctx, fid, 7, "us")
        assert "error" not in r

    def test_solitaire_jp(self):
        ctx, store, fid = make_ctx()
        r = self._check(run_jewelry_create_solitaire_ring, ctx, fid, 17, "jp")
        assert "error" not in r
