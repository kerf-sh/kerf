"""pcb_pins.py — extract pin→net assignments from a KiCad .kicad_pcb file.

Parses the s-expression PCB format and returns a mapping:
    {pad_number_str: net_name_str}

for a specified component reference (default: the first MCU/U* component).

A "pin" in the PCB context is a pad number (e.g. "1", "21", "PA0").
The returned dict maps each pad's pin number to its net name.

Public API
----------
parse_kicad_pcb_pins(text, ref=None) -> dict[str, PcbPin]
    text  — contents of a .kicad_pcb file
    ref   — component reference to inspect (e.g. "U1").
            If None, picks the first footprint whose reference starts with "U".

Returns dict mapping pad_number → PcbPin(net, direction)
  direction is inferred from net-name conventions:
    - nets containing "SDA", "SCL" → i2c
    - nets containing "TX", "RX"   → uart
    - nets containing "MOSI", "MISO", "SCK", "SS" → spi
    - nets starting "GPIO" or "D"   → gpio
    - else                          → unknown
    - INPUT_ONLY in net name        → input_only (read-only hw constraint)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PcbPin:
    """One pad on the PCB with its net assignment."""
    pad: str          # pad number / name as string (e.g. "21")
    net: str          # net name (e.g. "SDA", "GPIO21", "INPUT_ONLY_PA0")
    direction: str    # inferred: "input_only" | "i2c" | "spi" | "uart" | "gpio" | "unknown"


def _tokenize(text: str) -> list[str]:
    """Minimal s-expression tokenizer (same logic as kicad_io)."""
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "(":
            tokens.append("(")
            i += 1
        elif c == ")":
            tokens.append(")")
            i += 1
        elif c == '"':
            j = i + 1
            buf: list[str] = []
            while j < n:
                ch = text[j]
                if ch == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                elif ch == '"':
                    j += 1
                    break
                else:
                    buf.append(ch)
                    j += 1
            tokens.append('"' + "".join(buf) + '"')
            i = j
        else:
            j = i
            while j < n and text[j] not in " \t\r\n()\"":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse(tokens: list[str], pos: int = 0) -> tuple:
    if pos >= len(tokens):
        return None, pos
    tok = tokens[pos]
    if tok == "(":
        pos += 1
        node: list = []
        while pos < len(tokens) and tokens[pos] != ")":
            child, pos = _parse(tokens, pos)
            node.append(child)
        pos += 1  # consume ')'
        return node, pos
    elif tok == ")":
        raise ValueError(f"Unexpected ')' at position {pos}")
    else:
        if tok.startswith('"') and tok.endswith('"'):
            return tok[1:-1], pos + 1
        return tok, pos + 1


def _parse_sexpr(text: str):
    tokens = _tokenize(text)
    if not tokens:
        return []
    node, _ = _parse(tokens, 0)
    return node


def _infer_direction(net_name: str) -> str:
    """Infer pin direction/type from net name conventions."""
    upper = net_name.upper()
    if "INPUT_ONLY" in upper:
        return "input_only"
    if any(kw in upper for kw in ("SDA", "SCL")):
        return "i2c"
    if any(kw in upper for kw in ("MOSI", "MISO", "SCK", "/SS", "_SS", "NSS", "MOSI", "CS")):
        return "spi"
    if any(kw in upper for kw in ("TX", "RX", "UART")):
        return "uart"
    if re.search(r"(GPIO|^D\d|_D\d|PA\d|PB\d|PC\d|PD\d|PE\d|PF\d|PG\d)", net_name, re.IGNORECASE):
        return "gpio"
    return "unknown"


def _find_footprint_node(root_nodes: list, ref: Optional[str]) -> Optional[list]:
    """Walk top-level nodes and return the footprint node for *ref*.

    If ref is None, returns the first footprint whose reference starts with "U".
    """
    candidates: list[tuple[str, list]] = []

    for node in root_nodes:
        if not isinstance(node, list) or not node or node[0] != "footprint":
            continue
        # Extract reference from fp_text reference or property Reference children
        fp_ref = ""
        for child in node[2:]:
            if not isinstance(child, list) or not child:
                continue
            tag = child[0]
            if tag == "fp_text" and len(child) >= 3 and child[1] == "reference":
                fp_ref = child[2] if isinstance(child[2], str) else ""
                break
            if tag == "property" and len(child) >= 3:
                key = child[1] if isinstance(child[1], str) else ""
                val = child[2] if isinstance(child[2], str) else ""
                if key.lower() == "reference":
                    fp_ref = val
                    break
        if ref is not None:
            if fp_ref == ref:
                return node
        else:
            if fp_ref.startswith("U"):
                candidates.append((fp_ref, node))

    if ref is None and candidates:
        # Return the first U* component found
        return candidates[0][1]
    return None


def parse_kicad_pcb_pins(text: str, ref: Optional[str] = None) -> dict[str, PcbPin]:
    """Parse a .kicad_pcb string and return pad-number → PcbPin for *ref*.

    Parameters
    ----------
    text:
        Full text content of a .kicad_pcb file.
    ref:
        Component reference (e.g. "U1").  If None, picks the first "U*" component.

    Returns
    -------
    dict mapping pad number string → PcbPin.  Empty dict if component not found.
    """
    root = _parse_sexpr(text)
    if not isinstance(root, list) or not root:
        return {}

    # Build net index → name table from top-level net declarations
    net_index_to_name: dict[int, str] = {}
    for node in root[1:]:
        if not isinstance(node, list) or not node or node[0] != "net":
            continue
        if len(node) >= 3:
            try:
                idx = int(node[1])
                name = node[2] if isinstance(node[2], str) else str(node[2])
                if name:
                    net_index_to_name[idx] = name
            except (ValueError, TypeError):
                pass

    fp_node = _find_footprint_node(root[1:], ref)
    if fp_node is None:
        return {}

    pins: dict[str, PcbPin] = {}

    for child in fp_node[2:]:
        if not isinstance(child, list) or not child or child[0] != "pad":
            continue
        # (pad <number> <type> <shape> (at ...) (size ...) (net <idx> <name>) ...)
        if len(child) < 3:
            continue
        pad_num = str(child[1]) if child[1] is not None else ""
        if not pad_num:
            continue

        # Find the (net ...) sub-node
        net_name = ""
        for sub in child[3:]:
            if not isinstance(sub, list) or not sub or sub[0] != "net":
                continue
            if len(sub) >= 3:
                # (net <idx> <name>) or (net <idx> "name")
                try:
                    net_idx = int(sub[1])
                    net_name = sub[2] if isinstance(sub[2], str) else str(sub[2])
                except (ValueError, TypeError):
                    pass
            elif len(sub) >= 2:
                # (net <idx>) — look up by index
                try:
                    net_idx = int(sub[1])
                    net_name = net_index_to_name.get(net_idx, "")
                except (ValueError, TypeError):
                    pass
            break  # only one (net) child per pad

        if not net_name:
            # Try resolving via net index table (some writers only store index)
            for sub in child[3:]:
                if not isinstance(sub, list) or not sub or sub[0] != "net":
                    continue
                if len(sub) >= 2:
                    try:
                        net_idx = int(sub[1])
                        net_name = net_index_to_name.get(net_idx, "")
                    except (ValueError, TypeError):
                        pass

        if net_name:
            pins[pad_num] = PcbPin(
                pad=pad_num,
                net=net_name,
                direction=_infer_direction(net_name),
            )

    return pins
