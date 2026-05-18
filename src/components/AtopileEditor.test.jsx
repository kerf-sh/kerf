/**
 * AtopileEditor.test.jsx (T-196)
 *
 * Tests for:
 *   1. atopileMonacoLanguage.js — tokenizer recognises all keywords +
 *      operators + number-unit literals; emits `invalid` tokens on garbage.
 *   2. atopileCompileBridge.js  — fetch wrapper normalisation logic.
 *
 * We DO NOT render <AtopileEditor> directly here because @monaco-editor/react
 * spins up a Worker context that vitest-jsdom can't run.  The interesting
 * logic lives in the pure helper modules, so we test at that layer and rely
 * on the Monaco integration being covered by manual browser testing.
 *
 * Run:
 *   npm test -- src/components/AtopileEditor.test.jsx
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { tokenizeLine, KEYWORDS, LANGUAGE_ID } from '../lib/atopileMonacoLanguage.js'
import { compileAtopile } from '../lib/atopileCompileBridge.js'

// ---------------------------------------------------------------------------
// Tokenizer tests — atopileMonacoLanguage.tokenizeLine
// ---------------------------------------------------------------------------

describe('atopileMonacoLanguage — keyword recognition', () => {
  it.each(KEYWORDS)('keyword "%s" is classified as keyword token', (kw) => {
    const tokens = tokenizeLine(kw)
    const kwToken = tokens.find((t) => t.value === kw)
    expect(kwToken, `token for "${kw}" not found in ${JSON.stringify(tokens)}`).toBeTruthy()
    expect(kwToken.type).toBe('keyword')
  })

  it('identifies all 8 keywords as the canonical set', () => {
    expect(KEYWORDS).toEqual(
      expect.arrayContaining([
        'module', 'component', 'signal', 'pin',
        'import', 'from', 'new', 'interface',
      ])
    )
    expect(KEYWORDS).toHaveLength(8)
  })

  it('module keyword at start of a declaration line', () => {
    const tokens = tokenizeLine('module LedDriver:')
    const types = tokens.filter((t) => t.type !== 'white').map((t) => t.type)
    expect(types[0]).toBe('keyword')
  })

  it('component keyword at start of a declaration line', () => {
    const tokens = tokenizeLine('component Resistor:')
    const first = tokens.find((t) => t.type !== 'white')
    expect(first.type).toBe('keyword')
    expect(first.value).toBe('component')
  })

  it('signal keyword in indented line', () => {
    const tokens = tokenizeLine('    signal VCC')
    const kw = tokens.find((t) => t.value === 'signal')
    expect(kw?.type).toBe('keyword')
  })

  it('pin keyword in indented line', () => {
    const tokens = tokenizeLine('    pin 1')
    const kw = tokens.find((t) => t.value === 'pin')
    expect(kw?.type).toBe('keyword')
  })

  it('new keyword in instantiation line', () => {
    const tokens = tokenizeLine('    r1 = new Resistor')
    const kw = tokens.find((t) => t.value === 'new')
    expect(kw?.type).toBe('keyword')
  })

  it('import keyword at start of import line', () => {
    const tokens = tokenizeLine('import Resistor from "generics/res.ato"')
    const kw = tokens.find((t) => t.value === 'import')
    expect(kw?.type).toBe('keyword')
  })

  it('from keyword in import statement', () => {
    const tokens = tokenizeLine('import Resistor from "generics/res.ato"')
    const kw = tokens.find((t) => t.value === 'from')
    expect(kw?.type).toBe('keyword')
  })

  it('interface keyword classified correctly', () => {
    const tokens = tokenizeLine('interface PowerRail:')
    const kw = tokens.find((t) => t.value === 'interface')
    expect(kw?.type).toBe('keyword')
  })
})

describe('atopileMonacoLanguage — operator tokens', () => {
  it('tilde operator ~ is an operator token', () => {
    const tokens = tokenizeLine('r1.A ~ r2.B')
    const op = tokens.find((t) => t.value === '~')
    expect(op?.type).toBe('operator')
  })

  it('equals operator = is an operator token', () => {
    const tokens = tokenizeLine('r1 = new Resistor')
    const op = tokens.find((t) => t.value === '=')
    expect(op?.type).toBe('operator')
  })

  it('colon : is an operator token', () => {
    const tokens = tokenizeLine('module Foo:')
    const op = tokens.find((t) => t.value === ':')
    expect(op?.type).toBe('operator')
  })
})

describe('atopileMonacoLanguage — number+unit tokens', () => {
  const cases = [
    ['10kohm',  '10kohm'],
    ['100nF',   '100nF'],
    ['3.3V',    '3.3V'],
    ['1k',      '1k'],
    ['470R',    '470R'],
    ['22uF',    '22uF'],
    ['10M',     '10M'],
    ['100p',    '100p'],
  ]

  it.each(cases)('value "%s" is classified as number.unit', (input, expected) => {
    const tokens = tokenizeLine(input)
    const tok = tokens.find((t) => t.value === expected)
    expect(tok, `token for "${expected}" not found in ${JSON.stringify(tokens)}`).toBeTruthy()
    expect(tok.type).toBe('number.unit')
  })

  it('number+unit in assignment line', () => {
    const tokens = tokenizeLine('resistance = 10kohm')
    const numTok = tokens.find((t) => t.type === 'number.unit')
    expect(numTok).toBeTruthy()
    expect(numTok.value).toBe('10kohm')
  })
})

describe('atopileMonacoLanguage — comment tokens', () => {
  it('# comment line is classified as comment', () => {
    const tokens = tokenizeLine('# This is a comment')
    const comment = tokens.find((t) => t.type === 'comment')
    expect(comment).toBeTruthy()
    expect(comment.value).toContain('# This is a comment')
  })

  it('inline comment after code is comment', () => {
    const tokens = tokenizeLine('signal A  # VCC net')
    const comment = tokens.find((t) => t.type === 'comment')
    expect(comment).toBeTruthy()
  })

  it('code before inline comment is not comment', () => {
    const tokens = tokenizeLine('signal A  # VCC net')
    const kw = tokens.find((t) => t.value === 'signal')
    expect(kw?.type).toBe('keyword')
  })
})

describe('atopileMonacoLanguage — string tokens', () => {
  it('double-quoted string is classified as string', () => {
    const tokens = tokenizeLine('import Resistor from "generics/res.ato"')
    const str = tokens.find((t) => t.type === 'string')
    expect(str).toBeTruthy()
    expect(str.value).toBe('"generics/res.ato"')
  })

  it("single-quoted string is classified as string", () => {
    const tokens = tokenizeLine("from 'generics/res.ato' import Resistor")
    const str = tokens.find((t) => t.type === 'string')
    expect(str).toBeTruthy()
    expect(str.value).toBe("'generics/res.ato'")
  })
})

describe('atopileMonacoLanguage — identifiers', () => {
  it('plain identifier is classified as identifier', () => {
    const tokens = tokenizeLine('LedDriver')
    const id = tokens.find((t) => t.value === 'LedDriver')
    expect(id?.type).toBe('identifier')
  })

  it('dotted identifier is classified as identifier (not keyword)', () => {
    const tokens = tokenizeLine('r1.A')
    const id = tokens.find((t) => t.value === 'r1.A')
    expect(id?.type).toBe('identifier')
  })

  it('identifier starting with underscore is valid', () => {
    const tokens = tokenizeLine('_private_net')
    const id = tokens.find((t) => t.value === '_private_net')
    expect(id?.type).toBe('identifier')
  })
})

describe('atopileMonacoLanguage — invalid / error tokens', () => {
  it('bare @ character emits invalid token', () => {
    const tokens = tokenizeLine('@invalid')
    const inv = tokens.find((t) => t.type === 'invalid')
    expect(inv).toBeTruthy()
    expect(inv.value).toBe('@')
  })

  it('dollar sign emits invalid token', () => {
    const tokens = tokenizeLine('$bad')
    const inv = tokens.find((t) => t.type === 'invalid')
    expect(inv).toBeTruthy()
    expect(inv.value).toBe('$')
  })

  it('line of garbage characters emits only invalid tokens (plus whitespace)', () => {
    const tokens = tokenizeLine('@@@@')
    const nonWhite = tokens.filter((t) => t.type !== 'white')
    expect(nonWhite.length).toBeGreaterThan(0)
    expect(nonWhite.every((t) => t.type === 'invalid')).toBe(true)
  })

  it('valid line has zero invalid tokens', () => {
    const tokens = tokenizeLine('    r1 = new Resistor  # bias')
    const invalids = tokens.filter((t) => t.type === 'invalid')
    expect(invalids).toHaveLength(0)
  })
})

describe('atopileMonacoLanguage — language ID constant', () => {
  it('LANGUAGE_ID is "atopile"', () => {
    expect(LANGUAGE_ID).toBe('atopile')
  })
})

describe('atopileMonacoLanguage — full line tokenization round-trips', () => {
  it('reconstructed source matches original for a module declaration', () => {
    const line = 'module LedDriver:'
    const tokens = tokenizeLine(line)
    const reconstructed = tokens.map((t) => t.value).join('')
    expect(reconstructed).toBe(line)
  })

  it('reconstructed source matches original for an assignment', () => {
    const line = '    resistance = 10kohm'
    const tokens = tokenizeLine(line)
    expect(tokens.map((t) => t.value).join('')).toBe(line)
  })

  it('reconstructed source matches original for a connection', () => {
    const line = '    r1.A ~ r2.B'
    const tokens = tokenizeLine(line)
    expect(tokens.map((t) => t.value).join('')).toBe(line)
  })

  it('reconstructed source matches original for an import line', () => {
    const line = 'import Resistor from "generics/res.ato"'
    const tokens = tokenizeLine(line)
    expect(tokens.map((t) => t.value).join('')).toBe(line)
  })
})

// ---------------------------------------------------------------------------
// atopileCompileBridge — fetch wrapper
// ---------------------------------------------------------------------------

describe('atopileCompileBridge — normalisation', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function mockFetch(status, body) {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    })
  }

  it('returns ok=true with circuit array on successful compile', async () => {
    const fakeCircuit = [{ type: 'source_component', source_component_id: 'sc_1', name: 'r1', ftype: 'simple_resistor' }]
    mockFetch(200, { ok: true, circuit: fakeCircuit, warnings: [] })

    const result = await compileAtopile('module T:\n    r1 = new Resistor\n')
    expect(result.ok).toBe(true)
    expect(result.circuit).toEqual(fakeCircuit)
    expect(result.errors).toBeNull()
  })

  it('returns ok=false with errors on backend compile error', async () => {
    mockFetch(200, {
      ok: false,
      errors: [{ message: 'no module found', line: 1 }],
      warnings: [],
    })

    const result = await compileAtopile('not atopile source')
    expect(result.ok).toBe(false)
    expect(result.circuit).toBeNull()
    expect(result.errors).toEqual([{ message: 'no module found', line: 1 }])
  })

  it('returns ok=false on HTTP 400', async () => {
    mockFetch(400, { detail: 'source is required' })

    const result = await compileAtopile('  ')
    expect(result.ok).toBe(false)
    expect(result.errors[0].message).toContain('source is required')
  })

  it('returns ok=false on HTTP 422 validation error', async () => {
    mockFetch(422, { detail: [{ msg: 'field required', loc: ['body', 'source'] }] })

    const result = await compileAtopile('')
    expect(result.ok).toBe(false)
    expect(result.errors[0].message).toContain('field required')
  })

  it('returns ok=false on network failure', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Failed to fetch'))

    const result = await compileAtopile('module T: pass')
    expect(result.ok).toBe(false)
    expect(result.errors[0].message).toContain('Failed to fetch')
  })

  it('returns ok=false when fetch is aborted', async () => {
    const err = new Error('aborted')
    err.name = 'AbortError'
    globalThis.fetch = vi.fn().mockRejectedValue(err)

    const result = await compileAtopile('module T:', { signal: { aborted: true } })
    expect(result.ok).toBe(false)
    expect(result.errors[0].message).toBe('aborted')
  })

  it('passes module param to the request body when provided', async () => {
    mockFetch(200, { ok: true, circuit: [], warnings: [] })

    await compileAtopile('module A:\nmodule B:', { module: 'A' })

    const calls = globalThis.fetch.mock.calls
    expect(calls.length).toBe(1)
    const body = JSON.parse(calls[0][1].body)
    expect(body.module).toBe('A')
  })

  it('omits module param from body when not provided', async () => {
    mockFetch(200, { ok: true, circuit: [], warnings: [] })

    await compileAtopile('module A:')

    const body = JSON.parse(globalThis.fetch.mock.calls[0][1].body)
    expect(body).not.toHaveProperty('module')
  })

  it('passes warnings through when ok=true', async () => {
    mockFetch(200, {
      ok: true,
      circuit: [],
      warnings: ["module 'X' not found; compiling 'Y' instead"],
    })

    const result = await compileAtopile('module Y:')
    expect(result.ok).toBe(true)
    expect(result.warnings).toHaveLength(1)
    expect(result.warnings[0]).toContain("'X' not found")
  })

  it('always returns a warnings array even when backend omits it', async () => {
    mockFetch(200, { ok: true, circuit: [] })

    const result = await compileAtopile('module T:')
    expect(result.warnings).toBeInstanceOf(Array)
  })

  it('returns ok=false on HTTP 500 server error', async () => {
    mockFetch(500, { detail: 'internal server error' })

    const result = await compileAtopile('module T:')
    expect(result.ok).toBe(false)
    expect(result.errors[0].message).toContain('internal server error')
  })
})
