// Coverage for src/lib/equations.js — parsing, evaluation, and the
// fresh-regex placeholder substitution. The session previously hit a silent
// "all parameterised dimensions resolve to 0" bug caused by a shared /g regex
// whose lastIndex leaked across calls. The pure unit tests below pin the
// fix in place: substituteParams must be idempotent across repeated calls
// and survive interleaving with extractParamPlaceholders.
import { describe, it, expect } from 'vitest'
import {
  parseEquations,
  serializeEquations,
  evaluateEquations,
  mergeEquationFiles,
  substituteParams,
  substituteFeatureTree,
  substituteSketch,
  extractParamPlaceholders,
  validIdent,
} from '../lib/equations.js'

describe('equations parse + evaluate', () => {
  it('parses a valid equations doc', () => {
    const doc = parseEquations(JSON.stringify({
      version: 1,
      params: [
        { name: 'wall', expr: '2', unit: 'mm', comment: 'thickness' },
        { name: 'h', expr: 'wall*5' },
      ],
    }))
    expect(doc.version).toBe(1)
    expect(doc.params).toHaveLength(2)
    expect(doc.params[0].name).toBe('wall')
    expect(doc.params[0].comment).toBe('thickness')
    expect(doc.errors).toEqual([])
  })

  it('records a parse error for malformed JSON without throwing', () => {
    const doc = parseEquations('{ not json')
    expect(doc.errors.length).toBe(1)
    expect(doc.errors[0].paramIndex).toBe(-1)
    expect(doc.params).toEqual([])
  })

  it('treats empty content as an empty (but valid) doc', () => {
    const doc = parseEquations('   ')
    expect(doc.params).toEqual([])
    expect(doc.errors).toEqual([])
  })

  it('evaluates expressions in declaration order with partial scope', () => {
    const doc = parseEquations(JSON.stringify({
      params: [
        { name: 'a', expr: '3' },
        { name: 'b', expr: 'a*4' },
        { name: 'c', expr: '!!!' }, // bad
        { name: 'd', expr: 'b+1' }, // still resolves against a,b
      ],
    }))
    const { values, errors } = evaluateEquations(doc)
    expect(values.a).toBe(3)
    expect(values.b).toBe(12)
    expect(values.d).toBe(13)
    expect(errors.some((e) => e.name === 'c')).toBe(true)
  })

  it('flags duplicate names and missing identifiers', () => {
    const doc = parseEquations(JSON.stringify({
      params: [
        { name: 'x', expr: '1' },
        { name: 'x', expr: '2' },
        { name: '1bad', expr: '3' },
        { name: '', expr: '4' },
      ],
    }))
    const { errors } = evaluateEquations(doc)
    const messages = errors.map((e) => e.message)
    expect(messages.some((m) => /duplicate/.test(m))).toBe(true)
    expect(messages.some((m) => /valid identifier/.test(m))).toBe(true)
    expect(messages.some((m) => /name is required/.test(m))).toBe(true)
  })

  it('roundtrips through serializeEquations', () => {
    const doc = parseEquations(JSON.stringify({
      params: [{ name: 'w', expr: '10', unit: 'mm' }],
    }))
    const json = serializeEquations(doc)
    const re = parseEquations(json)
    expect(re.params).toEqual([{ name: 'w', expr: '10', unit: 'mm', comment: '' }])
  })

  it('blocks the disabled mathjs surfaces (import / createUnit)', () => {
    const doc = parseEquations(JSON.stringify({
      params: [{ name: 'x', expr: 'createUnit("foo")' }],
    }))
    const { errors } = evaluateEquations(doc)
    expect(errors.length).toBe(1)
    expect(errors[0].name).toBe('x')
  })
})

describe('equations placeholder substitution (fresh-regex anti-leak)', () => {
  const scope = { wall: 2, h: 10 }

  it('returns a number when the entire string is a single placeholder', () => {
    expect(substituteParams('${wall}', scope)).toBe(2)
    // surrounding whitespace is tolerated.
    expect(substituteParams('  ${h}  ', scope)).toBe(10)
  })

  it('substitutes inline placeholders within larger strings', () => {
    expect(substituteParams('w=${wall}mm', scope)).toBe('w=2mm')
  })

  it('leaves missing/undefined placeholders intact (no NaN bleed)', () => {
    expect(substituteParams('${ghost}', scope)).toBe('${ghost}')
    expect(substituteParams('a${ghost}b', scope)).toBe('a${ghost}b')
  })

  it('returns input unchanged when there is no placeholder', () => {
    expect(substituteParams('plain', scope)).toBe('plain')
    expect(substituteParams(42, scope)).toBe(42)
  })

  it('is idempotent across repeated calls (regex lastIndex must not leak)', () => {
    // The historic bug: a shared /g regex caused .test() on the second call
    // to skip a placeholder it should have matched. Hammer it.
    const calls = []
    for (let i = 0; i < 20; i++) {
      calls.push(substituteParams('${wall}', scope))
      calls.push(substituteParams('x=${h}', scope))
    }
    for (let i = 0; i < 20; i++) {
      expect(calls[i * 2]).toBe(2)
      expect(calls[i * 2 + 1]).toBe('x=10')
    }
  })

  it('survives interleaving with extractParamPlaceholders', () => {
    expect(extractParamPlaceholders('${wall} and ${h}')).toEqual(['wall', 'h'])
    expect(substituteParams('${wall}', scope)).toBe(2)
    expect(extractParamPlaceholders('${wall}')).toEqual(['wall'])
    expect(substituteParams('${wall}', scope)).toBe(2)
  })

  it('handles malformed placeholders (unmatched braces)', () => {
    // Missing closing brace — the regex should not match, value passes through.
    expect(substituteParams('${wall', scope)).toBe('${wall')
    expect(substituteParams('wall}', scope)).toBe('wall}')
  })
})

describe('equations tree + sketch + merge helpers', () => {
  it('walks nested arrays/objects in substituteFeatureTree', () => {
    const tree = [{ type: 'extrude', height: '${h}', nested: { d: '${wall}' } }]
    const out = substituteFeatureTree(tree, { wall: 2, h: 10 })
    expect(out[0].height).toBe(10)
    expect(out[0].nested.d).toBe(2)
  })

  it('substituteSketch only rewrites dimensional constraints', () => {
    const sketch = {
      constraints: [
        { type: 'distance', value: '${wall}' },
        { type: 'horizontal', a: 0 },
      ],
    }
    const out = substituteSketch(sketch, { wall: 2 })
    expect(out.constraints[0].value).toBe(2)
    expect(out.constraints[1]).toEqual({ type: 'horizontal', a: 0 })
  })

  it('mergeEquationFiles takes last-loaded wins and reports duplicates', () => {
    const files = [
      { path: 'a.equations', content: JSON.stringify({ params: [{ name: 'x', expr: '1' }] }) },
      { path: 'b.equations', content: JSON.stringify({ params: [{ name: 'x', expr: '2' }] }) },
    ]
    const merged = mergeEquationFiles(files)
    expect(merged.values.x).toBe(2)
    expect(merged.duplicates).toHaveLength(1)
    expect(merged.duplicates[0].name).toBe('x')
  })

  it('validIdent enforces JS identifier shape', () => {
    expect(validIdent('foo')).toBe(true)
    expect(validIdent('_a1')).toBe(true)
    expect(validIdent('1bad')).toBe(false)
    expect(validIdent('')).toBe(false)
    expect(validIdent('with space')).toBe(false)
  })
})
