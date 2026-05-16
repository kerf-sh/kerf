"""
3D tolerance / variation analysis for assemblies.

Covers:
  - Parts with feature datums and 6-DOF placement (translation + rotation).
  - GD&T feature tolerances: position, flatness, perpendicularity, profile, linear.
  - Assembly mate chains (linear or branched).
  - Monte-Carlo propagation (seeded deterministic LCG + Box-Muller).
  - Statistical summary: mean, sigma, Cp/Cpk, defect-ppm.
  - Sensitivity / contribution analysis (variance decomposition, % per tolerance).
  - Worst-case 3D and RSS 3D bounds.

Never raises -- all public functions return {"ok": False, "reason": ...} on bad
input, or a result dict on success.

LLM tool: tolerance3d_analysis_spec / run_tolerance3d_analysis
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# compat shim -- same try/except pattern used in tools.py
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_mates._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx


# ---------------------------------------------------------------------------
# Deterministic LCG + Box-Muller (no external dependencies)
# ---------------------------------------------------------------------------

class _LCG:
    """Linear Congruential Generator (Knuth params, 64-bit modulus)."""

    _A = 6364136223846793005
    _C = 1442695040888963407
    _M = 2 ** 64

    def __init__(self, seed: int) -> None:
        self._state = int(seed) & (self._M - 1)

    def random(self) -> float:
        """Return a float in [0, 1)."""
        self._state = (self._A * self._state + self._C) % self._M
        return self._state / self._M

    def gauss(self) -> float:
        """Standard-normal deviate via Box-Muller (uses two uniform draws)."""
        while True:
            u1 = self.random()
            u2 = self.random()
            if u1 > 0.0:
                return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


# ---------------------------------------------------------------------------
# GD&T tolerance types
# ---------------------------------------------------------------------------

VALID_GDNT_TYPES = frozenset({
    "position",
    "flatness",
    "perpendicularity",
    "profile",
    "linear",
})


@dataclass
class FeatureTolerance:
    """Single GD&T tolerance on a part feature.

    Parameters
    ----------
    tol_id:       unique label used in contribution analysis output.
    tol_type:     one of VALID_GDNT_TYPES.
    value:        full tolerance zone width (e.g. 0.1 mm).  Half-zone = value/2.
    distribution: "normal" | "uniform".
    axis:         unit vector (3-tuple) along which this tolerance projects onto
                  the measurement direction.  Defaults to Z (0, 0, 1).
    """

    tol_id: str
    tol_type: str
    value: float
    distribution: str = "normal"
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)

    def __post_init__(self) -> None:
        if self.tol_type not in VALID_GDNT_TYPES:
            raise ValueError(f"unknown tol_type '{self.tol_type}'")
        if self.value < 0.0:
            raise ValueError(f"tolerance value must be >= 0, got {self.value}")
        ax = self.axis
        mag = math.sqrt(ax[0] ** 2 + ax[1] ** 2 + ax[2] ** 2)
        if mag < 1e-10:
            raise ValueError("tolerance axis must be a non-zero vector")
        self.axis = (ax[0] / mag, ax[1] / mag, ax[2] / mag)

    def half_zone(self) -> float:
        """Half the tolerance zone (one-sided deviation limit)."""
        return self.value / 2.0

    def sigma(self) -> float:
        """1-sigma equivalent, assuming +/-3sigma spans the full zone."""
        return self.half_zone() / 3.0

    def projection(self, meas_dir: tuple[float, float, float]) -> float:
        """Scalar projection factor of this tolerance axis onto meas_dir."""
        return abs(
            self.axis[0] * meas_dir[0]
            + self.axis[1] * meas_dir[1]
            + self.axis[2] * meas_dir[2]
        )


@dataclass
class AssemblyFeature:
    """A named feature datum on a part, with its 3-D position in part-space.

    Parameters
    ----------
    feature_id:  unique string label.
    position:    nominal (x, y, z) in mm.
    tolerances:  list of FeatureTolerance objects.
    """

    feature_id: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    tolerances: list[FeatureTolerance] = field(default_factory=list)


@dataclass
class AssemblyPart:
    """A part in the assembly with 6-DOF placement.

    Parameters
    ----------
    part_id:      unique label.
    features:     list of AssemblyFeature.
    translation:  nominal (tx, ty, tz) placement in assembly space (mm).
    rotation_deg: nominal (rx, ry, rz) Euler angles in degrees (XYZ order).
    """

    part_id: str
    features: list[AssemblyFeature] = field(default_factory=list)
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass
class MateLink:
    """One directed link in the mate chain.

    Connects a feature on part_a to a feature on part_b and specifies the
    measurement axis.  The link projects each tolerance through meas_dir.
    """

    link_id: str
    part_a_id: str
    feature_a_id: str
    part_b_id: str
    feature_b_id: str
    meas_dir: tuple[float, float, float] = (0.0, 0.0, 1.0)

    def __post_init__(self) -> None:
        md = self.meas_dir
        mag = math.sqrt(md[0] ** 2 + md[1] ** 2 + md[2] ** 2)
        if mag < 1e-10:
            raise ValueError("meas_dir must be a non-zero vector")
        self.meas_dir = (md[0] / mag, md[1] / mag, md[2] / mag)


@dataclass
class AssemblyModel:
    """Full assembly model: parts + mate chain + optional spec limits."""

    parts: list[AssemblyPart] = field(default_factory=list)
    mate_chain: list[MateLink] = field(default_factory=list)
    usl: float | None = None  # upper specification limit (mm)
    lsl: float | None = None  # lower specification limit (mm)


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def _feature_world_pos(
    part: AssemblyPart,
    feat: AssemblyFeature,
) -> tuple[float, float, float]:
    """Transform feature nominal position from part-space to assembly-space.

    Applies XYZ Euler rotation then translation.
    """
    rx = math.radians(part.rotation_deg[0])
    ry = math.radians(part.rotation_deg[1])
    rz = math.radians(part.rotation_deg[2])

    px, py, pz = feat.position

    # Rx
    cx, sx = math.cos(rx), math.sin(rx)
    x1, y1, z1 = px, py * cx - pz * sx, py * sx + pz * cx

    # Ry
    cy, sy = math.cos(ry), math.sin(ry)
    x2, y2, z2 = x1 * cy + z1 * sy, y1, -x1 * sy + z1 * cy

    # Rz
    cz, sz = math.cos(rz), math.sin(rz)
    x3, y3, z3 = x2 * cz - y2 * sz, x2 * sz + y2 * cz, z2

    tx, ty, tz = part.translation
    return (x3 + tx, y3 + ty, z3 + tz)


# ---------------------------------------------------------------------------
# Internal tolerance contribution record
# ---------------------------------------------------------------------------

@dataclass
class _TolContrib:
    """Single tolerance contribution to the measurement scalar."""

    tol_id: str
    half_zone: float        # half-zone before projection
    sigma: float            # 1-sigma before projection
    proj: float             # projection factor onto measurement direction
    effective_sigma: float  # sigma * proj
    distribution: str


def _collect_contributions(
    model: AssemblyModel,
) -> tuple[list[_TolContrib], float]:
    """Walk the mate chain and collect all tolerance contributions.

    Returns (contributions, nominal_gap).  nominal_gap is the scalar
    accumulated along each link's meas_dir through the chain.
    """
    part_map = {p.part_id: p for p in model.parts}
    feat_map: dict[str, dict[str, AssemblyFeature]] = {
        p.part_id: {f.feature_id: f for f in p.features}
        for p in model.parts
    }

    contribs: list[_TolContrib] = []
    nominal_gap = 0.0

    for link in model.mate_chain:
        pa = part_map.get(link.part_a_id)
        pb = part_map.get(link.part_b_id)
        if pa is None or pb is None:
            continue
        fa = feat_map.get(link.part_a_id, {}).get(link.feature_a_id)
        fb = feat_map.get(link.part_b_id, {}).get(link.feature_b_id)
        if fa is None or fb is None:
            continue

        wa = _feature_world_pos(pa, fa)
        wb = _feature_world_pos(pb, fb)
        md = link.meas_dir
        gap_contrib = (
            (wb[0] - wa[0]) * md[0]
            + (wb[1] - wa[1]) * md[1]
            + (wb[2] - wa[2]) * md[2]
        )
        nominal_gap += gap_contrib

        for feat in (fa, fb):
            for tol in feat.tolerances:
                proj = tol.projection(md)
                sigma = tol.sigma()
                contribs.append(_TolContrib(
                    tol_id=tol.tol_id,
                    half_zone=tol.half_zone(),
                    sigma=sigma,
                    proj=proj,
                    effective_sigma=sigma * proj,
                    distribution=tol.distribution,
                ))

    return contribs, nominal_gap


# ---------------------------------------------------------------------------
# RSS 3D
# ---------------------------------------------------------------------------

def rss3d(model: AssemblyModel) -> dict[str, Any]:
    """Root-Sum-Squares 3D tolerance analysis.

    Returns a result dict with keys:
      ok, nominal, rss_sigma, rss_band, max, min, contributions.
    """
    try:
        contribs, nominal = _collect_contributions(model)
    except Exception as e:
        return {"ok": False, "reason": str(e)}

    if not contribs:
        return {"ok": False, "reason": "no tolerances found in mate chain"}

    var_total = sum(c.effective_sigma ** 2 for c in contribs)
    rss_sigma = math.sqrt(var_total)
    rss_band = 3.0 * rss_sigma

    contribution_pct = []
    for c in contribs:
        pct = 100.0 * c.effective_sigma ** 2 / var_total if var_total > 0 else 0.0
        contribution_pct.append({
            "tol_id": c.tol_id,
            "effective_sigma": c.effective_sigma,
            "variance_contribution_pct": round(pct, 4),
        })
    contribution_pct.sort(key=lambda x: x["variance_contribution_pct"], reverse=True)

    return {
        "ok": True,
        "method": "rss3d",
        "nominal": nominal,
        "rss_sigma": rss_sigma,
        "rss_band": rss_band,
        "max": nominal + rss_band,
        "min": nominal - rss_band,
        "contributions": contribution_pct,
    }


# ---------------------------------------------------------------------------
# Worst-case 3D
# ---------------------------------------------------------------------------

def worst_case3d(model: AssemblyModel) -> dict[str, Any]:
    """Worst-case 3D tolerance analysis (arithmetic sum of projected half-zones)."""
    try:
        contribs, nominal = _collect_contributions(model)
    except Exception as e:
        return {"ok": False, "reason": str(e)}

    if not contribs:
        return {"ok": False, "reason": "no tolerances found in mate chain"}

    wc_band = sum(c.half_zone * c.proj for c in contribs)

    return {
        "ok": True,
        "method": "worst_case3d",
        "nominal": nominal,
        "wc_band": wc_band,
        "max": nominal + wc_band,
        "min": nominal - wc_band,
    }


# ---------------------------------------------------------------------------
# Capability indices
# ---------------------------------------------------------------------------

def _erfc_approx(x: float) -> float:
    """erfc via math.erfc (stdlib >= 3.2)."""
    return math.erfc(x)


def _norm_tail(z: float) -> float:
    """P(Z > z) for standard normal."""
    return 0.5 * _erfc_approx(z / math.sqrt(2.0))


def _capability(
    mean: float,
    sigma: float,
    usl: float | None,
    lsl: float | None,
) -> dict[str, Any]:
    """Compute Cp, Cpk, and defect-ppm from distribution parameters."""
    result: dict[str, Any] = {}
    if sigma <= 0.0:
        return result

    if usl is not None and lsl is not None:
        spec_range = usl - lsl
        if spec_range > 0.0:
            result["cp"] = spec_range / (6.0 * sigma)
        zu = (usl - mean) / sigma
        zl = (mean - lsl) / sigma
        result["cpk"] = min(zu, zl) / 3.0
        result["defect_ppm"] = (_norm_tail(zu) + _norm_tail(zl)) * 1e6
    elif usl is not None:
        zu = (usl - mean) / sigma
        result["cpk"] = zu / 3.0
        result["defect_ppm"] = _norm_tail(zu) * 1e6
    elif lsl is not None:
        zl = (mean - lsl) / sigma
        result["cpk"] = zl / 3.0
        result["defect_ppm"] = _norm_tail(zl) * 1e6

    return result


# ---------------------------------------------------------------------------
# Monte-Carlo 3D
# ---------------------------------------------------------------------------

def monte_carlo3d(
    model: AssemblyModel,
    samples: int = 10000,
    seed: int = 42,
) -> dict[str, Any]:
    """Monte-Carlo 3D tolerance analysis.

    Uses the deterministic LCG + Box-Muller generator for reproducibility.
    Returns mean, sigma, Cp/Cpk, defect-ppm, percentiles, and contribution %.

    Parameters
    ----------
    model:   AssemblyModel with parts, mate chain, and optional spec limits.
    samples: number of MC trials (clamped to [1, 2_000_000]).
    seed:    RNG seed for deterministic results.
    """
    if not isinstance(samples, int) or samples <= 0:
        samples = 10000
    if samples > 2_000_000:
        samples = 2_000_000

    try:
        contribs, nominal = _collect_contributions(model)
    except Exception as e:
        return {"ok": False, "reason": str(e)}

    if not contribs:
        return {"ok": False, "reason": "no tolerances found in mate chain"}

    rng = _LCG(seed)
    results: list[float] = []

    for _ in range(samples):
        gap = nominal
        for c in contribs:
            hz = c.half_zone * c.proj
            if hz <= 0.0:
                continue
            if c.distribution == "uniform":
                gap += rng.random() * 2.0 * hz - hz
            else:
                # normal (default): +/-3sigma spans the half-zone
                sig = hz / 3.0
                gap += rng.gauss() * sig
        results.append(gap)

    n = len(results)
    mean = sum(results) / n
    variance = sum((v - mean) ** 2 for v in results) / n
    sigma = math.sqrt(variance)

    results_sorted = sorted(results)

    def _pct(p: float) -> float:
        idx = max(0, min(n - 1, int(p * n)))
        return results_sorted[idx]

    cap = _capability(mean, sigma, model.usl, model.lsl)

    # Analytical sensitivity: each contrib's variance fraction
    denom_var = sum((c.half_zone * c.proj / 3.0) ** 2 for c in contribs)
    sens_list = []
    for c in contribs:
        contrib_var = (c.half_zone * c.proj / 3.0) ** 2
        pct = 100.0 * contrib_var / denom_var if denom_var > 0 else 0.0
        sens_list.append({
            "tol_id": c.tol_id,
            "effective_sigma": c.half_zone * c.proj / 3.0,
            "variance_contribution_pct": round(pct, 4),
        })
    sens_list.sort(key=lambda x: x["variance_contribution_pct"], reverse=True)

    result: dict[str, Any] = {
        "ok": True,
        "method": "monte_carlo3d",
        "samples": samples,
        "seed": seed,
        "nominal": nominal,
        "mean": mean,
        "sigma": sigma,
        "p01": _pct(0.01),
        "p50": _pct(0.50),
        "p99": _pct(0.99),
        "max_simulated": results_sorted[-1],
        "min_simulated": results_sorted[0],
        "contributions": sens_list,
    }
    result.update(cap)
    return result


# ---------------------------------------------------------------------------
# Combined analysis
# ---------------------------------------------------------------------------

def analyze3d(
    model: AssemblyModel,
    samples: int = 10000,
    seed: int = 42,
) -> dict[str, Any]:
    """Run worst-case, RSS, and Monte-Carlo and return a combined result dict."""
    wc = worst_case3d(model)
    rs = rss3d(model)
    mc = monte_carlo3d(model, samples=samples, seed=seed)

    for r in (wc, rs, mc):
        if not r.get("ok"):
            return {"ok": False, "reason": r.get("reason", "analysis failed")}

    return {
        "ok": True,
        "nominal": mc["nominal"],
        "worst_case": wc,
        "rss": rs,
        "monte_carlo": mc,
    }


# ---------------------------------------------------------------------------
# Dict-based constructors (for use from JSON / LLM tool)
# ---------------------------------------------------------------------------

def _parse_model(data: dict) -> AssemblyModel | dict:
    """Parse a plain-dict assembly model spec.  Returns AssemblyModel or err dict."""
    try:
        usl = data.get("usl")
        lsl = data.get("lsl")

        parts: list[AssemblyPart] = []
        for pr in data.get("parts", []):
            feats: list[AssemblyFeature] = []
            for fr in pr.get("features", []):
                tols: list[FeatureTolerance] = []
                for tr in fr.get("tolerances", []):
                    ax_raw = tr.get("axis", [0.0, 0.0, 1.0])
                    tols.append(FeatureTolerance(
                        tol_id=str(tr["tol_id"]),
                        tol_type=str(tr.get("tol_type", "linear")),
                        value=float(tr["value"]),
                        distribution=str(tr.get("distribution", "normal")),
                        axis=(float(ax_raw[0]), float(ax_raw[1]), float(ax_raw[2])),
                    ))
                pos_raw = fr.get("position", [0.0, 0.0, 0.0])
                feats.append(AssemblyFeature(
                    feature_id=str(fr["feature_id"]),
                    position=(float(pos_raw[0]), float(pos_raw[1]), float(pos_raw[2])),
                    tolerances=tols,
                ))
            trans_raw = pr.get("translation", [0.0, 0.0, 0.0])
            rot_raw = pr.get("rotation_deg", [0.0, 0.0, 0.0])
            parts.append(AssemblyPart(
                part_id=str(pr["part_id"]),
                features=feats,
                translation=(float(trans_raw[0]), float(trans_raw[1]), float(trans_raw[2])),
                rotation_deg=(float(rot_raw[0]), float(rot_raw[1]), float(rot_raw[2])),
            ))

        chain: list[MateLink] = []
        for lr in data.get("mate_chain", []):
            md_raw = lr.get("meas_dir", [0.0, 0.0, 1.0])
            chain.append(MateLink(
                link_id=str(lr.get("link_id", "")),
                part_a_id=str(lr["part_a_id"]),
                feature_a_id=str(lr["feature_a_id"]),
                part_b_id=str(lr["part_b_id"]),
                feature_b_id=str(lr["feature_b_id"]),
                meas_dir=(float(md_raw[0]), float(md_raw[1]), float(md_raw[2])),
            ))

        return AssemblyModel(
            parts=parts,
            mate_chain=chain,
            usl=float(usl) if usl is not None else None,
            lsl=float(lsl) if lsl is not None else None,
        )
    except Exception as e:
        return {"ok": False, "reason": f"model parse error: {e}"}


# ---------------------------------------------------------------------------
# LLM tool
# ---------------------------------------------------------------------------

tolerance3d_analysis_spec = ToolSpec(
    name="tolerance3d_analysis",
    description=(
        "3D tolerance / variation analysis for an assembly mate chain. "
        "Propagates GD&T feature tolerances (position, flatness, "
        "perpendicularity, profile, linear) through a mate chain to a measured "
        "gap/clearance/keypoint. Returns worst-case 3D, RSS 3D, and Monte-Carlo "
        "results including mean, sigma, Cp/Cpk, defect-ppm, and per-tolerance "
        "sensitivity/contribution analysis."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "parts": {
                "type": "array",
                "description": "List of parts with features and GD&T tolerances.",
                "items": {
                    "type": "object",
                    "properties": {
                        "part_id": {"type": "string"},
                        "translation": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "[tx, ty, tz] mm",
                        },
                        "rotation_deg": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "[rx, ry, rz] Euler degrees XYZ",
                        },
                        "features": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "feature_id": {"type": "string"},
                                    "position": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                    },
                                    "tolerances": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "tol_id": {"type": "string"},
                                                "tol_type": {
                                                    "type": "string",
                                                    "enum": [
                                                        "position", "flatness",
                                                        "perpendicularity",
                                                        "profile", "linear",
                                                    ],
                                                },
                                                "value": {"type": "number"},
                                                "distribution": {
                                                    "type": "string",
                                                    "enum": ["normal", "uniform"],
                                                },
                                                "axis": {
                                                    "type": "array",
                                                    "items": {"type": "number"},
                                                },
                                            },
                                            "required": ["tol_id", "tol_type", "value"],
                                        },
                                    },
                                },
                                "required": ["feature_id"],
                            },
                        },
                    },
                    "required": ["part_id"],
                },
            },
            "mate_chain": {
                "type": "array",
                "description": "Ordered mate links forming the tolerance chain.",
                "items": {
                    "type": "object",
                    "properties": {
                        "link_id": {"type": "string"},
                        "part_a_id": {"type": "string"},
                        "feature_a_id": {"type": "string"},
                        "part_b_id": {"type": "string"},
                        "feature_b_id": {"type": "string"},
                        "meas_dir": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Unit vector measurement direction [x, y, z]",
                        },
                    },
                    "required": [
                        "part_a_id", "feature_a_id",
                        "part_b_id", "feature_b_id",
                    ],
                },
            },
            "samples": {
                "type": "integer",
                "description": "Monte-Carlo sample count (default 10000, max 2000000).",
            },
            "seed": {
                "type": "integer",
                "description": "RNG seed for deterministic MC (default 42).",
            },
            "usl": {"type": "number", "description": "Upper specification limit (mm)."},
            "lsl": {"type": "number", "description": "Lower specification limit (mm)."},
        },
        "required": ["parts", "mate_chain"],
    },
)


@register(tolerance3d_analysis_spec)
async def run_tolerance3d_analysis(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    model_or_err = _parse_model(a)
    if isinstance(model_or_err, dict):
        return err_payload(model_or_err["reason"], "BAD_ARGS")

    model = model_or_err
    samples = a.get("samples", 10000)
    seed = a.get("seed", 42)
    if not isinstance(samples, int) or samples <= 0:
        samples = 10000

    result = analyze3d(model, samples=samples, seed=seed)
    if not result.get("ok"):
        return err_payload(result.get("reason", "analysis failed"), "ANALYSIS_ERROR")

    return ok_payload(result)
