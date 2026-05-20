"""
Spectral analysis: FFT + 1/3-octave band summing.

Uses only numpy (scipy optional for window functions).
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np


class NarrowbandSpectrum(NamedTuple):
    """Raw (single-sided) FFT result."""
    frequencies_hz: np.ndarray   # (N//2+1,)
    spl_db: np.ndarray           # dB SPL per bin  (N//2+1,)
    p_rms_per_bin: np.ndarray    # RMS pressure per bin (Pa)


class OctaveBandSpectrum(NamedTuple):
    """1/3-octave band result."""
    band_center_hz: np.ndarray   # centre frequencies (Hz)
    spl_db: np.ndarray           # dB SPL per band
    p_rms_per_band: np.ndarray   # RMS pressure per band (Pa)


# Standard 1/3-octave centre frequencies (Hz), ISO 266
_ISO_THIRD_OCTAVE_CENTERS = np.array([
    12.5, 16, 20, 25, 31.5, 40, 50, 63, 80,
    100, 125, 160, 200, 250, 315, 400, 500, 630, 800,
    1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000,
    10000, 12500, 16000, 20000,
], dtype=float)

P_REF: float = 20e-6  # Pa


def narrowband_spectrum(
    p: np.ndarray,
    dt: float,
    window: str = "hann",
) -> NarrowbandSpectrum:
    """
    Compute single-sided narrowband FFT spectrum.

    Parameters
    ----------
    p : ndarray (N,)
        Acoustic pressure time series (Pa).
    dt : float
        Sample interval (s).
    window : str
        Window function name: "hann", "hamming", or "none".

    Returns
    -------
    NarrowbandSpectrum
    """
    N = len(p)
    if N < 2:
        raise ValueError("Need at least 2 samples")

    # Apply window
    if window == "hann":
        w = np.hanning(N)
    elif window == "hamming":
        w = np.hamming(N)
    else:
        w = np.ones(N)

    # Normalise window for RMS preservation
    w_norm = w / np.sqrt(np.mean(w ** 2))
    p_win = p * w_norm

    # FFT
    P_fft = np.fft.rfft(p_win) / N
    freqs = np.fft.rfftfreq(N, d=dt)

    # Single-sided amplitude (double for interior bins)
    n_bins = len(freqs)
    P_amp = np.abs(P_fft)
    P_amp[1:-1] *= math.sqrt(2)  # RMS correction for single-sided

    spl = np.where(
        P_amp > 1e-30,
        20.0 * np.log10(P_amp / P_REF),
        np.full(n_bins, -math.inf),
    )
    return NarrowbandSpectrum(
        frequencies_hz=freqs,
        spl_db=spl,
        p_rms_per_bin=P_amp,
    )


def third_octave_spectrum(
    p: np.ndarray,
    dt: float,
    window: str = "hann",
) -> OctaveBandSpectrum:
    """
    Compute 1/3-octave band spectrum by summing narrowband RMS² values.

    Parameters
    ----------
    p : ndarray (N,)
        Acoustic pressure time series (Pa).
    dt : float
        Sample interval (s).
    window : str
        Window function name.

    Returns
    -------
    OctaveBandSpectrum
    """
    nb = narrowband_spectrum(p, dt, window=window)
    freqs = nb.frequencies_hz
    p_rms_bin = nb.p_rms_per_bin

    band_centers = []
    band_spl = []
    band_rms = []

    f_nyq = 1.0 / (2.0 * dt)
    factor = 2.0 ** (1.0 / 6.0)  # half-bandwidth factor for 1/3-oct

    for f_c in _ISO_THIRD_OCTAVE_CENTERS:
        if f_c >= f_nyq:
            break
        f_lo = f_c / factor
        f_hi = f_c * factor
        mask = (freqs >= f_lo) & (freqs < f_hi)
        p_sq_sum = float(np.sum(p_rms_bin[mask] ** 2))
        p_band = math.sqrt(p_sq_sum)
        spl_val = 20.0 * math.log10(p_band / P_REF) if p_band > 1e-30 else -math.inf
        band_centers.append(f_c)
        band_spl.append(spl_val)
        band_rms.append(p_band)

    return OctaveBandSpectrum(
        band_center_hz=np.array(band_centers),
        spl_db=np.array(band_spl),
        p_rms_per_band=np.array(band_rms),
    )
