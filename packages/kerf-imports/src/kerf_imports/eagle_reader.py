"""
eagle_reader.py — Autodesk Eagle schematic (.sch) and board (.brd) reader.

Parses Eagle XML files (v6+, EAGLE XML format used by Eagle 6-9 and
the Autodesk / Fusion 360 Eagle v10 dialect).  Pure Python — stdlib
xml.etree only; no third-party deps.

Supported constructs
--------------------
Schematic (.sch):
  - <library> → library name + devicesets/devices
  - <parts>/<part>  → ref, value, library, deviceset, device, package
  - <nets>/<net>/<segment>/<pinref> → net name + pin references

Board (.brd):
  - <elements>/<element> → ref, value, library, package, x, y, rot, layer
  - <signals>/<signal>/<wire>  → signal name + wire segments (x1,y1,x2,y2,layer)
  - <signals>/<signal>/<via>   → via coords, drill, layer range
  - <signals>/<signal>/<contactref> → component-pin → net mapping

Output model
------------
  {
    "ok": True,
    "source": "sch" | "brd" | "unknown",
    "parts": [
      {
        "ref":       str,   # e.g. "R1"
        "value":     str,   # e.g. "10k"
        "library":   str,
        "deviceset": str,
        "device":    str,
        "package":   str,
      },
      ...
    ],
    "nets": [
      {
        "name": str,
        "pins": ["R1.1", "C2.2", ...],
      },
      ...
    ],
    "signals": [
      {
        "name": str,
        "wires": [
          {"x1": float, "y1": float, "x2": float, "y2": float, "layer": str},
          ...
        ],
        "vias": [
          {"x": float, "y": float, "drill": float, "extent": str},
          ...
        ],
        "contactrefs": [
          {"element": str, "pad": str},
          ...
        ],
      },
      ...
    ],
    "footprints": [
      {
        "ref":     str,
        "value":   str,
        "library": str,
        "package": str,
        "x":       float,
        "y":       float,
        "rot":     float,
        "layer":   str,
      },
      ...
    ],
    "warnings": [str, ...],
  }

On error:
  {"ok": False, "reason": str}

Never raises.

LLM tool ``import_eagle`` registered via @register; gated on "imports.eagle".
"""

from __future__ import annotations

import json
import logging
import uuid
import xml.etree.ElementTree as ET
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# XML helpers (namespace-aware)
# ---------------------------------------------------------------------------

def _strip_ns(tag: str) -> str:
    """Strip namespace URI from an XML tag, returning the local name."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find(elem: ET.Element, *local_names: str) -> Optional[ET.Element]:
    """Depth-first search for the first descendant matching any local name."""
    for child in elem:
        local = _strip_ns(child.tag)
        if local in local_names:
            return child
        found = _find(child, *local_names)
        if found is not None:
            return found
    return None


def _findall_immediate(elem: ET.Element, local_name: str) -> list[ET.Element]:
    """Return immediate children whose local name matches."""
    return [c for c in elem if _strip_ns(c.tag) == local_name]


def _findall_deep(elem: ET.Element, local_name: str) -> list[ET.Element]:
    """Return all descendants at any depth whose local name matches."""
    out: list[ET.Element] = []
    for child in elem:
        if _strip_ns(child.tag) == local_name:
            out.append(child)
        out.extend(_findall_deep(child, local_name))
    return out


def _attr(elem: ET.Element, *names: str, default: str = "") -> str:
    """Return the first matching attribute from *names* (namespace-stripped)."""
    # Try exact attribute match first
    for name in names:
        val = elem.get(name)
        if val is not None:
            return val
    # Namespace-stripped fallback
    for attr_key, attr_val in elem.attrib.items():
        local = _strip_ns(attr_key)
        if local in names:
            return attr_val
    return default


def _float_attr(elem: ET.Element, *names: str, default: float = 0.0) -> float:
    raw = _attr(elem, *names, default="")
    if not raw:
        return default
    try:
        # Eagle rotation values look like "R90" or "MR90" — strip leading letters
        raw_stripped = raw.lstrip("MR")
        return float(raw_stripped) if raw_stripped else default
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Schematic parsing
# ---------------------------------------------------------------------------

def _parse_parts(root: ET.Element) -> tuple[list[dict], list[str]]:
    """Parse <parts>/<part> elements from the schematic root."""
    parts: list[dict] = []
    warns: list[str] = []

    # Eagle schema: drawing > schematic > parts > part
    # Or at top level in some variants
    for part_el in _findall_deep(root, "part"):
        try:
            ref = _attr(part_el, "name")
            value = _attr(part_el, "value")
            library = _attr(part_el, "library")
            deviceset = _attr(part_el, "deviceset")
            device = _attr(part_el, "device")
            package = _attr(part_el, "package")

            # If package not on <part>, look it up in the library
            if not package:
                # Try attribute "technology" or "variant"
                package = _attr(part_el, "technology") or _attr(part_el, "variant", default="")

            parts.append({
                "ref": ref,
                "value": value,
                "library": library,
                "deviceset": deviceset,
                "device": device,
                "package": package,
            })
        except Exception as exc:
            warns.append(f"part parse error: {exc}")

    return parts, warns


def _parse_nets(root: ET.Element) -> tuple[list[dict], list[str]]:
    """Parse <nets>/<net>/<segment>/<pinref> from schematic."""
    nets: list[dict] = []
    warns: list[str] = []

    for net_el in _findall_deep(root, "net"):
        try:
            net_name = _attr(net_el, "name")
            pins: list[str] = []
            for pinref in _findall_deep(net_el, "pinref"):
                part = _attr(pinref, "part")
                pin = _attr(pinref, "pin")
                if part:
                    pins.append(f"{part}.{pin}" if pin else part)
            nets.append({"name": net_name, "pins": pins})
        except Exception as exc:
            warns.append(f"net parse error: {exc}")

    return nets, warns


# ---------------------------------------------------------------------------
# Board parsing
# ---------------------------------------------------------------------------

def _parse_elements(root: ET.Element) -> tuple[list[dict], list[str]]:
    """Parse <elements>/<element> board footprints."""
    footprints: list[dict] = []
    warns: list[str] = []

    for elem_el in _findall_deep(root, "element"):
        try:
            ref = _attr(elem_el, "name")
            value = _attr(elem_el, "value")
            library = _attr(elem_el, "library")
            package = _attr(elem_el, "package")
            x = _float_attr(elem_el, "x")
            y = _float_attr(elem_el, "y")
            rot_raw = _attr(elem_el, "rot", default="R0")
            # Parse rotation: "R90" → 90.0, "MR90" → 90.0 (mirrored)
            mirrored = rot_raw.startswith("M")
            rot_str = rot_raw.lstrip("MR")
            try:
                rot = float(rot_str) if rot_str else 0.0
            except ValueError:
                rot = 0.0
            layer = "Top" if not mirrored else "Bottom"

            footprints.append({
                "ref": ref,
                "value": value,
                "library": library,
                "package": package,
                "x": x,
                "y": y,
                "rot": rot,
                "layer": layer,
            })
        except Exception as exc:
            warns.append(f"element parse error: {exc}")

    return footprints, warns


def _parse_signals(root: ET.Element) -> tuple[list[dict], list[str]]:
    """Parse <signals>/<signal> board routing."""
    signals: list[dict] = []
    warns: list[str] = []

    for sig_el in _findall_deep(root, "signal"):
        try:
            sig_name = _attr(sig_el, "name")
            wires: list[dict] = []
            vias: list[dict] = []
            contactrefs: list[dict] = []

            for wire_el in _findall_immediate(sig_el, "wire"):
                wires.append({
                    "x1": _float_attr(wire_el, "x1"),
                    "y1": _float_attr(wire_el, "y1"),
                    "x2": _float_attr(wire_el, "x2"),
                    "y2": _float_attr(wire_el, "y2"),
                    "layer": _attr(wire_el, "layer"),
                })

            for via_el in _findall_immediate(sig_el, "via"):
                vias.append({
                    "x": _float_attr(via_el, "x"),
                    "y": _float_attr(via_el, "y"),
                    "drill": _float_attr(via_el, "drill"),
                    "extent": _attr(via_el, "extent"),
                })

            for cref_el in _findall_immediate(sig_el, "contactref"):
                contactrefs.append({
                    "element": _attr(cref_el, "element"),
                    "pad": _attr(cref_el, "pad"),
                })

            signals.append({
                "name": sig_name,
                "wires": wires,
                "vias": vias,
                "contactrefs": contactrefs,
            })
        except Exception as exc:
            warns.append(f"signal parse error: {exc}")

    return signals, warns


# ---------------------------------------------------------------------------
# Source detection
# ---------------------------------------------------------------------------

def _detect_source(root: ET.Element) -> str:
    """
    Detect whether this is a schematic (.sch) or board (.brd) XML file.

    Eagle XML uses <drawing><schematic> for .sch and <drawing><board> for .brd.
    """
    if _find(root, "schematic") is not None:
        return "sch"
    if _find(root, "board") is not None:
        return "brd"
    return "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_eagle(data: str | bytes) -> dict:
    """
    Parse an Eagle XML schematic or board file.

    Accepts a UTF-8 string or bytes.  Returns the Kerf netlist + footprint dict
    format (see module docstring).  Never raises — errors surface as
    {"ok": False, "reason": str}.
    """
    warns: list[str] = []

    try:
        if isinstance(data, bytes):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("latin-1", errors="replace")
        else:
            text = data

        if not text or not text.strip():
            return {"ok": False, "reason": "empty input"}

        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            return {"ok": False, "reason": f"XML parse error: {exc}"}

        # Validate root is an EAGLE document
        root_local = _strip_ns(root.tag)
        if root_local not in ("eagle", "EAGLE"):
            # Some dialects omit the outer <eagle> wrapper or rename it
            warns.append(
                f"root element is <{root_local}>, expected <eagle>; "
                "attempting parse anyway"
            )

        source = _detect_source(root)

        parts, part_warns = _parse_parts(root)
        warns.extend(part_warns)

        nets, net_warns = _parse_nets(root)
        warns.extend(net_warns)

        footprints, fp_warns = _parse_elements(root)
        warns.extend(fp_warns)

        signals, sig_warns = _parse_signals(root)
        warns.extend(sig_warns)

        return {
            "ok": True,
            "source": source,
            "parts": parts,
            "nets": nets,
            "signals": signals,
            "footprints": footprints,
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

    _import_eagle_spec = ToolSpec(
        name="import_eagle",
        description=(
            "Import an Autodesk Eagle schematic (.sch) or board (.brd) XML file "
            "into the current Kerf project. "
            "Accepts a blob_id or storage_key pointing to the uploaded Eagle XML file. "
            "Parses parts/nets from schematics and elements/signals/footprints from "
            "board files.  Returns a structured netlist + footprint model. "
            "Gate: imports.eagle capability."
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
                    "description": "Blob ID or storage key for the Eagle .sch/.brd file.",
                },
                "import_folder": {
                    "type": "string",
                    "description": (
                        "Path in the project tree for the imported file. "
                        "Defaults to /eagle_import."
                    ),
                },
            },
            "required": ["project_id", "file_blob_id_or_storage_key"],
        },
    )

    @register(_import_eagle_spec, write=True)
    async def run_import_eagle(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        project_id = a.get("project_id", "").strip()
        blob_ref = a.get("file_blob_id_or_storage_key", "").strip()
        import_folder = a.get("import_folder", "/eagle_import").strip()

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

        model = parse_eagle(blob_bytes)
        if not model.get("ok"):
            return err_payload(model.get("reason", "Eagle parse failed"), "PARSE_ERROR")

        try:
            _pid = uuid.UUID(project_id)
        except Exception:
            return err_payload("project_id must be a valid UUID", "BAD_ARGS")

        fid = uuid.uuid4()
        content = json.dumps({
            "version": 1,
            "source": model["source"],
            "parts": model["parts"],
            "nets": model["nets"],
            "signals": model["signals"],
            "footprints": model["footprints"],
        })

        try:
            ctx.pool.execute(
                "insert into files (id, project_id, name, kind, content, "
                "created_at, updated_at) values ($1, $2, $3, $4, $5, now(), now())",
                fid, _pid,
                f"{import_folder}/eagle_netlist.json",
                "eagle_netlist",
                content,
            )
        except Exception as exc:
            model["warnings"].append(f"failed to persist Eagle file: {exc}")

        return ok_payload({
            "ok": True,
            "file_id": str(fid),
            "source": model["source"],
            "part_count": len(model["parts"]),
            "net_count": len(model["nets"]),
            "signal_count": len(model["signals"]),
            "footprint_count": len(model["footprints"]),
            "warnings": model["warnings"],
        })

    TOOLS = []  # tools registered via @register decorator; list kept for symmetry

except ImportError:
    pass
