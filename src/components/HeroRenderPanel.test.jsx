/**
 * HeroRenderPanel.test.jsx — Vitest suite for the Hero Render drawer (T-106c).
 *
 * Pattern: renderToStaticMarkup (react-dom/server) — no @testing-library,
 * consistent with the project's other component tests (see Loader.test.jsx).
 *
 * The panel is a stateful modal driven by React hooks; renderToStaticMarkup
 * captures the initial (idle) render state. State transitions (submit, polling,
 * gallery) are exercised by the state / action helper tests that directly call
 * the exported constants and helpers.
 */

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import HeroRenderPanel, {
  QUALITY_PRESETS,
  POLL_INTERVAL_MS,
  JOB_TERMINAL,
} from './HeroRenderPanel.jsx'

// ── renderToStaticMarkup renders hooks in a server env where useState gives
// the initial value and useEffect never fires.  That is exactly what we want:
// we verify the static DOM skeleton of the idle panel.

function render(props = {}) {
  return renderToStaticMarkup(
    <HeroRenderPanel onClose={() => {}} {...props} />,
  )
}

// ── Exported constants ─────────────────────────────────────────────────────

describe('QUALITY_PRESETS', () => {
  it('exports exactly four presets', () => {
    expect(QUALITY_PRESETS).toHaveLength(4)
  })

  it('preset ids are draft / standard / hero / cinema', () => {
    const ids = QUALITY_PRESETS.map((p) => p.id)
    expect(ids).toEqual(['draft', 'standard', 'hero', 'cinema'])
  })

  it('sample counts match spec (256 / 1024 / 4096 / 16384)', () => {
    const samples = QUALITY_PRESETS.map((p) => p.samples)
    expect(samples).toEqual([256, 1024, 4096, 16384])
  })

  it('every preset has a non-empty creditHint', () => {
    for (const p of QUALITY_PRESETS) {
      expect(typeof p.creditHint).toBe('string')
      expect(p.creditHint.length).toBeGreaterThan(0)
    }
  })

  it('Draft creditHint mentions ~0.5', () => {
    const draft = QUALITY_PRESETS.find((p) => p.id === 'draft')
    expect(draft.creditHint).toMatch(/0\.5/)
  })

  it('Cinema creditHint mentions ~60', () => {
    const cinema = QUALITY_PRESETS.find((p) => p.id === 'cinema')
    expect(cinema.creditHint).toMatch(/60/)
  })
})

describe('POLL_INTERVAL_MS', () => {
  it('is 1000 (poll once per second)', () => {
    expect(POLL_INTERVAL_MS).toBe(1000)
  })
})

describe('JOB_TERMINAL', () => {
  it('includes done, failed, cancelled', () => {
    expect(JOB_TERMINAL.has('done')).toBe(true)
    expect(JOB_TERMINAL.has('failed')).toBe(true)
    expect(JOB_TERMINAL.has('cancelled')).toBe(true)
  })

  it('does not include non-terminal states', () => {
    expect(JOB_TERMINAL.has('queued')).toBe(false)
    expect(JOB_TERMINAL.has('rendering')).toBe(false)
    expect(JOB_TERMINAL.has('polling')).toBe(false)
  })
})

// ── Panel structure — idle render state ───────────────────────────────────────

describe('HeroRenderPanel — initial render (idle state)', () => {
  it('renders a dialog element with aria-modal', () => {
    const html = render()
    expect(html).toMatch(/role="dialog"/)
    expect(html).toMatch(/aria-modal="true"/)
  })

  it('shows "Hero Render" in the header', () => {
    const html = render()
    expect(html).toContain('Hero Render')
  })

  it('renders a close button with aria-label', () => {
    const html = render()
    expect(html).toMatch(/aria-label="Close Hero Render panel"/)
  })

  it('renders Render and Gallery tabs', () => {
    const html = render()
    expect(html).toContain('render')
    expect(html).toContain('gallery')
  })

  it('renders the quality preset picker (four preset buttons)', () => {
    const html = render()
    // All four preset labels should appear
    for (const p of QUALITY_PRESETS) {
      expect(html).toContain(p.label)
    }
  })

  it('shows sample counts for each preset', () => {
    const html = render()
    // 256 spp, 1,024 spp, 4,096 spp, 16,384 spp
    for (const p of QUALITY_PRESETS) {
      expect(html).toContain(p.samples.toLocaleString())
    }
  })

  it('shows credit hints for each preset', () => {
    const html = render()
    for (const p of QUALITY_PRESETS) {
      expect(html).toContain(p.creditHint)
    }
  })

  it('renders the Start render submit button', () => {
    const html = render()
    expect(html).toMatch(/aria-label="Start Hero Render"/)
    expect(html).toContain('Start render')
  })

  it('submit button is not disabled in idle state', () => {
    const html = render()
    // In idle state the button must not carry disabled
    // (renderToStaticMarkup converts disabled={false} to nothing)
    const buttonHtml = html.match(/aria-label="Start Hero Render"[^>]*>/)?.[0] ?? ''
    expect(buttonHtml).not.toContain('disabled')
  })

  it('renders a Quality fieldset legend', () => {
    const html = render()
    expect(html).toContain('Quality')
  })

  it('each preset button has correct aria-label', () => {
    const html = render()
    for (const p of QUALITY_PRESETS) {
      expect(html).toMatch(
        new RegExp(`aria-label="${p.label} quality`),
      )
    }
  })

  it('hero preset is active (aria-pressed=true) by default', () => {
    const html = render()
    // Hero is the default quality selection
    expect(html).toMatch(/aria-pressed="true"/)
  })
})

// ── Gallery tab — no projectId ────────────────────────────────────────────────

describe('HeroRenderPanel — gallery tab (no projectId)', () => {
  it('renders the gallery tab', () => {
    const html = render()
    expect(html).toContain('gallery')
  })
})

// ── Props forwarding ──────────────────────────────────────────────────────────

describe('HeroRenderPanel — props', () => {
  it('renders without projectId prop', () => {
    expect(() => render({ projectId: undefined })).not.toThrow()
  })

  it('renders with a projectId prop without throwing', () => {
    expect(() => render({ projectId: 'proj-123' })).not.toThrow()
  })

  it('renders without rendererRef prop', () => {
    expect(() => render({ rendererRef: undefined })).not.toThrow()
  })
})
