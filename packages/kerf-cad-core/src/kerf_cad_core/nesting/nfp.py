"""
kerf_cad_core.nesting.nfp — True-shape polygon nesting via No-Fit Polygons.

Algorithm
---------
1.  Polygon primitives with signed area, centroid, bbox, convex hull,
    point-in-polygon (winding-number) and polygon–polygon intersection test.

2.  No-Fit Polygon (NFP) via Minkowski sum:
      NFP(A, B) = A ⊕ (−B)
    For concave polygons each operand is decomposed into convex pieces
    (ear-clipping convex decomposition) and the union of pairwise Minkowski
    sums approximated by their merged bounding regions.

3.  Inner-Fit Polygon (IFP) for the rectangular container:
      IFP(container, B) = container ⊖ B
    (eroded rectangle — the set of reference-point positions where B fits
    entirely inside the container).

4.  Bottom-left-fill placement:
    For each part (area-descending) compute the feasible region = IFP minus
    the union of NFPs against already-placed parts.  Sample candidate points
    from IFP vertices plus a grid, filter by feasibility, and pick the
    bottom-most then left-most point.  Try rotations 0/90/180/270°.

5.  Returns a list of Placement objects plus overall utilisation.

LLM tool
--------
nesting_true_shape(parts, bin_size, rotations)  — registered below.

Validation benchmarks (run via pytest):
  - 10 L-shapes in 500×500 bin: utilisation > 50 %
  - 5 circles (32-gon) in 200×200: utilisation ≈ 78.5 %

Pure-Python — no NumPy, no OCCT, no external dependencies.

Author: imranparuk
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Vector helpers
# ---------------------------------------------------------------------------

def _cross2(o: Tuple[float, float], a: Tuple[float, float],
             b: Tuple[float, float]) -> float:
    """2-D cross product of vectors OA and OB."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _dot2(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _sub2(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return (a[0] - b[0], a[1] - b[1])


def _add2(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return (a[0] + b[0], a[1] + b[1])


def _scale2(a: Tuple[float, float], s: float) -> Tuple[float, float]:
    return (a[0] * s, a[1] * s)


# ---------------------------------------------------------------------------
# Polygon class
# ---------------------------------------------------------------------------

@dataclass
class Polygon:
    """
    A simple (possibly non-convex) polygon described by an ordered vertex list.

    Vertices are (x, y) float tuples.  The winding order is preserved; sign
    of area reveals orientation (positive ↔ CCW, negative ↔ CW).
    """
    vertices: List[Tuple[float, float]]

    def __post_init__(self) -> None:
        self.vertices = list(self.vertices)
        if len(self.vertices) < 3:
            raise ValueError("Polygon requires at least 3 vertices.")

    # ------------------------------------------------------------------
    # Basic properties
    # ------------------------------------------------------------------

    def signed_area(self) -> float:
        """Signed area via the shoelace formula.  Positive ↔ CCW."""
        verts = self.vertices
        n = len(verts)
        acc = 0.0
        for i in range(n):
            x0, y0 = verts[i]
            x1, y1 = verts[(i + 1) % n]
            acc += (x0 * y1) - (x1 * y0)
        return acc * 0.5

    def area(self) -> float:
        return abs(self.signed_area())

    def centroid(self) -> Tuple[float, float]:
        verts = self.vertices
        n = len(verts)
        cx = cy = 0.0
        sa6 = 0.0
        for i in range(n):
            x0, y0 = verts[i]
            x1, y1 = verts[(i + 1) % n]
            cross = (x0 * y1) - (x1 * y0)
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
            sa6 += cross
        sa6 *= 3.0
        if abs(sa6) < 1e-12:
            xs = [v[0] for v in verts]
            ys = [v[1] for v in verts]
            return (sum(xs) / n, sum(ys) / n)
        return (cx / sa6, cy / sa6)

    def bbox(self) -> Tuple[float, float, float, float]:
        """Return (min_x, min_y, max_x, max_y)."""
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        return (min(xs), min(ys), max(xs), max(ys))

    def convex_hull(self) -> "Polygon":
        """Graham-scan convex hull; returns a new CCW Polygon."""
        pts = sorted(set(self.vertices))
        if len(pts) < 3:
            raise ValueError("Convex hull requires at least 3 distinct points.")
        # Lower hull
        lower: list = []
        for p in pts:
            while len(lower) >= 2 and _cross2(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        # Upper hull
        upper: list = []
        for p in reversed(pts):
            while len(upper) >= 2 and _cross2(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        hull = lower[:-1] + upper[:-1]
        return Polygon(hull)

    def is_convex(self) -> bool:
        verts = self.vertices
        n = len(verts)
        sign = None
        for i in range(n):
            c = _cross2(verts[i], verts[(i + 1) % n], verts[(i + 2) % n])
            if abs(c) < 1e-10:
                continue
            s = 1 if c > 0 else -1
            if sign is None:
                sign = s
            elif s != sign:
                return False
        return True

    def to_ccw(self) -> "Polygon":
        """Return a CCW-wound copy of this polygon."""
        if self.signed_area() < 0:
            return Polygon(list(reversed(self.vertices)))
        return Polygon(list(self.vertices))

    # ------------------------------------------------------------------
    # Point-in-polygon (winding number)
    # ------------------------------------------------------------------

    def contains_point(self, p: Tuple[float, float], tol: float = 1e-9) -> bool:
        """
        Winding-number test.  Returns True when p is inside (or on the
        boundary of) the polygon.
        """
        px, py = p
        verts = self.vertices
        n = len(verts)
        wn = 0
        for i in range(n):
            x0, y0 = verts[i]
            x1, y1 = verts[(i + 1) % n]
            if y0 <= py:
                if y1 > py:
                    if _cross2((x0, y0), (x1, y1), (px, py)) > tol:
                        wn += 1
            else:
                if y1 <= py:
                    if _cross2((x0, y0), (x1, y1), (px, py)) < -tol:
                        wn -= 1
        return wn != 0

    # ------------------------------------------------------------------
    # Translation / rotation
    # ------------------------------------------------------------------

    def translate(self, dx: float, dy: float) -> "Polygon":
        return Polygon([(x + dx, y + dy) for x, y in self.vertices])

    def rotate(self, angle_deg: float, cx: float = 0.0, cy: float = 0.0) -> "Polygon":
        """Rotate around (cx, cy) by angle_deg degrees (CCW)."""
        rad = math.radians(angle_deg)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        new_verts = []
        for x, y in self.vertices:
            tx, ty = x - cx, y - cy
            new_verts.append((
                cx + tx * cos_a - ty * sin_a,
                cy + tx * sin_a + ty * cos_a,
            ))
        return Polygon(new_verts)

    def normalize_origin(self) -> "Polygon":
        """Translate so that bbox min_x, min_y == 0, 0."""
        bx, by, _, _ = self.bbox()
        return self.translate(-bx, -by)

    # ------------------------------------------------------------------
    # Polygon–polygon intersection (AABB + separating axis)
    # ------------------------------------------------------------------

    def intersects(self, other: "Polygon", tol: float = 1e-6) -> bool:
        """
        Conservative collision test using the Separating Axis Theorem (SAT).
        Works for convex polygons; for concave ones we use the convex hull
        as a conservative approximation (may produce false positives but
        never false negatives, so it's safe for nesting feasibility checks).
        """
        # Quick AABB reject
        ax0, ay0, ax1, ay1 = self.bbox()
        bx0, by0, bx1, by1 = other.bbox()
        if ax1 + tol < bx0 or bx1 + tol < ax0:
            return False
        if ay1 + tol < by0 or by1 + tol < ay0:
            return False

        # SAT on convex hulls
        a = self.convex_hull()
        b = other.convex_hull()
        for poly in (a, b):
            verts = poly.vertices
            n = len(verts)
            for i in range(n):
                x0, y0 = verts[i]
                x1, y1 = verts[(i + 1) % n]
                # Edge normal
                nx, ny = -(y1 - y0), (x1 - x0)
                # Project both polygons
                pa = [nx * vx + ny * vy for vx, vy in a.vertices]
                pb = [nx * vx + ny * vy for vx, vy in b.vertices]
                if max(pa) + tol < min(pb) or max(pb) + tol < min(pa):
                    return False
        return True


# ---------------------------------------------------------------------------
# Convex decomposition (ear-clipping into triangles, then merged)
# ---------------------------------------------------------------------------

def _convex_decompose(poly: Polygon) -> List[Polygon]:
    """
    Decompose a simple polygon into a list of convex polygons.

    Strategy: if the polygon is already convex, return it as-is.
    Otherwise perform ear-clipping into triangles (always convex).
    The resulting triangles are a valid (though not optimal) decomposition.
    """
    if poly.is_convex():
        return [poly]

    # Ear-clip to triangles
    p = poly.to_ccw()
    verts = list(p.vertices)
    triangles: List[Polygon] = []

    while len(verts) > 3:
        n = len(verts)
        found_ear = False
        for i in range(n):
            prev_v = verts[(i - 1) % n]
            curr_v = verts[i]
            next_v = verts[(i + 1) % n]

            # Must be a left turn (CCW ear)
            if _cross2(prev_v, curr_v, next_v) <= 1e-10:
                continue

            # No other vertex inside the ear triangle
            ear = Polygon([prev_v, curr_v, next_v])
            is_ear = True
            for j in range(n):
                if j in {(i - 1) % n, i, (i + 1) % n}:
                    continue
                if ear.contains_point(verts[j]):
                    is_ear = False
                    break

            if is_ear:
                triangles.append(ear)
                verts.pop(i)
                found_ear = True
                break

        if not found_ear:
            # Fallback: just take the first triple (handles degenerate cases)
            triangles.append(Polygon([verts[0], verts[1], verts[2]]))
            verts.pop(1)

    if len(verts) == 3:
        triangles.append(Polygon(verts))

    return triangles


# ---------------------------------------------------------------------------
# Minkowski sum of two CONVEX polygons (A ⊕ B)
# ---------------------------------------------------------------------------

def _minkowski_sum_convex(a: Polygon, b: Polygon) -> Polygon:
    """
    Minkowski sum of two CCW convex polygons.
    Algorithm: merge the edge sequences sorted by angle, then accumulate.
    Result is a CCW convex polygon.
    """
    va = a.to_ccw().vertices
    vb = b.to_ccw().vertices

    # Find bottom-most (then left-most) vertex indices
    def _start(verts: list) -> int:
        idx = 0
        for i in range(1, len(verts)):
            if verts[i][1] < verts[idx][1] or (
                verts[i][1] == verts[idx][1] and verts[i][0] < verts[idx][0]
            ):
                idx = i
        return idx

    ia = _start(va)
    ib = _start(vb)
    na, nb = len(va), len(vb)

    result = [_add2(va[ia], vb[ib])]
    ca, cb = ia, ib

    for _ in range(na + nb):
        ea = _sub2(va[(ca + 1) % na], va[ca])
        eb = _sub2(vb[(cb + 1) % nb], vb[cb])
        cross = ea[0] * eb[1] - ea[1] * eb[0]
        if cross > 0:
            ca = (ca + 1) % na
            step = ea
        elif cross < 0:
            cb = (cb + 1) % nb
            step = eb
        else:
            ca = (ca + 1) % na
            cb = (cb + 1) % nb
            step = _add2(ea, eb)
        next_pt = _add2(result[-1], step)
        result.append(next_pt)

    # Remove duplicate closing vertex
    if len(result) > 1 and (
        abs(result[-1][0] - result[0][0]) < 1e-9 and
        abs(result[-1][1] - result[0][1]) < 1e-9
    ):
        result.pop()

    return Polygon(result)


# ---------------------------------------------------------------------------
# NFP: No-Fit Polygon  NFP(A, B) = A ⊕ (−B)
# ---------------------------------------------------------------------------

def _negate_polygon(poly: Polygon) -> Polygon:
    """Return −P (reflect through origin)."""
    return Polygon([(-x, -y) for x, y in poly.vertices])


def compute_nfp(a: Polygon, b: Polygon) -> List[Polygon]:
    """
    Compute the No-Fit Polygon of A and B.

    NFP(A, B) = A ⊕ (−B).

    For concave polygons we decompose both into convex pieces and return the
    list of pairwise Minkowski sums (an over-approximation of the true NFP
    union; sufficient for feasibility filtering).

    The returned polygons are in the coordinate frame of A's reference point
    (bottom-left corner of A's bbox).
    """
    a_pieces = _convex_decompose(a.to_ccw())
    neg_b_pieces = _convex_decompose(_negate_polygon(b.to_ccw()))

    nfps: List[Polygon] = []
    for pa in a_pieces:
        for pb in neg_b_pieces:
            mink = _minkowski_sum_convex(pa, pb)
            nfps.append(mink)
    return nfps


# ---------------------------------------------------------------------------
# IFP: Inner-Fit Polygon  IFP(container, B)
# ---------------------------------------------------------------------------

def compute_ifp(container_w: float, container_h: float, b: Polygon) -> Optional[Polygon]:
    """
    Inner-Fit Polygon: the set of valid reference-point positions for B
    inside a rectangular container of size container_w × container_h.

    B is assumed to be normalised to origin (bbox min at 0,0).

    Returns a rectangle (Polygon) or None if B does not fit.
    """
    bx0, by0, bx1, by1 = b.bbox()
    bw = bx1 - bx0
    bh = by1 - by0

    ifp_w = container_w - bw
    ifp_h = container_h - bh

    if ifp_w < -1e-9 or ifp_h < -1e-9:
        return None

    # Rectangle of valid reference positions (bottom-left corner of B's bbox)
    return Polygon([
        (0.0, 0.0),
        (ifp_w, 0.0),
        (ifp_w, ifp_h),
        (0.0, ifp_h),
    ])


# ---------------------------------------------------------------------------
# Feasibility helper
# ---------------------------------------------------------------------------

def _point_in_any(pt: Tuple[float, float], polys: List[Polygon]) -> bool:
    """Return True if pt is inside any of the given polygons."""
    for poly in polys:
        if poly.contains_point(pt):
            return True
    return False


def _point_in_ifp(pt: Tuple[float, float], ifp: Polygon) -> bool:
    return ifp.contains_point(pt)


def _candidate_points(ifp: Polygon, grid_step: float = 10.0) -> List[Tuple[float, float]]:
    """
    Generate candidate placement positions: IFP vertices + interior grid.
    """
    # Floor prevents pathological O((bin/step)^2) memory blow-up from caller input.
    grid_step = max(float(grid_step), 1.0)
    pts: List[Tuple[float, float]] = list(ifp.vertices)
    bx0, by0, bx1, by1 = ifp.bbox()
    x = bx0
    while x <= bx1 + 1e-9:
        y = by0
        while y <= by1 + 1e-9:
            pts.append((x, y))
            y += grid_step
        x += grid_step
    return pts


def _bottom_left_key(pt: Tuple[float, float]) -> Tuple[float, float]:
    """Sort key: bottom (small y) then left (small x)."""
    return (round(pt[1], 6), round(pt[0], 6))


# ---------------------------------------------------------------------------
# Placement result
# ---------------------------------------------------------------------------

@dataclass
class NFPPlacement:
    """One placed part."""
    name: str
    rotation: float              # degrees (0/90/180/270)
    ref_x: float                 # x of part's bbox min after placement
    ref_y: float                 # y of part's bbox min after placement
    poly: Polygon                # placed polygon (translated)
    part_area: float             # area of original polygon


# ---------------------------------------------------------------------------
# Main nesting function
# ---------------------------------------------------------------------------

def nest_true_shape(
    parts: List[dict],
    bin_w: float,
    bin_h: float,
    rotations: List[float] = None,
    grid_step: float = 5.0,
) -> dict:
    """
    NFP-based true-shape nesting.

    Parameters
    ----------
    parts : list of dicts
        Each dict must have:
          ``name`` (str) — identifier
          ``vertices`` (list of [x, y]) — polygon vertices
        Optional:
          ``qty`` (int, default 1) — repeat count
    bin_w, bin_h : float
        Container dimensions.
    rotations : list of float, optional
        Rotation angles in degrees to try per part.  Default [0, 90, 180, 270].
    grid_step : float
        Grid resolution for sampling candidate positions (mm).

    Returns
    -------
    dict with keys:
      ok          : bool
      placements  : list of placement dicts
      utilization : float in [0, 1]
      errors      : list of str
    """
    if rotations is None:
        rotations = [0.0, 90.0, 180.0, 270.0]

    errors: List[str] = []

    # Expand qty and build Polygon objects
    expanded: List[Tuple[str, Polygon]] = []
    for p in parts:
        name = str(p.get("name", "?"))
        raw_verts = p.get("vertices")
        if not raw_verts or len(raw_verts) < 3:
            errors.append(f"Part '{name}': vertices must have >= 3 points.")
            continue
        try:
            verts = [(float(v[0]), float(v[1])) for v in raw_verts]
        except Exception as exc:
            errors.append(f"Part '{name}': vertex parse error: {exc}")
            continue
        try:
            poly = Polygon(verts)
        except ValueError as exc:
            errors.append(f"Part '{name}': {exc}")
            continue
        qty = int(p.get("qty", 1))
        for _ in range(qty):
            expanded.append((name, poly))

    if errors:
        return {"ok": False, "placements": [], "utilization": 0.0, "errors": errors}

    if not expanded:
        return {"ok": True, "placements": [], "utilization": 0.0, "errors": []}

    # Sort parts by area descending (largest first)
    expanded.sort(key=lambda x: x[1].area(), reverse=True)

    total_part_area = sum(poly.area() for _, poly in expanded)
    bin_area = bin_w * bin_h

    placements: List[NFPPlacement] = []
    unplaced: List[str] = []

    for name, original_poly in expanded:
        best: Optional[NFPPlacement] = None

        for angle in rotations:
            # Rotate and normalise to origin
            rotated = original_poly.rotate(angle)
            norm = rotated.normalize_origin()

            # Compute IFP (feasible region for this part in the container)
            ifp = compute_ifp(bin_w, bin_h, norm)
            if ifp is None:
                # Part doesn't fit at this rotation
                continue

            # Compute NFP of each placed part against the current part
            nfp_list: List[Polygon] = []
            for placed in placements:
                placed_norm = placed.poly.translate(-placed.ref_x, -placed.ref_y)
                local_nfps = compute_nfp(placed_norm, norm)
                # Translate NFPs to world frame
                for nfp in local_nfps:
                    nfp_list.append(nfp.translate(placed.ref_x, placed.ref_y))

            # Generate candidate positions and filter
            candidates = _candidate_points(ifp, grid_step=grid_step)
            feasible: List[Tuple[float, float]] = []

            for pt in candidates:
                # pt is the candidate for norm's bbox-min (ref point)
                # Check it's inside IFP
                if not _point_in_ifp(pt, ifp):
                    continue
                # Check it's NOT inside any NFP (which would mean collision)
                if _point_in_any(pt, nfp_list):
                    continue
                feasible.append(pt)

            if not feasible:
                continue

            # Bottom-left fill: pick bottom-most then left-most
            feasible.sort(key=_bottom_left_key)
            chosen = feasible[0]
            ref_x, ref_y = chosen

            placed_poly = norm.translate(ref_x, ref_y)
            candidate_placement = NFPPlacement(
                name=name,
                rotation=angle,
                ref_x=ref_x,
                ref_y=ref_y,
                poly=placed_poly,
                part_area=original_poly.area(),
            )

            # Prefer lower y, then lower x, then smaller rotation index
            if best is None or _bottom_left_key(chosen) < _bottom_left_key((best.ref_x, best.ref_y)):
                best = candidate_placement

        if best is None:
            unplaced.append(name)
        else:
            placements.append(best)

    utilization = sum(pl.part_area for pl in placements) / bin_area if bin_area > 0 else 0.0

    placement_dicts = [
        {
            "name": pl.name,
            "rotation": pl.rotation,
            "x": pl.ref_x,
            "y": pl.ref_y,
            "vertices": pl.poly.vertices,
        }
        for pl in placements
    ]

    if unplaced:
        errors += [f"Part '{n}' could not be placed (does not fit at any rotation)." for n in unplaced]

    return {
        "ok": len(unplaced) == 0,
        "placements": placement_dicts,
        "utilization": utilization,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Shape factories
# ---------------------------------------------------------------------------

def make_l_shape(w: float = 60.0, h: float = 60.0, arm: float = 20.0) -> List[Tuple[float, float]]:
    """
    L-shape polygon with overall bounding box w×h and arm thickness arm.

    Vertices (CCW):
      (0,0) → (arm,0) → (arm,h-arm) → (w,h-arm) → (w,h) → (0,h)
    """
    return [
        (0.0, 0.0),
        (arm, 0.0),
        (arm, h - arm),
        (w, h - arm),
        (w, h),
        (0.0, h),
    ]


def make_ngon(n: int, r: float) -> List[Tuple[float, float]]:
    """Regular n-gon approximation of a circle with radius r (CCW)."""
    verts = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        verts.append((r + r * math.cos(angle), r + r * math.sin(angle)))
    return verts


# ---------------------------------------------------------------------------
# LLM tool
# ---------------------------------------------------------------------------

def nesting_true_shape(
    parts: List[dict],
    bin_size: Tuple[float, float],
    rotations: Optional[List[float]] = None,
    grid_step: float = 5.0,
) -> dict:
    """
    LLM-callable tool: true-shape polygon nesting via NFP.

    Parameters
    ----------
    parts : list of dicts
        ``name`` (str), ``vertices`` (list of [x, y]), optional ``qty`` (int).
    bin_size : (width, height)
        Container dimensions.
    rotations : list of float, optional
        Rotation angles (degrees) to try. Default [0, 90, 180, 270].
    grid_step : float
        Sampling resolution (mm). Smaller = better utilisation, slower.

    Returns
    -------
    dict: ok, placements, utilization, utilization_pct, errors.
    """
    bin_w, bin_h = float(bin_size[0]), float(bin_size[1])
    if rotations is None:
        rotations = [0.0, 90.0, 180.0, 270.0]

    result = nest_true_shape(
        parts=parts,
        bin_w=bin_w,
        bin_h=bin_h,
        rotations=rotations,
        grid_step=grid_step,
    )
    result["utilization_pct"] = round(result["utilization"] * 100, 2)
    return result
