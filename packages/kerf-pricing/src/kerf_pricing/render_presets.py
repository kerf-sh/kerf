"""Render quality presets and their kerf_paid credit costs.

Credit costs are the canonical billing authority for the render pipeline.
The cycles_worker reads these at job-dispatch time; ``kerf_billing.render_meter``
imports them to quote and charge jobs.

Costs are intentionally coarse-grained per preset, not per GPU-second — the
preset already encodes expected GPU time (samples, resolution, denoising
passes) and this keeps the billing model legible to users.
"""
from __future__ import annotations

from typing import TypedDict


# ── Credit-cost table ────────────────────────────────────────────────────────
# Each entry is (preset_name → kerf_paid credits).  The values map to the
# expected GPU compute: draft ~1 min, standard ~4 min, hero ~20 min, cinema ~2 h.
RENDER_CREDIT_COST: dict[str, float] = {
    "draft":    0.5,
    "standard": 2.0,
    "hero":     10.0,
    "cinema":   60.0,
}


class PresetInfo(TypedDict):
    credits: float
    description: str
    resolution: str
    samples: int


# ── Human-readable preset descriptions ──────────────────────────────────────
RENDER_PRESETS: dict[str, PresetInfo] = {
    "draft": PresetInfo(
        credits=RENDER_CREDIT_COST["draft"],
        description=(
            "Fast preview — low sample count, no denoising passes. "
            "Useful for checking composition and lighting placement."
        ),
        resolution="1080p",
        samples=64,
    ),
    "standard": PresetInfo(
        credits=RENDER_CREDIT_COST["standard"],
        description=(
            "Balanced quality for client previews and social media exports. "
            "Intel Open Image Denoise applied post-render."
        ),
        resolution="2K",
        samples=512,
    ),
    "hero": PresetInfo(
        credits=RENDER_CREDIT_COST["hero"],
        description=(
            "High-fidelity hero shot — full caustics, dispersion, SSS. "
            "Suitable for e-commerce product imagery and pitch decks."
        ),
        resolution="4K",
        samples=2048,
    ),
    "cinema": PresetInfo(
        credits=RENDER_CREDIT_COST["cinema"],
        description=(
            "Cinema-grade output — maximum samples, adaptive sampling, "
            "multi-pass OIDN, 32-bit EXR. For print, film, or archival use."
        ),
        resolution="8K",
        samples=8192,
    ),
}

VALID_PRESETS: frozenset[str] = frozenset(RENDER_CREDIT_COST)

__all__ = [
    "RENDER_CREDIT_COST",
    "RENDER_PRESETS",
    "VALID_PRESETS",
    "PresetInfo",
]
