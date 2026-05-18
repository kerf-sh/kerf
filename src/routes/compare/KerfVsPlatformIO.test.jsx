/**
 * KerfVsPlatformIO.test.jsx — smoke tests for the firmware/embedded compare page.
 *
 * Tests (no DOM renderer required; uses react-dom/server renderToStaticMarkup):
 *   1. Page renders without throwing.
 *   2. Hero h1 contains "Kerf vs PlatformIO".
 *   3. PlatformIO vendor name is present in the output.
 *   4. A feature matrix table is rendered.
 *   5. The FairnessNote GitHub issues link is present.
 *   6. Firmware hex interop is mentioned (core differentiator).
 */
import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import KerfVsPlatformIOPage from './KerfVsPlatformIO.jsx'

function render() {
  return renderToStaticMarkup(
    <MemoryRouter>
      <KerfVsPlatformIOPage />
    </MemoryRouter>
  )
}

describe('KerfVsPlatformIO page', () => {
  it('renders without throwing', () => {
    expect(() => render()).not.toThrow()
  })

  it('has the hero h1 heading', () => {
    const html = render()
    expect(html).toMatch(/<h1[^>]*>.*Kerf vs PlatformIO.*<\/h1>/s)
  })

  it('contains the PlatformIO vendor name', () => {
    const html = render()
    expect(html).toContain('PlatformIO')
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

  it('mentions firmware hex output', () => {
    const html = render()
    expect(html).toMatch(/\.hex|firmware/i)
  })

  it('mentions embedded platform support', () => {
    const html = render()
    expect(html).toMatch(/AVR|STM32|ESP32|RP2040|embedded/i)
  })

  it('carries the FairnessNote GitHub issues link', () => {
    const html = render()
    expect(html).toContain('https://github.com/kerf-sh/kerf/issues')
  })

  it('has a breadcrumb link back to /compare', () => {
    const html = render()
    expect(html).toContain('href="/compare"')
  })

  it('mentions Gerber or PCB fabrication output', () => {
    const html = render()
    expect(html).toMatch(/Gerber|IPC-2581|PCB/i)
  })
})
