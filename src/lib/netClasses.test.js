import { describe, it, expect } from 'vitest'
import {
  defaultNetClasses,
  findNetClass,
  assignNetToClass,
  defineNetClass,
  removeNetClass,
  effectiveRulesForNet,
} from './netClasses.js'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeCircuit(overrides = {}) {
  return {
    type: 'pcb_board',
    width: 50,
    height: 50,
    ...overrides,
  }
}

// ── defaultNetClasses ─────────────────────────────────────────────────────────

describe('defaultNetClasses', () => {
  it('returns exactly 5 classes', () => {
    expect(defaultNetClasses()).toHaveLength(5)
  })

  it('includes Default, Power, Signal, HighSpeed, Differential', () => {
    const names = defaultNetClasses().map(c => c.name)
    expect(names).toContain('Default')
    expect(names).toContain('Power')
    expect(names).toContain('Signal')
    expect(names).toContain('HighSpeed')
    expect(names).toContain('Differential')
  })

  it('HighSpeed has target_impedance_ohms = 50', () => {
    const hs = defaultNetClasses().find(c => c.name === 'HighSpeed')
    expect(hs.target_impedance_ohms).toBe(50)
  })

  it('returns a deep copy (mutation does not affect next call)', () => {
    const first = defaultNetClasses()
    first[0].trace_width_mm = 99
    const second = defaultNetClasses()
    expect(second[0].trace_width_mm).not.toBe(99)
  })
})

// ── findNetClass ──────────────────────────────────────────────────────────────

describe('findNetClass', () => {
  it('returns Default when net has no assignment', () => {
    const circuit = makeCircuit()
    expect(findNetClass(circuit, 'GND')).toBe('Default')
  })

  it('returns the assigned class name', () => {
    const circuit = makeCircuit({
      net_class_assignments: { GND: 'Power' },
    })
    expect(findNetClass(circuit, 'GND')).toBe('Power')
  })

  it('returns Default for an unknown net even when assignments exist', () => {
    const circuit = makeCircuit({
      net_class_assignments: { GND: 'Power' },
    })
    expect(findNetClass(circuit, 'VCC')).toBe('Default')
  })
})

// ── assignNetToClass ──────────────────────────────────────────────────────────

describe('assignNetToClass', () => {
  it('assigns a builtin class and returns a new object', () => {
    const circuit = makeCircuit()
    const result = assignNetToClass(circuit, 'GND', 'Power')
    expect(result).not.toBe(circuit)
    expect(findNetClass(result, 'GND')).toBe('Power')
  })

  it('does not mutate the original circuit', () => {
    const circuit = makeCircuit()
    assignNetToClass(circuit, 'GND', 'Power')
    expect(circuit.net_class_assignments).toBeUndefined()
  })

  it('is idempotent — assigning the same class twice yields same result', () => {
    const circuit = makeCircuit()
    const r1 = assignNetToClass(circuit, 'GND', 'Power')
    const r2 = assignNetToClass(r1, 'GND', 'Power')
    expect(findNetClass(r2, 'GND')).toBe('Power')
    expect(JSON.stringify(r1)).toBe(JSON.stringify(r2))
  })

  it('throws when class does not exist', () => {
    const circuit = makeCircuit()
    expect(() => assignNetToClass(circuit, 'GND', 'NonExistent')).toThrow()
  })

  it('can assign a user-defined class', () => {
    const circuit = defineNetClass(makeCircuit(), {
      name: 'RF',
      trace_width_mm: 0.18,
      clearance_mm: 0.15,
      via_diameter_mm: 0.45,
      via_drill_mm: 0.20,
      target_impedance_ohms: 50,
    })
    const result = assignNetToClass(circuit, 'ANT', 'RF')
    expect(findNetClass(result, 'ANT')).toBe('RF')
  })
})

// ── defineNetClass ────────────────────────────────────────────────────────────

describe('defineNetClass', () => {
  it('adds a new class', () => {
    const circuit = makeCircuit()
    const result = defineNetClass(circuit, {
      name: 'HV',
      trace_width_mm: 1.0,
      clearance_mm: 0.8,
      via_diameter_mm: 1.2,
      via_drill_mm: 0.6,
    })
    expect(result.net_classes).toHaveLength(1)
    expect(result.net_classes[0].name).toBe('HV')
  })

  it('updates an existing class without duplicating', () => {
    const base = defineNetClass(makeCircuit(), {
      name: 'HV',
      trace_width_mm: 1.0,
      clearance_mm: 0.8,
      via_diameter_mm: 1.2,
      via_drill_mm: 0.6,
    })
    const updated = defineNetClass(base, {
      name: 'HV',
      trace_width_mm: 1.5,
      clearance_mm: 0.8,
      via_diameter_mm: 1.2,
      via_drill_mm: 0.6,
    })
    expect(updated.net_classes).toHaveLength(1)
    expect(updated.net_classes[0].trace_width_mm).toBe(1.5)
  })

  it('does not mutate the original', () => {
    const circuit = makeCircuit()
    defineNetClass(circuit, {
      name: 'HV',
      trace_width_mm: 1.0,
      clearance_mm: 0.8,
      via_diameter_mm: 1.2,
      via_drill_mm: 0.6,
    })
    expect(circuit.net_classes).toBeUndefined()
  })
})

// ── removeNetClass ────────────────────────────────────────────────────────────

describe('removeNetClass', () => {
  it('removes the class and reassigns nets to Default', () => {
    let circuit = defineNetClass(makeCircuit(), {
      name: 'HV',
      trace_width_mm: 1.0,
      clearance_mm: 0.8,
      via_diameter_mm: 1.2,
      via_drill_mm: 0.6,
    })
    circuit = assignNetToClass(circuit, 'HVNET', 'HV')
    const result = removeNetClass(circuit, 'HV')
    expect(result.net_classes.find(c => c.name === 'HV')).toBeUndefined()
    expect(findNetClass(result, 'HVNET')).toBe('Default')
  })

  it('throws when trying to remove Default', () => {
    expect(() => removeNetClass(makeCircuit(), 'Default')).toThrow()
  })

  it('is a no-op (no error) when class was not defined in net_classes', () => {
    // Power is a builtin, not in net_classes array — removeNetClass on it is a no-op
    const circuit = makeCircuit()
    const result = removeNetClass(circuit, 'Power')
    expect(result.net_classes).toHaveLength(0)
  })
})

// ── effectiveRulesForNet ──────────────────────────────────────────────────────

describe('effectiveRulesForNet', () => {
  it('returns Default rules for an unassigned net', () => {
    const rules = effectiveRulesForNet(makeCircuit(), 'GND')
    expect(rules.net_class).toBe('Default')
    expect(rules.trace_width_mm).toBe(0.25)
  })

  it('returns the Power class rules for a Power net', () => {
    const circuit = assignNetToClass(makeCircuit(), 'VCC', 'Power')
    const rules = effectiveRulesForNet(circuit, 'VCC')
    expect(rules.net_class).toBe('Power')
    expect(rules.trace_width_mm).toBe(0.50)
  })

  it('applies per-net overrides on top of class rules', () => {
    let circuit = assignNetToClass(makeCircuit(), 'GND', 'Power')
    // Add a per-net override
    const board = circuit // single board object
    board.net_rules = { GND: { trace_width_mm: 0.8 } }
    const rules = effectiveRulesForNet(circuit, 'GND')
    expect(rules.trace_width_mm).toBe(0.8)   // override wins
    expect(rules.clearance_mm).toBe(0.25)     // still from Power class
    expect(rules.net_class).toBe('Power')
  })

  it('HighSpeed effective rules include target_impedance_ohms', () => {
    const circuit = assignNetToClass(makeCircuit(), 'CLK', 'HighSpeed')
    const rules = effectiveRulesForNet(circuit, 'CLK')
    expect(rules.target_impedance_ohms).toBe(50)
  })
})
