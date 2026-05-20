"""
OASPL (Overall Sound Pressure Level) helpers.

Reference: ISO 1683 / Beranek & Mellow, "Acoustics: Sound Fields and Transducers"

    OASPL = 20 · log₁₀(p_rms / p_ref)  [dB]

where p_ref = 20 µPa (20e-6 Pa) — standard threshold of hearing in air.
"""

from __future__ import annotations

import math

import numpy as np

# Standard reference pressure (Pa)
P_REF: float = 20e-6


def rms(p: np.ndarray) -> float:
    """Root-mean-square of pressure time series."""
    return float(np.sqrt(np.mean(p ** 2)))


def oaspl_db(p: np.ndarray, p_ref: float = P_REF) -> float:
    """
    Compute OASPL in dB SPL from a pressure time-history array.

    Parameters
    ----------
    p : ndarray
        Acoustic pressure time series (Pa).
    p_ref : float
        Reference pressure (Pa). Default 20 µPa.

    Returns
    -------
    float
        OASPL in dB.
    """
    p_rms = rms(p)
    if p_rms < 1e-30:
        return -math.inf
    return 20.0 * math.log10(p_rms / p_ref)


def spl_db(p_rms: float, p_ref: float = P_REF) -> float:
    """Convert RMS pressure (Pa) to SPL in dB."""
    if p_rms < 1e-30:
        return -math.inf
    return 20.0 * math.log10(p_rms / p_ref)
