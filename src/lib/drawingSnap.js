// TechDraw-style snap helpers for the drawing canvas.
//
// Given the cached projection of a view (`{polylines, bbox}` from
// projection.js) plus a cursor position in PAGE-MM, returns the closest
// snap target within tolerance, or null. Snap targets carry both their type
// (for the visual marker) and the snapped point in PAGE-MM coordinates.
//
// Snap kinds in priority order (when several land within radius):
//   1. endpoint    — terminal of any projected segment
//   2. center      — center of a detected circle/arc
//   3. midpoint    — middle of a straight segment
//   4. intersection — where two segments cross in 2D
//   5. origin      — sheet origin (0,0)
//
// Intersection detection is O(n²) but runs lazily — only when no higher-
// priority snap lands first AND the cursor is close to multiple segments.
// For typical drawings (≤ a few hundred segments per view) the scan is fast
// enough; we don't pre-build a spatial index.

import { detectCenterlines } from './annotations.js'

// Page-mm tolerance == 12 screen-px / current px-per-mm. Caller passes
// `pxPerMm` (rect.width / viewBox.w from DrawingView) so we can convert
// the spec's "12px screen distance" into a model-space radius.
const SNAP_PIXELS = 12

// ---------------------------------------------------------------------------
// Per-view snap-target extraction
//
// Walks the projected polyline list once and returns:
//   {
//     endpoints:    [[x, y], ...]    — page-mm
//     midpoints:    [[x, y, ax, ay, bx, by], ...]
//     segments:     [[ax, ay, bx, by], ...]  — for intersection scans
//     centers:      [[x, y, r], ...] — detected circle centres
//   }
// All coordinates are in PAGE-MM (already transformed from the projection's
// local model units via the view's bbox + scale). This way the cursor (also
// in page-mm) can be compared directly without per-frame transforms.

export function extractSnapTargets(view, projection) {
  if (!view || !projection || !projection.bbox) {
    return { endpoints: [], midpoints: [], segments: [], centers: [], viewId: view?.id || null }
  }
  const minU = projection.bbox.min[0]
  const minV = projection.bbox.min[1]
  const tx = view.position[0]
  const ty = view.position[1]
  const sw = 1 / (view.scale || 1)
  // Projection-local model coords → page-mm.
  const toPage = (u, v) => [tx + (u - minU) * sw, ty + (v - minV) * sw]

  // Only visible/silhouette edges contribute to snaps; hidden lines aren't
  // visible to the user so snapping to them surprises rather than helps.
  const visible = projection.polylines.filter(
    (p) => p.kind === 'visible' || p.kind === 'silhouette',
  )

  const endpoints = []
  const midpoints = []
  const segments = []
  const epKeys = new Set() // dedupe coincident endpoints (very common for shared corners)

  for (const pl of visible) {
    const [a, b] = pl.points
    const pa = toPage(a[0], a[1])
    const pb = toPage(b[0], b[1])
    // Skip zero-length artefacts (can happen at sample boundaries from HLR).
    if (Math.abs(pa[0] - pb[0]) < 1e-4 && Math.abs(pa[1] - pb[1]) < 1e-4) continue
    const ka = `${pa[0].toFixed(3)},${pa[1].toFixed(3)}`
    const kb = `${pb[0].toFixed(3)},${pb[1].toFixed(3)}`
    if (!epKeys.has(ka)) { epKeys.add(ka); endpoints.push(pa) }
    if (!epKeys.has(kb)) { epKeys.add(kb); endpoints.push(pb) }
    midpoints.push([(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, pa[0], pa[1], pb[0], pb[1]])
    segments.push([pa[0], pa[1], pb[0], pb[1]])
  }

  // Centers — re-use the existing arc/circle detector. It expects local
  // model coords, so feed it raw projection points and convert hits to page
  // coords. detectCenterlines is approximate; that's fine, we only need
  // the rough centre.
  const localSegs = visible.map((p) => p.points)
  const detected = detectCenterlines(localSegs)
  const centers = detected.map((c) => {
    const [x, y] = toPage(c.cx, c.cy)
    return [x, y, c.r * sw]
  })

  return { endpoints, midpoints, segments, centers, viewId: view.id }
}

// ---------------------------------------------------------------------------
// Snap resolution

// Find the closest snap target to (cx, cy) in page-mm. Returns:
//   { kind, x, y, viewId } | null
// where kind ∈ 'endpoint'|'midpoint'|'center'|'intersection'|'origin'.
//
// Higher-priority kinds win ties: an endpoint snap is preferred over a
// midpoint at the same distance because the endpoint is a hard geometric
// feature.
export function resolveSnap(targets, cx, cy, opts = {}) {
  const tolMm = (opts.tolMm != null ? opts.tolMm : SNAP_PIXELS) || 12
  const tol2 = tolMm * tolMm
  let best = null

  function consider(kind, px, py, priority) {
    const dx = px - cx
    const dy = py - cy
    const d2 = dx * dx + dy * dy
    if (d2 > tol2) return
    // Distance is primary; the priority number is just a tiebreaker for
    // exact-distance ties (extremely rare but keeps the behaviour
    // deterministic when an endpoint and midpoint coincide on a 0-length
    // edge).
    if (!best || d2 < best.d2 || (d2 === best.d2 && priority < best.priority)) {
      best = { kind, x: px, y: py, d2, priority }
    }
  }

  // Origin snap — only when the cursor is near (0,0).
  consider('origin', 0, 0, 5)

  for (const list of targets) {
    if (!list) continue
    for (const p of list.endpoints) consider('endpoint', p[0], p[1], 1)
    for (const p of list.centers)   consider('center', p[0], p[1], 2)
    for (const m of list.midpoints) consider('midpoint', m[0], m[1], 3)
  }

  // Intersection scan — O(n²) over near-cursor segments only. We bound the
  // candidate list at 64 to keep dense views snappy; in practice fewer than
  // that ever land within the snap radius simultaneously.
  const near = []
  for (const list of targets) {
    if (!list) continue
    for (const seg of list.segments) {
      if (segmentNearPoint(seg, cx, cy, tolMm)) {
        near.push({ seg, viewId: list.viewId })
        if (near.length >= 64) break
      }
    }
    if (near.length >= 64) break
  }
  for (let i = 0; i < near.length; i++) {
    for (let j = i + 1; j < near.length; j++) {
      const ix = segIntersect(near[i].seg, near[j].seg)
      if (!ix) continue
      consider('intersection', ix[0], ix[1], 4)
    }
  }

  if (!best) return null
  // viewId — find the list this point came from. We don't track per-target
  // viewId because it's only ever consumed for the dim/view binding; pick
  // the first (typically only) target list.
  const viewId = (targets.find((t) => t && t.viewId) || {}).viewId || null
  return { kind: best.kind, x: best.x, y: best.y, viewId }
}

// True iff the perpendicular distance from (cx, cy) to the segment is ≤ tol.
function segmentNearPoint(seg, cx, cy, tol) {
  const [ax, ay, bx, by] = seg
  const dx = bx - ax
  const dy = by - ay
  const lenSq = dx * dx + dy * dy
  if (lenSq < 1e-12) {
    return (ax - cx) ** 2 + (ay - cy) ** 2 <= tol * tol
  }
  let t = ((cx - ax) * dx + (cy - ay) * dy) / lenSq
  t = Math.max(0, Math.min(1, t))
  const px = ax + dx * t
  const py = ay + dy * t
  return (px - cx) ** 2 + (py - cy) ** 2 <= tol * tol
}

// 2D segment-segment intersection. Returns [x, y] if the segments cross
// strictly within their interiors, else null. Coincident endpoints don't
// count as intersections (they're already covered by the endpoint snap).
function segIntersect(s1, s2) {
  const [x1, y1, x2, y2] = s1
  const [x3, y3, x4, y4] = s2
  const dx1 = x2 - x1, dy1 = y2 - y1
  const dx2 = x4 - x3, dy2 = y4 - y3
  const denom = dx1 * dy2 - dy1 * dx2
  if (Math.abs(denom) < 1e-9) return null // parallel
  const t = ((x3 - x1) * dy2 - (y3 - y1) * dx2) / denom
  const u = ((x3 - x1) * dy1 - (y3 - y1) * dx1) / denom
  // Strictly interior — exclude the segment endpoints themselves with a
  // small epsilon so coincident-corner cases don't fight the endpoint snap.
  const eps = 1e-3
  if (t < eps || t > 1 - eps || u < eps || u > 1 - eps) return null
  return [x1 + t * dx1, y1 + t * dy1]
}

// ---------------------------------------------------------------------------
// Visual marker

// Color used by every snap marker — kerf-300 is the existing focus tone.
export const SNAP_COLOR = '#ffd633'

// Page-mm size of the marker glyph. Markers are rendered with
// `vector-effect="non-scaling-stroke"` so the stroke stays at 1px regardless
// of zoom; their FILL/SHAPE size scales with the SVG viewBox just like any
// other primitive, which keeps the geometric meaning ("this is exactly where
// the snap landed") visually obvious.
export const SNAP_MARKER_MM = 1.6

// Human-readable label for a snap kind. Lowercase to match the contract's
// hint-chip convention.
export function snapLabel(kind) {
  switch (kind) {
    case 'endpoint':     return 'endpoint'
    case 'midpoint':     return 'midpoint'
    case 'center':       return 'center'
    case 'intersection': return 'intersection'
    case 'origin':       return 'origin'
    default:             return ''
  }
}
