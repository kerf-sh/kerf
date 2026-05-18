// projectStarters.test.js — guided New Project dialog + full starter set.
//
// Covers task #208: every project domain (TAG_PRESETS) is offered with a
// one-line blurb and nudges to a real starter; STARTER_OPTIONS is the full
// set the backend can seed; the create dialog is a friendly, responsive,
// guided UI (domain card grid + guidance copy + "More options").

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'
import {
  STARTER_OPTIONS,
  DEFAULT_STARTER,
  TAG_PRESETS,
  suggestStarterFor,
} from '../lib/projectTags.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const projectsSrc = readFileSync(
  path.resolve(__dirname, '../routes/Projects.jsx'), 'utf8',
)

const starterIds = new Set(STARTER_OPTIONS.map((s) => s.id))

describe('starter catalog', () => {
  it('offers the full set the backend seeds', () => {
    expect([...starterIds].sort()).toEqual(
      ['assembly', 'blank', 'circuit', 'drawing', 'feature', 'jscad'],
    )
  })

  it('DEFAULT_STARTER is a real option', () => {
    expect(starterIds.has(DEFAULT_STARTER)).toBe(true)
  })

  it('every STARTER_OPTION has a label + hint', () => {
    for (const s of STARTER_OPTIONS) {
      expect(s.label, `label for ${s.id}`).toBeTruthy()
      expect(s.hint, `hint for ${s.id}`).toBeTruthy()
    }
  })
})

describe('domain presets — all types, guided', () => {
  it('every preset nudges to a starter the backend can seed', () => {
    for (const p of TAG_PRESETS) {
      expect(starterIds.has(p.suggestStarter), `${p.id} -> ${p.suggestStarter}`)
        .toBe(true)
    }
  })

  it('every preset has a non-empty blurb (dialog cards explain each domain)', () => {
    for (const p of TAG_PRESETS) {
      expect(typeof p.blurb).toBe('string')
      expect(p.blurb.trim().length, `blurb for ${p.id}`).toBeGreaterThan(0)
    }
  })

  it('covers the named domains the user asked for (archi, jewelry, …)', () => {
    const ids = new Set(TAG_PRESETS.map((p) => p.id))
    for (const need of ['mechanical', 'electronics', 'architecture', 'jewelry', 'pcb']) {
      expect(ids.has(need), `domain ${need}`).toBe(true)
    }
  })

  it('suggestStarterFor returns the domain starter, DEFAULT for unknown', () => {
    for (const p of TAG_PRESETS) {
      expect(suggestStarterFor([p.id])).toBe(p.suggestStarter)
    }
    expect(suggestStarterFor(['totally-made-up-tag'])).toBe(DEFAULT_STARTER)
    expect(suggestStarterFor([])).toBe(DEFAULT_STARTER)
  })
})

describe('New Project dialog — friendly, guided, responsive', () => {
  it('renders a domain card grid (DomainGrid)', () => {
    expect(projectsSrc).toContain('function DomainGrid')
    expect(projectsSrc).toContain('<DomainGrid')
  })

  it('grid is responsive (2 cols on phones, 3 on larger screens)', () => {
    expect(projectsSrc).toContain('grid-cols-2 sm:grid-cols-3')
  })

  it('guides the user with copy + a question label', () => {
    expect(projectsSrc).toContain('What are you designing?')
    expect(projectsSrc).toMatch(/pick what you.{0,3}re designing/i)
  })

  it('keeps advanced fields behind a "More options" disclosure', () => {
    expect(projectsSrc).toContain('More options')
    expect(projectsSrc).toContain('showMore')
  })

  it('dialog body scrolls on small screens', () => {
    expect(projectsSrc).toContain('overflow-y-auto')
  })
})
