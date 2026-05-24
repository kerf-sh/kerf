// ChatPanel.test.jsx — Vitest tests for ChatPanel wiring:
//   - childrenToText utility
//   - isCircuitJson guard (via Markdown code component)
//   - Markdown component renders without crashing
//   - ```ato and ```json (circuit) fences render the correct preview components
//
// We use react-dom/server renderToStaticMarkup — no @testing-library/react needed.

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

// ---------------------------------------------------------------------------
// Mocks — hoisted before component imports
// ---------------------------------------------------------------------------

vi.mock('./Chat/AtopilePreview.jsx', () => ({
  default: ({ source }) => (
    <div data-testid="atopile-preview" data-source-len={source?.length ?? 0} />
  ),
}))

vi.mock('./Chat/CircuitJsonPreview.jsx', () => ({
  default: ({ circuitJson }) => (
    <div data-testid="circuit-json-preview" data-count={circuitJson?.length ?? 0} />
  ),
}))

vi.mock('../../lib/api.js', () => ({
  api: {
    listModels: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('../store/workspace.js', () => ({
  useWorkspace: (sel) => sel({
    projectId: null,
    setThreadModel: vi.fn(),
  }),
}))

vi.mock('../lib/usePrefersReducedMotion.js', () => ({
  default: () => false,
}))

import { childrenToText, Markdown } from './ChatPanel.jsx'

// ---------------------------------------------------------------------------
// childrenToText
// ---------------------------------------------------------------------------

describe('childrenToText', () => {
  it('returns empty string for null/undefined', () => {
    expect(childrenToText(null)).toBe('')
    expect(childrenToText(undefined)).toBe('')
    expect(childrenToText(false)).toBe('')
  })

  it('returns the string directly', () => {
    expect(childrenToText('hello')).toBe('hello')
  })

  it('converts numbers to string', () => {
    expect(childrenToText(42)).toBe('42')
  })

  it('joins arrays', () => {
    expect(childrenToText(['a', 'b', 'c'])).toBe('abc')
  })

  it('recurses into React-element props.children', () => {
    const node = { props: { children: 'nested' } }
    expect(childrenToText(node)).toBe('nested')
  })
})

// ---------------------------------------------------------------------------
// Markdown — basic rendering
// ---------------------------------------------------------------------------

describe('Markdown', () => {
  it('renders nothing for empty text', () => {
    const html = renderToStaticMarkup(<Markdown text="" />)
    expect(html).toBe('')
  })

  it('renders a paragraph for plain text', () => {
    const html = renderToStaticMarkup(<Markdown text="Hello world" />)
    expect(html).toContain('Hello world')
  })

  it('renders a normal code block for a generic fence', () => {
    const html = renderToStaticMarkup(
      <Markdown text={'```python\nprint("hi")\n```'} />,
    )
    // Should be a plain code block, not a special preview
    expect(html).not.toContain('atopile-preview')
    expect(html).not.toContain('circuit-json-preview')
    expect(html).toContain('print')
  })

  it('renders AtopilePreview for ```ato fences', () => {
    const atoSource = 'module Blinky:\n  signal gnd\n  led = new LED\n  led.~[1] ~ gnd'
    const md = `\`\`\`ato\n${atoSource}\n\`\`\``
    const html = renderToStaticMarkup(<Markdown text={md} />)
    expect(html).toContain('atopile-preview')
  })

  it('renders normal code block for non-circuit JSON', () => {
    const md = '```json\n{"key": "value"}\n```'
    const html = renderToStaticMarkup(<Markdown text={md} />)
    expect(html).not.toContain('circuit-json-preview')
    // Should render as a normal code block
    expect(html).toContain('key')
  })

  it('renders CircuitJsonPreview for circuit-json ```json fences', () => {
    const circuitArr = JSON.stringify([
      { type: 'source_component', source_component_id: 'sc1', name: 'R1', ftype: 'simple_resistor' },
    ])
    const md = `\`\`\`json\n${circuitArr}\n\`\`\``
    const html = renderToStaticMarkup(<Markdown text={md} />)
    expect(html).toContain('circuit-json-preview')
  })

  it('does not render CircuitJsonPreview for a non-array JSON object', () => {
    const md = '```json\n{"type": "source_component", "name": "R1"}\n```'
    const html = renderToStaticMarkup(<Markdown text={md} />)
    expect(html).not.toContain('circuit-json-preview')
  })

  it('preserves the sanitizer — urlTransform is not bypassed', () => {
    // A javascript: link should be stripped (rendered with empty href or omitted)
    const md = '[click](javascript:alert(1))'
    const html = renderToStaticMarkup(<Markdown text={md} />)
    // The link should not contain the javascript: href
    expect(html).not.toContain('javascript:alert')
  })
})
