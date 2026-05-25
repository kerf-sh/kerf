"""
geda_reader.py — gEDA gschem schematic and PCB layout reader.

Parses gEDA's native text formats:

  gschem (.sch) — the gEDA schematic capture tool format.
    Objects are written as single-character type codes followed by
    attribute lines.  This reader handles:
      C — component instance (x, y, basename, refdes, value, footprint)
      N — net segment (x1, y1, x2, y2, colour)
      { } — attribute blocks attached to the preceding object
      T — text/attribute objects (for standalone attributes)

  PCB (.pcb) — the gEDA PCB layout tool format.
    S-expression-like format using parenthesised element declarations.
    This reader handles:
      Element[ ... ] — component placement (ref, description, x, y)
      Net( ... )     — connectivity (net name + pin refs)
      Line[ ... ]    — copper wire segments on a layer
      Via[ ... ]     — through-hole vias

Pure Python — stdlib only; no third-party deps.

Output model
------------
  {
    "ok": True,
    "source": "sch" | "pcb" | "unknown",
    "parts": [
      {
        "ref":       str,
        "value":     str,
        "footprint": str,
        "basename":  str,   # component file basename (.sym)
        "x":         float,
        "y":         float,
      },
      ...
    ],
    "nets": [
      {
        "name": str,
        "pins": ["R1.1", "U2.A3", ...],   # gschem nets derive from net= attrs
      },
      ...
    ],
    "signals": [
      {
        "name":  str,
        "wires": [
          {"x1": float, "y1": float, "x2": float, "y2": float, "layer": str},
          ...
        ],
        "vias": [
          {"x": float, "y": float, "drill": float},
          ...
        ],
      },
      ...
    ],
    "footprints": [
      {
        "ref":         str,
        "description": str,
        "x":           float,
        "y":           float,
        "layer":       str,   # "Top" / "Bottom"
      },
      ...
    ],
    "warnings": [str, ...],
  }

On error:
  {"ok": False, "reason": str}

Never raises.

LLM tool ``import_geda`` registered via @register; gated on "imports.geda".
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# gschem parser
# ---------------------------------------------------------------------------

# Attribute line regex: key=value (leading/trailing whitespace stripped)
_ATTR_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

# Component line: C x y selectable angle mirror basename
_COMP_RE = re.compile(
    r"^C\s+(-?\d+)\s+(-?\d+)\s+\d+\s+\d+\s+\d+\s+(\S+)$"
)

# Net segment line: N x1 y1 x2 y2 colour
_NET_SEG_RE = re.compile(
    r"^N\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+\d+"
)


def _parse_gschem(lines: list[str]) -> tuple[list[dict], list[dict], list[str]]:
    """
    Parse gschem format lines.

    Returns (parts, nets, warnings).

    Strategy:
    - Walk lines.  When we see a 'C' line, read subsequent attribute block
      { ... } to collect refdes=, value=, footprint=, net= attributes.
    - Build net dict from net= attributes: "net=NET_NAME:1" means pin 1 of
      this component connects to NET_NAME.  We reconstruct net connectivity
      as {net_name: [ref.pin, ...]} across the whole schematic.
    """
    parts: list[dict] = []
    warns: list[str] = []
    net_pins: dict[str, list[str]] = {}  # net_name → [ref.pin, ...]

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        i += 1

        # Component object
        m = _COMP_RE.match(line)
        if m:
            x = float(m.group(1))
            y = float(m.group(2))
            basename = m.group(3)

            # Collect attribute block if next non-blank line is "{"
            attrs: dict[str, str] = {}
            if i < len(lines) and lines[i].strip() == "{":
                i += 1  # skip "{"
                while i < len(lines):
                    attr_line = lines[i].strip()
                    i += 1
                    if attr_line == "}":
                        break
                    # Text object inside attribute block — skip header,
                    # read the actual attribute on the next line
                    if attr_line.startswith("T "):
                        if i < len(lines):
                            inner = lines[i].strip()
                            i += 1
                            am = _ATTR_RE.match(inner)
                            if am:
                                attrs[am.group(1)] = am.group(2)
                    else:
                        am = _ATTR_RE.match(attr_line)
                        if am:
                            attrs[am.group(1)] = am.group(2)

            ref = attrs.get("refdes", "")
            value = attrs.get("value", "")
            footprint = attrs.get("footprint", "")

            # net= attributes: format "NET_NAME:pin_number[,NET_NAME2:pin2,...]"
            net_raw = attrs.get("net", "")
            if net_raw and ref:
                for net_entry in net_raw.split(","):
                    net_entry = net_entry.strip()
                    if ":" in net_entry:
                        net_name, pin_num = net_entry.split(":", 1)
                        net_name = net_name.strip()
                        pin_num = pin_num.strip()
                        if net_name:
                            net_pins.setdefault(net_name, []).append(
                                f"{ref}.{pin_num}" if pin_num else ref
                            )

            parts.append({
                "ref": ref,
                "value": value,
                "footprint": footprint,
                "basename": basename,
                "x": x,
                "y": y,
            })
            continue

        # Top-level text/attribute object (T line — two-line format)
        if line.startswith("T "):
            if i < len(lines):
                attr_line = lines[i].strip()
                i += 1
                # Ignore standalone text — only component attrs matter

    # Build nets list
    nets = [{"name": name, "pins": pins} for name, pins in net_pins.items()]

    return parts, nets, warns


# ---------------------------------------------------------------------------
# PCB parser helpers
# ---------------------------------------------------------------------------

# Match Element declarations (both old-style [] and new-style ())
_ELEMENT_RE = re.compile(
    r'Element[(\[]\s*'
    r'"([^"]*)"\s*'     # flags (may be empty)
    r'"([^"]*)"\s*'     # description / footprint
    r'"([^"]*)"\s*'     # ref designator
    r'"([^"]*)"\s*'     # value
    r'(-?\d+(?:\.\d+)?)\s+'   # x
    r'(-?\d+(?:\.\d+)?)\s+'   # y
    r'(-?\d+(?:\.\d+)?)\s+'   # text_x
    r'(-?\d+(?:\.\d+)?)\s+'   # text_y
    r'(\d+)\s+'         # direction
    r'(\d+)',           # scale
)

# Net( "name" "element.pin" ) inside a Netlist block
_NETLIST_NET_RE = re.compile(r'Net\s*\(\s*"([^"]*)"\s*"([^"]*)"\s*\)')

# Line segments: Line[ x1 y1 x2 y2 thickness clearance solder_mask flags ]
_LINE_RE = re.compile(
    r'Line\s*[(\[]\s*'
    r'(-?\d+(?:\.\d+)?)\s+'
    r'(-?\d+(?:\.\d+)?)\s+'
    r'(-?\d+(?:\.\d+)?)\s+'
    r'(-?\d+(?:\.\d+)?)'
)

# Via: Via[ x y thickness clearance mask drill name flags ]
_VIA_RE = re.compile(
    r'Via\s*[(\[]\s*'
    r'(-?\d+(?:\.\d+)?)\s+'
    r'(-?\d+(?:\.\d+)?)\s+'
    r'\S+\s+\S+\s+\S+\s+'
    r'(-?\d+(?:\.\d+)?)'  # drill
)


def _parse_pcb(text: str) -> tuple[list[dict], list[dict], list[dict], list[dict], list[str]]:
    """
    Parse gEDA PCB format text.

    Returns (parts, nets, signals, footprints, warnings).
    """
    parts: list[dict] = []
    nets: list[dict] = []
    signals: list[dict] = []
    footprints: list[dict] = []
    warns: list[str] = []

    # ── Elements ──────────────────────────────────────────────────────────
    for m in _ELEMENT_RE.finditer(text):
        try:
            desc = m.group(2)
            ref = m.group(3)
            value = m.group(4)
            x = float(m.group(5))
            y = float(m.group(6))

            entry = {
                "ref": ref,
                "description": desc,
                "value": value,
                "x": x,
                "y": y,
                "layer": "Top",   # PCB format doesn't always encode side here
            }
            parts.append({
                "ref": ref,
                "value": value,
                "footprint": desc,
                "basename": desc,
                "x": x,
                "y": y,
            })
            footprints.append(entry)
        except Exception as exc:
            warns.append(f"PCB element parse error: {exc}")

    # ── Netlist (Net declarations) ─────────────────────────────────────────
    # Group by net name.
    net_map: dict[str, list[str]] = {}
    for m in _NETLIST_NET_RE.finditer(text):
        net_name = m.group(1)
        pin_ref = m.group(2)  # already in "ELEMENT.PAD" form
        net_map.setdefault(net_name, []).append(pin_ref)
    nets = [{"name": name, "pins": pins} for name, pins in net_map.items()]

    # ── Routing (Line segments) ────────────────────────────────────────────
    # All lines are folded into a single unnamed signal for now (PCB format
    # doesn't directly bind wires to nets without full layer-level analysis).
    wire_list: list[dict] = []
    for m in _LINE_RE.finditer(text):
        try:
            wire_list.append({
                "x1": float(m.group(1)),
                "y1": float(m.group(2)),
                "x2": float(m.group(3)),
                "y2": float(m.group(4)),
                "layer": "",
            })
        except Exception:
            pass

    via_list: list[dict] = []
    for m in _VIA_RE.finditer(text):
        try:
            via_list.append({
                "x": float(m.group(1)),
                "y": float(m.group(2)),
                "drill": float(m.group(3)),
            })
        except Exception:
            pass

    if wire_list or via_list:
        signals.append({
            "name": "",
            "wires": wire_list,
            "vias": via_list,
        })

    return parts, nets, signals, footprints, warns


# ---------------------------------------------------------------------------
# Source detection
# ---------------------------------------------------------------------------

def _detect_geda_source(text: str) -> str:
    """
    Detect whether text is a gschem (.sch) or PCB (.pcb) file.

    gschem files start with "v " (version line).
    PCB files contain "PCBName(" or "Element[" or "Element(" constructs.
    """
    stripped = text.lstrip()
    if stripped.startswith("v "):
        return "sch"
    if re.search(r"\bElement\s*[(\[]", text):
        return "pcb"
    return "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_geda(data: str | bytes) -> dict:
    """
    Parse a gEDA gschem schematic or PCB layout file.

    Accepts a UTF-8 string or bytes.  Returns the Kerf netlist + footprint dict
    (see module docstring).  Never raises — errors surface as
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

        source = _detect_geda_source(text)

        if source == "sch":
            lines = text.splitlines()
            parts, nets, parse_warns = _parse_gschem(lines)
            warns.extend(parse_warns)
            signals: list[dict] = []
            footprints: list[dict] = []

        elif source == "pcb":
            parts, nets, signals, footprints, parse_warns = _parse_pcb(text)
            warns.extend(parse_warns)

        else:
            # Try both parsers as best-effort
            warns.append("could not determine gEDA file type; attempting schematic parse")
            lines = text.splitlines()
            parts, nets, parse_warns = _parse_gschem(lines)
            warns.extend(parse_warns)
            signals = []
            footprints = []

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

    _import_geda_spec = ToolSpec(
        name="import_geda",
        description=(
            "Import a gEDA gschem schematic (.sch) or PCB layout (.pcb) file "
            "into the current Kerf project. "
            "Accepts a blob_id or storage_key pointing to the uploaded gEDA file. "
            "Parses component instances, net connectivity, and board routing into "
            "a structured netlist + footprint model. "
            "Gate: imports.geda capability."
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
                    "description": "Blob ID or storage key for the gEDA .sch/.pcb file.",
                },
                "import_folder": {
                    "type": "string",
                    "description": (
                        "Path in the project tree for the imported file. "
                        "Defaults to /geda_import."
                    ),
                },
            },
            "required": ["project_id", "file_blob_id_or_storage_key"],
        },
    )

    @register(_import_geda_spec, write=True)
    async def run_import_geda(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        project_id = a.get("project_id", "").strip()
        blob_ref = a.get("file_blob_id_or_storage_key", "").strip()
        import_folder = a.get("import_folder", "/geda_import").strip()

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

        model = parse_geda(blob_bytes)
        if not model.get("ok"):
            return err_payload(model.get("reason", "gEDA parse failed"), "PARSE_ERROR")

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
                f"{import_folder}/geda_netlist.json",
                "geda_netlist",
                content,
            )
        except Exception as exc:
            model["warnings"].append(f"failed to persist gEDA file: {exc}")

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

    TOOLS = [(_import_geda_spec.name, _import_geda_spec, run_import_geda)]

except ImportError:
    pass
