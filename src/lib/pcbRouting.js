// pcbRouting.js — Pure geometry helpers for manual PCB trace routing.
// No React or browser imports — safe to use in vitest and workers.

// ─── Internal geometry primitives ────────────────────────────────────────────

function dist2(a, b) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  return Math.sqrt(dx * dx + dy * dy)
}

function ptEq(a, b, tol = 1e-9) {
  return Math.abs(a.x - b.x) <= tol && Math.abs(a.y - b.y) <= tol
}

/**
 * Minimum distance from point p to segment [a, b].
 */
export function pointToSegmentDist(p, a, b) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const lenSq = dx * dx + dy * dy
  if (lenSq === 0) {
    return dist2(p, a)
  }
  const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lenSq))
  return dist2(p, { x: a.x + t * dx, y: a.y + t * dy })
}

/**
 * Project p onto segment [a, b]; return the t parameter in [0,1].
 */
function projectOntoSegment(p, a, b) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const lenSq = dx * dx + dy * dy
  if (lenSq === 0) return 0
  return Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lenSq))
}

// ─── orthogonalSnap ───────────────────────────────────────────────────────────

/**
 * Snap p2 so the segment p1→p2 is horizontal or vertical.
 *
 * When `lastDirection` is provided, that axis is preferred in a tie.
 *
 * @param {{x: number, y: number}} p1
 * @param {{x: number, y: number}} p2
 * @param {'horizontal'|'vertical'|undefined} lastDirection
 * @returns {{ p2_snapped: {x: number, y: number}, direction: 'horizontal'|'vertical' }}
 */
export function orthogonalSnap(p1, p2, lastDirection) {
  // Guard: identical points
  if (!p1 || !p2) {
    const pt = p2 || p1 || { x: 0, y: 0 }
    return { p2_snapped: { x: pt.x, y: pt.y }, direction: lastDirection || 'horizontal' }
  }

  const dx = Math.abs(p2.x - p1.x)
  const dy = Math.abs(p2.y - p1.y)

  let direction
  if (dx > dy) {
    direction = 'horizontal'
  } else if (dy > dx) {
    direction = 'vertical'
  } else {
    // Tie — prefer lastDirection, else horizontal
    direction = lastDirection || 'horizontal'
  }

  const p2_snapped =
    direction === 'horizontal'
      ? { x: p2.x, y: p1.y }
      : { x: p1.x, y: p2.y }

  return { p2_snapped, direction }
}

// ─── corner45 ────────────────────────────────────────────────────────────────

/**
 * Generate a 45°-preferred two-segment route from p1 to p2.
 * Returns [mid, p2] where mid is the bend point that minimises total length.
 *
 * Special cases (already 45° or already axis-aligned) return [p2] — one
 * segment, no bend.
 *
 * Strategy: the bend can be placed at the "horizontal-first" position
 * (go 45° then straight in x) or the "vertical-first" position (go 45°
 * then straight in y). Pick whichever gives a shorter total path — they are
 * always equal in this scheme, so we use horizontal-first as default.
 *
 * @param {{x: number, y: number}} p1
 * @param {{x: number, y: number}} p2
 * @returns {Array<{x: number, y: number}>}
 */
export function corner45(p1, p2) {
  if (!p1 || !p2) return [p2 || p1 || { x: 0, y: 0 }]

  const dx = p2.x - p1.x
  const dy = p2.y - p1.y
  const adx = Math.abs(dx)
  const ady = Math.abs(dy)

  // Zero-length or already pure axis-aligned or already 45°
  if (adx === 0 || ady === 0 || adx === ady) {
    return [{ x: p2.x, y: p2.y }]
  }

  const sx = dx > 0 ? 1 : -1
  const sy = dy > 0 ? 1 : -1

  // Candidate A: 45° diagonal first, then straight along dominant axis
  // Candidate B: straight along recessive axis first, then 45° diagonal
  // Both have the same total length. We choose A (diagonal first) as default.

  let mid
  if (adx > ady) {
    // Longer in X — start 45°, then horizontal
    mid = { x: p1.x + sx * ady, y: p1.y + sy * ady }
  } else {
    // Longer in Y — start 45°, then vertical
    mid = { x: p1.x + sx * adx, y: p1.y + sy * adx }
  }

  return [mid, { x: p2.x, y: p2.y }]
}

// ─── freeRoute ────────────────────────────────────────────────────────────────

/**
 * Straight-line route from p1 to p2.
 *
 * @param {{x: number, y: number}} p1
 * @param {{x: number, y: number}} p2
 * @returns {Array<{x: number, y: number}>}
 */
export function freeRoute(p1, p2) {
  if (!p2) return []
  return [{ x: p2.x, y: p2.y }]
}

// ─── pickRoutingMode ──────────────────────────────────────────────────────────

/**
 * Dispatch to the correct routing helper based on `mode`.
 *
 * @param {'orthogonal'|'45'|'free'} mode
 * @param {{x: number, y: number}} p1
 * @param {{x: number, y: number}} p2
 * @param {'horizontal'|'vertical'|undefined} lastDirection  — passed through to orthogonalSnap
 * @returns {Array<{x: number, y: number}>|{ p2_snapped: {x,y}, direction: string }}
 */
export function pickRoutingMode(mode, p1, p2, lastDirection) {
  switch (mode) {
    case 'orthogonal':
      return orthogonalSnap(p1, p2, lastDirection)
    case '45':
      return corner45(p1, p2)
    case 'free':
      return freeRoute(p1, p2)
    default:
      return freeRoute(p1, p2)
  }
}

// ─── splitTraceAtPoint ────────────────────────────────────────────────────────

/**
 * Split a trace at a point near one of its segments. Returns [traceA, traceB]
 * where traceA ends at the split point and traceB starts from it. The union
 * of both traces covers the same total polyline length.
 *
 * @param {{ id: string, points: Array<{x,y}>, net_id: string, [string]: any }} trace
 * @param {{x: number, y: number}} point
 * @param {number} tolerance
 * @returns {[object, object]|null}  null if no segment within tolerance found
 */
export function splitTraceAtPoint(trace, point, tolerance = 0.1) {
  if (!trace || !trace.points || trace.points.length < 2) return null
  if (!point) return null

  const pts = trace.points
  let bestSegIdx = -1
  let bestDist = Infinity

  for (let i = 0; i < pts.length - 1; i++) {
    const d = pointToSegmentDist(point, pts[i], pts[i + 1])
    if (d < bestDist) {
      bestDist = d
      bestSegIdx = i
    }
  }

  if (bestSegIdx === -1 || bestDist > tolerance) return null

  const a = pts[bestSegIdx]
  const b = pts[bestSegIdx + 1]

  // Snap the split point onto the segment
  const t = projectOntoSegment(point, a, b)
  const snap = {
    x: a.x + t * (b.x - a.x),
    y: a.y + t * (b.y - a.y),
  }

  // If the snap lands on an existing endpoint, bail — can't split at an endpoint
  if (ptEq(snap, a, tolerance) || ptEq(snap, b, tolerance)) return null

  const base = { net_id: trace.net_id, width_mm: trace.width_mm, layer: trace.layer }

  const traceA = {
    ...base,
    id: trace.id ? `${trace.id}_a` : undefined,
    points: [...pts.slice(0, bestSegIdx + 1), snap],
  }
  const traceB = {
    ...base,
    id: trace.id ? `${trace.id}_b` : undefined,
    points: [snap, ...pts.slice(bestSegIdx + 1)],
  }

  return [traceA, traceB]
}

// ─── detectTJunction ─────────────────────────────────────────────────────────

/**
 * Find any trace in `traces` whose interior (non-endpoint) passes through
 * `vertex` on the SAME net. Returns the matching trace id, or null.
 *
 * "SAME net" means `trace.net_id === vertex_net_id`. Pass `vertex` as
 * `{x, y, net_id}` or pass `net_id` as a separate argument.
 *
 * Overload:
 *   detectTJunction(traces, vertex, tolerance)
 *   detectTJunction(segA, segB, point, tol)  ← legacy two-segment form
 *
 * @param {Array<{id, points, net_id}>} traces
 * @param {{x: number, y: number, net_id?: string}} vertex
 * @param {number} tolerance
 * @returns {string|null}
 */
export function detectTJunction(traces, vertex, tolerance = 0.1) {
  // Legacy two-argument segment form: detectTJunction(segA, segB, point, tol)
  if (
    traces &&
    !Array.isArray(traces) &&
    typeof traces.x === 'number' &&
    typeof vertex.x === 'number'
  ) {
    const segA = traces
    const segB = vertex
    const p = tolerance
    const tol = arguments[3] !== undefined ? arguments[3] : 0.1
    return _detectTJunctionSegment(segA, segB, p, tol)
  }

  if (!Array.isArray(traces) || traces.length === 0) return null
  if (!vertex) return null

  const netId = vertex.net_id

  for (const trace of traces) {
    if (netId !== undefined && trace.net_id !== netId) continue
    const pts = trace.points
    if (!pts || pts.length < 2) continue

    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i]
      const b = pts[i + 1]

      // Check if vertex is within tolerance of this segment
      const d = pointToSegmentDist(vertex, a, b)
      if (d > tolerance) continue

      // Exclude if it's at an endpoint of the whole trace
      const atStart = ptEq(vertex, pts[0], tolerance)
      const atEnd = ptEq(vertex, pts[pts.length - 1], tolerance)
      if (atStart || atEnd) continue

      return trace.id ?? null
    }
  }

  return null
}

/** @private Legacy two-point-segment form used by existing tests */
function _detectTJunctionSegment(segA, segB, p, tol) {
  const distToA = dist2(p, segA)
  const distToB = dist2(p, segB)
  if (distToA < tol || distToB < tol) {
    return { hit: false, point: { x: p.x, y: p.y } }
  }
  const d = pointToSegmentDist(p, segA, segB)
  if (d <= tol) {
    const dx = segB.x - segA.x
    const dy = segB.y - segA.y
    const lenSq = dx * dx + dy * dy
    const t = lenSq > 0
      ? Math.max(0, Math.min(1, ((p.x - segA.x) * dx + (p.y - segA.y) * dy) / lenSq))
      : 0
    return { hit: true, point: { x: segA.x + t * dx, y: segA.y + t * dy } }
  }
  return { hit: false, point: { x: p.x, y: p.y } }
}

// ─── mergeTraces ──────────────────────────────────────────────────────────────

/**
 * Merge traces that share endpoints AND are on the same net. Returns a new
 * array with merged traces; idempotent (calling again produces the same
 * result).
 *
 * Refuses to merge traces on different nets (different net_id).
 *
 * @param {Array<{id, points, net_id, [string]: any}>} traces
 * @param {number} tolerance
 * @returns {Array<object>}
 */
export function mergeTraces(traces, tolerance = 0.1) {
  if (!Array.isArray(traces) || traces.length === 0) return []

  // Work on a mutable copy keyed by index
  let working = traces.map((t, i) => ({ ...t, _idx: i }))
  let merged = true

  while (merged) {
    merged = false
    outer:
    for (let i = 0; i < working.length; i++) {
      for (let j = i + 1; j < working.length; j++) {
        const a = working[i]
        const b = working[j]

        // Must be same net
        if (a.net_id !== b.net_id) continue

        const ptsA = a.points
        const ptsB = b.points
        if (!ptsA || !ptsB || ptsA.length < 2 || ptsB.length < 2) continue

        const aStart = ptsA[0]
        const aEnd = ptsA[ptsA.length - 1]
        const bStart = ptsB[0]
        const bEnd = ptsB[ptsB.length - 1]

        let mergedPoints = null

        if (ptEq(aEnd, bStart, tolerance)) {
          // a → b
          mergedPoints = [...ptsA, ...ptsB.slice(1)]
        } else if (ptEq(aStart, bEnd, tolerance)) {
          // b → a
          mergedPoints = [...ptsB, ...ptsA.slice(1)]
        } else if (ptEq(aEnd, bEnd, tolerance)) {
          // a → reverse(b)
          mergedPoints = [...ptsA, ...[...ptsB].reverse().slice(1)]
        } else if (ptEq(aStart, bStart, tolerance)) {
          // reverse(a) → b
          mergedPoints = [...[...ptsA].reverse(), ...ptsB.slice(1)]
        }

        if (mergedPoints) {
          const newTrace = {
            ...a,
            points: mergedPoints,
            id: a.id || b.id,
          }
          delete newTrace._idx
          // Replace a, remove b
          working.splice(j, 1)
          working[i] = newTrace
          merged = true
          break outer
        }
      }
    }
  }

  // Strip internal bookkeeping
  return working.map(({ _idx, ...rest }) => rest)
}
