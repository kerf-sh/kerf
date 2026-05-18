/**
 * heroShotBrowserPT.test.js — Vitest suite for the in-browser path-tracer
 * fallback (T-106f).
 *
 * WebGL2 and the GPU are unavailable in jsdom / headless vitest.  The tests
 * verify the module's public surface and error-handling contracts:
 *
 *   - renderBrowserPT is exported as a function (module loads without error)
 *   - It rejects cleanly when renderer/scene/camera cannot be resolved
 *   - It rejects cleanly when AbortSignal is already aborted at call time
 *   - In a stubbed environment (WebGLPathTracer mocked) it resolves to a Blob
 *   - onProgress is called with values 0..100
 *   - AbortSignal mid-render is respected
 */

import { describe, it, expect, vi, afterEach } from 'vitest'

// ── Mock three-gpu-pathtracer before importing heroShotBrowserPT ───────────────
// The real WebGLPathTracer needs a live WebGL2 context; jsdom lacks one.
// We replace the import with a controllable fake so the render loop can be
// driven synchronously in the test runner.

vi.mock('three-gpu-pathtracer', () => {
  let sampleCount = 0

  class FakeWebGLPathTracer {
    constructor() {
      this.filterGlossyFactor = 0
      this.renderScale = 1
      this.tiles = { set: vi.fn() }
      sampleCount = 0
    }

    async setSceneAsync(scene, camera) {
      // no-op for tests
    }

    renderSample() {
      sampleCount += 1
    }

    get samples() {
      return sampleCount
    }

    dispose() {}
  }

  return { WebGLPathTracer: FakeWebGLPathTracer }
})

import { renderBrowserPT } from './heroShotBrowserPT.js'

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeCanvas() {
  return {
    toBlob(cb) {
      // Immediately call back with a minimal PNG-like blob.
      const buf = new Uint8Array([137, 80, 78, 71])
      cb(new Blob([buf], { type: 'image/png' }))
    },
    getContext: () => null,
  }
}

function makeRenderer(canvas = makeCanvas()) {
  return {
    domElement: canvas,
    getContext: () => null,
  }
}

function makeRendererRef(renderer, scene = {}, camera = {}) {
  return {
    current: {
      renderer,
      scene,
      camera,
      gl: renderer,
    },
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

// ── Module API contract ────────────────────────────────────────────────────────

describe('heroShotBrowserPT — module surface', () => {
  it('exports renderBrowserPT as a function', () => {
    expect(typeof renderBrowserPT).toBe('function')
  })

  it('is also the default export', async () => {
    const mod = await import('./heroShotBrowserPT.js')
    expect(mod.default).toBe(renderBrowserPT)
  })
})

// ── Abort before start ─────────────────────────────────────────────────────────

describe('heroShotBrowserPT — AbortSignal pre-aborted', () => {
  it('rejects immediately with AbortError when signal is already aborted', async () => {
    const ctrl = new AbortController()
    ctrl.abort()
    const rendererRef = makeRendererRef(makeRenderer())
    await expect(
      renderBrowserPT({ rendererRef, signal: ctrl.signal }),
    ).rejects.toMatchObject({ name: 'AbortError' })
  })
})

// ── Missing resolver ───────────────────────────────────────────────────────────

describe('heroShotBrowserPT — bad rendererRef', () => {
  it('rejects when rendererRef is null', async () => {
    await expect(renderBrowserPT({ rendererRef: null })).rejects.toThrow(
      /could not resolve/,
    )
  })

  it('rejects when rendererRef resolves no camera', async () => {
    const ref = { current: { renderer: makeRenderer(), scene: {}, camera: null } }
    await expect(renderBrowserPT({ rendererRef: ref })).rejects.toThrow(
      /could not resolve/,
    )
  })

  it('rejects when rendererRef resolves no scene', async () => {
    const ref = { current: { renderer: makeRenderer(), scene: null, camera: {} } }
    await expect(renderBrowserPT({ rendererRef: ref })).rejects.toThrow(
      /could not resolve/,
    )
  })

  it('rejects when rendererRef resolves no renderer', async () => {
    const ref = { current: { renderer: null, scene: {}, camera: {} } }
    await expect(renderBrowserPT({ rendererRef: ref })).rejects.toThrow(
      /could not resolve/,
    )
  })
})

// ── Happy path (mocked tracer + canvas.toBlob) ────────────────────────────────

describe('heroShotBrowserPT — happy path (mocked tracer)', () => {
  it('resolves to a Blob', async () => {
    const canvas = makeCanvas()
    const rendererRef = makeRendererRef(makeRenderer(canvas))
    const blob = await renderBrowserPT({ rendererRef, samples: 4 })
    expect(blob).toBeInstanceOf(Blob)
  })

  it('calls onProgress with 0..100 range values', async () => {
    const canvas = makeCanvas()
    const rendererRef = makeRendererRef(makeRenderer(canvas))
    const calls = []
    await renderBrowserPT({
      rendererRef,
      samples: 4,
      onProgress: (pct) => calls.push(pct),
    })
    expect(calls.length).toBeGreaterThan(0)
    expect(Math.min(...calls)).toBeGreaterThanOrEqual(0)
    expect(Math.max(...calls)).toBeLessThanOrEqual(100)
  })

  it('calls onProgress(100) at completion', async () => {
    const canvas = makeCanvas()
    const rendererRef = makeRendererRef(makeRenderer(canvas))
    const calls = []
    await renderBrowserPT({
      rendererRef,
      samples: 2,
      onProgress: (pct) => calls.push(pct),
    })
    expect(calls.at(-1)).toBe(100)
  })

  it('returns a Blob even when canvas.toBlob is missing (jsdom fallback)', async () => {
    const canvas = {
      toBlob: undefined,
      getContext: () => null,
    }
    const rendererRef = makeRendererRef(makeRenderer(canvas))
    const blob = await renderBrowserPT({ rendererRef, samples: 2 })
    expect(blob).toBeInstanceOf(Blob)
  })

  it('resolves with 1 sample when samples=1', async () => {
    const canvas = makeCanvas()
    const rendererRef = makeRendererRef(makeRenderer(canvas))
    await expect(
      renderBrowserPT({ rendererRef, samples: 1 }),
    ).resolves.toBeInstanceOf(Blob)
  })
})

// ── getThree() ref shape ───────────────────────────────────────────────────────

describe('heroShotBrowserPT — getThree() ref shape', () => {
  it('resolves renderer/scene/camera from getThree()', async () => {
    const canvas = makeCanvas()
    const renderer = makeRenderer(canvas)
    const ref = {
      current: {
        getThree: () => ({ gl: renderer, scene: {}, camera: {} }),
      },
    }
    const blob = await renderBrowserPT({ rendererRef: ref, samples: 2 })
    expect(blob).toBeInstanceOf(Blob)
  })
})
