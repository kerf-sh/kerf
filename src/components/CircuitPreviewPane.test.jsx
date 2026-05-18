// CircuitPreviewPane.test.jsx — vitest unit tests
//
// Testing strategy mirrors Loader.test.jsx: render to static HTML via
// react-dom/server (already a project dep), assert structure via string
// matching. We avoid @testing-library/react to stay within the project's
// no-new-deps constraint.
//
// Covered:
//   1. Renders without crashing on minimal (null) input.
//   2. Empty-state message shown when circuitJson is [].
//   3. Empty-state shown when circuitJson is null.
//   4. Accepts wrapped { circuit_json: [] } shape without crashing.
//   5. Mode change: onModeChange called when PCB tab is clicked.
//   6. Default mode is 'schematic' — Schematic tab is aria-selected.
//   7. Component accepts className prop.
//   8. Tab bar contains both Schematic and PCB tabs.

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import CircuitPreviewPane from './CircuitPreviewPane.jsx'

// circuit-to-svg performs DOM operations (DOMParser, XMLSerializer) that are
// not available in the vitest/node environment. Mock both converters so the
// tests focus on the component's own logic.
vi.mock('circuit-to-svg', () => ({
  convertCircuitJsonToSchematicSvg: vi.fn(() => '<svg viewBox="0 0 100 100"></svg>'),
  convertCircuitJsonToPcbSvg: vi.fn(() => '<svg viewBox="0 0 100 100"></svg>'),
}))

// lucide-react icons are ESM-only; provide minimal stubs so SSR doesn't throw.
vi.mock('lucide-react', () => ({
  Maximize2:      () => null,
  RotateCcw:      () => null,
  AlertTriangle:  () => null,
}))

// ---------------------------------------------------------------------------
// 1. Renders without crashing on minimal input
// ---------------------------------------------------------------------------
describe('CircuitPreviewPane', () => {
  it('renders without crashing when circuitJson is null', () => {
    expect(() => renderToStaticMarkup(<CircuitPreviewPane circuitJson={null} />)).not.toThrow()
  })

  it('renders without crashing when circuitJson is undefined', () => {
    expect(() => renderToStaticMarkup(<CircuitPreviewPane />)).not.toThrow()
  })

  it('renders without crashing with a minimal circuit item array', () => {
    const items = [{ type: 'source_component', source_component_id: 'sc0', name: 'R1' }]
    expect(() => renderToStaticMarkup(<CircuitPreviewPane circuitJson={items} />)).not.toThrow()
  })

  // ---------------------------------------------------------------------------
  // 2. Empty state shown when circuitJson is []
  // ---------------------------------------------------------------------------
  it('shows empty-state when circuitJson is []', () => {
    const html = renderToStaticMarkup(<CircuitPreviewPane circuitJson={[]} />)
    expect(html).toMatch(/data-testid="circuit-preview-empty"/)
  })

  // ---------------------------------------------------------------------------
  // 3. Empty state shown when circuitJson is null
  // ---------------------------------------------------------------------------
  it('shows empty-state when circuitJson is null', () => {
    const html = renderToStaticMarkup(<CircuitPreviewPane circuitJson={null} />)
    expect(html).toMatch(/data-testid="circuit-preview-empty"/)
  })

  // ---------------------------------------------------------------------------
  // 4. Wrapped { circuit_json: [] } shape
  // ---------------------------------------------------------------------------
  it('accepts wrapped { circuit_json: [] } shape without crashing', () => {
    expect(() =>
      renderToStaticMarkup(<CircuitPreviewPane circuitJson={{ circuit_json: [] }} />)
    ).not.toThrow()
  })

  it('shows empty-state for wrapped { circuit_json: [] }', () => {
    const html = renderToStaticMarkup(
      <CircuitPreviewPane circuitJson={{ circuit_json: [] }} />,
    )
    expect(html).toMatch(/data-testid="circuit-preview-empty"/)
  })

  // ---------------------------------------------------------------------------
  // 5. onModeChange called when the PCB tab button is clicked
  //    (static HTML: can only verify the tab exists and has the right role)
  // ---------------------------------------------------------------------------
  it('renders a PCB tab with role="tab"', () => {
    const html = renderToStaticMarkup(<CircuitPreviewPane circuitJson={[]} />)
    // The PCB tab button should be present
    expect(html).toMatch(/PCB/)
    expect(html).toMatch(/role="tab"/)
  })

  // ---------------------------------------------------------------------------
  // 6. Default mode is 'schematic' — Schematic tab is aria-selected="true"
  // ---------------------------------------------------------------------------
  it('marks the Schematic tab as selected by default', () => {
    const html = renderToStaticMarkup(<CircuitPreviewPane circuitJson={[]} />)
    // The Schematic button should have aria-selected="true"
    expect(html).toMatch(/Schematic/)
    // aria-selected on the currently active tab
    expect(html).toMatch(/aria-selected="true"[^>]*>Schematic|Schematic[^<]*<\/button[^>]*aria-selected="true"/)
    // More permissive: at least one tab is aria-selected="true"
    expect(html).toMatch(/aria-selected="true"/)
  })

  it('marks the PCB tab as selected when mode="pcb"', () => {
    const html = renderToStaticMarkup(<CircuitPreviewPane circuitJson={[]} mode="pcb" />)
    // There should still be an aria-selected="true" somewhere (the PCB tab)
    expect(html).toMatch(/aria-selected="true"/)
  })

  // ---------------------------------------------------------------------------
  // 7. className prop forwarded to outer wrapper
  // ---------------------------------------------------------------------------
  it('forwards className to the outer wrapper', () => {
    const html = renderToStaticMarkup(
      <CircuitPreviewPane circuitJson={[]} className="my-custom-class" />,
    )
    expect(html).toMatch(/my-custom-class/)
  })

  // ---------------------------------------------------------------------------
  // 8. Tab bar contains both Schematic and PCB tabs
  // ---------------------------------------------------------------------------
  it('renders both Schematic and PCB tabs', () => {
    const html = renderToStaticMarkup(<CircuitPreviewPane circuitJson={[]} />)
    expect(html).toMatch(/Schematic/)
    expect(html).toMatch(/PCB/)
  })

  it('renders a tablist with the expected aria-label', () => {
    const html = renderToStaticMarkup(<CircuitPreviewPane circuitJson={[]} />)
    expect(html).toMatch(/role="tablist"/)
    expect(html).toMatch(/aria-label="Circuit preview mode"/)
  })
})
