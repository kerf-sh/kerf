// printSliceView.test.js — unit tests for the pure helpers exported by
// PrintSliceView.jsx. DOM rendering is not tested here; we only validate the
// parsePrintConfig, parseGcodeLayers helpers and the DEFAULT_SETTINGS shape
// so the FileTree icon and the view's parsing logic are covered without
// needing a jsdom/canvas environment.

import { describe, it, expect } from 'vitest'
import {
  parsePrintConfig,
  parseGcodeLayers,
  DEFAULT_SETTINGS,
} from '../components/PrintSliceView.jsx'

// ---------------------------------------------------------------------------
// parsePrintConfig
// ---------------------------------------------------------------------------

describe('parsePrintConfig', () => {
  it('returns empty for null / undefined / empty string', () => {
    expect(parsePrintConfig(null).kind).toBe('empty')
    expect(parsePrintConfig(undefined).kind).toBe('empty')
    expect(parsePrintConfig('').kind).toBe('empty')
    expect(parsePrintConfig('   ').kind).toBe('empty')
  })

  it('returns invalid for non-JSON content', () => {
    expect(parsePrintConfig('{ not json').kind).toBe('invalid')
    expect(parsePrintConfig('[1,2,3]').kind).toBe('invalid')
  })

  it('parses a well-formed .print config', () => {
    const r = parsePrintConfig(JSON.stringify({
      version: 1,
      mesh_ref: '/models/bracket.stl',
      settings: { layer_height: 0.15, infill_density: 30 },
    }))
    expect(r.kind).toBe('ok')
    expect(r.meshRef).toBe('/models/bracket.stl')
    expect(r.settings.layer_height).toBe(0.15)
    expect(r.settings.infill_density).toBe(30)
  })

  it('merges missing settings with defaults', () => {
    const r = parsePrintConfig(JSON.stringify({ version: 1 }))
    expect(r.kind).toBe('ok')
    expect(r.settings.layer_height).toBe(DEFAULT_SETTINGS.layer_height)
    expect(r.settings.infill_density).toBe(DEFAULT_SETTINGS.infill_density)
    expect(r.settings.perimeters).toBe(DEFAULT_SETTINGS.perimeters)
    expect(r.settings.retraction_enabled).toBe(DEFAULT_SETTINGS.retraction_enabled)
    expect(r.settings.print_temperature).toBe(DEFAULT_SETTINGS.print_temperature)
    expect(r.settings.bed_temperature).toBe(DEFAULT_SETTINGS.bed_temperature)
  })

  it('meshRef defaults to empty string when absent', () => {
    const r = parsePrintConfig(JSON.stringify({ version: 1 }))
    expect(r.kind).toBe('ok')
    expect(r.meshRef).toBe('')
  })

  it('meshRef defaults to empty string when not a string', () => {
    const r = parsePrintConfig(JSON.stringify({ mesh_ref: 42 }))
    expect(r.kind).toBe('ok')
    expect(r.meshRef).toBe('')
  })

  it('settings override defaults key-by-key', () => {
    const r = parsePrintConfig(JSON.stringify({
      settings: { layer_height: 0.3, perimeters: 5 },
    }))
    expect(r.settings.layer_height).toBe(0.3)
    expect(r.settings.perimeters).toBe(5)
    // others are defaults
    expect(r.settings.infill_density).toBe(DEFAULT_SETTINGS.infill_density)
  })
})

// ---------------------------------------------------------------------------
// parseGcodeLayers
// ---------------------------------------------------------------------------

const SAMPLE_GCODE = `
;FLAVOR:Marlin
;TIME:300
;LAYER_COUNT:3
G28
;LAYER:0
G1 X10 Y10 E0.1 F3000
G1 X20 Y10 E0.2
G1 X20 Y20 E0.3
;LAYER:1
G1 X5 Y5 E0.4
G0 X15 Y5
;LAYER:2
G1 X50 Y50 E0.5
`

describe('parseGcodeLayers', () => {
  it('returns empty array for null / empty input', () => {
    expect(parseGcodeLayers(null)).toEqual([])
    expect(parseGcodeLayers('')).toEqual([])
    expect(parseGcodeLayers(42)).toEqual([])
  })

  it('parses 3 layers from sample G-code', () => {
    const layers = parseGcodeLayers(SAMPLE_GCODE)
    expect(layers).toHaveLength(3)
  })

  it('layer 0 has correct X-Y points', () => {
    const layers = parseGcodeLayers(SAMPLE_GCODE)
    const l0 = layers[0]
    expect(l0.length).toBeGreaterThanOrEqual(3)
    expect(l0[0]).toEqual([10, 10])
    expect(l0[1]).toEqual([20, 10])
    expect(l0[2]).toEqual([20, 20])
  })

  it('G0 moves are included', () => {
    const layers = parseGcodeLayers(SAMPLE_GCODE)
    const l1 = layers[1]
    // G1 X5 Y5 and G0 X15 Y5
    expect(l1.some(([x, y]) => x === 15 && y === 5)).toBe(true)
  })

  it('inline semicolon comments are stripped before parsing', () => {
    const gcode = ';LAYER:0\nG1 X10 Y20 ; move to start\nG1 X30 Y20\n'
    const layers = parseGcodeLayers(gcode)
    expect(layers[0][0]).toEqual([10, 20])
  })

  it('carries last X/Y forward when only one axis changes', () => {
    const gcode = ';LAYER:0\nG1 X5 Y10\nG1 Y20\n'
    const layers = parseGcodeLayers(gcode)
    // Second move only updates Y; X stays 5
    expect(layers[0][1]).toEqual([5, 20])
  })

  it('moves before first ;LAYER: comment are not included', () => {
    const gcode = 'G1 X100 Y100\n;LAYER:0\nG1 X0 Y0\n'
    const layers = parseGcodeLayers(gcode)
    expect(layers).toHaveLength(1)
    expect(layers[0][0]).toEqual([0, 0])
  })
})

// ---------------------------------------------------------------------------
// DEFAULT_SETTINGS shape
// ---------------------------------------------------------------------------

describe('DEFAULT_SETTINGS', () => {
  it('has all required Tier 1 keys with sensible defaults', () => {
    expect(DEFAULT_SETTINGS.layer_height).toBe(0.2)
    expect(DEFAULT_SETTINGS.infill_density).toBe(20)
    expect(DEFAULT_SETTINGS.perimeters).toBe(3)
    expect(DEFAULT_SETTINGS.retraction_enabled).toBe(true)
    expect(DEFAULT_SETTINGS.print_temperature).toBe(200)
    expect(DEFAULT_SETTINGS.bed_temperature).toBe(60)
  })
})
