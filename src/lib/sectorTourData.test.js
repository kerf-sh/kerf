/**
 * sectorTourData.test.js
 *
 * Tests the shape and completeness of the SECTORS array.
 *
 * Coverage areas:
 *   1.  SECTORS has exactly 14 entries
 *   2.  Every entry has a non-empty title string
 *   3.  All titles are distinct (no duplicates)
 *   4.  Every entry has a blurb string (≥ 10 chars)
 *   5.  Every entry has a llm_example_prompt string (≥ 10 chars)
 *   6.  Every entry has a cta_route starting with /
 *   7.  Every entry has an eyebrow_color starting with text-
 *   8.  Named sector titles match the 14 required domains
 *   9.  Default export equals SECTORS
 *  10.  No entry has undefined or null for any required field
 */

import { describe, it, expect } from 'vitest'
import SECTORS, { SECTORS as namedSectors } from './sectorTourData.js'

const REQUIRED_TITLES = [
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

describe('SECTORS array', () => {
  it('has exactly 14 entries', () => {
    expect(SECTORS).toHaveLength(14)
  })

  it('default export equals named SECTORS export', () => {
    expect(SECTORS).toBe(namedSectors)
  })

  it('all titles are distinct', () => {
    const titles = SECTORS.map((s) => s.title)
    const unique = new Set(titles)
    expect(unique.size).toBe(titles.length)
  })

  it('contains all 14 required domain titles', () => {
    const titles = new Set(SECTORS.map((s) => s.title))
    for (const required of REQUIRED_TITLES) {
      expect(titles.has(required), `missing sector: ${required}`).toBe(true)
    }
  })
})

describe('Each sector entry shape', () => {
  it.each(SECTORS)('$title — has non-empty title', ({ title }) => {
    expect(typeof title).toBe('string')
    expect(title.length).toBeGreaterThan(0)
  })

  it.each(SECTORS)('$title — blurb is a non-trivial string', ({ title, blurb }) => {
    expect(typeof blurb, `${title}.blurb should be string`).toBe('string')
    expect(blurb.length, `${title}.blurb too short`).toBeGreaterThanOrEqual(10)
  })

  it.each(SECTORS)(
    '$title — llm_example_prompt is a non-trivial string',
    ({ title, llm_example_prompt }) => {
      expect(typeof llm_example_prompt, `${title}.llm_example_prompt should be string`).toBe(
        'string',
      )
      expect(llm_example_prompt.length, `${title}.llm_example_prompt too short`).toBeGreaterThanOrEqual(10)
    },
  )

  it.each(SECTORS)('$title — cta_route starts with /', ({ title, cta_route }) => {
    expect(typeof cta_route, `${title}.cta_route should be string`).toBe('string')
    expect(cta_route.startsWith('/'), `${title}.cta_route must start with /`).toBe(true)
  })

  it.each(SECTORS)(
    '$title — eyebrow_color starts with text-',
    ({ title, eyebrow_color }) => {
      expect(typeof eyebrow_color, `${title}.eyebrow_color should be string`).toBe('string')
      expect(
        eyebrow_color.startsWith('text-'),
        `${title}.eyebrow_color must start with text-`,
      ).toBe(true)
    },
  )

  it.each(SECTORS)('$title — no required field is null or undefined', (entry) => {
    const fields = ['title', 'blurb', 'llm_example_prompt', 'cta_route', 'eyebrow_color']
    for (const field of fields) {
      expect(entry[field], `${entry.title}.${field} must not be null/undefined`).not.toBeNull()
      expect(entry[field], `${entry.title}.${field} must not be null/undefined`).not.toBeUndefined()
    }
  })
})
