/**
 * Tolerance stack-up algorithms: worst-case, RSS, and Monte-Carlo.
 * Pure functions suitable for use in both the main thread and Web Workers.
 */

/**
 * @typedef {Object} ToleranceDim
 * @property {number} nominal
 * @property {number} [plus]
 * @property {number} [minus]
 * @property {number} [upper]
 * @property {number} [lower]
 * @property {string} [grade]
 * @property {string} [distribution] - "normal" | "uniform" | "triangular"
 * @property {string} [unit]
 */

/**
 * @typedef {Object} WorstCaseResult
 * @property {string} method - "worst_case"
 * @property {number} nominal
 * @property {number} max
 * @property {number} min
 */

/**
 * @typedef {Object} RSSResult
 * @property {string} method - "rss"
 * @property {number} nominal
 * @property {number} band
 * @property {number} k
 */

/**
 * @typedef {Object} StackResult
 * @property {string} method - "worst_case+rss"
 * @property {number} nominal
 * @property {number} max
 * @property {number} min
 * @property {number} band
 */

/**
 * @typedef {Object} MonteCarloResult
 * @property {string} method - "monte_carlo"
 * @property {number} samples
 * @property {number} nominal
 * @property {number} p01
 * @property {number} p50
 * @property {number} p99
 * @property {number} mean
 * @property {number} std_dev
 * @property {number[]} histogram
 * @property {number[]} bin_edges
 */

const IT_GRADES = {
  IT01: 0.0003,
  IT0: 0.0005,
  IT1: 0.0008,
  IT2: 0.0012,
  IT3: 0.002,
  IT4: 0.003,
  IT5: 0.004,
  IT6: 0.006,
  IT7: 0.010,
  IT8: 0.014,
  IT9: 0.025,
  IT10: 0.040,
  IT11: 0.060,
  IT12: 0.100,
  IT13: 0.140,
  IT14: 0.250,
  IT15: 0.400,
  IT16: 0.630,
}

function gradeToTolerance(grade) {
  return IT_GRADES[grade] ?? 0
}

function hasField(d, key) {
  return d[key] !== undefined && d[key] !== null
}

function parseDim(d, defaultUnit = 'mm') {
  const tol = {
    nominal: Number(d.nominal) || 0,
    plus: 0,
    minus: 0,
    unit: d.unit || defaultUnit,
  }
  if (hasField(d, 'plus')) {
    tol.plus = Number(d.plus)
  }
  if (hasField(d, 'minus')) {
    tol.minus = Number(d.minus)
  }
  if (!hasField(d, 'plus') && hasField(d, 'upper')) {
    tol.plus = Number(d.upper) - tol.nominal
  }
  if (!hasField(d, 'minus') && hasField(d, 'lower')) {
    tol.minus = tol.nominal - Number(d.lower)
  }
  if (!hasField(d, 'plus') && !hasField(d, 'minus') && !hasField(d, 'upper') && !hasField(d, 'lower') && d.grade) {
    const g = gradeToTolerance(d.grade)
    tol.plus = g
    tol.minus = g
  }
  return tol
}

/**
 * Worst-case tolerance stack-up.
 * nominal = Σnominal
 * max = Σ(nominal + plus)
 * min = Σ(nominal − minus)
 * @param {ToleranceDim[]} dims
 * @returns {WorstCaseResult}
 */
export function worstCaseStack(dims) {
  let nominal = 0
  let max = 0
  let min = 0
  for (const d of dims) {
    const t = parseDim(d)
    nominal += t.nominal
    max += t.nominal + t.plus
    min += t.nominal - t.minus
  }
  return { method: 'worst_case', nominal, max, min }
}

/**
 * Root-Sum-Square tolerance stack-up.
 * nominal = Σnominal
 * band = k × √(Σ((plus + minus)/2)²)
 * @param {ToleranceDim[]} dims
 * @param {number} [k=3] - coverage factor (3 for 99.73%, 2.45 for 99%, 1.96 for 95%)
 * @returns {RSSResult}
 */
export function rssStack(dims, k = 3) {
  let nominal = 0
  let sumSquares = 0
  for (const d of dims) {
    const t = parseDim(d)
    nominal += t.nominal
    const half = (t.plus + t.minus) / 2
    sumSquares += half * half
  }
  const band = k * Math.sqrt(sumSquares)
  return { method: 'rss', nominal, band, k }
}

/**
 * Combined worst-case + RSS stack-up result.
 * @param {ToleranceDim[]} dims
 * @param {number} [k=3]
 * @returns {StackResult}
 */
export function stackup(dims, k = 3) {
  const wc = worstCaseStack(dims)
  const rss = rssStack(dims, k)
  return {
    method: 'worst_case+rss',
    nominal: wc.nominal,
    max: wc.max,
    min: wc.min,
    band: rss.band,
  }
}

/**
 * Sample a single dimension value from a distribution.
 * @param {Random} rng - seeded PRNG with float64 method
 * @param {number} nominal
 * @param {number} halfPlus
 * @param {number} halfMinus
 * @param {string} distribution - "normal" | "uniform" | "triangular"
 * @returns {number}
 */
function sampleDim(rng, nominal, halfPlus, halfMinus, distribution) {
  const lo = nominal - halfMinus
  const hi = nominal + halfPlus
  switch (distribution) {
    case 'uniform':
      return lo + rng() * (hi - lo)
    case 'triangular': {
      const mode = (lo + hi) / 2
      const u = rng()
      const sqrtU = Math.sqrt(u)
      if (u < (hi - mode) / (hi - lo)) {
        return lo + sqrtU * (mode - lo)
      }
      return hi - sqrtU * (hi - mode)
    }
    default: {
      const span = halfPlus + halfMinus
      return nominal + (rng() * 2 - 1) * span
    }
  }
}

function quickSelect(arr, k) {
  const A = [...arr]
  function partition(low, high, pivot) {
    const piv = A[pivot]
    ;[A[pivot], A[high]] = [A[high], A[pivot]]
    let i = low
    for (let j = low; j < high; j++) {
      if (A[j] < piv) {
        ;[A[i], A[j]] = [A[j], A[i]]
        i++
      }
    }
    ;[A[i], A[high]] = [A[high], A[i]]
    return i
  }
  function select(low, high, k) {
    if (low === high) return A[low]
    const pivot = low + Math.floor(Math.random() * (high - low + 1))
    const p = partition(low, high, pivot)
    if (k === p) return A[k]
    if (k < p) return select(low, p - 1, k)
    return select(p + 1, high, k)
  }
  return select(0, A.length - 1, k)
}

function percentile(arr, q) {
  const sorted = [...arr].sort((a, b) => a - b)
  const pos = (sorted.length - 1) * q
  const lo = Math.floor(pos)
  const hi = Math.ceil(pos)
  if (lo === hi) return sorted[lo]
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo)
}

function buildHistogram(values, bins) {
  let min = values[0]
  let max = values[0]
  for (const v of values) {
    if (v < min) min = v
    if (v > max) max = v
  }
  if (max === min) max = min + 1
  const binWidth = (max - min) / bins
  const counts = new Array(bins).fill(0)
  for (const v of values) {
    let bin = Math.floor((v - min) / binWidth)
    if (bin >= bins) bin = bins - 1
    if (bin < 0) bin = 0
    counts[bin]++
  }
  const edges = []
  for (let i = 0; i <= bins; i++) {
    edges.push(min + i * binWidth)
  }
  return { histogram: counts, binEdges: edges }
}

/**
 * Monte-Carlo tolerance stack-up.
 * @param {ToleranceDim[]} dims
 * @param {Object} [opts]
 * @param {number} [opts.samples=10000]
 * @param {string} [opts.unit='mm']
 * @param {Function} [opts.rng] - optional RNG function returning float in [0,1); defaults to Math.random
 * @returns {MonteCarloResult}
 */
export function monteCarloStack(dims, { samples = 10000, unit = 'mm', rng = Math.random } = {}) {
  if (!dims || dims.length === 0) {
    throw new Error('at least one dimension is required')
  }
  const n = Math.min(Math.max(1, samples), 1_000_000)
  const parsed = dims.map(d => {
    const t = parseDim(d, unit)
    return {
      nominal: t.nominal,
      halfPlus: t.plus / 2,
      halfMinus: t.minus / 2,
      distribution: d.distribution || 'normal',
      unit: t.unit,
    }
  })
  const nominal = parsed.reduce((s, d) => s + d.nominal, 0)
  const results = new Float64Array(n)
  let sum = 0
  for (let i = 0; i < n; i++) {
    let v = 0
    for (const d of parsed) {
      v += sampleDim(rng, d.nominal, d.halfPlus, d.halfMinus, d.distribution)
    }
    results[i] = v
    sum += v
  }
  const mean = sum / n
  let m2 = 0
  for (let i = 0; i < n; i++) {
    const d = results[i] - mean
    m2 += d * d
  }
  const stdDev = Math.sqrt(m2 / n)
  const sorted = new Float64Array(results)
  sorted.sort()
  const p01 = sorted[Math.floor(n * 0.01)]
  const p50 = sorted[Math.floor(n * 0.50)]
  const p99 = sorted[Math.floor(n * 0.99)]
  const { histogram, binEdges } = buildHistogram(Array.from(sorted), 20)
  return {
    method: 'monte_carlo',
    samples: n,
    nominal,
    p01,
    p50,
    p99,
    mean,
    std_dev: stdDev,
    histogram: Array.from(histogram),
    bin_edges: binEdges,
  }
}

export { gradeToTolerance, IT_GRADES }