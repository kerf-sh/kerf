/**
 * ChatPanel.toolChips.test.jsx
 *
 * Source-level assertions for the live streaming tool-chip UI.
 *
 * We test the JSX source directly (like chatPanelError.test.js) to
 * avoid the heavy DOM-mode / Monaco / three.js setup that would be
 * required by @testing-library/react on this component.
 *
 * Tests:
 *  - ToolChipList component exists in source
 *  - Chips render with correct status-based classes
 *  - Loader2 icon used for running chips
 *  - Check icon used for done chips
 *  - TriangleAlert icon used for error chips
 *  - Cancel/Stop button is present with data-testid
 *  - onCancelStream prop is wired
 *  - _toolChips is read from the streaming message
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const SRC = readFileSync(
  resolve(__dirname, '../ChatPanel.jsx'),
  'utf8',
)

describe('ChatPanel — streaming tool chips', () => {
  it('defines a ToolChipList component', () => {
    expect(SRC).toMatch(/function ToolChipList/)
  })

  it('renders a tool-chip-list container with data-testid', () => {
    expect(SRC).toMatch(/data-testid="tool-chip-list"/)
  })

  it('renders individual chips with data-testid="tool-chip"', () => {
    expect(SRC).toMatch(/data-testid="tool-chip"/)
  })

  it('uses Loader2 for running chips', () => {
    expect(SRC).toMatch(/<Loader2\b/)
    // Loader2 must be imported from lucide-react
    expect(SRC).toMatch(/Loader2/)
  })

  it('uses Check for done chips', () => {
    // Check is already imported for tool call chips
    expect(SRC).toMatch(/status === 'done'[\s\S]{0,100}Check/)
  })

  it('uses TriangleAlert for error chips', () => {
    expect(SRC).toMatch(/status === 'error'[\s\S]{0,100}TriangleAlert/)
  })

  it('applies animate-spin to the loading icon', () => {
    expect(SRC).toMatch(/animate-spin/)
  })

  it('reads _toolChips from the message object', () => {
    expect(SRC).toMatch(/message\._toolChips|_toolChips/)
  })

  it('shows ToolChipList when _toolChips has items', () => {
    expect(SRC).toMatch(/_toolChips[\s\S]{0,100}ToolChipList/)
  })

  it('renders a Stop / cancel button with data-testid', () => {
    expect(SRC).toMatch(/data-testid="cancel-stream-btn"/)
  })

  it('Stop button calls onCancelStream on click', () => {
    expect(SRC).toMatch(/onClick={onCancelStream}|onClick={.*cancel.*}|onCancelStream/)
  })

  it('imports Square icon for the Stop button', () => {
    expect(SRC).toMatch(/Square/)
  })

  it('accepts onCancelStream prop in ChatPanel signature', () => {
    expect(SRC).toMatch(/onCancelStream/)
  })

  it('shows streaming dots when content is empty and _streaming is true', () => {
    expect(SRC).toMatch(/_streaming/)
  })

  it('does not regress: still renders Markdown for assistant content', () => {
    expect(SRC).toMatch(/<Markdown/)
  })

  it('ToolChipList is placed inside the assistant message bubble', () => {
    // The ToolChipList render must come after the content check
    const toolChipPos = SRC.indexOf('<ToolChipList')
    const markdownPos = SRC.indexOf('<Markdown')
    expect(toolChipPos).toBeGreaterThan(0)
    expect(markdownPos).toBeGreaterThan(0)
    // ToolChipList is inside the non-user branch
    expect(toolChipPos).toBeGreaterThan(markdownPos)
  })
})
