/**
 * hdriPresets.test.js — Vitest suite for the HDRI preset registry.
 */

import { describe, it, expect } from 'vitest'
import { HDRI_PRESETS, getPresetBySlug } from './hdriPresets.js'

// ── Registry shape ─────────────────────────────────────────────────────────────

describe('HDRI_PRESETS registry', () => {
  it('contains exactly 5 entries', () => {
    expect(HDRI_PRESETS).toHaveLength(5)
  })

  it('all slugs are distinct', () => {
    const slugs = HDRI_PRESETS.map((p) => p.slug)
    const unique = new Set(slugs)
    expect(unique.size).toBe(HDRI_PRESETS.length)
  })

  it('all file_url paths are consistent with /hdri/<slug>.hdr', () => {
    HDRI_PRESETS.forEach((p) => {
      expect(p.file_url).toBe(`/hdri/${p.slug}.hdr`)
    })
  })

  it('all entries have the required string fields', () => {
    const required = ['slug', 'name', 'file_url', 'license', 'source', 'description']
    HDRI_PRESETS.forEach((p) => {
      required.forEach((field) => {
        expect(typeof p[field], `${p.slug}.${field}`).toBe('string')
        expect(p[field].length, `${p.slug}.${field} is non-empty`).toBeGreaterThan(0)
      })
    })
  })

  it('all entries have a numeric intensity > 0', () => {
    HDRI_PRESETS.forEach((p) => {
      expect(typeof p.intensity, `${p.slug}.intensity`).toBe('number')
      expect(p.intensity, `${p.slug}.intensity > 0`).toBeGreaterThan(0)
    })
  })

  it('includes the five expected slugs', () => {
    const slugs = HDRI_PRESETS.map((p) => p.slug)
    expect(slugs).toContain('clear-noon')
    expect(slugs).toContain('overcast')
    expect(slugs).toContain('sunset')
    expect(slugs).toContain('studio-soft')
    expect(slugs).toContain('night-stars')
  })

  it('all entries have a thumbnail_url field (string or null)', () => {
    HDRI_PRESETS.forEach((p) => {
      const ok = typeof p.thumbnail_url === 'string' || p.thumbnail_url === null
      expect(ok, `${p.slug}.thumbnail_url must be string or null`).toBe(true)
    })
  })
})

// ── getPresetBySlug ────────────────────────────────────────────────────────────

describe('getPresetBySlug', () => {
  it('returns the correct preset for a known slug', () => {
    const preset = getPresetBySlug('sunset')
    expect(preset).toBeDefined()
    expect(preset.slug).toBe('sunset')
    expect(preset.name).toBe('Sunset')
  })

  it('returns undefined for an unknown slug', () => {
    expect(getPresetBySlug('nonexistent')).toBeUndefined()
  })

  it('returns a preset whose file_url matches the slug pattern', () => {
    const preset = getPresetBySlug('studio-soft')
    expect(preset.file_url).toBe('/hdri/studio-soft.hdr')
  })

  it('each preset can be retrieved by its own slug', () => {
    HDRI_PRESETS.forEach((p) => {
      const found = getPresetBySlug(p.slug)
      expect(found).toBe(p)
    })
  })
})
