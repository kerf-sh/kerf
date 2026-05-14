// copperPour.js — Pure geometry helpers for copper pour rendering.
// No React or browser imports — safe to use in vitest and workers.

/**
 * Ray-casting point-in-polygon test.
 * Returns true if point p is strictly inside the polygon.
 *
 * @param {{x: number, y: number}} p
 * @param {Array<{x: number, y: number}>} polygon
 * @returns {boolean}
 */
export function pointInPolygon(p, polygon) {
  if (!polygon || polygon.length < 3) return false
  let inside = false
  const n = polygon.length
  let j = n - 1
  for (let i = 0; i < n; i++) {
    const xi = polygon[i].x
    const yi = polygon[i].y
    const xj = polygon[j].x
    const yj = polygon[j].y
    const intersect =
      yi > p.y !== yj > p.y &&
      p.x < ((xj - xi) * (p.y - yi)) / (yj - yi) + xi
    if (intersect) inside = !inside
    j = i
  }
  return inside
}

/**
 * Offset a polygon outward by `amount` mm using a simple per-vertex normal
 * average. Not as accurate as Shapely but good enough for a frontend preview.
 *
 * @param {Array<{x: number, y: number}>} polygon
 * @param {number} amount - offset distance (positive = outward)
 * @returns {Array<{x: number, y: number}>}
 */
export function offsetPolygon(polygon, amount) {
  if (!polygon || polygon.length < 3) return polygon
  const n = polygon.length
  const result = []
  for (let i = 0; i < n; i++) {
    const prev = polygon[(i + n - 1) % n]
    const curr = polygon[i]
    const next = polygon[(i + 1) % n]

    // Edge normals (pointing outward for CCW winding, inward for CW — we normalise)
    const e1x = curr.x - prev.x
    const e1y = curr.y - prev.y
    const e1len = Math.hypot(e1x, e1y) || 1
    const n1x = -e1y / e1len
    const n1y = e1x / e1len

    const e2x = next.x - curr.x
    const e2y = next.y - curr.y
    const e2len = Math.hypot(e2x, e2y) || 1
    const n2x = -e2y / e2len
    const n2y = e2x / e2len

    // Bisector normal
    const bx = n1x + n2x
    const by = n1y + n2y
    const blen = Math.hypot(bx, by) || 1
    const scale = amount / blen

    result.push({ x: curr.x + bx * scale, y: curr.y + by * scale })
  }
  return result
}

/**
 * Approximate circular clearance holes for a list of pad objects.
 * Each hole is an octagon approximating a circle of (pad.radius + clearanceMm).
 *
 * @param {Array<{x: number, y: number, diameter_mm?: number}>} pads
 * @param {number} clearanceMm
 * @returns {Array<Array<{x: number, y: number}>>}  array of hole polygons
 */
export function padClearanceHoles(pads, clearanceMm) {
  if (!pads || pads.length === 0) return []
  const SIDES = 8
  return pads.map((pad) => {
    const r = (pad.diameter_mm != null ? pad.diameter_mm / 2 : 0.5) + clearanceMm
    const cx = pad.x || 0
    const cy = pad.y || 0
    const pts = []
    for (let i = 0; i < SIDES; i++) {
      const angle = (2 * Math.PI * i) / SIDES
      pts.push({ x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) })
    }
    return pts
  })
}

/**
 * Build an SVG path `d` string for a polygon-with-holes using the even-odd
 * fill rule. Each subpath (outer + each hole) is a separate "M ... Z" segment.
 *
 * @param {Array<{x: number, y: number}>} outer  - outer boundary
 * @param {Array<Array<{x: number, y: number}>>} holes  - array of hole polygons
 * @returns {string}  SVG path `d` attribute
 */
export function pourToSvgPath(outer, holes) {
  /**
   * @param {Array<{x: number, y: number}>} pts
   * @returns {string}
   */
  function ringToPath(pts) {
    if (!pts || pts.length === 0) return ''
    const start = pts[0]
    let d = `M ${_fmt(start.x)} ${_fmt(start.y)}`
    for (let i = 1; i < pts.length; i++) {
      d += ` L ${_fmt(pts[i].x)} ${_fmt(pts[i].y)}`
    }
    d += ' Z'
    return d
  }

  const parts = []
  if (outer && outer.length > 0) parts.push(ringToPath(outer))
  if (holes) {
    for (const hole of holes) {
      if (hole && hole.length > 0) parts.push(ringToPath(hole))
    }
  }
  return parts.join(' ')
}

/** Format a number for SVG path output — up to 4 decimal places. */
function _fmt(n) {
  if (!Number.isFinite(n)) return '0'
  const s = Number(n.toFixed(4))
  return String(s)
}
