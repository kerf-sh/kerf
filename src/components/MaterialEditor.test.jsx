// MaterialEditor.test.jsx — Vitest tests for MaterialEditor + MaterialPbrEditor wiring.
//
// Uses react-dom/server renderToStaticMarkup — no @testing-library/react needed.
// MaterialPbrEditor is mocked to a lightweight stub so this test suite stays
// focused on the integration wiring, not PBR internals (which have their own
// test file: MaterialPbrEditor.test.jsx).

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

// ---------------------------------------------------------------------------
// Mocks — hoisted before component import
// ---------------------------------------------------------------------------

vi.mock('./MaterialPbrEditor.jsx', () => ({
  default: ({ material, onClose, className }) => (
    <div
      data-testid="material-pbr-editor-stub"
      data-mat-name={material?.name ?? ''}
      data-has-close={typeof onClose === 'function' ? 'true' : 'false'}
      className={className ?? ''}
    />
  ),
}))

vi.mock('../store/workspace.js', () => ({
  useWorkspace: (sel) => sel({
    currentFile: { name: 'steel.material' },
    currentFileContent: JSON.stringify({
      version: 1,
      name: 'AISI 1018 Steel',
      category: 'metal/steel/carbon',
      callout: 'AISI 1018',
      mechanical: { E_GPa: 200, nu: 0.29 },
      thermal: {},
      physical: { rho_kg_m3: 7870 },
    }),
    editContent: vi.fn(),
  }),
}))

import MaterialEditor from './MaterialEditor.jsx'

// ---------------------------------------------------------------------------
// Smoke tests
// ---------------------------------------------------------------------------

describe('MaterialEditor renders without crashing', () => {
  it('renders the editor root', () => {
    const html = renderToStaticMarkup(<MaterialEditor />)
    expect(typeof html).toBe('string')
    expect(html.length).toBeGreaterThan(0)
  })

  it('shows the material name from the workspace content', () => {
    const html = renderToStaticMarkup(<MaterialEditor />)
    expect(html).toContain('AISI 1018 Steel')
  })

  it('renders the PBR toggle button (collapsed by default)', () => {
    const html = renderToStaticMarkup(<MaterialEditor />)
    expect(html).toMatch(/data-testid="pbr-panel-toggle"/)
    expect(html).toContain('PBR Material Properties')
  })

  it('does NOT render the PBR sub-panel when collapsed (default)', () => {
    const html = renderToStaticMarkup(<MaterialEditor />)
    // The stub is only rendered when pbrOpen === true — initial state is false
    expect(html).not.toContain('material-pbr-editor-stub')
  })
})

// ---------------------------------------------------------------------------
// Toggle aria state
// ---------------------------------------------------------------------------

describe('MaterialEditor PBR toggle aria', () => {
  it('renders aria-expanded="false" when collapsed', () => {
    const html = renderToStaticMarkup(<MaterialEditor />)
    expect(html).toMatch(/aria-expanded="false"/)
  })
})

// ---------------------------------------------------------------------------
// Section headings present
// ---------------------------------------------------------------------------

describe('MaterialEditor section structure', () => {
  it('renders Mechanical section', () => {
    const html = renderToStaticMarkup(<MaterialEditor />)
    expect(html).toContain('Mechanical')
  })

  it('renders Thermal section', () => {
    const html = renderToStaticMarkup(<MaterialEditor />)
    expect(html).toContain('Thermal')
  })

  it('renders Physical section', () => {
    const html = renderToStaticMarkup(<MaterialEditor />)
    expect(html).toContain('Physical')
  })

  it('renders Notes section', () => {
    const html = renderToStaticMarkup(<MaterialEditor />)
    expect(html).toContain('Notes')
  })
})
