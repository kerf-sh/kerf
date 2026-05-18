/**
 * compareSearch.test.js — unit tests for the compare manifest search utility.
 */
import { describe, it, expect } from 'vitest'
import {
  compareSearch,
  groupByCategory,
  COMPARE_MANIFEST,
  COMPARE_CATEGORIES,
} from './compareSearch.js'

describe('compareSearch', () => {
  it('empty query returns all manifest items', () => {
    const results = compareSearch('')
    expect(results).toHaveLength(COMPARE_MANIFEST.length)
  })

  it('null query returns all manifest items', () => {
    const results = compareSearch(null)
    expect(results).toHaveLength(COMPARE_MANIFEST.length)
  })

  it('whitespace-only query returns all manifest items', () => {
    const results = compareSearch('   ')
    expect(results).toHaveLength(COMPARE_MANIFEST.length)
  })

  it('compareSearch("fus") returns Fusion 360 among results', () => {
    const results = compareSearch('fus')
    const slugs = results.map((r) => r.slug)
    expect(slugs).toContain('fusion')
  })

  it('search is case-insensitive', () => {
    const lower = compareSearch('freecad')
    const upper = compareSearch('FREECAD')
    const mixed = compareSearch('FrEeCAD')
    expect(lower.map((r) => r.slug)).toContain('freecad')
    expect(upper.map((r) => r.slug)).toContain('freecad')
    expect(mixed.map((r) => r.slug)).toContain('freecad')
  })

  it('matches on slug', () => {
    const results = compareSearch('kicad')
    expect(results.map((r) => r.slug)).toContain('kicad')
  })

  it('matches on competitor name', () => {
    const results = compareSearch('Altium')
    expect(results.map((r) => r.competitor)).toContain('Altium Designer')
  })

  it('matches on hero_tagline substring', () => {
    const results = compareSearch('open-source')
    expect(results.length).toBeGreaterThanOrEqual(1)
    results.forEach((r) => {
      expect(r.hero_tagline.toLowerCase()).toMatch(/open-source/)
    })
  })

  it('no match returns empty array', () => {
    const results = compareSearch('zzz_no_match_xyz')
    expect(results).toHaveLength(0)
  })

  it('category filter narrows results to that category only', () => {
    const results = compareSearch('', 'cad-electronics')
    results.forEach((r) => expect(r.category).toBe('cad-electronics'))
    expect(results.length).toBeGreaterThanOrEqual(1)
  })

  it('category + query combine correctly', () => {
    const results = compareSearch('kicad', 'cad-electronics')
    expect(results.map((r) => r.slug)).toContain('kicad')
    results.forEach((r) => expect(r.category).toBe('cad-electronics'))
  })

  it('category filter with non-matching query returns empty array', () => {
    const results = compareSearch('fusion', 'cad-electronics')
    expect(results).toHaveLength(0)
  })
})

describe('compareSearch result shape', () => {
  it('each result has slug, competitor, category, hero_tagline', () => {
    const results = compareSearch('')
    results.forEach((r) => {
      expect(typeof r.slug).toBe('string')
      expect(typeof r.competitor).toBe('string')
      expect(typeof r.category).toBe('string')
      expect(typeof r.hero_tagline).toBe('string')
    })
  })
})

describe('COMPARE_MANIFEST', () => {
  it('has at least 14 entries', () => {
    expect(COMPARE_MANIFEST.length).toBeGreaterThanOrEqual(14)
  })

  it('every entry has a non-empty slug', () => {
    COMPARE_MANIFEST.forEach((item) => {
      expect(item.slug.length).toBeGreaterThan(0)
    })
  })

  it('slugs are unique', () => {
    const slugs = COMPARE_MANIFEST.map((i) => i.slug)
    expect(new Set(slugs).size).toBe(slugs.length)
  })
})

describe('COMPARE_CATEGORIES', () => {
  it('contains all 7 required category ids', () => {
    const ids = COMPARE_CATEGORIES.map((c) => c.id)
    const required = [
      'cad-mechanical',
      'cad-electronics',
      'cad-architecture',
      'cad-sim',
      'cad-silicon',
      'cad-firmware',
      'cad-creative',
    ]
    required.forEach((id) => expect(ids).toContain(id))
  })

  it('each category has a non-empty label', () => {
    COMPARE_CATEGORIES.forEach((cat) => {
      expect(cat.label.length).toBeGreaterThan(0)
    })
  })
})

describe('groupByCategory', () => {
  it('groups items by their category field', () => {
    const items = compareSearch('')
    const groups = groupByCategory(items)
    groups.forEach((group) => {
      group.items.forEach((item) => {
        expect(item.category).toBe(group.category)
      })
    })
  })

  it('preserves COMPARE_CATEGORIES order', () => {
    const items = compareSearch('')
    const groups = groupByCategory(items)
    const groupIds = groups.map((g) => g.category)
    // Check that the order is a subsequence of COMPARE_CATEGORIES order
    const catOrder = COMPARE_CATEGORIES.map((c) => c.id)
    let lastIdx = -1
    groupIds.forEach((id) => {
      const idx = catOrder.indexOf(id)
      if (idx !== -1) {
        expect(idx).toBeGreaterThan(lastIdx)
        lastIdx = idx
      }
    })
  })

  it('empty input returns empty array', () => {
    const groups = groupByCategory([])
    expect(groups).toHaveLength(0)
  })
})
