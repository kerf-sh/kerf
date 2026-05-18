// QualityPicker.test.jsx — Vitest assertions for QualityPicker helpers.
//
// Pure data-layer tests: verifies getPresetMeta logic without React render
// overhead, following the project's established pattern for component tests.

import { describe, it, expect } from 'vitest'
import { getPresetMeta } from './QualityPicker.jsx'
import { QUALITY_PRESETS } from '../lib/qualityPresets.js'

// ── getPresetMeta — all four presets ──────────────────────────────────────────

describe('getPresetMeta — draft', () => {
  it('returns label "Draft"', () => {
    expect(getPresetMeta('draft').label).toBe('Draft')
  })

  it('description mentions samples', () => {
    expect(getPresetMeta('draft').description).toMatch(/1 sample/)
  })

  it('description mentions no AA', () => {
    expect(getPresetMeta('draft').description.toLowerCase()).toMatch(/no aa/)
  })

  it('shortDesc is "1 spp"', () => {
    expect(getPresetMeta('draft').shortDesc).toBe('1 spp')
  })
})

describe('getPresetMeta — preview', () => {
  it('returns label "Preview"', () => {
    expect(getPresetMeta('preview').label).toBe('Preview')
  })

  it('description mentions 4 samples', () => {
    expect(getPresetMeta('preview').description).toMatch(/4 sample/)
  })

  it('description mentions FXAA', () => {
    expect(getPresetMeta('preview').description).toMatch(/FXAA/)
  })

  it('shortDesc is "4 spp"', () => {
    expect(getPresetMeta('preview').shortDesc).toBe('4 spp')
  })
})

describe('getPresetMeta — final', () => {
  it('returns label "Final"', () => {
    expect(getPresetMeta('final').label).toBe('Final')
  })

  it('description mentions 64 samples', () => {
    expect(getPresetMeta('final').description).toMatch(/64 sample/)
  })

  it('description mentions TAA', () => {
    expect(getPresetMeta('final').description).toMatch(/TAA/)
  })

  it('shortDesc is "64 spp"', () => {
    expect(getPresetMeta('final').shortDesc).toBe('64 spp')
  })
})

describe('getPresetMeta — path_traced', () => {
  it('returns label "Path"', () => {
    expect(getPresetMeta('path_traced').label).toBe('Path')
  })

  it('description mentions 512 samples', () => {
    expect(getPresetMeta('path_traced').description).toMatch(/512 sample/)
  })

  it('description mentions TAA', () => {
    expect(getPresetMeta('path_traced').description).toMatch(/TAA/)
  })

  it('shortDesc is "512 spp"', () => {
    expect(getPresetMeta('path_traced').shortDesc).toBe('512 spp')
  })
})

// ── getPresetMeta — unknown name fallback ─────────────────────────────────────

describe('getPresetMeta — unknown name', () => {
  it('falls back gracefully for an unknown preset name', () => {
    const meta = getPresetMeta('ultra')
    expect(meta.label).toBe('ultra')
    expect(meta.description).toBe('')
    expect(meta.shortDesc).toBe('')
  })
})

// ── All four QUALITY_PRESETS have metadata ────────────────────────────────────

describe('getPresetMeta — coverage for all QUALITY_PRESETS', () => {
  it('every preset in QUALITY_PRESETS has a non-empty label', () => {
    QUALITY_PRESETS.forEach((name) => {
      const meta = getPresetMeta(name)
      expect(meta.label).toBeTruthy()
    })
  })

  it('every preset in QUALITY_PRESETS has a non-empty description', () => {
    QUALITY_PRESETS.forEach((name) => {
      const meta = getPresetMeta(name)
      expect(meta.description).toBeTruthy()
    })
  })

  it('every preset in QUALITY_PRESETS has a non-empty shortDesc', () => {
    QUALITY_PRESETS.forEach((name) => {
      const meta = getPresetMeta(name)
      expect(meta.shortDesc).toBeTruthy()
    })
  })

  it('labels are distinct across all presets', () => {
    const labels = QUALITY_PRESETS.map((name) => getPresetMeta(name).label)
    const unique = new Set(labels)
    expect(unique.size).toBe(QUALITY_PRESETS.length)
  })
})
