import { describe, it, expect } from 'vitest'
import { routeByExtension, ATO_TEMPLATE } from './editorRouter.js'

// ── routeByExtension ──────────────────────────────────────────────────────────

describe('routeByExtension', () => {
  it('routes .ato to AtopileEditor', () => {
    expect(routeByExtension('schematic.ato')).toBe('AtopileEditor')
    expect(routeByExtension('Foo.ato')).toBe('AtopileEditor')
  })

  it('routes .tsx to TscircuitEditor', () => {
    expect(routeByExtension('usb_power.circuit.tsx')).toBe('TscircuitEditor')
    expect(routeByExtension('board.tsx')).toBe('TscircuitEditor')
  })

  it('routes .py to MonacoEditor', () => {
    expect(routeByExtension('main.py')).toBe('MonacoEditor')
  })

  it('routes .md to MonacoEditor', () => {
    expect(routeByExtension('README.md')).toBe('MonacoEditor')
  })

  it('routes .json to MonacoEditor', () => {
    expect(routeByExtension('config.json')).toBe('MonacoEditor')
  })

  it('routes .txt to MonacoEditor', () => {
    expect(routeByExtension('notes.txt')).toBe('MonacoEditor')
  })

  it('falls back to MonacoEditor for unknown extensions', () => {
    expect(routeByExtension('archive.tar')).toBe('MonacoEditor')
    expect(routeByExtension('data.csv')).toBe('MonacoEditor')
    expect(routeByExtension('binary.bin')).toBe('MonacoEditor')
  })

  it('falls back to MonacoEditor for files with no extension', () => {
    expect(routeByExtension('Makefile')).toBe('MonacoEditor')
    expect(routeByExtension('LICENSE')).toBe('MonacoEditor')
  })

  it('handles path prefixes — only the basename matters', () => {
    expect(routeByExtension('dir/sub/schematic.ato')).toBe('AtopileEditor')
    expect(routeByExtension('a/b/c.tsx')).toBe('TscircuitEditor')
  })

  it('falls back for null / undefined / empty input', () => {
    expect(routeByExtension(null)).toBe('MonacoEditor')
    expect(routeByExtension(undefined)).toBe('MonacoEditor')
    expect(routeByExtension('')).toBe('MonacoEditor')
  })
})

// ── ATO_TEMPLATE — well-formed minimum module ─────────────────────────────────
// kerf_electronics.atopile.parser structural checks (JS-side):
//  • starts with `module <Name>:` declaration
//  • ends with matching `end <Name>;` terminator
//  • has non-empty body between declaration and terminator

describe('ATO_TEMPLATE', () => {
  it('is a non-empty string', () => {
    expect(typeof ATO_TEMPLATE).toBe('string')
    expect(ATO_TEMPLATE.length).toBeGreaterThan(0)
  })

  it('opens with a module declaration (module <Name>:)', () => {
    expect(ATO_TEMPLATE).toMatch(/^\s*module\s+\w+\s*:/)
  })

  it('closes with a matching end statement (end <Name>;)', () => {
    // Extract module name from declaration
    const declMatch = ATO_TEMPLATE.match(/^\s*module\s+(\w+)\s*:/)
    expect(declMatch).toBeTruthy()
    const name = declMatch[1]
    // Template must end with `end <Name>;` (whitespace-tolerant)
    expect(ATO_TEMPLATE).toMatch(new RegExp(`end\\s+${name}\\s*;\\s*$`))
  })

  it('module name in declaration matches module name in end statement', () => {
    const declMatch = ATO_TEMPLATE.match(/module\s+(\w+)\s*:/)
    const endMatch = ATO_TEMPLATE.match(/end\s+(\w+)\s*;/)
    expect(declMatch).toBeTruthy()
    expect(endMatch).toBeTruthy()
    expect(declMatch[1]).toBe(endMatch[1])
  })

  it('contains a body between declaration and end (non-trivial module)', () => {
    const lines = ATO_TEMPLATE.split('\n').map((l) => l.trim()).filter(Boolean)
    // More than just the opening and closing lines
    expect(lines.length).toBeGreaterThan(2)
  })
})
