// Coverage for the pure paths in src/lib/exporters.js — filename sanitisation,
// the FORMATS table, and the JSCAD-JSON serialiser. We deliberately avoid the
// THREE.js exporter paths (STL/OBJ/PLY/GLTF/3MF) since those need a configured
// renderer and are integration-tested in the running app.
import { describe, it, expect } from 'vitest'
import { FORMATS, sanitizeFilename, exportParts, downloadBlob } from '../lib/exporters.js'

describe('sanitizeFilename', () => {
  it('replaces unsafe characters with underscores', () => {
    expect(sanitizeFilename('a/b\\c?d%e*f:g|h"i<j>k')).toBe('a_b_c_d_e_f_g_h_i_j_k')
  })

  it('collapses whitespace runs and consecutive underscores', () => {
    expect(sanitizeFilename('hello   world')).toBe('hello_world')
    expect(sanitizeFilename('a___b')).toBe('a_b')
  })

  it('trims leading and trailing underscores', () => {
    expect(sanitizeFilename('___edge___')).toBe('edge')
  })

  it('falls back to "untitled" for empty / all-stripped inputs', () => {
    expect(sanitizeFilename('')).toBe('untitled')
    expect(sanitizeFilename(null)).toBe('untitled')
    expect(sanitizeFilename('   ')).toBe('untitled') // collapses to '_' then strip → ''
  })
})

describe('FORMATS table', () => {
  it('exposes the eight expected formats', () => {
    const ids = FORMATS.map((f) => f.id)
    expect(ids).toEqual([
      'stl-binary', 'stl-ascii', 'obj', 'glb', 'gltf', 'ply', '3mf', 'jscad-json',
    ])
  })

  it('every format has a label + extension', () => {
    for (const fmt of FORMATS) {
      expect(typeof fmt.label).toBe('string')
      expect(fmt.label.length).toBeGreaterThan(0)
      expect(typeof fmt.ext).toBe('string')
      expect(fmt.ext.length).toBeGreaterThan(0)
    }
  })

  it('only jscad-json is jscadOnly', () => {
    const jscadOnly = FORMATS.filter((f) => f.jscadOnly).map((f) => f.id)
    expect(jscadOnly).toEqual(['jscad-json'])
  })
})

describe('exportParts (JSCAD JSON path)', () => {
  // Build a tiny JSCAD-shaped Geom3 with one triangular polygon.
  const triPart = {
    id: 'tri',
    color: 0xff0000,
    geom: { polygons: [{ vertices: [[0, 0, 0], [1, 0, 0], [0, 1, 0]] }] },
  }

  it('throws Unknown export format for an unknown id', async () => {
    await expect(exportParts([triPart], 'nope')).rejects.toThrow(/Unknown export format/)
  })

  it('throws when no parts are provided', async () => {
    await expect(exportParts([], 'jscad-json')).rejects.toThrow(/No parts to export/)
  })

  it('serialises a Geom3 part to JSCAD JSON with sanitised filename', async () => {
    const { blob, filename } = await exportParts([triPart], 'jscad-json', {
      baseName: 'My Project.jscad',
    })
    expect(filename).toBe('My_Project.json')
    const text = await blob.text()
    const parsed = JSON.parse(text)
    expect(parsed.format).toBe('kerf-jscad-json')
    expect(parsed.version).toBe(1)
    expect(parsed.parts).toHaveLength(1)
    expect(parsed.parts[0].id).toBe('tri')
    expect(parsed.parts[0].color).toBe(0xff0000)
    expect(parsed.parts[0].polygons[0].vertices).toEqual([[0, 0, 0], [1, 0, 0], [0, 1, 0]])
  })

  it('appends the singlePartId to the filename when provided', async () => {
    const { filename } = await exportParts([triPart], 'jscad-json', {
      baseName: 'proj',
      singlePartId: 'left/wall', // contains an unsafe slash
    })
    expect(filename).toBe('proj-left_wall.json')
  })

  it('refuses to JSCAD-serialise a non-Geom3 (BufferGeometry-only) part', async () => {
    const stepPart = { id: 'step', geom: { isBufferGeometry: true } }
    await expect(exportParts([stepPart], 'jscad-json')).rejects.toThrow(/not a JSCAD Geom3/)
  })
})

describe('downloadBlob (smoke)', () => {
  it('is exported as a function', () => {
    // We don't invoke it — it requires document/URL.createObjectURL — but
    // we want a regression alarm if the public surface is renamed.
    expect(typeof downloadBlob).toBe('function')
  })
})
