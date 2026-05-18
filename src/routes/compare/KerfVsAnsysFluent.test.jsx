/**
 * KerfVsAnsysFluent.test.jsx — smoke tests for the aerospace CFD/FEM compare page.
 *
 * Tests (no DOM renderer required; uses react-dom/server renderToStaticMarkup):
 *   1. Page renders without throwing.
 *   2. Hero h1 contains "Kerf vs ANSYS Fluent".
 *   3. ANSYS vendor name is present in the output.
 *   4. A feature matrix table is rendered.
 *   5. The FairnessNote GitHub issues link is present.
 *   6. STEP interop is mentioned (core CFD geometry bridge).
 */
import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import KerfVsAnsysFluentPage from './KerfVsAnsysFluent.jsx'

function render() {
  return renderToStaticMarkup(
    <MemoryRouter>
      <KerfVsAnsysFluentPage />
    </MemoryRouter>
  )
}

describe('KerfVsAnsysFluent page', () => {
  it('renders without throwing', () => {
    expect(() => render()).not.toThrow()
  })

  it('has the hero h1 heading', () => {
    const html = render()
    expect(html).toMatch(/<h1[^>]*>.*Kerf vs ANSYS Fluent.*<\/h1>/s)
  })

  it('contains the ANSYS vendor name', () => {
    const html = render()
    expect(html).toContain('ANSYS')
  })

  it('contains the Fluent product name', () => {
    const html = render()
    expect(html).toContain('Fluent')
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

  it('mentions STEP geometry interoperability', () => {
    const html = render()
    expect(html).toContain('STEP')
  })

  it('mentions CFD', () => {
    const html = render()
    expect(html).toMatch(/CFD|Navier-Stokes/i)
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
    expect(html).toMatch(/aerospace|FEM|simulation/i)
  })
})
