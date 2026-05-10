// bomAlternates.test.js — exercises the pure helpers exported from
// `src/components/BOMTable.jsx` for the Alternates column: pickAlternates
// (which non-cheapest distributors are surfaced) and the interaction with
// pickCheapestDistributor (so the tests reflect the production call shape).

import { describe, it, expect } from 'vitest'
import { pickAlternates, pickCheapestDistributor } from '../components/BOMTable.jsx'

describe('pickAlternates', () => {
  it('returns empty for missing / empty distributors', () => {
    expect(pickAlternates(undefined, null)).toEqual([])
    expect(pickAlternates(null, null)).toEqual([])
    expect(pickAlternates([], null)).toEqual([])
  })

  it('returns empty when there is exactly one entry (it is the cheapest)', () => {
    const only = { name: 'DigiKey', price_usd: 0.05 }
    const cheapest = pickCheapestDistributor([only])
    expect(cheapest).toBe(only)
    expect(pickAlternates([only], cheapest)).toEqual([])
  })

  it('returns all-but-cheapest sorted by unit price ascending', () => {
    const digi = { name: 'DigiKey', price_usd: 0.05 }
    const mouser = { name: 'Mouser', price_usd: 0.0145 }
    const lcsc = { name: 'LCSC', price_usd: 0.012 }
    const dists = [digi, mouser, lcsc]
    const cheapest = pickCheapestDistributor(dists)
    expect(cheapest).toBe(lcsc)
    const alts = pickAlternates(dists, cheapest)
    expect(alts).toHaveLength(2)
    // Mouser ($0.0145) should sort before DigiKey ($0.05).
    expect(alts[0].entry).toBe(mouser)
    expect(alts[0].price).toBeCloseTo(0.0145)
    expect(alts[1].entry).toBe(digi)
    expect(alts[1].price).toBeCloseTo(0.05)
  })

  it('falls back to price_min when price_usd is absent', () => {
    const a = { name: 'A', price_usd: 1.0 }
    const b = { name: 'B', price_min: 0.5, price_max: 0.8 }
    const dists = [a, b]
    const cheapest = pickCheapestDistributor(dists)
    expect(cheapest).toBe(b)
    const alts = pickAlternates(dists, cheapest)
    expect(alts).toHaveLength(1)
    expect(alts[0].entry).toBe(a)
  })

  it('skips entries that lack any usable price field', () => {
    const a = { name: 'A', price_usd: 0.10 }
    const b = { name: 'B' /* no price */ }
    const c = { name: 'C', price_usd: 0.20 }
    const dists = [a, b, c]
    const cheapest = pickCheapestDistributor(dists)
    expect(cheapest).toBe(a)
    const alts = pickAlternates(dists, cheapest)
    // Only `c` is a usable alternate; `b` is skipped.
    expect(alts.map((x) => x.entry.name)).toEqual(['C'])
  })
})
