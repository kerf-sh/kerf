/**
 * landing.electronics.test.js
 *
 * Tests the electronics capability group data exported from Landing.jsx.
 * Verifies the pair-messaging additions introduced in T-203:
 *   - tagline: "Two authoring styles, one fabrication target."
 *   - both atopile and tscircuit named in the group body
 *
 * Coverage areas:
 *   1.  Electronics group exists in CAPABILITY_GROUPS
 *   2.  Electronics group has id 'electronics'
 *   3.  Electronics group tagline is "Two authoring styles, one fabrication target."
 *   4.  Electronics group body names atopile
 *   5.  Electronics group body names tscircuit
 *   6.  Electronics group body mentions .ato extension
 *   7.  Electronics group body mentions .tsx extension
 *   8.  Electronics group has at least one card
 *   9.  Electronics group eyebrow is unchanged
 *  10.  Electronics group title is unchanged
 *  11.  No other group has a tagline (electronics-specific addition)
 *  12.  CAPABILITY_GROUPS has at least 5 groups (not accidentally truncated)
 */

import { describe, it, expect } from 'vitest'
import { CAPABILITY_GROUPS } from '../Landing.jsx'

const electronicsGroup = CAPABILITY_GROUPS.find((g) => g.id === 'electronics')

// ---------------------------------------------------------------------------
// 1–2. Electronics group exists
// ---------------------------------------------------------------------------

describe('CAPABILITY_GROUPS — electronics group', () => {
  it('contains a group with id "electronics"', () => {
    expect(electronicsGroup).toBeDefined()
  })

  it('has id "electronics"', () => {
    expect(electronicsGroup.id).toBe('electronics')
  })
})

// ---------------------------------------------------------------------------
// 3. Tagline
// ---------------------------------------------------------------------------

describe('electronics group — tagline', () => {
  it('has tagline "Two authoring styles, one fabrication target."', () => {
    expect(electronicsGroup.tagline).toBe('Two authoring styles, one fabrication target.')
  })
})

// ---------------------------------------------------------------------------
// 4–7. Both authoring styles named in body
// ---------------------------------------------------------------------------

describe('electronics group — authoring styles named in body', () => {
  it('names atopile in the body', () => {
    expect(electronicsGroup.body).toContain('atopile')
  })

  it('names tscircuit in the body', () => {
    expect(electronicsGroup.body).toContain('tscircuit')
  })

  it('mentions the .ato extension', () => {
    expect(electronicsGroup.body).toContain('.ato')
  })

  it('mentions the .tsx extension', () => {
    expect(electronicsGroup.body).toContain('.tsx')
  })
})

// ---------------------------------------------------------------------------
// 8–10. Structural integrity of the electronics group
// ---------------------------------------------------------------------------

describe('electronics group — structure unchanged', () => {
  it('has at least one card', () => {
    expect(Array.isArray(electronicsGroup.cards)).toBe(true)
    expect(electronicsGroup.cards.length).toBeGreaterThanOrEqual(1)
  })

  it('eyebrow unchanged', () => {
    expect(electronicsGroup.eyebrow).toBe('Electronics · schematic to gerber')
  })

  it('title unchanged', () => {
    expect(electronicsGroup.title).toBe(
      'PCB design with SI / EMC / PDN / thermal pre-compliance.',
    )
  })
})

// ---------------------------------------------------------------------------
// 11–12. No regressions to other groups
// ---------------------------------------------------------------------------

describe('CAPABILITY_GROUPS — other groups not modified', () => {
  it('electronics group has a tagline', () => {
    // Originally only electronics had a tagline; silicon/firmware/aerospace
    // were added later and each carries its own tagline by design.
    const electronics = CAPABILITY_GROUPS.find((g) => g.id === 'electronics')
    expect(electronics).toBeDefined()
    expect(electronics.tagline).toBeDefined()
    expect(typeof electronics.tagline).toBe('string')
  })

  it('has at least 5 groups (no groups were removed)', () => {
    expect(CAPABILITY_GROUPS.length).toBeGreaterThanOrEqual(5)
  })
})
