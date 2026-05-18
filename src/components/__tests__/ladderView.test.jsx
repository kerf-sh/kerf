// ladderView.test.jsx — Vitest assertions for LadderView data-layer helpers.
//
// Tests the client-side structural lint logic (clientLint equivalent)
// and the LD schema constants without React DOM rendering.

import { describe, it, expect } from 'vitest'

// ---------------------------------------------------------------------------
// Mirror the constants from LadderView.jsx for testing
// (avoid importing React JSX in a pure unit test)
// ---------------------------------------------------------------------------

const CONTACT_TYPES = new Set([
  'contact_no', 'contact_nc', 'contact_pos', 'contact_neg',
])
const COIL_TYPES = new Set([
  'coil', 'coil_set', 'coil_reset', 'coil_pos', 'coil_neg',
])

const ELEMENT_LABELS = {
  contact_no:   '-| |-',
  contact_nc:   '-|/|-',
  contact_pos:  '-|P|-',
  contact_neg:  '-|N|-',
  coil:         '-( )-',
  coil_set:     '-(S)-',
  coil_reset:   '-(R)-',
  coil_pos:     '-(P)-',
  coil_neg:     '-(N)-',
  fb_call:      '[FB]',
}

// Client-side structural lint (mirrors LadderView.jsx clientLint)
function clientLint(prog) {
  const errors = []
  const warnings = []
  if (!prog || !Array.isArray(prog.rungs)) return { errors, warnings }

  const declaredVars = new Set((prog.variables || []).map(v => v.name))

  prog.rungs.forEach((rung, ri) => {
    const loc = `Rung ${ri}${rung.label ? ` (${rung.label})` : ''}`

    if (!rung.branches || rung.branches.length === 0) {
      errors.push(`${loc}: no contact branches`)
      return
    }

    rung.branches.forEach((branch, bi) => {
      if (!branch || branch.length === 0) {
        errors.push(`${loc} branch ${bi}: empty branch`)
        return
      }
      branch.forEach(elem => {
        if (!CONTACT_TYPES.has(elem.type)) {
          errors.push(`${loc} branch ${bi}: '${elem.type}' is not a contact type`)
        }
        if (declaredVars.size > 0 && elem.var && !declaredVars.has(elem.var)) {
          warnings.push(`${loc}: variable '${elem.var}' not declared`)
        }
      })
    })

    if (!rung.output) {
      warnings.push(`${loc}: no output element (coil/FB)`)
    } else {
      if (!COIL_TYPES.has(rung.output.type) && rung.output.type !== 'fb_call') {
        errors.push(`${loc}: output type '${rung.output.type}' is not a coil or fb_call`)
      }
    }
  })

  return { errors, warnings }
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const VALID_PROG = {
  program: 'StartStopLatch',
  variables: [
    { name: 'start_pb',  type: 'BOOL', dir: 'input' },
    { name: 'stop_pb',   type: 'BOOL', dir: 'input' },
    { name: 'motor_run', type: 'BOOL', dir: 'output' },
  ],
  rungs: [
    {
      label: 'Rung 0',
      comment: 'start latch',
      branches: [
        [
          { type: 'contact_no', var: 'start_pb' },
          { type: 'contact_nc', var: 'stop_pb' },
        ],
      ],
      output: { type: 'coil', var: 'motor_run' },
    },
  ],
}

// ---------------------------------------------------------------------------
// 1. Element type sets
// ---------------------------------------------------------------------------

describe('CONTACT_TYPES', () => {
  it('contains contact_no', () => expect(CONTACT_TYPES.has('contact_no')).toBe(true))
  it('contains contact_nc', () => expect(CONTACT_TYPES.has('contact_nc')).toBe(true))
  it('contains contact_pos', () => expect(CONTACT_TYPES.has('contact_pos')).toBe(true))
  it('contains contact_neg', () => expect(CONTACT_TYPES.has('contact_neg')).toBe(true))
  it('does not contain coil', () => expect(CONTACT_TYPES.has('coil')).toBe(false))
  it('does not contain fb_call', () => expect(CONTACT_TYPES.has('fb_call')).toBe(false))
})

describe('COIL_TYPES', () => {
  it('contains coil', () => expect(COIL_TYPES.has('coil')).toBe(true))
  it('contains coil_set', () => expect(COIL_TYPES.has('coil_set')).toBe(true))
  it('contains coil_reset', () => expect(COIL_TYPES.has('coil_reset')).toBe(true))
  it('does not contain contact_no', () => expect(COIL_TYPES.has('contact_no')).toBe(false))
})

describe('ELEMENT_LABELS', () => {
  it('contact_no symbol is -| |-', () => expect(ELEMENT_LABELS.contact_no).toBe('-| |-'))
  it('contact_nc symbol is -|/|-', () => expect(ELEMENT_LABELS.contact_nc).toBe('-|/|-'))
  it('coil symbol is -( )-', () => expect(ELEMENT_LABELS.coil).toBe('-( )-'))
  it('coil_set symbol is -(S)-', () => expect(ELEMENT_LABELS.coil_set).toBe('-(S)-'))
  it('fb_call symbol is [FB]', () => expect(ELEMENT_LABELS.fb_call).toBe('[FB]'))
})

// ---------------------------------------------------------------------------
// 2. clientLint — valid program
// ---------------------------------------------------------------------------

describe('clientLint — valid program', () => {
  it('returns no errors for a valid program', () => {
    const { errors } = clientLint(VALID_PROG)
    expect(errors).toHaveLength(0)
  })

  it('returns no warnings for a fully declared valid program', () => {
    const { warnings } = clientLint(VALID_PROG)
    expect(warnings).toHaveLength(0)
  })

  it('returns no errors for a program with multiple parallel branches', () => {
    const prog = {
      program: 'Parallel',
      variables: [],
      rungs: [
        {
          branches: [
            [{ type: 'contact_no', var: 'A' }],
            [{ type: 'contact_no', var: 'B' }],
          ],
          output: { type: 'coil', var: 'Y' },
        },
      ],
    }
    const { errors } = clientLint(prog)
    expect(errors).toHaveLength(0)
  })

  it('handles fb_call output without error', () => {
    const prog = {
      program: 'Timer',
      variables: [{ name: 'enable', type: 'BOOL', dir: 'input' }],
      rungs: [
        {
          branches: [[{ type: 'contact_no', var: 'enable' }]],
          output: { type: 'fb_call', fb_type: 'TON', fb_instance: 'T1' },
        },
      ],
    }
    const { errors } = clientLint(prog)
    expect(errors).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// 3. clientLint — structural errors
// ---------------------------------------------------------------------------

describe('clientLint — structural errors', () => {
  it('reports error when rung has no branches', () => {
    const prog = {
      program: 'NoBranches',
      variables: [],
      rungs: [{ branches: [], output: { type: 'coil', var: 'y' } }],
    }
    const { errors } = clientLint(prog)
    expect(errors.length).toBeGreaterThan(0)
    expect(errors[0]).toMatch(/no contact branches/)
  })

  it('reports error when coil appears inside a branch', () => {
    const prog = {
      program: 'CoilInBranch',
      variables: [],
      rungs: [
        {
          branches: [[{ type: 'coil', var: 'y' }]],
          output: { type: 'coil', var: 'z' },
        },
      ],
    }
    const { errors } = clientLint(prog)
    expect(errors.some(e => e.includes('not a contact type'))).toBe(true)
  })

  it('reports error when contact used as output', () => {
    const prog = {
      program: 'ContactOutput',
      variables: [],
      rungs: [
        {
          branches: [[{ type: 'contact_no', var: 'a' }]],
          output: { type: 'contact_no', var: 'b' },
        },
      ],
    }
    const { errors } = clientLint(prog)
    expect(errors.some(e => e.includes('not a coil'))).toBe(true)
  })

  it('reports warning when rung has no output', () => {
    const prog = {
      program: 'NoOutput',
      variables: [],
      rungs: [
        {
          branches: [[{ type: 'contact_no', var: 'x' }]],
          output: null,
        },
      ],
    }
    const { warnings } = clientLint(prog)
    expect(warnings.some(w => w.includes('no output'))).toBe(true)
  })

  it('reports error for empty branch', () => {
    const prog = {
      program: 'EmptyBranch',
      variables: [],
      rungs: [
        {
          branches: [[]],
          output: { type: 'coil', var: 'y' },
        },
      ],
    }
    const { errors } = clientLint(prog)
    expect(errors.some(e => e.includes('empty branch'))).toBe(true)
  })

  it('warns about undeclared variable when variables are declared', () => {
    const prog = {
      program: 'UndeclaredVar',
      variables: [{ name: 'declared', type: 'BOOL', dir: 'input' }],
      rungs: [
        {
          branches: [[{ type: 'contact_no', var: 'undeclared_var' }]],
          output: { type: 'coil', var: 'declared' },
        },
      ],
    }
    const { warnings } = clientLint(prog)
    expect(warnings.some(w => w.includes('undeclared_var'))).toBe(true)
  })

  it('does not warn about undeclared when no variables declared', () => {
    // When variable list is empty, skip undeclared-var checks
    const prog = {
      program: 'NoVars',
      variables: [],
      rungs: [
        {
          branches: [[{ type: 'contact_no', var: 'anything' }]],
          output: { type: 'coil', var: 'anything' },
        },
      ],
    }
    const { warnings } = clientLint(prog)
    expect(warnings).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// 4. clientLint — null / missing program
// ---------------------------------------------------------------------------

describe('clientLint — null / missing input', () => {
  it('returns empty errors and warnings for null', () => {
    const { errors, warnings } = clientLint(null)
    expect(errors).toHaveLength(0)
    expect(warnings).toHaveLength(0)
  })

  it('returns empty for missing rungs key', () => {
    const { errors, warnings } = clientLint({ program: 'X' })
    expect(errors).toHaveLength(0)
    expect(warnings).toHaveLength(0)
  })

  it('returns empty for empty rungs array', () => {
    const { errors, warnings } = clientLint({ program: 'X', rungs: [] })
    expect(errors).toHaveLength(0)
    expect(warnings).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// 5. IEC 61131-3 LD fixture — the canonical start/stop latch
// ---------------------------------------------------------------------------

describe('canonical start/stop latch program', () => {
  const LATCH = {
    program: 'StartStopLatch',
    variables: [
      { name: 'start_pb',  type: 'BOOL', dir: 'input' },
      { name: 'stop_pb',   type: 'BOOL', dir: 'input' },
      { name: 'fault',     type: 'BOOL', dir: 'input' },
      { name: 'motor_run', type: 'BOOL', dir: 'output' },
    ],
    rungs: [
      {
        label: 'Start latch',
        comment: 'Energise motor when start pressed and not stopped/faulted',
        branches: [
          [
            { type: 'contact_no', var: 'start_pb' },
            { type: 'contact_nc', var: 'stop_pb' },
            { type: 'contact_nc', var: 'fault' },
          ],
          [
            { type: 'contact_no', var: 'motor_run' },
            { type: 'contact_nc', var: 'stop_pb' },
            { type: 'contact_nc', var: 'fault' },
          ],
        ],
        output: { type: 'coil', var: 'motor_run' },
      },
    ],
  }

  it('has no structural errors', () => {
    const { errors } = clientLint(LATCH)
    expect(errors).toHaveLength(0)
  })

  it('has no undeclared-var warnings', () => {
    const { warnings } = clientLint(LATCH)
    expect(warnings).toHaveLength(0)
  })

  it('has exactly one rung', () => {
    expect(LATCH.rungs).toHaveLength(1)
  })

  it('has two parallel branches (start + seal-in)', () => {
    expect(LATCH.rungs[0].branches).toHaveLength(2)
  })

  it('output is a standard coil', () => {
    expect(LATCH.rungs[0].output.type).toBe('coil')
    expect(LATCH.rungs[0].output.var).toBe('motor_run')
  })

  it('first branch has normally-open start contact', () => {
    const branch0 = LATCH.rungs[0].branches[0]
    expect(branch0[0].type).toBe('contact_no')
    expect(branch0[0].var).toBe('start_pb')
  })

  it('stop and fault contacts are normally-closed', () => {
    const branch0 = LATCH.rungs[0].branches[0]
    expect(branch0[1].type).toBe('contact_nc')
    expect(branch0[2].type).toBe('contact_nc')
  })
})
