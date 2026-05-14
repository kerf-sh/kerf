// pcbRouting.js — Pure geometry helpers for manual PCB trace routing.
// No React or browser imports — safe to use in vitest and workers.

/**
 * Snap a cursor position to the nearest orthogonal (90°-only) candidate
 * from the previous point. Horizontal is preferred when dx === dy.
 *
 * @param {{x: number, y: number}} prev  - last placed vertex
 * @param {{x: number, y: number}} cursor - raw mouse position
 * @returns {{x: number, y: number}}
 */
export function orthogonalSnap(prev, cursor) {
  const dx = Math.abs(cursor.x - prev.x)
  const dy = Math.abs(cursor.y - prev.y)
  if (dx >= dy) {
    // Horizontal: keep prev.y
    return { x: cursor.x, y: prev.y }
  } else {
    // Vertical: keep prev.x
    return { x: prev.x, y: cursor.y }
  }
}

/**
 * Generate 45° corner points between prev and cursor.
 * Returns an array of intermediate + final points so the path bends at 45°.
 *
 * Strategy:
 *   - If dx === dy (already 45°) or one dimension is 0 (already orthogonal),
 *     return [cursor] directly.
 *   - Otherwise emit a bend point at 45° followed by the cursor.
 *     When dx > dy: travel 45° for `dy` units horizontally+vertically, then
 *     straight horizontally to the cursor.
 *     When dy > dx: travel 45° for `dx` units, then straight vertically.
 *
 * @param {{x: number, y: number}} prev
 * @param {{x: number, y: number}} cursor
 * @returns {Array<{x: number, y: number}>}
 */
export function corner45(prev, cursor) {
  const dx = cursor.x - prev.x
  const dy = cursor.y - prev.y
  const adx = Math.abs(dx)
  const ady = Math.abs(dy)

  // Already 45° or pure horizontal/vertical — no bend needed
  if (adx === ady || adx === 0 || ady === 0) {
    return [{ x: cursor.x, y: cursor.y }]
  }

  const sx = dx > 0 ? 1 : -1
  const sy = dy > 0 ? 1 : -1

  if (adx > ady) {
    // Longer in X: start with a 45° segment (length ady), then continue horizontal
    const bendX = prev.x + sx * ady
    const bendY = prev.y + sy * ady
    return [
      { x: bendX, y: bendY },
      { x: cursor.x, y: cursor.y },
    ]
  } else {
    // Longer in Y: start with a 45° segment (length adx), then continue vertical
    const bendX = prev.x + sx * adx
    const bendY = prev.y + sy * adx
    return [
      { x: bendX, y: bendY },
      { x: cursor.x, y: cursor.y },
    ]
  }
}

/**
 * Compute the minimum distance from point p to segment [a, b].
 *
 * @param {{x: number, y: number}} p
 * @param {{x: number, y: number}} a  - segment start
 * @param {{x: number, y: number}} b  - segment end
 * @returns {number}
 */
export function pointToSegmentDist(p, a, b) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const lenSq = dx * dx + dy * dy
  if (lenSq === 0) {
    // Degenerate segment — distance to point a
    return Math.hypot(p.x - a.x, p.y - a.y)
  }
  // Parameter t: projection of p onto the line through a,b (clamped to [0,1])
  const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lenSq))
  const closestX = a.x + t * dx
  const closestY = a.y + t * dy
  return Math.hypot(p.x - closestX, p.y - closestY)
}

/**
 * Detect whether point p lies on segment [segA, segB] within tolerance `tol`,
 * excluding the endpoints (those are continuations, not T-junctions).
 *
 * @param {{x: number, y: number}} segA  - segment start
 * @param {{x: number, y: number}} segB  - segment end
 * @param {{x: number, y: number}} p     - point to test
 * @param {number} [tol=0.1]             - tolerance in mm
 * @returns {{ hit: boolean, point: {x: number, y: number} }}
 */
export function detectTJunction(segA, segB, p, tol = 0.1) {
  // Exclude endpoints
  const distToA = Math.hypot(p.x - segA.x, p.y - segA.y)
  const distToB = Math.hypot(p.x - segB.x, p.y - segB.y)
  if (distToA < tol || distToB < tol) {
    return { hit: false, point: { x: p.x, y: p.y } }
  }

  const dist = pointToSegmentDist(p, segA, segB)
  if (dist <= tol) {
    // Snap p to the closest point on segment for the returned junction point
    const dx = segB.x - segA.x
    const dy = segB.y - segA.y
    const lenSq = dx * dx + dy * dy
    const t = lenSq > 0
      ? Math.max(0, Math.min(1, ((p.x - segA.x) * dx + (p.y - segA.y) * dy) / lenSq))
      : 0
    return {
      hit: true,
      point: { x: segA.x + t * dx, y: segA.y + t * dy },
    }
  }
  return { hit: false, point: { x: p.x, y: p.y } }
}
