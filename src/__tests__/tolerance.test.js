import { describe, it, expect } from 'vitest'
import { worstCaseStack, rssStack, stackup, monteCarloStack, gradeToTolerance, IT_GRADES } from '../lib/tolerance.js'

function rngFixed() {
  let seed = 42
  return () => {
    seed = (seed * 1664525 + 1013904223) & 0xffffffff
    return (seed >>> 0) / 0xffffffff
  }
}

describe('tolerance.js', () => {
  describe('worstCaseStack', () => {
    it('sums nominal, max, min correctly', () => {
      const result = worstCaseStack([
        { nominal: 10, plus: 0.1, minus: 0.1 },
        { nominal: 5, plus: 0.05, minus: 0.05 },
        { nominal: 2, plus: 0.02, minus: 0.02 },
      ])
      expect(result.method).toBe('worst_case')
      expect(result.nominal).toBeCloseTo(17.0, 5)
      expect(result.max).toBeCloseTo(17.17, 4)
      expect(result.min).toBeCloseTo(16.83, 4)
    })

    it('handles asymmetric plus/minus', () => {
      const result = worstCaseStack([
        { nominal: 10, plus: 0.2, minus: 0.05 },
      ])
      expect(result.nominal).toBeCloseTo(10, 5)
      expect(result.max).toBeCloseTo(10.2, 5)
      expect(result.min).toBeCloseTo(9.95, 5)
    })

    it('handles empty array', () => {
      const result = worstCaseStack([])
      expect(result.nominal).toBe(0)
      expect(result.max).toBe(0)
      expect(result.min).toBe(0)
    })
  })

  describe('rssStack', () => {
    it('computes RSS band with k=3', () => {
      const result = rssStack([
        { nominal: 10, plus: 0.1, minus: 0.1 },
        { nominal: 5, plus: 0.05, minus: 0.05 },
      ], 3)
      expect(result.method).toBe('rss')
      expect(result.nominal).toBeCloseTo(15.0, 5)
      const half1 = 0.1
      const half2 = 0.05
      const expectedBand = 3 * Math.sqrt(half1 * half1 + half2 * half2)
      expect(result.band).toBeCloseTo(expectedBand, 5)
      expect(result.k).toBe(3)
    })

    it('uses k=3 default when not specified', () => {
      const result = rssStack([{ nominal: 10, plus: 0.1, minus: 0.1 }])
      expect(result.k).toBe(3)
    })

    it('accepts custom k', () => {
      const result = rssStack([{ nominal: 10, plus: 0.1, minus: 0.1 }], 2.45)
      expect(result.k).toBe(2.45)
    })

it('handles IT grades', () => {
      const result = rssStack([
        { nominal: 25, grade: 'IT8' },
        { nominal: 10, grade: 'IT7' },
      ])
      expect(result.nominal).toBeCloseTo(35.0, 5)
      const it8 = IT_GRADES.IT8
      const it7 = IT_GRADES.IT7
      const expectedBand = 3 * Math.sqrt(it8 * it8 + it7 * it7)
      expect(result.band).toBeCloseTo(expectedBand, 5)
    })
  })

  describe('stackup', () => {
    it('returns combined worst-case and RSS results', () => {
      const result = stackup([
        { nominal: 10, plus: 0.1, minus: 0.1 },
        { nominal: 5, plus: 0.05, minus: 0.05 },
      ])
      expect(result.method).toBe('worst_case+rss')
      expect(result.nominal).toBeCloseTo(15.0, 5)
      expect(result.max).toBeCloseTo(15.15, 4)
      expect(result.min).toBeCloseTo(14.85, 4)
      expect(typeof result.band).toBe('number')
      expect(result.band).toBeGreaterThan(0)
    })
  })

  describe('gradeToTolerance', () => {
    it('returns correct IT grade values in mm', () => {
      expect(gradeToTolerance('IT6')).toBeCloseTo(0.006, 5)
      expect(gradeToTolerance('IT7')).toBeCloseTo(0.010, 5)
      expect(gradeToTolerance('IT8')).toBeCloseTo(0.014, 5)
      expect(gradeToTolerance('IT9')).toBeCloseTo(0.025, 5)
      expect(gradeToTolerance('IT10')).toBeCloseTo(0.040, 5)
    })

    it('returns 0 for unknown grades', () => {
      expect(gradeToTolerance('INVALID')).toBe(0)
      expect(gradeToTolerance('')).toBe(0)
    })
  })

  describe('IT_GRADES', () => {
    it('contains expected keys', () => {
      expect(IT_GRADES.IT6).toBe(0.006)
      expect(IT_GRADES.IT7).toBe(0.010)
      expect(IT_GRADES.IT8).toBe(0.014)
      expect(IT_GRADES.IT12).toBe(0.100)
      expect(IT_GRADES.IT16).toBe(0.630)
    })
  })

  describe('monteCarloStack', () => {
    it('returns expected fields', () => {
      const result = monteCarloStack(
        [{ nominal: 10, plus: 0.1, minus: 0.1, distribution: 'normal' }],
        { samples: 1000, rng: rngFixed() }
      )
      expect(result.method).toBe('monte_carlo')
      expect(result.samples).toBe(1000)
      expect(result.nominal).toBeCloseTo(10, 5)
      expect(typeof result.p01).toBe('number')
      expect(typeof result.p50).toBe('number')
      expect(typeof result.p99).toBe('number')
      expect(typeof result.mean).toBe('number')
      expect(typeof result.std_dev).toBe('number')
      expect(Array.isArray(result.histogram)).toBe(true)
      expect(Array.isArray(result.bin_edges)).toBe(true)
      expect(result.histogram.length).toBe(20)
      expect(result.bin_edges.length).toBe(21)
    })

    it('mean is close to nominal for symmetric normal', () => {
      const result = monteCarloStack(
        [{ nominal: 10, plus: 0.1, minus: 0.1, distribution: 'normal' }],
        { samples: 5000, rng: rngFixed() }
      )
      expect(result.mean).toBeCloseTo(10, 1)
    })

    it('p50 is close to nominal for symmetric distributions', () => {
      const result = monteCarloStack(
        [{ nominal: 10, plus: 0.1, minus: 0.1, distribution: 'uniform' }],
        { samples: 5000, rng: rngFixed() }
      )
      expect(result.p50).toBeCloseTo(10, 1)
    })

    it('throws on empty dimensions', () => {
      expect(() => monteCarloStack([])).toThrow()
    })

    it('respects sample cap at 1e6', () => {
      const result = monteCarloStack(
        [{ nominal: 10, distribution: 'normal' }],
        { samples: 99999999 }
      )
      expect(result.samples).toBe(1_000_000)
    })

    it('handles upper/lower form', () => {
      const result = monteCarloStack(
        [{ nominal: 10, upper: 10.1, lower: 9.9, distribution: 'normal' }],
        { samples: 1000, rng: rngFixed() }
      )
      expect(result.nominal).toBeCloseTo(10, 5)
      expect(result.p50).toBeCloseTo(10, 1)
    })

    it('handles IT grade form', () => {
      const result = monteCarloStack(
        [{ nominal: 25, grade: 'IT8', distribution: 'normal' }],
        { samples: 1000, rng: rngFixed() }
      )
      expect(result.nominal).toBeCloseTo(25, 5)
      const it8tol = IT_GRADES.IT8
      const halfSpan = it8tol / 2
      expect(result.std_dev).toBeGreaterThan(0)
      expect(result.p99 - result.p01).toBeGreaterThan(halfSpan)
    })

    it('uses default unit mm', () => {
      const result = monteCarloStack([{ nominal: 10, distribution: 'normal' }])
      expect(result.nominal).toBe(10)
    })

    it('p01 < p50 < p99', () => {
      const result = monteCarloStack(
        [
          { nominal: 10, plus: 0.1, minus: 0.1, distribution: 'normal' },
          { nominal: 5, plus: 0.05, minus: 0.05, distribution: 'uniform' },
        ],
        { samples: 5000, rng: rngFixed() }
      )
      expect(result.p01).toBeLessThan(result.p50)
      expect(result.p50).toBeLessThan(result.p99)
    })
  })

  describe('upper/lower form', () => {
    it('converts upper/lower to plus/minus in worst-case', () => {
      const result = worstCaseStack([
        { nominal: 10, upper: 10.1, lower: 9.9 },
      ])
      expect(result.max).toBeCloseTo(10.1, 5)
      expect(result.min).toBeCloseTo(9.9, 5)
    })

    it('converts upper/lower in rssStack', () => {
      const result = rssStack([
        { nominal: 10, upper: 10.1, lower: 9.9 },
      ])
      const half = (0.1 + 0.1) / 2
      expect(result.band).toBeCloseTo(3 * Math.sqrt(half * half), 5)
    })
  })
})