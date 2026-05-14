// simulationView.test.js — covers the pure parseSimulation helper that
// SimulationView uses to interpret `.simulation` JSON. DOM rendering is
// out of scope; we only assert the normalized shape the view consumes.

import { describe, it, expect } from 'vitest'
import {
  parseSimulation,
  normalizeWaveforms,
} from '../components/SimulationView.jsx'

describe('parseSimulation', () => {
  it('parses a well-formed transient analysis', () => {
    const r = parseSimulation(JSON.stringify({
      version: 1,
      circuit_file_id: 'c1',
      analysis: { type: 'transient', tstep: '1us', tstop: '10ms' },
      probes: [{ name: 'VOUT', kind: 'V', source_port_id: 'p1' }],
      results: { waveforms: [], warnings: [], errors: [] },
    }))
    expect(r.kind).toBe('ok')
    expect(r.spec.type).toBe('transient')
    expect(r.spec.tstep).toBe('1us')
    expect(r.spec.tstop).toBe('10ms')
    expect(r.probes).toHaveLength(1)
    expect(r.probes[0].name).toBe('VOUT')
    expect(r.results.waveforms).toEqual([])
  })

  it('parses a well-formed DC sweep', () => {
    const r = parseSimulation(JSON.stringify({
      version: 1,
      analysis: { type: 'dc', vstart: 0, vstop: 5, vstep: 0.1 },
      probes: [],
    }))
    expect(r.kind).toBe('ok')
    expect(r.spec.type).toBe('dc')
    expect(r.spec.vstart).toBe(0)
    expect(r.spec.vstop).toBe(5)
    expect(r.spec.vstep).toBeCloseTo(0.1)
  })

  it('returns unsupported for non-1 version', () => {
    const r = parseSimulation(JSON.stringify({ version: 2, analysis: {} }))
    expect(r.kind).toBe('unsupported')
    expect(typeof r.raw).toBe('string')
  })

  it('returns invalid for malformed JSON', () => {
    const r = parseSimulation('{ not json')
    expect(r.kind).toBe('invalid')
    expect(r.raw).toBe('{ not json')
  })

  it('returns invalid when top-level is not an object', () => {
    const r = parseSimulation('[1,2,3]')
    expect(r.kind).toBe('invalid')
  })

  it('defaults missing optional fields sensibly', () => {
    const r = parseSimulation(JSON.stringify({ version: 1 }))
    expect(r.kind).toBe('ok')
    expect(r.spec.type).toBe('transient')
    expect(r.probes).toEqual([])
    expect(r.results.waveforms).toEqual([])
    expect(r.results.warnings).toEqual([])
    expect(r.results.errors).toEqual([])
  })

  it('treats empty content as a fresh ok shell', () => {
    const r = parseSimulation('')
    expect(r.kind).toBe('ok')
    expect(r.probes).toEqual([])
    expect(r.results.waveforms).toEqual([])
  })

  it('drops non-object probe entries defensively', () => {
    const r = parseSimulation(JSON.stringify({
      version: 1,
      probes: [{ name: 'A', kind: 'V' }, null, 42, { name: 'B', kind: 'I' }],
    }))
    expect(r.kind).toBe('ok')
    expect(r.probes).toHaveLength(2)
    expect(r.probes.map((p) => p.name)).toEqual(['A', 'B'])
  })

  it('preserves results.errors and results.warnings arrays', () => {
    const r = parseSimulation(JSON.stringify({
      version: 1,
      results: { errors: ['ngspice exited 1'], warnings: ['no .tran convergence'] },
    }))
    expect(r.kind).toBe('ok')
    expect(r.results.errors).toEqual(['ngspice exited 1'])
    expect(r.results.warnings).toEqual(['no .tran convergence'])
    expect(r.results.waveforms).toEqual([])
  })

  it('coerces probes to [] when missing or wrong type', () => {
    const r = parseSimulation(JSON.stringify({ version: 1, probes: 'oops' }))
    expect(r.kind).toBe('ok')
    expect(r.probes).toEqual([])
  })
})

describe('normalizeWaveforms', () => {
  it('returns an empty shape for [] input', () => {
    const out = normalizeWaveforms([])
    expect(out.data).toEqual([])
    expect(out.names).toEqual([])
    expect(out.units).toEqual([])
    expect(out.warnings).toEqual([])
  })

  it('returns an empty shape for non-array input', () => {
    const out = normalizeWaveforms(null)
    expect(out.data).toEqual([])
    expect(out.names).toEqual([])
  })

  it('shapes a single waveform into [xs, ys]', () => {
    const out = normalizeWaveforms([
      { name: 'VOUT', kind: 'V', xUnit: 's', yUnit: 'V', x: [0, 1, 2], y: [0, 0.5, 1] },
    ])
    expect(out.data).toHaveLength(2)
    expect(out.data[0]).toEqual([0, 1, 2])
    expect(out.data[1]).toEqual([0, 0.5, 1])
    expect(out.names).toEqual(['VOUT'])
    expect(out.units).toEqual(['V'])
    expect(out.kinds).toEqual(['V'])
    expect(out.warnings).toEqual([])
  })

  it('aligns multiple aligned waveforms into [xs, ys1, ys2, ...]', () => {
    const out = normalizeWaveforms([
      { name: 'VOUT', kind: 'V', xUnit: 's', yUnit: 'V', x: [0, 1, 2], y: [0, 1, 2] },
      { name: 'IIN', kind: 'I', xUnit: 's', yUnit: 'A', x: [0, 1, 2], y: [10, 20, 30] },
    ])
    expect(out.data).toHaveLength(3)
    expect(out.data[0]).toEqual([0, 1, 2])
    expect(out.data[1]).toEqual([0, 1, 2])
    expect(out.data[2]).toEqual([10, 20, 30])
    expect(out.names).toEqual(['VOUT', 'IIN'])
    expect(out.units).toEqual(['V', 'A'])
    expect(out.kinds).toEqual(['V', 'I'])
    expect(out.warnings).toEqual([])
  })

  it('emits a warning when a non-canonical x array length differs', () => {
    const out = normalizeWaveforms([
      { name: 'VOUT', kind: 'V', x: [0, 1, 2, 3], y: [0, 1, 2, 3] },
      { name: 'IIN', kind: 'I', x: [0, 1], y: [5, 6] },
    ])
    expect(out.warnings).toHaveLength(1)
    expect(out.warnings[0]).toMatch(/IIN/)
    expect(out.warnings[0]).toMatch(/expected length 4/)
    expect(out.warnings[0]).toMatch(/got 2/)
    // Canonical x preserved; mismatched y is null-padded out to canonical length
    expect(out.data[0]).toEqual([0, 1, 2, 3])
    expect(out.data[1]).toEqual([0, 1, 2, 3])
    expect(out.data[2]).toHaveLength(4)
    expect(out.data[2][0]).toBe(5)
    expect(out.data[2][1]).toBe(6)
    expect(out.data[2][2]).toBeNull()
    expect(out.data[2][3]).toBeNull()
  })

  it('produces a sensible no-data shape when canonical x is empty', () => {
    const out = normalizeWaveforms([
      { name: 'A', kind: 'V', xUnit: 's', yUnit: 'V', x: [], y: [] },
      { name: 'B', kind: 'V', xUnit: 's', yUnit: 'V', x: [], y: [] },
    ])
    expect(out.data[0]).toEqual([])
    expect(out.data).toHaveLength(3)
    expect(out.names).toEqual(['A', 'B'])
    expect(out.units).toEqual(['V', 'V'])
    expect(out.warnings).toEqual([])
  })

  it('round-trips names and units in canonical order', () => {
    const out = normalizeWaveforms([
      { name: 'VBUS', kind: 'V', xUnit: 's', yUnit: 'V', x: [0, 1], y: [0, 5] },
      { name: 'ILOAD', kind: 'I', xUnit: 's', yUnit: 'mA', x: [0, 1], y: [0, 100] },
      { name: 'VFB', kind: 'V', xUnit: 's', yUnit: 'V', x: [0, 1], y: [0, 1.2] },
    ])
    expect(out.names).toEqual(['VBUS', 'ILOAD', 'VFB'])
    expect(out.units).toEqual(['V', 'mA', 'V'])
    expect(out.kinds).toEqual(['V', 'I', 'V'])
  })

  it('replaces non-finite y values with null (NaN, Infinity)', () => {
    const out = normalizeWaveforms([
      { name: 'A', kind: 'V', x: [0, 1, 2], y: [0, Number.NaN, Number.POSITIVE_INFINITY] },
    ])
    expect(out.data[1][0]).toBe(0)
    expect(out.data[1][1]).toBeNull()
    expect(out.data[1][2]).toBeNull()
  })

  it('falls back to a synthetic name when name is missing', () => {
    const out = normalizeWaveforms([
      { kind: 'V', x: [0, 1], y: [0, 1] },
      { kind: 'V', x: [0, 1], y: [2, 3] },
    ])
    expect(out.names).toEqual(['trace1', 'trace2'])
  })

  it('drops malformed waveform entries (missing x or y arrays)', () => {
    const out = normalizeWaveforms([
      { name: 'OK', kind: 'V', x: [0, 1], y: [0, 1] },
      { name: 'NOPE_X', kind: 'V', y: [0, 1] },
      { name: 'NOPE_Y', kind: 'V', x: [0, 1] },
      null,
    ])
    expect(out.names).toEqual(['OK'])
    expect(out.data).toHaveLength(2)
  })
})

