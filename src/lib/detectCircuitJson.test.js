// detectCircuitJson.test.js — Vitest assertions for the Circuit JSON heuristic.

import { describe, it, expect } from 'vitest'
import { detectCircuitJson, normaliseCircuitJson } from './detectCircuitJson.js'

// ── Sample payloads ────────────────────────────────────────────────────────

const RESISTOR_ARRAY = [
  { type: 'source_component', source_component_id: 'sc1', name: 'R1', ftype: 'simple_resistor', resistance: '10k' },
  { type: 'source_port', source_port_id: 'sp1', name: 'plus', source_component_id: 'sc1' },
  { type: 'pcb_component', pcb_component_id: 'pbc1', source_component_id: 'sc1', x: 0, y: 0, layer: 'top' },
]

const WRAPPED_PAYLOAD = { circuit_json: RESISTOR_ARRAY }

const PLAIN_OBJECT = { name: 'some project', version: '1.0', files: [] }

const RANDOM_ARRAY = [
  { id: 1, label: 'foo' },
  { id: 2, label: 'bar' },
]

const SCHEMATIC_ONLY = [
  { type: 'schematic_component', schematic_component_id: 'sc1', source_component_id: 'sc1', center: { x: 0, y: 0 } },
]

// ── detectCircuitJson ──────────────────────────────────────────────────────

describe('detectCircuitJson — positive cases', () => {
  it('detects an array of source_/pcb_/schematic_ primitives', () => {
    expect(detectCircuitJson(JSON.stringify(RESISTOR_ARRAY))).toBe(true)
  })

  it('detects a { circuit_json: [...] } wrapper object', () => {
    expect(detectCircuitJson(JSON.stringify(WRAPPED_PAYLOAD))).toBe(true)
  })

  it('detects an already-parsed array', () => {
    expect(detectCircuitJson(RESISTOR_ARRAY)).toBe(true)
  })

  it('detects an already-parsed wrapper object', () => {
    expect(detectCircuitJson(WRAPPED_PAYLOAD)).toBe(true)
  })

  it('detects array with only schematic_ items', () => {
    expect(detectCircuitJson(SCHEMATIC_ONLY)).toBe(true)
  })

  it('detects array where only some items are circuit primitives (mixed)', () => {
    const mixed = [{ type: 'pcb_trace', trace_id: 't1' }, { type: 'unrelated', x: 1 }]
    expect(detectCircuitJson(mixed)).toBe(true)
  })
})

describe('detectCircuitJson — negative cases', () => {
  it('rejects a plain object without circuit_json key', () => {
    expect(detectCircuitJson(JSON.stringify(PLAIN_OBJECT))).toBe(false)
  })

  it('rejects a random array with no circuit primitive types', () => {
    expect(detectCircuitJson(JSON.stringify(RANDOM_ARRAY))).toBe(false)
  })

  it('rejects an empty array', () => {
    expect(detectCircuitJson([])).toBe(false)
  })

  it('rejects a plain string', () => {
    expect(detectCircuitJson('hello world')).toBe(false)
  })

  it('rejects a number', () => {
    expect(detectCircuitJson(42)).toBe(false)
  })

  it('rejects null', () => {
    expect(detectCircuitJson(null)).toBe(false)
  })

  it('rejects invalid JSON string', () => {
    expect(detectCircuitJson('{bad json')).toBe(false)
  })

  it('rejects an object that merely has a "type" key not matching the prefix', () => {
    expect(detectCircuitJson([{ type: 'component', id: '1' }])).toBe(false)
  })
})

// ── normaliseCircuitJson ───────────────────────────────────────────────────

describe('normaliseCircuitJson', () => {
  it('returns the array directly for a bare array payload', () => {
    const result = normaliseCircuitJson(JSON.stringify(RESISTOR_ARRAY))
    expect(Array.isArray(result)).toBe(true)
    expect(result).toHaveLength(RESISTOR_ARRAY.length)
    expect(result[0].type).toBe('source_component')
  })

  it('unwraps the circuit_json key from a wrapper object', () => {
    const result = normaliseCircuitJson(JSON.stringify(WRAPPED_PAYLOAD))
    expect(Array.isArray(result)).toBe(true)
    expect(result).toHaveLength(RESISTOR_ARRAY.length)
  })

  it('returns null for a non-circuit JSON string', () => {
    expect(normaliseCircuitJson(JSON.stringify(PLAIN_OBJECT))).toBe(null)
  })

  it('returns null for invalid JSON', () => {
    expect(normaliseCircuitJson('{broken')).toBe(null)
  })
})
