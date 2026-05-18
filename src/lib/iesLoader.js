/**
 * iesLoader.js — Pure-JS IES LM-63 photometric file parser and sampler.
 *
 * Supports the LM-63-1991 (IESNA:LM-63-1991) format commonly used by
 * luminaire manufacturers to describe light distribution.
 *
 * Key exports:
 *   parseIES(text)                      — parse raw IES text → profile object
 *   iesPolarSample(profile, theta, phi) — interpolate candela at a direction
 *   polarPlot2D(profile, angleStep)     — array of (theta_deg, candela) pairs
 *   loadIES(path)                       — fetch + parse from a URL/path
 */

// ── LM-63 data-line tokeniser ─────────────────────────────────────────────────

/**
 * Flatten all whitespace-separated numeric tokens from an array of lines.
 * Lines that are empty or start with '[' (keyword lines) are skipped.
 */
function extractNumbers(lines) {
  const nums = []
  for (const line of lines) {
    const t = line.trim()
    if (!t || t.startsWith('[') || t.startsWith('TILT') || t.startsWith('IESNA')) continue
    for (const tok of t.split(/[\s,]+/)) {
      const n = Number(tok)
      if (tok !== '' && !Number.isNaN(n)) nums.push(n)
    }
  }
  return nums
}

// ── parseIES ──────────────────────────────────────────────────────────────────

/**
 * Parse LM-63-1991 IES text into a structured profile.
 *
 * Returns:
 *   {
 *     vertical_angles:   number[]   — θ values (0 = nadir, 90 = horizontal)
 *     horizontal_angles: number[]   — φ values (0, 90, 180, 270)
 *     candela_grid:      number[][] — [phi_index][theta_index]
 *     lumens:            number     — total lamp lumens (may be -1 = calculated)
 *     width:             number     — luminaire width  (metres)
 *     length:            number     — luminaire length (metres)
 *     height:            number     — luminaire height (metres)
 *   }
 *
 * Throws if mandatory data is absent or malformed.
 */
export function parseIES(text) {
  if (typeof text !== 'string' || !text.trim()) {
    throw new Error('parseIES: text must be a non-empty string')
  }

  const lines = text.split(/\r?\n/)

  // Locate TILT line — everything after it is photometric data
  const tiltIdx = lines.findIndex((l) => /^TILT\s*=/.test(l.trim()))
  if (tiltIdx === -1) {
    throw new Error('parseIES: no TILT= line found — not a valid LM-63 file')
  }

  // TILT=NONE means no separate tilt table; other values (INCLUDE/filename)
  // indicate a tilt table follows the TILT line. We only handle NONE for now.
  const tiltValue = lines[tiltIdx].trim().replace(/^TILT\s*=\s*/, '').toUpperCase()
  const dataStartIdx = tiltValue === 'NONE' ? tiltIdx + 1 : tiltIdx + 1

  const dataLines = lines.slice(dataStartIdx)
  const nums = extractNumbers(dataLines)

  if (nums.length < 10) {
    throw new Error('parseIES: insufficient photometric data after TILT line')
  }

  // LM-63 lamp descriptor line:
  // num_lamps  lumens_per_lamp  multiplier  num_vert  num_horiz
  //   photometric_type  units_type  width  length  height
  let cursor = 0
  const _numLamps        = nums[cursor++]  // eslint-disable-line no-unused-vars
  const lumensPerLamp    = nums[cursor++]
  const multiplier       = nums[cursor++]
  const numVert          = Math.round(nums[cursor++])
  const numHoriz         = Math.round(nums[cursor++])
  const _photometricType = nums[cursor++]  // eslint-disable-line no-unused-vars
  const _unitsType       = nums[cursor++]  // eslint-disable-line no-unused-vars
  const width            = nums[cursor++]
  const length           = nums[cursor++]
  const height           = nums[cursor++]

  if (numVert < 1 || numHoriz < 1) {
    throw new Error(`parseIES: invalid angle counts numVert=${numVert} numHoriz=${numHoriz}`)
  }

  // LM-63-1991: after the lamp descriptor line there is exactly one
  // "ballast factor" value before the vertical angle array begins.
  const _ballastFactor   = nums[cursor++]  // eslint-disable-line no-unused-vars

  // Read vertical angles
  if (cursor + numVert > nums.length) {
    throw new Error('parseIES: not enough data for vertical angles')
  }
  const vertical_angles = nums.slice(cursor, cursor + numVert)
  cursor += numVert

  // Read horizontal angles
  if (cursor + numHoriz > nums.length) {
    throw new Error('parseIES: not enough data for horizontal angles')
  }
  const horizontal_angles = nums.slice(cursor, cursor + numHoriz)
  cursor += numHoriz

  // Read candela values: numHoriz rows × numVert columns
  const totalCandela = numHoriz * numVert
  if (cursor + totalCandela > nums.length) {
    throw new Error(
      `parseIES: not enough candela values (need ${totalCandela}, have ${nums.length - cursor})`
    )
  }

  const candela_grid = []
  for (let h = 0; h < numHoriz; h++) {
    candela_grid.push(nums.slice(cursor, cursor + numVert).map((v) => v * multiplier))
    cursor += numVert
  }

  const lumens = lumensPerLamp < 0 ? -1 : lumensPerLamp

  return {
    vertical_angles,
    horizontal_angles,
    candela_grid,
    lumens,
    width,
    length,
    height,
  }
}

// ── Linear interpolation helper ───────────────────────────────────────────────

/**
 * 1D linear interpolation within a sorted array of (x, y) pairs.
 * Clamps to the first/last value outside the defined range.
 */
function interpolate1D(xs, ys, x) {
  if (xs.length === 0) return 0
  if (x <= xs[0]) return ys[0]
  if (x >= xs[xs.length - 1]) return ys[ys.length - 1]
  // Binary search for bracket
  let lo = 0
  let hi = xs.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (xs[mid] <= x) lo = mid
    else hi = mid
  }
  const t = (x - xs[lo]) / (xs[hi] - xs[lo])
  return ys[lo] + t * (ys[hi] - ys[lo])
}

// ── iesPolarSample ────────────────────────────────────────────────────────────

/**
 * Interpolate the candela intensity at direction (theta_deg, phi_deg).
 *
 * @param  {object} profile   — result of parseIES
 * @param  {number} theta_deg — vertical angle in degrees (0 = nadir/downward axis)
 * @param  {number} phi_deg   — horizontal angle in degrees (0 = reference plane)
 * @returns {number}           candela value (cd)
 */
export function iesPolarSample(profile, theta_deg, phi_deg) {
  if (!profile || !profile.candela_grid) {
    throw new Error('iesPolarSample: invalid profile')
  }

  const { vertical_angles, horizontal_angles, candela_grid } = profile

  // Normalise phi to [0, 360)
  let phi = ((phi_deg % 360) + 360) % 360

  // For symmetric distributions (single horizontal angle = 0), phi doesn't matter.
  if (horizontal_angles.length === 1) {
    return interpolate1D(vertical_angles, candela_grid[0], theta_deg)
  }

  // Fold phi into the defined horizontal range (IES files typically cover
  // 0–90, 0–180, or 0–360). Mirror symmetry is assumed outside defined range.
  const maxPhi = horizontal_angles[horizontal_angles.length - 1]
  if (maxPhi <= 90) {
    // Quarter-plane symmetry
    phi = phi % 90
  } else if (maxPhi <= 180) {
    // Half-plane symmetry
    if (phi > 180) phi = 360 - phi
  }
  // clamp to defined range
  phi = Math.max(horizontal_angles[0], Math.min(maxPhi, phi))

  // Find bracketing horizontal planes
  let phiLo = 0
  let phiHi = horizontal_angles.length - 1
  while (phiHi - phiLo > 1) {
    const mid = (phiLo + phiHi) >> 1
    if (horizontal_angles[mid] <= phi) phiLo = mid
    else phiHi = mid
  }

  // Interpolate candela along theta for each bounding phi plane
  const cdLo = interpolate1D(vertical_angles, candela_grid[phiLo], theta_deg)
  const cdHi = interpolate1D(vertical_angles, candela_grid[phiHi], theta_deg)

  // Interpolate between the two phi planes
  const phiRange = horizontal_angles[phiHi] - horizontal_angles[phiLo]
  if (phiRange === 0) return cdLo
  const t = (phi - horizontal_angles[phiLo]) / phiRange
  return cdLo + t * (cdHi - cdLo)
}

// ── polarPlot2D ───────────────────────────────────────────────────────────────

/**
 * Generate a 2D polar plot of the candela distribution at phi=0.
 *
 * @param  {object} profile         — result of parseIES
 * @param  {number} [angleStep=5]   — step size in degrees
 * @returns {{ theta_deg: number, candela: number }[]}
 */
export function polarPlot2D(profile, angleStep = 5) {
  if (!profile || !profile.candela_grid) {
    throw new Error('polarPlot2D: invalid profile')
  }
  if (typeof angleStep !== 'number' || angleStep <= 0) {
    throw new Error('polarPlot2D: angleStep must be a positive number')
  }

  const maxTheta = profile.vertical_angles[profile.vertical_angles.length - 1]
  const results = []
  for (let theta = 0; theta <= maxTheta + 1e-9; theta += angleStep) {
    const t = Math.min(theta, maxTheta)
    results.push({
      theta_deg: t,
      candela: iesPolarSample(profile, t, 0),
    })
  }
  return results
}

// ── loadIES ───────────────────────────────────────────────────────────────────

/**
 * Fetch an IES file from a URL or path and parse it.
 *
 * @param  {string} path  — URL or path string accepted by fetch()
 * @returns {Promise<object>}  parsed profile
 */
export async function loadIES(path) {
  if (typeof path !== 'string' || !path.trim()) {
    throw new Error('loadIES: path must be a non-empty string')
  }
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`loadIES: failed to fetch "${path}" — HTTP ${response.status}`)
  }
  const text = await response.text()
  return parseIES(text)
}
