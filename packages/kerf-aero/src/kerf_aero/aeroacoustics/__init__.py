"""
kerf_aero.aeroacoustics — FW-H far-field noise solver (Farassat 1A).

Quick start
-----------
>>> from kerf_aero.aeroacoustics import compute_far_field_noise, RotorSurface, RotorMotion
>>> from kerf_aero.flight_dynamics import std_atmosphere
>>> atm = std_atmosphere(0.0)   # sea level
>>> # Build surface + motion from your propeller mesh …
>>> result = compute_far_field_noise(surface, motion, observers)
>>> print(result.oaspl_total_db)   # dB SPL per observer

Modules
-------
fwh        — Farassat 1A time-domain kernel + entry point
observer   — retarded-time solver
oaspl      — OASPL helper (20·log10(p_rms / 20µPa))
spectrum   — FFT + 1/3-octave band analysis
"""

from __future__ import annotations

from .fwh import (
    RotorSurface,
    RotorMotion,
    NoiseResult,
    compute_far_field_noise,
)
from .oaspl import oaspl_db, spl_db, rms as pressure_rms, P_REF
from .spectrum import narrowband_spectrum, third_octave_spectrum
from .observer import Observer, retarded_time

__all__ = [
    # FW-H core
    "RotorSurface",
    "RotorMotion",
    "NoiseResult",
    "compute_far_field_noise",
    # OASPL helpers
    "oaspl_db",
    "spl_db",
    "pressure_rms",
    "P_REF",
    # Spectral analysis
    "narrowband_spectrum",
    "third_octave_spectrum",
    # Observer geometry
    "Observer",
    "retarded_time",
]
