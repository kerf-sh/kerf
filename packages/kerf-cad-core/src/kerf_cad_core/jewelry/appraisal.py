"""
kerf_cad_core.jewelry.appraisal
================================

Insurance / replacement appraisal document generator for finished jewelry
pieces.

This module is pure-Python with no external dependencies. It reuses
``gem_cert``, ``gem_studio``, and ``metal_cost`` / ``production`` data.

Public API
----------
appraise(piece)         — main entry-point; returns structured appraisal dict
                          + formatted Markdown certificate
value_summary(result)   — compact {replacement, fair_market, liquidation} dict

Valuation levels
----------------
Three values are produced for each piece:

  replacement (retail)   — the cost to replace the piece with a comparable
                           item purchased from a retail jeweler. This is the
                           figure used for insurance purposes.

  fair_market            — the price a willing buyer and willing seller would
                           agree on in an arm's-length transaction (estate,
                           resale market). Typically 60–80 % of replacement.

  liquidation            — the distressed-sale value (pawnbroker / quick-sale),
                           typically 30–50 % of replacement.

Invariant: replacement >= fair_market >= liquidation >= 0

Multipliers are configurable via AppraisalConfig and default to conservative
industry midpoints.

Input schema (piece dict)
-------------------------
{
  "id":           str or None,      — piece identifier
  "description":  str,              — human-readable description
  "piece_type":   str,              — ring / necklace / bracelet / earring / pendant / brooch / other
  "metal": {
      "alloy":          str,        — key from metal_cost.METAL_DENSITY_G_CM3
      "weight_grams":   float,      — measured net weight in grams
      "spot_price_per_gram": float, — current spot price in USD/g
      "fabrication_per_gram": float,— fabrication premium per gram (default 0)
  },
  "stones": [                       — optional; omit or [] for metal-only piece
    {
      "stone_type":     str,        — "diamond" / "ruby" / "sapphire" / …
      "cut":            str,        — cut name
      "carat":          float,      — weight in carats
      "color_grade":    str or None,— D-Z or fancy / colour descriptor
      "clarity_grade":  str or None,— FL-I3 or trade equivalent
      "measurements_mm":dict or None,— {length, width, depth}
      "cert_ref":       str or None,— lab#number e.g. "GIA#1234567890"
      "price_per_carat": float,     — per-carat value for this stone
      "setting_type":   str,        — prong / bezel / pave / channel / flush
    }, …
  ],
  "labor_value":    float,          — appraiser's estimate of bench labor + setting (USD)
  "notes":          str or None,    — additional remarks
}

AppraisalConfig fields (all optional — defaults are conservative midpoints)
---------------------------------------------------------------------------
  replacement_multiplier  float   1.0   (replacement = base × multiplier)
  fair_market_multiplier  float   0.70  (fair_market = replacement × fm_mult)
  liquidation_multiplier  float   0.40  (liquidation = replacement × liq_mult)
  appraiser_name          str     "Appraiser"
  appraiser_credentials   str     ""
  appraiser_location      str     ""
  date_of_appraisal       str     (ISO-8601 date; defaults to today)
  methodology             str     (free-text; a default is supplied)
  purpose                 str     "Insurance / Replacement"

Output structure
----------------
{
  "piece_id":          str or None,
  "description":       str,
  "piece_type":        str,
  "appraisal_date":    str,
  "purpose":           str,
  "stones_schedule":   list[dict],   — per-stone itemisation
  "metal_schedule":    dict,         — alloy / weight / spot / fab / metal_value
  "labor_value":       float,
  "base_value":        float,        — stones + metal + labor
  "replacement_value": float,        — base × replacement_multiplier
  "fair_market_value": float,        — replacement × fair_market_multiplier
  "liquidation_value": float,        — replacement × liquidation_multiplier
  "methodology":       str,
  "appraiser":         dict,
  "warnings":          list[str],
  "certificate_md":    str,          — formatted Markdown appraisal certificate
}

LLM tools (gated, @register)
-----------------------------
  jewelry_appraise          — full appraisal from piece dict
  jewelry_value_summary     — compact value summary from appraisal result

All public functions never raise. Errors are captured in warnings[].
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

from kerf_cad_core.jewelry.gem_cert import (
    CLARITY_GRADES_GIA,
    COLOR_GRADES_GIA,
    CertificateRef,
)
from kerf_cad_core.jewelry.gem_studio import GEM_STUDIO_CATALOG
from kerf_cad_core.jewelry.metal_cost import (
    METAL_DENSITY_G_CM3,
    METAL_HALLMARK,
    METAL_LABELS,
)

# ---------------------------------------------------------------------------
# Configurable multipliers / defaults
# ---------------------------------------------------------------------------

_DEFAULT_REPLACEMENT_MULT: float = 1.0
_DEFAULT_FAIR_MARKET_MULT: float = 0.70
_DEFAULT_LIQUIDATION_MULT: float = 0.40

_DEFAULT_METHODOLOGY: str = (
    "Valuation is based on prevailing retail replacement cost methodology. "
    "Gemstone values are derived from industry price-per-carat bands adjusted "
    "for grade, cut quality, and market conditions as of the appraisal date. "
    "Metal value is computed from measured net weight, current spot price, and "
    "fabrication premium. Labor and setting valuation reflects current bench "
    "rates. Fair-market and liquidation values are applied as configurable "
    "fractions of replacement value, representing estate/resale and distressed-"
    "sale scenarios respectively. This appraisal is prepared for insurance / "
    "replacement purposes and is not a guarantee of purchase price."
)

_DEFAULT_APPRAISER_STATEMENT: str = (
    "The appraiser certifies that the above item was personally examined and "
    "that the values stated herein represent the appraiser's best professional "
    "judgment of the described values as of the appraisal date. This appraisal "
    "is subject to the limiting conditions set forth herein."
)

# Known piece types for validation (informational only — no hard rejection)
_PIECE_TYPES: frozenset[str] = frozenset({
    "ring", "necklace", "bracelet", "earring", "pendant",
    "brooch", "bangle", "cuff", "chain", "locket", "charm", "other",
})

# Grade quality multiplier tables
# Maps each grade to a multiplier applied to the catalog mid-band price.
# Conservative: top grades get a premium, lower grades a discount.

_COLOR_GRADE_MULT: dict[str, float] = {
    "D": 1.40, "E": 1.30, "F": 1.20,
    "G": 1.10, "H": 1.05, "I": 1.00, "J": 0.95,
    "K": 0.85, "L": 0.80, "M": 0.75,
    "N": 0.70, "O": 0.68, "P": 0.66, "Q": 0.64, "R": 0.62,
    "S": 0.58, "T": 0.56, "U": 0.54, "V": 0.52, "W": 0.50,
    "X": 0.48, "Y": 0.46, "Z": 0.44,
}

_CLARITY_GRADE_MULT: dict[str, float] = {
    "FL": 1.40, "IF": 1.30,
    "VVS1": 1.20, "VVS2": 1.15,
    "VS1": 1.10, "VS2": 1.05,
    "SI1": 0.90, "SI2": 0.80,
    "I1": 0.60, "I2": 0.45, "I3": 0.30,
}

# For coloured stones without a GIA D-Z colour grade, use "Eye-clean" etc.
_COLOURED_CLARITY_MULT: dict[str, float] = {
    "Eye-clean": 1.05,
    "Slightly included": 0.85,
    "Moderately included": 0.65,
    "Jardin": 0.75,
    "Slightly jardin": 0.90,
    "No-crack": 1.00,
    "Minor fissure": 0.80,
    "Crazing": 0.50,
}


# ---------------------------------------------------------------------------
# AppraisalConfig dataclass
# ---------------------------------------------------------------------------

@dataclass
class AppraisalConfig:
    """Configuration for a jewelry appraisal.

    All fields have conservative industry-midpoint defaults.
    """
    replacement_multiplier: float = _DEFAULT_REPLACEMENT_MULT
    fair_market_multiplier: float = _DEFAULT_FAIR_MARKET_MULT
    liquidation_multiplier: float = _DEFAULT_LIQUIDATION_MULT
    appraiser_name: str = "Appraiser"
    appraiser_credentials: str = ""
    appraiser_location: str = ""
    date_of_appraisal: Optional[str] = None   # ISO-8601; None = today
    methodology: str = _DEFAULT_METHODOLOGY
    appraiser_statement: str = _DEFAULT_APPRAISER_STATEMENT
    purpose: str = "Insurance / Replacement"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float = 0.0) -> float:
    """Convert val to float; return default on failure. Never raises."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _catalog_mid_price(stone_type: str) -> float:
    """Return the midpoint of the price_per_ct_band for a gem type.

    Falls back to 0.0 if the stone type is not in the catalog.
    """
    key = str(stone_type).strip().lower().replace(" ", "_")
    entry = GEM_STUDIO_CATALOG.get(key)
    if entry is None:
        return 0.0
    band = entry.get("price_per_ct_band")
    if not isinstance(band, (list, tuple)) or len(band) < 2:
        return 0.0
    try:
        lo, hi = float(band[0]), float(band[1])
        return (lo + hi) / 2.0
    except (TypeError, ValueError):
        return 0.0


def _grade_multiplier(
    stone_type: str,
    color_grade: Optional[str],
    clarity_grade: Optional[str],
) -> float:
    """Return a combined grade quality multiplier (product of color × clarity)."""
    color_mult = 1.0
    clarity_mult = 1.0

    if color_grade:
        cg = str(color_grade).strip()
        if cg in _COLOR_GRADE_MULT:
            color_mult = _COLOR_GRADE_MULT[cg]
        # Fancy colour commands a premium over colorless D
        elif any(cg.startswith(p) for p in (
            "Fancy Vivid", "Fancy Intense", "Fancy Deep",
        )):
            color_mult = 1.50
        elif cg.startswith("Fancy"):
            color_mult = 1.20

    if clarity_grade:
        cl = str(clarity_grade).strip()
        if cl in _CLARITY_GRADE_MULT:
            clarity_mult = _CLARITY_GRADE_MULT[cl]
        elif cl in _COLOURED_CLARITY_MULT:
            clarity_mult = _COLOURED_CLARITY_MULT[cl]

    return color_mult * clarity_mult


def _stone_per_carat_price(
    stone_type: str,
    carat: float,
    color_grade: Optional[str],
    clarity_grade: Optional[str],
    explicit_price_per_carat: Optional[float],
) -> float:
    """Resolve a defensible per-carat price for a stone.

    Priority:
      1. Explicit price_per_carat from caller (trusted, e.g. from current
         market quotation or independent valuation).
      2. Grade-adjusted catalog mid-band price (fallback if explicit absent).

    The grade multiplier is always applied to the catalog price; an explicit
    price_per_carat is taken as-is (the caller has already accounted for grade).
    """
    if explicit_price_per_carat is not None:
        try:
            p = float(explicit_price_per_carat)
            if p >= 0:
                return p
        except (TypeError, ValueError):
            pass

    mid = _catalog_mid_price(stone_type)
    if mid <= 0:
        return 0.0

    mult = _grade_multiplier(stone_type, color_grade, clarity_grade)
    return mid * mult


def _carat_size_premium(carat: float, stone_type: str) -> float:
    """Apply a size premium for large single stones.

    For diamonds and coloured stones, per-carat price increases non-linearly
    with carat weight. We apply a modest premium for stones above thresholds.
    This is conservative and defensible.

    Multiplier schedule (cumulative applied once at the relevant tier):
      < 0.50 ct  : 1.00 (no premium)
      0.50–0.99  : 1.10
      1.00–1.99  : 1.25
      2.00–2.99  : 1.45
      3.00–4.99  : 1.65
      >= 5.00    : 1.90
    """
    if carat < 0.50:
        return 1.00
    if carat < 1.00:
        return 1.10
    if carat < 2.00:
        return 1.25
    if carat < 3.00:
        return 1.45
    if carat < 5.00:
        return 1.65
    return 1.90


# ---------------------------------------------------------------------------
# Stone schedule
# ---------------------------------------------------------------------------

def _build_stone_schedule(
    stones: list[dict],
    warnings: list[str],
) -> tuple[list[dict], float]:
    """Build the per-stone itemisation schedule.

    Returns (schedule_list, total_stones_value).
    Errors for individual stones are appended to warnings; the stone is
    included with value 0 so the document remains complete.
    """
    schedule: list[dict] = []
    total: float = 0.0

    for idx, raw in enumerate(stones):
        if not isinstance(raw, dict):
            warnings.append(f"stones[{idx}] is not a dict — skipped")
            continue

        stone_type = str(raw.get("stone_type", "diamond")).strip().lower()
        cut = str(raw.get("cut", "round_brilliant")).strip().lower()

        carat_raw = raw.get("carat")
        if carat_raw is None:
            warnings.append(f"stones[{idx}] missing carat — value set to 0")
            carat = 0.0
        else:
            carat = _safe_float(carat_raw, 0.0)
            if carat <= 0:
                warnings.append(
                    f"stones[{idx}] carat must be > 0 (got {carat_raw!r}) — "
                    "value set to 0"
                )
                carat = 0.0

        color_grade = raw.get("color_grade") or None
        clarity_grade = raw.get("clarity_grade") or None
        measurements_mm = raw.get("measurements_mm") or None
        cert_ref = raw.get("cert_ref") or None

        explicit_ppc = raw.get("price_per_carat")
        setting_type = str(raw.get("setting_type", "prong")).strip().lower()

        # Compute per-carat price
        ppc = _stone_per_carat_price(
            stone_type, carat, color_grade, clarity_grade, explicit_ppc
        )

        # Apply size premium only when using catalog price (not explicit price)
        if explicit_ppc is None:
            size_prem = _carat_size_premium(carat, stone_type)
            ppc = ppc * size_prem

        stone_value = round(carat * ppc, 4)
        total += stone_value

        schedule.append({
            "index":          idx,
            "stone_type":     stone_type,
            "cut":            cut,
            "carat":          round(carat, 4),
            "color_grade":    color_grade,
            "clarity_grade":  clarity_grade,
            "measurements_mm": measurements_mm,
            "cert_ref":       cert_ref,
            "price_per_carat": round(ppc, 4),
            "stone_value":    stone_value,
            "setting_type":   setting_type,
            "source": "explicit" if explicit_ppc is not None else "catalog_grade_adjusted",
        })

    return schedule, round(total, 4)


# ---------------------------------------------------------------------------
# Metal schedule
# ---------------------------------------------------------------------------

def _build_metal_schedule(
    metal_spec: dict,
    warnings: list[str],
) -> tuple[dict, float]:
    """Build the metal schedule and return (schedule, metal_value)."""
    alloy = str(metal_spec.get("alloy", "")).strip().lower()
    weight_grams = _safe_float(metal_spec.get("weight_grams"), 0.0)
    spot = _safe_float(metal_spec.get("spot_price_per_gram"), 0.0)
    fab = _safe_float(metal_spec.get("fabrication_per_gram"), 0.0)

    alloy_invalid: bool = False
    if alloy and alloy not in METAL_DENSITY_G_CM3:
        warnings.append(
            f"Unknown metal alloy {alloy!r}; known: "
            f"{sorted(METAL_DENSITY_G_CM3)}. Metal value set to 0."
        )
        alloy_invalid = True
        alloy = ""

    if weight_grams <= 0:
        warnings.append(
            f"metal.weight_grams must be > 0 (got {metal_spec.get('weight_grams')!r}); "
            "metal value set to 0"
        )
        weight_grams = 0.0

    if spot < 0:
        warnings.append(
            f"metal.spot_price_per_gram must be >= 0 (got {spot!r}); set to 0"
        )
        spot = 0.0

    if fab < 0:
        warnings.append(
            f"metal.fabrication_per_gram must be >= 0 (got {fab!r}); set to 0"
        )
        fab = 0.0

    effective_price = spot + fab
    if alloy_invalid:
        metal_value = 0.0
    else:
        metal_value = round(weight_grams * effective_price, 4)

    hallmark = METAL_HALLMARK.get(alloy) if alloy else None
    label = METAL_LABELS.get(alloy, alloy) if alloy else "Custom"

    schedule = {
        "alloy":                alloy,
        "alloy_label":          label,
        "hallmark":             hallmark,
        "weight_grams":         round(weight_grams, 4),
        "spot_price_per_gram":  round(spot, 4),
        "fabrication_per_gram": round(fab, 4),
        "effective_price_per_gram": round(effective_price, 4),
        "metal_value":          metal_value,
    }

    return schedule, metal_value


# ---------------------------------------------------------------------------
# Markdown certificate renderer
# ---------------------------------------------------------------------------

_MD_DIVIDER = "---"


def _render_certificate_md(result: dict, cfg: AppraisalConfig) -> str:
    """Render a formatted Markdown appraisal certificate from the result dict."""
    lines: list[str] = []

    def _h(level: int, text: str) -> None:
        lines.append(f"{'#' * level} {text}")
        lines.append("")

    def _kv(key: str, value: Any) -> None:
        lines.append(f"**{key}:** {value}")

    def _blank() -> None:
        lines.append("")

    def _divider() -> None:
        lines.append(_MD_DIVIDER)
        lines.append("")

    # ---- Header ----
    _h(1, "JEWELRY APPRAISAL CERTIFICATE")
    _kv("Purpose", result.get("purpose", "Insurance / Replacement"))
    _kv("Date of Appraisal", result.get("appraisal_date", ""))
    piece_id = result.get("piece_id")
    if piece_id:
        _kv("Piece ID", piece_id)
    _kv("Item Description", result.get("description", ""))
    piece_type = result.get("piece_type", "")
    if piece_type:
        _kv("Piece Type", piece_type.title())
    _blank()
    _divider()

    # ---- Gemstone Schedule ----
    _h(2, "Gemstone Schedule")
    stones = result.get("stones_schedule", [])
    if not stones:
        lines.append("*No gemstones — metal-only piece.*")
        _blank()
    else:
        # Table header
        lines.append(
            "| # | Type | Cut | Carat | Color | Clarity | Cert | USD/ct | Value |"
        )
        lines.append(
            "|---|------|-----|-------|-------|---------|------|--------|-------|"
        )
        for s in stones:
            idx_disp = s["index"] + 1
            stype = s["stone_type"].replace("_", " ").title()
            cut = s["cut"].replace("_", " ").title()
            carat = f"{s['carat']:.3f} ct"
            color = s["color_grade"] or "—"
            clarity = s["clarity_grade"] or "—"
            cert = s["cert_ref"] or "—"
            ppc = f"${s['price_per_carat']:,.2f}"
            val = f"${s['stone_value']:,.2f}"
            lines.append(
                f"| {idx_disp} | {stype} | {cut} | {carat} | {color} | "
                f"{clarity} | {cert} | {ppc} | {val} |"
            )
        _blank()
        _kv("Total Stone Value", f"${result.get('total_stone_value', 0.0):,.2f}")
        _blank()
    _divider()

    # ---- Metal Schedule ----
    _h(2, "Metal Schedule")
    ms = result.get("metal_schedule", {})
    if ms:
        _kv("Alloy", ms.get("alloy_label", ms.get("alloy", "—")))
        hallmark = ms.get("hallmark")
        if hallmark is not None:
            _kv("Hallmark / Fineness", str(hallmark))
        _kv("Net Weight", f"{ms.get('weight_grams', 0.0):.3f} g")
        _kv("Spot Price", f"${ms.get('spot_price_per_gram', 0.0):.4f}/g")
        fab = ms.get("fabrication_per_gram", 0.0)
        if fab > 0:
            _kv("Fabrication Premium", f"${fab:.4f}/g")
        _kv("Effective Metal Price", f"${ms.get('effective_price_per_gram', 0.0):.4f}/g")
        _kv("Metal Value", f"${ms.get('metal_value', 0.0):,.2f}")
    else:
        lines.append("*Metal schedule not available.*")
    _blank()
    _divider()

    # ---- Labor & Setting ----
    _h(2, "Labor & Setting Valuation")
    labor = result.get("labor_value", 0.0)
    _kv("Labor, Setting & Finishing", f"${labor:,.2f}")
    _blank()
    _divider()

    # ---- Value Summary ----
    _h(2, "Value Summary")
    base = result.get("base_value", 0.0)
    replacement = result.get("replacement_value", 0.0)
    fair_market = result.get("fair_market_value", 0.0)
    liquidation = result.get("liquidation_value", 0.0)

    lines.append("| Component | Amount |")
    lines.append("|-----------|--------|")
    lines.append(f"| Total Stone Value | ${result.get('total_stone_value', 0.0):,.2f} |")
    lines.append(f"| Metal Value | ${ms.get('metal_value', 0.0):,.2f} |")
    lines.append(f"| Labor & Setting | ${labor:,.2f} |")
    lines.append(f"| **Base Value** | **${base:,.2f}** |")
    _blank()
    lines.append("| Valuation Level | Amount |")
    lines.append("|-----------------|--------|")
    lines.append(f"| **Replacement (Retail)** | **${replacement:,.2f}** |")
    lines.append(f"| Fair Market | ${fair_market:,.2f} |")
    lines.append(f"| Liquidation | ${liquidation:,.2f} |")
    _blank()

    rm = cfg.replacement_multiplier
    fm = cfg.fair_market_multiplier
    lm = cfg.liquidation_multiplier
    lines.append(
        f"*Multipliers applied: replacement={rm:.2f}, "
        f"fair-market={fm:.2f}, liquidation={lm:.2f}*"
    )
    _blank()
    _divider()

    # ---- Methodology ----
    _h(2, "Appraisal Methodology")
    lines.append(result.get("methodology", _DEFAULT_METHODOLOGY))
    _blank()
    _divider()

    # ---- Appraiser Statement ----
    _h(2, "Appraiser Statement")
    lines.append(cfg.appraiser_statement)
    _blank()

    appraiser = result.get("appraiser", {})
    _kv("Appraiser", appraiser.get("name", "Appraiser"))
    creds = appraiser.get("credentials", "")
    if creds:
        _kv("Credentials", creds)
    loc = appraiser.get("location", "")
    if loc:
        _kv("Location", loc)
    _blank()

    # ---- Warnings ----
    warnings_list = result.get("warnings", [])
    if warnings_list:
        _divider()
        _h(2, "Notes & Warnings")
        for w in warnings_list:
            lines.append(f"- {w}")
        _blank()

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main appraise() function
# ---------------------------------------------------------------------------

def appraise(
    piece: dict,
    cfg: Optional[AppraisalConfig] = None,
) -> dict:
    """Generate an insurance / replacement appraisal for a jewelry piece.

    Parameters
    ----------
    piece : dict
        Piece specification dict (see module docstring for schema).
    cfg : AppraisalConfig, optional
        Valuation configuration. Uses conservative defaults if None.

    Returns
    -------
    dict with keys:
        piece_id, description, piece_type, appraisal_date, purpose,
        stones_schedule, metal_schedule, labor_value, total_stone_value,
        base_value, replacement_value, fair_market_value, liquidation_value,
        methodology, appraiser, warnings, certificate_md

    Never raises. All errors captured in warnings[].
    """
    if cfg is None:
        cfg = AppraisalConfig()

    warnings: list[str] = []

    # --- Validate config multipliers ---
    rm = _safe_float(cfg.replacement_multiplier, _DEFAULT_REPLACEMENT_MULT)
    fm = _safe_float(cfg.fair_market_multiplier, _DEFAULT_FAIR_MARKET_MULT)
    lm = _safe_float(cfg.liquidation_multiplier, _DEFAULT_LIQUIDATION_MULT)

    if rm < 0:
        warnings.append(f"replacement_multiplier {rm} clamped to 0")
        rm = 0.0
    if fm < 0:
        warnings.append(f"fair_market_multiplier {fm} clamped to 0")
        fm = 0.0
    if lm < 0:
        warnings.append(f"liquidation_multiplier {lm} clamped to 0")
        lm = 0.0

    # Enforce ordering: replacement >= fair_market >= liquidation
    # If the caller passes them in wrong order, clamp conservatively.
    if fm > rm:
        warnings.append(
            f"fair_market_multiplier ({fm}) > replacement_multiplier ({rm}); "
            "clamped to replacement_multiplier"
        )
        fm = rm
    if lm > fm:
        warnings.append(
            f"liquidation_multiplier ({lm}) > fair_market_multiplier ({fm}); "
            "clamped to fair_market_multiplier"
        )
        lm = fm

    # --- Basic piece fields ---
    if not isinstance(piece, dict):
        warnings.append("piece must be a dict; returning empty appraisal")
        piece = {}

    piece_id = piece.get("id") or piece.get("piece_id") or None
    description = str(piece.get("description", "Jewelry piece")).strip()
    piece_type = str(piece.get("piece_type", "other")).strip().lower()
    if piece_type not in _PIECE_TYPES:
        warnings.append(
            f"piece_type {piece_type!r} not in known types {sorted(_PIECE_TYPES)}; "
            "recorded as-is"
        )

    # --- Appraisal date ---
    appraisal_date = cfg.date_of_appraisal
    if appraisal_date is None:
        try:
            appraisal_date = date.today().isoformat()
        except Exception:
            appraisal_date = "unknown"

    # --- Stone schedule ---
    raw_stones = piece.get("stones") or []
    if not isinstance(raw_stones, list):
        warnings.append("stones must be a list; treating as no stones")
        raw_stones = []

    stones_schedule, total_stone_value = _build_stone_schedule(raw_stones, warnings)

    # --- Metal schedule ---
    metal_spec = piece.get("metal")
    if not isinstance(metal_spec, dict):
        if metal_spec is not None:
            warnings.append("piece.metal must be a dict; metal value set to 0")
        metal_spec = {"alloy": "", "weight_grams": 0.0, "spot_price_per_gram": 0.0}

    metal_schedule, metal_value = _build_metal_schedule(metal_spec, warnings)

    # --- Labor ---
    labor_raw = piece.get("labor_value", 0.0)
    labor_value = _safe_float(labor_raw, 0.0)
    if labor_value < 0:
        warnings.append(
            f"labor_value {labor_raw!r} < 0; clamped to 0"
        )
        labor_value = 0.0

    # --- Base value = stones + metal + labor ---
    base_value = round(total_stone_value + metal_value + labor_value, 4)

    # --- Three valuation levels ---
    replacement_value = round(base_value * rm, 4)
    fair_market_value = round(replacement_value * fm, 4)
    liquidation_value = round(replacement_value * lm, 4)

    # Guarantee ordering invariant post-multiplication rounding
    fair_market_value = min(fair_market_value, replacement_value)
    liquidation_value = min(liquidation_value, fair_market_value)

    # --- Appraiser dict ---
    appraiser = {
        "name":        cfg.appraiser_name or "Appraiser",
        "credentials": cfg.appraiser_credentials or "",
        "location":    cfg.appraiser_location or "",
    }

    result: dict = {
        "piece_id":           piece_id,
        "description":        description,
        "piece_type":         piece_type,
        "appraisal_date":     appraisal_date,
        "purpose":            cfg.purpose,
        "stones_schedule":    stones_schedule,
        "metal_schedule":     metal_schedule,
        "labor_value":        round(labor_value, 4),
        "total_stone_value":  total_stone_value,
        "base_value":         base_value,
        "replacement_value":  replacement_value,
        "fair_market_value":  fair_market_value,
        "liquidation_value":  liquidation_value,
        "methodology":        cfg.methodology,
        "appraiser":          appraiser,
        "warnings":           warnings,
    }

    # --- Markdown certificate ---
    try:
        result["certificate_md"] = _render_certificate_md(result, cfg)
    except Exception as exc:
        result["certificate_md"] = f"*Certificate rendering failed: {exc}*"
        warnings.append(f"certificate rendering error: {exc}")

    return result


# ---------------------------------------------------------------------------
# value_summary
# ---------------------------------------------------------------------------

def value_summary(appraisal_result: dict) -> dict:
    """Return a compact value summary from an appraise() result dict.

    Parameters
    ----------
    appraisal_result : dict
        Return value of appraise().

    Returns
    -------
    dict:
        replacement   — replacement (retail) value
        fair_market   — fair-market value
        liquidation   — liquidation value
        base          — base value (stones + metal + labor)
        currency      — "USD"

    Never raises; returns zero values if input is not a valid appraisal.
    """
    if not isinstance(appraisal_result, dict):
        return {
            "replacement": 0.0,
            "fair_market": 0.0,
            "liquidation": 0.0,
            "base": 0.0,
            "currency": "USD",
        }
    return {
        "replacement": _safe_float(appraisal_result.get("replacement_value"), 0.0),
        "fair_market": _safe_float(appraisal_result.get("fair_market_value"), 0.0),
        "liquidation": _safe_float(appraisal_result.get("liquidation_value"), 0.0),
        "base": _safe_float(appraisal_result.get("base_value"), 0.0),
        "currency": "USD",
    }


# ---------------------------------------------------------------------------
# LLM tool: jewelry_appraise
# ---------------------------------------------------------------------------

_appraise_spec = ToolSpec(
    name="jewelry_appraise",
    description=(
        "Generate a comprehensive insurance / replacement appraisal document "
        "for a finished jewelry piece.\n\n"
        "Produces:\n"
        "  - Itemised gemstone schedule (cut, carat, color/clarity grades, "
        "cert reference, per-stone value from grade-adjusted price band)\n"
        "  - Metal schedule (alloy, weight, spot price + fabrication premium)\n"
        "  - Labor and setting valuation\n"
        "  - Three valuation levels: replacement (retail) >= fair-market >= liquidation\n"
        "  - Methodology statement and appraiser declaration\n"
        "  - Formatted Markdown certificate\n\n"
        "All values in USD. Gemstone prices are derived from GEM_STUDIO_CATALOG "
        "price bands, adjusted for color/clarity grade and carat size premium, "
        "unless an explicit price_per_carat is supplied per stone.\n\n"
        "Returns the full appraisal dict including certificate_md (Markdown text)."
    ),
    input_schema={
        "type": "object",
        "required": ["piece"],
        "properties": {
            "piece": {
                "type": "object",
                "description": (
                    "Jewelry piece spec dict. Required sub-keys:\n"
                    "  description (str), metal.alloy (str), "
                    "metal.weight_grams (float), metal.spot_price_per_gram (float).\n"
                    "Optional: id, piece_type, stones[], labor_value, notes."
                ),
            },
            "replacement_multiplier": {
                "type": "number",
                "description": (
                    "Multiplier applied to base value to compute replacement value. "
                    "Default 1.0 (retail replacement = base)."
                ),
            },
            "fair_market_multiplier": {
                "type": "number",
                "description": (
                    "Fraction of replacement value for fair-market estimate. "
                    "Default 0.70."
                ),
            },
            "liquidation_multiplier": {
                "type": "number",
                "description": (
                    "Fraction of replacement value for liquidation / distressed-sale "
                    "estimate. Default 0.40."
                ),
            },
            "appraiser_name": {
                "type": "string",
                "description": "Name of the appraiser. Default 'Appraiser'.",
            },
            "appraiser_credentials": {
                "type": "string",
                "description": "Appraiser credentials (GIA GG, ASA, etc.).",
            },
            "appraiser_location": {
                "type": "string",
                "description": "Appraiser business location.",
            },
            "date_of_appraisal": {
                "type": "string",
                "description": "ISO-8601 date of appraisal. Defaults to today.",
            },
            "purpose": {
                "type": "string",
                "description": "Appraisal purpose. Default 'Insurance / Replacement'.",
            },
        },
    },
)


@register(_appraise_spec, write=False)
async def run_jewelry_appraise(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    piece = a.get("piece")
    if not isinstance(piece, dict):
        return err_payload("piece must be a dict", "BAD_ARGS")

    cfg = AppraisalConfig()

    # Optional overrides from args
    for attr, key in [
        ("replacement_multiplier", "replacement_multiplier"),
        ("fair_market_multiplier", "fair_market_multiplier"),
        ("liquidation_multiplier", "liquidation_multiplier"),
    ]:
        if key in a:
            try:
                setattr(cfg, attr, float(a[key]))
            except (TypeError, ValueError):
                return err_payload(f"{key} must be a number", "BAD_ARGS")

    for attr, key in [
        ("appraiser_name", "appraiser_name"),
        ("appraiser_credentials", "appraiser_credentials"),
        ("appraiser_location", "appraiser_location"),
        ("date_of_appraisal", "date_of_appraisal"),
        ("purpose", "purpose"),
    ]:
        if key in a:
            setattr(cfg, attr, str(a[key]))

    result = appraise(piece, cfg)
    return ok_payload(result)


# ---------------------------------------------------------------------------
# LLM tool: jewelry_value_summary
# ---------------------------------------------------------------------------

_value_summary_spec = ToolSpec(
    name="jewelry_value_summary",
    description=(
        "Extract a compact value summary from a jewelry_appraise result.\n\n"
        "Returns {replacement, fair_market, liquidation, base, currency} — "
        "all in USD. Pass the full appraisal dict from jewelry_appraise."
    ),
    input_schema={
        "type": "object",
        "required": ["appraisal"],
        "properties": {
            "appraisal": {
                "type": "object",
                "description": "Full appraisal dict returned by jewelry_appraise.",
            },
        },
    },
)


@register(_value_summary_spec, write=False)
async def run_jewelry_value_summary(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

    appraisal = a.get("appraisal")
    if not isinstance(appraisal, dict):
        return err_payload("appraisal must be a dict from jewelry_appraise", "BAD_ARGS")

    summary = value_summary(appraisal)
    return ok_payload(summary)
