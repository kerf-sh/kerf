"""Hermetic tests for POST /api/composites/clt and /api/composites/failure.

No DB, no network.  kerf_cad_core must be on sys.path (conftest.py handles this).
"""
from __future__ import annotations

import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kerf_api.routes_composites import router


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


# ---------------------------------------------------------------------------
# T300/5208 graphite-epoxy reference material (Jones, 2nd ed., Table 2-1)
# ---------------------------------------------------------------------------
E1 = 181e9
E2 = 10.3e9
NU12 = 0.28
G12 = 7.17e9

T300 = {
    "E1": E1, "E2": E2, "nu12": NU12, "G12": G12,
    "thickness": 0.125e-3, "angle_deg": 0.0,
}

STRENGTHS = {
    "F1t": 1500e6, "F1c": 1500e6,
    "F2t": 40e6,   "F2c": 246e6,
    "F12": 68e6,
}


def _ply(angle_deg):
    return {**T300, "angle_deg": angle_deg}


# ===========================================================================
# CLT endpoint
# ===========================================================================

class TestCLT:

    def test_single_ply_returns_200(self, client):
        """Single 0° ply → 200 with ok=True."""
        r = client.post("/api/composites/clt", json={
            "plies": [T300],
        })
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_abd_matrices_present(self, client):
        """Response contains A, B, D and ABD matrices."""
        r = client.post("/api/composites/clt", json={
            "plies": [T300],
        })
        body = r.json()
        for key in ("A", "B", "D", "ABD"):
            assert key in body, f"Missing key: {key}"

    def test_a_matrix_is_9_elements(self, client):
        """A matrix is a flat 9-element list."""
        r = client.post("/api/composites/clt", json={
            "plies": [T300],
        })
        body = r.json()
        assert isinstance(body["A"], list)
        assert len(body["A"]) == 9

    def test_abd_is_6x6(self, client):
        """ABD is a 6×6 matrix (list of 6 lists of 6)."""
        r = client.post("/api/composites/clt", json={
            "plies": [T300],
        })
        body = r.json()
        abd = body["ABD"]
        assert len(abd) == 6
        for row in abd:
            assert len(row) == 6

    def test_total_thickness_correct(self, client):
        """total_thickness = sum of ply thicknesses."""
        plies = [_ply(0), _ply(90), _ply(0)]
        r = client.post("/api/composites/clt", json={"plies": plies})
        body = r.json()
        expected = 3 * 0.125e-3
        assert abs(body["total_thickness"] - expected) / expected < 1e-9

    def test_n_plies_correct(self, client):
        """n_plies matches the number of plies supplied."""
        plies = [_ply(a) for a in [0, 45, -45, 90, 90, -45, 45, 0]]
        r = client.post("/api/composites/clt", json={"plies": plies})
        body = r.json()
        assert body["n_plies"] == 8

    def test_symmetric_laminate_flagged(self, client):
        """[0/90]_s → is_symmetric=True."""
        plies = [_ply(0), _ply(90), _ply(90), _ply(0)]
        r = client.post("/api/composites/clt", json={"plies": plies})
        body = r.json()
        assert body["is_symmetric"] is True

    def test_response_null_when_no_nm(self, client):
        """Without N_M the response field is null."""
        r = client.post("/api/composites/clt", json={"plies": [T300]})
        body = r.json()
        assert body.get("response") is None

    def test_response_present_with_nm(self, client):
        """With N_M supplied the response dict is non-null."""
        plies = [_ply(0), _ply(90), _ply(90), _ply(0)]
        r = client.post("/api/composites/clt", json={
            "plies": plies,
            "N_M": [1000.0, 0, 0, 0, 0, 0],
        })
        body = r.json()
        assert body["response"] is not None
        assert "epsilon0" in body["response"]
        assert "kappa" in body["response"]

    def test_uniaxial_nx_gives_positive_epsilon_x(self, client):
        """[0/90]_s under Nx=1000 N/m → ε_x > 0."""
        plies = [_ply(0), _ply(90), _ply(90), _ply(0)]
        r = client.post("/api/composites/clt", json={
            "plies": plies,
            "N_M": [1000.0, 0, 0, 0, 0, 0],
        })
        body = r.json()
        assert body["response"]["epsilon0"][0] > 0

    def test_symmetric_laminate_no_curvature_under_n(self, client):
        """Symmetric laminate under pure N → κ ≈ 0."""
        plies = [_ply(0), _ply(90), _ply(90), _ply(0)]
        r = client.post("/api/composites/clt", json={
            "plies": plies,
            "N_M": [1000.0, 0, 0, 0, 0, 0],
        })
        kappa = r.json()["response"]["kappa"]
        for k in kappa:
            assert abs(k) < 1e-3

    def test_empty_plies_returns_422(self, client):
        """Empty plies list → 422."""
        r = client.post("/api/composites/clt", json={"plies": []})
        assert r.status_code == 422

    def test_wrong_nm_length_returns_422(self, client):
        """N_M with wrong length → 422."""
        r = client.post("/api/composites/clt", json={
            "plies": [T300],
            "N_M": [1.0, 2.0, 3.0],  # should be 6
        })
        assert r.status_code == 422

    def test_missing_plies_field_returns_422(self, client):
        """Missing 'plies' field → 422."""
        r = client.post("/api/composites/clt", json={})
        assert r.status_code == 422

    def test_z_coords_correct_length(self, client):
        """z_coords has n_plies + 1 entries."""
        plies = [_ply(a) for a in [0, 45, -45, 90]]
        r = client.post("/api/composites/clt", json={"plies": plies})
        body = r.json()
        assert len(body["z_coords"]) == body["n_plies"] + 1

    def test_quasi_isotropic_a11_approx_a22(self, client):
        """[0/±45/90]_s quasi-isotropic: A11 ≈ A22 within 1%."""
        plies = [_ply(a) for a in [0, 45, -45, 90, 90, -45, 45, 0]]
        r = client.post("/api/composites/clt", json={"plies": plies})
        A = r.json()["A"]
        assert abs(A[0] - A[4]) / A[0] < 0.01


# ===========================================================================
# Failure index endpoint
# ===========================================================================

class TestCompositesFailure:

    def test_no_load_no_failure(self, client):
        """Zero stress/strain → ok=True, failed=False."""
        r = client.post("/api/composites/failure", json={
            "stress_material": [0.0, 0.0, 0.0],
            "strain_material": [0.0, 0.0, 0.0],
            "strengths": STRENGTHS,
        })
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert body.get("failed") is False

    def test_fibre_tension_onset_max_stress(self, client):
        """σ1 = F1t → max-stress F.I. = 1.0 (onset)."""
        r = client.post("/api/composites/failure", json={
            "stress_material": [1500e6, 0.0, 0.0],
            "strain_material": [1500e6 / 181e9, 0.0, 0.0],
            "strengths": STRENGTHS,
            "criteria": ["max-stress"],
        })
        assert r.status_code == 200
        body = r.json()
        assert abs(body["max_stress"]["fi"] - 1.0) < 1e-6

    def test_fibre_tension_failure_above_strength(self, client):
        """σ1 = 2×F1t → max-stress F.I. > 1 (failure)."""
        r = client.post("/api/composites/failure", json={
            "stress_material": [3000e6, 0.0, 0.0],
            "strain_material": [3000e6 / 181e9, 0.0, 0.0],
            "strengths": STRENGTHS,
            "criteria": ["max-stress"],
        })
        body = r.json()
        assert body["max_stress"]["fi"] > 1.0
        assert body["max_stress"]["failed"] is True

    def test_tsai_wu_below_strength_no_failure(self, client):
        """Low biaxial stress → Tsai-Wu F.I. < 1."""
        r = client.post("/api/composites/failure", json={
            "stress_material": [100e6, 10e6, 5e6],
            "strain_material": [5.5e-4, 9.7e-4, 7e-4],
            "strengths": STRENGTHS,
            "criteria": ["tsai-wu"],
        })
        body = r.json()
        assert body["tsai_wu"]["fi"] < 1.0
        assert body["tsai_wu"]["failed"] is False

    def test_tsai_hill_transverse_onset(self, client):
        """σ2 = F2t → Tsai-Hill fi_squared ≈ 1.0."""
        r = client.post("/api/composites/failure", json={
            "stress_material": [0.0, 40e6, 0.0],
            "strain_material": [0.0, 40e6 / 10.3e9, 0.0],
            "strengths": STRENGTHS,
            "criteria": ["tsai-hill"],
        })
        body = r.json()
        assert abs(body["tsai_hill"]["fi_squared"] - 1.0) < 1e-6

    def test_all_criteria_returned_by_default(self, client):
        """Without specifying criteria, all four are computed."""
        r = client.post("/api/composites/failure", json={
            "stress_material": [100e6, 5e6, 3e6],
            "strain_material": [5.5e-4, 4.85e-4, 4.2e-4],
            "strengths": STRENGTHS,
        })
        body = r.json()
        for key in ("max_stress", "tsai_wu", "tsai_hill"):
            assert key in body, f"Missing criterion: {key}"

    def test_failed_field_true_when_any_criterion_fails(self, client):
        """If any criterion fails, top-level 'failed' is True."""
        r = client.post("/api/composites/failure", json={
            "stress_material": [2000e6, 0.0, 0.0],
            "strain_material": [2000e6 / 181e9, 0.0, 0.0],
            "strengths": STRENGTHS,
            "criteria": ["max-stress"],
        })
        body = r.json()
        assert body.get("failed") is True

    def test_missing_strength_key_returns_422(self, client):
        """Partial strengths dict missing F2c → 422."""
        r = client.post("/api/composites/failure", json={
            "stress_material": [100e6, 0.0, 0.0],
            "strain_material": [5.5e-4, 0.0, 0.0],
            "strengths": {"F1t": 1500e6},  # missing required keys
        })
        assert r.status_code == 422

    def test_missing_stress_field_returns_422(self, client):
        """Missing stress_material → 422."""
        r = client.post("/api/composites/failure", json={
            "strain_material": [1e-3, 0.0, 0.0],
            "strengths": STRENGTHS,
        })
        assert r.status_code == 422

    def test_wrong_stress_length_returns_422(self, client):
        """stress_material with wrong length → 422."""
        r = client.post("/api/composites/failure", json={
            "stress_material": [100e6, 5e6],  # only 2 elements
            "strain_material": [5.5e-4, 4.85e-4, 0.0],
            "strengths": STRENGTHS,
        })
        assert r.status_code == 422

    def test_max_strain_null_without_allowables(self, client):
        """max-strain criterion returns fi=None when no strain allowables provided."""
        r = client.post("/api/composites/failure", json={
            "stress_material": [100e6, 5e6, 3e6],
            "strain_material": [5.5e-4, 4.85e-4, 4.2e-4],
            "strengths": STRENGTHS,
            "criteria": ["max-strain"],
        })
        assert r.status_code == 200
        body = r.json()
        assert body.get("max_strain", {}).get("fi") is None
