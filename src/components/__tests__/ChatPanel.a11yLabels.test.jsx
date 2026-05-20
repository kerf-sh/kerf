/**
 * ChatPanel.a11yLabels.test.jsx
 *
 * Source-level assertions for T-B1 "Label the chat input + model options".
 *
 * Verifies:
 *  - The chat textarea carries aria-label="Chat message"
 *  - The model-picker listbox carries role="listbox" + aria-label
 *  - The trigger button carries aria-haspopup="listbox" + aria-expanded
 *  - Each model option uses role="option" + aria-selected
 *  - aria-activedescendant is set on the listbox pointing at the active option
 *  - Option ids are derived from the model id (stable, sanitised)
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const SRC = readFileSync(
  resolve(__dirname, '../ChatPanel.jsx'),
  'utf8',
)

describe('ChatPanel — T-B1 label chat input + model options', () => {
  it('textarea carries aria-label="Chat message"', () => {
    expect(SRC).toMatch(/aria-label="Chat message"/)
  })

  it('model listbox element has role="listbox"', () => {
    // The open popover div should declare role="listbox"
    expect(SRC).toMatch(/role="listbox"/)
  })

  it('model listbox has aria-label', () => {
    expect(SRC).toMatch(/aria-label="Select model"/)
  })

  it('model listbox carries aria-activedescendant linked to the active option id', () => {
    expect(SRC).toMatch(/aria-activedescendant=\{activeOptionId\}/)
  })

  it('each model option uses role="option"', () => {
    expect(SRC).toMatch(/role="option"/)
  })

  it('each model option carries aria-selected', () => {
    expect(SRC).toMatch(/aria-selected=\{active\}/)
  })

  it('option id is derived from the sanitised model id', () => {
    // e.g. `model-option-${m.id.replace(...)}`
    expect(SRC).toMatch(/model-option-\$\{m\.id\.replace/)
  })

  it('trigger button has aria-haspopup="listbox"', () => {
    expect(SRC).toMatch(/aria-haspopup="listbox"/)
  })

  it('trigger button has aria-expanded reflecting open state', () => {
    expect(SRC).toMatch(/aria-expanded=\{open\}/)
  })

  it('trigger button aria-label includes the current model name', () => {
    // aria-label={`Model: ${current?.label || 'pick model'}`}
    expect(SRC).toMatch(/aria-label=\{`Model: \$\{current\?\.label/)
  })
})
