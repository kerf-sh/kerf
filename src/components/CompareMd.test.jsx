/**
 * CompareMd.test.jsx — unit tests for the CompareMd renderer.
 *
 * Uses the same pattern as Loader.test.jsx: renderToStaticMarkup (react-dom/server)
 * to render to an HTML string and assert via substring / regex.
 * No @testing-library/react dependency required.
 */

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import CompareMd from './CompareMd.jsx'

// Wrap in MemoryRouter because CompareMd renders <Link> elements.
function render(jsx) {
  return renderToStaticMarkup(
    <MemoryRouter>
      {jsx}
    </MemoryRouter>
  )
}

// ── Null/empty/falsy meta ─────────────────────────────────────────────────────

describe('CompareMd — null/empty/falsy meta', () => {
  it('renders without crashing when meta is null', () => {
    expect(() => render(<CompareMd meta={null} />)).not.toThrow()
  })

  it('renders without crashing when meta is undefined', () => {
    expect(() => render(<CompareMd meta={undefined} />)).not.toThrow()
  })

  it('renders a fallback message when meta is null', () => {
    const html = render(<CompareMd meta={null} />)
    expect(html).toContain('No comparison data')
  })

  it('renders without crashing when meta is empty object', () => {
    expect(() => render(<CompareMd meta={{}} />)).not.toThrow()
  })

  it('renders a loading state when loading=true', () => {
    const html = render(<CompareMd loading={true} meta={null} />)
    expect(html).toMatch(/loading/i)
  })

  it('renders an error state when error is set', () => {
    const html = render(<CompareMd error="404 not found" meta={null} />)
    expect(html).toContain('404 not found')
  })
})

// ── Hero rendering ────────────────────────────────────────────────────────────

describe('CompareMd — hero rendering', () => {
  const meta = {
    slug: 'fusion',
    competitor: 'Autodesk Fusion 360',
    category: 'cad-mechanical',
    hero_tagline: 'Two CAD tools, two cognitive models',
    left: 'kerf',
    right: 'fusion',
    reviewed_at: '2026-05-19',
    title: 'Kerf vs Fusion 360',
    body: '# Kerf vs Fusion 360\n\nIntro paragraph.\n',
  }

  it('renders the H1 title', () => {
    const html = render(<CompareMd meta={meta} />)
    expect(html).toContain('Kerf vs Fusion 360')
  })

  it('renders the hero tagline', () => {
    const html = render(<CompareMd meta={meta} />)
    expect(html).toContain('Two CAD tools, two cognitive models')
  })

  it('renders the reviewed_at date', () => {
    const html = render(<CompareMd meta={meta} />)
    expect(html).toContain('2026-05-19')
  })

  it('renders a "Compare" label above the H1', () => {
    const html = render(<CompareMd meta={meta} />)
    expect(html.toLowerCase()).toMatch(/compare/)
  })
})

// ── Left/right vendor invariant ────────────────────────────────────────────────

describe('CompareMd — Kerf always on the left', () => {
  const meta = {
    slug: 'fusion',
    competitor: 'Autodesk Fusion 360',
    left: 'kerf',
    right: 'fusion',
    title: 'Kerf vs Fusion 360',
    body: '',
  }

  it('data-testid="left-vendor" contains "Kerf"', () => {
    const html = render(<CompareMd meta={meta} />)
    // Find all data-testid="left-vendor" occurrences and verify Kerf is there
    const matches = [...html.matchAll(/data-testid="left-vendor"[^>]*>([^<]*)</g)]
    expect(matches.length).toBeGreaterThan(0)
    const hasKerf = matches.some((m) => m[1].trim().toLowerCase() === 'kerf')
    expect(hasKerf).toBe(true)
  })

  it('data-testid="right-vendor" contains the competitor name', () => {
    const html = render(<CompareMd meta={meta} />)
    const matches = [...html.matchAll(/data-testid="right-vendor"[^>]*>([^<]*)</g)]
    expect(matches.length).toBeGreaterThan(0)
    const hasCompetitor = matches.some((m) =>
      m[1].trim().includes('Fusion') || m[1].trim().includes('Autodesk')
    )
    expect(hasCompetitor).toBe(true)
  })

  it('Kerf vendor label appears before competitor in the HTML', () => {
    const html = render(<CompareMd meta={meta} />)
    const leftIdx = html.indexOf('data-testid="left-vendor"')
    const rightIdx = html.indexOf('data-testid="right-vendor"')
    // Both should exist
    expect(leftIdx).toBeGreaterThan(-1)
    expect(rightIdx).toBeGreaterThan(-1)
    // Left (Kerf) should appear first
    expect(leftIdx).toBeLessThan(rightIdx)
  })

  it('Kerf appears as left-vendor even when meta.left is set to something else', () => {
    const trickMeta = { ...meta, left: 'wrong-vendor' }
    // The component ignores meta.left and always uses 'kerf'
    const html = render(<CompareMd meta={trickMeta} />)
    const matches = [...html.matchAll(/data-testid="left-vendor"[^>]*>([^<]*)</g)]
    const hasKerf = matches.some((m) => m[1].trim().toLowerCase() === 'kerf')
    expect(hasKerf).toBe(true)
  })
})

// ── Body / markdown rendering ─────────────────────────────────────────────────

describe('CompareMd — body rendering', () => {
  const meta = {
    slug: 'kicad',
    competitor: 'KiCad',
    left: 'kerf',
    right: 'kicad',
    title: 'Kerf vs KiCad',
    body: `# Kerf vs KiCad

## Where KiCad is strong

- **Mature EDA.** Long track record.
- **Free.** GPL v3.

## Where Kerf differs

- **Chat-native.** Edit circuits via chat.

## Side by side

| Feature | KiCad | Kerf |
|---|---|---|
| License | ✅ GPL v3 | ✅ MIT |
| Chat editing | ❌ None | ✅ Yes |
`,
  }

  it('renders H2 section headings', () => {
    const html = render(<CompareMd meta={meta} />)
    expect(html).toContain('Where KiCad is strong')
    expect(html).toContain('Where Kerf differs')
  })

  it('renders list items', () => {
    const html = render(<CompareMd meta={meta} />)
    expect(html).toContain('Mature EDA')
    expect(html).toContain('GPL v3')
    expect(html).toContain('Chat-native')
  })

  it('renders the feature-matrix table', () => {
    const html = render(<CompareMd meta={meta} />)
    expect(html).toContain('License')
    expect(html).toContain('GPL v3')
    expect(html).toContain('MIT')
  })

  it('renders without crashing when body is empty string', () => {
    const emptyMeta = { ...meta, body: '' }
    expect(() => render(<CompareMd meta={emptyMeta} />)).not.toThrow()
  })

  it('renders without crashing when body is null', () => {
    const nullBodyMeta = { ...meta, body: null }
    expect(() => render(<CompareMd meta={nullBodyMeta} />)).not.toThrow()
  })
})

// ── Table header detection for Kerf column ────────────────────────────────────

describe('CompareMd — table Kerf column detection', () => {
  const meta = {
    slug: 'rhino',
    competitor: 'Rhino',
    left: 'kerf',
    right: 'rhino',
    title: 'Kerf vs Rhino',
    body: `# Kerf vs Rhino

| Feature | Rhino | Kerf |
|---|---|---|
| NURBS | ✅ Class-leading | ⚠️ Phase 4 early |
`,
  }

  it('renders table header cells', () => {
    const html = render(<CompareMd meta={meta} />)
    expect(html).toContain('Feature')
    expect(html).toContain('Rhino')
    expect(html).toContain('Kerf')
  })

  it('Kerf table header has data-testid="left-vendor"', () => {
    const html = render(<CompareMd meta={meta} />)
    // The TH for Kerf should have the left-vendor testid
    expect(html).toMatch(/data-testid="left-vendor"[^>]*>(?:[^<]|<(?!\/th))*Kerf/)
  })
})

// ── Responsive: table and code-block overflow handling ────────────────────────

describe('CompareMd — responsive overflow handling', () => {
  const tableMeta = {
    slug: 'kicad',
    competitor: 'KiCad',
    left: 'kerf',
    right: 'kicad',
    title: 'Kerf vs KiCad',
    body: `# Kerf vs KiCad

| Feature | KiCad | Kerf |
|---|---|---|
| License | ✅ GPL v3 | ✅ MIT |
| Chat editing | ❌ None | ✅ Yes |
`,
  }

  it('wraps markdown tables in a horizontal-scroll container', () => {
    const html = render(<CompareMd meta={tableMeta} />)
    // The Table component wraps with overflow-x-auto
    expect(html).toContain('data-testid="table-scroll-container"')
  })

  it('table scroll container has overflow-x-auto class', () => {
    const html = render(<CompareMd meta={tableMeta} />)
    // The wrapper div should carry overflow-x-auto so wide tables scroll
    // inside the content column rather than widening the page on mobile.
    const scrollContainerMatch = html.match(/data-testid="table-scroll-container"[^>]*>|class="([^"]*)"[^>]*data-testid="table-scroll-container"/)
    expect(scrollContainerMatch).not.toBeNull()
    expect(html).toContain('overflow-x-auto')
  })

  it('table has min-w so it scrolls rather than collapses', () => {
    const html = render(<CompareMd meta={tableMeta} />)
    // Ensures the table width is enforced so the scroll container is meaningful
    expect(html).toContain('min-w-[640px]')
  })

  const codeMeta = {
    slug: 'openscad',
    competitor: 'OpenSCAD',
    left: 'kerf',
    right: 'openscad',
    title: 'Kerf vs OpenSCAD',
    body: `# Kerf vs OpenSCAD

\`\`\`python
cube([10, 20, 30])
sphere(r=5)
\`\`\`
`,
  }

  it('wraps fenced code blocks in a pre with overflow-x-auto', () => {
    const html = render(<CompareMd meta={codeMeta} />)
    // The Pre component must render with overflow-x-auto so wide code
    // samples scroll inside the content column on mobile.
    expect(html).toContain('data-testid="pre-scroll-container"')
  })

  it('pre scroll container has overflow-x-auto class', () => {
    const html = render(<CompareMd meta={codeMeta} />)
    expect(html).toContain('overflow-x-auto')
    expect(html).toContain('data-testid="pre-scroll-container"')
  })

  it('renders code inside the pre scroll container', () => {
    const html = render(<CompareMd meta={codeMeta} />)
    expect(html).toContain('cube')
    expect(html).toContain('sphere')
  })

  it('renders both table and code responsive wrappers together', () => {
    const combinedMeta = {
      ...tableMeta,
      body: tableMeta.body + '\n' + codeMeta.body.replace(/# [^\n]+\n\n/, ''),
    }
    const html = render(<CompareMd meta={combinedMeta} />)
    expect(html).toContain('data-testid="table-scroll-container"')
    expect(html).toContain('data-testid="pre-scroll-container"')
  })
})
