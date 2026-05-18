/**
 * ladderPowerFlow.test.js — vitest unit tests for src/lib/ladderPowerFlow.js
 *
 * Covers:
 *   1. NO / NC / R_TRIG / F_TRIG contact semantics
 *   2. Series (AND) evaluation
 *   3. Parallel (OR) branch evaluation
 *   4. Coil energisation and COIL_NC negation
 *   5. colorForState colour-helper
 */

import { describe, it, expect } from 'vitest'
import { computePowerFlow, colorForState, evaluateContact } from './ladderPowerFlow.js'

// ---------------------------------------------------------------------------
// 1. evaluateContact — individual contact semantics
// ---------------------------------------------------------------------------

describe('evaluateContact', () => {
  it('NO: lit when variable is true', () => {
    expect(evaluateContact({ type: 'NO', variable: 'x' }, { x: true })).toBe(true)
  })

  it('NO: NOT lit when variable is false', () => {
    expect(evaluateContact({ type: 'NO', variable: 'x' }, { x: false })).toBe(false)
  })

  it('NO: NOT lit when variable is absent', () => {
    expect(evaluateContact({ type: 'NO', variable: 'x' }, {})).toBe(false)
  })

  it('NC: lit when variable is false', () => {
    expect(evaluateContact({ type: 'NC', variable: 'y' }, { y: false })).toBe(true)
  })

  it('NC: lit when variable is absent (treated as false)', () => {
    expect(evaluateContact({ type: 'NC', variable: 'y' }, {})).toBe(true)
  })

  it('NC: NOT lit when variable is true', () => {
    expect(evaluateContact({ type: 'NC', variable: 'y' }, { y: true })).toBe(false)
  })

  it('R_TRIG: lit when variable is true', () => {
    expect(evaluateContact({ type: 'R_TRIG', variable: 'clk' }, { clk: true })).toBe(true)
  })

  it('R_TRIG: NOT lit when variable is false', () => {
    expect(evaluateContact({ type: 'R_TRIG', variable: 'clk' }, { clk: false })).toBe(false)
  })

  it('F_TRIG: lit when variable is false', () => {
    expect(evaluateContact({ type: 'F_TRIG', variable: 'sig' }, { sig: false })).toBe(true)
  })

  it('F_TRIG: NOT lit when variable is true', () => {
    expect(evaluateContact({ type: 'F_TRIG', variable: 'sig' }, { sig: true })).toBe(false)
  })

  it('evaluateContact accepts a Map as varState', () => {
    const m = new Map([['a', true]])
    expect(evaluateContact({ type: 'NO', variable: 'a' }, m)).toBe(true)
    expect(evaluateContact({ type: 'NO', variable: 'b' }, m)).toBe(false)
  })

  it('unknown contact type returns false', () => {
    expect(evaluateContact({ type: 'UNKNOWN', variable: 'x' }, { x: true })).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// 2. Series (AND) semantics via computePowerFlow
// ---------------------------------------------------------------------------

describe('computePowerFlow — series contacts', () => {
  it('single NO contact lit when variable true → wire complete', () => {
    const rung = [
      { id: 'c1', type: 'NO', variable: 'start' },
      { id: 'q1', type: 'COIL', variable: 'motor' },
    ]
    const { contactsLit, coilsLit, wiresLit } = computePowerFlow(rung, { start: true })
    expect(contactsLit.has('c1')).toBe(true)
    expect(coilsLit.has('q1')).toBe(true)
    expect(wiresLit.has('wire_rung_complete')).toBe(true)
  })

  it('single NO contact NOT lit when variable false → coil de-energised', () => {
    const rung = [
      { id: 'c1', type: 'NO', variable: 'start' },
      { id: 'q1', type: 'COIL', variable: 'motor' },
    ]
    const { contactsLit, coilsLit } = computePowerFlow(rung, { start: false })
    expect(contactsLit.has('c1')).toBe(false)
    expect(coilsLit.has('q1')).toBe(false)
  })

  it('series: all contacts true → coil lit', () => {
    const rung = [
      { id: 'c1', type: 'NO', variable: 'a' },
      { id: 'c2', type: 'NO', variable: 'b' },
      { id: 'c3', type: 'NC', variable: 'fault' },
      { id: 'q1', type: 'COIL', variable: 'run' },
    ]
    const { coilsLit } = computePowerFlow(rung, { a: true, b: true, fault: false })
    expect(coilsLit.has('q1')).toBe(true)
  })

  it('series: any contact false → coil NOT lit', () => {
    const rung = [
      { id: 'c1', type: 'NO', variable: 'a' },
      { id: 'c2', type: 'NO', variable: 'b' },
      { id: 'q1', type: 'COIL', variable: 'run' },
    ]
    const { coilsLit } = computePowerFlow(rung, { a: true, b: false })
    expect(coilsLit.has('q1')).toBe(false)
  })

  it('wire_after_<id> entries track intermediate series state', () => {
    const rung = [
      { id: 'c1', type: 'NO', variable: 'x' },
      { id: 'c2', type: 'NO', variable: 'y' },
      { id: 'q1', type: 'COIL', variable: 'out' },
    ]
    const { wiresLit } = computePowerFlow(rung, { x: true, y: true })
    expect(wiresLit.has('wire_after_c1')).toBe(true)
    expect(wiresLit.has('wire_after_c2')).toBe(true)
  })

  it('NC contact breaks series when variable is true', () => {
    const rung = [
      { id: 'c1', type: 'NO', variable: 'run' },
      { id: 'c2', type: 'NC', variable: 'stop' },
      { id: 'q1', type: 'COIL', variable: 'motor' },
    ]
    // stop=true → NC breaks power
    const { coilsLit } = computePowerFlow(rung, { run: true, stop: true })
    expect(coilsLit.has('q1')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// 3. Parallel (OR) branch evaluation
// ---------------------------------------------------------------------------

describe('computePowerFlow — parallel branches', () => {
  it('parallel: at least one branch true → downstream coil lit', () => {
    const rung = [
      [                                           // parallel group
        [{ id: 'c1', type: 'NO', variable: 'a' }],  // branch A
        [{ id: 'c2', type: 'NO', variable: 'b' }],  // branch B
      ],
      { id: 'q1', type: 'COIL', variable: 'out' },
    ]
    // only a=true
    const { coilsLit } = computePowerFlow(rung, { a: true, b: false })
    expect(coilsLit.has('q1')).toBe(true)
  })

  it('parallel: only second branch true → coil still lit', () => {
    const rung = [
      [
        [{ id: 'c1', type: 'NO', variable: 'a' }],
        [{ id: 'c2', type: 'NO', variable: 'b' }],
      ],
      { id: 'q1', type: 'COIL', variable: 'out' },
    ]
    const { coilsLit } = computePowerFlow(rung, { a: false, b: true })
    expect(coilsLit.has('q1')).toBe(true)
  })

  it('parallel: both branches false → coil NOT lit', () => {
    const rung = [
      [
        [{ id: 'c1', type: 'NO', variable: 'a' }],
        [{ id: 'c2', type: 'NO', variable: 'b' }],
      ],
      { id: 'q1', type: 'COIL', variable: 'out' },
    ]
    const { coilsLit } = computePowerFlow(rung, { a: false, b: false })
    expect(coilsLit.has('q1')).toBe(false)
  })

  it('parallel: both branches true → coil lit', () => {
    const rung = [
      [
        [{ id: 'c1', type: 'NO', variable: 'a' }],
        [{ id: 'c2', type: 'NO', variable: 'b' }],
      ],
      { id: 'q1', type: 'COIL', variable: 'out' },
    ]
    const { coilsLit } = computePowerFlow(rung, { a: true, b: true })
    expect(coilsLit.has('q1')).toBe(true)
  })

  it('series contact before parallel group must also be true', () => {
    const rung = [
      { id: 'c0', type: 'NO', variable: 'enable' },
      [
        [{ id: 'c1', type: 'NO', variable: 'a' }],
        [{ id: 'c2', type: 'NO', variable: 'b' }],
      ],
      { id: 'q1', type: 'COIL', variable: 'out' },
    ]
    // enable=false means no power regardless of parallel branches
    const { coilsLit } = computePowerFlow(rung, { enable: false, a: true, b: true })
    expect(coilsLit.has('q1')).toBe(false)
  })

  it('parallel group with multi-contact series branches: AND inside OR', () => {
    const rung = [
      [
        [
          { id: 'c1', type: 'NO', variable: 'a' },
          { id: 'c2', type: 'NO', variable: 'b' },
        ],
        [{ id: 'c3', type: 'NO', variable: 'c' }],
      ],
      { id: 'q1', type: 'COIL', variable: 'out' },
    ]
    // Branch A: a AND b; Branch B: c
    // a=true, b=false → branch A false; c=true → branch B true → coil lit
    const { coilsLit } = computePowerFlow(rung, { a: true, b: false, c: true })
    expect(coilsLit.has('q1')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// 4. Coil semantics
// ---------------------------------------------------------------------------

describe('computePowerFlow — coil semantics', () => {
  it('COIL_NC energises when power NOT flowing', () => {
    const rung = [
      { id: 'c1', type: 'NO', variable: 'trip' },
      { id: 'q1', type: 'COIL_NC', variable: 'alarm' },
    ]
    // trip=false → power not flowing → COIL_NC lit
    const { coilsLit } = computePowerFlow(rung, { trip: false })
    expect(coilsLit.has('q1')).toBe(true)
  })

  it('COIL_NC NOT energised when power flowing', () => {
    const rung = [
      { id: 'c1', type: 'NO', variable: 'trip' },
      { id: 'q1', type: 'COIL_NC', variable: 'alarm' },
    ]
    const { coilsLit } = computePowerFlow(rung, { trip: true })
    expect(coilsLit.has('q1')).toBe(false)
  })

  it('SET coil energises like a normal COIL for display purposes', () => {
    const rung = [
      { id: 'c1', type: 'NO', variable: 'pb' },
      { id: 'q1', type: 'SET', variable: 'latch' },
    ]
    const { coilsLit } = computePowerFlow(rung, { pb: true })
    expect(coilsLit.has('q1')).toBe(true)
  })

  it('RESET coil energises like a normal COIL for display purposes', () => {
    const rung = [
      { id: 'c1', type: 'NO', variable: 'pb' },
      { id: 'q1', type: 'RESET', variable: 'latch' },
    ]
    const { coilsLit } = computePowerFlow(rung, { pb: true })
    expect(coilsLit.has('q1')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// 5. colorForState helper
// ---------------------------------------------------------------------------

describe('colorForState', () => {
  it('lit=true → green (#34d399) for a NO contact', () => {
    expect(colorForState(true, 'NO')).toBe('#34d399')
  })

  it('lit=true → green (#34d399) for an NC contact', () => {
    expect(colorForState(true, 'NC')).toBe('#34d399')
  })

  it('lit=true → green (#34d399) for a COIL', () => {
    expect(colorForState(true, 'COIL')).toBe('#34d399')
  })

  it('lit=false for a contact → dim grey (#6b7280)', () => {
    expect(colorForState(false, 'NO')).toBe('#6b7280')
    expect(colorForState(false, 'NC')).toBe('#6b7280')
    expect(colorForState(false, 'R_TRIG')).toBe('#6b7280')
    expect(colorForState(false, 'F_TRIG')).toBe('#6b7280')
  })

  it('lit=false for a COIL → red (#f87171) — broken wire indicator', () => {
    expect(colorForState(false, 'COIL')).toBe('#f87171')
  })

  it('lit=false for SET coil → red (#f87171)', () => {
    expect(colorForState(false, 'SET')).toBe('#f87171')
  })

  it('lit=false for RESET coil → red (#f87171)', () => {
    expect(colorForState(false, 'RESET')).toBe('#f87171')
  })

  it('lit=false for COIL_NC → red (#f87171)', () => {
    expect(colorForState(false, 'COIL_NC')).toBe('#f87171')
  })
})

// ---------------------------------------------------------------------------
// 6. Edge cases
// ---------------------------------------------------------------------------

describe('computePowerFlow — edge cases', () => {
  it('empty rung returns empty sets', () => {
    const { contactsLit, coilsLit, wiresLit } = computePowerFlow([], {})
    expect(contactsLit.size).toBe(0)
    expect(coilsLit.size).toBe(0)
    expect(wiresLit.size).toBe(0)
  })

  it('null rung returns empty sets', () => {
    const { contactsLit, coilsLit, wiresLit } = computePowerFlow(null, {})
    expect(contactsLit.size).toBe(0)
    expect(coilsLit.size).toBe(0)
    expect(wiresLit.size).toBe(0)
  })

  it('null variableState defaults to all-false', () => {
    const rung = [{ id: 'c1', type: 'NO', variable: 'x' }]
    const { contactsLit } = computePowerFlow(rung, null)
    expect(contactsLit.has('c1')).toBe(false)
  })

  it('rung with no coils still evaluates contacts correctly', () => {
    const rung = [{ id: 'c1', type: 'NO', variable: 'a' }]
    const { contactsLit } = computePowerFlow(rung, { a: true })
    expect(contactsLit.has('c1')).toBe(true)
  })

  it('accepts Map as variableState', () => {
    const rung = [
      { id: 'c1', type: 'NO', variable: 'motor_on' },
      { id: 'q1', type: 'COIL', variable: 'output' },
    ]
    const state = new Map([['motor_on', true]])
    const { coilsLit } = computePowerFlow(rung, state)
    expect(coilsLit.has('q1')).toBe(true)
  })
})
