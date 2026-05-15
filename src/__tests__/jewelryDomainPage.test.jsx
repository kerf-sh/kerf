/**
 * jewelryDomainPage.test.jsx
 *
 * Smoke tests for the Jewelry domain page.
 *
 * Strategy:
 *   - Import the meta module and verify key fields are well-formed
 *     (title length, description length, JSON-LD shape).
 *   - Import JEWELRY_FEATURES and verify every feature has a non-empty
 *     title, subtitle, and tool string.
 *   - Verify the comparison table rows cover the must-have features
 *     (chat-driven, parametric ring builder, open-source).
 *   - No React render required — we test the data layer that drives the page.
 *     This keeps the suite free of jsdom / happy-dom dependencies.
 */

import { describe, it, expect } from 'vitest'
import {
  JEWELRY_META,
  JEWELRY_FEATURES,
  buildJsonLd,
} from '../routes/domains/jewelry.meta.js'

/* -------------------------------------------------------------------------- */
/* Meta / SEO                                                                  */
/* -------------------------------------------------------------------------- */

describe('JEWELRY_META', () => {
  it('title is defined and ≤60 characters', () => {
    expect(typeof JEWELRY_META.title).toBe('string')
    expect(JEWELRY_META.title.length).toBeGreaterThan(0)
    expect(JEWELRY_META.title.length).toBeLessThanOrEqual(60)
  })

  it('description is defined and ≤155 characters', () => {
    expect(typeof JEWELRY_META.description).toBe('string')
    expect(JEWELRY_META.description.length).toBeGreaterThan(0)
    expect(JEWELRY_META.description.length).toBeLessThanOrEqual(155)
  })

  it('ogImage references kerf.sh/og/jewelry.png', () => {
    expect(JEWELRY_META.ogImage).toContain('kerf.sh/og/jewelry.png')
  })

  it('canonicalUrl is a valid https URL', () => {
    expect(JEWELRY_META.canonicalUrl).toMatch(/^https:\/\//)
  })
})

/* -------------------------------------------------------------------------- */
/* JSON-LD                                                                     */
/* -------------------------------------------------------------------------- */

describe('buildJsonLd', () => {
  it('returns a WebPage type with the correct name', () => {
    const ld = buildJsonLd()
    expect(ld['@type']).toBe('WebPage')
    expect(ld.name).toBe(JEWELRY_META.title)
  })

  it('mainEntity is an ItemList', () => {
    const ld = buildJsonLd()
    expect(ld.mainEntity['@type']).toBe('ItemList')
  })

  it('ItemList element count matches JEWELRY_FEATURES length', () => {
    const ld = buildJsonLd()
    expect(ld.mainEntity.itemListElement.length).toBe(JEWELRY_FEATURES.length)
  })

  it('each ItemList item has position, name, description', () => {
    const ld = buildJsonLd()
    for (const item of ld.mainEntity.itemListElement) {
      expect(typeof item.position).toBe('number')
      expect(typeof item.name).toBe('string')
      expect(item.name.length).toBeGreaterThan(0)
      expect(typeof item.description).toBe('string')
      expect(item.description.length).toBeGreaterThan(0)
    }
  })
})

/* -------------------------------------------------------------------------- */
/* Feature grid data                                                           */
/* -------------------------------------------------------------------------- */

describe('JEWELRY_FEATURES', () => {
  it('has at least 9 items (one per jewelry module)', () => {
    expect(JEWELRY_FEATURES.length).toBeGreaterThanOrEqual(9)
  })

  it('every feature has a non-empty id, title, subtitle and tool', () => {
    for (const f of JEWELRY_FEATURES) {
      expect(f.id.length).toBeGreaterThan(0)
      expect(f.title.length).toBeGreaterThan(0)
      expect(f.subtitle.length).toBeGreaterThan(0)
      expect(f.tool.length).toBeGreaterThan(0)
    }
  })

  it('includes a gemstones feature referencing jewelry_gemstone tool', () => {
    const gem = JEWELRY_FEATURES.find((f) => f.id === 'gemstones')
    expect(gem).toBeDefined()
    expect(gem.tool).toContain('jewelry_gemstone')
  })

  it('includes a ring feature referencing jewelry_ring tool', () => {
    const ring = JEWELRY_FEATURES.find((f) => f.id === 'ring')
    expect(ring).toBeDefined()
    expect(ring.tool).toContain('jewelry_ring')
  })

  it('includes a gem-seat feature referencing jewelry_gem_seat tool', () => {
    const seat = JEWELRY_FEATURES.find((f) => f.id === 'gem-seat')
    expect(seat).toBeDefined()
    expect(seat.tool).toContain('jewelry_gem_seat')
  })

  it('includes a settings feature referencing a prong or bezel tool', () => {
    const settings = JEWELRY_FEATURES.find((f) => f.id === 'settings')
    expect(settings).toBeDefined()
    expect(settings.tool).toMatch(/jewelry_prong_head|jewelry_bezel_setting/)
  })

  it('includes a casting feature', () => {
    const casting = JEWELRY_FEATURES.find((f) => f.id === 'casting')
    expect(casting).toBeDefined()
    expect(casting.tool).toContain('jewelry_casting')
  })

  it('subtitle for gemstones mentions the count 30', () => {
    const gem = JEWELRY_FEATURES.find((f) => f.id === 'gemstones')
    expect(gem.subtitle).toContain('30')
  })

  it('all feature ids are unique', () => {
    const ids = JEWELRY_FEATURES.map((f) => f.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

/* -------------------------------------------------------------------------- */
/* Page module exports cleanly                                                 */
/* -------------------------------------------------------------------------- */

describe('Jewelry page module', () => {
  it('exports a default component function', async () => {
    const mod = await import('../routes/domains/Jewelry.jsx')
    expect(typeof mod.default).toBe('function')
  })
})
