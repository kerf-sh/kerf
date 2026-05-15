"""
Assembly variant system for CircuitJSON boards.

Defines named build variants that carry per-refdes overrides:
  - fitted: false  → DNP (do-not-populate): component excluded from P&P and
                      flagged in BOM
  - value           → alternate component value for this variant
  - mpn             → alternate MPN
  - footprint       → alternate footprint

Variant model
─────────────
A variant is a lightweight dict overlay keyed by source_component_id (or
refdes name).  It does NOT mutate circuit_json; instead it patches a deep
copy of the source_component elements before delegating to the existing
export_fab_bom / export_pnp generators.

The overlay is applied at the source_component level so that both BOM and
P&P generators see a consistent "patched" circuit — they don't need to know
about variants at all.

Overlay precedence (per refdes, per field):
  variant override > original circuit_json value

DNP handling
────────────
If a refdes override carries ``fitted: false``, the corresponding
pcb_component element is removed from the patched circuit.  This means:

  BOM  — export_fab_bom skips unplaced source_components (its existing
          logic: "if we have pcb_components at all, skip unplaced sources").
          The DNP part disappears from the placed count.  We add an
          informational DNP section to the BOM output as a separate CSV
          with suffix ``-dnp.csv``.

  P&P  — export_pnp only processes pcb_component elements, so removing the
          pcb_component is sufficient to exclude a DNP part entirely.

LLM tools registered
─────────────────────
  define_variant      — create / update a named variant in the session store
  list_variants       — list variants currently defined in the session store
  variant_bom         — produce per-variant fab BOM CSV using export_fab_bom
  variant_fab         — produce per-variant complete fab package zip

Registry
────────
Registered via the existing @register decorator from kerf_chat.tools.registry;
plugin.py adds one line to _register_tools.
"""

from __future__ import annotations

import base64
import copy
import io
import json
import zipfile
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

from kerf_electronics.fab.fab_bom import export_fab_bom, _extract_bom_rows, _render_csv
from kerf_electronics.fab.pnp import export_pnp
from kerf_electronics.fab.gerber import export_gerber
from kerf_electronics.fab.excellon import export_excellon
from kerf_electronics.fab.ipc2581 import export_ipc2581


# ─── In-process variant store ─────────────────────────────────────────────────
# Maps variant_name → {refdes_or_source_id → override_dict}
# This is a simple process-level dict. In a real session the LLM would pass
# stored variants back as JSON; the store is also accepted as an explicit
# argument on the BOM/fab tools so callers can pass serialised variants.

_VARIANT_STORE: dict[str, dict[str, dict]] = {}

# ─── Overlay application ──────────────────────────────────────────────────────

_OVERRIDE_FIELDS = ("value", "mpn", "footprint", "manufacturer", "description")


def _apply_variant(
    circuit_json: list[dict],
    overrides: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    """Return (patched_circuit, dnp_sources) by applying variant overrides.

    Args:
        circuit_json:  Original CircuitJSON array (not mutated).
        overrides:     Mapping of {source_component_id_or_refdes_name → override_dict}.
                       Each override may contain any of: fitted (bool), value, mpn,
                       footprint, manufacturer, description.

    Returns:
        patched_circuit: Deep-copied circuit with overrides applied and DNP
                         pcb_component elements removed.
        dnp_sources:     List of original source_component dicts for DNP parts
                         (fitted=false) for inclusion in the DNP BOM section.
    """
    patched = copy.deepcopy(circuit_json)

    # Build index: source_component_id → element (in patched copy)
    src_by_id: dict[str, dict] = {}
    src_by_name: dict[str, dict] = {}
    for el in patched:
        if el.get("type") == "source_component":
            sid = el.get("source_component_id", el.get("id", ""))
            name = el.get("name", el.get("refdes", ""))
            if sid:
                src_by_id[sid] = el
            if name:
                src_by_name[name] = el

    def _find_src(key: str) -> dict | None:
        return src_by_id.get(key) or src_by_name.get(key)

    # Determine DNP source_component_ids
    dnp_sids: set[str] = set()
    for key, ov in overrides.items():
        src = _find_src(key)
        if src is None:
            continue
        if ov.get("fitted") is False or str(ov.get("fitted", "")).lower() == "false":
            sid = src.get("source_component_id", src.get("id", ""))
            if sid:
                dnp_sids.add(sid)
        else:
            # Apply field overrides (non-DNP)
            for field in _OVERRIDE_FIELDS:
                if field in ov:
                    src[field] = ov[field]

    # Collect original source dicts for DNP report (before patching strips them)
    # We need the originals for the DNP section — re-read from unpatched circuit
    original_src_by_id: dict[str, dict] = {}
    for el in circuit_json:
        if el.get("type") == "source_component":
            sid = el.get("source_component_id", el.get("id", ""))
            if sid:
                original_src_by_id[sid] = el

    dnp_sources = [original_src_by_id[sid] for sid in dnp_sids if sid in original_src_by_id]

    # Remove pcb_component elements for DNP parts
    patched = [
        el for el in patched
        if not (
            el.get("type") == "pcb_component"
            and el.get("source_component_id", "") in dnp_sids
        )
    ]

    return patched, dnp_sources


def _dnp_csv(dnp_sources: list[dict]) -> str:
    """Render a minimal CSV listing DNP parts (refdes + value + mpn)."""
    buf = io.StringIO()
    buf.write("Refdes,Value,Footprint,MPN,Note\n")
    for src in sorted(dnp_sources, key=lambda s: s.get("name", "")):
        refdes = src.get("name", src.get("refdes", ""))
        value = src.get("value", src.get("part_value", ""))
        footprint = src.get("footprint", src.get("ftype", ""))
        mpn = src.get("mpn", src.get("manufacturer_part_number", ""))
        buf.write(f"{refdes},{value},{footprint},{mpn},DNP\n")
    return buf.getvalue()


# ─── Tool: define_variant ─────────────────────────────────────────────────────

define_variant_spec = ToolSpec(
    name="define_variant",
    description=(
        "Define or update a named assembly variant for a CircuitJSON board. "
        "A variant carries per-refdes overrides: set fitted=false to mark a component "
        "DNP (do-not-populate), or supply alternate value/MPN/footprint for a build "
        "configuration (e.g. 'debug', 'production', 'low-cost'). "
        "The variant is stored by name in the session and can be referenced by "
        "variant_bom and variant_fab tools. "
        "Call list_variants to see all currently defined variants."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "variant_name": {
                "type": "string",
                "description": "Name for the variant (e.g. 'production', 'debug', 'low-cost').",
            },
            "overrides": {
                "type": "object",
                "description": (
                    "Mapping of refdes (e.g. 'R1', 'U2') or source_component_id → "
                    "override dict. Each override may include: "
                    "fitted (bool, false=DNP), value (string), mpn (string), "
                    "footprint (string), manufacturer (string), description (string)."
                ),
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "fitted": {"type": "boolean"},
                        "value": {"type": "string"},
                        "mpn": {"type": "string"},
                        "footprint": {"type": "string"},
                        "manufacturer": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
            "description": {
                "type": "string",
                "description": "Optional human-readable description of the variant.",
            },
        },
        "required": ["variant_name", "overrides"],
    },
)


@register(define_variant_spec)
async def run_define_variant(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    variant_name = a.get("variant_name", "").strip()
    if not variant_name:
        return err_payload("variant_name is required", "BAD_ARGS")

    overrides = a.get("overrides", {})
    if not isinstance(overrides, dict):
        return err_payload("overrides must be an object", "BAD_ARGS")

    description = a.get("description", "")

    # Validate override values
    for key, ov in overrides.items():
        if not isinstance(ov, dict):
            return err_payload(
                f"override for '{key}' must be an object", "BAD_ARGS"
            )

    _VARIANT_STORE[variant_name] = {
        "_meta": {"description": description},
        **{k: v for k, v in overrides.items()},
    }

    dnp_count = sum(
        1 for k, v in overrides.items()
        if isinstance(v, dict) and (v.get("fitted") is False or str(v.get("fitted", "")).lower() == "false")
    )
    alt_count = len(overrides) - dnp_count

    return ok_payload({
        "variant_name": variant_name,
        "description": description,
        "override_count": len(overrides),
        "dnp_parts": dnp_count,
        "alternate_parts": alt_count,
        "message": (
            f"Variant '{variant_name}' defined: {dnp_count} DNP part(s), "
            f"{alt_count} alternate-value part(s). "
            "Use variant_bom or variant_fab to generate outputs."
        ),
    })


# ─── Tool: list_variants ──────────────────────────────────────────────────────

list_variants_spec = ToolSpec(
    name="list_variants",
    description=(
        "List all named assembly variants currently defined in the session. "
        "Shows each variant name, its description, DNP part count, and "
        "alternate-value override count. "
        "Use define_variant to create or update variants."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
)


@register(list_variants_spec)
async def run_list_variants(ctx: Any, args: bytes) -> str:
    if not _VARIANT_STORE:
        return ok_payload({
            "variants": [],
            "count": 0,
            "message": "No variants defined. Use define_variant to create one.",
        })

    variants_out = []
    for name, store in _VARIANT_STORE.items():
        meta = store.get("_meta", {})
        overrides = {k: v for k, v in store.items() if k != "_meta"}
        dnp_count = sum(
            1 for v in overrides.values()
            if isinstance(v, dict) and (v.get("fitted") is False or str(v.get("fitted", "")).lower() == "false")
        )
        alt_count = len(overrides) - dnp_count
        variants_out.append({
            "name": name,
            "description": meta.get("description", ""),
            "override_count": len(overrides),
            "dnp_parts": dnp_count,
            "alternate_parts": alt_count,
        })

    return ok_payload({
        "variants": variants_out,
        "count": len(variants_out),
        "message": f"{len(variants_out)} variant(s) defined.",
    })


# ─── Tool: variant_bom ────────────────────────────────────────────────────────

variant_bom_spec = ToolSpec(
    name="variant_bom",
    description=(
        "Generate a per-variant fab BOM CSV by applying a named variant's overrides "
        "onto the board's CircuitJSON and delegating to the existing fab BOM generator. "
        "DNP (do-not-populate) parts are excluded from the main BOM and listed in a "
        "separate DNP CSV (suffix -dnp.csv). "
        "Returns {bom_csv, dnp_csv, dnp_count, bom_row_count} — both CSVs as strings. "
        "Accepts either variant_name (to look up a previously defined_variant) or an "
        "inline overrides dict (same schema as define_variant.overrides)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "Parsed CircuitJSON array from the board file.",
                "items": {"type": "object"},
            },
            "variant_name": {
                "type": "string",
                "description": "Name of a previously defined variant (from define_variant).",
            },
            "overrides": {
                "type": "object",
                "description": (
                    "Inline override map (same schema as define_variant.overrides). "
                    "Ignored when variant_name is given."
                ),
                "additionalProperties": {"type": "object"},
            },
            "stem": {
                "type": "string",
                "description": "Base filename stem (default: 'board').",
            },
        },
        "required": ["circuit_json"],
    },
)


@register(variant_bom_spec)
async def run_variant_bom(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    # Resolve overrides
    overrides = _resolve_overrides(a)
    if overrides is None:
        vname = a.get("variant_name", "")
        return err_payload(f"variant '{vname}' not found; use define_variant first", "NOT_FOUND")

    stem = a.get("stem", "board") or "board"
    variant_label = a.get("variant_name", "") or "inline"

    try:
        patched, dnp_sources = _apply_variant(circuit_json, overrides)
        bom_files = export_fab_bom(patched, stem=stem)
    except Exception as e:
        return err_payload(f"variant BOM generation failed: {e}", "EXPORT_ERROR")

    bom_csv = bom_files.get(f"{stem}-bom.csv", "")
    dnp_csv_text = _dnp_csv(dnp_sources) if dnp_sources else ""

    bom_rows = max(0, len(bom_csv.strip().splitlines()) - 1)  # exclude header

    return ok_payload({
        "variant_name": variant_label,
        "bom_csv": bom_csv,
        "dnp_csv": dnp_csv_text,
        "bom_row_count": bom_rows,
        "dnp_count": len(dnp_sources),
        "message": (
            f"Variant '{variant_label}' BOM: {bom_rows} line-item(s) fitted, "
            f"{len(dnp_sources)} DNP part(s) listed in dnp_csv. "
            "Use variant_fab for the complete fab package."
        ),
    })


# ─── Tool: variant_fab ────────────────────────────────────────────────────────

variant_fab_spec = ToolSpec(
    name="variant_fab",
    description=(
        "Generate a complete per-variant fab package (Gerbers + drill + P&P + BOM + "
        "IPC-2581 + DNP list) by applying a named variant's overrides and delegating "
        "to the existing fab generators. "
        "DNP parts are excluded from P&P and from the main fab BOM; a separate "
        "DNP CSV (<stem>-<variant>-dnp.csv) is included in the zip. "
        "Returns a base64-encoded zip archive. "
        "Accepts variant_name (previously defined) or an inline overrides dict."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": "Parsed CircuitJSON array from the board file.",
                "items": {"type": "object"},
            },
            "variant_name": {
                "type": "string",
                "description": "Name of a previously defined variant.",
            },
            "overrides": {
                "type": "object",
                "description": "Inline override map. Ignored when variant_name is given.",
                "additionalProperties": {"type": "object"},
            },
            "stem": {
                "type": "string",
                "description": "Base filename stem (default: 'board').",
            },
        },
        "required": ["circuit_json"],
    },
)


@register(variant_fab_spec)
async def run_variant_fab(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    overrides = _resolve_overrides(a)
    if overrides is None:
        vname = a.get("variant_name", "")
        return err_payload(f"variant '{vname}' not found; use define_variant first", "NOT_FOUND")

    stem = a.get("stem", "board") or "board"
    variant_label = a.get("variant_name", "") or "inline"

    try:
        patched, dnp_sources = _apply_variant(circuit_json, overrides)

        gerber_files = export_gerber(patched, stem=stem)
        drill_files = export_excellon(patched, stem=stem)
        pnp_files = export_pnp(patched, stem=stem)
        bom_files = export_fab_bom(patched, stem=stem)
        ipc_files = export_ipc2581(patched, stem=stem)
    except Exception as e:
        return err_payload(f"variant fab package failed: {e}", "EXPORT_ERROR")

    all_files: dict[str, str] = {}
    all_files.update(gerber_files)
    all_files.update(drill_files)
    all_files.update(pnp_files)
    all_files.update(bom_files)
    all_files.update(ipc_files)

    # Add DNP list
    dnp_key = f"{stem}-{variant_label}-dnp.csv"
    dnp_csv_text = _dnp_csv(dnp_sources) if dnp_sources else "Refdes,Value,Footprint,MPN,Note\n"
    all_files[dnp_key] = dnp_csv_text

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, content in sorted(all_files.items()):
            zf.writestr(fname, content.encode("utf-8"))

    zip_bytes = buf.getvalue()
    zip_b64 = base64.b64encode(zip_bytes).decode()
    zip_filename = f"{stem}-{variant_label}-fab.zip"

    manifest = sorted(all_files.keys())

    return ok_payload({
        "variant_name": variant_label,
        "zip_filename": zip_filename,
        "zip_b64": zip_b64,
        "zip_size_bytes": len(zip_bytes),
        "manifest": manifest,
        "dnp_count": len(dnp_sources),
        "dnp_parts": [s.get("name", s.get("refdes", "")) for s in dnp_sources],
        "message": (
            f"Variant '{variant_label}' fab package: {zip_filename} ({len(zip_bytes):,} bytes). "
            f"{len(dnp_sources)} DNP part(s) excluded from P&P and BOM. "
            f"DNP list in {dnp_key}."
        ),
    })


# ─── Internal helper ──────────────────────────────────────────────────────────

def _resolve_overrides(a: dict) -> dict | None:
    """Resolve override dict from args: variant_name lookup or inline.

    Resolution order:
    1. If variant_name is given AND exists in store → use stored overrides.
    2. If variant_name is given AND inline overrides key is present in args
       (even as {}) → use the inline overrides (allows ad-hoc named runs
       without define_variant first).
    3. If variant_name is given with no overrides key and not in store → NOT_FOUND.
    4. If no variant_name → use inline overrides (may be empty dict).
    """
    variant_name = a.get("variant_name", "")
    has_inline = "overrides" in a
    inline = a.get("overrides") or {}
    if variant_name:
        store = _VARIANT_STORE.get(variant_name)
        if store is not None:
            return {k: v for k, v in store.items() if k != "_meta"}
        # Fall back to inline overrides when the caller supplied the key
        if has_inline:
            return inline
        # Named variant not found and no inline fallback → error
        return None
    return inline
