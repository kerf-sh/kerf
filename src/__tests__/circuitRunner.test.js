// circuitRunner.test.js — coverage for the pure helpers in circuitRunner.js.
//
// runCircuit/cancelCircuit need a Worker so we can't drive them headlessly,
// but splitCircuitJson is a flat .filter()-style bucket sort and DEFAULT_CIRCUIT
// is a string seed — both fully exercisable in a Node test runner.

import { describe, it, expect } from 'vitest'
import { splitCircuitJson, DEFAULT_CIRCUIT } from '../lib/circuitRunner.js'

describe('splitCircuitJson', () => {
  it('returns empty buckets for non-array input', () => {
    const r = splitCircuitJson(null)
    expect(r.raw).toBeNull()
    expect(r.schematic).toEqual([])
    expect(r.pcb).toEqual([])
    expect(r.threeD).toEqual([])
    expect(r.errors).toEqual([])
  })

  it('returns empty buckets for empty array but preserves raw', () => {
    const r = splitCircuitJson([])
    expect(r.raw).toEqual([])
    expect(r.schematic).toHaveLength(0)
    expect(r.pcb).toHaveLength(0)
    expect(r.threeD).toHaveLength(0)
  })

  it('routes schematic_* into the schematic bucket', () => {
    const json = [
      { type: 'schematic_component', id: 'sc1' },
      { type: 'schematic_port', id: 'sp1' },
      { type: 'schematic_trace', id: 'st1' },
    ]
    const r = splitCircuitJson(json)
    expect(r.schematic).toHaveLength(3)
    expect(r.pcb).toHaveLength(0)
    expect(r.threeD).toHaveLength(0)
  })

  it('routes source_component / source_port / source_trace / source_net into schematic', () => {
    const json = [
      { type: 'source_component', id: 'A' },
      { type: 'source_port', id: 'B' },
      { type: 'source_trace', id: 'C' },
      { type: 'source_net', id: 'D' },
    ]
    const r = splitCircuitJson(json)
    expect(r.schematic.map((e) => e.id)).toEqual(['A', 'B', 'C', 'D'])
  })

  it('routes pcb_* into the pcb bucket', () => {
    const json = [
      { type: 'pcb_component', id: 'p1' },
      { type: 'pcb_smtpad', id: 'p2' },
      { type: 'pcb_trace', id: 'p3' },
    ]
    const r = splitCircuitJson(json)
    expect(r.pcb).toHaveLength(3)
    expect(r.schematic).toHaveLength(0)
  })

  it('routes cad_component and cad_* into the threeD bucket', () => {
    const json = [
      { type: 'cad_component', id: 'cad1' },
      { type: 'cad_model', id: 'cad2' },
    ]
    const r = splitCircuitJson(json)
    expect(r.threeD).toHaveLength(2)
  })

  it('captures records with error_type into errors regardless of bucket', () => {
    const json = [
      { type: 'pcb_trace', id: 'p1', error_type: 'pcb_trace_error' },
      { type: 'schematic_trace', id: 's1' },
    ]
    const r = splitCircuitJson(json)
    expect(r.errors).toHaveLength(1)
    expect(r.errors[0].id).toBe('p1')
    // error record still goes in its prefix bucket too:
    expect(r.pcb).toHaveLength(1)
  })

  it('skips entries that are null, non-object, or missing a string type', () => {
    const json = [
      null,
      'not-an-object',
      42,
      { id: 'no-type' },
      { type: 123, id: 'numeric-type' },
      { type: 'schematic_component', id: 'ok' },
    ]
    const r = splitCircuitJson(json)
    expect(r.schematic).toHaveLength(1)
    expect(r.schematic[0].id).toBe('ok')
    expect(r.pcb).toHaveLength(0)
    expect(r.threeD).toHaveLength(0)
  })

  it('passes the original array through as raw', () => {
    const json = [{ type: 'pcb_trace', id: 'x' }]
    const r = splitCircuitJson(json)
    expect(r.raw).toBe(json) // identity, not just equality
  })

  it('ignores unknown type prefixes (neither schematic/pcb/cad/source)', () => {
    const json = [
      { type: 'simulation_voltage_probe', id: 'v1' },
      { type: 'unknown_thing', id: 'x' },
    ]
    const r = splitCircuitJson(json)
    expect(r.schematic).toHaveLength(0)
    expect(r.pcb).toHaveLength(0)
    expect(r.threeD).toHaveLength(0)
    // but they're still in raw:
    expect(r.raw).toHaveLength(2)
  })
})

describe('DEFAULT_CIRCUIT', () => {
  it('is a non-empty TSX-flavoured string', () => {
    expect(typeof DEFAULT_CIRCUIT).toBe('string')
    expect(DEFAULT_CIRCUIT.length).toBeGreaterThan(50)
  })

  it('imports from tscircuit and exports a default', () => {
    expect(DEFAULT_CIRCUIT).toContain('from "tscircuit"')
    expect(DEFAULT_CIRCUIT).toContain('export default')
  })

  it('contains a board with three resistors and two traces', () => {
    expect(DEFAULT_CIRCUIT).toContain('<board')
    const resistors = DEFAULT_CIRCUIT.match(/<resistor /g) || []
    expect(resistors.length).toBe(3)
    const traces = DEFAULT_CIRCUIT.match(/<trace /g) || []
    expect(traces.length).toBe(2)
  })
})
