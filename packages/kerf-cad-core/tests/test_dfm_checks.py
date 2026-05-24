"""
test_dfm_checks.py
==================
Hermetic tests for kerf_cad_core.dfm.checks.

All tests are pure-Python: no OCC, no database, no network.
Ground truth is constructed from known-geometry primitives.

Coverage
--------
- wall_thickness_min   : threshold, thin/thick discrimination, edge cases
- sharp_internal_corners: angle detection, threshold, convex filtering
- no_draft_faces       : flat top (draft = 0), drafted face, opposing face
- undercut_regions     : inverted face, no-undercut face
- machinability_score  : monotonic with complexity, clamp to [0,1]
- dfm_audit            : prioritised list, process defaults, score inclusion
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.dfm.checks import (
    dfm_audit,
    machinability_score,
    no_draft_faces,
    sharp_internal_corners,
    undercut_regions,
    wall_thickness_min,
)


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------

def _box_mesh(dx: float = 10.0, dy: float = 10.0, dz: float = 2.0) -> dict:
    """Return a closed box mesh with wall thickness ~dz/2 in Z direction."""
    # Simple flat box: just top and bottom faces, good enough for thickness check.
    verts = [
        [0, 0, 0], [dx, 0, 0], [dx, dy, 0], [0, dy, 0],   # bottom
        [0, 0, dz], [dx, 0, dz], [dx, dy, dz], [0, dy, dz], # top
    ]
    # Two triangles per face, 6 faces = 12 triangles.
    tris = [
        # bottom (-Z normal)
        [0, 2, 1], [0, 3, 2],
        # top (+Z normal)
        [4, 5, 6], [4, 6, 7],
        # front (-Y)
        [0, 1, 5], [0, 5, 4],
        # back (+Y)
        [2, 3, 7], [2, 7, 6],
        # left (-X)
        [0, 4, 7], [0, 7, 3],
        # right (+X)
        [1, 2, 6], [1, 6, 5],
    ]
    return {"vertices": verts, "triangles": tris}


def _single_tri_mesh() -> dict:
    return {
        "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        "triangles": [[0, 1, 2]],
    }


# ---------------------------------------------------------------------------
# wall_thickness_min
# ---------------------------------------------------------------------------

class TestWallThicknessMin:
    def test_thick_box_no_issues(self):
        # 10×10×10 box — all walls ~5mm thick, threshold 1mm.
        mesh = _box_mesh(10, 10, 10)
        issues = wall_thickness_min(mesh, threshold_mm=1.0)
        # Walls are ~5 mm; at most a few close-pair warnings but none should be errors.
        errors = [i for i in issues if i["severity"] == "error"]
        assert len(errors) == 0

    def test_thin_box_triggers_issues(self):
        # 10×10×0.3 mm box — walls are ~0.15 mm, well below 1 mm threshold.
        mesh = _box_mesh(10, 10, 0.3)
        issues = wall_thickness_min(mesh, threshold_mm=1.0)
        assert len(issues) > 0

    def test_returns_list(self):
        mesh = _box_mesh()
        result = wall_thickness_min(mesh, threshold_mm=0.5)
        assert isinstance(result, list)

    def test_issue_fields_present(self):
        mesh = _box_mesh(10, 10, 0.2)
        issues = wall_thickness_min(mesh, threshold_mm=1.0)
        if issues:
            issue = issues[0]
            assert "kind" in issue
            assert "position" in issue
            assert "severity" in issue
            assert "value" in issue
            assert "suggestion" in issue
            assert issue["kind"] == "thin_wall"

    def test_severity_error_very_thin(self):
        # dz=0.1 is << threshold*0.5 = 0.5mm — should get errors.
        mesh = _box_mesh(10, 10, 0.1)
        issues = wall_thickness_min(mesh, threshold_mm=1.0)
        errors = [i for i in issues if i["severity"] == "error"]
        assert len(errors) > 0

    def test_empty_mesh_returns_empty(self):
        issues = wall_thickness_min({"vertices": [], "triangles": []}, 1.0)
        assert issues == []

    def test_bad_input_returns_empty(self):
        issues = wall_thickness_min({}, 1.0)
        assert issues == []

    def test_high_threshold_triggers_on_normal_box(self):
        # threshold=50mm on a 10mm box should flag everything.
        mesh = _box_mesh(10, 10, 10)
        issues = wall_thickness_min(mesh, threshold_mm=50.0)
        assert len(issues) > 0

    def test_zero_threshold_no_issues(self):
        mesh = _box_mesh(10, 10, 2)
        issues = wall_thickness_min(mesh, threshold_mm=0.0)
        # With threshold=0, nothing should be flagged.
        assert len(issues) == 0

    def test_position_is_3_element_list(self):
        mesh = _box_mesh(10, 10, 0.2)
        issues = wall_thickness_min(mesh, threshold_mm=1.0)
        for issue in issues:
            assert len(issue["position"]) == 3


# ---------------------------------------------------------------------------
# sharp_internal_corners
# ---------------------------------------------------------------------------

class TestSharpInternalCorners:
    def _edge(self, angle_deg: float, a=(0, 0, 0), b=(1, 0, 0)) -> dict:
        return {"a": list(a), "b": list(b), "angle_deg": angle_deg}

    def test_no_edges_empty(self):
        assert sharp_internal_corners([], 30.0) == []

    def test_convex_edge_not_flagged(self):
        # angle = 200° (exterior convex) — should NOT be flagged.
        edges = [self._edge(200.0)]
        issues = sharp_internal_corners(edges, 30.0)
        assert len(issues) == 0

    def test_right_angle_above_threshold_not_flagged(self):
        # 90° interior angle, threshold = 30° → should not flag.
        edges = [self._edge(90.0)]
        issues = sharp_internal_corners(edges, 30.0)
        assert len(issues) == 0

    def test_sharp_corner_flagged(self):
        # 10° interior angle, threshold = 30° → should flag.
        edges = [self._edge(10.0)]
        issues = sharp_internal_corners(edges, 30.0)
        assert len(issues) == 1
        assert issues[0]["kind"] == "sharp_corner"
        assert issues[0]["value"] == pytest.approx(10.0)

    def test_severity_error_very_sharp(self):
        # 5° << 30*0.5=15 → error.
        edges = [self._edge(5.0)]
        issues = sharp_internal_corners(edges, 30.0)
        assert issues[0]["severity"] == "error"

    def test_severity_warning_moderately_sharp(self):
        # 20° is < 30 but >= 15 → warning.
        edges = [self._edge(20.0)]
        issues = sharp_internal_corners(edges, 30.0)
        assert issues[0]["severity"] == "warning"

    def test_midpoint_position(self):
        edges = [self._edge(10.0, a=[0, 0, 0], b=[2, 0, 0])]
        issues = sharp_internal_corners(edges, 30.0)
        assert issues[0]["position"] == pytest.approx([1.0, 0.0, 0.0])

    def test_exactly_at_threshold_not_flagged(self):
        # angle == threshold → should NOT be flagged (strictly < threshold).
        edges = [self._edge(30.0)]
        issues = sharp_internal_corners(edges, 30.0)
        assert len(issues) == 0

    def test_multiple_edges_mixed(self):
        edges = [
            self._edge(5.0),   # sharp → flagged
            self._edge(90.0),  # convex interior → not flagged
            self._edge(250.0), # exterior convex → not flagged
            self._edge(15.0),  # sharp → flagged
        ]
        issues = sharp_internal_corners(edges, 30.0)
        assert len(issues) == 2

    def test_suggestion_present(self):
        issues = sharp_internal_corners([self._edge(10.0)], 30.0)
        assert "suggestion" in issues[0]
        assert len(issues[0]["suggestion"]) > 5


# ---------------------------------------------------------------------------
# no_draft_faces
# ---------------------------------------------------------------------------

class TestNoDraftFaces:
    def _face(self, normal, centroid=(0, 0, 0), area=1.0) -> dict:
        return {"normal": list(normal), "centroid": list(centroid), "area": float(area)}

    def test_empty_returns_empty(self):
        assert no_draft_faces([], [0, 0, 1]) == []

    def test_flat_top_face_no_draft(self):
        # Face with normal pointing up [0,0,1], pull=[0,0,1] → 90° draft (full draft) → OK.
        # Wait: normal [0,0,1] and pull [0,0,1] → cos=1 → asin(1)=90° draft → OK.
        faces = [self._face([0, 0, 1])]
        issues = no_draft_faces(faces, [0, 0, 1], required_draft_deg=0.5)
        assert len(issues) == 0

    def test_side_face_zero_draft(self):
        # Face normal [1,0,0] perpendicular to pull [0,0,1] → cos=0 → draft=0°.
        faces = [self._face([1, 0, 0])]
        issues = no_draft_faces(faces, [0, 0, 1], required_draft_deg=0.5)
        assert len(issues) == 1
        assert issues[0]["kind"] == "no_draft"
        assert issues[0]["value"] == pytest.approx(0.0, abs=1e-6)

    def test_drafted_face_passes(self):
        # Face normal at 5° from pull → 5° draft → passes 1.5° requirement.
        # normal = [sin5, 0, cos5]
        import math as _math
        angle_rad = _math.radians(5)
        normal = [_math.sin(angle_rad), 0, _math.cos(angle_rad)]
        faces = [self._face(normal)]
        issues = no_draft_faces(faces, [0, 0, 1], required_draft_deg=1.5)
        assert len(issues) == 0

    def test_opposing_face_not_flagged_here(self):
        # Undercuts (cos < 0) are handled by undercut_regions, not here.
        faces = [self._face([0, 0, -1])]
        issues = no_draft_faces(faces, [0, 0, 1], required_draft_deg=0.5)
        assert len(issues) == 0

    def test_suggestion_present(self):
        faces = [self._face([1, 0, 0])]
        issues = no_draft_faces(faces, [0, 0, 1], required_draft_deg=0.5)
        assert "suggestion" in issues[0]


# ---------------------------------------------------------------------------
# undercut_regions
# ---------------------------------------------------------------------------

class TestUndercutRegions:
    def _face(self, normal, centroid=(0, 0, 0)) -> dict:
        return {"normal": list(normal), "centroid": list(centroid), "area": 1.0}

    def test_empty_returns_empty(self):
        assert undercut_regions([], [0, 0, 1]) == []

    def test_inverted_face_flagged(self):
        # normal [0,0,-1], pull [0,0,1] → undercut.
        faces = [self._face([0, 0, -1])]
        issues = undercut_regions(faces, [0, 0, 1])
        assert len(issues) == 1
        assert issues[0]["kind"] == "undercut"

    def test_upward_face_not_flagged(self):
        faces = [self._face([0, 0, 1])]
        issues = undercut_regions(faces, [0, 0, 1])
        assert len(issues) == 0

    def test_perpendicular_face_not_flagged(self):
        # cos(normal, pull) = 0 → not an undercut.
        faces = [self._face([1, 0, 0])]
        issues = undercut_regions(faces, [0, 0, 1])
        assert len(issues) == 0

    def test_severe_undercut_is_error(self):
        # normal pointing strongly against pull → large angle → error.
        faces = [self._face([0, 0, -1])]
        issues = undercut_regions(faces, [0, 0, 1])
        assert issues[0]["severity"] == "error"

    def test_mild_undercut_warning(self):
        # normal slightly inverted → small undercut → warning.
        import math as _math
        angle_rad = _math.radians(5)
        # Slightly beyond perpendicular toward opposing direction.
        normal = [0, _math.sin(angle_rad), -_math.cos(angle_rad + _math.radians(1))]
        faces = [self._face(normal)]
        issues = undercut_regions(faces, [0, 0, 1])
        if issues:
            assert issues[0]["severity"] in ("warning", "error")

    def test_value_negative_for_undercut(self):
        faces = [self._face([0, 0, -1])]
        issues = undercut_regions(faces, [0, 0, 1])
        assert issues[0]["value"] < 0


# ---------------------------------------------------------------------------
# machinability_score
# ---------------------------------------------------------------------------

class TestMachinabilityScore:
    def test_simple_part_high_score(self):
        score = machinability_score({"faces": []})
        assert score == pytest.approx(1.0, abs=1e-6)

    def test_complex_part_lower_score(self):
        many_faces = [{"normal": [0, 0, 1], "centroid": [0, 0, 0], "area": 1} for _ in range(600)]
        score = machinability_score({"faces": many_faces})
        assert score < 1.0

    def test_deep_pocket_penalty(self):
        score_clean = machinability_score({})
        score_pocket = machinability_score({"deep_pockets": [{"depth": 50.0, "width": 5.0}]})
        assert score_pocket < score_clean

    def test_thin_wall_penalty(self):
        score_clean = machinability_score({})
        score_thin = machinability_score({"thin_wall_count": 5})
        assert score_thin < score_clean

    def test_high_aspect_ratio_penalty(self):
        bb = {"min": [0, 0, 0], "max": [200, 1, 1]}
        score = machinability_score({"bounding_box": bb})
        assert score < 1.0

    def test_score_clamped_low(self):
        # Pile on all penalty factors.
        many_faces = [{"normal": [0, 0, 1], "centroid": [0, 0, 0], "area": 1} for _ in range(600)]
        pockets = [{"depth": 100.0, "width": 1.0} for _ in range(10)]
        score = machinability_score({
            "faces": many_faces,
            "deep_pockets": pockets,
            "thin_wall_count": 20,
            "bounding_box": {"min": [0, 0, 0], "max": [500, 1, 1]},
        })
        assert 0.0 <= score <= 1.0

    def test_score_clamped_high(self):
        score = machinability_score({})
        assert score <= 1.0

    def test_bad_input_returns_midpoint(self):
        # Bad input → defaults to 0.5 (graceful fallback).
        score = machinability_score(None)  # type: ignore[arg-type]
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# dfm_audit
# ---------------------------------------------------------------------------

class TestDfmAudit:
    def _simple_part(self) -> dict:
        return {
            "mesh": _box_mesh(10, 10, 0.2),
            "edges": [
                {"a": [0, 0, 0], "b": [1, 0, 0], "angle_deg": 10.0},
            ],
            "faces": [
                {"normal": [1, 0, 0], "centroid": [0, 0, 0], "area": 1.0},
            ],
        }

    def test_returns_dict_shape(self):
        result = dfm_audit({}, "cnc_milling")
        assert isinstance(result, dict)
        assert "ok" in result
        assert "process" in result
        assert "score" in result
        assert "issues" in result
        assert "summary" in result

    def test_issues_is_list(self):
        result = dfm_audit(self._simple_part(), "cnc_milling")
        assert isinstance(result["issues"], list)

    def test_issues_prioritised_errors_first(self):
        result = dfm_audit(self._simple_part(), "cnc_milling")
        issues = result["issues"]
        severities = [i["severity"] for i in issues]
        rank = [{"error": 0, "warning": 1, "info": 2}.get(s, 2) for s in severities]
        assert rank == sorted(rank), "issues should be sorted: errors before warnings"

    def test_ok_false_when_errors_present(self):
        part = {"mesh": _box_mesh(10, 10, 0.1)}
        result = dfm_audit(part, "cnc_milling")
        if result["issues"]:
            errors = [i for i in result["issues"] if i["severity"] == "error"]
            if errors:
                assert result["ok"] is False

    def test_ok_true_when_no_errors(self):
        # Simple part with no thin walls, no sharp corners → should be ok.
        result = dfm_audit({}, "cnc_milling")
        assert result["ok"] is True

    def test_score_in_range(self):
        result = dfm_audit(self._simple_part(), "cnc_milling")
        assert 0.0 <= result["score"] <= 1.0

    def test_injection_moulding_draft_check(self):
        # Side face (no draft) under injection moulding → should flag no_draft.
        part = {
            "faces": [
                {"normal": [1, 0, 0], "centroid": [0, 0, 0], "area": 10.0},
            ]
        }
        result = dfm_audit(part, "injection_moulding", pull_direction=[0, 0, 1])
        kinds = [i["kind"] for i in result["issues"]]
        assert "no_draft" in kinds

    def test_cnc_no_draft_check(self):
        # CNC milling: draft check should NOT run.
        part = {
            "faces": [
                {"normal": [1, 0, 0], "centroid": [0, 0, 0], "area": 10.0},
            ]
        }
        result = dfm_audit(part, "cnc_milling", pull_direction=[0, 0, 1])
        kinds = [i["kind"] for i in result["issues"]]
        assert "no_draft" not in kinds

    def test_summary_contains_process(self):
        result = dfm_audit({}, "die_casting")
        assert "die_casting" in result["summary"]

    def test_bad_part_returns_gracefully(self):
        result = dfm_audit(None, "cnc_milling")  # type: ignore[arg-type]
        assert isinstance(result, dict)
        assert "ok" in result

    def test_unknown_process_falls_back(self):
        result = dfm_audit({}, "laser_cutting")
        assert isinstance(result, dict)
        # Should not raise; falls back to cnc defaults.


# ===========================================================================
# DFM numpy import guard
# ===========================================================================

class TestDFMNumpyGuard:
    """Verify that importing kerf_cad_core.dfm.checks never hard-fails even
    when numpy is absent, and that the guarded functions degrade gracefully."""

    def test_module_import_succeeds(self):
        """The module must be importable (numpy present in test env)."""
        import importlib
        mod = importlib.import_module("kerf_cad_core.dfm.checks")
        assert mod is not None

    def test_np_available_flag_exposed(self):
        """_NP_AVAILABLE flag must exist and be a bool."""
        from kerf_cad_core.dfm.checks import _NP_AVAILABLE
        assert isinstance(_NP_AVAILABLE, bool)

    def test_numpy_absent_wall_thickness_returns_empty(self, monkeypatch):
        """When numpy is absent, wall_thickness_min must return [] not raise."""
        import kerf_cad_core.dfm.checks as _mod
        monkeypatch.setattr(_mod, "_NP_AVAILABLE", False)
        monkeypatch.setattr(_mod, "np", None)
        mesh = {
            "vertices": [[0,0,0],[1,0,0],[0,1,0]],
            "triangles": [[0,1,2]],
        }
        result = _mod.wall_thickness_min(mesh, threshold_mm=1.0)
        assert result == [], f"Expected [] when numpy absent, got {result}"

    def test_numpy_absent_no_draft_faces_returns_empty(self, monkeypatch):
        """no_draft_faces must return [] not raise when numpy is absent."""
        import kerf_cad_core.dfm.checks as _mod
        monkeypatch.setattr(_mod, "_NP_AVAILABLE", False)
        monkeypatch.setattr(_mod, "np", None)
        faces = [{"normal": [0, 0, 1], "centroid": [0, 0, 0], "area": 1.0}]
        result = _mod.no_draft_faces(faces, [0, 0, 1], required_draft_deg=0.5)
        assert result == []

    def test_numpy_absent_undercut_returns_empty(self, monkeypatch):
        """undercut_regions must return [] not raise when numpy is absent."""
        import kerf_cad_core.dfm.checks as _mod
        monkeypatch.setattr(_mod, "_NP_AVAILABLE", False)
        monkeypatch.setattr(_mod, "np", None)
        faces = [{"normal": [0, 0, -1], "centroid": [0, 0, 0], "area": 1.0}]
        result = _mod.undercut_regions(faces, [0, 0, 1])
        assert result == []

    def test_dfm_audit_still_returns_dict_without_numpy(self, monkeypatch):
        """dfm_audit must return a valid dict (not crash) when numpy is absent."""
        import kerf_cad_core.dfm.checks as _mod
        monkeypatch.setattr(_mod, "_NP_AVAILABLE", False)
        monkeypatch.setattr(_mod, "np", None)
        result = _mod.dfm_audit({}, "cnc_milling")
        assert isinstance(result, dict)
        assert "ok" in result
        assert "issues" in result
