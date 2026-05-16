"""
ibis_reader.py — IBIS (I/O Buffer Information Specification) file reader.

Parses IBIS files conforming to ANSI/EIA-656 (versions 1.x – 6.x) into a
structured Kerf model.  Pure Python — stdlib only; IBIS is a line-oriented
keyword text format, not XML.

Supported IBIS sections
-----------------------
  [IBIS Ver]            → ibis_version string
  [File Name]           → file_name string (optional metadata)
  [File Rev]            → file_rev string  (optional metadata)
  [Component]           → component name, manufacturer
  [Manufacturer]        → manufacturer name (alt location)
  [Package]             → R_pkg / L_pkg / C_pkg with typ/min/max columns
  [Pin]                 → pin table: signal_name, model_name, R/L/C per pin
  [Model]               → Model_type, C_comp, Vinl, Vinh, Vmeas columns
  [Voltage Range]       → typ/min/max supply voltage
  [Pullup] / [Pulldown] → V-I table rows (voltage, typ/min/max current)
  [GND_clamp]           → V-I table rows
  [POWER_clamp]         → V-I table rows
  [Ramp]                → dV/dt_r and dV/dt_f (rise/fall) entries
  [Temperature Range]   → typ/min/max temperature

Unsupported keywords → collected in ``warnings`` list, never raise.

Output model (on success)
--------------------------
  {
    "ok": True,
    "ibis_version": str,
    "file_name": str | None,
    "file_rev":  str | None,
    "components": [
      {
        "name": str,
        "manufacturer": str | None,
        "package": {
          "R_pkg": {"typ": float|None, "min": float|None, "max": float|None},
          "L_pkg": {"typ": float|None, "min": float|None, "max": float|None},
          "C_pkg": {"typ": float|None, "min": float|None, "max": float|None},
        },
        "pins": [
          {
            "name": str,
            "signal_name": str,
            "model_name": str,
            "R_pin": float | None,
            "L_pin": float | None,
            "C_pin": float | None,
          },
          ...
        ],
      },
      ...
    ],
    "models": {
      "<model_name>": {
        "name": str,
        "model_type": str,       # "Output" | "Input" | "I/O" | "3-state" | ...
        "c_comp": {"typ": float|None, "min": float|None, "max": float|None},
        "vinl": float | None,
        "vinh": float | None,
        "vmeas": float | None,
        "voltage_range": {"typ": float|None, "min": float|None, "max": float|None},
        "pulldown": [{"V": float, "typ": float|None, "min": float|None, "max": float|None}, ...],
        "pullup":   [{"V": float, "typ": float|None, "min": float|None, "max": float|None}, ...],
        "gnd_clamp": [...],
        "power_clamp": [...],
        "ramp": {
          "dV_dt_r": {"typ": str|None, "min": str|None, "max": str|None},
          "dV_dt_f": {"typ": str|None, "min": str|None, "max": str|None},
        },
        "temperature_range": {"typ": float|None, "min": float|None, "max": float|None},
      },
      ...
    },
    "warnings": [str, ...],
  }

On error:
  {"ok": False, "reason": str}

Never raises.

LLM tool ``import_ibis`` registered via @register; gated on "imports.ibis".
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unit suffix conversion
# ---------------------------------------------------------------------------

# Multiplier map for SI prefixes used in IBIS files (case-sensitive per spec,
# but we normalise to lower-case for robustness).
_UNIT_MAP: dict[str, float] = {
    "f":  1e-15,   # femto
    "p":  1e-12,   # pico
    "n":  1e-9,    # nano
    "u":  1e-6,    # micro
    "m":  1e-3,    # milli
    "k":  1e3,     # kilo
    "meg": 1e6,    # mega (IBIS uses "Meg" or "meg")
    "g":  1e9,     # giga
    "t":  1e12,    # tera
}

_NUM_RE = re.compile(
    r"""
    ^\s*
    ([+-]?                          # optional sign
      (?:\d+\.?\d*|\.\d+)           # digits
      (?:[eE][+-]?\d+)?             # optional exponent
    )
    \s*
    (f|p|n|u|m|k|Meg|meg|G|g|T|t)? # optional SI prefix (case-insensitive kept)
    \s*
    [a-zA-Z/°]*                     # optional unit label (V, A, Ohm, H, F, …)
    \s*$
    """,
    re.VERBOSE,
)


def _parse_value(token: str) -> Optional[float]:
    """
    Convert an IBIS value token (e.g. "1.5pF", "33n", "0.1", "NA") to float.

    Returns None for NA/na/missing/unparseable tokens.
    """
    if not token:
        return None
    t = token.strip()
    if t.upper() in ("NA", "N/A", "-", ""):
        return None
    m = _NUM_RE.match(t)
    if not m:
        return None
    mantissa = float(m.group(1))
    prefix = m.group(2)
    if prefix is None:
        return mantissa
    mult = _UNIT_MAP.get(prefix.lower(), None)
    if mult is None:
        # Unknown prefix — treat as no multiplier
        return mantissa
    return mantissa * mult


# ---------------------------------------------------------------------------
# Line preprocessing helpers
# ---------------------------------------------------------------------------

def _strip_comment(line: str) -> str:
    """Remove IBIS '|' comment and trailing whitespace from a line."""
    idx = line.find("|")
    if idx >= 0:
        line = line[:idx]
    return line.rstrip()


def _keyword_name(line: str) -> Optional[str]:
    """
    If *line* is an IBIS keyword line (starts with '['), return the keyword
    name (normalised, without brackets).  Otherwise return None.
    """
    stripped = line.strip()
    if stripped.startswith("[") and "]" in stripped:
        end = stripped.index("]")
        return stripped[1:end].strip()
    return None


def _keyword_value(line: str) -> str:
    """Return the text that follows the closing ']' on a keyword line."""
    stripped = line.strip()
    if "]" in stripped:
        return stripped[stripped.index("]") + 1:].strip()
    return ""


# ---------------------------------------------------------------------------
# typ/min/max column parsing
# ---------------------------------------------------------------------------

def _parse_tmc(tokens: list[str], start: int = 0) -> dict[str, Optional[float]]:
    """
    Parse typ / min / max from tokens at positions start, start+1, start+2.
    Missing positions or NA tokens yield None.
    """
    def _safe(idx: int) -> Optional[float]:
        if idx >= len(tokens):
            return None
        return _parse_value(tokens[idx])

    return {
        "typ": _safe(start),
        "min": _safe(start + 1),
        "max": _safe(start + 2),
    }


# ---------------------------------------------------------------------------
# IBIS file tokeniser / section iterator
# ---------------------------------------------------------------------------

def _iter_sections(text: str):
    """
    Yield ``(keyword, value, body_lines)`` tuples where:
      - ``keyword``    is the text between [ ] (normalised, lower-case)
      - ``value``      is the text on the same line after ']'
      - ``body_lines`` is a list of pre-processed (comment-stripped) lines
                       that belong to the section, up to (not including) the
                       next keyword line or end-of-file.

    Comment-only lines and blank lines within a body are included so that
    continuation-line handling in callers can work correctly.
    """
    lines = text.splitlines()
    current_kw: Optional[str] = None
    current_val: str = ""
    current_body: list[str] = []

    for raw in lines:
        clean = _strip_comment(raw)
        kw = _keyword_name(clean)

        if kw is not None:
            # Flush previous section
            if current_kw is not None:
                yield current_kw, current_val, current_body
            current_kw = kw
            current_val = _keyword_value(clean)
            current_body = []
        else:
            if current_kw is not None:
                current_body.append(clean)

    # Flush last section
    if current_kw is not None:
        yield current_kw, current_val, current_body


# ---------------------------------------------------------------------------
# Pin table parser
# ---------------------------------------------------------------------------

def _parse_pin_table(body_lines: list[str]) -> list[dict]:
    """
    Parse [Pin] table lines into a list of pin dicts.

    Each data line has the form:
      pin_name  signal_name  model_name  [R_pin  L_pin  C_pin]
    Header line(s) begin with "signal_name" (case-insensitive) and are skipped.
    """
    pins: list[dict] = []
    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("signal_name"):
            continue  # header row
        tokens = stripped.split()
        if len(tokens) < 3:
            continue
        pin: dict[str, Any] = {
            "name": tokens[0],
            "signal_name": tokens[1],
            "model_name": tokens[2],
            "R_pin": _parse_value(tokens[3]) if len(tokens) > 3 else None,
            "L_pin": _parse_value(tokens[4]) if len(tokens) > 4 else None,
            "C_pin": _parse_value(tokens[5]) if len(tokens) > 5 else None,
        }
        pins.append(pin)
    return pins


# ---------------------------------------------------------------------------
# V-I table parser
# ---------------------------------------------------------------------------

def _parse_vi_table(body_lines: list[str]) -> list[dict]:
    """
    Parse a V-I table (Pullup, Pulldown, GND_clamp, POWER_clamp).

    Each data row: voltage  typ_I  [min_I  max_I]
    Returns list of {"V": float, "typ": ..., "min": ..., "max": ...}.
    Skips header/comment/blank lines.
    """
    rows: list[dict] = []
    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip sub-keyword lines (e.g. [End]) or header rows containing "Voltage"
        if stripped.startswith("["):
            break
        if re.match(r"^[Vv]oltage", stripped):
            continue
        tokens = stripped.split()
        if len(tokens) < 2:
            continue
        v = _parse_value(tokens[0])
        if v is None:
            continue
        tmc = _parse_tmc(tokens, start=1)
        rows.append({"V": v, **tmc})
    return rows


# ---------------------------------------------------------------------------
# Package section parser
# ---------------------------------------------------------------------------

_PKG_KEYS = {
    "r_pkg": "R_pkg",
    "l_pkg": "L_pkg",
    "c_pkg": "C_pkg",
}


def _parse_package(body_lines: list[str]) -> dict:
    """
    Parse [Package] section lines.

    Each line:  R_pkg  typ  [min  max]
    Returns {"R_pkg": {typ/min/max}, "L_pkg": {...}, "C_pkg": {...}}.
    """
    pkg: dict[str, Any] = {
        "R_pkg": {"typ": None, "min": None, "max": None},
        "L_pkg": {"typ": None, "min": None, "max": None},
        "C_pkg": {"typ": None, "min": None, "max": None},
    }
    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("["):
            break
        tokens = stripped.split()
        if not tokens:
            continue
        key_raw = tokens[0].lower()
        canonical = _PKG_KEYS.get(key_raw)
        if canonical and len(tokens) >= 2:
            pkg[canonical] = _parse_tmc(tokens, start=1)
    return pkg


# ---------------------------------------------------------------------------
# Ramp section parser
# ---------------------------------------------------------------------------

def _parse_ramp(body_lines: list[str]) -> dict:
    """
    Parse [Ramp] section.

    Lines of interest:
      dV/dt_r   typ_val  [min_val  max_val]
      dV/dt_f   typ_val  [min_val  max_val]

    Values may be "0.6V/1.2ns" style — stored as raw strings (not converted
    to float) because they are differential expressions, but the split
    position (typ/min/max) is preserved.
    """
    ramp: dict[str, Any] = {
        "dV_dt_r": {"typ": None, "min": None, "max": None},
        "dV_dt_f": {"typ": None, "min": None, "max": None},
    }
    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("["):
            break
        tokens = stripped.split()
        if not tokens:
            continue
        key_raw = tokens[0].lower().replace("/", "_")
        if key_raw in ("dv_dt_r", "dvdt_r"):
            ramp["dV_dt_r"] = {
                "typ": tokens[1] if len(tokens) > 1 else None,
                "min": tokens[2] if len(tokens) > 2 else None,
                "max": tokens[3] if len(tokens) > 3 else None,
            }
        elif key_raw in ("dv_dt_f", "dvdt_f"):
            ramp["dV_dt_f"] = {
                "typ": tokens[1] if len(tokens) > 1 else None,
                "min": tokens[2] if len(tokens) > 2 else None,
                "max": tokens[3] if len(tokens) > 3 else None,
            }
    return ramp


# ---------------------------------------------------------------------------
# Model section parser
# ---------------------------------------------------------------------------

_MODEL_SCALAR_KEYS = {
    "vinl": "vinl",
    "vinh": "vinh",
    "vmeas": "vmeas",
}

# Sub-sections that have their own V-I body accumulation
_VI_SUBSECTIONS = {
    "pulldown": "pulldown",
    "pullup":   "pullup",
    "gnd_clamp": "gnd_clamp",
    "power_clamp": "power_clamp",
}


def _make_empty_model(name: str) -> dict:
    """Return an empty model dict with all fields at their defaults."""
    return {
        "name": name,
        "model_type": None,
        "c_comp": {"typ": None, "min": None, "max": None},
        "vinl": None,
        "vinh": None,
        "vmeas": None,
        "voltage_range": {"typ": None, "min": None, "max": None},
        "pulldown": [],
        "pullup": [],
        "gnd_clamp": [],
        "power_clamp": [],
        "ramp": {
            "dV_dt_r": {"typ": None, "min": None, "max": None},
            "dV_dt_f": {"typ": None, "min": None, "max": None},
        },
        "temperature_range": {"typ": None, "min": None, "max": None},
    }


def _parse_model_scalars(body_lines: list[str], model: dict) -> None:
    """
    Parse scalar keywords from the [Model] section body into *model* in-place.

    Only Model_type, C_comp, Vinl, Vinh, Vmeas are handled here.  The V-I
    sub-sections ([Pulldown], [Ramp], etc.) are top-level IBIS sections that
    the main parser dispatches separately.
    """
    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            continue
        tokens = stripped.split()
        if not tokens:
            continue
        key_raw = tokens[0].lower()

        if key_raw == "model_type" and len(tokens) >= 2:
            model["model_type"] = tokens[1]
        elif key_raw == "c_comp" and len(tokens) >= 2:
            model["c_comp"] = _parse_tmc(tokens, start=1)
        elif key_raw in _MODEL_SCALAR_KEYS and len(tokens) >= 2:
            model[_MODEL_SCALAR_KEYS[key_raw]] = _parse_value(tokens[1])


# ---------------------------------------------------------------------------
# Top-level parser
# ---------------------------------------------------------------------------

# Known keywords that are intentionally not parsed (logged as warning once)
_KNOWN_UNSUPPORTED = frozenset({
    "file name", "file rev", "date", "source", "notes", "disclaimer",
    "copyright", "begin board description", "end board description",
    "driver schedule", "add submodel", "submodel", "begin submodel",
    "end submodel", "test data", "begin test data", "end test data",
    "test load", "driver waveform", "input waveform",
    "rising waveform", "falling waveform",
    "composite current", "ignore bits", "bit vectors",
    "series mosfet models", "series pin mapping",
    "diff pin",
})


def parse_ibis(text: str | bytes) -> dict:
    """
    Parse an IBIS file from a string or bytes.

    Returns the Kerf IBIS model (see module docstring).
    Never raises — errors surface as {"ok": False, "reason": str}.
    """
    warns: list[str] = []

    try:
        if isinstance(text, bytes):
            try:
                text = text.decode("utf-8")
            except UnicodeDecodeError:
                text = text.decode("latin-1", errors="replace")

        if not text or not text.strip():
            return {"ok": False, "reason": "empty input"}

        ibis_version: Optional[str] = None
        file_name: Optional[str] = None
        file_rev: Optional[str] = None

        # Component-level state
        components: list[dict] = []
        cur_comp: Optional[dict] = None

        # Model-level state — IBIS models are defined by [Model] followed by
        # optional sub-sections ([Pulldown], [Ramp], [Voltage Range], etc.)
        # that appear as separate top-level sections until the next [Model],
        # [Component], or [End] keyword.
        models: dict[str, dict] = {}
        cur_model: Optional[dict] = None

        sections = list(_iter_sections(text))

        # First pass: check there is an [IBIS Ver] section
        has_ver = any(kw.lower() == "ibis ver" for kw, _, _ in sections)
        if not has_ver:
            return {"ok": False, "reason": "missing [IBIS Ver] keyword"}

        for kw, val, body in sections:
            kw_lower = kw.lower().strip()

            # ── Top-level metadata ─────────────────────────────────────────
            if kw_lower == "ibis ver":
                ibis_version = val.strip() or (body[0].strip() if body else None)
                continue

            if kw_lower == "file name":
                file_name = val.strip() or (body[0].strip() if body else None)
                continue

            if kw_lower == "file rev":
                file_rev = val.strip() or (body[0].strip() if body else None)
                continue

            # ── Component ─────────────────────────────────────────────────
            if kw_lower == "component":
                # Starting a new component ends any in-progress model context
                cur_model = None
                if cur_comp is not None:
                    components.append(cur_comp)
                cur_comp = {
                    "name": val.strip(),
                    "manufacturer": None,
                    "package": {
                        "R_pkg": {"typ": None, "min": None, "max": None},
                        "L_pkg": {"typ": None, "min": None, "max": None},
                        "C_pkg": {"typ": None, "min": None, "max": None},
                    },
                    "pins": [],
                }
                continue

            if kw_lower == "manufacturer":
                mfr = val.strip()
                if not mfr and body:
                    mfr = body[0].strip()
                if cur_comp is not None:
                    cur_comp["manufacturer"] = mfr or None
                continue

            if kw_lower == "package":
                if cur_comp is not None:
                    cur_comp["package"] = _parse_package(body)
                continue

            if kw_lower == "pin":
                if cur_comp is not None:
                    cur_comp["pins"] = _parse_pin_table(body)
                continue

            # ── Model ──────────────────────────────────────────────────────
            if kw_lower == "model":
                model_name = val.strip()
                if model_name:
                    cur_model = _make_empty_model(model_name)
                    _parse_model_scalars(body, cur_model)
                    models[model_name] = cur_model
                continue

            # ── Model sub-sections (belong to cur_model context) ───────────
            if kw_lower == "voltage range":
                if cur_model is not None:
                    # body[0] contains "typ  min  max"
                    for line in body:
                        stripped = line.strip()
                        if stripped:
                            cur_model["voltage_range"] = _parse_tmc(stripped.split(), start=0)
                            break
                continue

            if kw_lower == "temperature range":
                if cur_model is not None:
                    for line in body:
                        stripped = line.strip()
                        if stripped:
                            cur_model["temperature_range"] = _parse_tmc(stripped.split(), start=0)
                            break
                continue

            if kw_lower == "pulldown":
                if cur_model is not None:
                    cur_model["pulldown"] = _parse_vi_table(body)
                continue

            if kw_lower == "pullup":
                if cur_model is not None:
                    cur_model["pullup"] = _parse_vi_table(body)
                continue

            if kw_lower == "gnd_clamp":
                if cur_model is not None:
                    cur_model["gnd_clamp"] = _parse_vi_table(body)
                continue

            if kw_lower == "power_clamp":
                if cur_model is not None:
                    cur_model["power_clamp"] = _parse_vi_table(body)
                continue

            if kw_lower == "ramp":
                if cur_model is not None:
                    cur_model["ramp"] = _parse_ramp(body)
                continue

            # ── End ────────────────────────────────────────────────────────
            if kw_lower == "end":
                # Flush current component
                if cur_comp is not None:
                    components.append(cur_comp)
                    cur_comp = None
                cur_model = None
                continue

            # ── Unknown / unsupported keywords ─────────────────────────────
            if kw_lower not in _KNOWN_UNSUPPORTED:
                warns.append(f"unsupported keyword [{kw}] skipped")
            # Known-unsupported: silently skip

        # Flush trailing component if [End] was absent
        if cur_comp is not None:
            components.append(cur_comp)

        if ibis_version is None:
            return {"ok": False, "reason": "could not determine IBIS version"}

        return {
            "ok": True,
            "ibis_version": ibis_version,
            "file_name": file_name,
            "file_rev": file_rev,
            "components": components,
            "models": models,
            "warnings": warns,
        }

    except Exception as exc:
        return {"ok": False, "reason": f"unexpected error: {exc}"}


# ---------------------------------------------------------------------------
# LLM tool (gated — only registered when Kerf runtime is available)
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx

    _import_ibis_spec = ToolSpec(
        name="import_ibis",
        description=(
            "Import an IBIS (I/O Buffer Information Specification, ANSI/EIA-656) "
            "signal-integrity model file into the current project. "
            "Accepts a blob_id or storage_key pointing to the uploaded .ibs file. "
            "Parses component/pin tables, buffer models (Output/Input/I/O/3-state), "
            "package parasitics (R/L/C), V-I tables, ramp data, and voltage/temperature "
            "ranges.  Returns a structured model with components, pins, and models. "
            "Gate: imports.ibis capability."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "UUID of the target Kerf project.",
                },
                "file_blob_id_or_storage_key": {
                    "type": "string",
                    "description": "Blob ID or storage key for the .ibs file.",
                },
                "import_folder": {
                    "type": "string",
                    "description": (
                        "Path in the project tree for the imported file. "
                        "Defaults to /ibis_import."
                    ),
                },
            },
            "required": ["project_id", "file_blob_id_or_storage_key"],
        },
    )

    @register(_import_ibis_spec, write=True)
    async def run_import_ibis(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        project_id = a.get("project_id", "").strip()
        blob_ref = a.get("file_blob_id_or_storage_key", "").strip()
        import_folder = a.get("import_folder", "/ibis_import").strip()

        if not project_id:
            return err_payload("project_id is required", "BAD_ARGS")
        if not blob_ref:
            return err_payload("file_blob_id_or_storage_key is required", "BAD_ARGS")

        if ctx.storage is None:
            return err_payload("storage backend not configured", "NO_STORAGE")

        try:
            blob_bytes = await ctx.storage.get(blob_ref)
        except Exception as exc:
            return err_payload(f"failed to fetch blob {blob_ref!r}: {exc}", "STORAGE_ERROR")

        if not blob_bytes:
            return err_payload(f"blob not found: {blob_ref}", "NOT_FOUND")

        model = parse_ibis(blob_bytes)
        if not model.get("ok"):
            return err_payload(model.get("reason", "IBIS parse failed"), "PARSE_ERROR")

        try:
            _pid = uuid.UUID(project_id)
        except Exception:
            return err_payload("project_id must be a valid UUID", "BAD_ARGS")

        fid = uuid.uuid4()
        content = json.dumps({
            "version": 1,
            "ibis_version": model["ibis_version"],
            "components": model["components"],
            "models": model["models"],
        })

        try:
            ctx.pool.execute(
                "insert into files (id, project_id, name, kind, content, "
                "created_at, updated_at) values ($1, $2, $3, $4, $5, now(), now())",
                fid, _pid,
                f"{import_folder}/ibis_model.json",
                "ibis_model",
                content,
            )
        except Exception as exc:
            model["warnings"].append(f"failed to persist IBIS file: {exc}")

        total_pins = sum(len(c["pins"]) for c in model["components"])

        return ok_payload({
            "ok": True,
            "file_id": str(fid),
            "ibis_version": model["ibis_version"],
            "component_count": len(model["components"]),
            "pin_count": total_pins,
            "model_count": len(model["models"]),
            "warnings": model["warnings"],
        })

    # Expose TOOLS list for plugin loader (mirrors qif_reader pattern).
    TOOLS = []  # tools registered via @register decorator; list kept for symmetry

except ImportError:
    # Standalone / test mode — no Kerf runtime available
    pass
