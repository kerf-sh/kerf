"""
kerf_cad_core.reverse_engineering.feature_map — Segment → feature node mapping.

Maps each fitted primitive segment to a ``.feature``-style dict node.

Mapping table (v1)
------------------

+------------+--------------+--------------------------------------------------+
| Primitive  | Feature op   | Key parameters stored on the node               |
+============+==============+==================================================+
| plane      | extrude      | normal, d (plane equation), extent (bbox depth) |
+------------+--------------+--------------------------------------------------+
| cylinder   | revolve      | axis, axis_point, radius, height                |
+------------+--------------+--------------------------------------------------+
| sphere     | sphere       | centre, radius                                  |
+------------+--------------+--------------------------------------------------+
| cone       | cone         | apex, axis, half_angle_deg, height              |
+------------+--------------+--------------------------------------------------+

Design notes
------------
- This mapping is intentionally simple and lossless: all geometric parameters
  from the RANSAC fit are preserved on the node.
- ``op`` values follow the conventions used elsewhere in kerf feature trees
  (``pad``, ``pocket``, etc. for history-based ops; ``sphere`` / ``cone`` for
  analytic primitives).
- The ``id`` field uses the pattern ``"<primitive>-<index>"`` so nodes can be
  referenced from downstream tools.
- No OCCT dependency — feature nodes are pure-Python dicts.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any


def segment_to_feature(seg: dict[str, Any], index: int) -> dict[str, Any]:
    """Convert a segment dict (from sequential_ransac) to a feature node dict.

    Parameters
    ----------
    seg:
        A segment record returned by ``sequential_ransac``.  Must have
        a ``primitive`` key.
    index:
        Zero-based counter used to generate a unique ``id`` for the node.

    Returns
    -------
    Feature node dict with at minimum:
        id          str     e.g. "plane-0", "cylinder-1"
        op          str     e.g. "extrude", "revolve", "sphere", "cone"
        source      str     "reverse_engineering_v1"
        inlier_count int
        residual    float
        ... primitive-specific parameters ...

    Raises
    ------
    ValueError
        If ``seg["primitive"]`` is not a recognised type.
    """
    kind = seg.get("primitive", "")
    node: dict[str, Any] = {
        "id": f"{kind}-{index}",
        "source": "reverse_engineering_v1",
        "inlier_count": seg.get("inlier_count", 0),
        "residual": seg.get("residual", 0.0),
    }

    if kind == "plane":
        node["op"] = "extrude"
        node["normal"] = seg["normal"]
        node["d"] = seg["d"]
        # extent: distance the extrude is pushed along the normal.
        # We don't have sketch geometry, so we store the inlier bbox depth
        # as a best-effort extent.  A real sketch-fit would be done in v2.
        node["extent"] = seg.get("extent", 0.0)
        node["centre"] = seg.get("centre")

    elif kind == "cylinder":
        node["op"] = "revolve"
        node["axis"] = seg["axis"]
        node["axis_point"] = seg["axis_point"]
        node["radius"] = seg["radius"]
        node["height"] = seg.get("height", 0.0)

    elif kind == "sphere":
        node["op"] = "sphere"
        node["centre"] = seg["centre"]
        node["radius"] = seg["radius"]

    elif kind == "cone":
        node["op"] = "cone"
        node["apex"] = seg["apex"]
        node["axis"] = seg["axis"]
        node["half_angle_deg"] = math.degrees(seg["half_angle"])
        node["height"] = seg.get("height", 0.0)

    else:
        raise ValueError(
            f"segment_to_feature: unrecognised primitive '{kind}'. "
            "Supported: plane, cylinder, sphere, cone."
        )

    return node


def segments_to_feature_tree(
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert a list of segment dicts to a feature tree (ordered list of nodes).

    Returns
    -------
    List of feature node dicts, ordered by fit priority (dominant primitive first).
    """
    return [segment_to_feature(seg, i) for i, seg in enumerate(segments)]
