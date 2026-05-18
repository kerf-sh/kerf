// AttitudeViewer.test.jsx — Vitest smoke tests for the AttitudeViewer component.
//
// Strategy: render to static HTML via react-dom/server (already a project dep).
// Three.js is dynamically imported inside a useEffect, which does NOT run in
// the SSR path, so no Three.js mock is needed. The SSR output exercises all of
// the JSX structure (container, canvas, HUD overlay, axis legend).

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import AttitudeViewer from './AttitudeViewer.jsx'

// ── Helpers ────────────────────────────────────────────────────────────────────

function render(props = {}) {
  return renderToStaticMarkup(<AttitudeViewer {...props} />)
}

// ── 1. Renders without crash ───────────────────────────────────────────────────

describe('AttitudeViewer renders without crash', () => {
  it('renders with no props (defaults)', () => {
    expect(() => render()).not.toThrow()
  })

  it('renders with identity quaternion', () => {
    expect(() => render({ quaternion: { w: 1, x: 0, y: 0, z: 0 } })).not.toThrow()
  })

  it('renders with an arbitrary unit quaternion', () => {
    const q = { w: 0.5, x: 0.5, y: 0.5, z: 0.5 }
    expect(() => render({ quaternion: q })).not.toThrow()
  })

  it('renders with custom width/height', () => {
    expect(() => render({ width: 400, height: 400 })).not.toThrow()
  })

  it('renders with extra className', () => {
    expect(() => render({ className: 'my-extra-class' })).not.toThrow()
  })
})

// ── 2. DOM structure ───────────────────────────────────────────────────────────

describe('AttitudeViewer DOM structure', () => {
  it('renders a canvas element', () => {
    const html = render()
    expect(html).toMatch(/<canvas\b/)
  })

  it('canvas carries width and height attributes', () => {
    const html = render({ width: 320, height: 320 })
    expect(html).toMatch(/width="320"/)
    expect(html).toMatch(/height="320"/)
  })

  it('container has the spacecraft attitude viewer role="img"', () => {
    const html = render()
    expect(html).toMatch(/role="img"/)
  })

  it('container has the aria-label for screen readers', () => {
    const html = render()
    expect(html).toMatch(/aria-label="Spacecraft attitude viewer"/)
  })

  it('accepts and passes through a custom className', () => {
    const html = render({ className: 'test-extra-cls' })
    expect(html).toMatch(/test-extra-cls/)
  })
})

// ── 3. Quaternion HUD readout ─────────────────────────────────────────────────

describe('AttitudeViewer HUD quaternion readout', () => {
  it('shows w=1.0000 for identity quaternion', () => {
    const html = render({ quaternion: { w: 1, x: 0, y: 0, z: 0 } })
    expect(html).toMatch(/w=1\.0000/)
  })

  it('shows x=0.0000 for identity quaternion', () => {
    const html = render({ quaternion: { w: 1, x: 0, y: 0, z: 0 } })
    expect(html).toMatch(/x=0\.0000/)
  })

  it('displays all four quaternion components w, x, y, z', () => {
    const html = render({ quaternion: { w: 0.5, x: 0.5, y: 0.5, z: 0.5 } })
    expect(html).toMatch(/w=/)
    expect(html).toMatch(/x=/)
    expect(html).toMatch(/y=/)
    expect(html).toMatch(/z=/)
  })

  it('formats components to 4 decimal places', () => {
    const html = render({ quaternion: { w: 0.70711, x: 0, y: 0, z: 0.70711 } })
    // Should have 4 decimal places for w
    expect(html).toMatch(/w=\d+\.\d{4}/)
  })

  it('defaults to identity when no quaternion prop is supplied', () => {
    const html = render()
    expect(html).toMatch(/w=1\.0000/)
  })
})

// ── 4. Axis legend ────────────────────────────────────────────────────────────

describe('AttitudeViewer axis legend', () => {
  it('shows X axis label', () => {
    const html = render()
    expect(html).toMatch(/● X/)
  })

  it('shows Y axis label', () => {
    const html = render()
    expect(html).toMatch(/● Y/)
  })

  it('shows Z axis label', () => {
    const html = render()
    expect(html).toMatch(/● Z/)
  })
})

// ── 5. Size prop wiring ────────────────────────────────────────────────────────

describe('AttitudeViewer size prop', () => {
  it('uses the supplied width for the inline style', () => {
    const html = render({ width: 480, height: 480 })
    expect(html).toMatch(/width:480px/)
  })

  it('uses the supplied height for the inline style', () => {
    const html = render({ width: 480, height: 256 })
    expect(html).toMatch(/height:256px/)
  })

  it('defaults to 320×320 when no size props are given', () => {
    const html = render()
    expect(html).toMatch(/width:320px/)
    expect(html).toMatch(/height:320px/)
  })
})
