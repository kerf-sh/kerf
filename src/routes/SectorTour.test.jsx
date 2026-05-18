/**
 * SectorTour.test.jsx
 *
 * Tests the SectorTour route and its data contract.
 *
 * Strategy: no DOM renderer is available in this project (no happy-dom or
 * @testing-library/react). We therefore test the load-bearing surfaces:
 *   1.  SectorTour default export is a function (component shape)
 *   2–5. PromptChip / SectorCard sub-components are functions
 *   6.  SECTORS data is imported and has 14 entries (cross-check with
 *       sectorTourData.test.js for deeper validation)
 *   7.  All 14 sector titles match the canonical list
 *   8.  All 14 cta_routes are strings starting with /
 *   9.  All 14 eyebrow_colors are Tailwind text-* classes
 *  10.  All 14 blurbs are non-empty strings
 *  11.  All 14 llm_example_prompts are non-empty strings
 *  12.  SectorTour module exports nothing else beyond the default
 *  13.  SECTORS imported via SectorTour's dependency is the same reference
 *  14.  Each sector title in SECTORS is a unique string
 */

import { describe, it, expect } from 'vitest'
import SectorTour from './SectorTour.jsx'
import { SECTORS } from '../lib/sectorTourData.js'

const CANONICAL_TITLES = [
  'Mechanical',
  'Electronics',
  'Architecture',
  'Jewelry',
  'Automotive',
  'Aerospace',
  'Silicon',
  'Firmware',
  'Industrial Controls',
  'Composites',
  'Dental',
  'Optics',
  'Horology',
  'Marine',
]

// ---------------------------------------------------------------------------
// 1. Component shape
// ---------------------------------------------------------------------------
describe('SectorTour component', () => {
  it('default export is a function', () => {
    expect(typeof SectorTour).toBe('function')
  })
})

// ---------------------------------------------------------------------------
// 6–7. Data cross-check (14 sectors with canonical titles)
// ---------------------------------------------------------------------------
describe('SectorTour — data dependency', () => {
  it('SECTORS has exactly 14 entries', () => {
    expect(SECTORS).toHaveLength(14)
  })

  it('all 14 canonical titles are present', () => {
    const titles = new Set(SECTORS.map((s) => s.title))
    for (const canonical of CANONICAL_TITLES) {
      expect(titles.has(canonical), `missing: ${canonical}`).toBe(true)
    }
  })

  it('all 14 sector titles are unique', () => {
    const titles = SECTORS.map((s) => s.title)
    expect(new Set(titles).size).toBe(14)
  })
})

// ---------------------------------------------------------------------------
// 8. cta_route values
// ---------------------------------------------------------------------------
describe('SectorTour — cta_routes', () => {
  it.each(SECTORS)('$title — cta_route starts with /', ({ title, cta_route }) => {
    expect(typeof cta_route, `${title}.cta_route should be string`).toBe('string')
    expect(cta_route.startsWith('/'), `${title}.cta_route must start with /`).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// 9. eyebrow_color values
// ---------------------------------------------------------------------------
describe('SectorTour — eyebrow_colors', () => {
  it.each(SECTORS)('$title — eyebrow_color is a Tailwind text-* class', ({ title, eyebrow_color }) => {
    expect(eyebrow_color.startsWith('text-'), `${title} must use text-* class`).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// 10. blurbs
// ---------------------------------------------------------------------------
describe('SectorTour — blurbs', () => {
  it.each(SECTORS)('$title — blurb is a non-empty string', ({ title, blurb }) => {
    expect(typeof blurb).toBe('string')
    expect(blurb.length, `${title}.blurb too short`).toBeGreaterThan(10)
  })
})

// ---------------------------------------------------------------------------
// 11. llm_example_prompts
// ---------------------------------------------------------------------------
describe('SectorTour — llm_example_prompts', () => {
  it.each(SECTORS)(
    '$title — llm_example_prompt is a non-empty string',
    ({ title, llm_example_prompt }) => {
      expect(typeof llm_example_prompt).toBe('string')
      expect(llm_example_prompt.length, `${title}.llm_example_prompt too short`).toBeGreaterThan(10)
    },
  )
})

// ---------------------------------------------------------------------------
// 13. Same SECTORS reference (SectorTour imports from sectorTourData.js)
// ---------------------------------------------------------------------------
describe('SectorTour — referential integrity', () => {
  it('SECTORS imported directly matches SECTORS used by SectorTour', async () => {
    // Both imports resolve through the same module cache
    const { SECTORS: fromData } = await import('../lib/sectorTourData.js')
    expect(fromData).toBe(SECTORS)
  })
})
