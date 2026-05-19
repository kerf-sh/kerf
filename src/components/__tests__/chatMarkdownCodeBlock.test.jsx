/**
 * chatMarkdownCodeBlock.test.jsx
 *
 * Regression: fenced code blocks rendered inside the chat panel rendered as
 * `[object Object],[object Object],…` instead of the actual JS source. ReactMarkdown 9+ paired with rehype-highlight passes an ARRAY of React
 * nodes (one <span> per syntax-highlighted token) as `children` to the
 * custom `code` component. The old implementation did
 *     const text = String(children || '')
 * which calls Array.prototype.toString — `[<span>, <span>, …]` becomes
 * `"[object Object],[object Object],…"`. Users saw that string verbatim in
 * the chat next to "It looks like there's a temporary backend issue…".
 *
 * Fix: render `children` directly inside <pre><code>, and use a
 * children-to-text walker only for the "looks like a block?" heuristic.
 */
import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { Markdown, childrenToText } from '../ChatPanel.jsx'

// ── 1. childrenToText helper ─────────────────────────────────────────────────

describe('childrenToText', () => {
  it('returns "" for null/undefined/false', () => {
    expect(childrenToText(null)).toBe('')
    expect(childrenToText(undefined)).toBe('')
    expect(childrenToText(false)).toBe('')
  })

  it('passes strings through', () => {
    expect(childrenToText('hello')).toBe('hello')
  })

  it('coerces numbers to strings', () => {
    expect(childrenToText(42)).toBe('42')
  })

  it('concatenates an array of strings', () => {
    expect(childrenToText(['a', 'b', 'c'])).toBe('abc')
  })

  it('descends into React-like element nodes via props.children', () => {
    // Shape mimics what react-markdown passes: { type, props: { children } }
    const node = { type: 'span', props: { children: 'token1' } }
    expect(childrenToText(node)).toBe('token1')
  })

  it('handles a mixed array of strings and element nodes', () => {
    const mixed = [
      'const ',
      { type: 'span', props: { children: 'W' } },
      ' = ',
      { type: 'span', props: { children: '80' } },
      ';',
    ]
    expect(childrenToText(mixed)).toBe('const W = 80;')
  })

  it('recurses into nested element children', () => {
    const nested = {
      type: 'span',
      props: {
        children: [
          { type: 'span', props: { children: 'outer ' } },
          { type: 'span', props: { children: 'inner' } },
        ],
      },
    }
    expect(childrenToText(nested)).toBe('outer inner')
  })

  it('NEVER produces "[object Object]" for an array of elements', () => {
    const elements = [
      { type: 'span', props: { children: 'a' } },
      { type: 'span', props: { children: 'b' } },
    ]
    expect(childrenToText(elements)).not.toContain('[object Object]')
  })
})

// ── 2. Markdown component — fenced code-block rendering ──────────────────────

describe('Markdown — fenced code blocks', () => {
  it('does NOT render "[object Object]" for a ```js block', () => {
    const md = [
      '```js',
      'const W = 80;',
      'const D = 60;',
      'function main() { return W * D; }',
      '```',
    ].join('\n')
    const html = renderToStaticMarkup(<Markdown text={md} />)
    expect(html).not.toContain('[object Object]')
  })

  it('preserves the source text of a code block', () => {
    const md = [
      '```js',
      'const TAG = "regression-pin";',
      '```',
    ].join('\n')
    const html = renderToStaticMarkup(<Markdown text={md} />)
    // The exact source must appear in the rendered HTML (possibly wrapped in
    // hljs spans, so we test substring presence).
    expect(html).toContain('regression-pin')
    expect(html).toContain('TAG')
  })

  it('keeps the language label on block code', () => {
    const md = ['```js', 'x = 1', '```'].join('\n')
    const html = renderToStaticMarkup(<Markdown text={md} />)
    // Block-treatment renders the language pill ("js" lower-cased in source,
    // but text-transform: uppercase in CSS — we just check the raw text).
    expect(html).toMatch(/>js</)
  })

  it('inline `code` still renders as inline <code>, not the block wrapper', () => {
    const html = renderToStaticMarkup(<Markdown text="Use `foo()` to bar." />)
    expect(html).toContain('<code')
    // The block wrapper has the language pill — inline must not have it.
    expect(html).not.toMatch(/>code</)  // the "code" language pill
  })

  it('renders multiple code blocks without cross-contamination', () => {
    const md = [
      'First:',
      '```js',
      'one()',
      '```',
      'Second:',
      '```py',
      'two()',
      '```',
    ].join('\n')
    const html = renderToStaticMarkup(<Markdown text={md} />)
    expect(html).not.toContain('[object Object]')
    // The function names live in separate hljs token spans
    // (`<span class="hljs-title function_">one</span>()`), so we look for
    // the identifiers on their own — syntax highlighting splits them off
    // from the `()`.
    expect(html).toContain('>one<')
    expect(html).toContain('two()')
    expect(html).toContain('language-js')
    expect(html).toContain('language-py')
  })

  it('never leaks the react-markdown `node` AST prop to the DOM', () => {
    // The original symptom was `<code class="…" node="[object Object]">`.
    // Future custom MD_COMPONENTS overrides must also remember to strip
    // `node` from `...rest` — pin the regression so a refactor catches it.
    const md = '```js\nconst x = 1;\n```'
    const html = renderToStaticMarkup(<Markdown text={md} />)
    expect(html).not.toMatch(/\bnode="\[object Object\]"/)
    expect(html).not.toMatch(/\bnode=/)
  })
})
