// CurvatureCombOverlay.test.jsx — T-K2: curvature comb overlay contrast/labelling.
//
// Strategy: source-file structural checks via readFileSync.  The component
// depends on THREE.js and a Web Worker which cannot be instantiated in a Vitest
// Node environment, so we inspect the source text for the accessibility fixes.
//
// Tests cover:
//   1. Legend text has been bumped from #6b7280 (3.86:1 — FAILS AA) to
//      #9ca3af (7.35:1 — PASSES AA).
//   2. Panel container has an accessible region label (aria-label on <section>).
//   3. Toggle button carries aria-pressed for state announcement.
//   4. Toggle button has an aria-label describing the action.
//   5. Error notice uses role="alert" so it is announced on appearance.
//   6. Colour legend is present as a <dl> with aria-label.
//   7. No forbidden low-contrast colour #6b7280 remains in panel text paths.
//
// Contrast check helper — pure JS, no DOM required.

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const src = readFileSync(
  path.resolve(__dirname, './CurvatureCombOverlay.jsx'),
  'utf8',
)

// ---------------------------------------------------------------------------
// Inline WCAG contrast helper (no external deps)
// ---------------------------------------------------------------------------
function toLinear(c) {
  const s = c / 255
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
}
function luminance(r, g, b) {
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b)
}
function contrastRatio(l1, l2) {
  const lighter = Math.max(l1, l2)
  const darker  = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}
function hexToRgb(hex) {
  const h = hex.replace('#', '')
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ]
}

// Panel background: rgba(18,18,24,0.92) treated as opaque
const BG = [18, 18, 24]

describe('CurvatureCombOverlay T-K2 — contrast + labelling', () => {
  // --- Contrast checks ---

  it('legend text colour #9ca3af meets WCAG AA (≥4.5:1) against panel bg', () => {
    const fg  = hexToRgb('9ca3af')
    const bgL = luminance(...BG)
    const fgL = luminance(...fg)
    const ratio = contrastRatio(fgL, bgL)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  it('primary text colour #e5e7eb meets WCAG AA (≥4.5:1) against panel bg', () => {
    const fg  = hexToRgb('e5e7eb')
    const bgL = luminance(...BG)
    const fgL = luminance(...fg)
    const ratio = contrastRatio(fgL, bgL)
    expect(ratio).toBeGreaterThanOrEqual(4.5)
  })

  it('does not use the low-contrast grey #6b7280 for panel text', () => {
    // #6b7280 gives only 3.86:1 — below WCAG AA for small text.
    // It must not appear in the CurvatureCombPanel JSX section.
    // We allow it in comments or the pure-logic section above the component.
    const panelStart = src.indexOf('export function CurvatureCombPanel')
    expect(panelStart).toBeGreaterThan(-1)
    const panelSrc = src.slice(panelStart)
    // Strip both // line comments and {/* … */} JSX block comments before checking
    const noComments = panelSrc
      .replace(/\/\/[^\n]*/g, '')          // // line comments
      .replace(/\{\/\*[\s\S]*?\*\/\}/g, '') // {/* block comments */}
    expect(noComments).not.toContain('#6b7280')
  })

  // --- Accessible labelling checks ---

  it('panel container is a <section> with aria-label', () => {
    expect(src).toContain('<section')
    expect(src).toContain('aria-label="Curvature Combs overlay controls"')
  })

  it('panel heading is an <h2> element', () => {
    expect(src).toContain('<h2')
    expect(src).toContain('Curvature Combs')
  })

  it('toggle button carries aria-pressed for state announcement', () => {
    expect(src).toContain('aria-pressed={enabled}')
  })

  it('toggle button has an aria-label', () => {
    // The aria-label should describe the action for each state
    expect(src).toContain('aria-label={enabled ?')
  })

  it('error notice uses role="alert"', () => {
    expect(src).toContain('role="alert"')
  })

  it('colour legend is a <dl> with aria-label', () => {
    expect(src).toContain('<dl')
    expect(src).toContain('aria-label="Curvature colour legend"')
  })
})
