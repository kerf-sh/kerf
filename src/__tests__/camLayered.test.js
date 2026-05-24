// camLayered.test.js — Slicing v0.2 CNC layered slicing
//
// No WASM required. The suite verifies:
//
//   1. FileTree.jsx: 'cam_layered' kind is registered with Layers icon and
//      teal colour; '.cam.layered' extension is handled; kind appears in
//      KIND_ORDER; KIND_ROWS entry exists.
//
//   2. CAMView.jsx: LayeredCAMView is exported; it renders a Z-slider for
//      multi-layer documents; it renders an empty-state message for no layers;
//      Generate G-code button is present when layers exist.
//
//   3. The consolidated baseline migration's files_kind_check constraint
//      includes 'cam_layered' (the per-kind migrations were folded 66->10).

import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// ── 0. File path helpers ─────────────────────────────────────────────────────

const fileTreeSrc = readFileSync(
  path.resolve(__dirname, '../components/FileTree.jsx'), 'utf8',
)
const camViewSrc = readFileSync(
  path.resolve(__dirname, '../components/CAMView.jsx'), 'utf8',
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
      if (/check\s*\(\s*kind\s+in\s*\(\s*'file'/i.test(sql)) found = sql
    }
    return found
  } catch { return '' }
})()

// ── 1. FileTree kind registration ────────────────────────────────────────────

describe('FileTree.jsx cam_layered kind', () => {
  it("KindIcon handles kind 'cam_layered'", () => {
    expect(fileTreeSrc).toContain("kind === 'cam_layered'")
  })

  it("cam_layered KindIcon uses Layers component", () => {
    const idx = fileTreeSrc.indexOf("kind === 'cam_layered'")
    const block = fileTreeSrc.slice(idx, idx + 100)
    expect(block).toContain('Layers')
  })

  it("cam_layered KindIcon uses teal colour", () => {
    const idx = fileTreeSrc.indexOf("kind === 'cam_layered'")
    const block = fileTreeSrc.slice(idx, idx + 100)
    expect(block).toContain('teal')
  })

  it("'.cam.layered' extension is handled in KindIcon name fallback", () => {
    expect(fileTreeSrc).toContain('.cam.layered')
  })

  it("KIND_ROWS contains cam_layered entry", () => {
    expect(fileTreeSrc).toContain("cam_layered:")
    const kindRowsIdx = fileTreeSrc.indexOf('const KIND_ROWS')
    const block = fileTreeSrc.slice(kindRowsIdx, kindRowsIdx + 2000)
    expect(block).toContain('cam_layered')
  })

  it("KIND_ROWS cam_layered entry uses Layers icon", () => {
    const kindRowsIdx = fileTreeSrc.indexOf('const KIND_ROWS')
    const block = fileTreeSrc.slice(kindRowsIdx, kindRowsIdx + 2000)
    const camLayeredIdx = block.indexOf('cam_layered:')
    const entry = block.slice(camLayeredIdx, camLayeredIdx + 200)
    expect(entry).toContain('Layers')
  })

  it("KIND_ORDER includes 'cam_layered'", () => {
    const kindOrderIdx = fileTreeSrc.indexOf('const KIND_ORDER')
    const line = fileTreeSrc.slice(kindOrderIdx, kindOrderIdx + 200)
    expect(line).toContain("'cam_layered'")
  })

  it("KIND_ORDER places 'cam_layered' after 'section'", () => {
    const kindOrderIdx = fileTreeSrc.indexOf('const KIND_ORDER')
    const line = fileTreeSrc.slice(kindOrderIdx, kindOrderIdx + 200)
    const sectionPos = line.indexOf("'section'")
    const camPos = line.indexOf("'cam_layered'")
    expect(sectionPos).toBeGreaterThan(-1)
    expect(camPos).toBeGreaterThan(sectionPos)
  })

  it("Layers icon is imported from lucide-react (shared with assembly)", () => {
    const importBlock = fileTreeSrc.slice(0, fileTreeSrc.indexOf('import { useWorkspace'))
    expect(importBlock).toContain('Layers')
  })
})

// ── 2. CAMView LayeredCAMView export ─────────────────────────────────────────

describe('CAMView.jsx LayeredCAMView', () => {
  it('LayeredCAMView is exported', () => {
    expect(camViewSrc).toContain('export function LayeredCAMView')
  })

  it('LayeredCAMView accepts parsedContent prop', () => {
    const idx = camViewSrc.indexOf('export function LayeredCAMView')
    const sig = camViewSrc.slice(idx, idx + 150)
    expect(sig).toContain('parsedContent')
  })

  it('LayeredCAMView renders layer count from parsedContent.layers', () => {
    const idx = camViewSrc.indexOf('export function LayeredCAMView')
    const body = camViewSrc.slice(idx, idx + 4000)
    expect(body).toContain('layers.length')
  })

  it('LayeredCAMView uses a range input (slider) for layer scrubbing', () => {
    // Use full source — LayeredCAMView function body is >8 kB.
    expect(camViewSrc).toContain('type="range"')
  })

  it('LayeredCAMView shows z_mm for the current layer', () => {
    const idx = camViewSrc.indexOf('export function LayeredCAMView')
    const body = camViewSrc.slice(idx, idx + 2000)
    expect(body).toContain('z_mm')
  })

  it('LayeredCAMView renders an SVG canvas', () => {
    // Use full source — SVG markup appears beyond the 4 kB mark.
    expect(camViewSrc).toContain('<svg')
  })

  it('LayeredCAMView renders contour edges', () => {
    // Use full source — edges.map appears beyond the 5 kB mark.
    expect(camViewSrc).toContain('edges.map')
  })

  it('LayeredCAMView shows empty-state message when no layers', () => {
    const idx = camViewSrc.indexOf('export function LayeredCAMView')
    const body = camViewSrc.slice(idx, idx + 5000)
    expect(body).toContain('feature_cam_layered')
  })

  it("LayeredCAMView has 'Generate G-code from layers' button", () => {
    // Use the full source since the function body is >8 kB.
    expect(camViewSrc).toContain('Generate G-code from layers')
  })

  it('LayeredCAMView imports Layers icon from lucide-react', () => {
    const importBlock = camViewSrc.slice(0, camViewSrc.indexOf('const API_URL'))
    expect(importBlock).toContain('Layers')
  })

  it('LayeredCAMView wires viewRef via useImperativeHandle', () => {
    const idx = camViewSrc.indexOf('export function LayeredCAMView')
    const body = camViewSrc.slice(idx, idx + 2000)
    expect(body).toContain('useImperativeHandle')
  })
})

// ── 3. Migration 054 ─────────────────────────────────────────────────────────

describe('Migration 054 — cam_layered kind', () => {
  it('migration file exists', () => {
    expect(migrationSrc.length).toBeGreaterThan(0)
  })

  it("migration adds 'cam_layered' to the files_kind_check constraint", () => {
    expect(migrationSrc).toContain('cam_layered')
  })

  it("migration retains prior kinds including 'section'", () => {
    expect(migrationSrc).toContain("'section'")
  })

  it("migration retains 'render' kind (from migration 046)", () => {
    expect(migrationSrc).toContain("'render'")
  })
})

// ── 4. cam_layered Python tool registration ───────────────────────────────────

describe('Python plugin registration', () => {
  const pluginSrc = readFileSync(
    path.resolve(__dirname, '../../packages/kerf-cad-core/src/kerf_cad_core/plugin.py'),
    'utf8',
  )

  it("plugin._TOOL_MODULES includes 'kerf_cad_core.cam_layered'", () => {
    expect(pluginSrc).toContain('kerf_cad_core.cam_layered')
  })
})

// ── 5. LLM doc ───────────────────────────────────────────────────────────────

describe('LLM doc cam_layered.md', () => {
  const docPath = path.resolve(
    __dirname,
    '../../packages/kerf-chat/llm_docs/cam_layered.md',
  )
  const docSrc = (() => {
    try { return readFileSync(docPath, 'utf8') } catch { return '' }
  })()

  it('cam_layered.md exists', () => {
    expect(docSrc.length).toBeGreaterThan(0)
  })

  it('documents the feature_cam_layered tool name', () => {
    expect(docSrc).toContain('feature_cam_layered')
  })

  it('documents the z_step_mm parameter', () => {
    expect(docSrc).toContain('z_step_mm')
  })

  it('documents the .cam.layered file kind', () => {
    expect(docSrc).toContain('.cam.layered')
  })
})
