"""GK-122: Interference / collision detection between two Body objects.

Pure-Python implementation (no OCCT dependency). Uses :func:`body_intersection`
(GK-18) to compute the overlapping region, then :func:`body_mass_props` to
measure its volume.
"""

from __future__ import annotations

from typing import Optional

from kerf_cad_core.geom.brep import Body
from kerf_cad_core.geom.boolean import body_intersection
from kerf_cad_core.geom.mass_props import body_mass_props


def interference(
    body_a: Body,
    body_b: Body,
    tol: float = 1e-6,
    vol_tol: float = 1e-10,
) -> dict:
    """Detect geometric interference (overlap) between two solid bodies.

    Parameters
    ----------
    body_a:
        First :class:`~kerf_cad_core.geom.brep.Body`.
    body_b:
        Second :class:`~kerf_cad_core.geom.brep.Body`.
    tol:
        Geometric tolerance forwarded to :func:`body_intersection`.
    vol_tol:
        Volume threshold below which the intersection is treated as empty
        (handles degenerate face-touching / edge-touching cases that produce
        a zero-volume shell).  Default 1e-10.

    Returns
    -------
    dict with keys:

    ``"interferes"``
        ``True`` when the overlap volume exceeds *vol_tol*.
    ``"volume"``
        Absolute volume of the intersection region (``0.0`` when disjoint).
    ``"region"``
        The intersection :class:`~kerf_cad_core.geom.brep.Body` when
        *interferes* is ``True``, otherwise ``None``.
    """
    region = body_intersection(body_a, body_b, tol=tol)

    # An empty Body (no faces) means the inputs are disjoint.
    if not region.all_faces():
        return {"interferes": False, "volume": 0.0, "region": None}

    props = body_mass_props(region)
    vol = abs(props["volume"])

    if vol <= vol_tol:
        return {"interferes": False, "volume": 0.0, "region": None}

    return {"interferes": True, "volume": vol, "region": region}
