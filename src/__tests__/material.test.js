// material.test.js — pure-helper coverage for the Material library document
// (parse / serialize / defaultMaterial / MATERIAL_FIELD_META).
//
// Numeric fields are nullable; the editor relies on `null` to render "—".
// Round-trips MUST be lossless.

import { describe, it, expect } from 'vitest'
import {
  parseMaterial,
  serializeMaterial,
  defaultMaterial,
  MATERIAL_FIELD_META,
} from '../lib/material.js'

describe('parseMaterial', () => {
  it('returns the empty default for null/undefined/empty input', () => {
    expect(parseMaterial(null)).toEqual(defaultMaterial())
    expect(parseMaterial(undefined)).toEqual(defaultMaterial())
    expect(parseMaterial('')).toEqual(defaultMaterial())
    expect(parseMaterial('   ')).toEqual(defaultMaterial())
  })

  it('returns the empty default for malformed JSON', () => {
    const out = parseMaterial('{not json')
    expect(out.name).toBe('')
    expect(out.mechanical.E_GPa).toBeNull()
  })

  it('accepts a plain object as input (not just a JSON string)', () => {
    const obj = { name: 'Steel', mechanical: { E_GPa: 200 } }
    const out = parseMaterial(obj)
    expect(out.name).toBe('Steel')
    expect(out.mechanical.E_GPa).toBe(200)
  })

  it('coerces numeric strings inside groups to numbers', () => {
    const out = parseMaterial({ mechanical: { E_GPa: '205', nu: '0.29' } })
    expect(out.mechanical.E_GPa).toBe(205)
    expect(out.mechanical.nu).toBe(0.29)
  })

  it('keeps unknown numeric fields as null on partial groups', () => {
    const out = parseMaterial({ mechanical: { E_GPa: 70 } })
    expect(out.mechanical.E_GPa).toBe(70)
    expect(out.mechanical.G_GPa).toBeNull()
    expect(out.mechanical.yield_MPa).toBeNull()
    expect(out.thermal.k_W_mK).toBeNull()
    expect(out.physical.rho_kg_m3).toBeNull()
  })

  it('maps non-finite numbers and bad strings to null', () => {
    const out = parseMaterial({ mechanical: { E_GPa: 'foo', nu: NaN } })
    expect(out.mechanical.E_GPa).toBeNull()
    expect(out.mechanical.nu).toBeNull()
  })

  it('filters non-string entries out of common_names', () => {
    const out = parseMaterial({ common_names: ['mild steel', 1, null, 'low-carbon'] })
    expect(out.common_names).toEqual(['mild steel', 'low-carbon'])
  })

  it('always pins version 1 even when the input claims otherwise', () => {
    const out = parseMaterial({ version: 7, name: 'X' })
    expect(out.version).toBe(1)
  })
})

describe('serializeMaterial', () => {
  it('round-trips a fully-populated document losslessly', () => {
    const seed = {
      name: 'AISI 1018',
      category: 'metal/steel/carbon',
      common_names: ['mild steel'],
      color_hex: '#7d8088',
      mechanical: { E_GPa: 205, G_GPa: 80, nu: 0.29, yield_MPa: 370, ultimate_MPa: 440, elongation_pct: 15 },
      thermal: { alpha_per_K: 1.17e-5, k_W_mK: 51.9, cp_J_kgK: 486, T_min_C: -40, T_max_C: 250 },
      physical: { rho_kg_m3: 7870 },
      callout: 'AISI 1018',
      notes: 'mild steel',
    }
    const json = serializeMaterial(seed)
    expect(parseMaterial(json)).toEqual({ version: 1, ...seed })
  })

  it('drops blank common_names entries on serialize', () => {
    const json = serializeMaterial({ name: 'X', common_names: ['a', '   ', 'b'] })
    expect(parseMaterial(json).common_names).toEqual(['a', 'b'])
  })

  it('produces stable pretty-printed JSON', () => {
    const json = serializeMaterial(defaultMaterial('seed'))
    expect(json.includes('\n')).toBe(true)
    expect(json.includes('"version": 1')).toBe(true)
    expect(json.includes('"name": "seed"')).toBe(true)
  })
})

describe('defaultMaterial', () => {
  it('seeds an empty material with version 1 and null numerics', () => {
    const m = defaultMaterial()
    expect(m.version).toBe(1)
    expect(m.name).toBe('')
    expect(m.mechanical.E_GPa).toBeNull()
    expect(m.thermal.alpha_per_K).toBeNull()
    expect(m.physical.rho_kg_m3).toBeNull()
    expect(m.common_names).toEqual([])
  })

  it('accepts an optional starting name', () => {
    expect(defaultMaterial('Aluminum').name).toBe('Aluminum')
  })
})

describe('MATERIAL_FIELD_META', () => {
  it('lists every persisted numeric key in some group', () => {
    const declaredKeys = [
      ...MATERIAL_FIELD_META.mechanical.map((f) => f.key),
      ...MATERIAL_FIELD_META.thermal.map((f) => f.key),
      ...MATERIAL_FIELD_META.physical.map((f) => f.key),
    ]
    const m = defaultMaterial()
    const persistedKeys = [
      ...Object.keys(m.mechanical),
      ...Object.keys(m.thermal),
      ...Object.keys(m.physical),
    ]
    for (const k of persistedKeys) {
      expect(declaredKeys.includes(k)).toBe(true)
    }
  })
})
