"""
pads_reader.py — PADS ASCII netlist / layout reader.

Parses PADS ASCII format as used by PADS Logic / PADS Layout / PADS PCB.
The file is structured around section records delimited by ``*KEYWORD*``
markers.  This reader handles the most common exchange sections:

  *PART*      → reference designators, part types, component locations
  *NET*       → net names + pin assignments
  *ROUTE*     → routed wire segments on copper layers
  *SIGNAL*    → alias for *NET* used by some PADS variants
  *REMARK*    → comments (skipped)
  *END*       → end of file

Pure Python — stdlib only; no third-party deps.

Output model
------------
  {
    "ok": True,
    "parts": [
      {
        "ref":        str,   # e.g. "R1"
        "part_type":  str,   # e.g. "RES-0805"
        "x":          float | None,
        "y":          float | None,
        "rot":        float | None,
        "layer":      str,   # "Top" | "Bottom" | ""
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

LLM tool ``import_pads`` registered via @register; gated on "imports.pads".
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Section splitter
# ---------------------------------------------------------------------------

# PADS ASCII sections start with *KEYWORD* on a line by themselves.
_SECTION_RE = re.compile(r"^\*([A-Z][A-Z0-9_]*)\*\s*$", re.IGNORECASE | re.MULTILINE)


def _iter_sections(text: str):
    """
    Yield ``(keyword, lines)`` for each PADS ASCII section.

    *keyword* is the marker name (upper-case, no asterisks).
    *lines*   is the list of non-empty, non-comment lines until the next
               ``*KEYWORD*`` marker.
    """
    current_kw: Optional[str] = None
    current_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Skip blank lines
        if not line:
            if current_kw is not None:
                pass  # allow blanks inside sections; they are stripped anyway
            continue

        # Skip comment lines (start with "!" or ";")
        if line.startswith("!") or line.startswith(";"):
            continue

        m = _SECTION_RE.match(line)
        if m:
            if current_kw is not None:
                yield current_kw, current_lines
            current_kw = m.group(1).upper()
            current_lines = []
        else:
            if current_kw is not None:
                current_lines.append(line)

    if current_kw is not None:
        yield current_kw, current_lines


# ---------------------------------------------------------------------------
# *PART* section parser
# ---------------------------------------------------------------------------

def _parse_part_section(lines: list[str]) -> tuple[list[dict], list[dict], list[str]]:
    """
    Parse lines from a *PART* section.

    PADS Layout *PART* line format (one component per line):
      REF PART_TYPE X Y ROT LAYER_FLAG [attributes...]

    Where LAYER_FLAG is 0 = Top, 1 = Bottom (some variants use T/B strings).

    PADS Logic *PART* format is simpler:
      REF PART_TYPE

    We parse both forms and attempt float conversion of X/Y/ROT.
    Returns (parts_list, footprints_list, warnings).
    """
    parts: list[dict] = []
    footprints: list[dict] = []
    warns: list[str] = []

    for line in lines:
        tokens = line.split()
        if len(tokens) < 2:
            warns.append(f"*PART* line too short, skipping: {line!r}")
            continue

        ref = tokens[0]
        part_type = tokens[1]
        x: Optional[float] = None
        y: Optional[float] = None
        rot: Optional[float] = None
        layer = ""

        if len(tokens) >= 5:
            try:
                x = float(tokens[2])
                y = float(tokens[3])
                rot = float(tokens[4])
            except ValueError:
                warns.append(f"non-numeric coordinates in *PART* line: {line!r}")

        if len(tokens) >= 6:
            lf = tokens[5]
            if lf in ("0", "T", "TOP"):
                layer = "Top"
            elif lf in ("1", "B", "BOTTOM"):
                layer = "Bottom"
            else:
                layer = lf

        entry = {
            "ref": ref,
            "part_type": part_type,
            "x": x,
            "y": y,
            "rot": rot,
            "layer": layer,
        }
        parts.append(entry)
        footprints.append(entry.copy())

    return parts, footprints, warns


# ---------------------------------------------------------------------------
# *NET* / *SIGNAL* section parser
# ---------------------------------------------------------------------------

def _parse_net_section(lines: list[str]) -> tuple[list[dict], list[str]]:
    """
    Parse lines from a *NET* or *SIGNAL* section.

    PADS ASCII *NET* format (multiple nets, each introduced by a
    net-header line):

      NET_NAME pin_count
      REF.PIN REF.PIN ...   (one or more continuation lines)

    Continuation lines contain whitespace-delimited REF.PIN tokens.
    Some variants use a dash-separated "REF-PIN" form.  We normalise
    both to "REF.PIN".

    Returns (nets_list, warnings).
    """
    nets: list[dict] = []
    warns: list[str] = []
    cur_net: Optional[dict] = None

    for line in lines:
        tokens = line.split()
        if not tokens:
            continue

        # Heuristic: a line with exactly 2 tokens where the second is an
        # integer is a net header (net_name + pin_count).
        if len(tokens) == 2 and tokens[1].lstrip("-").isdigit():
            if cur_net is not None:
                nets.append(cur_net)
            cur_net = {"name": tokens[0], "pins": []}
            continue

        # Fallback: single token that looks like a net name (no "." or "-"
        # separating a pin) is also treated as a net header line if there
        # is no current net yet.
        if len(tokens) == 1 and "." not in tokens[0] and "-" not in tokens[0]:
            if cur_net is not None:
                nets.append(cur_net)
            cur_net = {"name": tokens[0], "pins": []}
            continue

        # Otherwise: pin reference line
        if cur_net is None:
            warns.append(f"*NET* pin line before net header, skipping: {line!r}")
            continue

        for tok in tokens:
            # Normalise dash separator to dot: "U1-A3" → "U1.A3"
            normalised = tok.replace("-", ".", 1) if "-" in tok and "." not in tok else tok
            cur_net["pins"].append(normalised)

    if cur_net is not None:
        nets.append(cur_net)

    return nets, warns


# ---------------------------------------------------------------------------
# *ROUTE* section parser
# ---------------------------------------------------------------------------

_COORD_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")


def _parse_route_section(lines: list[str]) -> tuple[list[dict], list[str]]:
    """
    Parse lines from a *ROUTE* section.

    PADS ASCII *ROUTE* format:
      NET_NAME
      X1 Y1 X2 Y2 LAYER_NUM [width]

    Returns (signals_list, warnings).
    """
    signals: list[dict] = []
    warns: list[str] = []
    cur_signal: Optional[dict] = None

    for line in lines:
        tokens = line.split()
        if not tokens:
            continue

        # Net / signal name line: single token, no digits-only values
        if len(tokens) == 1:
            if cur_signal is not None:
                signals.append(cur_signal)
            cur_signal = {"name": tokens[0], "wires": []}
            continue

        # Try to parse a coordinate line: X1 Y1 X2 Y2 [LAYER ...]
        if len(tokens) >= 4:
            try:
                x1 = float(tokens[0])
                y1 = float(tokens[1])
                x2 = float(tokens[2])
                y2 = float(tokens[3])
                layer = tokens[4] if len(tokens) > 4 else ""
                if cur_signal is None:
                    cur_signal = {"name": "UNNAMED", "wires": []}
                cur_signal["wires"].append({
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "layer": layer,
                })
                continue
            except ValueError:
                pass

        # Net name with extra info
        if cur_signal is not None:
            signals.append(cur_signal)
        cur_signal = {"name": tokens[0], "wires": []}

    if cur_signal is not None:
        signals.append(cur_signal)

    return signals, warns


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_pads(data: str | bytes) -> dict:
    """
    Parse a PADS ASCII netlist or layout file from a string or bytes.

    Returns the Kerf netlist + footprint dict (see module docstring).
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

        # Require at least one *KEYWORD* marker to distinguish from random text
        if not _SECTION_RE.search(text):
            return {"ok": False, "reason": "no PADS section markers found; not a PADS ASCII file"}

        parts: list[dict] = []
        nets: list[dict] = []
        signals: list[dict] = []
        footprints: list[dict] = []

        seen_sections: set[str] = set()

        for kw, lines in _iter_sections(text):
            seen_sections.add(kw)

            if kw in ("PART", "PARTS"):
                p, fp, w = _parse_part_section(lines)
                parts.extend(p)
                footprints.extend(fp)
                warns.extend(w)

            elif kw in ("NET", "SIGNAL", "NETS"):
                n, w = _parse_net_section(lines)
                nets.extend(n)
                warns.extend(w)

            elif kw in ("ROUTE", "ROUTES"):
                s, w = _parse_route_section(lines)
                signals.extend(s)
                warns.extend(w)

            elif kw in ("REMARK", "END", "PADS2000", "PADS-PCB"):
                pass  # known, intentionally skipped

            else:
                warns.append(f"unsupported PADS section *{kw}* skipped")

        if not seen_sections:
            return {"ok": False, "reason": "no recognisable PADS sections found"}

        return {
            "ok": True,
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

    _import_pads_spec = ToolSpec(
        name="import_pads",
        description=(
            "Import a PADS ASCII netlist or PCB layout file into the current "
            "Kerf project. "
            "Accepts a blob_id or storage_key pointing to the uploaded PADS file. "
            "Parses *PART*, *NET*, and *ROUTE* sections into structured parts, "
            "nets, signals, and footprints. "
            "Gate: imports.pads capability."
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
                    "description": "Blob ID or storage key for the PADS ASCII file.",
                },
                "import_folder": {
                    "type": "string",
                    "description": (
                        "Path in the project tree for the imported file. "
                        "Defaults to /pads_import."
                    ),
                },
            },
            "required": ["project_id", "file_blob_id_or_storage_key"],
        },
    )

    @register(_import_pads_spec, write=True)
    async def run_import_pads(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        project_id = a.get("project_id", "").strip()
        blob_ref = a.get("file_blob_id_or_storage_key", "").strip()
        import_folder = a.get("import_folder", "/pads_import").strip()

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

        model = parse_pads(blob_bytes)
        if not model.get("ok"):
            return err_payload(model.get("reason", "PADS parse failed"), "PARSE_ERROR")

        try:
            _pid = uuid.UUID(project_id)
        except Exception:
            return err_payload("project_id must be a valid UUID", "BAD_ARGS")

        fid = uuid.uuid4()
        content = json.dumps({
            "version": 1,
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
                f"{import_folder}/pads_netlist.json",
                "pads_netlist",
                content,
            )
        except Exception as exc:
            model["warnings"].append(f"failed to persist PADS file: {exc}")

        return ok_payload({
            "ok": True,
            "file_id": str(fid),
            "part_count": len(model["parts"]),
            "net_count": len(model["nets"]),
            "signal_count": len(model["signals"]),
            "footprint_count": len(model["footprints"]),
            "warnings": model["warnings"],
        })

    TOOLS = [(_import_pads_spec.name, _import_pads_spec, run_import_pads)]

except ImportError:
    pass
