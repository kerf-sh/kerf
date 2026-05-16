"""
One-click fab bundle for PCB fabrication houses.

Orchestrates the shipped fab writers (Gerber, Excellon, P&P, BOM, IPC-2581)
into a single zip-ready dict of {filename: bytes} with vendor-specific naming,
a per-vendor README, and an optional IPC-2581 / IPC-D-356A addition.

Supported vendors: jlcpcb, pcbway, oshpark, seeed, allpcb.

Public API
----------
vendor_presets()
    -> dict of vendor_name -> default option dict

fab_bundle(board, vendor='jlcpcb', options={})
    -> dict[str, bytes]  (filename → raw bytes, ready to zip or write)

fab_readme(board, vendor, options)
    -> str  (plain-text README.txt body)

bundle_zip(file_dict)
    -> bytes  (in-memory ZIP via stdlib zipfile)

Never raises — all errors produce empty/fallback output.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from typing import Any

from kerf_electronics.fab.gerber import export_gerber, layer_extension
from kerf_electronics.fab.excellon import export_excellon
from kerf_electronics.fab.pnp import export_pnp, _extract_components
from kerf_electronics.fab.fab_bom import export_fab_bom, _extract_bom_rows
from kerf_electronics.fab.ipc2581 import export_ipc2581


# ─── vendor presets ───────────────────────────────────────────────────────────

def vendor_presets() -> dict[str, dict]:
    """Return default fab options keyed by vendor name.

    Keys common to all vendors:
        stem            - base filename stem
        copper_weight   - e.g. "1oz"
        surface_finish  - e.g. "HASL", "ENIG", "OSP"
        soldermask      - e.g. "green", "black", "blue"
        silkscreen      - e.g. "white", "black"
        board_thickness - e.g. "1.6mm"
        special         - free-form extra instructions string
        include_ipc2581 - bool, whether to include IPC-2581 XML
        include_drl     - bool, whether to include Excellon drill file
    """
    return {
        "jlcpcb": {
            "stem": "board",
            "copper_weight": "1oz",
            "surface_finish": "HASL(with lead)",
            "soldermask": "green",
            "silkscreen": "white",
            "board_thickness": "1.6mm",
            "special": "",
            "include_ipc2581": False,
            "include_drl": True,
        },
        "pcbway": {
            "stem": "board",
            "copper_weight": "1oz",
            "surface_finish": "HASL",
            "soldermask": "green",
            "silkscreen": "white",
            "board_thickness": "1.6mm",
            "special": "",
            "include_ipc2581": True,
            "include_drl": True,
        },
        "oshpark": {
            "stem": "board",
            "copper_weight": "1oz",
            "surface_finish": "ENIG",
            "soldermask": "purple",
            "silkscreen": "white",
            "board_thickness": "1.6mm",
            "special": "OSHPark 4-layer process: use GTL/G2L/G3L/GBL naming",
            "include_ipc2581": False,
            "include_drl": True,
        },
        "seeed": {
            "stem": "board",
            "copper_weight": "1oz",
            "surface_finish": "HASL",
            "soldermask": "green",
            "silkscreen": "white",
            "board_thickness": "1.6mm",
            "special": "",
            "include_ipc2581": False,
            "include_drl": True,
        },
        "allpcb": {
            "stem": "board",
            "copper_weight": "1oz",
            "surface_finish": "HASL",
            "soldermask": "green",
            "silkscreen": "white",
            "board_thickness": "1.6mm",
            "special": "",
            "include_ipc2581": False,
            "include_drl": True,
        },
    }


_KNOWN_VENDORS = set(vendor_presets().keys())


# ─── vendor-specific Gerber layer naming ────────────────────────────────────

# JLCPCB expects files named with a "gerber_" prefix and .gbr extension.
# e.g. gerber_top_copper.gbr, gerber_edge_cuts.gbr
# All other vendors (pcbway, seeed, allpcb) use standard Gerber extensions:
# board.GTL, board.GBL, board.GKO, etc.
# OSHPark uses the same standard extension scheme but expects specific ones:
# board.GTL, board.GTS, board.GTP, board.GTO for top; mirror for bottom.

_JLCPCB_LAYER_NAMES: dict[str, str] = {
    "top_copper": "gerber_top_copper.gbr",
    "bottom_copper": "gerber_bottom_copper.gbr",
    "top_silk": "gerber_top_silkscreen.gbr",
    "bottom_silk": "gerber_bottom_silkscreen.gbr",
    "top_mask": "gerber_top_soldermask.gbr",
    "bottom_mask": "gerber_bottom_soldermask.gbr",
    "top_paste": "gerber_top_paste.gbr",
    "bottom_paste": "gerber_bottom_paste.gbr",
    "edge_cuts": "gerber_board_outline.gbr",
}


def _jlcpcb_layer_filename(layer_name: str) -> str:
    if layer_name in _JLCPCB_LAYER_NAMES:
        return _JLCPCB_LAYER_NAMES[layer_name]
    m = re.match(r"inner_(\d+)$", layer_name)
    if m:
        return f"gerber_inner_{m.group(1)}.gbr"
    return f"gerber_{layer_name}.gbr"


def _standard_layer_filename(stem: str, layer_name: str) -> str:
    """Standard Gerber extension (used by PCBWay, OSHPark, Seeed, AllPCB)."""
    ext = layer_extension(layer_name)
    return f"{stem}.{ext}"


def _remap_gerber_filenames(
    gerber_dict: dict[str, str],
    stem: str,
    vendor: str,
) -> dict[str, bytes]:
    """Rename gerber output keys to vendor-specific filenames."""
    # gerber_dict keys are like "board.GTL", "board.GBL", etc. (standard)
    # Build reverse map: extension -> standard layer name
    ext_to_layer: dict[str, str] = {}
    for layer_name in [
        "top_copper", "bottom_copper", "top_silk", "bottom_silk",
        "top_mask", "bottom_mask", "top_paste", "bottom_paste", "edge_cuts",
    ]:
        ext_to_layer[layer_extension(layer_name)] = layer_name
    # inner layers
    for ext_key in gerber_dict:
        suffix = ext_key.rsplit(".", 1)[-1].upper()
        if suffix not in ext_to_layer:
            m = re.match(r"GL(\d+)$", suffix)
            if m:
                idx = int(m.group(1)) - 1
                ext_to_layer[suffix] = f"inner_{idx}"

    result: dict[str, bytes] = {}
    for fname, content in gerber_dict.items():
        suffix = fname.rsplit(".", 1)[-1].upper()
        layer_name = ext_to_layer.get(suffix, fname.rsplit(".", 1)[-1])

        if vendor == "jlcpcb":
            new_name = _jlcpcb_layer_filename(layer_name)
        else:
            new_name = _standard_layer_filename(stem, layer_name)

        result[new_name] = content.encode("utf-8")

    return result


# ─── vendor-specific drill file naming ───────────────────────────────────────

def _drill_filename(stem: str, vendor: str, plated: bool = True) -> str:
    if vendor == "jlcpcb":
        return "gerber_drill.drl" if plated else "gerber_drill_npth.drl"
    return f"{stem}.DRL" if plated else f"{stem}.NPTH.DRL"


def _remap_drill_filenames(
    drill_dict: dict[str, str],
    stem: str,
    vendor: str,
) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for fname, content in drill_dict.items():
        is_npth = "NPTH" in fname.upper() or "npth" in fname
        new_name = _drill_filename(stem, vendor, plated=not is_npth)
        result[new_name] = content.encode("utf-8")
    return result


# ─── vendor-specific P&P CSV ─────────────────────────────────────────────────

# JLCPCB PnP CSV header: Designator,Mid X,Mid Y,Layer,Rotation
# Standard (PCBWay, Seeed, AllPCB, OSHPark): Designator,Value,Footprint,MidX(mm),MidY(mm),Rotation(deg),Layer,MPN

_JLCPCB_PNP_HEADER = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]


def _jlcpcb_pnp_csv(circuit_json: list[dict]) -> str:
    """Generate JLCPCB-specific PnP CSV from CircuitJSON."""
    components = _extract_components(circuit_json)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_JLCPCB_PNP_HEADER, lineterminator="\n")
    writer.writeheader()
    for c in components:
        writer.writerow({
            "Designator": c["refdes"],
            "Mid X": f"{c['x']:.4f}mm",
            "Mid Y": f"{c['y']:.4f}mm",
            "Layer": "Top" if c["side"] == "top" else "Bottom",
            "Rotation": f"{c['rotation']:.2f}",
        })
    return buf.getvalue()


def _pcbway_pnp_csv(circuit_json: list[dict]) -> str:
    """Generate PCBWay-specific PnP CSV (Ref,Value,Package,X,Y,Rotation,Layer)."""
    components = _extract_components(circuit_json)
    header = ["Ref", "Value", "Package", "X(mm)", "Y(mm)", "Rotation", "Layer"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    for c in components:
        writer.writerow({
            "Ref": c["refdes"],
            "Value": c["value"],
            "Package": c["footprint"],
            "X(mm)": f"{c['x']:.4f}",
            "Y(mm)": f"{c['y']:.4f}",
            "Rotation": f"{c['rotation']:.2f}",
            "Layer": "Top" if c["side"] == "top" else "Bottom",
        })
    return buf.getvalue()


def _pnp_files(
    circuit_json: list[dict],
    stem: str,
    vendor: str,
) -> dict[str, bytes]:
    """Generate vendor-specific PnP CSV(s)."""
    if vendor == "jlcpcb":
        content = _jlcpcb_pnp_csv(circuit_json)
        return {f"{stem}-cpl.csv": content.encode("utf-8")}
    elif vendor == "pcbway":
        content = _pcbway_pnp_csv(circuit_json)
        return {f"{stem}-pnp.csv": content.encode("utf-8")}
    else:
        # OSHPark, Seeed, AllPCB — standard format, both sides
        pnp = export_pnp(circuit_json, stem=stem)
        return {k: v.encode("utf-8") for k, v in pnp.items()}


# ─── vendor-specific BOM CSV ─────────────────────────────────────────────────

# JLCPCB BOM header: Comment,Designator,Footprint,LCSC Part #
# Standard: Item,Qty,Refdes,Value,Footprint,MPN,Manufacturer,Distributor,DistributorPN,Description

_JLCPCB_BOM_HEADER = ["Comment", "Designator", "Footprint", "LCSC Part #"]


def _jlcpcb_bom_csv(circuit_json: list[dict]) -> str:
    """Generate JLCPCB-specific BOM CSV."""
    rows = _extract_bom_rows(circuit_json)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_JLCPCB_BOM_HEADER, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "Comment": r["value"],
            "Designator": r["refdes"],
            "Footprint": r["footprint"],
            "LCSC Part #": r["mpn"],
        })
    return buf.getvalue()


def _bom_files(
    circuit_json: list[dict],
    stem: str,
    vendor: str,
) -> dict[str, bytes]:
    """Generate vendor-specific BOM CSV."""
    if vendor == "jlcpcb":
        content = _jlcpcb_bom_csv(circuit_json)
        return {f"{stem}-bom.csv": content.encode("utf-8")}
    else:
        bom = export_fab_bom(circuit_json, stem=stem)
        return {k: v.encode("utf-8") for k, v in bom.items()}


# ─── board dimension helper ──────────────────────────────────────────────────

def _board_dims(board: list[dict]) -> tuple[float, float]:
    for el in board:
        if el.get("type") in ("pcb_board", "board"):
            w = float(el.get("width", 0.0))
            h = float(el.get("height", 0.0))
            if w > 0 and h > 0:
                return w, h
    return 0.0, 0.0


# ─── vendor README ────────────────────────────────────────────────────────────

_VENDOR_URLS: dict[str, str] = {
    "jlcpcb": "https://jlcpcb.com/",
    "pcbway": "https://www.pcbway.com/",
    "oshpark": "https://oshpark.com/",
    "seeed": "https://www.seeedstudio.com/fusion_pcb.html",
    "allpcb": "https://www.allpcb.com/",
}

_VENDOR_NAMES: dict[str, str] = {
    "jlcpcb": "JLCPCB",
    "pcbway": "PCBWay",
    "oshpark": "OSHPark",
    "seeed": "Seeed Fusion PCB",
    "allpcb": "AllPCB",
}

_SURFACE_FINISH_NOTES: dict[str, str] = {
    "HASL": "Hot Air Solder Leveling (lead-based). Low cost, good solderability.",
    "HASL(with lead)": "Hot Air Solder Leveling (lead-based). Low cost, good solderability.",
    "HASL(lead free)": "Lead-free HASL. RoHS compliant, slightly higher cost.",
    "ENIG": "Electroless Nickel Immersion Gold. Flat surface, excellent for fine-pitch SMD.",
    "OSP": "Organic Solderability Preservative. Flat surface, low cost, limited shelf life.",
    "ITEQ": "ITEQ IT-180A high-Tg laminate process.",
    "hard gold": "Hard gold finger plating. For edge connectors.",
}


def fab_readme(
    board: list[dict],
    vendor: str = "jlcpcb",
    options: dict | None = None,
) -> str:
    """Generate a vendor-specific README.txt for the fab bundle.

    Includes: stackup description, copper weight, surface finish, soldermask
    colour, silkscreen colour, board dimensions, and any special instructions.

    Never raises; returns a best-effort plain-text string.
    """
    if options is None:
        options = {}

    presets = vendor_presets()
    defaults = presets.get(vendor, presets["jlcpcb"])
    opts = {**defaults, **options}

    vendor_name = _VENDOR_NAMES.get(vendor, vendor.upper())
    vendor_url = _VENDOR_URLS.get(vendor, "")

    stem = opts.get("stem", "board")
    copper_weight = opts.get("copper_weight", "1oz")
    surface_finish = str(opts.get("surface_finish", "HASL"))
    soldermask = opts.get("soldermask", "green")
    silkscreen = opts.get("silkscreen", "white")
    board_thickness = opts.get("board_thickness", "1.6mm")
    special = opts.get("special", "")

    w, h = _board_dims(board)
    dims_str = f"{w:.1f} x {h:.1f} mm" if (w > 0 and h > 0) else "unknown dimensions"

    sf_note = _SURFACE_FINISH_NOTES.get(surface_finish, surface_finish)

    lines = [
        f"{vendor_name} Fabrication Package",
        "=" * 40,
        "",
        f"Project stem : {stem}",
        f"Vendor       : {vendor_name}",
        f"Upload URL   : {vendor_url}",
        "",
        "─── Board Specifications ───────────────────",
        f"Board dimensions : {dims_str}",
        f"Board thickness  : {board_thickness}",
        f"Copper weight    : {copper_weight}  (outer layers)",
        f"Surface finish   : {surface_finish}",
        f"Soldermask       : {soldermask}",
        f"Silkscreen       : {silkscreen}",
        "",
        "─── Surface Finish Notes ───────────────────",
        sf_note,
        "",
        "─── Stackup ────────────────────────────────",
        "Layer 1 (Top)    : Signal / Component side",
        "Prepreg / Core",
        "Layer 2 (Bottom) : Signal / GND plane",
        "(For multi-layer boards, inner layers follow the same copper weight",
        " unless otherwise specified in your order.)",
        "",
        "─── File Contents ──────────────────────────",
    ]

    if vendor == "jlcpcb":
        lines += [
            "gerber_top_copper.gbr        Top copper layer",
            "gerber_bottom_copper.gbr     Bottom copper layer",
            "gerber_top_silkscreen.gbr    Top silkscreen",
            "gerber_bottom_silkscreen.gbr Bottom silkscreen",
            "gerber_top_soldermask.gbr    Top soldermask",
            "gerber_bottom_soldermask.gbr Bottom soldermask",
            "gerber_board_outline.gbr     Board outline / edge cuts",
            "gerber_drill.drl             Drilled holes (Excellon)",
            f"{stem}-bom.csv              Bill of Materials (JLCPCB format)",
            f"{stem}-cpl.csv              Component placement list (JLCPCB format)",
        ]
    elif vendor == "oshpark":
        lines += [
            f"{stem}.GTL  Top copper",
            f"{stem}.GBL  Bottom copper",
            f"{stem}.GTS  Top soldermask",
            f"{stem}.GBS  Bottom soldermask",
            f"{stem}.GTO  Top silkscreen",
            f"{stem}.GBO  Bottom silkscreen",
            f"{stem}.GTP  Top paste",
            f"{stem}.GKO  Board outline",
            f"{stem}.DRL  Drilled holes (Excellon)",
        ]
    elif vendor == "pcbway":
        lines += [
            f"{stem}.GTL  Top copper",
            f"{stem}.GBL  Bottom copper",
            f"{stem}.GTS  Top soldermask",
            f"{stem}.GBS  Bottom soldermask",
            f"{stem}.GTO  Top silkscreen",
            f"{stem}.GBO  Bottom silkscreen",
            f"{stem}.GKO  Board outline",
            f"{stem}.DRL  Drilled holes (Excellon)",
            f"{stem}-bom.csv  Bill of Materials",
            f"{stem}-pnp.csv  Pick and Place",
        ]
    else:
        lines += [
            "Gerber RS-274X files (.GTL, .GBL, .GTS, .GBS, .GTO, .GBO, .GKO)",
            f"{stem}.DRL  Excellon drill file",
            f"{stem}-bom.csv  Bill of Materials",
            f"{stem}-top-pnp.csv / {stem}-bottom-pnp.csv  Pick and Place",
        ]

    if opts.get("include_ipc2581"):
        lines.append(f"{stem}.xml  IPC-2581 data package")

    lines += [
        "",
        "─── Upload Instructions ─────────────────────",
    ]

    if vendor == "jlcpcb":
        lines += [
            "1. Zip all gerber_*.gbr + gerber_drill.drl files.",
            "2. Upload the zip at https://jlcpcb.com/ → 'Instant Quote'.",
            "3. For PCBA: also upload the BOM CSV and CPL CSV in the SMT Assembly step.",
            "4. Verify layer count, copper weight, and surface finish in the order form.",
        ]
    elif vendor == "pcbway":
        lines += [
            "1. Zip all .GTL/.GBL/.GTS/.GBS/.GTO/.GBO/.GKO/.DRL files.",
            "2. Upload at https://www.pcbway.com/ → 'PCB Instant Quote'.",
            "3. For assembly: upload BOM and PnP CSVs separately.",
            "4. Check IPC-2581 XML upload option if your order supports it.",
        ]
    elif vendor == "oshpark":
        lines += [
            "1. Zip all .GTL/.GBL/.GTS/.GBS/.GTP/.GBO/.GKO/.DRL files.",
            "2. Upload at https://oshpark.com/ — drag the zip directly.",
            "3. OSHPark uses the Gerber extensions to detect layers automatically.",
        ]
    else:
        lines += [
            "1. Zip all Gerber + drill files.",
            f"2. Upload at {vendor_url}",
            "3. Include BOM and PnP CSVs for assembly orders.",
        ]

    if special:
        lines += [
            "",
            "─── Special Instructions ───────────────────",
            special,
        ]

    lines += [
        "",
        "─────────────────────────────────────────────",
        "Generated by Kerf Electronics",
        "https://kerf.app",
    ]

    return "\n".join(lines) + "\n"


# ─── core bundle assembler ───────────────────────────────────────────────────

def fab_bundle(
    board: list[dict],
    vendor: str = "jlcpcb",
    options: dict | None = None,
) -> dict[str, bytes]:
    """Assemble a complete fab bundle for the given vendor.

    Args:
        board:   CircuitJSON array (the tscircuit PCB data model).
        vendor:  One of 'jlcpcb', 'pcbway', 'oshpark', 'seeed', 'allpcb'.
                 Defaults to 'jlcpcb'.
        options: Override dict merged on top of vendor_presets()[vendor].
                 Supported keys: stem, copper_weight, surface_finish,
                 soldermask, silkscreen, board_thickness, special,
                 include_ipc2581, include_drl.

    Returns:
        dict mapping filename (str) → raw file bytes.
        Returns {} (never raises) if vendor is unsupported or board is invalid.

    Unsupported vendor:
        Returns {'ERROR': b'unsupported vendor: <name>'}.
    """
    if not isinstance(board, list):
        board = []

    # Normalise vendor string
    vendor_key = str(vendor).lower().strip()
    if vendor_key not in _KNOWN_VENDORS:
        return {"ERROR": f"unsupported vendor: {vendor}".encode()}

    presets = vendor_presets()
    defaults = presets[vendor_key]
    opts: dict = {**defaults, **(options or {})}

    stem: str = str(opts.get("stem", "board") or "board")

    result: dict[str, bytes] = {}

    # ── Gerber layers ─────────────────────────────────────────────────────────
    try:
        gerber_str = export_gerber(board, stem=stem)
        gerber_bytes = _remap_gerber_filenames(gerber_str, stem, vendor_key)
        result.update(gerber_bytes)
    except Exception:
        pass

    # ── Drill files ───────────────────────────────────────────────────────────
    if opts.get("include_drl", True):
        try:
            drill_str = export_excellon(board, stem=stem)
            drill_bytes = _remap_drill_filenames(drill_str, stem, vendor_key)
            result.update(drill_bytes)
        except Exception:
            pass

    # ── Pick-and-place ────────────────────────────────────────────────────────
    try:
        pnp = _pnp_files(board, stem, vendor_key)
        result.update(pnp)
    except Exception:
        pass

    # ── BOM ───────────────────────────────────────────────────────────────────
    try:
        bom = _bom_files(board, stem, vendor_key)
        result.update(bom)
    except Exception:
        pass

    # ── IPC-2581 (optional) ───────────────────────────────────────────────────
    if opts.get("include_ipc2581", False):
        try:
            ipc_str = export_ipc2581(board, stem=stem)
            for k, v in ipc_str.items():
                result[k] = v.encode("utf-8")
        except Exception:
            pass

    # ── README ────────────────────────────────────────────────────────────────
    try:
        readme_text = fab_readme(board, vendor=vendor_key, options=opts)
        result["README.txt"] = readme_text.encode("utf-8")
    except Exception:
        pass

    return result


# ─── zip packager ────────────────────────────────────────────────────────────

def bundle_zip(file_dict: dict[str, bytes]) -> bytes:
    """Pack a {filename: bytes} dict into a ZIP archive (in memory).

    Uses stdlib zipfile with ZIP_DEFLATED compression.
    Files are stored in sorted order for reproducible output.
    Never raises — returns empty zip bytes on failure.
    """
    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for fname in sorted(file_dict.keys()):
                data = file_dict[fname]
                if isinstance(data, str):
                    data = data.encode("utf-8")
                zf.writestr(fname, data)
    except Exception:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            pass  # return empty zip
    return buf.getvalue()
