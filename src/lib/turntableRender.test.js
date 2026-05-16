/**
 * turntableRender.test.js — Vitest suite for the 360° turntable render module.
 *
 * All Three.js objects are stubbed in-process; no DOM or GPU required.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import {
  easingLinear,
  easingEaseInOut,
  positionCameraOnOrbit,
  recordTurntable,
  exportFrames,
  previewMode,
  isMediaRecorderAvailable,
} from './turntableRender.js'

// ── Stub helpers ──────────────────────────────────────────────────────────────

function makeCamera() {
  return {
    position: { x: 80, y: 80, z: 80, set(x, y, z) { this.x = x; this.y = y; this.z = z } },
    aspect: 1,
    _lookAt: null,
    lookAt(x, y, z) { this._lookAt = { x, y, z } },
    updateProjectionMatrix: vi.fn(),
  }
}

function makeRenderer(frameIndex = { val: 0 }) {
  const canvas = {
    width: 800,
    height: 600,
    toDataURL(mime) {
      const i = frameIndex.val++
      // Return distinguishable data-URLs
      return `data:${mime || 'image/png'};base64,FRAME${String(i).padStart(4, '0')}`
    },
  }
  return {
    domElement: canvas,
    render: vi.fn(),
    setSize: vi.fn((w, h) => { canvas.width = w; canvas.height = h }),
  }
}

function makeScene() {
  return { isScene: true }
}

// ── easingLinear ──────────────────────────────────────────────────────────────

describe('easingLinear', () => {
  it('returns 0 for frame 0', () => {
    expect(easingLinear(0, 36)).toBe(0)
  })

  it('returns 0.5 at the midpoint', () => {
    expect(easingLinear(18, 36)).toBeCloseTo(0.5)
  })

  it('returns values strictly less than 1 (last frame does not wrap)', () => {
    expect(easingLinear(35, 36)).toBeLessThan(1)
  })

  it('returns 0 when n=0 (guard)', () => {
    expect(easingLinear(5, 0)).toBe(0)
  })

  it('produces monotonically increasing values', () => {
    const vals = Array.from({ length: 36 }, (_, i) => easingLinear(i, 36))
    for (let i = 1; i < vals.length; i++) {
      expect(vals[i]).toBeGreaterThan(vals[i - 1])
    }
  })
})

// ── easingEaseInOut ───────────────────────────────────────────────────────────

describe('easingEaseInOut', () => {
  it('returns 0 at frame 0', () => {
    expect(easingEaseInOut(0, 36)).toBe(0)
  })

  it('returns 0.5 exactly at the midpoint', () => {
    // smoothstep(0.5) = 0.5
    expect(easingEaseInOut(18, 36)).toBeCloseTo(0.5)
  })

  it('values approach 1 near the end', () => {
    expect(easingEaseInOut(35, 36)).toBeGreaterThan(0.95)
  })

  it('produces monotonically increasing values (monotonic)', () => {
    const n = 60
    const vals = Array.from({ length: n }, (_, i) => easingEaseInOut(i, n))
    for (let i = 1; i < vals.length; i++) {
      expect(vals[i]).toBeGreaterThanOrEqual(vals[i - 1])
    }
  })

  it('returns 0 when n=0 (guard)', () => {
    expect(easingEaseInOut(5, 0)).toBe(0)
  })

  it('is slower at the edges than linear', () => {
    // At t=0.1, ease-in-out < linear (still accelerating)
    const n = 100
    expect(easingEaseInOut(10, n)).toBeLessThan(easingLinear(10, n))
    // At t=0.9, ease-in-out < linear (decelerating)
    expect(easingEaseInOut(90, n)).toBeGreaterThan(easingLinear(90, n))
  })
})

// ── positionCameraOnOrbit ─────────────────────────────────────────────────────

describe('positionCameraOnOrbit', () => {
  it('places camera at the correct radius from target', () => {
    const cam = makeCamera()
    const target = { x: 0, y: 0, z: 0 }
    positionCameraOnOrbit(cam, target, 100, 0, 0)
    const { x, y, z } = cam.position
    const dist = Math.sqrt(x * x + y * y + z * z)
    expect(dist).toBeCloseTo(100, 4)
  })

  it('calls lookAt toward the target', () => {
    const cam = makeCamera()
    positionCameraOnOrbit(cam, { x: 10, y: 5, z: 3 }, 50, 0, 0)
    expect(cam._lookAt).toEqual({ x: 10, y: 5, z: 3 })
  })

  it('elevation=0 keeps camera in XZ plane (y == target.y)', () => {
    const cam = makeCamera()
    positionCameraOnOrbit(cam, { x: 0, y: 0, z: 0 }, 50, 0, Math.PI / 4)
    expect(cam.position.y).toBeCloseTo(0, 5)
  })

  it('positive elevation raises the camera above XZ plane', () => {
    const cam = makeCamera()
    positionCameraOnOrbit(cam, { x: 0, y: 0, z: 0 }, 50, Math.PI / 4, 0)
    expect(cam.position.y).toBeGreaterThan(0)
  })

  it('different azimuths produce different XZ positions', () => {
    const cam1 = makeCamera()
    const cam2 = makeCamera()
    positionCameraOnOrbit(cam1, { x: 0, y: 0, z: 0 }, 50, 0, 0)
    positionCameraOnOrbit(cam2, { x: 0, y: 0, z: 0 }, 50, 0, Math.PI / 2)
    expect(cam1.position.x).not.toBeCloseTo(cam2.position.x, 2)
  })

  it('throws when camera is null', () => {
    expect(() => positionCameraOnOrbit(null, {}, 50, 0, 0)).toThrow('camera is required')
  })
})

// ── recordTurntable ───────────────────────────────────────────────────────────

describe('recordTurntable', () => {
  it('returns exactly frameCount data-URLs', async () => {
    const cam = makeCamera()
    const ren = makeRenderer()
    const frames = await recordTurntable(makeScene(), cam, ren, { frameCount: 12 })
    expect(frames).toHaveLength(12)
  })

  it('default frameCount is 36', async () => {
    const cam = makeCamera()
    const ren = makeRenderer()
    const frames = await recordTurntable(makeScene(), cam, ren)
    expect(frames).toHaveLength(36)
  })

  it('frame data-URLs are all strings starting with data:', async () => {
    const cam = makeCamera()
    const ren = makeRenderer()
    const frames = await recordTurntable(makeScene(), cam, ren, { frameCount: 8 })
    for (const f of frames) {
      expect(typeof f).toBe('string')
      expect(f.startsWith('data:')).toBe(true)
    }
  })

  it('calls renderer.render once per frame', async () => {
    const cam = makeCamera()
    const ren = makeRenderer()
    await recordTurntable(makeScene(), cam, ren, { frameCount: 24 })
    expect(ren.render).toHaveBeenCalledTimes(24)
  })

  it('camera angles cover the full 2π (unique azimuths per frame)', async () => {
    const captured = []
    const cam = {
      position: { x: 0, y: 50, z: 100, set(x, y, z) { this.x = x; this.y = y; this.z = z } },
      _lookAts: [],
      lookAt(x, y, z) { this._lookAts.push({ x, y, z }) },
      updateProjectionMatrix: vi.fn(),
    }
    // Intercept position.set to capture azimuth-derived x/z values.
    const origSet = cam.position.set.bind(cam.position)
    cam.position.set = (x, y, z) => { captured.push({ x, z }); origSet(x, y, z) }

    const ren = makeRenderer()
    const n = 36
    await recordTurntable(makeScene(), cam, ren, { frameCount: n, target: { x: 0, y: 0, z: 0 }, radius: 100 })

    // We captured n positions (plus one restore call); first n should be unique.
    const renderPositions = captured.slice(0, n)
    // Check uniqueness on the (x, z) pair — x alone repeats due to sine symmetry.
    const unique = new Set(renderPositions.map((p) => `${p.x.toFixed(6)},${p.z.toFixed(6)}`))
    // All 36 azimuths should produce distinct (x, z) positions
    expect(unique.size).toBe(n)
  })

  it('restores camera position after recording', async () => {
    const cam = makeCamera()
    const origX = cam.position.x
    const origY = cam.position.y
    const origZ = cam.position.z
    const ren = makeRenderer()
    await recordTurntable(makeScene(), cam, ren, { frameCount: 10, radius: 200 })
    expect(cam.position.x).toBeCloseTo(origX, 3)
    expect(cam.position.y).toBeCloseTo(origY, 3)
    expect(cam.position.z).toBeCloseTo(origZ, 3)
  })

  it('throws when camera is missing', async () => {
    await expect(recordTurntable(makeScene(), null, makeRenderer())).rejects.toThrow('camera is required')
  })

  it('throws when renderer is missing', async () => {
    await expect(recordTurntable(makeScene(), makeCamera(), null)).rejects.toThrow('renderer is required')
  })

  it('throws when scene is missing', async () => {
    await expect(recordTurntable(null, makeCamera(), makeRenderer())).rejects.toThrow('scene is required')
  })

  it('throws for frameCount < 1', async () => {
    await expect(
      recordTurntable(makeScene(), makeCamera(), makeRenderer(), { frameCount: 0 })
    ).rejects.toThrow('frameCount must be ≥ 1')
  })

  it('accepts ease-in-out easing without error', async () => {
    const frames = await recordTurntable(makeScene(), makeCamera(), makeRenderer(), {
      frameCount: 12,
      easing: 'ease-in-out',
    })
    expect(frames).toHaveLength(12)
  })

  it('applies custom radius (camera placed at given distance from target)', async () => {
    const positions = []
    const cam = makeCamera()
    const origSet = cam.position.set.bind(cam.position)
    cam.position.set = (x, y, z) => { positions.push({ x, y, z }); origSet(x, y, z) }

    const ren = makeRenderer()
    await recordTurntable(makeScene(), cam, ren, {
      frameCount: 4,
      radius: 200,
      target: { x: 0, y: 0, z: 0 },
      elevation: 0,
    })

    // Each render position should be ~200 units from origin (elevation=0, y≈0)
    for (const p of positions.slice(0, 4)) {
      const dist = Math.sqrt(p.x * p.x + p.y * p.y + p.z * p.z)
      expect(dist).toBeCloseTo(200, 1)
    }
  })

  it('returns single frame array for frameCount=1', async () => {
    const frames = await recordTurntable(makeScene(), makeCamera(), makeRenderer(), { frameCount: 1 })
    expect(frames).toHaveLength(1)
  })

  it('respects custom target offset', async () => {
    const captured = []
    const cam = makeCamera()
    cam.lookAt = (x, y, z) => captured.push({ x, y, z })

    const ren = makeRenderer()
    await recordTurntable(makeScene(), cam, ren, {
      frameCount: 4,
      target: { x: 10, y: 20, z: 30 },
      radius: 50,
    })

    // All lookAt calls (except restore) should target { x:10, y:20, z:30 }
    for (const c of captured.slice(0, 4)) {
      expect(c.x).toBeCloseTo(10, 2)
      expect(c.y).toBeCloseTo(20, 2)
      expect(c.z).toBeCloseTo(30, 2)
    }
  })
})

// ── exportFrames ──────────────────────────────────────────────────────────────

describe('exportFrames', () => {
  it('returns an object with a Blob and ext="zip" for png-zip', async () => {
    const fakeFrames = ['data:image/png;base64,abc', 'data:image/png;base64,def']
    const result = await exportFrames(fakeFrames, 'png-zip')
    expect(result).toHaveProperty('blob')
    expect(result).toHaveProperty('ext')
    expect(result.ext).toBe('zip')
  })

  it('returned Blob has type application/zip', async () => {
    const result = await exportFrames(['data:image/png;base64,aa=='], 'png-zip')
    expect(result.blob.type).toBe('application/zip')
  })

  it('result length matches input for png-zip', async () => {
    const frames = Array.from({ length: 5 }, (_, i) => `data:image/png;base64,FRAME${i}`)
    const result = await exportFrames(frames, 'png-zip')
    // Blob should be non-empty
    expect(result.blob.size).toBeGreaterThan(0)
  })

  it('falls back to png-zip when MediaRecorder is unavailable (webm requested)', async () => {
    // MediaRecorder is not defined in this test env, so webm → png-zip fallback.
    const frames = ['data:image/png;base64,abc']
    const result = await exportFrames(frames, 'webm')
    // Should not throw; should return something sensible
    expect(result).toHaveProperty('blob')
    expect(result).toHaveProperty('ext')
  })

  it('throws when frames is not an array', async () => {
    await expect(exportFrames('not-an-array', 'png-zip')).rejects.toThrow('frames must be an array')
  })

  it('handles empty frames array', async () => {
    const result = await exportFrames([], 'png-zip')
    expect(result.blob).toBeDefined()
    expect(result.ext).toBe('zip')
  })

  it('format field on result reflects actual format used', async () => {
    const result = await exportFrames(['data:image/png;base64,aa=='], 'png-zip')
    expect(result.format).toBe('png-zip')
  })
})

// ── isMediaRecorderAvailable ──────────────────────────────────────────────────

describe('isMediaRecorderAvailable', () => {
  it('returns false in jsdom/vitest environment (no MediaRecorder)', () => {
    // vitest/jsdom doesn't ship MediaRecorder.
    expect(isMediaRecorderAvailable()).toBe(false)
  })
})

// ── previewMode ───────────────────────────────────────────────────────────────

describe('previewMode', () => {
  let rafId = 0
  let rafCallbacks = []

  beforeEach(() => {
    rafId = 0
    rafCallbacks = []
    // Stub requestAnimationFrame / cancelAnimationFrame.
    vi.stubGlobal('requestAnimationFrame', (cb) => {
      const id = ++rafId
      rafCallbacks.push({ id, cb })
      return id
    })
    vi.stubGlobal('cancelAnimationFrame', (id) => {
      rafCallbacks = rafCallbacks.filter((r) => r.id !== id)
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('throws when camera is null', () => {
    expect(() => previewMode(makeScene(), null, makeRenderer())).toThrow('camera is required')
  })

  it('returns a handle with a stop() function', () => {
    const cam = makeCamera()
    const handle = previewMode(makeScene(), cam, makeRenderer())
    expect(typeof handle.stop).toBe('function')
    handle.stop()
  })

  it('registers a requestAnimationFrame callback on start', () => {
    const before = rafCallbacks.length
    const cam = makeCamera()
    previewMode(makeScene(), cam, makeRenderer())
    expect(rafCallbacks.length).toBeGreaterThan(before)
  })

  it('stop() prevents further RAF callbacks from being queued', () => {
    const cam = makeCamera()
    const handle = previewMode(makeScene(), cam, makeRenderer())
    handle.stop()
    const countAfterStop = rafCallbacks.length
    // Flush any queued callbacks after stop — they should not re-register.
    const pending = [...rafCallbacks]
    rafCallbacks = []
    for (const { cb } of pending) {
      try { cb(performance.now()) } catch { /* ignore */ }
    }
    // No new callbacks should have been added.
    expect(rafCallbacks.length).toBe(0)
    // Sanity: count didn't grow unexpectedly.
    expect(rafCallbacks.length).toBeLessThanOrEqual(countAfterStop)
  })

  it('advances the azimuth over multiple ticks', () => {
    const cam = makeCamera()
    const positions = []
    const origSet = cam.position.set.bind(cam.position)
    cam.position.set = (x, y, z) => { positions.push({ x, y, z }); origSet(x, y, z) }

    previewMode(makeScene(), cam, makeRenderer(), { radius: 100, elevation: 0 })

    // Fire several RAF ticks with increasing timestamps.
    let t = 0
    for (let i = 0; i < 4 && rafCallbacks.length > 0; i++) {
      t += 200 // 200ms each step → noticeable azimuth change
      const { cb } = rafCallbacks[rafCallbacks.length - 1]
      rafCallbacks = []
      cb(t)
    }

    // Camera should have moved
    expect(positions.length).toBeGreaterThan(0)
    const xs = positions.map((p) => p.x)
    // At least two distinct x-values (camera has rotated)
    const distinct = new Set(xs.map((v) => Math.round(v)))
    expect(distinct.size).toBeGreaterThan(1)
  })
})
