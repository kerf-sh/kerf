// circuitObjectsPanel.test.js — vitest coverage for the pure helpers in
// CircuitObjectsPanel.jsx. We test the exported `buildPanelData` harness and
// the `formatEngineering` formatter directly; the React render is left to
// integration testing.

import { describe, it, expect } from 'vitest'
import { buildPanelData, formatEngineering } from '../components/CircuitObjectsPanel.jsx'

const comp = (id, ftype, name, extra = {}) => ({
  type: 'source_component',
  source_component_id: id,
  ftype,
  name,
  ...extra,
})
const port = (id, compId, pin) => ({
  type: 'source_port',
  source_port_id: id,
  source_component_id: compId,
  pin_number: pin,
})
const trace = (...portIds) => ({
  type: 'source_trace',
  connected_source_port_ids: portIds,
})

// V1(+) → R1 → mid → R2 → GND, V1(-) → GND
const rDivider = () => [
  comp('c_v1', 'simple_voltage_source', 'V1', { voltage: 5 }),
  comp('c_r1', 'simple_resistor', 'R1', { resistance: 1000 }),
  comp('c_r2', 'simple_resistor', 'R2', { resistance: 2000 }),
  comp('c_gnd', 'simple_ground', 'GND'),
  port('p_v1_plus', 'c_v1', 1),
  port('p_v1_minus', 'c_v1', 2),
  port('p_r1_a', 'c_r1', 1),
  port('p_r1_b', 'c_r1', 2),
  port('p_r2_a', 'c_r2', 1),
  port('p_r2_b', 'c_r2', 2),
  port('p_gnd', 'c_gnd', 1),
  trace('p_v1_plus', 'p_r1_a'),
  trace('p_r1_b', 'p_r2_a'),
  trace('p_r2_b', 'p_gnd'),
  trace('p_v1_minus', 'p_gnd'),
]

describe('formatEngineering', () => {
  it('formats 1000 as 1k', () => {
    expect(formatEngineering(1000, 'Ω')).toBe('1kΩ')
  })

  it('formats 100e-9 as 100n', () => {
    expect(formatEngineering(100e-9, 'F')).toBe('100nF')
  })

  it('formats 4_700_000 as 4.7M', () => {
    expect(formatEngineering(4_700_000, 'Ω')).toBe('4.7MΩ')
  })

  it('formats 1.5e-6 as 1.5µ', () => {
    expect(formatEngineering(1.5e-6, 'F')).toBe('1.5µF')
  })

  it('formats 0 with the bare unit', () => {
    expect(formatEngineering(0, 'Ω')).toBe('0Ω')
  })

  it('returns empty for non-numeric input', () => {
    expect(formatEngineering(null)).toBe('')
    expect(formatEngineering(undefined)).toBe('')
    expect(formatEngineering(NaN)).toBe('')
  })

  it('coerces numeric strings', () => {
    expect(formatEngineering('2200', 'Ω')).toBe('2.2kΩ')
  })

  it('uses pico for very small values', () => {
    expect(formatEngineering(22e-12, 'F')).toBe('22pF')
  })
})

describe('buildPanelData — empty input', () => {
  it('returns empty arrays for null', () => {
    expect(buildPanelData(null)).toEqual({ components: [], nets: [] })
  })

  it('returns empty arrays for []', () => {
    expect(buildPanelData([])).toEqual({ components: [], nets: [] })
  })
})

describe('buildPanelData — R divider', () => {
  const out = buildPanelData(rDivider())

  it('lists all four source_components', () => {
    expect(out.components.map((c) => c.refdes).sort()).toEqual(['GND', 'R1', 'R2', 'V1'])
  })

  it('formats resistor values with engineering notation', () => {
    const r1 = out.components.find((c) => c.refdes === 'R1')
    const r2 = out.components.find((c) => c.refdes === 'R2')
    expect(r1.value).toBe('1kΩ')
    expect(r2.value).toBe('2kΩ')
  })

  it('exposes ftype with the simple_ prefix stripped', () => {
    const r1 = out.components.find((c) => c.refdes === 'R1')
    expect(r1.ftype).toBe('resistor')
  })

  it('detects GND as net 0 with label "GND"', () => {
    const gnd = out.nets.find((n) => n.id === 0)
    expect(gnd).toBeTruthy()
    expect(gnd.label).toBe('GND')
  })

  it('numbers non-ground nets N1, N2, …', () => {
    const labels = out.nets.map((n) => n.label)
    expect(labels[0]).toBe('GND')
    expect(labels.slice(1).every((l) => /^N\d+$/.test(l))).toBe(true)
  })

  it('produces three nets total (GND, V1+/R1.a, R1.b/R2.a)', () => {
    expect(out.nets.length).toBe(3)
  })

  it('GND net touches at least three ports (V1-, R2.b, GND.1)', () => {
    const gnd = out.nets.find((n) => n.id === 0)
    expect(gnd.portCount).toBeGreaterThanOrEqual(3)
  })
})

describe('buildPanelData — fallback refdes', () => {
  it('synthesises ftype-N when source_component.name is missing', () => {
    const json = [
      comp('c_x1', 'simple_resistor', '', { resistance: 470 }),
      port('p_x1_a', 'c_x1', 1),
      port('p_x1_b', 'c_x1', 2),
      trace('p_x1_a', 'p_x1_b'),
    ]
    const out = buildPanelData(json)
    expect(out.components[0].refdes).toBe('resistor-1')
    expect(out.components[0].value).toBe('470Ω')
  })
})

describe('buildPanelData — selection contract', () => {
  // The bidirectional highlight (panel ↔ schematic) drives off the row's
  // `id` field, which must be the underlying source_component_id (so the
  // schematic side can map [data-schematic-component-id] → source via the
  // existing `schIdToSrcCompId` table). The panel test guards the contract.
  it('exposes source_component_id as the row `id`', () => {
    const out = buildPanelData(rDivider())
    const r1 = out.components.find((c) => c.refdes === 'R1')
    expect(r1).toBeTruthy()
    expect(r1.id).toBe('c_r1')
  })

  it('every row has a string id matching some source_component_id', () => {
    const json = rDivider()
    const knownIds = new Set(
      json.filter((r) => r.type === 'source_component').map((r) => r.source_component_id),
    )
    const out = buildPanelData(json)
    for (const c of out.components) {
      expect(typeof c.id).toBe('string')
      expect(knownIds.has(c.id)).toBe(true)
    }
  })

  it('row `id`s are unique across the components list', () => {
    const out = buildPanelData(rDivider())
    const ids = out.components.map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

describe('buildPanelData — Library mapping chips', () => {
  it('attaches mappedLibraryRef when parseLibraryMappings has the refdes', () => {
    const out = buildPanelData(rDivider(), { R1: 'file-uuid-1', R2: 'file-uuid-2' })
    const r1 = out.components.find((c) => c.refdes === 'R1')
    const r2 = out.components.find((c) => c.refdes === 'R2')
    expect(r1.mappedLibraryRef).toBe('file-uuid-1')
    expect(r2.mappedLibraryRef).toBe('file-uuid-2')
  })

  it('leaves mappedLibraryRef null for unmapped components', () => {
    const out = buildPanelData(rDivider(), { R1: 'file-uuid-1' })
    const r2 = out.components.find((c) => c.refdes === 'R2')
    const v1 = out.components.find((c) => c.refdes === 'V1')
    expect(r2.mappedLibraryRef).toBeNull()
    expect(v1.mappedLibraryRef).toBeNull()
  })

  it('treats every component as unmapped when no mappings argument is provided', () => {
    const out = buildPanelData(rDivider())
    for (const c of out.components) expect(c.mappedLibraryRef).toBeNull()
  })

  it('looks up refdes case-sensitively (R1 ≠ r1)', () => {
    const out = buildPanelData(rDivider(), { r1: 'file-uuid-lower' })
    const r1 = out.components.find((c) => c.refdes === 'R1')
    expect(r1.mappedLibraryRef).toBeNull()
  })
})
