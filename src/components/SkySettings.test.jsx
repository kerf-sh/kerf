/**
 * SkySettings.test.jsx — Vitest unit tests for the SkySettings panel.
 *
 * Uses react-dom/server (already a project dep) to render to static HTML and
 * assert on structure. No @testing-library or DOM required.
 */

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import SkySettings, { DEFAULT_SKY_SETTINGS } from './SkySettings.jsx'

// ── Helpers ────────────────────────────────────────────────────────────────────

function render(props = {}) {
  return renderToStaticMarkup(
    <SkySettings settings={{ ...DEFAULT_SKY_SETTINGS, ...props.settings }} onChange={props.onChange} />
  )
}

// ── DEFAULT_SKY_SETTINGS ───────────────────────────────────────────────────────

describe('DEFAULT_SKY_SETTINGS', () => {
  it('exports a defaults object', () => {
    expect(DEFAULT_SKY_SETTINGS).toBeDefined()
    expect(DEFAULT_SKY_SETTINGS.kind).toBe('procedural')
  })

  it('includes all required keys', () => {
    const keys = ['kind', 'elevation_deg', 'azimuth_deg', 'turbidity', 'rayleigh', 'mieCoefficient', 'mieDirectionalG']
    keys.forEach(k => expect(DEFAULT_SKY_SETTINGS).toHaveProperty(k))
  })

  it('default elevation is in range 0–90', () => {
    expect(DEFAULT_SKY_SETTINGS.elevation_deg).toBeGreaterThanOrEqual(0)
    expect(DEFAULT_SKY_SETTINGS.elevation_deg).toBeLessThanOrEqual(90)
  })

  it('default azimuth is in range 0–360', () => {
    expect(DEFAULT_SKY_SETTINGS.azimuth_deg).toBeGreaterThanOrEqual(0)
    expect(DEFAULT_SKY_SETTINGS.azimuth_deg).toBeLessThanOrEqual(360)
  })
})

// ── Kind selector ──────────────────────────────────────────────────────────────

describe('SkySettings — kind selector', () => {
  it('renders three radio buttons: none, procedural, hdri', () => {
    const html = render()
    expect(html).toMatch(/value="none"/)
    expect(html).toMatch(/value="procedural"/)
    expect(html).toMatch(/value="hdri"/)
  })

  it('marks procedural radio as checked when kind=procedural', () => {
    const html = render({ settings: { kind: 'procedural' } })
    // React may place checked="" before or after value=; check both orderings.
    const hasChecked = /value="procedural"[^/]*checked/.test(html) ||
                       /checked=""[^/]*value="procedural"/.test(html)
    expect(hasChecked).toBe(true)
  })

  it('marks none radio as checked when kind=none', () => {
    const html = render({ settings: { kind: 'none' } })
    const hasChecked = /value="none"[^/]*checked/.test(html) ||
                       /checked=""[^/]*value="none"/.test(html)
    expect(hasChecked).toBe(true)
  })

  it('shows the HDRI future-hook label', () => {
    const html = render()
    expect(html).toMatch(/HDRI/)
  })

  it('shows T-207 annotation next to HDRI option', () => {
    const html = render()
    expect(html).toMatch(/T-207/)
  })
})

// ── Procedural sliders ─────────────────────────────────────────────────────────

describe('SkySettings — procedural controls', () => {
  it('renders elevation slider when kind=procedural', () => {
    const html = render({ settings: { kind: 'procedural' } })
    expect(html).toMatch(/Elevation/)
  })

  it('renders azimuth slider when kind=procedural', () => {
    const html = render({ settings: { kind: 'procedural' } })
    expect(html).toMatch(/Azimuth/)
  })

  it('renders turbidity slider when kind=procedural', () => {
    const html = render({ settings: { kind: 'procedural' } })
    expect(html).toMatch(/Turbidity/)
  })

  it('elevation slider has min=0 and max=90', () => {
    const html = render({ settings: { kind: 'procedural' } })
    // Find the elevation slider — it should have min="0" max="90"
    expect(html).toMatch(/min="0"/)
    expect(html).toMatch(/max="90"/)
  })

  it('azimuth slider has max=360', () => {
    const html = render({ settings: { kind: 'procedural' } })
    expect(html).toMatch(/max="360"/)
  })

  it('turbidity slider has min=1 and max=10', () => {
    const html = render({ settings: { kind: 'procedural' } })
    expect(html).toMatch(/min="1"/)
    expect(html).toMatch(/max="10"/)
  })

  it('hides procedural sliders when kind=none', () => {
    const html = render({ settings: { kind: 'none' } })
    expect(html).not.toMatch(/Elevation/)
    expect(html).not.toMatch(/Azimuth/)
  })

  it('hides procedural sliders when kind=hdri', () => {
    const html = render({ settings: { kind: 'hdri' } })
    expect(html).not.toMatch(/Elevation/)
  })
})

// ── HDRI placeholder ───────────────────────────────────────────────────────────

describe('SkySettings — HDRI placeholder', () => {
  it('shows coming-soon note when kind=hdri', () => {
    const html = render({ settings: { kind: 'hdri' } })
    expect(html).toMatch(/T-207/)
    // Should show some placeholder text
    expect(html).toMatch(/coming in T-207/)
  })

  it('does not show HDRI placeholder when kind=procedural', () => {
    const html = render({ settings: { kind: 'procedural' } })
    expect(html).not.toMatch(/coming in T-207/)
  })
})

// ── onChange wiring (smoke test) ───────────────────────────────────────────────

describe('SkySettings — onChange wiring', () => {
  it('renders without errors when onChange is undefined', () => {
    expect(() => render({ settings: { kind: 'procedural' } })).not.toThrow()
  })

  it('renders without errors when onChange is a no-op', () => {
    expect(() =>
      renderToStaticMarkup(
        <SkySettings settings={DEFAULT_SKY_SETTINGS} onChange={() => {}} />
      )
    ).not.toThrow()
  })
})
