"""
DXF R12 export for civil alignment and earthwork data.

Produces a self-contained DXF R12 ASCII string that can be written to a
.dxf file.  No external dependencies — only the Python standard library.

Layers
------
  ALIGNMENT   — centreline polyline (easting / northing stations)
  STATIONS    — tick marks at each station interval
  EARTHWORK   — cut/fill profile polyline

Units: metres.
"""

from __future__ import annotations

from typing import Sequence


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _gc(lines: list[str], *pairs) -> None:
    """Append DXF group-code / value pairs to *lines*."""
    codes = list(pairs[::2])
    values = list(pairs[1::2])
    for code, val in zip(codes, values):
        lines.append(str(code))
        if isinstance(val, float):
            lines.append(f"{val:.6f}")
        else:
            lines.append(str(val))


def _polyline_2d(
    lines: list[str],
    pts: Sequence[tuple[float, float]],
    layer: str = "0",
    closed: bool = False,
) -> None:
    """Emit a 2-D POLYLINE entity with VERTEXes."""
    closed_flag = 1 if closed else 0
    _gc(lines, 0, "POLYLINE", 8, layer, 66, 1, 70, closed_flag)
    for x, y in pts:
        _gc(lines, 0, "VERTEX", 8, layer, 10, float(x), 20, float(y), 30, 0.0)
    _gc(lines, 0, "SEQEND", 8, layer)


def _line_2d(
    lines: list[str],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    layer: str = "0",
) -> None:
    """Emit a single LINE entity."""
    _gc(
        lines,
        0, "LINE",
        8, layer,
        10, float(x0), 20, float(y0), 30, 0.0,
        11, float(x1), 21, float(y1), 31, 0.0,
    )


def _text_2d(
    lines: list[str],
    x: float,
    y: float,
    text: str,
    height: float = 2.5,
    layer: str = "ANNOT",
) -> None:
    """Emit a TEXT entity."""
    _gc(
        lines,
        0, "TEXT",
        8, layer,
        10, float(x), 20, float(y), 30, 0.0,
        40, float(height),
        1, str(text),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def alignment_to_dxf(
    station_coords: Sequence[tuple[float, float, float]],
    *,
    station_interval: float = 20.0,
    include_station_labels: bool = True,
    tick_half_length: float = 2.0,
) -> str:
    """Export a civil alignment as DXF R12.

    Parameters
    ----------
    station_coords:
        Sequence of (station, x, y) tuples — one per station.  The alignment
        centreline is drawn as a POLYLINE connecting the (x, y) points in
        order.
    station_interval:
        Nominal station interval; used to filter which stations get tick marks
        and labels.  Labels are omitted when *include_station_labels* is False.
    tick_half_length:
        Half-length of perpendicular station tick marks (metres).
    include_station_labels:
        If True, add TEXT entities with the chainage label at each station.

    Returns
    -------
    str
        DXF R12 ASCII string.
    """
    lines: list[str] = []

    # Header
    _gc(lines, 0, "SECTION", 2, "HEADER")
    _gc(lines, 9, "$ACADVER", 1, "AC1009")
    _gc(lines, 0, "ENDSEC")

    # Entities section
    _gc(lines, 0, "SECTION", 2, "ENTITIES")

    # Centreline polyline
    cl_pts = [(x, y) for _s, x, y in station_coords]
    if len(cl_pts) >= 2:
        _polyline_2d(lines, cl_pts, layer="ALIGNMENT")

    # Station ticks and labels
    for i, (s, x, y) in enumerate(station_coords):
        # Draw a tick at every station
        # Compute perpendicular direction from finite difference
        if i == 0 and len(station_coords) > 1:
            _ns, nx, ny = station_coords[1]
            dx, dy = nx - x, ny - y
        elif i > 0:
            _ps, px, py = station_coords[i - 1]
            dx, dy = x - px, y - py
        else:
            dx, dy = 1.0, 0.0

        length = (dx * dx + dy * dy) ** 0.5
        if length > 1e-10:
            # Perpendicular: (-dy, dx) / length
            px_tick = -dy / length * tick_half_length
            py_tick = dx / length * tick_half_length
        else:
            px_tick = 0.0
            py_tick = tick_half_length

        _line_2d(
            lines,
            x - px_tick, y - py_tick,
            x + px_tick, y + py_tick,
            layer="STATIONS",
        )

        if include_station_labels:
            label = f"{s:.0f}"
            _text_2d(
                lines,
                x + px_tick * 1.5,
                y + py_tick * 1.5,
                label,
                height=2.5,
                layer="ANNOT",
            )

    _gc(lines, 0, "ENDSEC")
    _gc(lines, 0, "EOF")

    return "\n".join(lines)


def cut_fill_profile_to_dxf(
    stations: Sequence[float],
    cut_areas: Sequence[float],
    fill_areas: Sequence[float],
) -> str:
    """Export a cut/fill area profile as DXF R12.

    Produces two POLYLINE entities — one for cut areas and one for fill areas —
    plotted as an area-versus-station profile diagram.

    Parameters
    ----------
    stations:
        Chainage values (metres).
    cut_areas:
        Cut cross-sectional areas (m²) at each station.
    fill_areas:
        Fill cross-sectional areas (m²) at each station.

    Returns
    -------
    str
        DXF R12 ASCII string.
    """
    if not (len(stations) == len(cut_areas) == len(fill_areas)):
        raise ValueError(
            "stations, cut_areas, and fill_areas must have the same length"
        )

    lines: list[str] = []

    _gc(lines, 0, "SECTION", 2, "HEADER")
    _gc(lines, 9, "$ACADVER", 1, "AC1009")
    _gc(lines, 0, "ENDSEC")

    _gc(lines, 0, "SECTION", 2, "ENTITIES")

    # Cut profile (positive upward)
    cut_pts = [(float(s), float(a)) for s, a in zip(stations, cut_areas)]
    if len(cut_pts) >= 2:
        _polyline_2d(lines, cut_pts, layer="CUT")

    # Fill profile (negative — plotted below zero axis)
    fill_pts = [(float(s), -float(a)) for s, a in zip(stations, fill_areas)]
    if len(fill_pts) >= 2:
        _polyline_2d(lines, fill_pts, layer="FILL")

    # Zero datum line
    if stations:
        _line_2d(lines, float(stations[0]), 0.0, float(stations[-1]), 0.0, layer="DATUM")

    _gc(lines, 0, "ENDSEC")
    _gc(lines, 0, "EOF")

    return "\n".join(lines)


def validate_dxf(dxf_text: str) -> list[str]:
    """Basic structural validation of a DXF R12 string.

    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []
    text = dxf_text.strip()

    if not text:
        errors.append("DXF text is empty")
        return errors

    if "SECTION" not in text:
        errors.append("Missing SECTION marker")
    if "ENDSEC" not in text:
        errors.append("Missing ENDSEC marker")
    if not text.endswith("EOF"):
        errors.append("DXF does not end with EOF")
    if "$ACADVER" not in text:
        errors.append("Missing $ACADVER in HEADER")

    return errors
