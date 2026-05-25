"""
allegro_reader.py — Cadence Allegro PCB design reader.

Supports two Allegro export formats:

1. IPC-2581 XML (the preferred, documented open standard).
   Allegro's ``File → Export → IPC-2581`` produces ``*.xml`` / ``*.cvg``
   conforming to IPC-2581B.  This reader parses the main structural
   sections needed for ECAD import:
     <Bom>         → components + part numbers
     <LogicalNet>  → net names + pin associations (ref.pin)
     <LayerFeature> → routed wire segments per layer
     <Component>   → physical placement (x, y, rotation, layer)

2. Allegro ASCII board report (``*.brd`` ASCII variant, ``*.asc``).
   Allegro can export a text netlist/placement report.  This reader
   handles the common sections:
     $PACKAGES   → part type / footprint per reference
     $NETS       → net name + pin list (tab or space delimited)
     $LOCATIONS  → x, y, rot, layer per reference

Both are tried in order; the first that succeeds wins.
Pure Python — stdlib xml.etree + re; no third-party deps.

Output model
------------
  {
    "ok": True,
    "format": "ipc2581" | "allegro_asc" | "unknown",
    "parts": [
      {
        "ref":       str,
        "part_type": str,
        "value":     str,
        "x":         float | None,
        "y":         float | None,
        "rot":       float | None,
        "layer":     str,
      },
      ...
    ],
    "nets": [
      {
        "name": str,
        "pins": ["R1.1", "U2.A3", ...],
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
      },
      ...
    ],
    "footprints": [
      {
        "ref":       str,
        "part_type": str,
        "x":         float | None,
        "y":         float | None,
        "rot":       float | None,
        "layer":     str,
      },
      ...
    ],
    "warnings": [str, ...],
  }

On error:
  {"ok": False, "reason": str}

Never raises.

LLM tool ``import_allegro`` registered via @register; gated on "imports.allegro".
"""

from __future__ import annotations

import json
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IPC-2581 XML parser
# ---------------------------------------------------------------------------

# IPC-2581 namespace URI (2581B)
_IPC_NS = "http://webstds.ipc.org/2581"


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find_ipc(elem: ET.Element, *local_names: str) -> Optional[ET.Element]:
    for child in elem:
        if _strip_ns(child.tag) in local_names:
            return child
        found = _find_ipc(child, *local_names)
        if found is not None:
            return found
    return None


def _findall_ipc(elem: ET.Element, local_name: str) -> list[ET.Element]:
    return [c for c in elem if _strip_ns(c.tag) == local_name]


def _findall_deep_ipc(elem: ET.Element, local_name: str) -> list[ET.Element]:
    out: list[ET.Element] = []
    for child in elem:
        if _strip_ns(child.tag) == local_name:
            out.append(child)
        out.extend(_findall_deep_ipc(child, local_name))
    return out


def _attr(elem: ET.Element, *names: str, default: str = "") -> str:
    for name in names:
        val = elem.get(name)
        if val is not None:
            return val
    for k, v in elem.attrib.items():
        if _strip_ns(k) in names:
            return v
    return default


def _float_attr(elem: ET.Element, *names: str, default: float = 0.0) -> float:
    raw = _attr(elem, *names, default="")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _parse_ipc2581(root: ET.Element) -> tuple[list, list, list, list, list[str]]:
    """
    Parse an IPC-2581 XML document.

    Returns (parts, nets, signals, footprints, warnings).
    """
    parts: list[dict] = []
    nets: list[dict] = []
    signals: list[dict] = []
    footprints: list[dict] = []
    warns: list[str] = []

    # ── BOM / Component definitions ────────────────────────────────────────
    # IPC-2581 <Bom> → <BomItem refDes="R1" partName="...">
    for bom_item in _findall_deep_ipc(root, "BomItem"):
        ref = _attr(bom_item, "refDes", "RefDes", default="")
        part_type = _attr(bom_item, "partName", "PartName", default="")
        value = _attr(bom_item, "description", "Description", default="")

        if not ref:
            continue

        parts.append({
            "ref": ref,
            "part_type": part_type,
            "value": value,
            "x": None,
            "y": None,
            "rot": None,
            "layer": "",
        })

    # Build a ref→index map for updating with placement data
    ref_map: dict[str, int] = {p["ref"]: i for i, p in enumerate(parts)}

    # ── Logical nets ───────────────────────────────────────────────────────
    # <LogicalNet name="GND"> <PinRef componentRef="R1" pin="1"/> ...
    for net_el in _findall_deep_ipc(root, "LogicalNet"):
        net_name = _attr(net_el, "name", default="")
        pins: list[str] = []
        for pinref in _findall_deep_ipc(net_el, "PinRef"):
            comp_ref = _attr(pinref, "componentRef", "component", default="")
            pin = _attr(pinref, "pin", default="")
            if comp_ref:
                pins.append(f"{comp_ref}.{pin}" if pin else comp_ref)
        nets.append({"name": net_name, "pins": pins})

    # ── Component placements ───────────────────────────────────────────────
    # <Component refDes="R1" part="..."> <Xform rotation="0" x="10.5" y="5.2"/>
    for comp_el in _findall_deep_ipc(root, "Component"):
        ref = _attr(comp_el, "refDes", "RefDes", default="")
        if not ref:
            continue
        part_type = _attr(comp_el, "part", "partRef", default="")
        layer_raw = _attr(comp_el, "layerRef", "layer", default="")
        layer = "Top" if layer_raw.upper() in ("TOP", "F.CU", "1") else (
            "Bottom" if layer_raw.upper() in ("BOTTOM", "B.CU", "2") else layer_raw
        )

        xform = _find_ipc(comp_el, "Xform")
        x = _float_attr(xform, "x", "X") if xform is not None else 0.0
        y = _float_attr(xform, "y", "Y") if xform is not None else 0.0
        rot = _float_attr(xform, "rotation", "Rotation") if xform is not None else 0.0

        fp_entry = {
            "ref": ref,
            "part_type": part_type,
            "x": x,
            "y": y,
            "rot": rot,
            "layer": layer,
        }
        footprints.append(fp_entry)

        # Update parts list if we have a matching entry
        if ref in ref_map:
            p = parts[ref_map[ref]]
            p["x"] = x
            p["y"] = y
            p["rot"] = rot
            p["layer"] = layer
        else:
            parts.append({
                "ref": ref,
                "part_type": part_type,
                "value": "",
                "x": x,
                "y": y,
                "rot": rot,
                "layer": layer,
            })

    # ── Layer routing features ─────────────────────────────────────────────
    # <LayerFeature layerRef="TOP"> <Set> <Line> <Pt x y/><Pt x y/>
    for layer_feat in _findall_deep_ipc(root, "LayerFeature"):
        layer_ref = _attr(layer_feat, "layerRef", default="")
        wire_list: list[dict] = []

        for line_el in _findall_deep_ipc(layer_feat, "Line"):
            pts = _findall_deep_ipc(line_el, "Pt")
            for k in range(len(pts) - 1):
                wire_list.append({
                    "x1": _float_attr(pts[k], "x"),
                    "y1": _float_attr(pts[k], "y"),
                    "x2": _float_attr(pts[k + 1], "x"),
                    "y2": _float_attr(pts[k + 1], "y"),
                    "layer": layer_ref,
                })

        if wire_list:
            signals.append({"name": layer_ref, "wires": wire_list})

    return parts, nets, signals, footprints, warns


def _try_parse_ipc2581(text: str) -> Optional[dict]:
    """
    Attempt IPC-2581 parse.  Returns result dict or None if not recognised.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None

    root_local = _strip_ns(root.tag)
    if root_local not in ("IPC-2581", "IPC_2581", "Content", "Bom"):
        # Check if any child looks like IPC-2581
        if not any(_strip_ns(c.tag) in ("Bom", "LogicalNet", "Component") for c in root):
            return None

    parts, nets, signals, footprints, warns = _parse_ipc2581(root)
    return {
        "ok": True,
        "format": "ipc2581",
        "parts": parts,
        "nets": nets,
        "signals": signals,
        "footprints": footprints,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# Allegro ASCII report parser
# ---------------------------------------------------------------------------

_SECTION_HDR_RE = re.compile(r"^\$([A-Z_]+)\s*$", re.MULTILINE)


def _iter_allegro_sections(text: str):
    """Yield (section_name, lines) from an Allegro ASCII report."""
    current_kw: Optional[str] = None
    current_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        m = _SECTION_HDR_RE.match(line)
        if m:
            if current_kw is not None:
                yield current_kw, current_lines
            current_kw = m.group(1)
            current_lines = []
        else:
            if current_kw is not None:
                current_lines.append(line)

    if current_kw is not None:
        yield current_kw, current_lines


def _parse_allegro_packages(lines: list[str]) -> tuple[list[dict], list[dict]]:
    """
    Parse $PACKAGES section.

    Format: REF  PART_TYPE  [additional columns...]
    """
    parts: list[dict] = []
    footprints: list[dict] = []
    for line in lines:
        tokens = line.split()
        if len(tokens) < 2:
            continue
        ref = tokens[0]
        part_type = tokens[1]
        entry: dict = {
            "ref": ref,
            "part_type": part_type,
            "value": tokens[2] if len(tokens) > 2 else "",
            "x": None,
            "y": None,
            "rot": None,
            "layer": "",
        }
        parts.append(entry)
        footprints.append(entry.copy())
    return parts, footprints


def _parse_allegro_nets(lines: list[str]) -> list[dict]:
    """
    Parse $NETS section.

    Format (multi-line):
      NET_NAME
      REF.PIN REF.PIN ...
    """
    nets: list[dict] = []
    cur_net: Optional[dict] = None

    for line in lines:
        tokens = line.split()
        if not tokens:
            continue
        # Detect net header: single token with no "." separator
        if len(tokens) == 1 and "." not in tokens[0]:
            if cur_net is not None:
                nets.append(cur_net)
            cur_net = {"name": tokens[0], "pins": []}
            continue
        # Pin references
        if cur_net is None:
            cur_net = {"name": "UNNAMED", "pins": []}
        for tok in tokens:
            cur_net["pins"].append(tok)

    if cur_net is not None:
        nets.append(cur_net)

    return nets


def _parse_allegro_locations(lines: list[str], ref_map: dict[str, int], parts: list[dict]) -> None:
    """
    Parse $LOCATIONS section and mutate parts in-place.

    Format: REF  X  Y  ROT  SIDE(T/B)
    """
    for line in lines:
        tokens = line.split()
        if len(tokens) < 2:
            continue
        ref = tokens[0]
        try:
            x = float(tokens[1]) if len(tokens) > 1 else None
            y = float(tokens[2]) if len(tokens) > 2 else None
            rot = float(tokens[3]) if len(tokens) > 3 else None
            side = tokens[4].upper() if len(tokens) > 4 else ""
            layer = "Top" if side in ("T", "TOP") else ("Bottom" if side in ("B", "BOTTOM") else side)
        except (ValueError, IndexError):
            continue

        if ref in ref_map:
            p = parts[ref_map[ref]]
            p["x"] = x
            p["y"] = y
            p["rot"] = rot
            p["layer"] = layer


def _try_parse_allegro_asc(text: str) -> Optional[dict]:
    """
    Attempt Allegro ASCII (.asc / .brd text) parse.
    Returns result dict or None if not recognised.
    """
    if not _SECTION_HDR_RE.search(text):
        return None

    parts: list[dict] = []
    nets: list[dict] = []
    footprints: list[dict] = []
    warns: list[str] = []
    seen: set[str] = set()

    for kw, lines in _iter_allegro_sections(text):
        seen.add(kw)

        if kw in ("PACKAGES", "PACKAGE"):
            p, fp = _parse_allegro_packages(lines)
            parts.extend(p)
            footprints.extend(fp)

        elif kw in ("NETS", "NET"):
            nets.extend(_parse_allegro_nets(lines))

        elif kw == "LOCATIONS":
            ref_map = {p["ref"]: i for i, p in enumerate(parts)}
            _parse_allegro_locations(lines, ref_map, parts)
            # Sync footprints from parts
            fp_ref_map = {fp["ref"]: i for i, fp in enumerate(footprints)}
            for p in parts:
                if p["ref"] in fp_ref_map:
                    fp = footprints[fp_ref_map[p["ref"]]]
                    fp["x"] = p["x"]
                    fp["y"] = p["y"]
                    fp["rot"] = p["rot"]
                    fp["layer"] = p["layer"]

        elif kw == "END":
            break

        else:
            warns.append(f"unsupported Allegro section ${kw} skipped")

    if not seen:
        return None

    return {
        "ok": True,
        "format": "allegro_asc",
        "parts": parts,
        "nets": nets,
        "signals": [],
        "footprints": footprints,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_allegro(data: str | bytes) -> dict:
    """
    Parse a Cadence Allegro IPC-2581 XML or ASCII board export.

    Tries IPC-2581 first; falls back to Allegro ASCII format.
    Never raises — errors surface as {"ok": False, "reason": str}.
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

        # Try IPC-2581 if the content looks like XML
        stripped = text.lstrip()
        if stripped.startswith("<") or stripped.startswith("<?"):
            result = _try_parse_ipc2581(text)
            if result is not None:
                return result
            warns.append("XML detected but not recognised as IPC-2581; trying ASCII parser")

        # Try Allegro ASCII
        result = _try_parse_allegro_asc(text)
        if result is not None:
            result["warnings"] = warns + result["warnings"]
            return result

        return {
            "ok": False,
            "reason": (
                "input not recognised as IPC-2581 XML or Allegro ASCII; "
                "ensure the file is an Allegro IPC-2581 export or ASCII netlist"
            ),
        }

    except Exception as exc:
        return {"ok": False, "reason": f"unexpected error: {exc}"}


# ---------------------------------------------------------------------------
# LLM tool (gated — only registered when Kerf runtime is available)
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx

    _import_allegro_spec = ToolSpec(
        name="import_allegro",
        description=(
            "Import a Cadence Allegro PCB design file into the current Kerf project. "
            "Accepts a blob_id or storage_key pointing to an IPC-2581 XML export "
            "(preferred) or an Allegro ASCII netlist/board report. "
            "Parses components, nets, placement, and routing into a structured "
            "netlist + footprint model. "
            "Gate: imports.allegro capability."
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
                    "description": (
                        "Blob ID or storage key for the Allegro IPC-2581 or ASCII file."
                    ),
                },
                "import_folder": {
                    "type": "string",
                    "description": (
                        "Path in the project tree for the imported file. "
                        "Defaults to /allegro_import."
                    ),
                },
            },
            "required": ["project_id", "file_blob_id_or_storage_key"],
        },
    )

    @register(_import_allegro_spec, write=True)
    async def run_import_allegro(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        project_id = a.get("project_id", "").strip()
        blob_ref = a.get("file_blob_id_or_storage_key", "").strip()
        import_folder = a.get("import_folder", "/allegro_import").strip()

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

        model = parse_allegro(blob_bytes)
        if not model.get("ok"):
            return err_payload(model.get("reason", "Allegro parse failed"), "PARSE_ERROR")

        try:
            _pid = uuid.UUID(project_id)
        except Exception:
            return err_payload("project_id must be a valid UUID", "BAD_ARGS")

        fid = uuid.uuid4()
        content = json.dumps({
            "version": 1,
            "format": model["format"],
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
                f"{import_folder}/allegro_netlist.json",
                "allegro_netlist",
                content,
            )
        except Exception as exc:
            model["warnings"].append(f"failed to persist Allegro file: {exc}")

        return ok_payload({
            "ok": True,
            "file_id": str(fid),
            "format": model["format"],
            "part_count": len(model["parts"]),
            "net_count": len(model["nets"]),
            "signal_count": len(model["signals"]),
            "footprint_count": len(model["footprints"]),
            "warnings": model["warnings"],
        })

    TOOLS = [(_import_allegro_spec.name, _import_allegro_spec, run_import_allegro)]

except ImportError:
    pass
