// quadMeshView.test.js — Quad Remesher (Instant Meshes) feature
//
// No WASM required. The suite verifies:
//
//   1. FileTree.jsx: 'quadmesh' kind registered with Grid3x3 icon and
//      indigo colour; '.quadmesh' extension handled; kind appears in
//      KIND_ORDER and KIND_ROWS.
//
//   2. QuadMeshView.jsx: exported; accepts correct props; exposes
//      viewRef / snapshot; renders stats panel; wireframe legend present.
//
//   3. The consolidated baseline migration's files_kind_check constraint
//      includes 'quadmesh' (the per-kind migrations were folded 66->10).
//
//   4. Editor.jsx: isQuadMeshFile predicate present; QuadMeshView imported;
//      quadMeshFile const derived from currentFile.
//
//   5. FeatureView.jsx: quad_remesh op registered with target_feature_ref
//      and target_vertex_count fields.

import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// ── 0. Source readers ─────────────────────────────────────────────────────────

const fileTreeSrc = readFileSync(
  path.resolve(__dirname, '../components/FileTree.jsx'), 'utf8',
)

const quadMeshViewSrc = readFileSync(
  path.resolve(__dirname, '../components/QuadMeshView.jsx'), 'utf8',
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

const editorSrc = readFileSync(
  path.resolve(__dirname, '../routes/Editor.jsx'), 'utf8',
)

const featureViewSrc = readFileSync(
  path.resolve(__dirname, '../components/FeatureView.jsx'), 'utf8',
)

// ── 1. FileTree kind registration ─────────────────────────────────────────────

describe('FileTree.jsx quadmesh kind', () => {
  it("KindIcon handles kind 'quadmesh'", () => {
    expect(fileTreeSrc).toContain("kind === 'quadmesh'")
  })

  it("quadmesh KindIcon uses Grid3x3 component", () => {
    const idx = fileTreeSrc.indexOf("kind === 'quadmesh'")
    const block = fileTreeSrc.slice(idx, idx + 120)
    expect(block).toContain('Grid3x3')
  })

  it("quadmesh KindIcon uses indigo colour", () => {
    const idx = fileTreeSrc.indexOf("kind === 'quadmesh'")
    const block = fileTreeSrc.slice(idx, idx + 120)
    expect(block).toContain('indigo')
  })

  it("'.quadmesh' extension handled via KindIcon or KIND_ROWS", () => {
    expect(fileTreeSrc).toContain('quadmesh')
  })

  it("KIND_ROWS contains quadmesh entry", () => {
    const kindRowsIdx = fileTreeSrc.indexOf('const KIND_ROWS')
    const block = fileTreeSrc.slice(kindRowsIdx, kindRowsIdx + 4000)
    expect(block).toContain('quadmesh')
  })

  it("KIND_ROWS quadmesh entry uses Grid3x3 icon", () => {
    const kindRowsIdx = fileTreeSrc.indexOf('const KIND_ROWS')
    const block = fileTreeSrc.slice(kindRowsIdx, kindRowsIdx + 4000)
    const idx = block.indexOf('quadmesh:')
    const entry = block.slice(idx, idx + 200)
    expect(entry).toContain('Grid3x3')
  })

  it("KIND_ORDER includes 'quadmesh'", () => {
    const kindOrderIdx = fileTreeSrc.indexOf('const KIND_ORDER')
    const line = fileTreeSrc.slice(kindOrderIdx, kindOrderIdx + 400)
    expect(line).toContain("'quadmesh'")
  })

  it("KIND_ORDER places 'quadmesh' after 'plc_st'", () => {
    const kindOrderIdx = fileTreeSrc.indexOf('const KIND_ORDER')
    const line = fileTreeSrc.slice(kindOrderIdx, kindOrderIdx + 400)
    const plcPos    = line.indexOf("'plc_st'")
    const quadPos   = line.indexOf("'quadmesh'")
    expect(plcPos).toBeGreaterThan(-1)
    expect(quadPos).toBeGreaterThan(plcPos)
  })

  it("Grid3x3 icon is imported from lucide-react", () => {
    const importBlock = fileTreeSrc.slice(0, fileTreeSrc.indexOf('import { useWorkspace'))
    expect(importBlock).toContain('Grid3x3')
  })
})

// ── 2. QuadMeshView.jsx ───────────────────────────────────────────────────────

describe('QuadMeshView.jsx', () => {
  it('exports a default function QuadMeshView', () => {
    expect(quadMeshViewSrc).toContain('export default function QuadMeshView')
  })

  it('accepts content prop', () => {
    const sigIdx = quadMeshViewSrc.indexOf('export default function QuadMeshView')
    const sig = quadMeshViewSrc.slice(sigIdx, sigIdx + 200)
    expect(sig).toContain('content')
  })

  it('accepts fileName prop', () => {
    const sigIdx = quadMeshViewSrc.indexOf('export default function QuadMeshView')
    const sig = quadMeshViewSrc.slice(sigIdx, sigIdx + 200)
    expect(sig).toContain('fileName')
  })

  it('accepts viewRef prop for snapshot', () => {
    const sigIdx = quadMeshViewSrc.indexOf('export default function QuadMeshView')
    const sig = quadMeshViewSrc.slice(sigIdx, sigIdx + 200)
    expect(sig).toContain('viewRef')
  })

  it('uses useImperativeHandle for snapshot', () => {
    expect(quadMeshViewSrc).toContain('useImperativeHandle')
  })

  it('snapshot method delegates to snapshotCanvas', () => {
    expect(quadMeshViewSrc).toContain('snapshotCanvas')
  })

  it('renders wireframe quad overlay (gold/kerf-300)', () => {
    // Gold quad wireframe color constant
    expect(quadMeshViewSrc).toContain('0xffd633')
  })

  it('renders wireframe triangle overlay (amber)', () => {
    // Amber triangle wireframe color constant
    expect(quadMeshViewSrc).toContain('0xf59e0b')
  })

  it('imports three.js dynamically', () => {
    expect(quadMeshViewSrc).toContain("'three'")
  })

  it('imports OrbitControls', () => {
    expect(quadMeshViewSrc).toContain('OrbitControls')
  })

  it('renders stats panel with vertex_count', () => {
    expect(quadMeshViewSrc).toContain('vertex_count')
  })

  it('renders stats panel with quad_count', () => {
    expect(quadMeshViewSrc).toContain('quad_count')
  })

  it('renders stats panel with tri_count', () => {
    expect(quadMeshViewSrc).toContain('tri_count')
  })

  it('renders elapsed_s in stats panel', () => {
    expect(quadMeshViewSrc).toContain('elapsed_s')
  })

  it('renders wireframe legend for quads and triangles', () => {
    expect(quadMeshViewSrc).toContain('Quads')
    expect(quadMeshViewSrc).toContain('Triangles')
  })

  it('imports Grid3x3 icon from lucide-react', () => {
    const importBlock = quadMeshViewSrc.slice(0, quadMeshViewSrc.indexOf('export default'))
    expect(importBlock).toContain('Grid3x3')
  })

  it('imports snapshotHelpers', () => {
    const importBlock = quadMeshViewSrc.slice(0, quadMeshViewSrc.indexOf('export default'))
    expect(importBlock).toContain('snapshotHelpers')
  })

  it('renders error banner when file is empty', () => {
    expect(quadMeshViewSrc).toContain('Empty file')
  })

  it('calls parseQuadMesh on content', () => {
    expect(quadMeshViewSrc).toContain('parseQuadMesh')
  })
})

// ── 3. Migration 058 ──────────────────────────────────────────────────────────

describe('Migration 058 — quadmesh kind', () => {
  it('migration file exists', () => {
    expect(migrationSrc.length).toBeGreaterThan(0)
  })

  it("migration adds 'quadmesh' to the files_kind_check constraint", () => {
    expect(migrationSrc).toContain('quadmesh')
  })

  it('migration drops the old constraint before adding the new one', () => {
    expect(migrationSrc).toContain('drop constraint if exists files_kind_check')
  })

  it("migration retains prior kinds including 'plc_st'", () => {
    expect(migrationSrc).toContain("'plc_st'")
  })

  it("migration retains 'tool' kind", () => {
    expect(migrationSrc).toContain("'tool'")
  })

  it("migration retains 'mesh' kind (from migration 044)", () => {
    expect(migrationSrc).toContain("'mesh'")
  })

  it("migration retains 'section' kind (from migration 053)", () => {
    expect(migrationSrc).toContain("'section'")
  })
})

// ── 4. Editor.jsx dispatch ────────────────────────────────────────────────────

describe('Editor.jsx quadmesh dispatch', () => {
  it('imports QuadMeshView', () => {
    const importBlock = editorSrc.slice(0, editorSrc.indexOf('export default function Editor'))
    expect(importBlock).toContain('QuadMeshView')
  })

  it('has isQuadMeshFile predicate', () => {
    expect(editorSrc).toContain('isQuadMeshFile')
  })

  it('isQuadMeshFile checks quadmesh kind', () => {
    const idx = editorSrc.indexOf('isQuadMeshFile')
    const block = editorSrc.slice(idx, idx + 300)
    expect(block).toContain("'quadmesh'")
  })

  it('isQuadMeshFile checks .quadmesh extension', () => {
    const idx = editorSrc.indexOf('isQuadMeshFile')
    const block = editorSrc.slice(idx, idx + 300)
    expect(block).toContain('.quadmesh')
  })

  it('derives quadMeshFile from currentFile', () => {
    expect(editorSrc).toContain('quadMeshFile')
  })

  it('renders QuadMeshView for quadMeshFile', () => {
    expect(editorSrc).toContain('<QuadMeshView')
  })

  it('QuadMeshView receives viewRef', () => {
    const idx = editorSrc.indexOf('<QuadMeshView')
    const block = editorSrc.slice(idx, idx + 300)
    expect(block).toContain('viewRef')
  })

  it('QuadMeshView receives content', () => {
    const idx = editorSrc.indexOf('<QuadMeshView')
    const block = editorSrc.slice(idx, idx + 300)
    expect(block).toContain('content')
  })
})

// ── 5. FeatureView.jsx quad_remesh entry ──────────────────────────────────────

describe('FeatureView.jsx quad_remesh op', () => {
  it("FEATURE_KINDS contains op 'quad_remesh'", () => {
    expect(featureViewSrc).toContain("op: 'quad_remesh'")
  })

  it('quad_remesh uses Grid3x3 icon', () => {
    const idx = featureViewSrc.indexOf("op: 'quad_remesh'")
    const block = featureViewSrc.slice(idx, idx + 500)
    expect(block).toContain('Grid3x3')
  })

  it('quad_remesh defaults include target_vertex_count 5000', () => {
    const idx = featureViewSrc.indexOf("op: 'quad_remesh'")
    const block = featureViewSrc.slice(idx, idx + 500)
    expect(block).toContain('target_vertex_count')
    expect(block).toContain('5000')
  })

  it('quad_remesh defaults include smoothness_iters', () => {
    const idx = featureViewSrc.indexOf("op: 'quad_remesh'")
    const block = featureViewSrc.slice(idx, idx + 500)
    expect(block).toContain('smoothness_iters')
  })

  it('quad_remesh has target_feature_ref field (feature_picker)', () => {
    const idx = featureViewSrc.indexOf("op: 'quad_remesh'")
    const block = featureViewSrc.slice(idx, idx + 600)
    expect(block).toContain('target_feature_ref')
    expect(block).toContain('feature_picker')
  })

  it('Grid3x3 is imported from lucide-react in FeatureView', () => {
    const importBlock = featureViewSrc.slice(0, featureViewSrc.indexOf('export default function FeatureView'))
    expect(importBlock).toContain('Grid3x3')
  })
})
