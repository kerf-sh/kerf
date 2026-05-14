// helixGeom.js — Pure JS helix polyline generator for in-browser preview.
// No React or browser globals — safe for vitest and Web Workers.

/**
 * Generate a polyline approximation of a helix.
 *
 * @param {object} opts
 * @param {number}  opts.pitch           Axial distance per full turn (mm). Must be > 0.
 * @param {number}  opts.height          Total axial height (mm). Must be > 0.
 * @param {number}  opts.radius          Base coil radius (mm). Must be > 0.
 * @param {string}  [opts.direction]     'right' (CCW from above) or 'left' (CW). Default 'right'.
 * @param {number}  [opts.coneHalfAngleDeg] Half-angle of taper in degrees. 0 = cylindrical. Default 0.
 * @param {number}  [opts.segments]      Line segments per full turn. Default 64.
 * @returns {Array<{x: number, y: number, z: number}>} Ordered point array from z=0 to z=height.
 *   Returns an empty array if any required parameter is invalid.
 */
export function helixPolyline({
  pitch,
  height,
  radius,
  direction = 'right',
  coneHalfAngleDeg = 0,
  segments = 64,
} = {}) {
  if (!pitch || pitch <= 0) return []
  if (!height || height <= 0) return []
  if (!radius || radius <= 0) return []
  if (!Number.isFinite(segments) || segments < 3) return []

  const turns = height / pitch
  const totalPoints = Math.max(Math.ceil(turns * segments) + 1, 2)
  const sign = direction === 'left' ? -1 : 1
  const coneRad = (coneHalfAngleDeg * Math.PI) / 180

  const pts = []
  for (let i = 0; i < totalPoints; i++) {
    const t = i / (totalPoints - 1)        // 0..1
    const z = t * height
    const angle = sign * 2 * Math.PI * t * turns
    const r = radius + z * Math.tan(coneRad)
    pts.push({
      x: r * Math.cos(angle),
      y: r * Math.sin(angle),
      z,
    })
  }

  return pts
}
