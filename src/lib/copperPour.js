// copperPour.js — Pure geometry helpers for copper pour rendering.
// No React or browser imports — safe to use in vitest and workers.

const VALID_LAYERS = ['top_copper', 'bottom_copper', 'inner_1', 'inner_2']

/**
 * Validate a copper pour object. Returns { ok: boolean, errors: string[] }.
 *
 * @param {object} pour
 * @returns {{ ok: boolean, errors: string[] }}
 */
export function validatePour(pour) {
  const errors = []
  if (!pour || typeof pour !== 'object') {
    return { ok: false, errors: ['pour must be an object'] }
  }
  if (pour.type !== 'copper_pour') {
    errors.push('type must be "copper_pour"')
  }
  if (!Array.isArray(pour.polygon) || pour.polygon.length < 3) {
    errors.push('polygon must be an array of at least 3 {x, y} points')
  } else {
    for (let i = 0; i < pour.polygon.length; i++) {
      const pt = pour.polygon[i]
      if (typeof pt.x !== 'number' || typeof pt.y !== 'number') {
        errors.push(`polygon[${i}] must have numeric x and y`)
      }
    }
  }
  if (!pour.layer) {
    errors.push('layer is required')
  } else if (!VALID_LAYERS.includes(pour.layer)) {
    errors.push(`layer must be one of: ${VALID_LAYERS.join(', ')}`)
  }
  if (!pour.net_id || typeof pour.net_id !== 'string') {
    errors.push('net_id must be a non-empty string')
  }
  if (pour.clearance_mm !== undefined && typeof pour.clearance_mm !== 'number') {
    errors.push('clearance_mm must be a number')
  }
  if (pour.min_thickness_mm !== undefined && typeof pour.min_thickness_mm !== 'number') {
    errors.push('min_thickness_mm must be a number')
  }
  if (pour.priority !== undefined && typeof pour.priority !== 'number') {
    errors.push('priority must be a number')
  }
  if (pour.thermal_relief !== undefined) {
    const tr = pour.thermal_relief
    if (typeof tr !== 'object' || tr === null) {
      errors.push('thermal_relief must be an object')
    } else {
      if (tr.gap !== undefined && typeof tr.gap !== 'number') errors.push('thermal_relief.gap must be a number')
      if (tr.spoke_width !== undefined && typeof tr.spoke_width !== 'number') errors.push('thermal_relief.spoke_width must be a number')
      if (tr.spoke_count !== undefined && (!Number.isInteger(tr.spoke_count) || tr.spoke_count < 2)) errors.push('thermal_relief.spoke_count must be an integer >= 2')
    }
  }
  return { ok: errors.length === 0, errors }
}

/**
 * Generate thermal relief spokes connecting a pad to the surrounding pour.
 * Returns an array of line segments { x1, y1, x2, y2 }.
 *
 * @param {object} pour           - pour object (for context; unused directly here)
 * @param {{ x: number, y: number }} padCenter
 * @param {number} padRadius      - pad radius in mm
 * @param {number} spokeCount     - number of spokes (typically 4)
 * @param {number} spokeWidth     - width of each spoke in mm
 * @param {number} gap            - gap between pad edge and start of spoke in mm
 * @returns {Array<{ x1: number, y1: number, x2: number, y2: number }>}
 */
export function thermalReliefSpokes(pour, padCenter, padRadius, spokeCount, spokeWidth, gap) {
  const cx = padCenter.x
  const cy = padCenter.y
  const spokes = []
  const count = Math.max(2, Math.round(spokeCount))
  for (let i = 0; i < count; i++) {
    const angle = (2 * Math.PI * i) / count
    const x1 = cx + (padRadius + gap) * Math.cos(angle)
    const y1 = cy + (padRadius + gap) * Math.sin(angle)
    const x2 = cx + (padRadius + gap + spokeWidth * 4) * Math.cos(angle)
    const y2 = cy + (padRadius + gap + spokeWidth * 4) * Math.sin(angle)
    spokes.push({ x1, y1, x2, y2 })
  }
  return spokes
}

/**
 * Merge pours that share the same net_id and layer, combining overlapping polygons.
 * Non-overlapping pours on the same net/layer are left as separate entries.
 * Returns a new array (does not mutate input).
 *
 * @param {Array<object>} pours
 * @returns {Array<object>}
 */
export function mergePours(pours) {
  if (!Array.isArray(pours) || pours.length === 0) return []

  // Group by net_id + layer
  const groups = new Map()
  for (const pour of pours) {
    const key = `${pour.net_id}::${pour.layer}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(pour)
  }

  const result = []
  for (const [, group] of groups) {
    if (group.length === 1) {
      result.push(group[0])
      continue
    }
    // Try to merge overlapping polygons within the group
    // Use a simple union: repeatedly merge polygons that share any vertex proximity
    const merged = _mergePolygonGroup(group)
    result.push(...merged)
  }
  return result
}

/**
 * Attempt to union overlapping polygons in a group of same-net/layer pours.
 * Uses a bounding-box overlap test to identify candidates, then builds a
 * convex hull approximation for merged pairs. Non-overlapping pours are kept separate.
 *
 * @param {Array<object>} group
 * @returns {Array<object>}
 */
function _mergePolygonGroup(group) {
  // Work with mutable copies; track which have been consumed
  const remaining = group.map((p, i) => ({ ...p, _idx: i }))
  const out = []

  while (remaining.length > 0) {
    let base = remaining.shift()
    let merged = true
    while (merged) {
      merged = false
      for (let i = 0; i < remaining.length; i++) {
        if (_polygonsOverlap(base.polygon, remaining[i].polygon)) {
          // Merge: convex hull of combined vertices as approximation
          const combined = [...base.polygon, ...remaining[i].polygon]
          base = { ...base, polygon: _convexHull(combined) }
          remaining.splice(i, 1)
          merged = true
          break
        }
      }
    }
    const { _idx, ...clean } = base
    out.push(clean)
  }
  return out
}

/** Axis-aligned bounding-box overlap test for two polygons. */
function _polygonsOverlap(a, b) {
  const aMinX = Math.min(...a.map(p => p.x))
  const aMaxX = Math.max(...a.map(p => p.x))
  const aMinY = Math.min(...a.map(p => p.y))
  const aMaxY = Math.max(...a.map(p => p.y))
  const bMinX = Math.min(...b.map(p => p.x))
  const bMaxX = Math.max(...b.map(p => p.x))
  const bMinY = Math.min(...b.map(p => p.y))
  const bMaxY = Math.max(...b.map(p => p.y))
  return aMinX <= bMaxX && aMaxX >= bMinX && aMinY <= bMaxY && aMaxY >= bMinY
}

/**
 * Compute 2D convex hull (Andrew's monotone chain).
 * Returns CCW-wound polygon vertices.
 *
 * @param {Array<{x: number, y: number}>} pts
 * @returns {Array<{x: number, y: number}>}
 */
function _convexHull(pts) {
  const sorted = [...pts].sort((a, b) => a.x !== b.x ? a.x - b.x : a.y - b.y)
  if (sorted.length <= 2) return sorted

  function cross(O, A, B) {
    return (A.x - O.x) * (B.y - O.y) - (A.y - O.y) * (B.x - O.x)
  }

  const lower = []
  for (const p of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop()
    lower.push(p)
  }
  const upper = []
  for (let i = sorted.length - 1; i >= 0; i--) {
    const p = sorted[i]
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop()
    upper.push(p)
  }
  // Remove last point of each half because it's repeated
  lower.pop()
  upper.pop()
  return [...lower, ...upper]
}

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
