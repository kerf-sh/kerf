/**
 * KerfVsCadenceSynopsys.test.jsx — smoke tests for the silicon/EDA compare page.
 *
 * Tests (no DOM renderer required; uses react-dom/server renderToStaticMarkup):
 *   1. Page renders without throwing.
 *   2. Hero h1 contains "Kerf vs Cadence / Synopsys".
 *   3. Both vendor names are present in the output.
 *   4. A feature matrix table is rendered.
 *   5. The FairnessNote GitHub issues link is present.
 *   6. GDS-II interop is mentioned (core differentiator for silicon).
 */
import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import KerfVsCadenceSynopsysPage from './KerfVsCadenceSynopsys.jsx'

function render() {
  return renderToStaticMarkup(
    <MemoryRouter>
      <KerfVsCadenceSynopsysPage />
    </MemoryRouter>
  )
}

describe('KerfVsCadenceSynopsys page', () => {
  it('renders without throwing', () => {
    expect(() => render()).not.toThrow()
  })

  it('has the hero h1 heading', () => {
    const html = render()
    expect(html).toMatch(/<h1[^>]*>.*Kerf vs Cadence.*Synopsys.*<\/h1>/s)
  })

  it('contains the Cadence vendor name', () => {
    const html = render()
    expect(html).toContain('Cadence')
  })

  it('contains the Synopsys vendor name', () => {
    const html = render()
    expect(html).toContain('Synopsys')
  })

  it('renders a feature matrix table', () => {
    const html = render()
    expect(html).toMatch(/<table\b/)
  })

  it('has a thead row in the feature matrix', () => {
    const html = render()
    expect(html).toMatch(/<thead\b/)
  })

  it('has tbody rows in the feature matrix', () => {
    const html = render()
    expect(html).toMatch(/<tbody\b/)
  })

  it('mentions GDS-II interoperability', () => {
    const html = render()
    expect(html).toContain('GDS-II')
  })

  it('mentions SPICE simulation', () => {
    const html = render()
    expect(html).toContain('SPICE')
  })

  it('carries the FairnessNote GitHub issues link', () => {
    const html = render()
    expect(html).toContain('https://github.com/kerf-sh/kerf/issues')
  })

  it('has a breadcrumb link back to /compare', () => {
    const html = render()
    expect(html).toContain('href="/compare"')
  })

  it('includes the scope disclaimer callout', () => {
    const html = render()
    expect(html).toMatch(/tape-out/i)
  })
})
