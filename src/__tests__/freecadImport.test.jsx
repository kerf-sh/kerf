// freecadImport.test.jsx — T9 frontend FreeCAD import coverage.
//
// Covers:
//   1. isFCStdFile() extension matching (case-insensitive, non-.FCStd rejected)
//   2. api.importFreecadProject stub — always rejects with T7-pending error
//   3. T7 hook identifier: the stub error.code === 'FREECAD_T7_PENDING' so T7
//      can be detected cleanly when the real endpoint ships.
//
// React component render tests are omitted; @testing-library/react is not
// installed in this project. Component behaviour is covered by the pure-function
// tests here and the stub/error-code contract that FreeCADImportDialog relies on.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { isFCStdFile } from '../components/FreeCADImport.jsx'

// ---- Mock auth store so FreeCADImport can import api.js without crashing ----
vi.mock('../store/auth.js', () => ({
  useAuth: { getState: () => ({ accessToken: 'tok', refreshToken: null }) },
}))

// ---- 1. isFCStdFile extension matching ----------------------------------------

describe('isFCStdFile', () => {
  it('matches .FCStd extension', () => {
    expect(isFCStdFile('bracket.FCStd')).toBe(true)
  })

  it('matches lowercase .fcstd', () => {
    expect(isFCStdFile('bolt.fcstd')).toBe(true)
  })

  it('matches mixed case .FcStD', () => {
    expect(isFCStdFile('gear.FcStD')).toBe(true)
  })

  it('rejects .step files', () => {
    expect(isFCStdFile('model.step')).toBe(false)
  })

  it('rejects .FCStd.zip (double-extension)', () => {
    expect(isFCStdFile('archive.FCStd.zip')).toBe(false)
  })

  it('rejects empty string', () => {
    expect(isFCStdFile('')).toBe(false)
  })

  it('rejects .kicad_sch', () => {
    expect(isFCStdFile('schematic.kicad_sch')).toBe(false)
  })

  it('accepts a File object whose name ends in .FCStd', () => {
    const f = new File([], 'assembly.FCStd', { type: 'application/zip' })
    expect(isFCStdFile(f)).toBe(true)
  })

  it('rejects a File object whose name does not end in .FCStd', () => {
    const f = new File([], 'schematic.kicad_sch')
    expect(isFCStdFile(f)).toBe(false)
  })
})

// ---- 2. api.importFreecadProject — real endpoint contract --------------------
//
// FreeCAD import shipped (T7/T-142): importFreecadProject now POSTs to
// /api/projects/:id/imports/freecad with { file_blob_id, import_folder,
// mode }. These tests pin that wire contract (the FreeCADImportDialog
// depends on the URL, method, and body shape — and on the opts defaults).

describe('api.importFreecadProject — real endpoint', () => {
  let api
  let lastFetch

  beforeEach(async () => {
    vi.resetModules()
    lastFetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ created_file: { id: 'f1' }, stats: {} }),
    }))
    globalThis.fetch = lastFetch
    const mod = await import('../lib/api.js')
    api = mod.api
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete globalThis.fetch
  })

  function fetchCall() {
    expect(lastFetch).toHaveBeenCalledTimes(1)
    const [url, init] = lastFetch.mock.calls[0]
    return { url, init, body: JSON.parse(init.body) }
  }

  it('POSTs to the project freecad-import endpoint', async () => {
    await api.importFreecadProject('proj-1', 'blob-1')
    const { url, init } = fetchCall()
    expect(url).toContain('/api/projects/proj-1/imports/freecad')
    expect(init.method).toBe('POST')
  })

  it('sends file_blob_id and the documented opts defaults', async () => {
    await api.importFreecadProject('proj-1', 'blob-1')
    const { body } = fetchCall()
    expect(body).toEqual({
      file_blob_id: 'blob-1',
      import_folder: '/freecad_import',
      mode: 'project',
    })
  })

  it('honours importFolder / mode overrides from opts', async () => {
    await api.importFreecadProject('proj-1', 'blob-1', {
      importFolder: '/custom',
      mode: 'assembly',
    })
    const { body } = fetchCall()
    expect(body.import_folder).toBe('/custom')
    expect(body.mode).toBe('assembly')
  })

  it('resolves with the parsed JSON response', async () => {
    const res = await api.importFreecadProject('proj-1', 'blob-1')
    expect(res).toEqual({ created_file: { id: 'f1' }, stats: {} })
  })

  it('rejects when the server returns a non-OK status', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 422,
      statusText: 'Unprocessable',
      text: async () => JSON.stringify({ error: 'bad fcstd' }),
    }))
    await expect(
      api.importFreecadProject('proj-1', 'blob-1'),
    ).rejects.toThrow(/bad fcstd/)
  })
})
