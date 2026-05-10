// projectTags.test.js — coverage for the project-tag preset catalog and the
// pure helpers that read from it (presetById, suggestStarterFor,
// suggestKindsFor, tagSuggestionsFor).
//
// The module isn't a normalisation/dedup layer — it's a small lookup over the
// curated TAG_PRESETS list. These tests pin down lookup behaviour and the
// fallback/merge semantics that the create dialog and FileTree rely on.

import { describe, it, expect } from 'vitest'
import {
  TAG_PRESETS,
  STARTER_OPTIONS,
  DEFAULT_STARTER,
  presetById,
  suggestStarterFor,
  suggestKindsFor,
  tagSuggestionsFor,
} from '../lib/projectTags.js'

describe('TAG_PRESETS catalog', () => {
  it('exposes a non-empty preset list with required fields', () => {
    expect(Array.isArray(TAG_PRESETS)).toBe(true)
    expect(TAG_PRESETS.length).toBeGreaterThan(0)
    for (const p of TAG_PRESETS) {
      expect(typeof p.id).toBe('string')
      expect(typeof p.label).toBe('string')
      expect(Array.isArray(p.suggestKinds)).toBe(true)
    }
  })

  it('keeps preset ids unique', () => {
    const ids = TAG_PRESETS.map((p) => p.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('only references known starter ids on each preset', () => {
    const valid = new Set(STARTER_OPTIONS.map((s) => s.id))
    for (const p of TAG_PRESETS) {
      if (p.suggestStarter) expect(valid.has(p.suggestStarter)).toBe(true)
    }
  })

  it('exposes a default starter that exists in STARTER_OPTIONS', () => {
    expect(STARTER_OPTIONS.find((s) => s.id === DEFAULT_STARTER)).toBeTruthy()
  })
})

describe('presetById', () => {
  it('returns null for null/undefined/empty id', () => {
    expect(presetById(null)).toBeNull()
    expect(presetById(undefined)).toBeNull()
    expect(presetById('')).toBeNull()
  })

  it('returns the matching preset for a known id', () => {
    const p = presetById('mechanical')
    expect(p).toBeTruthy()
    expect(p.id).toBe('mechanical')
  })

  it('matches case-insensitively (the input is lowercased)', () => {
    const p = presetById('Mechanical')
    expect(p).toBeTruthy()
    expect(p.id).toBe('mechanical')
  })

  it('returns null for a free-text tag with no preset', () => {
    expect(presetById('made-up-tag')).toBeNull()
  })
})

describe('suggestStarterFor', () => {
  it('falls back to DEFAULT_STARTER for empty / null input', () => {
    expect(suggestStarterFor([])).toBe(DEFAULT_STARTER)
    expect(suggestStarterFor(null)).toBe(DEFAULT_STARTER)
    expect(suggestStarterFor(undefined)).toBe(DEFAULT_STARTER)
  })

  it('returns the first preset-tag starter in user-supplied order', () => {
    // electronics.suggestStarter === 'circuit'; mechanical === 'jscad'.
    expect(suggestStarterFor(['electronics', 'mechanical'])).toBe('circuit')
    expect(suggestStarterFor(['mechanical', 'electronics'])).toBe('jscad')
  })

  it('skips unknown free-text tags and uses the first preset hit', () => {
    expect(suggestStarterFor(['unknown', 'pcb'])).toBe('circuit')
  })

  it('falls back to DEFAULT_STARTER when no tag matches a preset', () => {
    expect(suggestStarterFor(['made-up', 'also-made-up'])).toBe(DEFAULT_STARTER)
  })
})

describe('suggestKindsFor', () => {
  it('returns the safe-default kinds list when no tags match a preset', () => {
    const out = suggestKindsFor(['nope'])
    expect(out).toEqual(['file', 'folder', 'sketch', 'assembly', 'drawing', 'feature', 'part'])
  })

  it('returns the safe-default kinds list for empty / null input', () => {
    expect(suggestKindsFor([]).length).toBeGreaterThan(0)
    expect(suggestKindsFor(null).length).toBeGreaterThan(0)
  })

  it('unions kinds across multiple matching tags without duplicates', () => {
    // electronics: folder, circuit, part, drawing
    // mechanical:  file, folder, sketch, assembly, drawing, feature, part
    const out = suggestKindsFor(['electronics', 'mechanical'])
    expect(new Set(out).size).toBe(out.length) // dedup
    expect(out).toContain('circuit')
    expect(out).toContain('sketch')
    expect(out).toContain('drawing')
    // Order-of-first-appearance: 'folder' from electronics comes before
    // 'sketch' from mechanical.
    expect(out.indexOf('folder')).toBeLessThan(out.indexOf('sketch'))
  })

  it('preserves the first-seen ordering across a single preset', () => {
    const out = suggestKindsFor(['electronics'])
    expect(out).toEqual(['folder', 'circuit', 'part', 'drawing'])
  })
})

describe('tagSuggestionsFor', () => {
  it('marks active flags case-insensitively against currentTags', () => {
    const out = tagSuggestionsFor(['Mechanical', 'PCB'])
    const mech = out.find((p) => p.id === 'mechanical')
    const pcb = out.find((p) => p.id === 'pcb')
    const arch = out.find((p) => p.id === 'architecture')
    expect(mech.active).toBe(true)
    expect(pcb.active).toBe(true)
    expect(arch.active).toBe(false)
  })

  it('returns one entry per preset, preserving TAG_PRESETS order', () => {
    const out = tagSuggestionsFor([])
    expect(out.length).toBe(TAG_PRESETS.length)
    for (let i = 0; i < TAG_PRESETS.length; i++) {
      expect(out[i].id).toBe(TAG_PRESETS[i].id)
      expect(out[i].active).toBe(false)
    }
  })

  it('treats null/undefined currentTags as no active tags', () => {
    const out = tagSuggestionsFor(null)
    expect(out.every((p) => p.active === false)).toBe(true)
  })
})
