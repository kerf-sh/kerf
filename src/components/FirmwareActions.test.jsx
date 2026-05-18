/**
 * FirmwareActions.test.jsx — vitest tests for the FirmwareActions component.
 *
 * Uses react-dom/server renderToStaticMarkup (same pattern as Loader.test.jsx)
 * since @testing-library/react is not installed.  We test structure and content
 * of the rendered HTML, not interactive state changes.
 *
 * Key assertions:
 *   - 3 buttons are rendered (Build, Upload, Monitor)
 *   - data-testid="firmware-actions" wrapper is present
 *   - "Firmware" header label is present
 *   - Button labels match expected text
 */

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import FirmwareActions from './FirmwareActions.jsx'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function render(props = {}) {
  return renderToStaticMarkup(
    <FirmwareActions sourcePath="/tmp/sketch" {...props} />
  )
}

// ---------------------------------------------------------------------------
// 1. Structural tests
// ---------------------------------------------------------------------------

describe('FirmwareActions — structure', () => {
  it('renders the firmware-actions wrapper with data-testid', () => {
    const html = render()
    expect(html).toContain('data-testid="firmware-actions"')
  })

  it('renders exactly 3 buttons', () => {
    const html = render()
    const matches = html.match(/<button\b/g) || []
    expect(matches.length).toBe(3)
  })

  it('renders a Build button', () => {
    const html = render()
    expect(html).toContain('Build')
  })

  it('renders an Upload button', () => {
    const html = render()
    expect(html).toContain('Upload')
  })

  it('renders a Monitor button', () => {
    const html = render()
    expect(html).toContain('Monitor')
  })

  it('renders the "Firmware" section label', () => {
    const html = render()
    expect(html).toContain('Firmware')
  })
})

// ---------------------------------------------------------------------------
// 2. Button attribute tests
// ---------------------------------------------------------------------------

describe('FirmwareActions — button attributes', () => {
  it('all buttons have type="button"', () => {
    const html = render()
    const typeButton = (html.match(/type="button"/g) || []).length
    expect(typeButton).toBe(3)
  })

  it('buttons are not disabled by default (idle state)', () => {
    const html = render()
    // In idle state no button should carry the disabled attribute
    // (disabled appears only when anyLoading is true; can't trigger in SSR)
    // We just confirm buttons render without all being disabled.
    const disabledCount = (html.match(/\bdisabled\b/g) || []).length
    // Idle state: 0 disabled buttons
    expect(disabledCount).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// 3. Props forwarding
// ---------------------------------------------------------------------------

describe('FirmwareActions — props', () => {
  it('renders without fwConfig prop (defaults to null)', () => {
    // Should not throw; SSR renders cleanly
    expect(() => render({ fwConfig: null })).not.toThrow()
  })

  it('renders without onResult prop', () => {
    expect(() => render({ onResult: undefined })).not.toThrow()
  })

  it('renders with a fwConfig object', () => {
    const html = render({
      fwConfig: { board: { fqbn: 'arduino:avr:uno' } },
    })
    // Component renders; fwConfig is passed to bridge calls (not shown in HTML)
    expect(html).toContain('Build')
  })
})

// ---------------------------------------------------------------------------
// 4. ResultPanel — static rendering (idle = no result panels shown)
// ---------------------------------------------------------------------------

describe('FirmwareActions — result panels in idle', () => {
  it('shows no result panels in idle state', () => {
    const html = render()
    // In idle state no result-panel text should appear.
    // (Button labels like "Build", "Upload", "Monitor" ARE present — we check
    //  for result-specific strings that only appear in result panels.)
    expect(html).not.toContain('Build succeeded')
    expect(html).not.toContain('Build failed')
    expect(html).not.toContain('Upload failed')
    expect(html).not.toContain('Uploaded →')
    expect(html).not.toContain('Serial')
    expect(html).not.toContain('Tool not ready')
    expect(html).not.toContain('No output')
  })
})
