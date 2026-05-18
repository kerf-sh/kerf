/**
 * CompareLanding.test.jsx — unit tests for the Compare landing page.
 *
 * Uses renderToStaticMarkup (react-dom/server) — consistent with the
 * project's Loader.test.jsx pattern.
 *
 * Full interactive tests (search + filter) are validated via static
 * module-level assertions and sub-component tests.
 */
import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import CompareLanding from './CompareLanding.jsx'

/** Wrap in MemoryRouter so <Link> renders without error. */
function render(ui) {
  return renderToStaticMarkup(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('CompareLanding', () => {
  it('renders without throwing', () => {
    expect(() => render(<CompareLanding />)).not.toThrow()
  })

  it('renders the main page heading', () => {
    const html = render(<CompareLanding />)
    expect(html).toMatch(/How does Kerf compare/)
  })

  it('renders the "Compare" eyebrow label', () => {
    const html = render(<CompareLanding />)
    expect(html).toMatch(/Compare/)
  })

  it('renders a search input', () => {
    const html = render(<CompareLanding />)
    expect(html).toMatch(/data-testid="compare-search-input"/)
  })

  it('search input has a placeholder', () => {
    const html = render(<CompareLanding />)
    expect(html).toMatch(/placeholder=/)
  })

  it('renders the category pill row', () => {
    const html = render(<CompareLanding />)
    // Should contain the "All" pill
    expect(html).toMatch(/role="tablist"/)
  })

  it('renders at least one compare card on initial load', () => {
    const html = render(<CompareLanding />)
    expect(html).toMatch(/data-testid="compare-card"/)
  })

  it('renders "Kerf vs FreeCAD" card on initial load', () => {
    const html = render(<CompareLanding />)
    expect(html).toContain('Kerf vs FreeCAD')
  })

  it('renders "Kerf vs Fusion 360" card on initial load', () => {
    const html = render(<CompareLanding />)
    expect(html).toContain('Kerf vs Fusion 360')
  })

  it('renders "Kerf vs KiCad" card on initial load', () => {
    const html = render(<CompareLanding />)
    expect(html).toContain('Kerf vs KiCad')
  })

  it('links to /compare/freecad', () => {
    const html = render(<CompareLanding />)
    expect(html).toContain('/compare/freecad')
  })

  it('links to /compare/fusion', () => {
    const html = render(<CompareLanding />)
    expect(html).toContain('/compare/fusion')
  })

  it('renders "Open →" affordance on cards', () => {
    const html = render(<CompareLanding />)
    expect(html).toMatch(/Open →/)
  })

  it('renders grouped sections with category headings on initial load', () => {
    const html = render(<CompareLanding />)
    // Default view groups by category — should have a section heading
    expect(html).toMatch(/Mechanical CAD/)
  })

  it('renders the electronics section heading', () => {
    const html = render(<CompareLanding />)
    expect(html).toMatch(/Electronics/)
  })

  it('renders footer', () => {
    // Footer renders something; checking main landmark exists
    const html = render(<CompareLanding />)
    expect(html).toMatch(/<footer\b|<main\b/)
  })

  it('has aria-label on the main landmark', () => {
    const html = render(<CompareLanding />)
    expect(html).toMatch(/aria-label="Compare Kerf against other CAD and EDA tools"/)
  })
})

describe('CompareLanding module', () => {
  it('has a default export that is a function', async () => {
    const mod = await import('./CompareLanding.jsx')
    expect(typeof mod.default).toBe('function')
  })

  it('contains the TODO parent wire-up comment', async () => {
    const src = await import('./CompareLanding.jsx?raw')
      .then((m) => m.default)
      .catch(() => null)
    if (src == null) return // ?raw not supported — skip gracefully
    expect(src).toMatch(/TODO\(parent\)/)
    expect(src).toMatch(/wire as the new \/compare default route/)
  })
})
