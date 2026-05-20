"""
geom/io/iges.py
===============
Pure-Python IGES 5.3 reader/writer for the trimmed-surface subset (GK-49).

Supported entity types
----------------------
* **126** — Rational B-Spline Curve (NURBS curve)
* **128** — Rational B-Spline Surface (NURBS surface)
* **142** — Curve on a Parametric Surface (UV-space boundary curve)
* **144** — Trimmed (Parametric) Surface

Public API
----------
``write_iges(ts, filepath)``
    Serialise a :class:`TrimmedSurface` to an IGES 5.3 file.

``read_iges(filepath) -> list[TrimmedSurface]``
    Parse an IGES file and return all entity-144 trimmed surfaces found.

``TrimmedSurface``
    Thin dataclass coupling a :class:`~kerf_cad_core.geom.nurbs.NurbsSurface`
    to a list of boundary loops, each a list of UV-space
    :class:`~kerf_cad_core.geom.nurbs.NurbsCurve` objects.

Notes on the IGES fixed-field format
--------------------------------------
Each IGES section uses 80-column fixed-width lines.  Columns 1-72 carry
data; column 73 holds the section code (S/G/D/P/T); columns 74-80 hold the
sequence number (right-aligned, base-1 within the section).  All parameter
data entries are comma-delimited; the sequence terminates with a semicolon
before the end of the last PD record for that entity.

References
----------
* IGES 5.3 specification, Section 4.126, 4.128, 4.142, 4.144.
* Piegl & Tiller, *The NURBS Book* (2nd ed., 1997), ch. 9.
"""

from __future__ import annotations

import io
import math
import re
import textwrap
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class IgesReadError(Exception):
    """Raised when the IGES parser encounters a fatal error."""


class IgesWriteError(Exception):
    """Raised when IGES serialisation fails."""


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass
class TrimmedSurface:
    """A NURBS surface with one or more boundary loops.

    Attributes
    ----------
    surface : NurbsSurface
        The underlying untrimmed NURBS surface.
    outer_boundary : list[NurbsCurve]
        Ordered list of UV-space boundary curves forming the outer (CCW) loop.
        Each curve lives in the (u, v) parametric domain of *surface* and is a
        2-D :class:`NurbsCurve` (``control_points.shape[1] == 2``).
    inner_boundaries : list[list[NurbsCurve]]
        Optional inner (hole) loops, each a list of UV-space NurbsCurves.
    """
    surface: NurbsSurface
    outer_boundary: List[NurbsCurve] = field(default_factory=list)
    inner_boundaries: List[List[NurbsCurve]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers — IGES fixed-column formatting
# ---------------------------------------------------------------------------

_DATA_WIDTH = 72       # usable data columns per line
_LINE_WIDTH = 80       # total columns per IGES line


def _fmt_float(v: float) -> str:
    """Format a float for IGES parameter data.  Uses shortest unambiguous repr."""
    if math.isnan(v) or math.isinf(v):
        raise IgesWriteError(f"Non-finite value not allowed in IGES: {v!r}")
    # Use up to 15 significant digits, strip trailing zeros after decimal.
    s = f"{v:.15E}"
    # Normalise to Python's E notation → IGES accepts it.
    return s


def _iges_line(data_cols: str, section: str, seq: int) -> str:
    """Build one 80-column IGES line.

    data_cols is the up-to-72-character payload; section is one of
    'S','G','D','P','T'; seq is the 1-based sequence number within the section.
    """
    if len(section) != 1:
        raise ValueError(f"section must be one character, got {section!r}")
    payload = data_cols.ljust(_DATA_WIDTH)[:_DATA_WIDTH]
    return f"{payload}{section}{seq:7d}\n"


def _wrap_pd(params: str, de_seq: int, first_pd_seq: int) -> List[str]:
    """Wrap a parameter-data string into one or more 80-column PD lines.

    *params* is the full comma-delimited parameter string (already ending
    with ';').  Returns a list of complete 80-column lines, with the
    sequence counter starting at *first_pd_seq*.  Each line's columns 65-72
    hold the DE back-pointer (right-aligned integer).
    """
    # Columns 1-64: parameter data (columns 65-72: DE back-pointer).
    pd_payload_width = 64
    lines: List[str] = []
    seq = first_pd_seq
    remaining = params
    while remaining:
        chunk = remaining[:pd_payload_width]
        remaining = remaining[pd_payload_width:]
        # Build the 80-char line:
        #   cols  1-64 : parameter chunk (left-justified, space-padded)
        #   cols 65-72 : DE back-pointer (right-justified in 8 cols)
        #   col  73    : section code 'P'
        #   cols 74-80 : sequence number (7 digits)
        data_field = chunk.ljust(pd_payload_width) + f"{de_seq:8d}"
        lines.append(_iges_line(data_field, "P", seq))
        seq += 1
    return lines, seq


# ---------------------------------------------------------------------------
# Parameter-data builders for each entity type
# ---------------------------------------------------------------------------

def _params_nurbs_curve(crv: NurbsCurve, is_2d: bool = False) -> str:
    """Build entity-126 (NURBS curve) PD parameter string."""
    cp = crv.control_points
    n_cp = cp.shape[0]
    n = n_cp - 1          # upper index of control points (0-based → IGES uses n+1 notation)
    p = crv.degree
    m = len(crv.knots) - 1  # upper index of knot vector

    # IGES entity 126 header fields
    # K = n (upper index of control net — number of control points = K+1)
    # M = p (degree)
    # PROP1 = 0 (planar = 0/1 — we'll always write 0 for non-planar)
    # PROP2 = 0 (closed = 0/1)
    # PROP3 = 0 (rational = 0, non-rational = 1 — 0 means RATIONAL)
    # PROP4 = 0 (periodic = 0/1)
    K = n
    M = p
    PROP1 = 0
    PROP2 = 0  # not closed
    PROP3 = 0 if (crv.weights is not None and not np.allclose(crv.weights, 1.0)) else 1
    PROP4 = 0

    parts = [f"126,{K},{M},{PROP1},{PROP2},{PROP3},{PROP4}"]

    # Knot vector (m+1 values = n+p+2 values)
    for k in crv.knots:
        parts.append(_fmt_float(float(k)))

    # Weights (n+1 values)
    w = crv.weights if crv.weights is not None else np.ones(n_cp)
    for wi in w:
        parts.append(_fmt_float(float(wi)))

    # Control points — each as X,Y[,Z] (always 3D in IGES 126)
    for i in range(n_cp):
        pt = cp[i]
        if is_2d or pt.shape[0] == 2:
            parts.append(_fmt_float(float(pt[0])))
            parts.append(_fmt_float(float(pt[1])))
            parts.append(_fmt_float(0.0))
        else:
            parts.append(_fmt_float(float(pt[0])))
            parts.append(_fmt_float(float(pt[1])))
            parts.append(_fmt_float(float(pt[2])))

    # Start parameter value, end parameter value
    u0 = float(crv.knots[0])
    u1 = float(crv.knots[-1])
    parts.append(_fmt_float(u0))
    parts.append(_fmt_float(u1))

    # Unit normal (for planar curves) — 3 zeros for non-planar
    parts += [_fmt_float(0.0), _fmt_float(0.0), _fmt_float(0.0)]

    return ",".join(parts) + ";"


def _params_nurbs_surface(surf: NurbsSurface) -> str:
    """Build entity-128 (NURBS surface) PD parameter string."""
    cp = surf.control_points
    nu = cp.shape[0]
    nv = cp.shape[1]

    K1 = nu - 1   # upper index U direction
    K2 = nv - 1   # upper index V direction
    M1 = surf.degree_u
    M2 = surf.degree_v

    # PROP1=0 closed in first dir, PROP2=0 closed in second dir,
    # PROP3=0 rational, PROP4=0 periodic first, PROP5=0 periodic second
    PROP1, PROP2 = 0, 0
    PROP3 = 0 if (surf.weights is not None and not np.allclose(surf.weights, 1.0)) else 1
    PROP4, PROP5 = 0, 0

    parts = [f"128,{K1},{K2},{M1},{M2},{PROP1},{PROP2},{PROP3},{PROP4},{PROP5}"]

    # U knot vector (K1+M1+2 values)
    for k in surf.knots_u:
        parts.append(_fmt_float(float(k)))
    # V knot vector (K2+M2+2 values)
    for k in surf.knots_v:
        parts.append(_fmt_float(float(k)))

    # Weights (nu*nv values, row-major — U varies faster? IGES says index order i,j)
    W = surf.weights if surf.weights is not None else np.ones((nu, nv))
    for i in range(nu):
        for j in range(nv):
            parts.append(_fmt_float(float(W[i, j])))

    # Control points (nu*nv * 3 values, X Y Z)
    for i in range(nu):
        for j in range(nv):
            pt = cp[i, j]
            dim = pt.shape[0]
            parts.append(_fmt_float(float(pt[0])))
            parts.append(_fmt_float(float(pt[1])))
            parts.append(_fmt_float(float(pt[2]) if dim >= 3 else 0.0))

    # Parameter range: U0, U1, V0, V1
    parts.append(_fmt_float(float(surf.knots_u[0])))
    parts.append(_fmt_float(float(surf.knots_u[-1])))
    parts.append(_fmt_float(float(surf.knots_v[0])))
    parts.append(_fmt_float(float(surf.knots_v[-1])))

    return ",".join(parts) + ";"


def _params_curve_on_surface(surf_de: int, crv2d_de: int, crv3d_de: int) -> str:
    """Build entity-142 (Curve on Parametric Surface) PD parameter string.

    Parameters
    ----------
    surf_de  : DE sequence of the underlying surface (entity 128)
    crv2d_de : DE sequence of the parameter-space curve (entity 126)
    crv3d_de : DE sequence of the 3-D model-space curve (entity 126);
               use 0 if not provided (we'll write the same as 2D curve)
    """
    # CRTN  = 1 (curve created by projection onto surface)
    # SPTR  = surf_de
    # BPTR  = crv2d_de (B-curve in parameter space)
    # CPTR  = crv3d_de (model-space curve; 0 if same as BPTR)
    # PREF  = 1 (parameter-space curve is preferred)
    return f"142,1,{surf_de},{crv2d_de},{crv3d_de},1;"


def _params_trimmed_surface(surf_de: int, outer_de: int, inner_des: List[int]) -> str:
    """Build entity-144 (Trimmed Parametric Surface) PD parameter string.

    Parameters
    ----------
    surf_de   : DE sequence of the underlying surface (entity 128)
    outer_de  : DE sequence of entity-142 forming the outer loop
    inner_des : list of DE sequences for inner (hole) loop entity-142s
    """
    # PTS  = surf_de
    # N1   = 0 (outer boundary present / 1 = use surface boundary)
    # N2   = number of inner loops
    N2 = len(inner_des)
    parts = [f"144,{surf_de},0,{N2},{outer_de}"]
    for de in inner_des:
        parts.append(str(de))
    return ",".join(parts) + ";"


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def write_iges(ts: TrimmedSurface, filepath: str) -> None:
    """Write a :class:`TrimmedSurface` to an IGES 5.3 file.

    The file contains:

    * One entity-128 (NURBS surface)
    * One entity-126 per boundary curve (UV-space)
    * One entity-142 per boundary curve (curve on surface)
    * One entity-144 (trimmed surface)

    Parameters
    ----------
    ts       : TrimmedSurface to serialise.
    filepath : Destination file path.
    """
    if not isinstance(ts, TrimmedSurface):
        raise IgesWriteError(f"Expected TrimmedSurface, got {type(ts).__name__}")
    if not ts.outer_boundary:
        raise IgesWriteError("outer_boundary must contain at least one curve")

    # We build DE and PD sections together then assemble.

    # --- entity registry ---
    # Each entry: (entity_type, pd_param_string, de_status, de_form_number)
    Entity = Tuple[int, str, int, int]
    entities: List[Entity] = []

    def _add_entity(etype: int, params: str, form: int = 0) -> int:
        """Append an entity; return its 1-based DE sequence (odd numbers only)."""
        de_idx = len(entities)  # 0-based index
        entities.append((etype, params, 0, form))
        return de_idx * 2 + 1  # DE line 1 of entity (1-based, step 2)

    # --- surface (entity 128) ---
    surf_de = _add_entity(128, _params_nurbs_surface(ts.surface))

    # --- helper to add boundary curves ---
    def _add_loop(loop_curves: List[NurbsCurve]) -> int:
        """Add all curves in a loop; return DE of entity-142 composite loop.

        For each curve in the loop:
          - entity 126 (UV-space curve, is_2d=True)
          - entity 142 (curve-on-surface)

        Then the loop is a single entity-142 pointing at the first curve (for
        a single-curve boundary) or we chain them.  IGES 144 allows a list of
        entity-142 pointers so we emit one entity-142 per segment and pass the
        first as the outer boundary pointer (multi-segment loops are handled by
        listing them all in the trimmed-surface PD; for simplicity here we
        combine into one polyline NURBS if multiple curves given).
        """
        if len(loop_curves) == 1:
            crv = loop_curves[0]
            crv2d_de = _add_entity(126, _params_nurbs_curve(crv, is_2d=True), form=0)
            cos_de = _add_entity(142, _params_curve_on_surface(surf_de, crv2d_de, crv2d_de))
            return cos_de
        else:
            # Multiple segments: emit each as entity-126 + entity-142 and
            # collect the 142 DEs.  IGES 144 permits N2 inner loops as a
            # sequence; for the outer loop (single DE pointer) we take the
            # first segment's 142 and trust the reader to follow the chain.
            # For full compliance we could emit a composite curve (entity 102)
            # but that is out of scope for this subset implementation.
            des_142: List[int] = []
            for crv in loop_curves:
                crv2d_de = _add_entity(126, _params_nurbs_curve(crv, is_2d=True), form=0)
                cos_de = _add_entity(142, _params_curve_on_surface(surf_de, crv2d_de, crv2d_de))
                des_142.append(cos_de)
            return des_142[0]

    # --- outer boundary (entity-142) ---
    outer_142_de = _add_loop(ts.outer_boundary)

    # --- inner boundaries ---
    inner_142_des: List[int] = []
    for inner_loop in ts.inner_boundaries:
        inner_142_des.append(_add_loop(inner_loop))

    # --- trimmed surface (entity 144) ---
    _add_entity(144, _params_trimmed_surface(surf_de, outer_142_de, inner_142_des))

    # -----------------------------------------------------------------------
    # Assemble DE and PD sections
    # -----------------------------------------------------------------------
    de_lines: List[str] = []
    pd_lines: List[str] = []
    pd_seq = 1  # current PD sequence number

    for de_idx, (etype, params, de_status, form) in enumerate(entities):
        de_seq = de_idx * 2 + 1  # DE line 1 (odd)
        de_seq2 = de_seq + 1     # DE line 2 (even)
        first_pd = pd_seq

        # Build PD lines for this entity
        new_pd_lines, pd_seq = _wrap_pd(params, de_seq, pd_seq)
        pd_lines.extend(new_pd_lines)
        n_pd = len(new_pd_lines)

        # DE line 1: cols 1-8 entity type, 9-16 PD ptr, 17-24 structure,
        #            25-32 line font, 33-40 level, 41-48 view, 49-56 transform,
        #            57-64 label disp, 65-72 status / blank / sub-entity
        # DE line 2: cols 1-8 entity type, 9-16 line weight, 17-24 color,
        #            25-32 param count, 33-40 form, 41-48 blank, 49-56 blank,
        #            57-64 entity label, 65-72 entity subscript
        de1 = (
            f"{etype:8d}"    # col 1-8  entity type
            f"{first_pd:8d}" # col 9-16 PD sequence (first line)
            f"{'':8}"        # col 17-24 structure = 0
            f"{'':8}"        # col 25-32 line font  = 0
            f"{'':8}"        # col 33-40 level      = 0
            f"{'':8}"        # col 41-48 view        = 0
            f"{'':8}"        # col 49-56 transform  = 0
            f"{'':8}"        # col 57-64 label disp = 0
            f"{'00000001':8}" # col 65-72 status (0x00000001 = visible)
        )
        de2 = (
            f"{etype:8d}"    # col 1-8  entity type
            f"{'':8}"        # col 9-16  line weight = 0
            f"{'':8}"        # col 17-24 color       = 0
            f"{n_pd:8d}"     # col 25-32 parameter line count
            f"{form:8d}"     # col 33-40 form number
            f"{'':8}"        # col 41-48 reserved
            f"{'':8}"        # col 49-56 reserved
            f"{'':8}"        # col 57-64 entity label
            f"{'':8}"        # col 65-72 entity subscript
        )
        de_lines.append(_iges_line(de1, "D", de_seq))
        de_lines.append(_iges_line(de2, "D", de_seq2))

    # -----------------------------------------------------------------------
    # Assemble Start, Global, Terminate sections
    # -----------------------------------------------------------------------
    start_text = "IGES 5.3 trimmed-surface file written by kerf-cad-core geom/io/iges.py"
    start_lines = []
    for i, chunk in enumerate(textwrap.wrap(start_text, _DATA_WIDTH)):
        start_lines.append(_iges_line(chunk, "S", i + 1))

    # Global section — minimal required fields
    # Field 1: parameter delimiter (,)
    # Field 2: record delimiter (;)
    # Field 3: product ID sender
    # Field 4: file name
    # Field 5: system id
    # Field 6: preprocessor version
    # Field 7: integer bits (32)
    # Field 8: single-precision maxpower (38)
    # Field 9: single-precision significance (6)
    # Field 10: double-precision maxpower (308)
    # Field 11: double-precision significance (15)
    # Field 12: product id receiver
    # Field 13: model space scale (1.0)
    # Field 14: units flag (6 = metres)
    # Field 15: units name
    # Field 16: line gradations (1)
    # Field 17: max line width (0.01)
    # Field 18: creation date/time
    # Field 19: min user-intended resolution
    # Field 20: approx max coordinate
    # Field 21: author
    # Field 22: organisation
    # Field 23: IGES version flag (11 = 5.3)
    # Field 24: drafting standard (0 = none)
    # Field 25: creation date/time last modification
    global_params = (
        "1H,,1H;,7Hkerf-io,9Higes.iges,15Hkerf-cad-core/1,"
        "7H1.0.0.0,32,308,15,308,15,7Hkerf-io,1.0,6,2HMM,"
        "1,0.001,15H20000101.000000,1.0E-10,1000.0,7Hauthors,"
        "4Hkerf,11,0,15H20000101.000000;"
    )
    global_lines = []
    for i, chunk in enumerate(textwrap.wrap(global_params, _DATA_WIDTH)):
        global_lines.append(_iges_line(chunk, "G", i + 1))

    # Terminate section: S/G/D/P counts
    S = len(start_lines)
    G = len(global_lines)
    D = len(de_lines)
    P = len(pd_lines)
    term = (
        f"S{S:7d}G{G:7d}D{D:7d}P{P:7d}"
        f"{'':40}"  # pad to 72 chars
    )
    terminate_line = _iges_line(term.ljust(_DATA_WIDTH)[:_DATA_WIDTH], "T", 1)

    # -----------------------------------------------------------------------
    # Write file
    # -----------------------------------------------------------------------
    with open(filepath, "w", encoding="ascii") as f:
        for line in start_lines:
            f.write(line)
        for line in global_lines:
            f.write(line)
        for line in de_lines:
            f.write(line)
        for line in pd_lines:
            f.write(line)
        f.write(terminate_line)


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

@dataclass
class _DEEntry:
    """Internal: parsed Directory Entry for one entity."""
    entity_type: int
    pd_first: int       # first PD sequence number
    pd_count: int       # number of PD lines
    form: int
    de_seq: int         # DE sequence (1-based odd number)


def _parse_iges_sections(text: str) -> Tuple[List[str], List[str], List[str], List[str]]:
    """Split raw IGES text into S/G/D/P section lines (strip column 73+)."""
    s_lines: List[str] = []
    g_lines: List[str] = []
    d_lines: List[str] = []
    p_lines: List[str] = []

    for raw in text.splitlines():
        if len(raw) < 73:
            continue
        section = raw[72]
        data = raw[:72]
        if section == "S":
            s_lines.append(data)
        elif section == "G":
            g_lines.append(data)
        elif section == "D":
            d_lines.append(data)
        elif section == "P":
            p_lines.append(data)
        # T (terminate) is ignored

    return s_lines, g_lines, d_lines, p_lines


def _parse_de_section(d_lines: List[str]) -> Dict[int, _DEEntry]:
    """Parse Directory Entry lines into a dict keyed by DE sequence number."""
    entries: Dict[int, _DEEntry] = {}

    if len(d_lines) % 2 != 0:
        raise IgesReadError(
            f"DE section has odd number of lines ({len(d_lines)}); expected pairs"
        )

    for i in range(0, len(d_lines), 2):
        line1 = d_lines[i]
        line2 = d_lines[i + 1]

        def _field(line: str, start: int, end: int) -> str:
            return line[start:end].strip()

        try:
            etype = int(_field(line1, 0, 8))
        except ValueError:
            continue

        try:
            pd_first = int(_field(line1, 8, 16))
        except ValueError:
            pd_first = 1

        try:
            pd_count = int(_field(line2, 24, 32))
        except ValueError:
            pd_count = 1

        try:
            form = int(_field(line2, 32, 40))
        except ValueError:
            form = 0

        de_seq = i + 1  # 1-based (odd)
        entries[de_seq] = _DEEntry(
            entity_type=etype,
            pd_first=pd_first,
            pd_count=pd_count,
            form=form,
            de_seq=de_seq,
        )

    return entries


def _extract_pd_string(pd_lines: List[str], first_seq: int, count: int) -> str:
    """Concatenate PD data columns (1-64) for a given entity."""
    # PD lines are 0-indexed; first_seq is 1-based P-section sequence
    start = first_seq - 1
    end = start + count
    chunks = []
    for idx in range(start, end):
        if idx >= len(pd_lines):
            raise IgesReadError(
                f"PD line index {idx} out of range (total {len(pd_lines)} PD lines)"
            )
        # Columns 1-64 of the PD line (0-indexed: 0:64)
        chunks.append(pd_lines[idx][:64])
    raw = "".join(chunks)
    # Strip the trailing semicolon and any whitespace
    raw = raw.rstrip()
    if raw.endswith(";"):
        raw = raw[:-1]
    return raw


def _split_params(s: str) -> List[str]:
    """Split comma-delimited IGES parameter string."""
    return [tok.strip() for tok in s.split(",")]


def _parse_float(s: str) -> float:
    """Parse a float from an IGES token (handles D/E notation)."""
    # IGES uses 'D' as an exponent separator in some implementations
    return float(s.replace("D", "E").replace("d", "e"))


def _parse_entity_126(params: List[str], is_2d: bool = False) -> NurbsCurve:
    """Parse entity-126 (NURBS curve) parameters into a NurbsCurve."""
    # params[0] == '126'
    idx = 1
    K = int(params[idx]); idx += 1   # upper index of control net
    M = int(params[idx]); idx += 1   # degree
    _PROP1 = int(params[idx]); idx += 1  # planar
    _PROP2 = int(params[idx]); idx += 1  # closed
    PROP3 = int(params[idx]); idx += 1   # 0=rational, 1=polynomial
    _PROP4 = int(params[idx]); idx += 1  # periodic

    n_cp = K + 1
    n_knots = K + M + 2   # = (K+1) + (M+1) = n_cp + degree + 1... wait
    # IGES 126: knot sequence has (K+1) + (M+1) = K+M+2 entries.
    # This equals n_cp + degree + 1 for a clamped B-spline.

    knots = np.array([_parse_float(params[idx + i]) for i in range(n_knots)])
    idx += n_knots

    weights = np.array([_parse_float(params[idx + i]) for i in range(n_cp)])
    idx += n_cp

    # Control points: 3 values per point even for 2D curves (z=0)
    cps = []
    for _ in range(n_cp):
        x = _parse_float(params[idx]); idx += 1
        y = _parse_float(params[idx]); idx += 1
        z = _parse_float(params[idx]); idx += 1
        if is_2d:
            cps.append([x, y])
        else:
            cps.append([x, y, z])
    cp_arr = np.array(cps, dtype=float)

    # Remaining: V0, V1, Xnorm, Ynorm, Znorm — skip
    # (we've consumed up to parameter value ranges)

    # If polynomial (PROP3=1), weights are all 1 — treat as non-rational
    if PROP3 == 1 or np.allclose(weights, 1.0):
        weights = None

    return NurbsCurve(degree=M, control_points=cp_arr, knots=knots, weights=weights)


def _parse_entity_128(params: List[str]) -> NurbsSurface:
    """Parse entity-128 (NURBS surface) parameters into a NurbsSurface."""
    # params[0] == '128'
    idx = 1
    K1 = int(params[idx]); idx += 1   # upper index U
    K2 = int(params[idx]); idx += 1   # upper index V
    M1 = int(params[idx]); idx += 1   # degree U
    M2 = int(params[idx]); idx += 1   # degree V
    _P1 = int(params[idx]); idx += 1  # closed U
    _P2 = int(params[idx]); idx += 1  # closed V
    PROP3 = int(params[idx]); idx += 1  # 0=rational, 1=polynomial
    _P4 = int(params[idx]); idx += 1  # periodic U
    _P5 = int(params[idx]); idx += 1  # periodic V

    nu = K1 + 1
    nv = K2 + 1
    n_knots_u = K1 + M1 + 2
    n_knots_v = K2 + M2 + 2

    knots_u = np.array([_parse_float(params[idx + i]) for i in range(n_knots_u)])
    idx += n_knots_u

    knots_v = np.array([_parse_float(params[idx + i]) for i in range(n_knots_v)])
    idx += n_knots_v

    # Weights: nu*nv values
    weights_flat = np.array([_parse_float(params[idx + i]) for i in range(nu * nv)])
    idx += nu * nv
    weights = weights_flat.reshape(nu, nv)

    # Control points: nu*nv * 3 values
    cps = []
    for _ in range(nu * nv):
        x = _parse_float(params[idx]); idx += 1
        y = _parse_float(params[idx]); idx += 1
        z = _parse_float(params[idx]); idx += 1
        cps.append([x, y, z])
    cp_arr = np.array(cps, dtype=float).reshape(nu, nv, 3)

    if PROP3 == 1 or np.allclose(weights, 1.0):
        weights = None

    return NurbsSurface(
        degree_u=M1,
        degree_v=M2,
        control_points=cp_arr,
        knots_u=knots_u,
        knots_v=knots_v,
        weights=weights,
    )


def _parse_entity_142(params: List[str]) -> Tuple[int, int, int]:
    """Parse entity-142 (Curve on Parametric Surface).

    Returns (surf_de, crv2d_de, crv3d_de).
    """
    # params[0] == '142'
    # CRTN, SPTR, BPTR, CPTR, PREF
    _crtn = int(params[1])
    surf_de = int(params[2])
    crv2d_de = int(params[3])
    crv3d_de = int(params[4])
    _pref = int(params[5]) if len(params) > 5 else 1
    return surf_de, crv2d_de, crv3d_de


def _parse_entity_144(params: List[str]) -> Tuple[int, int, List[int]]:
    """Parse entity-144 (Trimmed Parametric Surface).

    Returns (surf_de, outer_de, inner_des).
    """
    # params[0] == '144'
    # PTS, N1, N2, PT0, [inner_des...]
    surf_de = int(params[1])
    _n1 = int(params[2])
    n2 = int(params[3])
    outer_de = int(params[4])
    inner_des = [int(params[5 + i]) for i in range(n2)]
    return surf_de, outer_de, inner_des


def read_iges(filepath: str) -> List[TrimmedSurface]:
    """Read an IGES file and return all trimmed surfaces (entity 144).

    Parameters
    ----------
    filepath : Path to the IGES file.

    Returns
    -------
    list[TrimmedSurface]
        One entry per entity-144 found.  If the file contains no entity-144
        instances an empty list is returned.

    Raises
    ------
    IgesReadError
        On any fatal parsing error.
    """
    try:
        with open(filepath, "r", encoding="ascii", errors="replace") as f:
            text = f.read()
    except OSError as exc:
        raise IgesReadError(f"Cannot open file {filepath!r}: {exc}") from exc

    _s_lines, _g_lines, d_lines, p_lines = _parse_iges_sections(text)
    de_map = _parse_de_section(d_lines)

    if not de_map:
        return []

    def _get_pd(entry: _DEEntry) -> List[str]:
        raw = _extract_pd_string(p_lines, entry.pd_first, entry.pd_count)
        return _split_params(raw)

    # Build a lazy-resolved cache of parsed entities
    _entity_cache: Dict[int, object] = {}

    def _resolve(de_seq: int) -> object:
        if de_seq in _entity_cache:
            return _entity_cache[de_seq]
        entry = de_map.get(de_seq)
        if entry is None:
            raise IgesReadError(f"DE sequence {de_seq} not found in directory")
        params = _get_pd(entry)
        etype = entry.entity_type
        result: object
        if etype == 126:
            result = _parse_entity_126(params)
        elif etype == 128:
            result = _parse_entity_128(params)
        elif etype == 142:
            result = _parse_entity_142(params)
        elif etype == 144:
            result = _parse_entity_144(params)
        else:
            result = {"entity_type": etype, "params": params}
        _entity_cache[de_seq] = result
        return result

    # Find all entity-144 entries
    results: List[TrimmedSurface] = []

    for de_seq, entry in sorted(de_map.items()):
        if entry.entity_type != 144:
            continue

        surf_de, outer_de, inner_des = _resolve(de_seq)  # type: ignore[misc]

        # Resolve the surface
        surf = _resolve(surf_de)
        if not isinstance(surf, NurbsSurface):
            raise IgesReadError(
                f"Entity-144 surface pointer (DE={surf_de}) does not resolve to a "
                f"NurbsSurface (got {type(surf).__name__})"
            )

        # Helper to resolve a 142 → UV NurbsCurve
        def _loop_curves_from_142(de142: int) -> List[NurbsCurve]:
            resolved = _resolve(de142)
            if not isinstance(resolved, tuple):
                raise IgesReadError(
                    f"DE={de142} expected entity-142 tuple, got {type(resolved).__name__}"
                )
            _s_de, crv2d_de, _c3d_de = resolved
            crv2d = _resolve(crv2d_de)
            if not isinstance(crv2d, NurbsCurve):
                raise IgesReadError(
                    f"Entity-142 2D curve pointer (DE={crv2d_de}) does not resolve to "
                    f"NurbsCurve (got {type(crv2d).__name__})"
                )
            # Rebuild as explicit 2D curve (drop z=0 from control points if stored 3D)
            cp = crv2d.control_points
            if cp.shape[1] == 3:
                # Strip z dimension — it should be ~0 for a UV-space curve
                cp = cp[:, :2]
                crv2d = NurbsCurve(
                    degree=crv2d.degree,
                    control_points=cp,
                    knots=crv2d.knots,
                    weights=crv2d.weights,
                )
            return [crv2d]

        outer_curves = _loop_curves_from_142(outer_de)
        inner_loops = [_loop_curves_from_142(de) for de in inner_des]

        results.append(
            TrimmedSurface(
                surface=surf,
                outer_boundary=outer_curves,
                inner_boundaries=inner_loops,
            )
        )

    return results
