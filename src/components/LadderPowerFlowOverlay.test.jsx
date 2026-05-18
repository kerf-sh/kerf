/**
 * LadderPowerFlowOverlay.test.jsx — vitest tests for the SVG power-flow overlay.
 *
 * Uses react-dom/server renderToStaticMarkup (already a project dep) so no
 * JSDOM / testing-library install is required.
 *
 * Covers:
 *   1. Renders without crashing on null / empty inputs
 *   2. Root <g> element and data attribute
 *   3. Contact overlay elements are rendered per lit/unlit state
 *   4. Coil overlay elements are rendered per lit/unlit state
 *   5. Wire segment rendering when elements have positional data
 *   6. Opacity and strokeWidth props are forwarded
 *   7. Unknown element types are silently skipped
 */

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import LadderPowerFlowOverlay from './LadderPowerFlowOverlay.jsx'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Minimal positioned NO contact element. */
function noContact(id, variable, extras = {}) {
  return { id, type: 'NO', variable, x: 10, y: 10, width: 40, height: 40, ...extras }
}

/** Minimal positioned COIL element. */
function coil(id, variable, extras = {}) {
  return { id, type: 'COIL', variable, x: 80, y: 10, width: 40, height: 40, ...extras }
}

// ---------------------------------------------------------------------------
// 1. Null / empty inputs — must not throw
// ---------------------------------------------------------------------------

describe('LadderPowerFlowOverlay — null / empty inputs', () => {
  it('renders without crashing when rung is null', () => {
    expect(() => {
      renderToStaticMarkup(
        <LadderPowerFlowOverlay rung={null} powerFlow={null} />,
      )
    }).not.toThrow()
  })

  it('renders without crashing when rung is undefined', () => {
    expect(() => {
      renderToStaticMarkup(<LadderPowerFlowOverlay />)
    }).not.toThrow()
  })

  it('renders without crashing when rung is empty array', () => {
    expect(() => {
      renderToStaticMarkup(<LadderPowerFlowOverlay rung={[]} powerFlow={{}} />)
    }).not.toThrow()
  })

  it('renders without crashing when powerFlow is null', () => {
    const rung = [noContact('c1', 'x')]
    expect(() => {
      renderToStaticMarkup(<LadderPowerFlowOverlay rung={rung} powerFlow={null} />)
    }).not.toThrow()
  })

  it('renders without crashing when powerFlow is empty object', () => {
    const rung = [noContact('c1', 'x'), coil('q1', 'out')]
    expect(() => {
      renderToStaticMarkup(<LadderPowerFlowOverlay rung={rung} powerFlow={{}} />)
    }).not.toThrow()
  })

  it('renders without crashing when powerFlow sets are empty', () => {
    const rung = [noContact('c1', 'x'), coil('q1', 'out')]
    const powerFlow = {
      contactsLit: new Set(),
      coilsLit: new Set(),
      wiresLit: new Set(),
    }
    expect(() => {
      renderToStaticMarkup(<LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} />)
    }).not.toThrow()
  })
})

// ---------------------------------------------------------------------------
// 2. Root element structure
// ---------------------------------------------------------------------------

describe('LadderPowerFlowOverlay — root element', () => {
  it('renders a <g> root element (not a full <svg>)', () => {
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={[]} powerFlow={{}} />,
    )
    expect(html).toMatch(/^<g\b/)
  })

  it('root <g> carries data-component="LadderPowerFlowOverlay"', () => {
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={[]} powerFlow={{}} />,
    )
    expect(html).toContain('data-component="LadderPowerFlowOverlay"')
  })

  it('root <g> has pointer-events:none style', () => {
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={[]} powerFlow={{}} />,
    )
    expect(html).toContain('pointer-events')
    expect(html).toContain('none')
  })
})

// ---------------------------------------------------------------------------
// 3. Contact overlays
// ---------------------------------------------------------------------------

describe('LadderPowerFlowOverlay — contact overlays', () => {
  it('renders a rect for each contact element', () => {
    const rung = [noContact('c1', 'x'), noContact('c2', 'y')]
    const powerFlow = { contactsLit: new Set(['c1']), coilsLit: new Set(), wiresLit: new Set() }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} />,
    )
    expect(html).toContain('data-overlay-id="c1"')
    expect(html).toContain('data-overlay-id="c2"')
    expect(html).toContain('data-overlay-type="contact"')
  })

  it('lit contact uses green stroke (#34d399)', () => {
    const rung = [noContact('c1', 'x')]
    const powerFlow = { contactsLit: new Set(['c1']), coilsLit: new Set(), wiresLit: new Set() }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} />,
    )
    expect(html).toContain('#34d399')
  })

  it('unlit contact uses dim grey stroke (#6b7280)', () => {
    const rung = [noContact('c1', 'x')]
    const powerFlow = { contactsLit: new Set(), coilsLit: new Set(), wiresLit: new Set() }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} />,
    )
    expect(html).toContain('#6b7280')
  })

  it('accepts powerFlow.contactsLit as a plain Array', () => {
    const rung = [noContact('c1', 'x')]
    const powerFlow = { contactsLit: ['c1'], coilsLit: [], wiresLit: [] }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} />,
    )
    // Should render a green (lit) stroke for c1
    expect(html).toContain('#34d399')
  })
})

// ---------------------------------------------------------------------------
// 4. Coil overlays
// ---------------------------------------------------------------------------

describe('LadderPowerFlowOverlay — coil overlays', () => {
  it('renders a circle for each coil element', () => {
    const rung = [coil('q1', 'out')]
    const powerFlow = { contactsLit: new Set(), coilsLit: new Set(['q1']), wiresLit: new Set() }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} />,
    )
    expect(html).toContain('data-overlay-id="q1"')
    expect(html).toContain('data-overlay-type="coil"')
    expect(html).toMatch(/<circle\b/)
  })

  it('lit coil uses green fill / stroke', () => {
    const rung = [coil('q1', 'out')]
    const powerFlow = { contactsLit: new Set(), coilsLit: new Set(['q1']), wiresLit: new Set() }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} />,
    )
    expect(html).toContain('#34d399')
  })

  it('unlit coil uses red stroke (#f87171) — broken wire indicator', () => {
    const rung = [coil('q1', 'out')]
    const powerFlow = { contactsLit: new Set(), coilsLit: new Set(), wiresLit: new Set() }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} />,
    )
    expect(html).toContain('#f87171')
  })
})

// ---------------------------------------------------------------------------
// 5. Wire segments
// ---------------------------------------------------------------------------

describe('LadderPowerFlowOverlay — wire segments', () => {
  it('renders a line segment between two positioned elements', () => {
    const c = { id: 'c1', type: 'NO', variable: 'x', x: 0, y: 20, width: 40, height: 20 }
    const q = { id: 'q1', type: 'COIL', variable: 'out', x: 60, y: 20, width: 40, height: 20 }
    const powerFlow = {
      contactsLit: new Set(['c1']),
      coilsLit: new Set(['q1']),
      wiresLit: new Set(['wire_after_c1']),
    }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={[c, q]} powerFlow={powerFlow} />,
    )
    expect(html).toMatch(/<line\b/)
    expect(html).toContain('data-overlay-wire="wire_c1_to_q1"')
  })

  it('energised wire uses green colour', () => {
    const c = { id: 'c1', type: 'NO', variable: 'x', x: 0, y: 20, width: 40, height: 20 }
    const q = { id: 'q1', type: 'COIL', variable: 'out', x: 60, y: 20, width: 40, height: 20 }
    const powerFlow = {
      contactsLit: new Set(['c1']),
      coilsLit: new Set(['q1']),
      wiresLit: new Set(['wire_after_c1']),
    }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={[c, q]} powerFlow={powerFlow} />,
    )
    expect(html).toContain('#34d399')
  })

  it('de-energised wire uses red colour', () => {
    const c = { id: 'c1', type: 'NO', variable: 'x', x: 0, y: 20, width: 40, height: 20 }
    const q = { id: 'q1', type: 'COIL', variable: 'out', x: 60, y: 20, width: 40, height: 20 }
    const powerFlow = {
      contactsLit: new Set(),      // c1 NOT lit
      coilsLit: new Set(),
      wiresLit: new Set(),
    }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={[c, q]} powerFlow={powerFlow} />,
    )
    expect(html).toContain('#f87171')
  })

  it('no wire segments rendered when elements have no positional data', () => {
    const c = { id: 'c1', type: 'NO', variable: 'x' }
    const q = { id: 'q1', type: 'COIL', variable: 'out' }
    const powerFlow = { contactsLit: new Set(['c1']), coilsLit: new Set(['q1']), wiresLit: new Set() }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={[c, q]} powerFlow={powerFlow} />,
    )
    // No line element should appear
    expect(html).not.toMatch(/<line\b/)
  })
})

// ---------------------------------------------------------------------------
// 6. Props — opacity and strokeWidth
// ---------------------------------------------------------------------------

describe('LadderPowerFlowOverlay — opacity and strokeWidth props', () => {
  it('forwards opacity to root <g>', () => {
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={[]} powerFlow={{}} opacity={0.5} />,
    )
    expect(html).toContain('opacity="0.5"')
  })

  it('defaults opacity to 0.85', () => {
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={[]} powerFlow={{}} />,
    )
    expect(html).toContain('opacity="0.85"')
  })

  it('uses strokeWidth for contact rect stroke-width', () => {
    const rung = [noContact('c1', 'x')]
    const powerFlow = { contactsLit: new Set(), coilsLit: new Set(), wiresLit: new Set() }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} strokeWidth={5} />,
    )
    expect(html).toContain('stroke-width="5"')
  })
})

// ---------------------------------------------------------------------------
// 7. Unknown / unsupported element types are skipped
// ---------------------------------------------------------------------------

describe('LadderPowerFlowOverlay — unknown element types', () => {
  it('silently skips elements with unknown type', () => {
    const rung = [
      { id: 'u1', type: 'UNKNOWN_BLOCK', variable: 'foo', x: 0, y: 0, width: 40, height: 40 },
    ]
    const powerFlow = { contactsLit: new Set(), coilsLit: new Set(), wiresLit: new Set() }
    expect(() => {
      renderToStaticMarkup(
        <LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} />,
      )
    }).not.toThrow()
  })

  it('silently skips elements with missing id', () => {
    const rung = [
      { type: 'NO', variable: 'x', x: 0, y: 0, width: 40, height: 40 },
    ]
    const powerFlow = { contactsLit: new Set(), coilsLit: new Set(), wiresLit: new Set() }
    expect(() => {
      renderToStaticMarkup(
        <LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} />,
      )
    }).not.toThrow()
  })
})

// ---------------------------------------------------------------------------
// 8. Parallel (nested) rung elements are flattened
// ---------------------------------------------------------------------------

describe('LadderPowerFlowOverlay — parallel branch rendering', () => {
  it('renders overlay for contacts inside parallel branch arrays', () => {
    const rung = [
      [
        [noContact('c1', 'a')],
        [noContact('c2', 'b')],
      ],
      coil('q1', 'out'),
    ]
    const powerFlow = {
      contactsLit: new Set(['c1']),
      coilsLit: new Set(['q1']),
      wiresLit: new Set(),
    }
    const html = renderToStaticMarkup(
      <LadderPowerFlowOverlay rung={rung} powerFlow={powerFlow} />,
    )
    expect(html).toContain('data-overlay-id="c1"')
    expect(html).toContain('data-overlay-id="c2"')
    expect(html).toContain('data-overlay-id="q1"')
  })
})
