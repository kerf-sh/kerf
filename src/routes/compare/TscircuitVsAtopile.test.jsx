/**
 * TscircuitVsAtopile.test.jsx
 *
 * Tests the TscircuitVsAtopile comparison page.
 * No DOM rendering required — we exercise exported constants and verify the
 * component module shape. The route renders at /compare/tscircuit-vs-atopile.
 *
 * Coverage areas:
 *   1.  TSCIRCUIT_EXAMPLE is exported and non-empty
 *   2.  TSCIRCUIT_EXAMPLE contains JSX board element
 *   3.  TSCIRCUIT_EXAMPLE contains resistor elements
 *   4.  TSCIRCUIT_EXAMPLE mentions Vin / Vout / GND nets
 *   5.  ATOPILE_EXAMPLE is exported and non-empty
 *   6.  ATOPILE_EXAMPLE contains .ato component declaration
 *   7.  ATOPILE_EXAMPLE contains 10kohm resistance value
 *   8.  ATOPILE_EXAMPLE mentions vin / vout / gnd signals
 *   9.  TSCIRCUIT_EXAMPLE uses JSX angle-bracket syntax
 *  10.  ATOPILE_EXAMPLE does not contain angle-bracket JSX tags
 *  11.  Default export is a function (component shape)
 *  12.  BOTH_PRODUCE_KICAD_TEXT contains "Both produce KiCad"
 *  13.  HERO_HEADING contains "Two authoring styles"
 *  14.  TSCIRCUIT_PERSONAS contains "Visual-first" persona entries
 *  15.  ATOPILE_PERSONAS contains "Code-first" persona entries
 *  16.  TSCIRCUIT_PERSONAS has at least one entry
 *  17.  ATOPILE_PERSONAS has at least one entry
 *  18.  Both examples reference the same resistor value 10kohm
 *  19.  Both examples are valid text without null bytes
 *  20.  Component function takes zero or one argument (React FC contract)
 */

import { describe, it, expect } from 'vitest'
import TscircuitVsAtopile, {
  TSCIRCUIT_EXAMPLE,
  ATOPILE_EXAMPLE,
  TSCIRCUIT_PERSONAS,
  ATOPILE_PERSONAS,
  BOTH_PRODUCE_KICAD_TEXT,
  HERO_HEADING,
} from './TscircuitVsAtopile.jsx'

/* -------------------------------------------------------------------------- */
/* 1–4. TSCIRCUIT_EXAMPLE                                                      */
/* -------------------------------------------------------------------------- */

describe('TSCIRCUIT_EXAMPLE', () => {
  it('is a non-empty string', () => {
    expect(typeof TSCIRCUIT_EXAMPLE).toBe('string')
    expect(TSCIRCUIT_EXAMPLE.length).toBeGreaterThan(0)
  })

  it('contains JSX board element', () => {
    expect(TSCIRCUIT_EXAMPLE).toContain('<board')
  })

  it('contains resistor elements', () => {
    expect(TSCIRCUIT_EXAMPLE).toContain('<resistor')
  })

  it('mentions voltage-divider nets Vin, Vout, GND', () => {
    expect(TSCIRCUIT_EXAMPLE).toContain('Vin')
    expect(TSCIRCUIT_EXAMPLE).toContain('Vout')
    expect(TSCIRCUIT_EXAMPLE).toContain('GND')
  })
})

/* -------------------------------------------------------------------------- */
/* 5–8. ATOPILE_EXAMPLE                                                        */
/* -------------------------------------------------------------------------- */

describe('ATOPILE_EXAMPLE', () => {
  it('is a non-empty string', () => {
    expect(typeof ATOPILE_EXAMPLE).toBe('string')
    expect(ATOPILE_EXAMPLE.length).toBeGreaterThan(0)
  })

  it('contains atopile component declaration', () => {
    expect(ATOPILE_EXAMPLE).toContain('component')
  })

  it('contains resistance value 10kohm', () => {
    expect(ATOPILE_EXAMPLE).toContain('10kohm')
  })

  it('mentions voltage-divider signals vin, vout, gnd', () => {
    expect(ATOPILE_EXAMPLE).toContain('vin')
    expect(ATOPILE_EXAMPLE).toContain('vout')
    expect(ATOPILE_EXAMPLE).toContain('gnd')
  })
})

/* -------------------------------------------------------------------------- */
/* 9–10. Authoring-style isolation                                             */
/* -------------------------------------------------------------------------- */

describe('authoring style isolation', () => {
  it('TSCIRCUIT_EXAMPLE uses JSX angle-bracket syntax', () => {
    expect(TSCIRCUIT_EXAMPLE).toMatch(/<\w/)
  })

  it('ATOPILE_EXAMPLE does not contain JSX board/resistor tags', () => {
    expect(ATOPILE_EXAMPLE).not.toContain('<board')
    expect(ATOPILE_EXAMPLE).not.toContain('<resistor')
  })
})

/* -------------------------------------------------------------------------- */
/* 11. Module shape                                                             */
/* -------------------------------------------------------------------------- */

describe('TscircuitVsAtopile module', () => {
  it('default export is a function', () => {
    expect(typeof TscircuitVsAtopile).toBe('function')
  })
})

/* -------------------------------------------------------------------------- */
/* 12–13. Exported UI text constants                                           */
/* -------------------------------------------------------------------------- */

describe('exported UI text constants', () => {
  it('BOTH_PRODUCE_KICAD_TEXT contains "Both produce KiCad"', () => {
    expect(BOTH_PRODUCE_KICAD_TEXT).toContain('Both produce KiCad')
  })

  it('HERO_HEADING contains "Two authoring styles"', () => {
    expect(HERO_HEADING).toContain('Two authoring styles')
  })
})

/* -------------------------------------------------------------------------- */
/* 14–17. Persona arrays                                                       */
/* -------------------------------------------------------------------------- */

describe('TSCIRCUIT_PERSONAS', () => {
  it('is a non-empty array', () => {
    expect(Array.isArray(TSCIRCUIT_PERSONAS)).toBe(true)
    expect(TSCIRCUIT_PERSONAS.length).toBeGreaterThan(0)
  })

  it('contains Makers persona', () => {
    expect(TSCIRCUIT_PERSONAS.some((p) => p.includes('Makers'))).toBe(true)
  })
})

describe('ATOPILE_PERSONAS', () => {
  it('is a non-empty array', () => {
    expect(Array.isArray(ATOPILE_PERSONAS)).toBe(true)
    expect(ATOPILE_PERSONAS.length).toBeGreaterThan(0)
  })

  it('contains Embedded engineers persona', () => {
    expect(ATOPILE_PERSONAS.some((p) => p.includes('Embedded engineers'))).toBe(true)
  })
})

/* -------------------------------------------------------------------------- */
/* 18–19. Cross-example consistency                                            */
/* -------------------------------------------------------------------------- */

describe('cross-example consistency', () => {
  it('both examples reference the same resistor value 10kohm', () => {
    expect(TSCIRCUIT_EXAMPLE).toContain('10kohm')
    expect(ATOPILE_EXAMPLE).toContain('10kohm')
  })

  it('both examples are valid text without null bytes', () => {
    expect(TSCIRCUIT_EXAMPLE).not.toContain('\0')
    expect(ATOPILE_EXAMPLE).not.toContain('\0')
  })
})

/* -------------------------------------------------------------------------- */
/* 20. React component contract                                                */
/* -------------------------------------------------------------------------- */

describe('React component contract', () => {
  it('component function takes 0 or 1 argument (standard React FC)', () => {
    expect(TscircuitVsAtopile.length).toBeLessThanOrEqual(1)
  })
})
