"""
spice_netlist.py — SPICE deck emitter and raw-output parser for device-level
silicon simulation (MOSFET-level, BSIM4-style models, sub-circuits).

This module is distinct from kerf_electronics.routes_spice which handles
PCB-level analysis.  Here we target transistor-level CMOS netlists (130nm /
sky130 process corner), emit proper transient analysis decks, and parse
ngspice's columnar text output back into named time/voltage arrays.

Public API
----------
    build_transient_deck(title, elements, t_step_ns, t_stop_ns,
                         *, probes=None, models=None) -> str
        Emit a complete SPICE transient-analysis deck.

    build_dc_deck(title, elements, vstart, vstop, vstep,
                  *, probes=None, models=None) -> str
        Emit a SPICE DC sweep deck.

    parse_ngspice_output(text) -> dict[str, list[float]]
        Parse ngspice batch-mode columnar output (the text written to stdout
        by `ngspice -b -o stdout input.cir`) into
        ``{node_name: [v0, v1, ...], "time": [t0, t1, ...]}``.

Netlist element helpers
-----------------------
    mosfet_nmos(ref, drain, gate, source, bulk, model,
                W_nm=500, L_nm=130) -> str
    mosfet_pmos(ref, drain, gate, source, bulk, model,
                W_nm=1000, L_nm=130) -> str
    vdc(ref, pos, neg, voltage) -> str
    vpulse(ref, pos, neg, v0, v1, td_ns, tr_ns, tf_ns,
           pw_ns, per_ns) -> str
    cap(ref, pos, neg, farads) -> str
    res(ref, pos, neg, ohms) -> str
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Netlist element helpers
# ---------------------------------------------------------------------------

def mosfet_nmos(
    ref: str,
    drain: str,
    gate: str,
    source: str,
    bulk: str,
    model: str,
    W_nm: int = 500,
    L_nm: int = 130,
) -> str:
    """Return a MOSFET NMOS element line.

    SPICE syntax: M<ref> <drain> <gate> <source> <bulk> <model> W=<W>n L=<L>n
    """
    return f"M{ref} {drain} {gate} {source} {bulk} {model} W={W_nm}n L={L_nm}n"


def mosfet_pmos(
    ref: str,
    drain: str,
    gate: str,
    source: str,
    bulk: str,
    model: str,
    W_nm: int = 1000,
    L_nm: int = 130,
) -> str:
    """Return a MOSFET PMOS element line (wider than NMOS by default for CMOS)."""
    return f"M{ref} {drain} {gate} {source} {bulk} {model} W={W_nm}n L={L_nm}n"


def vdc(ref: str, pos: str, neg: str, voltage: float) -> str:
    """Return a DC voltage source element line."""
    return f"V{ref} {pos} {neg} DC {voltage:.4g}"


def vpulse(
    ref: str,
    pos: str,
    neg: str,
    v0: float,
    v1: float,
    td_ns: float,
    tr_ns: float,
    tf_ns: float,
    pw_ns: float,
    per_ns: float,
) -> str:
    """Return a PULSE voltage source element line (all times in ns)."""
    return (
        f"V{ref} {pos} {neg} PULSE({v0:.4g} {v1:.4g} "
        f"{td_ns:.4g}n {tr_ns:.4g}n {tf_ns:.4g}n "
        f"{pw_ns:.4g}n {per_ns:.4g}n)"
    )


def cap(ref: str, pos: str, neg: str, farads: float) -> str:
    """Return a capacitor element line."""
    return f"C{ref} {pos} {neg} {farads:.4g}"


def res(ref: str, pos: str, neg: str, ohms: float) -> str:
    """Return a resistor element line."""
    return f"R{ref} {pos} {neg} {ohms:.4g}"


# ---------------------------------------------------------------------------
# Deck builders
# ---------------------------------------------------------------------------

def _probe_lines(probes: Optional[list[str]], analysis_keyword: str) -> list[str]:
    """Return .PRINT lines for the requested probes."""
    if not probes:
        return []
    return [f".PRINT {analysis_keyword} " + " ".join(probes)]


def _model_lines(models: Optional[list[str]]) -> list[str]:
    """Return raw model lines (each already a complete SPICE directive)."""
    if not models:
        return []
    return list(models)


def build_transient_deck(
    title: str,
    elements: list[str],
    t_step_ns: float,
    t_stop_ns: float,
    *,
    probes: Optional[list[str]] = None,
    models: Optional[list[str]] = None,
) -> str:
    """Emit a complete SPICE transient-analysis deck.

    Parameters
    ----------
    title:
        First line of the deck (SPICE title comment).
    elements:
        List of SPICE element / directive lines.
    t_step_ns:
        Time step in nanoseconds.
    t_stop_ns:
        Stop time in nanoseconds.
    probes:
        Optional list of node expressions e.g. ``["V(vout)", "V(vdd)"]``.
    models:
        Optional list of raw model lines to inject before .TRAN.

    Returns
    -------
    str
        Complete SPICE deck ending with ``.end``.
    """
    lines: list[str] = [title]
    lines.extend(elements)
    lines.extend(_model_lines(models))
    lines.append(f".TRAN {t_step_ns:.4g}n {t_stop_ns:.4g}n")
    lines.extend(_probe_lines(probes, "TRAN"))
    lines.append(".end")
    return "\n".join(lines) + "\n"


def build_dc_deck(
    title: str,
    elements: list[str],
    source_name: str,
    vstart: float,
    vstop: float,
    vstep: float,
    *,
    probes: Optional[list[str]] = None,
    models: Optional[list[str]] = None,
) -> str:
    """Emit a SPICE DC sweep deck.

    Parameters
    ----------
    source_name:
        Name of the voltage source to sweep, e.g. ``"Vin"``.
    vstart, vstop, vstep:
        Sweep parameters in volts.
    """
    lines: list[str] = [title]
    lines.extend(elements)
    lines.extend(_model_lines(models))
    lines.append(f".DC {source_name} {vstart:.4g} {vstop:.4g} {vstep:.4g}")
    lines.extend(_probe_lines(probes, "DC"))
    lines.append(".end")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# ngspice columnar output parser
# ---------------------------------------------------------------------------

# ngspice -b writes its print output as:
#
#   Index   time        V(vout)     V(vin)
#   ------  ----------  ----------  ----------
#   0       0.000000e+00  1.800000e+00  0.000000e+00
#   1       1.000000e-09  1.799123e+00  ...
#   ...
#
# The exact format varies; we support both the ngspice "tabular" output
# and the simpler two-column form.

_FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def parse_ngspice_output(text: str) -> dict[str, list[float]]:
    """Parse ngspice batch-mode columnar print output.

    Handles the format produced by:
        .PRINT TRAN V(node1) V(node2) ...
    when run via ``ngspice -b``.

    Returns
    -------
    dict mapping column header names to lists of float values.
    The time axis (if present) is keyed ``"time"``.
    Unknown/index columns are keyed by their position (``"col_0"``, etc.).
    Returns an empty dict if no data is found.
    """
    result: dict[str, list[float]] = {}
    headers: list[str] = []
    data_started = False

    for line in text.splitlines():
        stripped = line.strip()

        # Skip blank lines and ngspice informational output
        if not stripped:
            continue
        if stripped.startswith(("Note:", "Warning:", "Error:", "**", "Circuit:", "ngspice")):
            continue

        # Detect header line: contains variable names (not pure numbers)
        # ngspice headers often look like: "Index   time   V(vout)  ..."
        # or just: "time   V(out)"
        if not data_started and not headers:
            # Check if this looks like a header: has alpha tokens
            tokens = stripped.split()
            if any(re.search(r"[a-zA-Z(]", t) for t in tokens):
                # Normalise header names
                raw_headers = tokens
                headers = []
                for h in raw_headers:
                    hl = h.lower()
                    if hl in ("index", "step"):
                        headers.append(f"_skip_{len(headers)}")
                    else:
                        headers.append(hl)
                for h in headers:
                    if not h.startswith("_skip_"):
                        result[h] = []
                continue

        # Separator line (dashes)
        if re.match(r"^[-\s]+$", stripped):
            if headers:
                data_started = True
            continue

        # Data line: must start with a float or index integer
        tokens = stripped.split()
        if not tokens:
            continue

        # Try to parse all tokens as floats
        values: list[float] = []
        all_numeric = True
        for t in tokens:
            try:
                values.append(float(t))
            except ValueError:
                all_numeric = False
                break

        if not all_numeric:
            # Not a data line; might be a sub-header or annotation
            # If we haven't found headers yet and this line has "time" in it,
            # treat it as a late header
            if not headers and "time" in stripped.lower():
                raw_headers = tokens
                headers = []
                for h in raw_headers:
                    hl = h.lower()
                    if hl in ("index", "step"):
                        headers.append(f"_skip_{len(headers)}")
                    else:
                        headers.append(hl)
                for h in headers:
                    if not h.startswith("_skip_"):
                        result[h] = []
            continue

        if not values:
            continue

        # Map values to headers
        if headers:
            for i, val in enumerate(values):
                if i < len(headers):
                    key = headers[i]
                    if not key.startswith("_skip_"):
                        result[key].append(val)
                else:
                    # Extra columns beyond header count
                    extra_key = f"col_{i}"
                    result.setdefault(extra_key, []).append(val)
        else:
            # No headers: use positional keys
            for i, val in enumerate(values):
                key = f"col_{i}"
                result.setdefault(key, []).append(val)

    return result


# ---------------------------------------------------------------------------
# SPICE deck validation helpers
# ---------------------------------------------------------------------------

def is_valid_spice_deck(text: str) -> tuple[bool, str]:
    """Return (True, "") if ``text`` is a plausibly valid SPICE deck.

    Checks:
    - Non-empty
    - Contains a title line (first non-blank line is not a directive)
    - Contains at least one analysis directive (.TRAN / .DC / .AC / .OP)
    - Ends with .end (case-insensitive)

    Returns (False, reason) on failure.
    """
    if not text or not text.strip():
        return False, "empty deck"

    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return False, "no non-blank lines"

    # First line is the title — must not start with '.' (directives)
    # Exception: some tools emit .title; treat those as valid
    first = lines[0].strip()
    if first.upper().startswith(".END") and len(lines) == 1:
        return False, "deck is only .end"

    # Must have an analysis directive
    analysis_re = re.compile(r"^\.(TRAN|DC|AC|OP|NOISE)\b", re.IGNORECASE)
    has_analysis = any(analysis_re.match(l.strip()) for l in lines)
    if not has_analysis:
        return False, "no analysis directive (.TRAN/.DC/.AC/.OP/.NOISE)"

    # Must end with .end
    last = lines[-1].strip().upper()
    if not last.startswith(".END"):
        return False, f"deck does not end with .end (last line: {lines[-1]!r})"

    return True, ""


def has_subckt(text: str) -> bool:
    """Return True if the deck contains at least one .SUBCKT definition."""
    return bool(re.search(r"^\.SUBCKT\b", text, re.IGNORECASE | re.MULTILINE))


def has_model(text: str) -> bool:
    """Return True if the deck contains at least one .MODEL directive."""
    return bool(re.search(r"^\.MODEL\b", text, re.IGNORECASE | re.MULTILINE))


def extract_probe_nodes(text: str) -> list[str]:
    """Return the list of node expressions from .PRINT lines in the deck."""
    nodes: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^\.PRINT\s+\S+\s+(.+)", line.strip(), re.IGNORECASE)
        if m:
            nodes.extend(m.group(1).split())
    return nodes
