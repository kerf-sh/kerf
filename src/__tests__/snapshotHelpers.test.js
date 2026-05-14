// snapshotHelpers tests — coverage for the canvas + SVG capture helpers
// that power per-file-kind thumbnail uploads.
//
// vitest runs node-only here (no jsdom), so we install the minimum
// browser DOM surface the helpers touch:
//   * document.createElement('canvas') → an offscreen canvas stub with
//     a 2d context + toBlob
//   * XMLSerializer / Blob / URL.createObjectURL
//   * new Image() returning a fake that fires onload after src is set
//
// The shape of the test is: hand the helper a fake canvas/SVG, assert
// the returned Blob has the right type — or null on intentionally broken
// input.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { snapshotCanvas, snapshotSvg } from '../lib/snapshotHelpers.js'

// ----- DOM shim -----
function makeFakeContext() {
  return {
    fillStyle: '',
    fillRect: vi.fn(),
    drawImage: vi.fn(),
  }
}

function makeFakeCanvas({ width = 100, height = 100, blobType = 'image/jpeg' } = {}) {
  return {
    width,
    height,
    getContext: vi.fn(() => makeFakeContext()),
    toBlob: vi.fn((cb, type) => {
      // Mimic the spec: pass a Blob with the requested type, async.
      setTimeout(() => cb({ size: 42, type: type || blobType }), 0)
    }),
  }
}

function installDom({
  createCanvas = () => makeFakeCanvas({ width: 512, height: 512 }),
  imageWillLoad = true,
} = {}) {
  globalThis.document = {
    createElement: vi.fn((tag) => {
      if (tag === 'canvas') return createCanvas()
      return {}
    }),
  }
  globalThis.Blob = class FakeBlob {
    constructor(parts, opts) {
      this.parts = parts
      this.type = opts?.type || ''
      this.size = parts.reduce((n, p) => n + (p?.length || 0), 0)
    }
  }
  globalThis.URL = {
    createObjectURL: vi.fn(() => 'blob:fake'),
    revokeObjectURL: vi.fn(),
  }
  globalThis.XMLSerializer = class FakeXMLSerializer {
    serializeToString(node) {
      // Surface whatever the caller stuck on the clone — good enough to
      // assert serialization happens, and lets us forge a parse failure
      // by handing the helper a node that serializes to '' (handled
      // separately by returning null).
      return node?.__xml || '<svg/>'
    }
  }
  // The Image global resolves onload synchronously on the next tick so
  // tests can `await` it without timing out.
  globalThis.Image = class FakeImage {
    constructor() {
      this.naturalWidth = 200
      this.naturalHeight = 200
      this._src = ''
    }
    set src(v) {
      this._src = v
      setTimeout(() => {
        if (imageWillLoad) this.onload?.()
        else this.onerror?.()
      }, 0)
    }
    get src() { return this._src }
  }
}

function uninstallDom() {
  delete globalThis.document
  delete globalThis.Blob
  delete globalThis.URL
  delete globalThis.XMLSerializer
  delete globalThis.Image
}

// ----- snapshotCanvas -----

describe('snapshotCanvas', () => {
  beforeEach(() => installDom())
  afterEach(() => uninstallDom())

  it('returns a JPEG blob from a healthy canvas', async () => {
    const src = makeFakeCanvas({ width: 800, height: 600 })
    const blob = await snapshotCanvas(src, { size: 256, quality: 0.7 })
    expect(blob).not.toBeNull()
    expect(blob.type).toBe('image/jpeg')
  })

  it('returns null when canvas has zero dimensions', async () => {
    const src = makeFakeCanvas({ width: 0, height: 0 })
    const blob = await snapshotCanvas(src)
    expect(blob).toBeNull()
  })

  it('returns null when canvas is missing entirely', async () => {
    expect(await snapshotCanvas(null)).toBeNull()
    expect(await snapshotCanvas(undefined)).toBeNull()
  })

  it('returns null when 2d context is unavailable', async () => {
    // Wire a fresh document.createElement that hands back a canvas whose
    // getContext returns null — simulates a headless environment without
    // 2d support, or a user-disabled canvas accel.
    uninstallDom()
    installDom({
      createCanvas: () => ({
        width: 512,
        height: 512,
        getContext: vi.fn(() => null),
        toBlob: vi.fn(),
      }),
    })
    const src = makeFakeCanvas({ width: 800, height: 600 })
    expect(await snapshotCanvas(src)).toBeNull()
  })

  it('center-crops a wide canvas to a square', async () => {
    const src = makeFakeCanvas({ width: 1000, height: 400 })
    let captured
    src._ctx = null
    const offCanvas = makeFakeCanvas({ width: 512, height: 512 })
    const offCtx = makeFakeContext()
    offCanvas.getContext = vi.fn(() => offCtx)
    uninstallDom()
    installDom({ createCanvas: () => offCanvas })
    await snapshotCanvas(src, { size: 512 })
    // drawImage(canvas, sx, sy, side, side, 0, 0, size, size)
    expect(offCtx.drawImage).toHaveBeenCalledTimes(1)
    const args = offCtx.drawImage.mock.calls[0]
    // side = min(1000, 400) = 400; sx = (1000-400)/2 = 300; sy = 0
    expect(args[1]).toBe(300)
    expect(args[2]).toBe(0)
    expect(args[3]).toBe(400)
    expect(args[4]).toBe(400)
  })
})

// ----- snapshotSvg -----

describe('snapshotSvg', () => {
  beforeEach(() => installDom())
  afterEach(() => uninstallDom())

  function makeFakeSvg({ width, height, viewBox, attrs = {} } = {}) {
    const attrMap = {}
    if (width != null) attrMap.width = String(width)
    if (height != null) attrMap.height = String(height)
    if (viewBox) attrMap.viewBox = viewBox
    Object.assign(attrMap, attrs)
    return {
      getAttribute: (k) => attrMap[k] ?? null,
      setAttribute: (k, v) => { attrMap[k] = v },
      cloneNode: () => makeFakeSvg({ width, height, viewBox, attrs: { ...attrMap, __xml: '<svg/>' } }),
      getBoundingClientRect: () => ({ width: width || 0, height: height || 0 }),
    }
  }

  it('returns a JPEG blob from an SVG with explicit width/height', async () => {
    const svg = makeFakeSvg({ width: 200, height: 200 })
    const blob = await snapshotSvg(svg, { size: 128, quality: 0.7 })
    expect(blob).not.toBeNull()
    expect(blob.type).toBe('image/jpeg')
  })

  it('falls back to viewBox when width/height attrs are missing', async () => {
    const svg = makeFakeSvg({ viewBox: '0 0 300 150' })
    const blob = await snapshotSvg(svg, { size: 128 })
    expect(blob).not.toBeNull()
    expect(blob.type).toBe('image/jpeg')
  })

  it('returns null when SVG has no dimensions anywhere', async () => {
    const svg = makeFakeSvg({})
    expect(await snapshotSvg(svg)).toBeNull()
  })

  it('returns null when the source is missing', async () => {
    expect(await snapshotSvg(null)).toBeNull()
    expect(await snapshotSvg(undefined)).toBeNull()
  })

  it('returns null when the SVG fails to decode as an image', async () => {
    uninstallDom()
    installDom({ imageWillLoad: false })
    const svg = makeFakeSvg({ width: 200, height: 200 })
    expect(await snapshotSvg(svg)).toBeNull()
  })

  it('rejects a non-svg-shaped object (no cloneNode)', async () => {
    expect(await snapshotSvg({})).toBeNull()
  })
})
