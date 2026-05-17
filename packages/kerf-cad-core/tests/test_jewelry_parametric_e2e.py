"""End-to-end integration test for the jewelry workflow through the new
parametric history DAG (GK P3 keystone).

This test wires the just-landed parametric kernel (box/cylinder primitives,
boolean, chamfer + rolling-ball fillet emitting a Body, persistent face
naming) against the real jewelry-vertical analyses (carat sizing, gem-seat
geometry, prong-head layout, metal-cost weight, casting-weight allowance,
appraisal, CAD QC audit).

The keystone assertion: edit the ring band thickness via dag.set_param(...)
→ regenerate() → the chamfer + fillet's persistent face role set is
identical pre/post, and the metal weight scales correctly with the new
Body volume.

Hermetic — no network, no OCCT, no third-party files.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kerf_cad_core.geom.brep import validate_body
from kerf_cad_core.geom.history import (
    BooleanFeature,
    BoxFeature,
    ChamferEdgeFeature,
    CylinderFeature,
    FeatureDAG,
    FeatureRef,
    FilletEdgeFeature,
    PersistentSelector,
    register_default_evaluators,
)

from kerf_cad_core.jewelry.appraisal import AppraisalConfig, appraise, value_summary
from kerf_cad_core.jewelry.cad_qc import cad_qc
from kerf_cad_core.jewelry.gem_seat import seat_geometry
from kerf_cad_core.jewelry.gemstones import carat_from_mm, mm_from_carat
from kerf_cad_core.jewelry.metal_cost import (
    casting_weight,
    metal_weight,
)
from kerf_cad_core.jewelry.production import production_weights
from kerf_cad_core.jewelry.settings import build_prong_head_node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _body_volume_mm3(body) -> float:
    """Estimate the volume of an axis-aligned-friendly Body in mm^3.

    Uses the divergence theorem over the outer loops of each face: V =
    (1/6) * |sum p . (a x b)| over triangles fanned from each face's first
    vertex. Good enough for our box/cylinder topologies (and well-tested
    against the existing GK test fixture).
    """
    vol = 0.0
    for face in body.all_faces():
        outer = face.outer_loop()
        if outer is None or len(outer.coedges) < 3:
            continue
        pts = [np.asarray(ce.start_point(), dtype=float) for ce in outer.coedges]
        p0 = pts[0]
        for i in range(1, len(pts) - 1):
            a = pts[i] - p0
            b = pts[i + 1] - p0
            cross = np.cross(a, b)
            vol += float(np.dot(p0, cross))
    return abs(vol) / 6.0


def _fresh_dag() -> FeatureDAG:
    dag = FeatureDAG()
    register_default_evaluators(dag)
    return dag


# ---------------------------------------------------------------------------
# Realistic engagement-ring build via the parametric DAG
# ---------------------------------------------------------------------------
#
# The shank is modelled as a small rectangular bar (a "signet-ring-style"
# stylised band) that is the easiest topology for which the kernel offers
# robust chamfer + fillet evaluators. We do not use the production
# ring-shank torus builder here because the GK P3 evaluator set covers
# axis-aligned primitives + booleans; the keystone test is about the DAG
# correctness, not the visual quality of the shank.
#
# Dimensions (mm):
#   - band outer "box" : 22.0 x 6.0 x 2.0  (a wide signet band approximation)
#   - we run a chamfer on the top-front edge and a fillet on the inside edge
#   - then a 1.0 ct round brilliant stone drives the seat + prong head
#
# Whole-piece weight = volume(body) * density(metal).
# ---------------------------------------------------------------------------


_BAND_DX_INITIAL = 22.0   # mm — wide axis (ring "length")
_BAND_DY = 6.0            # mm — band thickness across the finger axis
_BAND_DZ = 2.0            # mm — band height (axial)
_CHAMFER_W = 0.15         # mm
_FILLET_R = 0.20          # mm


def _build_ring_dag(band_dx: float = _BAND_DX_INITIAL):
    dag = _fresh_dag()

    band = BoxFeature((0.0, 0.0, 0.0), band_dx, _BAND_DY, _BAND_DZ)
    dag.add_feature(band)
    dag.evaluate(band.id)

    # Chamfer the top-front edge: between +Z face and -Y face.
    chamfer_sel = PersistentSelector(
        feature_id=band.id, entity_kind="edge", role="+Z/-Y"
    )
    chamf = ChamferEdgeFeature(
        body=FeatureRef(band.id),
        edge=chamfer_sel,
        width=_CHAMFER_W,
    )
    dag.add_feature(chamf)
    dag.evaluate(chamf.id)

    # Fillet the bottom-front edge: between -Z face and -Y face.
    fillet_sel = PersistentSelector(
        feature_id=band.id, entity_kind="edge", role="-Y/-Z"
    )
    fillet = FilletEdgeFeature(
        body=FeatureRef(band.id),
        edge=fillet_sel,
        radius=_FILLET_R,
    )
    dag.add_feature(fillet)
    dag.evaluate(fillet.id)

    return dag, band, chamf, fillet


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ring_dag_builds_three_valid_features():
    """DAG-1: the four-feature ring graph evaluates clean.

    Three valid Body outputs, each survives validate_body.
    """
    dag, band, chamf, fillet = _build_ring_dag()
    band_body = dag.evaluate(band.id)
    chamf_body = dag.evaluate(chamf.id)
    fillet_body = dag.evaluate(fillet.id)

    assert band_body is not None
    assert chamf_body is not None
    assert fillet_body is not None

    assert validate_body(band_body)["ok"]
    assert validate_body(chamf_body)["ok"]
    assert validate_body(fillet_body)["ok"]


def test_chamfer_topology_increment():
    """DAG-2: chamfer adds +2V +3E +1F over the box's 8/12/6 baseline."""
    dag, _band, chamf, _fillet = _build_ring_dag()
    body = dag.evaluate(chamf.id)
    c = body.euler_counts()
    assert c["V"] == 10
    assert c["E"] == 15
    assert c["F"] == 7


def test_fillet_emits_named_fillet_face():
    """DAG-3: rolling-ball fillet output carries a fillet:<role> face name."""
    dag, _band, _chamf, fillet = _build_ring_dag()
    dag.evaluate(fillet.id)
    table = dag.naming_table(fillet.id)
    fillet_roles = [r for r in table.faces.keys() if r.startswith("fillet:")]
    assert len(fillet_roles) >= 1, (
        f"expected fillet:<role> in face roles, got {list(table.faces.keys())}"
    )


def test_jewelry_volume_drives_metal_weight():
    """DAG-4: metal_weight() of the chamfered+filleted body is consistent
    with the underlying solid's geometric volume.

    For 18k yellow gold (ρ ≈ 15.6 g/cm^3) on a ~264 mm^3 band the expected
    weight is on the order of 4.1 g; we assert it is positive and within
    a generous 20% of the nominal (volume * density).
    """
    dag, _band, _chamf, fillet = _build_ring_dag()
    body = dag.evaluate(fillet.id)
    vol_mm3 = _body_volume_mm3(body)
    assert vol_mm3 > 0.0

    mw = metal_weight(vol_mm3, metal="18k_yellow")
    assert mw["grams"] > 0.0
    assert mw["density_g_cm3"] > 14.0  # 18k yellow ≈ 15.6
    # Reasonableness: grams ≈ vol_cm3 * density
    vol_cm3 = vol_mm3 / 1000.0
    expected_g = vol_cm3 * mw["density_g_cm3"]
    assert abs(mw["grams"] - expected_g) < 1e-6


def test_carat_round_trip_consistency():
    """JEW-1: carat_from_mm + mm_from_carat round-trip for round brilliant."""
    # 6.5 mm diamond ≈ 1.00 ct
    ct = carat_from_mm("round_brilliant", 6.5)
    assert 0.85 < ct < 1.15
    back_mm = mm_from_carat("round_brilliant", ct)
    assert abs(back_mm - 6.5) < 0.05


def test_seat_geometry_for_one_carat_stone():
    """JEW-2: seat_geometry uses the stone diameter and basic angles."""
    stone_mm = 6.5
    seat = seat_geometry(
        cut="round_brilliant",
        diameter_mm=stone_mm,
        pavilion_angle_deg=40.75,
        pavilion_depth_pct=43.1,
        girdle_pct=2.5,
        crown_angle_deg=34.0,
    )
    assert seat["girdle_radius_mm"] > stone_mm / 2.0
    assert seat["pavilion_depth_mm"] > 0.0
    assert seat["total_cutter_depth_mm"] > seat["pavilion_depth_mm"]


def test_prong_head_layout():
    """JEW-3: prong-head node has 4 prongs with positive geometry."""
    head = build_prong_head_node(
        node_id="head_4p",
        stone_diameter=6.5,
        prong_count=4,
        prong_wire_diameter=0.9,
        prong_height=2.6,
        head_style="basket",
        basket_rail_count=1,
        seat_angle_deg=15.0,
    )
    assert head["prong_count"] == 4
    assert head["_head_outer_diameter"] > 6.5
    assert head["_seat_depth"] > 0.0


def test_appraisal_total_value_chain():
    """JEW-4: appraise() produces a positive replacement value for a
    canonical 18k diamond solitaire.
    """
    piece = {
        "id": "test-ring-001",
        "description": "Parametric 18k YG diamond ring",
        "piece_type": "ring",
        "metal": {
            "alloy": "18k_yellow",
            "weight_grams": 4.2,
            "spot_price_per_gram": 60.0,
            "fabrication_per_gram": 6.0,
        },
        "stones": [
            {
                "id": "ds1",
                "stone_type": "diamond",
                "cut": "round_brilliant",
                "carat": 1.0,
                "color_grade": "G",
                "clarity_grade": "VS1",
                "measurements_mm": {"length": 6.5, "width": 6.5, "depth": 4.0},
                "setting_type": "prong",
                "price_per_carat": 9000.0,
            }
        ],
        "labor_value": 250.0,
    }
    result = appraise(piece, AppraisalConfig())
    assert result["base_value"] > 0
    assert result["replacement_value"] >= result["base_value"]
    assert result["fair_market_value"] <= result["replacement_value"]
    assert result["liquidation_value"] <= result["fair_market_value"]

    summary = value_summary(result)
    # value_summary uses short keys: base / fair_market / liquidation / currency
    assert summary["base"] > 0
    assert summary["currency"]


def test_cad_qc_passes_clean_model():
    """JEW-5: cad_qc() returns ready for a clean jewelry model."""
    model = {
        "process": "cast",
        "alloy": "18k_yellow",
        "walls": [{"id": "w1", "thickness_mm": 1.2}],
        "prongs": [
            {"id": "p1", "base_mm": 0.9, "tip_mm": 0.5, "height_mm": 2.5},
        ],
        "stones": [
            {
                "id": "s1",
                "girdle_mm": 6.5,
                "seat_depth_mm": 2.0,
                "clearance_to_neighbor_mm": 1.0,
                "clearance_to_edge_mm": 0.8,
            }
        ],
        "topology": {"is_manifold": True, "naked_edge_count": 0},
        "weight_g": 4.2,
        "target_weight_g": 4.2,
    }
    report = cad_qc(model)
    assert report["ok"] is True
    assert report.get("verdict") in ("ready", "rework", "n/a")
    # All FAILs (if any) must come from genuine geometry — for this clean
    # model we expect zero FAIL items.
    fails = [r for r in report.get("results", []) if r.get("severity") == "FAIL"]
    assert fails == [], f"expected clean model to have no FAILs, got {fails}"


def test_production_weights_scale_with_volume():
    """JEW-6: production_weights wax+metal weights both > 0 and metal >
    wax (gold is much denser than wax).
    """
    pw = production_weights(piece_volume_mm3=300.0, alloy_key="18k_yellow")
    assert pw["wax_weight_g"] > 0.0
    assert pw["metal_weight_g"] > pw["wax_weight_g"]


def test_casting_weight_allowance():
    """JEW-7: casting_weight() applies a positive allowance gross > net."""
    net = 4.5
    cw = casting_weight(net, casting_allowance_pct=15.0)
    assert cw["gross_grams"] > net
    assert abs(cw["gross_grams"] - net * 1.15) < 1e-9


# ===========================================================================
# Keystone DAG test: edit upstream → downstream persistent ids stable
# ===========================================================================


def test_keystone_resize_preserves_persistent_face_roles():
    """KEYSTONE-1: change band_dx (ring "size") → regenerate → fillet's
    + chamfer's set of face role keys stay identical pre/post.
    """
    dag, band, chamf, fillet = _build_ring_dag(band_dx=_BAND_DX_INITIAL)
    dag.evaluate(fillet.id)

    chamf_roles_before = set(dag.naming_table(chamf.id).faces.keys())
    fillet_roles_before = set(dag.naming_table(fillet.id).faces.keys())

    # Resize the ring — model a sizing-up bump in band length
    new_dx = _BAND_DX_INITIAL + 4.0  # +4 mm
    dag.set_param(band.id, "dx", new_dx)
    dag.regenerate()

    body_after = dag.evaluate(fillet.id)
    assert validate_body(body_after)["ok"]

    chamf_roles_after = set(dag.naming_table(chamf.id).faces.keys())
    fillet_roles_after = set(dag.naming_table(fillet.id).faces.keys())

    assert chamf_roles_after == chamf_roles_before, (
        f"chamfer face role set changed: "
        f"before={chamf_roles_before} after={chamf_roles_after}"
    )
    assert fillet_roles_after == fillet_roles_before, (
        f"fillet face role set changed: "
        f"before={fillet_roles_before} after={fillet_roles_after}"
    )


def test_keystone_resize_scales_metal_weight_linearly_in_dx():
    """KEYSTONE-2: enlarging dx grows the body's volume proportionally,
    hence the metal weight grows accordingly.
    """
    dag, band, _chamf, fillet = _build_ring_dag(band_dx=_BAND_DX_INITIAL)
    body_before = dag.evaluate(fillet.id)
    vol_before = _body_volume_mm3(body_before)
    g_before = metal_weight(vol_before, metal="18k_yellow")["grams"]

    new_dx = _BAND_DX_INITIAL + 4.0
    dag.set_param(band.id, "dx", new_dx)
    dag.regenerate()
    body_after = dag.evaluate(fillet.id)
    vol_after = _body_volume_mm3(body_after)
    g_after = metal_weight(vol_after, metal="18k_yellow")["grams"]

    # The "extra slab" is a chamfered+filleted band, but for the
    # axis-aligned add along dx the inner edges are unchanged — the volume
    # increase is approximately the new-slab volume of (Δdx · dy · dz)
    # minus small chamfer/fillet corrections. We assert the volume grew
    # by AT LEAST 80% of the geometric box delta (a generous lower bound
    # that absorbs the chamfer/fillet bite).
    box_delta_mm3 = (new_dx - _BAND_DX_INITIAL) * _BAND_DY * _BAND_DZ
    delta_vol = vol_after - vol_before
    assert delta_vol > 0.80 * box_delta_mm3, (
        f"vol delta {delta_vol:.3f} not >= 0.80 * {box_delta_mm3:.3f}"
    )
    # And weight scales with volume * density (linear).
    assert g_after > g_before
    # Density ratio is exact: g_after / g_before should equal vol_after / vol_before
    vol_ratio = vol_after / vol_before
    weight_ratio = g_after / g_before
    assert abs(weight_ratio - vol_ratio) < 1e-9


# ===========================================================================
# Cross-module pipeline assertion: weight -> casting -> appraise -> qc
# ===========================================================================


def test_full_pipeline_weight_to_appraisal():
    """X-MODULE: pipeline volume → metal_weight → casting_weight →
    production_weights → appraise; all values are mutually consistent.
    """
    dag, _band, _chamf, fillet = _build_ring_dag()
    body = dag.evaluate(fillet.id)
    vol_mm3 = _body_volume_mm3(body)

    mw = metal_weight(vol_mm3, metal="18k_yellow")
    cw = casting_weight(mw["grams"], casting_allowance_pct=15.0)
    pw = production_weights(vol_mm3, "18k_yellow")

    # The production_weights metal calculation must match metal_weight
    # for the same volume + alloy.
    assert abs(pw["metal_weight_g"] - mw["grams"]) < 1e-3

    # Build an appraisal piece using the DAG-derived weight
    piece = {
        "description": "Parametric-DAG ring (1ct VG)",
        "piece_type": "ring",
        "metal": {
            "alloy": "18k_yellow",
            "weight_grams": mw["grams"],
            "spot_price_per_gram": 60.0,
            "fabrication_per_gram": 6.0,
        },
        "stones": [
            {
                "id": "s1",
                "stone_type": "diamond",
                "cut": "round_brilliant",
                "carat": 1.0,
                "color_grade": "G",
                "clarity_grade": "VS1",
                "measurements_mm": {"length": 6.5, "width": 6.5, "depth": 4.0},
                "setting_type": "prong",
                "price_per_carat": 9000.0,
            }
        ],
        "labor_value": 200.0,
    }
    appraisal = appraise(piece, AppraisalConfig())
    assert appraisal["base_value"] > 0
    # Casting gross weight > net weight (positive allowance)
    assert cw["gross_grams"] > mw["grams"]


def test_resize_propagates_to_appraisal_value():
    """X-MODULE: after a parametric resize, the rebuilt appraisal value
    is strictly greater (more metal → higher base value when stone is fixed)."""
    dag, band, _chamf, fillet = _build_ring_dag()
    body_before = dag.evaluate(fillet.id)
    vol_before = _body_volume_mm3(body_before)
    g_before = metal_weight(vol_before, metal="18k_yellow")["grams"]

    def _appraise(weight_g):
        return appraise(
            {
                "description": "Param ring",
                "piece_type": "ring",
                "metal": {
                    "alloy": "18k_yellow",
                    "weight_grams": weight_g,
                    "spot_price_per_gram": 60.0,
                    "fabrication_per_gram": 6.0,
                },
                "stones": [
                    {
                        "id": "s1",
                        "stone_type": "diamond",
                        "cut": "round_brilliant",
                        "carat": 1.0,
                        "color_grade": "G",
                        "clarity_grade": "VS1",
                        "setting_type": "prong",
                        "price_per_carat": 9000.0,
                    }
                ],
                "labor_value": 200.0,
            },
            AppraisalConfig(),
        )

    appr_before = _appraise(g_before)

    new_dx = _BAND_DX_INITIAL + 6.0
    dag.set_param(band.id, "dx", new_dx)
    dag.regenerate()
    body_after = dag.evaluate(fillet.id)
    vol_after = _body_volume_mm3(body_after)
    g_after = metal_weight(vol_after, metal="18k_yellow")["grams"]
    appr_after = _appraise(g_after)

    # Bigger band → bigger metal value → bigger base_value
    assert appr_after["base_value"] > appr_before["base_value"]


def test_resize_does_not_break_cad_qc():
    """X-MODULE: post-resize cad_qc still produces an ok-True report (the
    band is still well within castable wall thresholds)."""
    dag, band, _chamf, fillet = _build_ring_dag()
    dag.set_param(band.id, "dx", _BAND_DX_INITIAL + 8.0)
    dag.regenerate()
    body = dag.evaluate(fillet.id)
    vol_mm3 = _body_volume_mm3(body)
    mw = metal_weight(vol_mm3, metal="18k_yellow")

    qc_report = cad_qc(
        {
            "process": "cast",
            "alloy": "18k_yellow",
            "walls": [{"id": "band", "thickness_mm": _BAND_DZ}],  # 2.0 mm
            "topology": {"is_manifold": True, "naked_edge_count": 0},
            "weight_g": mw["grams"],
        }
    )
    assert qc_report["ok"] is True
    fails = [r for r in qc_report.get("results", []) if r.get("severity") == "FAIL"]
    assert fails == []


# ===========================================================================
# Cache + DAG-bookkeeping invariants under the jewelry workflow
# ===========================================================================


def test_independent_chamfer_and_fillet_cache_independence():
    """CACHE-1: the chamfer feature does not re-evaluate when the fillet
    feature is touched (siblings on the band share the upstream)."""
    dag, _band, chamf, fillet = _build_ring_dag()
    dag.evaluate(chamf.id)
    dag.evaluate(fillet.id)

    # Touching fillet (no param change) → no re-evaluation of chamf.
    _, counts = dag.evaluate_with_counter(chamf.id)
    assert counts.get(chamf.id, 0) == 0


def test_dag_serialise_round_trip():
    """SERIAL-1: dag.to_dict() round-trips the four-feature ring graph."""
    dag, _band, _chamf, _fillet = _build_ring_dag()
    snap = dag.to_dict()
    assert "features" in snap
    assert len(snap["features"]) == 3
    kinds = sorted(f["kind"] for f in snap["features"])
    assert kinds == ["box", "chamfer_edge", "fillet_edge"]


def test_topo_order_is_box_chamfer_fillet():
    """DAG-INVARIANT: topological order places the band before both
    chamfer and fillet."""
    dag, band, chamf, fillet = _build_ring_dag()
    order = dag.topological_order()
    assert order.index(band.id) < order.index(chamf.id)
    assert order.index(band.id) < order.index(fillet.id)
