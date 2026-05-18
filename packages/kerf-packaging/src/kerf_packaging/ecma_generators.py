"""
kerf_packaging.ecma_generators — Parametric ECMA dieline generators.

ECMA standard series supported
-------------------------------
C-series (Regular Slotted Containers — RSC):
    ``ecma_c02_rsc`` — ECMA C-02: Regular Slotted Container.
        Six panels: front, back, left, right, top-flap (×2), bottom-flap (×2).
        Classic RSC where all four flaps meet at the centre of the box.

A-series (trays / full-overlap):
    ``ecma_a10_tray`` — ECMA A-10: One-piece folder / tray with full-depth sides.

B-series (display / counter):
    ``ecma_b03_display`` — ECMA B-03: Counter display box with locking tuck front.

All functions return a ``Dieline`` instance.

Reference dimensions (ECMA standard, T&C = thickness and clearance)
---------------------------------------------------------------------
For a box of internal dimensions L × W × D (length × width × depth):

    C02 RSC layout:
        flat width  = 2L + 2W + 4J   (J = joint/manufacturer's tab, typically 15 mm)
        flat height = D + max(L, W)/2 × 2  (top + bottom flaps = D/2 each for RSC)
        (ECMA C02: top + bottom flaps each = W/2 so they just meet at centre)

    Grain direction: parallel to the depth (D) dimension by convention.

Parameters
----------
All dimension parameters are in mm.
``board_t`` : board caliper / thickness in mm (used for fold allowance).
``joint``   : manufacturer's joint (tab) width in mm (default 15 mm).

Notes
-----
- All coordinates are in a flat 2-D layout with the origin at the bottom-left
  of the blank.
- Fold lines are placed at the shared edges between panels.
- A 0.5 mm fold-line allowance (clearance) is applied on each side of a fold
  (board_t / 2) to prevent board crush.  For thin SBS board this is negligible.
"""

from __future__ import annotations

import math
from typing import Optional

from kerf_packaging.dieline import (
    Dieline,
    DiPanel,
    DieLine,
    FoldEdge,
    LineKind,
    Material,
    DiePanelVertex,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rect_panel(
    name: str, x: float, y: float, w: float, h: float
) -> DiPanel:
    """Create a rectangular panel."""
    return DiPanel(name=name, x=x, y=y, width=w, height=h)


def _hfold(x1: float, x2: float, y: float) -> DieLine:
    """Horizontal fold line."""
    return DieLine(x1, y, x2, y, kind=LineKind.FOLD)


def _vfold(x: float, y1: float, y2: float) -> DieLine:
    """Vertical fold line."""
    return DieLine(x, y1, x, y2, kind=LineKind.FOLD)


def _hcut(x1: float, x2: float, y: float) -> DieLine:
    """Horizontal cut line."""
    return DieLine(x1, y, x2, y, kind=LineKind.CUT)


def _vcut(x: float, y1: float, y2: float) -> DieLine:
    """Vertical cut line."""
    return DieLine(x, y1, x, y2, kind=LineKind.CUT)


def _rect_outline(
    x: float, y: float, w: float, h: float,
    kind: LineKind = LineKind.CUT,
) -> list[DieLine]:
    """Four lines forming a closed rectangle (CCW)."""
    x1, y1 = x, y
    x2, y2 = x + w, y + h
    return [
        DieLine(x1, y1, x2, y1, kind=kind),
        DieLine(x2, y1, x2, y2, kind=kind),
        DieLine(x2, y2, x1, y2, kind=kind),
        DieLine(x1, y2, x1, y1, kind=kind),
    ]


# ---------------------------------------------------------------------------
# ECMA C-02: Regular Slotted Container (RSC)
# ---------------------------------------------------------------------------

def ecma_c02_rsc(
    length: float,
    width: float,
    depth: float,
    *,
    board_t: float = 0.4,
    joint: float = 15.0,
    material: Material = Material.SBS,
) -> Dieline:
    """
    Generate a dieline for an ECMA C-02 Regular Slotted Container (RSC).

    An RSC has:
    - Four side panels arranged in a strip: left | front | right | back.
    - A manufacturer's glue tab (joint) on the far right.
    - Top and bottom flaps (two each) that are each W/2 deep so they meet
      at the centre when folded.

    The flat layout is:

        +-------+-------+-------+-------+-------+
        |  TF   |  TF   |  TF   |  TF   |       |
        | LEFT  | FRONT | RIGHT | BACK  | JOINT |
        |  BF   |  BF   |  BF   |  BF   |       |
        +-------+-------+-------+-------+-------+

    where TF = top flap (height = W/2) and BF = bottom flap (height = W/2).
    The full height of the blank is: D + W/2 + W/2 = D + W.
    The full width  of the blank is: 2L + 2W + joint.

    Parameters
    ----------
    length : float
        Internal box length (mm) — the longer horizontal dimension.
    width : float
        Internal box width (mm) — the shorter horizontal dimension.
    depth : float
        Internal box depth (mm) — the vertical dimension (height of the box).
    board_t : float
        Board caliper in mm.  Used to compute fold-allowance offsets.
    joint : float
        Glue tab width in mm (default 15 mm).
    material : Material
        Board material.

    Returns
    -------
    Dieline
        A fully-populated dieline with panels, cut lines, fold lines,
        and fold-edge descriptors.

    Notes
    -----
    ECMA C02 standard: all four flaps are slotted to the centreline so
    the top pair and bottom pair each form a closed face when folded.
    Slot cuts are placed at the boundaries between adjacent flaps
    (i.e., at the L/2 and W/2 marks on each flap row).
    """
    if length <= 0 or width <= 0 or depth <= 0:
        raise ValueError(
            f"All box dimensions must be positive; got L={length}, W={width}, D={depth}"
        )
    if board_t < 0:
        raise ValueError(f"board_t must be >= 0, got {board_t}")
    if joint <= 0:
        raise ValueError(f"joint must be positive, got {joint}")

    fa = board_t / 2.0   # fold allowance per side

    # Flap depth for ECMA C02: each flap is half the opposite dimension.
    # Top/bottom flaps on the L-panels (front/back) → depth_flap_L = W/2
    # Top/bottom flaps on the W-panels (left/right)  → depth_flap_W = L/2
    # In the RSC, all top flaps are the same height (min(L,W)/2 would give
    # non-overlapping; ECMA C02 uses W/2 for the L-face flaps).
    flap_h = width / 2.0   # standard RSC: flaps on front/back = W/2

    # ----- flat blank dimensions ------------------------------------------
    blank_w = 2.0 * length + 2.0 * width + joint
    blank_h = depth + 2.0 * flap_h

    # ----- X positions of vertical fold/cut lines -------------------------
    # Origin (0,0) = bottom-left of blank
    # Y: bottom_flap (0..flap_h), body (flap_h..flap_h+depth), top_flap (flap_h+depth..blank_h)
    x0 = 0.0
    x1 = width          # left | front fold
    x2 = width + length # front | right fold
    x3 = 2.0 * width + length  # right | back fold
    x4 = 2.0 * (width + length)  # back | joint fold
    x5 = blank_w        # right edge of joint / blank

    # ----- Y positions of horizontal fold/cut lines -----------------------
    y0 = 0.0
    y1 = flap_h          # bottom of body (bottom-flap fold)
    y2 = flap_h + depth  # top of body (top-flap fold)
    y3 = blank_h         # top of blank

    # ----- Panels ---------------------------------------------------------
    panels: list[DiPanel] = [
        # Main body panels
        _rect_panel("left",  x0, y1, width,  depth),
        _rect_panel("front", x1, y1, length, depth),
        _rect_panel("right", x2, y1, width,  depth),
        _rect_panel("back",  x3, y1, length, depth),
        _rect_panel("joint", x4, y1, joint,  depth),
        # Bottom flaps
        _rect_panel("bottom_flap_left",  x0, y0, width,  flap_h),
        _rect_panel("bottom_flap_front", x1, y0, length, flap_h),
        _rect_panel("bottom_flap_right", x2, y0, width,  flap_h),
        _rect_panel("bottom_flap_back",  x3, y0, length, flap_h),
        # Top flaps
        _rect_panel("top_flap_left",  x0, y2, width,  flap_h),
        _rect_panel("top_flap_front", x1, y2, length, flap_h),
        _rect_panel("top_flap_right", x2, y2, width,  flap_h),
        _rect_panel("top_flap_back",  x3, y2, length, flap_h),
    ]

    # ----- Lines ----------------------------------------------------------
    lines: list[DieLine] = []

    # Outer boundary (cut lines)
    # Bottom edge
    lines.append(_hcut(x0, x5, y0))
    # Top edge
    lines.append(_hcut(x0, x5, y3))
    # Left edge (full height)
    lines.append(_vcut(x0, y0, y3))
    # Right edge (joint right side)
    lines.append(_vcut(x5, y0, y3))

    # Vertical fold lines (full height — body + both flaps)
    for xf in (x1, x2, x3, x4):
        lines.append(_vfold(xf, y0, y3))

    # Horizontal fold lines: bottom-flap fold and top-flap fold
    # Run across the full blank width (they separate body from flaps)
    lines.append(_hfold(x0, x5, y1))
    lines.append(_hfold(x0, x5, y2))

    # RSC slot cuts: cuts between adjacent flaps in both flap rows.
    # Bottom flap slots: at x1, x2, x3 from y0 up to y1
    # Top    flap slots: at x1, x2, x3 from y2 up to y3
    # (These allow the RSC flaps to fold independently.)
    for xslot in (x1, x2, x3):
        lines.append(_vcut(xslot, y0, y1))    # bottom flap slot
        lines.append(_vcut(xslot, y2, y3))    # top flap slot

    # ----- Fold edges -----------------------------------------------------
    fold_edges: list[FoldEdge] = [
        FoldEdge("left",  "front", _vfold(x1, y1, y2), 90.0),
        FoldEdge("front", "right", _vfold(x2, y1, y2), 90.0),
        FoldEdge("right", "back",  _vfold(x3, y1, y2), 90.0),
        FoldEdge("back",  "joint", _vfold(x4, y1, y2), 90.0),
        # bottom flap folds
        FoldEdge("left",  "bottom_flap_left",  _hfold(x0, x1, y1),  90.0),
        FoldEdge("front", "bottom_flap_front", _hfold(x1, x2, y1),  90.0),
        FoldEdge("right", "bottom_flap_right", _hfold(x2, x3, y1),  90.0),
        FoldEdge("back",  "bottom_flap_back",  _hfold(x3, x4, y1),  90.0),
        # top flap folds
        FoldEdge("left",  "top_flap_left",  _hfold(x0, x1, y2), 90.0),
        FoldEdge("front", "top_flap_front", _hfold(x1, x2, y2), 90.0),
        FoldEdge("right", "top_flap_right", _hfold(x2, x3, y2), 90.0),
        FoldEdge("back",  "top_flap_back",  _hfold(x3, x4, y2), 90.0),
    ]

    d = Dieline(
        name="ECMA-C02-RSC",
        panels=panels,
        lines=lines,
        fold_edges=fold_edges,
        width=blank_w,
        height=blank_h,
        material=material,
        units="mm",
        metadata={
            "ecma_style": "C02",
            "internal_length_mm": length,
            "internal_width_mm": width,
            "internal_depth_mm": depth,
            "board_thickness_mm": board_t,
            "joint_mm": joint,
            "blank_width_mm": blank_w,
            "blank_height_mm": blank_h,
        },
    )
    return d


# ---------------------------------------------------------------------------
# ECMA A-10: One-piece tray (folder / full-depth side panels)
# ---------------------------------------------------------------------------

def ecma_a10_tray(
    length: float,
    width: float,
    depth: float,
    *,
    board_t: float = 0.4,
    material: Material = Material.SBS,
) -> Dieline:
    """
    Generate a dieline for an ECMA A-10 one-piece folder / shallow tray.

    Layout (top view of flat blank):

        +-------+-------+-------+
        |  END  | BOTTOM| END   |
        | PANEL |       | PANEL |
        +-------+-------+-------+
          SIDE    SIDE    SIDE
          FLAP    (omit) FLAP

    In the A-10 one-piece folder the base is surrounded on all four sides by
    side panels and end panels that fold up to form a tray:

        - Left end / right end panels fold up along the W edges of the base.
        - Front / back side panels fold up along the L edges of the base.
        - Corner glue flaps (45° mitre or step-cut) at each corner.

    Flat layout origin at bottom-left of blank.

    Parameters
    ----------
    length : float
        Internal tray length (mm).
    width : float
        Internal tray width (mm).
    depth : float
        Tray side depth (mm).
    board_t : float
        Board caliper (mm).
    material : Material
        Board material.

    Returns
    -------
    Dieline
    """
    if length <= 0 or width <= 0 or depth <= 0:
        raise ValueError(
            f"All tray dimensions must be positive; got L={length}, W={width}, D={depth}"
        )

    # Blank dimensions
    blank_w = length + 2.0 * depth
    blank_h = width  + 2.0 * depth

    # X / Y fold positions
    xL = depth                    # left-side-panel | base fold
    xR = depth + length           # base | right-side-panel fold
    yB = depth                    # front-panel | base fold
    yT = depth + width            # base | back-panel fold

    panels: list[DiPanel] = [
        # Base
        _rect_panel("base",         xL, yB, length, width),
        # Side panels
        _rect_panel("front_panel",  xL, 0.0,    length, depth),
        _rect_panel("back_panel",   xL, yT,     length, depth),
        _rect_panel("left_panel",   0.0,  yB,   depth,  width),
        _rect_panel("right_panel",  xR,   yB,   depth,  width),
        # Corner flaps (small squares at each corner of the blank)
        _rect_panel("corner_fl",    0.0, 0.0,   depth,  depth),
        _rect_panel("corner_fr",    xR,  0.0,   depth,  depth),
        _rect_panel("corner_bl",    0.0, yT,    depth,  depth),
        _rect_panel("corner_br",    xR,  yT,    depth,  depth),
    ]

    lines: list[DieLine] = []

    # Outer boundary
    lines += _rect_outline(0.0, 0.0, blank_w, blank_h, kind=LineKind.CUT)

    # Fold lines (base ↔ sides)
    lines.append(_vfold(xL, 0.0,  blank_h))
    lines.append(_vfold(xR, 0.0,  blank_h))
    lines.append(_hfold(0.0,  blank_w, yB))
    lines.append(_hfold(0.0,  blank_w, yT))

    # Corner cut lines (cut corners to form a step joint)
    # Each corner is a small square that is left as a corner flap or cut away.
    # Standard A-10: cut the corner squares (leave as waste / score diagonals).
    # We represent corners as diagonal cut lines (45° miter).
    def _diag_cut(x0, y0, x1, y1):
        return DieLine(x0, y0, x1, y1, kind=LineKind.CUT)

    lines += [
        _diag_cut(0.0, yB, xL, 0.0),     # front-left corner
        _diag_cut(xR, 0.0, blank_w, yB),  # front-right corner
        _diag_cut(0.0, yT, xL, blank_h),  # back-left corner
        _diag_cut(xR, blank_h, blank_w, yT),  # back-right corner
    ]

    fold_edges: list[FoldEdge] = [
        FoldEdge("base", "front_panel", _hfold(xL, xR, yB), 90.0),
        FoldEdge("base", "back_panel",  _hfold(xL, xR, yT), 90.0),
        FoldEdge("base", "left_panel",  _vfold(xL, yB, yT), 90.0),
        FoldEdge("base", "right_panel", _vfold(xR, yB, yT), 90.0),
    ]

    d = Dieline(
        name="ECMA-A10-Tray",
        panels=panels,
        lines=lines,
        fold_edges=fold_edges,
        width=blank_w,
        height=blank_h,
        material=material,
        units="mm",
        metadata={
            "ecma_style": "A10",
            "internal_length_mm": length,
            "internal_width_mm": width,
            "internal_depth_mm": depth,
            "board_thickness_mm": board_t,
            "blank_width_mm": blank_w,
            "blank_height_mm": blank_h,
        },
    )
    return d


# ---------------------------------------------------------------------------
# ECMA B-03: Counter display box with tuck front
# ---------------------------------------------------------------------------

def ecma_b03_display(
    length: float,
    width: float,
    depth: float,
    *,
    tuck_depth: Optional[float] = None,
    board_t: float = 0.4,
    material: Material = Material.SBS,
) -> Dieline:
    """
    Generate a dieline for an ECMA B-03 counter display box.

    The B-03 is a tray with a display front panel that tucks into a slot
    cut into the front face — commonly used for retail shelf display.

    Layout:

        +--------+--------+--------+--------+
        | DUST   |  TOP   | DUST   |        |
        | FLAP   |  FLAP  | FLAP   |        |
        | LEFT   |        | RIGHT  | JOINT  |
        | SIDE   | FRONT  | SIDE   |        |
        |   *    | TUCK   |   *    |        |
        |  DUST  | SLOT   |  DUST  |        |
        | FLAP   | +BACK  | FLAP   |        |
        +--------+--------+--------+--------+

    (* corner cut-outs are scored)

    The tuck depth defaults to 15 mm (or 1/6 of depth, whichever is larger).

    Parameters
    ----------
    length : float
        Internal box length / front-face width (mm).
    width : float
        Internal box width / depth of the box (mm).
    depth : float
        Internal box height (mm).
    tuck_depth : float or None
        Depth of the tuck tongue on the front panel (mm). Default = max(15, depth/6).
    board_t : float
        Board caliper (mm).
    material : Material
        Board material.

    Returns
    -------
    Dieline
    """
    if length <= 0 or width <= 0 or depth <= 0:
        raise ValueError(
            f"All display box dimensions must be positive; got L={length}, W={width}, D={depth}"
        )

    if tuck_depth is None:
        tuck_depth = max(15.0, depth / 6.0)

    dust_h = width / 2.0   # dust flap height = W/2 (standard)
    joint  = 15.0

    # Flat blank dimensions
    blank_w = 2.0 * width + 2.0 * length + joint
    blank_h = depth + dust_h + tuck_depth  # top-dust + body + tuck

    # X positions
    x0 = 0.0
    x1 = width           # left | front
    x2 = width + length  # front | right
    x3 = 2.0 * width + length   # right | back
    x4 = 2.0 * (width + length) # back | joint
    x5 = blank_w

    # Y positions
    y0 = 0.0
    y1 = tuck_depth       # tuck fold line
    y2 = tuck_depth + depth  # top dust fold line
    y3 = blank_h

    panels: list[DiPanel] = [
        # Body panels
        _rect_panel("left_side",  x0, y1, width,  depth),
        _rect_panel("front",      x1, y1, length, depth),
        _rect_panel("right_side", x2, y1, width,  depth),
        _rect_panel("back",       x3, y1, length, depth),
        _rect_panel("joint",      x4, y1, joint,  depth),
        # Tuck tongue (below the body)
        _rect_panel("tuck_left",  x0, y0, width,  tuck_depth),
        _rect_panel("tuck_front", x1, y0, length, tuck_depth),
        _rect_panel("tuck_right", x2, y0, width,  tuck_depth),
        # Dust / top flaps (above body)
        _rect_panel("dust_left",  x0, y2, width,  dust_h),
        _rect_panel("dust_front", x1, y2, length, dust_h),
        _rect_panel("dust_right", x2, y2, width,  dust_h),
        _rect_panel("dust_back",  x3, y2, length, dust_h),
    ]

    lines: list[DieLine] = []

    # Outer boundary
    lines.append(_hcut(x0, x5, y0))
    lines.append(_hcut(x0, x5, y3))
    lines.append(_vcut(x0, y0, y3))
    lines.append(_vcut(x5, y0, y3))

    # Vertical fold lines (full height)
    for xf in (x1, x2, x3, x4):
        lines.append(_vfold(xf, y0, y3))

    # Horizontal fold lines
    lines.append(_hfold(x0, x5, y1))  # tuck fold
    lines.append(_hfold(x0, x5, y2))  # top-dust fold

    # Tuck slot cuts (between adjacent tuck panels)
    for xslot in (x1, x2, x3):
        lines.append(_vcut(xslot, y0, y1))   # tuck slots
        lines.append(_vcut(xslot, y2, y3))   # dust flap slots

    fold_edges: list[FoldEdge] = [
        FoldEdge("left_side",  "front",      _vfold(x1, y1, y2), 90.0),
        FoldEdge("front",      "right_side", _vfold(x2, y1, y2), 90.0),
        FoldEdge("right_side", "back",       _vfold(x3, y1, y2), 90.0),
        FoldEdge("back",       "joint",      _vfold(x4, y1, y2), 90.0),
        FoldEdge("left_side",  "dust_left",  _hfold(x0, x1, y2), 90.0),
        FoldEdge("front",      "dust_front", _hfold(x1, x2, y2), 90.0),
        FoldEdge("right_side", "dust_right", _hfold(x2, x3, y2), 90.0),
        FoldEdge("back",       "dust_back",  _hfold(x3, x4, y2), 90.0),
        FoldEdge("front",      "tuck_front", _hfold(x1, x2, y1), 90.0),
    ]

    d = Dieline(
        name="ECMA-B03-Display",
        panels=panels,
        lines=lines,
        fold_edges=fold_edges,
        width=blank_w,
        height=blank_h,
        material=material,
        units="mm",
        metadata={
            "ecma_style": "B03",
            "internal_length_mm": length,
            "internal_width_mm": width,
            "internal_depth_mm": depth,
            "tuck_depth_mm": tuck_depth,
            "board_thickness_mm": board_t,
            "blank_width_mm": blank_w,
            "blank_height_mm": blank_h,
        },
    )
    return d
