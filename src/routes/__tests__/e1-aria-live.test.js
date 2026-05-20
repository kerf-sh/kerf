/**
 * e1-aria-live.test.js — T-E1: aria-live on Projects error + scan Library/Profile
 *
 * Verifies that:
 *   - Projects.jsx page-level error banner has role="alert" + aria-live="assertive"
 *   - Library.jsx error banner has role="alert" + aria-live="assertive"
 *   - Library.jsx loading state has role="status" + aria-live="polite"
 *   - LibraryPart.jsx error card has role="alert" + aria-live="assertive"
 *   - LibraryPart.jsx loading state has role="status" + aria-live="polite"
 *   - Profile.jsx error banner has role="alert" + aria-live="assertive"
 *   - Profile.jsx success message has role="status" + aria-live="polite"
 *
 * Uses source-level checks (readFileSync) following the established pattern
 * in this codebase — no jsdom or heavy mocking required for structural ARIA
 * contract assertions.
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const PROJECTS_SRC = readFileSync(resolve(__dirname, '../Projects.jsx'), 'utf8')
const LIBRARY_SRC = readFileSync(resolve(__dirname, '../Library.jsx'), 'utf8')
const LIBRARY_PART_SRC = readFileSync(resolve(__dirname, '../LibraryPart.jsx'), 'utf8')
const PROFILE_SRC = readFileSync(resolve(__dirname, '../Profile.jsx'), 'utf8')

// ---------------------------------------------------------------------------
// Projects.jsx — page-level error banner
// ---------------------------------------------------------------------------

describe('Projects.jsx — page-level error banner a11y', () => {
  it('error banner has role="alert"', () => {
    expect(PROJECTS_SRC).toContain('role="alert"')
  })

  it('error banner has aria-live="assertive"', () => {
    expect(PROJECTS_SRC).toContain('aria-live="assertive"')
  })

  it('role="alert" and aria-live="assertive" appear close together on the error banner', () => {
    const lines = PROJECTS_SRC.split('\n')
    const alertLine = lines.findIndex((l) => l.includes('role="alert"'))
    expect(alertLine).toBeGreaterThanOrEqual(0)
    const window = lines.slice(Math.max(0, alertLine - 1), alertLine + 4).join('\n')
    expect(window).toContain('aria-live="assertive"')
  })
})

// ---------------------------------------------------------------------------
// Library.jsx — error banner + loading state
// ---------------------------------------------------------------------------

describe('Library.jsx — error banner a11y', () => {
  it('error banner has role="alert"', () => {
    expect(LIBRARY_SRC).toContain('role="alert"')
  })

  it('error banner has aria-live="assertive"', () => {
    expect(LIBRARY_SRC).toContain('aria-live="assertive"')
  })

  it('role="alert" and aria-live="assertive" appear close together on the error banner', () => {
    const lines = LIBRARY_SRC.split('\n')
    const alertLine = lines.findIndex((l) => l.includes('role="alert"'))
    expect(alertLine).toBeGreaterThanOrEqual(0)
    const window = lines.slice(Math.max(0, alertLine - 1), alertLine + 4).join('\n')
    expect(window).toContain('aria-live="assertive"')
  })
})

describe('Library.jsx — loading state a11y', () => {
  it('loading state has role="status"', () => {
    expect(LIBRARY_SRC).toContain('role="status"')
  })

  it('loading state has aria-live="polite"', () => {
    expect(LIBRARY_SRC).toContain('aria-live="polite"')
  })

  it('loading spinner has aria-hidden (decorative)', () => {
    expect(LIBRARY_SRC).toContain('aria-hidden')
  })

  it('loading state has sr-only text for screen readers', () => {
    expect(LIBRARY_SRC).toContain('sr-only')
  })
})

// ---------------------------------------------------------------------------
// LibraryPart.jsx — error state + loading state
// ---------------------------------------------------------------------------

describe('LibraryPart.jsx — error state a11y', () => {
  it('error card has role="alert"', () => {
    expect(LIBRARY_PART_SRC).toContain('role="alert"')
  })

  it('error card has aria-live="assertive"', () => {
    expect(LIBRARY_PART_SRC).toContain('aria-live="assertive"')
  })

  it('error icon has aria-hidden (decorative)', () => {
    expect(LIBRARY_PART_SRC).toContain('aria-hidden')
  })
})

describe('LibraryPart.jsx — loading state a11y', () => {
  it('loading state has role="status"', () => {
    expect(LIBRARY_PART_SRC).toContain('role="status"')
  })

  it('loading state has aria-live="polite"', () => {
    expect(LIBRARY_PART_SRC).toContain('aria-live="polite"')
  })

  it('loading state has sr-only text for screen readers', () => {
    expect(LIBRARY_PART_SRC).toContain('sr-only')
  })
})

// ---------------------------------------------------------------------------
// Profile.jsx — error banner + success message
// ---------------------------------------------------------------------------

describe('Profile.jsx — error banner a11y', () => {
  it('error banner has role="alert"', () => {
    expect(PROFILE_SRC).toContain('role="alert"')
  })

  it('error banner has aria-live="assertive"', () => {
    expect(PROFILE_SRC).toContain('aria-live="assertive"')
  })

  it('role="alert" and aria-live="assertive" appear close together on the error banner', () => {
    const lines = PROFILE_SRC.split('\n')
    const alertLine = lines.findIndex((l) => l.includes('role="alert"'))
    expect(alertLine).toBeGreaterThanOrEqual(0)
    const window = lines.slice(Math.max(0, alertLine - 1), alertLine + 4).join('\n')
    expect(window).toContain('aria-live="assertive"')
  })

  it('error icon has aria-hidden (decorative)', () => {
    expect(PROFILE_SRC).toContain('aria-hidden')
  })
})

describe('Profile.jsx — success message a11y', () => {
  it('success message has role="status"', () => {
    expect(PROFILE_SRC).toContain('role="status"')
  })

  it('success message has aria-live="polite"', () => {
    expect(PROFILE_SRC).toContain('aria-live="polite"')
  })
})
