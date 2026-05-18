/**
 * GdsLayoutPage.test.jsx — Vitest source-level suite for GdsLayoutPage.
 *
 * Verifies at the source-text level (readFileSync) — no jsdom required:
 *   1. The component renders an upload affordance.
 *   2. The component wires parseGds from gdsLoader.js.
 *   3. Errors from parseGds are surfaced to the user.
 *   4. The LayoutViewer is conditionally rendered with the parsed layout.
 *   5. The TODO comment is present for App.jsx route wiring.
 *
 * For the gdsLoader fetch bridge, see src/lib/gdsLoader.test.js which covers
 * error normalisation and the fetch contract.
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const read = (p) => readFileSync(join(root, p), 'utf8')

const PAGE_SRC = read('components/GdsLayoutPage.jsx')
const LOADER_SRC = read('lib/gdsLoader.js')

// ---------------------------------------------------------------------------
// Upload affordance
// ---------------------------------------------------------------------------

describe('GdsLayoutPage — upload affordance', () => {
  it('exports a default function GdsLayoutPage', () => {
    expect(PAGE_SRC).toMatch(/export default function GdsLayoutPage/)
  })

  it('renders an upload zone with role=button and aria-label for accessibility', () => {
    expect(PAGE_SRC).toContain('role="button"')
    expect(PAGE_SRC).toContain('aria-label="Upload GDS file"')
  })

  it('has a file input that accepts .gds files', () => {
    expect(PAGE_SRC).toContain('accept=".gds')
    expect(PAGE_SRC).toContain('type="file"')
  })

  it('has data-testid="gds-upload-zone" for test targeting', () => {
    expect(PAGE_SRC).toContain('data-testid="gds-upload-zone"')
  })

  it('has data-testid="gds-file-input" on the hidden input', () => {
    expect(PAGE_SRC).toContain('data-testid="gds-file-input"')
  })

  it('supports drag-and-drop (onDrop handler present)', () => {
    expect(PAGE_SRC).toContain('onDrop={handleDrop}')
    expect(PAGE_SRC).toContain('onDragOver={handleDragOver}')
  })
})

// ---------------------------------------------------------------------------
// Error surfacing
// ---------------------------------------------------------------------------

describe('GdsLayoutPage — error display', () => {
  it('shows an error alert element', () => {
    expect(PAGE_SRC).toContain('data-testid="gds-error"')
    expect(PAGE_SRC).toContain('role="alert"')
  })

  it('exposes the error message from state', () => {
    expect(PAGE_SRC).toContain('{error}')
  })

  it('offers a "Try another file" recovery button', () => {
    expect(PAGE_SRC).toContain('Try another file')
  })

  it('clears error state when recovery button is clicked', () => {
    expect(PAGE_SRC).toContain('setError(null)')
  })
})

// ---------------------------------------------------------------------------
// parseGds integration
// ---------------------------------------------------------------------------

describe('GdsLayoutPage — gdsLoader integration', () => {
  it('imports parseGds from gdsLoader.js', () => {
    expect(PAGE_SRC).toContain("from '../lib/gdsLoader.js'")
    expect(PAGE_SRC).toContain('parseGds')
  })

  it('calls parseGds with the selected file', () => {
    expect(PAGE_SRC).toContain('await parseGds(file)')
  })

  it('mounts LayoutViewer with the parsed layout', () => {
    expect(PAGE_SRC).toContain('import LayoutViewer')
    expect(PAGE_SRC).toContain('<LayoutViewer')
    expect(PAGE_SRC).toContain('layout={layout}')
  })

  it('passes the pdk prop down to LayoutViewer', () => {
    expect(PAGE_SRC).toContain('pdk={pdk}')
  })
})

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe('GdsLayoutPage — loading state', () => {
  it('shows a loading indicator while parsing', () => {
    expect(PAGE_SRC).toContain('data-testid="gds-loading"')
    expect(PAGE_SRC).toContain('aria-busy="true"')
  })

  it('sets loading state around the parseGds call', () => {
    expect(PAGE_SRC).toContain('setLoading(true)')
    expect(PAGE_SRC).toContain('setLoading(false)')
  })
})

// ---------------------------------------------------------------------------
// App.jsx wiring TODO
// ---------------------------------------------------------------------------

describe('GdsLayoutPage — App.jsx wiring TODO', () => {
  it('has a TODO comment instructing parent to wire the route in App.jsx', () => {
    expect(PAGE_SRC).toContain('TODO (App.jsx wiring)')
  })
})

// ---------------------------------------------------------------------------
// gdsLoader bridge — error normalisation
// ---------------------------------------------------------------------------

describe('gdsLoader bridge — error contract', () => {
  it('throws on non-2xx status codes', () => {
    // The loader must reject on non-ok responses
    expect(LOADER_SRC).toContain('!res.ok')
    expect(LOADER_SRC).toContain('throw new Error')
  })

  it('includes the HTTP status code in the thrown error', () => {
    expect(LOADER_SRC).toContain('res.status')
  })

  it('throws on network failures', () => {
    expect(LOADER_SRC).toContain('network')
  })

  it('throws when the cells array is missing from the response', () => {
    expect(LOADER_SRC).toContain('"cells" array')
  })

  it('throws when called with no file', () => {
    expect(LOADER_SRC).toContain('no file provided')
  })

  it('sends multipart FormData', () => {
    expect(LOADER_SRC).toContain('FormData')
    expect(LOADER_SRC).toContain("form.append('file'")
  })
})
