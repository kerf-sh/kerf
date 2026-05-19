"""Hermetic tests for POST /api/aero/atmosphere (ISA 1976).

No DB, no network.  kerf_cad_core must be on the Python path (see conftest.py).
"""
from __future__ import annotations

import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kerf_api.routes_aero_atmosphere import router


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


# ===========================================================================
# ISA atmosphere route
# ===========================================================================

class TestISAAtmosphereRoute:

    def test_sea_level_returns_200(self, client):
        """Sea level (0 m) → 200 with ok=True."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 0.0})
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True

    def test_sea_level_temperature(self, client):
        """ISA sea level: T = 288.15 K."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 0.0})
        body = r.json()
        assert abs(body["T_K"] - 288.15) < 0.01

    def test_sea_level_pressure(self, client):
        """ISA sea level: p = 101 325 Pa."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 0.0})
        body = r.json()
        assert abs(body["p_Pa"] - 101325.0) < 1.0

    def test_sea_level_density(self, client):
        """ISA sea level: ρ = 1.225 kg/m³."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 0.0})
        body = r.json()
        assert abs(body["rho_kg_m3"] - 1.225) < 0.001

    def test_sea_level_speed_of_sound(self, client):
        """ISA sea level: a ≈ 340.29 m/s."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 0.0})
        body = r.json()
        assert abs(body["a_m_s"] - 340.294) < 0.1

    def test_tropopause_temperature(self, client):
        """At 11 000 m: T = 216.65 K (ICAO tropopause)."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 11000.0})
        body = r.json()
        assert abs(body["T_K"] - 216.65) < 0.05

    def test_tropopause_pressure(self, client):
        """At 11 000 m: p ≈ 22 632 Pa (ICAO)."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 11000.0})
        body = r.json()
        assert abs(body["p_Pa"] - 22632.0) < 5.0

    def test_5km_temperature(self, client):
        """At 5 000 m: T = 255.65 K (ICAO)."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 5000.0})
        body = r.json()
        assert abs(body["T_K"] - 255.65) < 0.05

    def test_density_decreases_with_altitude(self, client):
        """Density at 5 km < density at sea level."""
        r0 = client.post("/api/aero/atmosphere", json={"altitude_m": 0.0})
        r5 = client.post("/api/aero/atmosphere", json={"altitude_m": 5000.0})
        assert r5.json()["rho_kg_m3"] < r0.json()["rho_kg_m3"]

    def test_pressure_decreases_with_altitude(self, client):
        """Pressure at 10 km < pressure at 5 km."""
        r5 = client.post("/api/aero/atmosphere", json={"altitude_m": 5000.0})
        r10 = client.post("/api/aero/atmosphere", json={"altitude_m": 10000.0})
        assert r10.json()["p_Pa"] < r5.json()["p_Pa"]

    def test_altitude_echoed_in_response(self, client):
        """Response includes the input altitude_m field."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 3500.0})
        body = r.json()
        assert "altitude_m" in body
        assert abs(body["altitude_m"] - 3500.0) < 1e-6

    def test_required_fields_present(self, client):
        """Response always includes T_K, p_Pa, rho_kg_m3, a_m_s."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 8000.0})
        body = r.json()
        for field in ("T_K", "p_Pa", "rho_kg_m3", "a_m_s"):
            assert field in body, f"Missing field: {field}"

    def test_negative_altitude_returns_422(self, client):
        """Negative altitude → 422 (out of ISA range)."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": -100.0})
        assert r.status_code == 422

    def test_above_20km_returns_422(self, client):
        """Altitude > 20 000 m → 422 (model limit)."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 25000.0})
        assert r.status_code == 422

    def test_missing_altitude_returns_422(self, client):
        """Missing altitude_m → 422 (Pydantic validation)."""
        r = client.post("/api/aero/atmosphere", json={})
        assert r.status_code == 422

    def test_stratosphere_isothermal(self, client):
        """At 15 km (stratosphere): T = 216.65 K (isothermal layer)."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 15000.0})
        body = r.json()
        assert abs(body["T_K"] - 216.65) < 0.1

    def test_ideal_gas_consistency(self, client):
        """ρ = p / (R × T) at 8 000 m (R = 287.05287 J/(kg·K))."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 8000.0})
        body = r.json()
        R = 287.05287
        rho_check = body["p_Pa"] / (R * body["T_K"])
        assert abs(body["rho_kg_m3"] - rho_check) / rho_check < 1e-5

    def test_speed_of_sound_formula(self, client):
        """a = √(γ R T) with γ=1.4, R=287.05287."""
        r = client.post("/api/aero/atmosphere", json={"altitude_m": 5000.0})
        body = r.json()
        a_check = math.sqrt(1.4 * 287.05287 * body["T_K"])
        assert abs(body["a_m_s"] - a_check) / a_check < 1e-4
