// plcView.test.js — PLC Structured Text v0.2 (Tier 1)
//
// No WASM required. The suite verifies:
//
//   1. FileTree.jsx: 'plc_st' kind registered with SquareCode icon and
//      lime colour; '.plc.st' extension handled; kind appears in KIND_ORDER
//      and KIND_ROWS.
//
//   2. PLCView.jsx: exported; accepts correct props; registers a custom
//      'iec61131-st' language (not falling back to 'pascal'); snapshot()
//      method present via useImperativeHandle; diagnostic panel rendered
//      when diagnostics exist; lint debounce constant is 600ms.
//
//   3. The consolidated baseline migration's files_kind_check constraint
//      includes 'plc_st' (the per-kind migrations were folded 66->10).
//
//   4. api.js: lintPLC function exported.
//
//   5. Editor.jsx: isPLCFile predicate present; PLCView imported.

import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// ── 0. Source readers ─────────────────────────────────────────────────────────

const fileTreeSrc = readFileSync(
  path.resolve(__dirname, '../components/FileTree.jsx'), 'utf8',
)

const plcViewSrc = readFileSync(
  path.resolve(__dirname, '../components/PLCView.jsx'), 'utf8',
)

// After the 66->10 migration fold the per-kind migrations were collapsed
// into the consolidated baseline. Use whichever migration carries the
// final files_kind_check constraint.
const migrationSrc = (() => {
  const migDir = path.resolve(
    __dirname,
    '../../packages/kerf-core/src/kerf_core/db/migrations',
  )
  try {
    let found = ''
    for (const f of readdirSync(migDir).filter(n => n.endsWith('.sql')).sort()) {
      const sql = readFileSync(path.join(migDir, f), 'utf8')
      if (/add constraint files_kind_check/i.test(sql)) found = sql
    }
    return found
  } catch { return '' }
})()

const apiSrc = readFileSync(
  path.resolve(__dirname, '../lib/api.js'), 'utf8',
)

const editorSrc = readFileSync(
  path.resolve(__dirname, '../routes/Editor.jsx'), 'utf8',
)

// ── 1. FileTree kind registration ─────────────────────────────────────────────

describe('FileTree.jsx plc_st kind', () => {
  it("KindIcon handles kind 'plc_st'", () => {
    expect(fileTreeSrc).toContain("kind === 'plc_st'")
  })

  it("plc_st KindIcon uses SquareCode component", () => {
    const idx = fileTreeSrc.indexOf("kind === 'plc_st'")
    const block = fileTreeSrc.slice(idx, idx + 100)
    expect(block).toContain('SquareCode')
  })

  it("plc_st KindIcon uses lime colour", () => {
    const idx = fileTreeSrc.indexOf("kind === 'plc_st'")
    const block = fileTreeSrc.slice(idx, idx + 100)
    expect(block).toContain('lime')
  })

  it("'.plc.st' extension handled in KindIcon name fallback", () => {
    expect(fileTreeSrc).toContain('.plc.st')
  })

  it("KIND_ROWS contains plc_st entry", () => {
    const kindRowsIdx = fileTreeSrc.indexOf('const KIND_ROWS')
    const block = fileTreeSrc.slice(kindRowsIdx, kindRowsIdx + 3000)
    expect(block).toContain('plc_st')
  })

  it("KIND_ROWS plc_st entry uses SquareCode icon", () => {
    const kindRowsIdx = fileTreeSrc.indexOf('const KIND_ROWS')
    const block = fileTreeSrc.slice(kindRowsIdx, kindRowsIdx + 3000)
    const idx = block.indexOf('plc_st:')
    const entry = block.slice(idx, idx + 200)
    expect(entry).toContain('SquareCode')
  })

  it("KIND_ORDER includes 'plc_st'", () => {
    const kindOrderIdx = fileTreeSrc.indexOf('const KIND_ORDER')
    const line = fileTreeSrc.slice(kindOrderIdx, kindOrderIdx + 300)
    expect(line).toContain("'plc_st'")
  })

  it("KIND_ORDER places 'plc_st' after 'tool'", () => {
    const kindOrderIdx = fileTreeSrc.indexOf('const KIND_ORDER')
    const line = fileTreeSrc.slice(kindOrderIdx, kindOrderIdx + 300)
    const toolPos = line.indexOf("'tool'")
    const plcPos = line.indexOf("'plc_st'")
    expect(toolPos).toBeGreaterThan(-1)
    expect(plcPos).toBeGreaterThan(toolPos)
  })

  it("SquareCode icon is imported from lucide-react", () => {
    const importBlock = fileTreeSrc.slice(0, fileTreeSrc.indexOf('import { useWorkspace'))
    expect(importBlock).toContain('SquareCode')
  })
})

// ── 2. PLCView.jsx ────────────────────────────────────────────────────────────

describe('PLCView.jsx', () => {
  it('exports a default function PLCView', () => {
    expect(plcViewSrc).toContain('export default function PLCView')
  })

  it('accepts content prop', () => {
    const sigIdx = plcViewSrc.indexOf('export default function PLCView')
    const sig = plcViewSrc.slice(sigIdx, sigIdx + 300)
    expect(sig).toContain('content')
  })

  it('accepts projectId prop', () => {
    const sigIdx = plcViewSrc.indexOf('export default function PLCView')
    const sig = plcViewSrc.slice(sigIdx, sigIdx + 300)
    expect(sig).toContain('projectId')
  })

  it('accepts viewRef prop for snapshot', () => {
    const sigIdx = plcViewSrc.indexOf('export default function PLCView')
    const sig = plcViewSrc.slice(sigIdx, sigIdx + 300)
    expect(sig).toContain('viewRef')
  })

  it('registers custom iec61131-st language (not pascal fallback)', () => {
    expect(plcViewSrc).toContain("'iec61131-st'")
    expect(plcViewSrc).not.toContain("language: 'pascal'")
    expect(plcViewSrc).not.toContain('language="pascal"')
  })

  it('registers language via registerIEC61131STLanguage', () => {
    expect(plcViewSrc).toContain('registerIEC61131STLanguage')
  })

  it('includes END_VAR in keyword list', () => {
    expect(plcViewSrc).toContain("'END_VAR'")
  })

  it('includes END_FOR in keyword list', () => {
    expect(plcViewSrc).toContain("'END_FOR'")
  })

  it('includes END_FUNCTION_BLOCK in keyword list', () => {
    expect(plcViewSrc).toContain("'END_FUNCTION_BLOCK'")
  })

  it('includes BOOL type in type list', () => {
    expect(plcViewSrc).toContain("'BOOL'")
  })

  it('includes DINT type in type list', () => {
    expect(plcViewSrc).toContain("'DINT'")
  })

  it('includes AND/OR/NOT/XOR in keyword list', () => {
    expect(plcViewSrc).toContain("'AND'")
    expect(plcViewSrc).toContain("'OR'")
    expect(plcViewSrc).toContain("'NOT'")
    expect(plcViewSrc).toContain("'XOR'")
  })

  it('uses useImperativeHandle for snapshot', () => {
    expect(plcViewSrc).toContain('useImperativeHandle')
  })

  it('snapshot method returns a Blob (canvas.toBlob)', () => {
    expect(plcViewSrc).toContain('toBlob')
  })

  it('lint debounce is 600ms', () => {
    expect(plcViewSrc).toContain('600')
  })

  it('calls api.lintPLC for lint', () => {
    expect(plcViewSrc).toContain('api.lintPLC')
  })

  it('renders diagnostic panel when diagnostics present', () => {
    expect(plcViewSrc).toContain('diagnostics.map')
  })

  it('renders warnings panel when warnings present', () => {
    expect(plcViewSrc).toContain('warnings.map')
  })

  it('sets Monaco markers via setModelMarkers', () => {
    expect(plcViewSrc).toContain('setModelMarkers')
  })

  it('imports SquareCode icon', () => {
    const importBlock = plcViewSrc.slice(0, plcViewSrc.indexOf('export default'))
    expect(importBlock).toContain('SquareCode')
  })

  it('imports @monaco-editor/react', () => {
    const importBlock = plcViewSrc.slice(0, plcViewSrc.indexOf('export default'))
    expect(importBlock).toContain('@monaco-editor/react')
  })
})

// ── 3. Migration 057 ──────────────────────────────────────────────────────────

describe('Migration 057 — plc_st kind', () => {
  it('migration file exists', () => {
    expect(migrationSrc.length).toBeGreaterThan(0)
  })

  it("migration adds 'plc_st' to the files_kind_check constraint", () => {
    expect(migrationSrc).toContain('plc_st')
  })

  it('migration drops the old constraint before adding the new one', () => {
    expect(migrationSrc).toContain('drop constraint if exists files_kind_check')
  })

  it("migration retains prior kinds including 'tool'", () => {
    expect(migrationSrc).toContain("'tool'")
  })

  it("migration retains 'section' kind (from migration 053)", () => {
    expect(migrationSrc).toContain("'section'")
  })

  it("migration retains 'cam_layered' kind (from migration 054)", () => {
    expect(migrationSrc).toContain("'cam_layered'")
  })
})

// ── 4. api.js lintPLC ─────────────────────────────────────────────────────────

describe('api.js lintPLC', () => {
  it('exports lintPLC function', () => {
    expect(apiSrc).toContain('lintPLC')
  })

  it('lintPLC posts to a plc/lint endpoint', () => {
    const idx = apiSrc.indexOf('lintPLC')
    const block = apiSrc.slice(idx, idx + 200)
    expect(block).toContain('plc')
    expect(block).toContain('lint')
  })

  it('lintPLC sends source in body', () => {
    const idx = apiSrc.indexOf('lintPLC')
    const block = apiSrc.slice(idx, idx + 200)
    expect(block).toContain('source')
  })
})

// ── 5. Editor.jsx dispatch ────────────────────────────────────────────────────

describe('Editor.jsx plc_st dispatch', () => {
  it('imports PLCView', () => {
    const importBlock = editorSrc.slice(0, editorSrc.indexOf('export default function Editor'))
    expect(importBlock).toContain('PLCView')
  })

  it('has isPLCFile predicate', () => {
    expect(editorSrc).toContain('isPLCFile')
  })

  it('isPLCFile checks plc_st kind', () => {
    const idx = editorSrc.indexOf('isPLCFile')
    const block = editorSrc.slice(idx, idx + 200)
    expect(block).toContain("plc_st")
  })

  it('isPLCFile checks .plc.st extension', () => {
    const idx = editorSrc.indexOf('isPLCFile')
    const block = editorSrc.slice(idx, idx + 200)
    expect(block).toContain('.plc.st')
  })

  it('renders PLCView for plcFile', () => {
    expect(editorSrc).toContain('<PLCView')
  })
})
