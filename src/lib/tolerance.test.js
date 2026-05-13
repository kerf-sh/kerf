import {
  worstCaseStack,
  rssStack,
  stackup,
  monteCarloStack,
  gradeToTolerance,
  IT_GRADES,
} from './tolerance.js'

const round = (n, d = 6) => Math.round(n * 10 ** d) / 10 ** d

function rngFixed(seed) {
  let s = seed
  return () => {
    s = (s * 1664525 + 1013904223) & 0xffffffff
    return (s >>> 0) / 0xffffffff
  }
}

describe('worstCaseStack', () => {
  it('sums nominals correctly', () => {
    const dims = [
      { nominal: 10, plus: 0.1, minus: 0.1 },
      { nominal: 5, plus: 0.05, minus: 0.05 },
      { nominal: 2, plus: 0.02, minus: 0.02 },
    ]
    const r = worstCaseStack(dims)
    expect(round(r.nominal)).toBe(17)
    expect(round(r.max)).toBe(17.17)
    expect(round(r.min)).toBe(16.83)
    expect(r.method).toBe('worst_case')
  })

  it('handles upper/lower form', () => {
    const dims = [
      { nominal: 10, upper: 10.1, lower: 9.9 },
      { nominal: 5, upper: 5.05, lower: 4.95 },
    ]
    const r = worstCaseStack(dims)
    expect(round(r.nominal)).toBe(15)
    expect(round(r.max)).toBe(15.15)
    expect(round(r.min)).toBe(14.85)
  })

  it('handles IT grade', () => {
    const dims = [
      { nominal: 25, grade: 'IT8' },
      { nominal: 10, grade: 'IT7' },
    ]
    const r = worstCaseStack(dims)
    expect(round(r.nominal)).toBe(35)
    expect(r.max).toBeGreaterThan(r.nominal)
    expect(r.min).toBeLessThan(r.nominal)
  })

  it('handles asymmetric plus/minus', () => {
    const dims = [{ nominal: 10, plus: 0.2, minus: 0.05 }]
    const r = worstCaseStack(dims)
    expect(round(r.max)).toBe(10.2)
    expect(round(r.min)).toBe(9.95)
  })

  it('returns zero for empty array', () => {
    const r = worstCaseStack([])
    expect(round(r.nominal)).toBe(0)
    expect(round(r.max)).toBe(0)
    expect(round(r.min)).toBe(0)
  })
})

describe('rssStack', () => {
  it('computes RSS band with k=3', () => {
    const dims = [
      { nominal: 10, plus: 0.1, minus: 0.1 },
      { nominal: 5, plus: 0.05, minus: 0.05 },
    ]
    const r = rssStack(dims, 3)
    expect(r.method).toBe('rss')
    expect(r.k).toBe(3)
    expect(r.band).toBeGreaterThan(0)
  })

  it('band scales with k', () => {
    const dims = [{ nominal: 10, plus: 0.1, minus: 0.1 }]
    const r2 = rssStack(dims, 2)
    const r3 = rssStack(dims, 3)
    expect(round(r2.band * 1.5, 4)).toBe(round(r3.band, 4))
  })

  it('handles IT grade', () => {
    const dims = [{ nominal: 25, grade: 'IT9' }]
    const r = rssStack(dims)
    expect(r.band).toBeGreaterThan(0)
  })
})

describe('stackup', () => {
  it('combines worst-case and RSS', () => {
    const dims = [
      { nominal: 10, plus: 0.1, minus: 0.1 },
      { nominal: 5, plus: 0.05, minus: 0.05 },
    ]
    const r = stackup(dims, 3)
    expect(r.method).toBe('worst_case+rss')
    expect(r.nominal).toBeDefined()
    expect(r.max).toBeDefined()
    expect(r.min).toBeDefined()
    expect(r.band).toBeDefined()
  })
})

describe('monteCarloStack', () => {
  it('returns percentiles and histogram', () => {
    const dims = [
      { nominal: 10, plus: 0.1, minus: 0.1, distribution: 'normal' },
      { nominal: 5, plus: 0.05, minus: 0.05, distribution: 'uniform' },
    ]
    const r = monteCarloStack(dims, { samples: 1000, rng: rngFixed(42) })
    expect(r.method).toBe('monte_carlo')
    expect(r.samples).toBe(1000)
    expect(r.p01).toBeLessThan(r.p50)
    expect(r.p50).toBeLessThan(r.p99)
    expect(r.mean).toBeGreaterThan(0)
    expect(r.std_dev).toBeGreaterThan(0)
    expect(r.histogram.length).toBe(20)
    expect(r.bin_edges.length).toBe(21)
    expect(r.nominal).toBe(15)
  })

  it('caps samples at 1M', () => {
    const dims = [{ nominal: 10, distribution: 'normal' }]
    const r = monteCarloStack(dims, { samples: 99999999 })
    expect(r.samples).toBe(1000000)
  })

  it('throws for empty dimensions', () => {
    expect(() => monteCarloStack([])).toThrow()
  })

  it('uses uniform distribution', () => {
    const dims = [
      { nominal: 10, plus: 0.1, minus: 0.1, distribution: 'uniform' },
    ]
    const r = monteCarloStack(dims, { samples: 500, rng: rngFixed(99) })
    expect(r.p01).toBeGreaterThanOrEqual(9.9 - 0.05)
    expect(r.p99).toBeLessThanOrEqual(10.1 + 0.05)
    expect(r.histogram.length).toBe(20)
  })

  it('uses triangular distribution', () => {
    const dims = [
      { nominal: 10, plus: 0.1, minus: 0.1, distribution: 'triangular' },
    ]
    const r = monteCarloStack(dims, { samples: 500, rng: rngFixed(77) })
    expect(r.p50).toBeCloseTo(10, 1)
    expect(r.histogram.length).toBe(20)
  })

  it('uses default normal distribution when not specified', () => {
    const dims = [{ nominal: 10, plus: 0.1, minus: 0.1 }]
    const r = monteCarloStack(dims, { samples: 500, rng: rngFixed(55) })
    expect(r.p01).toBeDefined()
    expect(r.p50).toBeDefined()
    expect(r.p99).toBeDefined()
  })
})

describe('gradeToTolerance / IT_GRADES', () => {
  it('returns correct IT grade values', () => {
    expect(gradeToTolerance('IT5')).toBe(0.002)
    expect(gradeToTolerance('IT6')).toBe(0.003)
    expect(gradeToTolerance('IT7')).toBe(0.005)
    expect(gradeToTolerance('IT8')).toBe(0.007)
    expect(gradeToTolerance('IT9')).toBe(0.0125)
    expect(gradeToTolerance('IT10')).toBe(0.020)
  })

  it('returns 0 for unknown grade', () => {
    expect(gradeToTolerance('UNKNOWN')).toBe(0)
  })

  it('IT_GRADES contains expected entries', () => {
    expect(IT_GRADES['IT5']).toBe(0.004)
    expect(IT_GRADES['IT6']).toBe(0.006)
    expect(IT_GRADES['IT7']).toBe(0.010)
    expect(IT_GRADES['IT8']).toBe(0.014)
  })
})