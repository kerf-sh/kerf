import { describe, it, expect } from 'vitest'
import { injectProbeRecords } from '../lib/circuitProbes.js'

const NO_PROBES = `<board><resistor name="R1" /></board>`

describe('injectProbeRecords', () => {
  it('returns a copy of circuitJson unchanged when source has no probes', () => {
    const cj = [{ type: 'source_component', source_component_id: 'r1' }]
    const out = injectProbeRecords(cj, NO_PROBES)
    expect(out).toEqual(cj)
    expect(out).not.toBe(cj)
  })

  it('synthesises one V-probe with source_port_id', () => {
    const src = `<board>\n  // @kerf-probe NAME=VOUT KIND=V PORT=src_port_abc\n</board>`
    const out = injectProbeRecords([], src)
    expect(out).toHaveLength(1)
    expect(out[0]).toEqual({
      type: 'simulation_probe',
      _kerf_probe: true,
      name: 'VOUT',
      kind: 'V',
      source_port_id: 'src_port_abc',
    })
  })

  it('synthesises two probes — V keeps source_port_id, I with simple_ component-like token uses source_component_id', () => {
    const src = `<board>
      // @kerf-probe NAME=VOUT KIND=V PORT=src_port_abc
      // @kerf-probe NAME=IQ1 KIND=I PORT=simple_q1
    </board>`
    const out = injectProbeRecords([], src)
    expect(out).toHaveLength(2)
    expect(out[0].kind).toBe('V')
    expect(out[0].source_port_id).toBe('src_port_abc')
    expect(out[0].source_component_id).toBeUndefined()
    expect(out[1].kind).toBe('I')
    expect(out[1].source_component_id).toBe('simple_q1')
    expect(out[1].source_port_id).toBeUndefined()
  })

  it('falls back to source_port_id for an I-probe whose token doesn\'t look like a component id', () => {
    const src = `// @kerf-probe NAME=IBR KIND=I PORT=src_port_xyz`
    const out = injectProbeRecords([], src)
    expect(out[0].kind).toBe('I')
    expect(out[0].source_port_id).toBe('src_port_xyz')
    expect(out[0].source_component_id).toBeUndefined()
  })

  it('does not mutate the input circuitJson array', () => {
    const cj = [{ type: 'source_component', source_component_id: 'r1' }]
    const before = cj.length
    const src = `// @kerf-probe NAME=A KIND=V PORT=p1`
    const out = injectProbeRecords(cj, src)
    expect(cj.length).toBe(before)
    expect(out).not.toBe(cj)
    expect(out).toHaveLength(before + 1)
  })

  it('handles non-array circuitJson gracefully', () => {
    const out = injectProbeRecords(null, `// @kerf-probe NAME=A KIND=V PORT=p1`)
    expect(out).toHaveLength(1)
    expect(out[0].name).toBe('A')
  })
})
