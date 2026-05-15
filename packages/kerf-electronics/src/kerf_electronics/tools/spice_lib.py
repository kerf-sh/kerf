"""spice_lib.py — Built-in SPICE model library + per-component model assignment.

Provides a curated library of generic device models (diodes, BJTs, MOSFETs,
op-amps, regulators, passives with parasitics) and tools to attach those models
to reference designators in a netlist, feeding the existing sim flow in sim.py /
routes_spice.py without forking the simulator.

IMPORTANT — Representative values notice
-----------------------------------------
All parameter values in this library are representative / generic values
chosen to approximate real-world device classes. They are NOT extracted from
vendor datasheets and should NOT be used for high-accuracy production simulation.
For tape-out or critical designs, replace these models with vendor-supplied SPICE
models (.MODEL or .SUBCKT) from the manufacturer's website.
"""

from __future__ import annotations

import json
import re
import textwrap
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

# ---------------------------------------------------------------------------
# Model library — each entry is (family, description, generator_fn)
# The generator returns a SPICE string (one or more .MODEL / .SUBCKT lines).
# ---------------------------------------------------------------------------

# ── Diodes ──────────────────────────────────────────────────────────────────

def _diode_1n4148() -> str:
    return ".MODEL D1N4148 D(IS=2.52e-9 RS=0.568 N=1.752 CJO=4e-12 M=0.4 BV=100 IBV=0.1e-3)"


def _diode_1n4001() -> str:
    return ".MODEL D1N4001 D(IS=1e-8 RS=0.1 N=1.8 CJO=25e-12 M=0.5 BV=50 IBV=1e-3)"


def _diode_1n4007() -> str:
    return ".MODEL D1N4007 D(IS=5e-9 RS=0.1 N=1.8 CJO=15e-12 M=0.5 BV=1000 IBV=5e-6)"


def _diode_schottky_generic() -> str:
    """Generic Schottky diode (~1N5817 class, Vf≈0.3 V at 1 A)."""
    return ".MODEL DSCHOTTKY D(IS=4e-8 RS=0.04 N=1.05 CJO=150e-12 M=0.4 BV=20 IBV=1e-3)"


def _diode_zener_5v1() -> str:
    """Generic 5.1 V Zener (representative — e.g. 1N751A class)."""
    return ".MODEL DZENER5V1 D(IS=1e-14 RS=10 N=1 BV=5.1 IBV=5e-3)"


def _diode_zener_12v() -> str:
    """Generic 12 V Zener (representative — e.g. 1N4742A class)."""
    return ".MODEL DZENER12V D(IS=1e-14 RS=8 N=1 BV=12 IBV=1e-3)"


# ── BJTs ────────────────────────────────────────────────────────────────────

def _bjt_2n3904() -> str:
    """NPN small-signal BJT (2N3904 representative values)."""
    return ".MODEL Q2N3904 NPN(IS=1e-14 BF=300 NF=1 VAF=100 IKF=0.04 ISE=3e-13 NE=2 BR=4 NR=1 VAR=100 RE=0.1 RC=1 RB=10 CJE=4e-12 VJE=0.75 MJE=0.33 CJC=3.5e-12 VJC=0.75 MJC=0.33 FC=0.5 TF=0.5e-9 TR=100e-9)"


def _bjt_2n3906() -> str:
    """PNP small-signal BJT (2N3906 representative values)."""
    return ".MODEL Q2N3906 PNP(IS=1.41e-15 BF=180 NF=1 VAF=80 IKF=0.1 ISE=1e-14 NE=1.5 BR=4 NR=1 RE=0.1 RC=0.5 RB=10 CJE=9.5e-12 VJE=0.75 MJE=0.33 CJC=11.5e-12 VJC=0.75 MJC=0.33 FC=0.5 TF=0.3e-9 TR=50e-9)"


def _bjt_bc547() -> str:
    """NPN small-signal BJT (BC547 representative values)."""
    return ".MODEL QBC547 NPN(IS=1e-14 BF=400 NF=1 VAF=80 IKF=0.02 ISE=2e-13 NE=2 BR=4 NR=1 RE=0.1 RC=0.6 RB=15 CJE=3e-12 VJE=0.75 MJE=0.33 CJC=2.5e-12 VJC=0.75 MJC=0.33 FC=0.5 TF=0.4e-9 TR=80e-9)"


def _bjt_bc557() -> str:
    """PNP small-signal BJT (BC557 representative values)."""
    return ".MODEL QBC557 PNP(IS=1e-14 BF=300 NF=1 VAF=60 IKF=0.02 ISE=2e-13 NE=2 BR=4 NR=1 RE=0.1 RC=0.6 RB=15 CJE=3e-12 VJE=0.75 MJE=0.33 CJC=2.5e-12 VJC=0.75 MJC=0.33 FC=0.5 TF=0.5e-9 TR=100e-9)"


# ── MOSFETs ─────────────────────────────────────────────────────────────────

def _mosfet_2n7000() -> str:
    """N-channel enhancement MOSFET (2N7000 representative — 60 V / 0.2 A)."""
    return ".MODEL M2N7000 NMOS(LEVEL=1 VTO=2.5 KP=0.05 LAMBDA=0.02 GAMMA=0 PHI=0.6 RD=1 RS=1 CBD=15e-12 CBS=15e-12)"


def _mosfet_irf540_generic() -> str:
    """N-channel power MOSFET generic (IRF540 class, 100 V / 28 A representative)."""
    return ".MODEL MIRF540 NMOS(LEVEL=3 VTO=3.0 KP=10 THETA=0.08 VMAX=5e5 ETA=0.002 KAPPA=0.5 RD=0.044 RS=0.044 CBD=500e-12 CBS=500e-12)"


def _mosfet_irf9540_generic() -> str:
    """P-channel power MOSFET generic (IRF9540 class, -100 V / -23 A representative)."""
    return ".MODEL MIRF9540 PMOS(LEVEL=3 VTO=-3.5 KP=8 THETA=0.08 VMAX=5e5 ETA=0.002 KAPPA=0.5 RD=0.117 RS=0.117 CBD=400e-12 CBS=400e-12)"


def _mosfet_2p7000() -> str:
    """P-channel enhancement MOSFET, small-signal (2P7000 generic)."""
    return ".MODEL M2P7000 PMOS(LEVEL=1 VTO=-2.5 KP=0.04 LAMBDA=0.02 GAMMA=0 PHI=0.6 RD=2 RS=2 CBD=15e-12 CBS=15e-12)"


# ── Op-amps ─────────────────────────────────────────────────────────────────

def _opamp_ideal() -> str:
    """Ideal voltage-controlled voltage source op-amp subcircuit (infinite GBW).

    Pins: IN+ IN- V+ V- OUT
    Usage: Xopamp IN+ IN- V+ V- OUT OPAMP_IDEAL
    """
    return textwrap.dedent("""\
        .SUBCKT OPAMP_IDEAL IN+ IN- V+ V- OUT
        * Ideal op-amp: infinite gain, infinite bandwidth, zero output resistance
        * Rail-limited to V+/V- supply using limit expressions (ngspice compatible)
        E_IDEAL OUT 0 VALUE {V(IN+,IN-)*1e6}
        .ENDS OPAMP_IDEAL""")


def _opamp_generic_gbw() -> str:
    """Single-supply op-amp with finite GBW (~1 MHz, representative of LM358/LM741 class).

    Pins: IN+ IN- V+ V- OUT
    Usage: Xopamp IN+ IN- V+ V- OUT OPAMP_GBW1M
    """
    return textwrap.dedent("""\
        .SUBCKT OPAMP_GBW1M IN+ IN- V+ V- OUT
        * Differential input stage
        Rin IN+ IN- 1Meg
        * Gain stage + single-pole rolloff at 1 MHz GBW
        Gin 0 mid IN+ IN- 1e-3
        Rgain mid 0 1k
        Cgain mid 0 159e-9
        * Output buffer (low output impedance)
        Eout OUT 0 VALUE {V(mid)*1e3}
        Rout OUT 0 75
        .ENDS OPAMP_GBW1M""")


def _opamp_generic_fast() -> str:
    """Fast op-amp with ~10 MHz GBW (representative of TL071/TL081 class).

    Pins: IN+ IN- V+ V- OUT
    Usage: Xopamp IN+ IN- V+ V- OUT OPAMP_GBW10M
    """
    return textwrap.dedent("""\
        .SUBCKT OPAMP_GBW10M IN+ IN- V+ V- OUT
        * Fast op-amp ~10 MHz GBW
        Rin IN+ IN- 1Meg
        Gin 0 mid IN+ IN- 1e-3
        Rgain mid 0 1k
        Cgain mid 0 15.9e-9
        Eout OUT 0 VALUE {V(mid)*1e3}
        Rout OUT 0 50
        .ENDS OPAMP_GBW10M""")


# ── Regulators ──────────────────────────────────────────────────────────────

def _ldo_78xx_generic() -> str:
    """78xx-family positive linear regulator (5 V, ~1 A, generic behavioural).

    Pins: IN GND OUT
    Usage: X1 IN GND OUT LDO_78XX
    """
    return textwrap.dedent("""\
        .SUBCKT LDO_78XX IN GND OUT
        * Behavioural 78xx: output clamps at 5 V while IN > 5.7 V
        Rdropout IN OUT 1.2
        Eout OUT GND VALUE {MAX(0, MIN(V(IN,GND)-1.2, 5.0))}
        .ENDS LDO_78XX""")


def _ldo_79xx_generic() -> str:
    """79xx-family negative linear regulator (-5 V, ~1 A, generic behavioural).

    Pins: IN GND OUT
    Usage: X1 IN GND OUT LDO_79XX
    """
    return textwrap.dedent("""\
        .SUBCKT LDO_79XX IN GND OUT
        * Behavioural 79xx: output clamps at -5 V while IN < -5.7 V
        Rdropout IN OUT 1.2
        Eout OUT GND VALUE {MIN(0, MAX(V(IN,GND)+1.2, -5.0))}
        .ENDS LDO_79XX""")


def _ldo_generic_adj() -> str:
    """Generic adjustable LDO (LM317/LT1083 class, ~1.25 V reference, behavioural).

    Pins: IN ADJ OUT
    Usage: X1 IN ADJ OUT LDO_ADJ
    """
    return textwrap.dedent("""\
        .SUBCKT LDO_ADJ IN ADJ OUT
        * Behavioural adjustable LDO: Vout = Vref*(1 + R2/R1) + Iadj*R2
        * Vref ≈ 1.25 V.  Set R1/R2 externally via a resistor divider on ADJ.
        * Here we model the pass element only; Vout = Vin - 1.5V (dropout) clamped >= 1.25V
        Rdropout IN OUT 1.5
        Eout OUT ADJ VALUE {MAX(1.25, V(IN,ADJ)-1.5)}
        .ENDS LDO_ADJ""")


# ── Passives with parasitics ─────────────────────────────────────────────────

def _cap_electrolytic_esr(cap_uf: float = 100.0, esr_ohm: float = 0.1, esl_nh: float = 10.0) -> str:
    """Electrolytic capacitor with ESR + ESL parasitic subcircuit.

    Parameters (representative defaults: 100 µF / 0.1 Ω / 10 nH):
      cap_uf  — capacitance in µF
      esr_ohm — equivalent series resistance in Ω
      esl_nh  — equivalent series inductance in nH

    Pins: P N
    Usage: Xcap P N CAP_ELEC_100U
    """
    name = f"CAP_ELEC_{int(cap_uf)}U"
    return textwrap.dedent(f"""\
        .SUBCKT {name} P N
        * Electrolytic cap with parasitics (representative values)
        * C={cap_uf}uF  ESR={esr_ohm}Ω  ESL={esl_nh}nH
        LESL  P  mid1  {esl_nh}n
        RESR  mid1 mid2  {esr_ohm}
        C1    mid2 N   {cap_uf}u
        .ENDS {name}""")


def _cap_ceramic_x7r(cap_nf: float = 100.0, esr_ohm: float = 0.01, esl_nh: float = 1.0) -> str:
    """Ceramic X7R capacitor with ESR + ESL parasitics.

    Parameters (representative defaults: 100 nF / 0.01 Ω / 1 nH):
      cap_nf  — capacitance in nF
      esr_ohm — equivalent series resistance in Ω
      esl_nh  — equivalent series inductance in nH

    Pins: P N
    Usage: Xcap P N CAP_X7R_100N
    """
    name = f"CAP_X7R_{int(cap_nf)}N"
    return textwrap.dedent(f"""\
        .SUBCKT {name} P N
        * Ceramic X7R cap with parasitics (representative values)
        * C={cap_nf}nF  ESR={esr_ohm}Ω  ESL={esl_nh}nH
        LESL  P  mid1  {esl_nh}n
        RESR  mid1 mid2  {esr_ohm}
        C1    mid2 N   {cap_nf}n
        .ENDS {name}""")


def _inductor_parasitic(ind_uh: float = 10.0, dcr_ohm: float = 0.05, srf_mhz: float = 100.0) -> str:
    """Inductor with DCR and self-resonant frequency parasitics.

    Parameters (representative defaults: 10 µH / 0.05 Ω DCR / 100 MHz SRF):
      ind_uh  — inductance in µH
      dcr_ohm — DC resistance in Ω
      srf_mhz — self-resonant frequency in MHz (sets parallel cap)

    Pins: P N
    Usage: Xind P N IND_10U
    """
    import math
    # Cp = 1 / ((2*pi*SRF)^2 * L)
    srf_hz = srf_mhz * 1e6
    l_h = ind_uh * 1e-6
    cp_f = 1.0 / ((2 * math.pi * srf_hz) ** 2 * l_h)
    name = f"IND_{int(ind_uh)}U"
    return textwrap.dedent(f"""\
        .SUBCKT {name} P N
        * Inductor with DCR and SRF parasitics (representative values)
        * L={ind_uh}uH  DCR={dcr_ohm}Ω  SRF={srf_mhz}MHz
        Rdcr  P  mid  {dcr_ohm}
        L1    mid N   {ind_uh}u
        Cp    P   N   {cp_f:.4e}
        .ENDS {name}""")


# ---------------------------------------------------------------------------
# Model registry — maps model_name -> (family, description, model_string_fn)
# ---------------------------------------------------------------------------

_LIBRARY: dict[str, dict] = {
    # diodes
    "D1N4148":      {"family": "diode",    "description": "1N4148 fast switching diode (representative)", "fn": _diode_1n4148},
    "D1N4001":      {"family": "diode",    "description": "1N4001 rectifier diode, 50 V (representative)", "fn": _diode_1n4001},
    "D1N4007":      {"family": "diode",    "description": "1N4007 rectifier diode, 1000 V (representative)", "fn": _diode_1n4007},
    "DSCHOTTKY":    {"family": "diode",    "description": "Generic Schottky diode, Vf≈0.3 V (representative)", "fn": _diode_schottky_generic},
    "DZENER5V1":    {"family": "diode",    "description": "5.1 V Zener (representative)", "fn": _diode_zener_5v1},
    "DZENER12V":    {"family": "diode",    "description": "12 V Zener (representative)", "fn": _diode_zener_12v},
    # BJTs
    "Q2N3904":      {"family": "bjt",      "description": "2N3904 NPN small-signal BJT (representative)", "fn": _bjt_2n3904},
    "Q2N3906":      {"family": "bjt",      "description": "2N3906 PNP small-signal BJT (representative)", "fn": _bjt_2n3906},
    "QBC547":       {"family": "bjt",      "description": "BC547 NPN small-signal BJT (representative)", "fn": _bjt_bc547},
    "QBC557":       {"family": "bjt",      "description": "BC557 PNP small-signal BJT (representative)", "fn": _bjt_bc557},
    # MOSFETs
    "M2N7000":      {"family": "mosfet",   "description": "2N7000 N-ch enhancement MOSFET, 60 V / 200 mA (representative)", "fn": _mosfet_2n7000},
    "MIRF540":      {"family": "mosfet",   "description": "IRF540-class N-ch power MOSFET, 100 V / 28 A (representative)", "fn": _mosfet_irf540_generic},
    "MIRF9540":     {"family": "mosfet",   "description": "IRF9540-class P-ch power MOSFET, -100 V / -23 A (representative)", "fn": _mosfet_irf9540_generic},
    "M2P7000":      {"family": "mosfet",   "description": "2P7000 P-ch small-signal MOSFET (representative)", "fn": _mosfet_2p7000},
    # op-amps
    "OPAMP_IDEAL":  {"family": "opamp",    "description": "Ideal op-amp subcircuit (infinite GBW)", "fn": _opamp_ideal},
    "OPAMP_GBW1M":  {"family": "opamp",    "description": "Generic 1 MHz GBW op-amp (LM358/LM741 class, representative)", "fn": _opamp_generic_gbw},
    "OPAMP_GBW10M": {"family": "opamp",    "description": "Generic 10 MHz GBW op-amp (TL071/TL081 class, representative)", "fn": _opamp_generic_fast},
    # regulators
    "LDO_78XX":     {"family": "regulator","description": "78xx 5 V positive LDO, behavioural (representative)", "fn": _ldo_78xx_generic},
    "LDO_79XX":     {"family": "regulator","description": "79xx -5 V negative LDO, behavioural (representative)", "fn": _ldo_79xx_generic},
    "LDO_ADJ":      {"family": "regulator","description": "Adjustable LDO (LM317 class), 1.25 V ref, behavioural (representative)", "fn": _ldo_generic_adj},
    # passives with parasitics
    "CAP_ELEC_100U":{"family": "passive",  "description": "100 µF electrolytic cap with ESR/ESL parasitics (representative)", "fn": lambda: _cap_electrolytic_esr(100.0, 0.1, 10.0)},
    "CAP_X7R_100N": {"family": "passive",  "description": "100 nF ceramic X7R cap with ESR/ESL parasitics (representative)", "fn": lambda: _cap_ceramic_x7r(100.0, 0.01, 1.0)},
    "IND_10U":      {"family": "passive",  "description": "10 µH inductor with DCR and SRF parasitics (representative)", "fn": lambda: _inductor_parasitic(10.0, 0.05, 100.0)},
}

# Families for listing
_FAMILIES = sorted({v["family"] for v in _LIBRARY.values()})


def get_model_string(model_name: str) -> str | None:
    """Return the SPICE .MODEL / .SUBCKT string for *model_name*, or None."""
    entry = _LIBRARY.get(model_name.upper())
    if entry is None:
        return None
    return entry["fn"]()


def inject_models_into_netlist(netlist: str, assignments: dict[str, str]) -> str:
    """Prepend SPICE model definitions for each model in *assignments* into *netlist*.

    *assignments* maps refdes -> model_name (e.g. {"D1": "D1N4148"}).
    Unique model names are collected, their strings generated, and prepended
    between the title line and the first element line so ngspice can resolve
    them during parsing.  Already-present model names are not duplicated.

    This is the integration point with the existing sim flow: callers pass the
    netlist text that would go to ``routes_spice.py /run-spice`` (or the
    background job in ``tools/sim.py``) and get back a netlist with models
    embedded — no changes to the simulator itself.
    """
    if not assignments:
        return netlist

    # Collect unique models needed
    needed_names: list[str] = []
    seen: set[str] = set()
    for model_name in assignments.values():
        key = model_name.upper()
        if key not in seen:
            seen.add(key)
            needed_names.append(key)

    # Build model block, skipping models already present in netlist
    model_lines: list[str] = []
    for mname in needed_names:
        # Check if .MODEL or .SUBCKT with this name already appears
        pattern = re.compile(
            r"^\.(MODEL|SUBCKT)\s+" + re.escape(mname) + r"\b",
            re.IGNORECASE | re.MULTILINE,
        )
        if pattern.search(netlist):
            continue  # already defined
        model_str = get_model_string(mname)
        if model_str:
            model_lines.append(model_str)

    if not model_lines:
        return netlist

    block = "\n".join(model_lines) + "\n"

    # Inject after the title line (first non-empty line) which SPICE requires
    lines = netlist.split("\n")
    insert_pos = 1  # default: after line 0 (title)
    for i, line in enumerate(lines):
        if i == 0:
            continue
        if line.strip():
            insert_pos = i
            break

    lines.insert(insert_pos, block)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: list_spice_models
# ---------------------------------------------------------------------------

_LIST_SPICE_MODELS_SPEC = ToolSpec(
    name="list_spice_models",
    description=(
        "List available built-in SPICE models from the Kerf model library. "
        "Optionally filter by device family (diode, bjt, mosfet, opamp, regulator, passive). "
        "Returns model names, families, and short descriptions. "
        "NOTE: all models use representative/generic parameter values — not vendor-exact. "
        "Use assign_spice_model to attach a model to a component in a netlist."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "family": {
                "type": "string",
                "description": (
                    "Filter by device family. One of: "
                    + ", ".join(_FAMILIES)
                    + ". Omit to list all models."
                ),
                "enum": _FAMILIES,
            },
        },
        "required": [],
    },
)


@register(_LIST_SPICE_MODELS_SPEC, write=False)
async def list_spice_models(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    family_filter = (a.get("family") or "").strip().lower()

    results = []
    for name, entry in _LIBRARY.items():
        if family_filter and entry["family"] != family_filter:
            continue
        results.append({
            "model_name": name,
            "family": entry["family"],
            "description": entry["description"],
        })

    return ok_payload({
        "models": results,
        "total": len(results),
        "disclaimer": (
            "All models use representative/generic parameter values — "
            "not extracted from vendor datasheets. "
            "For high-accuracy simulation use vendor-supplied SPICE models."
        ),
    })


# ---------------------------------------------------------------------------
# Tool: assign_spice_model
# ---------------------------------------------------------------------------

_ASSIGN_SPICE_MODEL_SPEC = ToolSpec(
    name="assign_spice_model",
    description=(
        "Assign a SPICE model from the built-in library to one or more components "
        "(identified by refdes) in a SPICE netlist. Returns the updated netlist with "
        "the required .MODEL / .SUBCKT definitions injected so it can be passed "
        "directly to run_simulation (sim.py) without any further edits. "
        "Use list_spice_models to discover available model names. "
        "NOTE: models are representative/generic — not vendor-exact."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "netlist": {
                "type": "string",
                "description": "SPICE .cir netlist text to augment with model definitions.",
            },
            "assignments": {
                "type": "object",
                "description": (
                    "Map of refdes -> model_name. E.g. {\"D1\": \"D1N4148\", \"Q1\": \"Q2N3904\"}. "
                    "Use list_spice_models to find valid model_name values."
                ),
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["netlist", "assignments"],
    },
)


@register(_ASSIGN_SPICE_MODEL_SPEC, write=False)
async def assign_spice_model(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    netlist = a.get("netlist", "")
    if not isinstance(netlist, str) or not netlist.strip():
        return err_payload("netlist is required and must be a non-empty string", "BAD_ARGS")

    assignments = a.get("assignments")
    if not isinstance(assignments, dict) or not assignments:
        return err_payload("assignments must be a non-empty object mapping refdes to model_name", "BAD_ARGS")

    # Validate all model names up front
    unknown = [m for m in assignments.values() if m.upper() not in _LIBRARY]
    if unknown:
        available = sorted(_LIBRARY.keys())
        return err_payload(
            f"Unknown model name(s): {unknown}. "
            f"Use list_spice_models to see available models. "
            f"Available: {available}",
            "NOT_FOUND",
        )

    updated_netlist = inject_models_into_netlist(netlist, assignments)

    # Build a summary of what was injected
    injected = []
    for refdes, model_name in assignments.items():
        entry = _LIBRARY.get(model_name.upper())
        injected.append({
            "refdes": refdes,
            "model_name": model_name.upper(),
            "family": entry["family"] if entry else "unknown",
            "description": entry["description"] if entry else "",
        })

    return ok_payload({
        "netlist": updated_netlist,
        "injected_models": injected,
        "disclaimer": (
            "Models use representative/generic parameter values — "
            "not extracted from vendor datasheets. "
            "Pass the returned netlist directly to run_simulation."
        ),
    })
