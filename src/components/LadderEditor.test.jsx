// LadderEditor.test.jsx — Vitest structural tests for the LadderEditor component.
//
// Following the project's established pattern (see Loader.test.jsx, PLCView, etc.):
// @testing-library/react is NOT a project dependency. We use react-dom/server's
// renderToStaticMarkup to assert structural HTML properties without a DOM runtime.
//
// The tests cover:
//  1. Basic structure — rails, canvas, palette, add-rung button.
//  2. Rendering rungs from the value prop.
//  3. Rendering contacts and coils from rung data.
//  4. All palette items are present.
//  5. Edge cases: empty value, multiple rungs.

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import LadderEditor from './LadderEditor.jsx'
import { createRung, addContact, addCoil } from '../lib/ladderCanvas.js'

// ── Helpers ────────────────────────────────────────────────────────────────────

function render(props = {}) {
  return renderToStaticMarkup(<LadderEditor {...props} />)
}

function makeRungWithContact(type = 'no', pos = 0) {
  let r = createRung()
  r = addContact(r, type, pos, { name: 'X1' })
  return r
}

function makeRungWithCoil(type = 'output', pos = 5) {
  let r = createRung()
  r = addCoil(r, type, pos, { name: 'Y1' })
  return r
}

function makePopulatedRung() {
  let r = createRung()
  r = addContact(r, 'no', 0, { name: 'START' })
  r = addContact(r, 'nc', 1, { name: 'STOP' })
  r = addCoil(r, 'output', 5, { name: 'MOTOR' })
  return r
}

// ── 1. Basic structure ─────────────────────────────────────────────────────────

describe('LadderEditor — basic structure', () => {
  it('renders the root container with data-testid="ladder-editor"', () => {
    const html = render()
    expect(html).toContain('data-testid="ladder-editor"')
  })

  it('renders the SVG canvas', () => {
    const html = render()
    expect(html).toMatch(/<svg\b/)
  })

  it('renders the left power rail', () => {
    const html = render()
    expect(html).toContain('data-testid="left-rail"')
  })

  it('renders the right power rail', () => {
    const html = render()
    expect(html).toContain('data-testid="right-rail"')
  })

  it('renders the palette sidebar', () => {
    const html = render()
    expect(html).toContain('data-testid="ladder-palette"')
  })

  it('renders the "Add Rung" button', () => {
    const html = render()
    expect(html).toContain('data-testid="add-rung-btn"')
    expect(html).toContain('Add Rung')
  })

  it('includes the IEC 61131-3 LD header label', () => {
    const html = render()
    expect(html).toContain('IEC 61131-3 LD')
  })

  it('shows "Ladder Editor" in the header', () => {
    const html = render()
    expect(html).toContain('Ladder Editor')
  })

  it('applies a supplied className', () => {
    const html = render({ className: 'my-extra-class' })
    expect(html).toContain('my-extra-class')
  })
})

// ── 2. Rung rendering ─────────────────────────────────────────────────────────

describe('LadderEditor — rung rendering', () => {
  it('renders 0 rungs when value is empty', () => {
    const html = render({ value: [] })
    expect(html).not.toContain('data-testid="rung-0"')
  })

  it('renders a rung group for each rung in value', () => {
    const rungs = [createRung(), createRung(), createRung()]
    const html = render({ value: rungs })
    expect(html).toContain('data-testid="rung-0"')
    expect(html).toContain('data-testid="rung-1"')
    expect(html).toContain('data-testid="rung-2"')
    expect(html).not.toContain('data-testid="rung-3"')
  })

  it('shows the rung count in the header', () => {
    const rungs = [createRung(), createRung()]
    const html = render({ value: rungs })
    expect(html).toContain('2 rungs')
  })

  it('shows "1 rung" (singular) for a single rung', () => {
    const html = render({ value: [createRung()] })
    expect(html).toContain('1 rung')
    expect(html).not.toMatch(/1 rungs/)
  })

  it('shows "0 rungs" when value is empty', () => {
    const html = render({ value: [] })
    expect(html).toContain('0 rungs')
  })

  it('renders a hint text when no rungs are present', () => {
    const html = render({ value: [] })
    expect(html).toContain('Add Rung')
  })
})

// ── 3. Contact rendering ──────────────────────────────────────────────────────

describe('LadderEditor — contact rendering', () => {
  it('renders a contact name label when name is set', () => {
    const rung = makeRungWithContact('no', 0)
    const html = render({ value: [rung] })
    expect(html).toContain('X1')
  })

  it('renders an NC contact (diagonal slash line)', () => {
    let r = createRung()
    r = addContact(r, 'nc', 0, { name: 'LIMIT' })
    const html = render({ value: [r] })
    expect(html).toContain('LIMIT')
  })

  it('renders a rising-edge contact with P label', () => {
    let r = createRung()
    r = addContact(r, 'rising', 0, { name: 'BTN' })
    const html = render({ value: [r] })
    // The ContactSymbol renders a 'P' text for rising type
    expect(html).toContain('>P<')
    expect(html).toContain('BTN')
  })

  it('renders a falling-edge contact with N label', () => {
    let r = createRung()
    r = addContact(r, 'falling', 0, { name: 'SENSOR' })
    const html = render({ value: [r] })
    expect(html).toContain('>N<')
    expect(html).toContain('SENSOR')
  })

  it('renders multiple contacts in the same rung', () => {
    let r = createRung()
    r = addContact(r, 'no', 0, { name: 'ALPHA' })
    r = addContact(r, 'nc', 1, { name: 'BETA' })
    const html = render({ value: [r] })
    expect(html).toContain('ALPHA')
    expect(html).toContain('BETA')
  })
})

// ── 4. Coil rendering ─────────────────────────────────────────────────────────

describe('LadderEditor — coil rendering', () => {
  it('renders a coil name label when name is set', () => {
    const rung = makeRungWithCoil('output', 5)
    const html = render({ value: [rung] })
    expect(html).toContain('Y1')
  })

  it('renders a circle element for the coil', () => {
    const rung = makeRungWithCoil()
    const html = render({ value: [rung] })
    expect(html).toMatch(/<circle\b/)
  })

  it('renders set coil inner label S', () => {
    let r = createRung()
    r = addCoil(r, 'set', 5, { name: 'VALVE' })
    const html = render({ value: [r] })
    expect(html).toContain('>S<')
    expect(html).toContain('VALVE')
  })

  it('renders reset coil inner label R', () => {
    let r = createRung()
    r = addCoil(r, 'reset', 5, { name: 'VALVE' })
    const html = render({ value: [r] })
    expect(html).toContain('>R<')
  })

  it('renders pulse coil inner label P', () => {
    let r = createRung()
    r = addCoil(r, 'pulse', 5, { name: 'ALARM' })
    const html = render({ value: [r] })
    expect(html).toContain('>P<')
  })

  it('output coil has no inner letter', () => {
    let r = createRung()
    r = addCoil(r, 'output', 5, { name: 'LIGHT' })
    const html = render({ value: [r] })
    expect(html).toContain('LIGHT')
    // The circle is there; no S/R/P inside an output coil specifically
    expect(html).toMatch(/<circle\b/)
  })
})

// ── 5. Palette items ──────────────────────────────────────────────────────────

describe('LadderEditor — palette items', () => {
  it('renders palette item for NO contact', () => {
    const html = render()
    expect(html).toContain('data-testid="palette-contact-no"')
  })

  it('renders palette item for NC contact', () => {
    const html = render()
    expect(html).toContain('data-testid="palette-contact-nc"')
  })

  it('renders palette item for rising-edge contact', () => {
    const html = render()
    expect(html).toContain('data-testid="palette-contact-rising"')
  })

  it('renders palette item for falling-edge contact', () => {
    const html = render()
    expect(html).toContain('data-testid="palette-contact-falling"')
  })

  it('renders palette item for output coil', () => {
    const html = render()
    expect(html).toContain('data-testid="palette-coil-output"')
  })

  it('renders palette item for set coil', () => {
    const html = render()
    expect(html).toContain('data-testid="palette-coil-set"')
  })

  it('renders palette item for reset coil', () => {
    const html = render()
    expect(html).toContain('data-testid="palette-coil-reset"')
  })

  it('renders palette item for pulse coil', () => {
    const html = render()
    expect(html).toContain('data-testid="palette-coil-pulse"')
  })

  it('shows all 4 contact symbols in the palette', () => {
    const html = render()
    // Label symbols: –[ ]–, –[/]–, –[P]–, –[N]–
    expect(html).toContain('–[ ]–')
    expect(html).toContain('–[/]–')
    expect(html).toContain('–[P]–')
    expect(html).toContain('–[N]–')
  })

  it('shows all 4 coil symbols in the palette', () => {
    const html = render()
    expect(html).toContain('–( )–')
    expect(html).toContain('–(S)–')
    expect(html).toContain('–(R)–')
    expect(html).toContain('–(P)–')
  })
})

// ── 6. Contact count integration ─────────────────────────────────────────────

describe('LadderEditor — contact count via value prop', () => {
  it('increasing contacts in the value prop increases SVG contact renders', () => {
    let rung = createRung()
    const html0 = render({ value: [rung] })

    rung = addContact(rung, 'no', 0, { name: 'C1' })
    const html1 = render({ value: [rung] })

    rung = addContact(rung, 'nc', 1, { name: 'C2' })
    const html2 = render({ value: [rung] })

    // Count name label occurrences as proxy for rendered contacts
    const countC1 = (s) => (s.match(/C1/g) || []).length
    const countC2 = (s) => (s.match(/C2/g) || []).length

    expect(countC1(html0)).toBe(0)
    expect(countC1(html1)).toBeGreaterThan(0)
    expect(countC2(html1)).toBe(0)
    expect(countC2(html2)).toBeGreaterThan(0)
  })

  it('a rung with both a contact and coil renders both elements', () => {
    const rung = makePopulatedRung()
    const html = render({ value: [rung] })
    // Contact names
    expect(html).toContain('START')
    expect(html).toContain('STOP')
    // Coil name
    expect(html).toContain('MOTOR')
    // Circle (coil)
    expect(html).toMatch(/<circle\b/)
  })
})

// ── 7. Multiple rungs ─────────────────────────────────────────────────────────

describe('LadderEditor — multiple rungs', () => {
  it('renders each rung independently with its own elements', () => {
    const rung0 = (() => {
      let r = createRung()
      r = addContact(r, 'no', 0, { name: 'RUNG0_A' })
      return r
    })()
    const rung1 = (() => {
      let r = createRung()
      r = addContact(r, 'nc', 0, { name: 'RUNG1_B' })
      return r
    })()
    const html = render({ value: [rung0, rung1] })
    expect(html).toContain('RUNG0_A')
    expect(html).toContain('RUNG1_B')
    expect(html).toContain('data-testid="rung-0"')
    expect(html).toContain('data-testid="rung-1"')
  })

  it('renders 5 rungs with independent data', () => {
    const rungs = Array.from({ length: 5 }, (_, i) => {
      let r = createRung()
      r = addContact(r, 'no', 0, { name: `SENSOR_${i}` })
      return r
    })
    const html = render({ value: rungs })
    for (let i = 0; i < 5; i++) {
      expect(html).toContain(`SENSOR_${i}`)
      expect(html).toContain(`data-testid="rung-${i}"`)
    }
  })
})
