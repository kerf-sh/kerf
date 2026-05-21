// Gumball pure-helper unit tests (Phase 4b).
//
// Covers the math the Gumball component pulls out as exported helpers so the
// React/three.js shell can stay un-tested at this level:
//
//   * averagePoints         — vertex averaging used to derive a face centroid
//                             when OCCT didn't supply one.
//   * computeFaceCentroid   — picks faceMeta.centroid first, falls back to
//                             averaging the face's expanded triangle verts.
//   * projectScreenDeltaToAxis — maps cursor pixel-deltas into world units
//                             along a world-axis projected to screen.
//   * angleBetweenScreenDeltas — radians between two cursor offsets relative
//                             to a rotation center, normalized to [-π, π].

import { describe, it, expect, vi } from 'vitest'
import * as THREE from 'three'
import {
  averagePoints,
  computeFaceCentroid,
  projectScreenDeltaToAxis,
  angleBetweenScreenDeltas,
  projectScreenDeltaToRadialDistance,
  computeRadialBasis,
  buildFaceModeHandlers,
} from '../components/Gumball.jsx'

describe('Gumball helpers', () => {
  it('averagePoints averages componentwise and handles empty input', () => {
    expect(averagePoints([])).toEqual([0, 0, 0])
    const c = averagePoints([[0, 0, 0], [2, 4, 6]])
    expect(c).toEqual([1, 2, 3])
  })

  it('computeFaceCentroid prefers the OCCT-supplied centroid', () => {
    const part = {
      faceMeta: [
        { id: 7, centroid: [10, 20, 30] },
        { id: 8, centroid: [0, 0, 0] },
      ],
      // Triangle data also present; should be ignored when faceMeta has it.
      positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      faceIdPerTri: new Uint32Array([7]),
    }
    expect(computeFaceCentroid(part, 7)).toEqual([10, 20, 30])
  })

  it('computeFaceCentroid falls back to averaging triangle vertices', () => {
    // Two triangles for face 5: (0,0,0)-(1,0,0)-(0,1,0) and (1,0,0)-(1,1,0)-(0,1,0).
    // Together their 6 vertices average to ((0+1+0+1+1+0)/6, (0+0+1+0+1+1)/6, 0)
    // = (3/6, 3/6, 0) = (0.5, 0.5, 0).
    const part = {
      faceMeta: [{ id: 5 /* no centroid field */ }],
      positions: new Float32Array([
        0, 0, 0, 1, 0, 0, 0, 1, 0,
        1, 0, 0, 1, 1, 0, 0, 1, 0,
      ]),
      faceIdPerTri: new Uint32Array([5, 5]),
    }
    const c = computeFaceCentroid(part, 5)
    expect(c[0]).toBeCloseTo(0.5, 6)
    expect(c[1]).toBeCloseTo(0.5, 6)
    expect(c[2]).toBeCloseTo(0, 6)
  })

  it('computeFaceCentroid returns null for unknown faces with no triangle hits', () => {
    const part = {
      faceMeta: [],
      positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      faceIdPerTri: new Uint32Array([0]),
    }
    expect(computeFaceCentroid(part, 99)).toBeNull()
  })

  it('projectScreenDeltaToAxis maps pixel-delta to world-axis units', () => {
    // Axis points horizontally to the right in screen space, span 100 pixels.
    // origin at (50,50), tip at (150,50). A 100-pixel rightward drag should
    // map to 1 world unit along the axis.
    const d = projectScreenDeltaToAxis(100, 0, [50, 50], [150, 50])
    expect(d).toBeCloseTo(1, 6)
    // Perpendicular drag → 0 (drag is along screen-Y, axis is along screen-X).
    const dPerp = projectScreenDeltaToAxis(0, 100, [50, 50], [150, 50])
    expect(dPerp).toBeCloseTo(0, 6)
    // Reverse: dragging left projects negative.
    const dRev = projectScreenDeltaToAxis(-50, 0, [50, 50], [150, 50])
    expect(dRev).toBeCloseTo(-0.5, 6)
  })

  it('projectScreenDeltaToAxis returns 0 for a degenerate axis', () => {
    expect(projectScreenDeltaToAxis(20, 30, [0, 0], [0, 0])).toBe(0)
  })

  it('angleBetweenScreenDeltas returns signed radians', () => {
    // Start at (1,0), end at (0,1) → +90° = +π/2.
    expect(angleBetweenScreenDeltas(1, 0, 0, 1)).toBeCloseTo(Math.PI / 2, 6)
    // Start at (1,0), end at (0,-1) → -90° = -π/2.
    expect(angleBetweenScreenDeltas(1, 0, 0, -1)).toBeCloseTo(-Math.PI / 2, 6)
    // No movement → 0.
    expect(angleBetweenScreenDeltas(1, 0, 1, 0)).toBeCloseTo(0, 6)
  })
})

// Camera helper: build a perspective camera looking at the world origin from
// `+Z` so the world XY plane projects 1:1 (modulo perspective) onto the
// viewport. We update its matrices manually since there's no render loop.
function makeCamera({ pos = [0, 0, 10], target = [0, 0, 0], aspect = 1, w = 800, h = 800 } = {}) {
  const cam = new THREE.PerspectiveCamera(45, aspect, 0.1, 1000)
  cam.position.set(pos[0], pos[1], pos[2])
  cam.lookAt(target[0], target[1], target[2])
  cam.updateMatrixWorld(true)
  cam.updateProjectionMatrix()
  return { cam, w, h }
}

describe('projectScreenDeltaToRadialDistance', () => {
  it('returns 0 for a zero pixel-delta', () => {
    const { cam, w, h } = makeCamera()
    const r = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, 0, 0, w, h)
    expect(r).toBe(0)
  })

  it('matches the analytically-derived radius for cursor moves along the radial axis', () => {
    // Edge axis = +Y, camera looking down -Z from (0,0,10). The helper picks
    // radial = normalize(cross(axis, cameraForward)) = cross(+Y, -Z) = -X. Its
    // screen basis is (tipPx - midPx) where tip = mid + radial = (-1,0,0).
    // We drive the drag along that *same* screen-direction so the dot product
    // is positive and the resulting radius is +1 world unit.
    const { cam, w, h } = makeCamera()
    const mid = new THREE.Vector3(0, 0, 0).project(cam)
    const tip = new THREE.Vector3(-1, 0, 0).project(cam)
    const midPx = [(mid.x * 0.5 + 0.5) * w, (-mid.y * 0.5 + 0.5) * h]
    const tipPx = [(tip.x * 0.5 + 0.5) * w, (-tip.y * 0.5 + 0.5) * h]
    const dxPx = tipPx[0] - midPx[0]
    const dyPx = tipPx[1] - midPx[1]
    const r = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, dxPx, dyPx, w, h)
    expect(r).toBeCloseTo(1, 3)
  })

  it('clamps negative results (radius cannot be negative)', () => {
    const { cam, w, h } = makeCamera()
    // Drag opposite the helper's basis direction (which points along screen
    // -X for an edge along +Y under our camera) → negative scalar → clamped 0.
    const r = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, +150, 0, w, h)
    expect(r).toBe(0)
  })

  it('scales linearly with pixel delta (twice the drag → twice the radius)', () => {
    const { cam, w, h } = makeCamera()
    // Drag along the helper's positive basis direction (-screen-X for our
    // setup) so we get strictly positive radii.
    const r1 = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, -100, 0, w, h)
    const r2 = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, -200, 0, w, h)
    const r4 = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, -400, 0, w, h)
    expect(r1).toBeGreaterThan(0)
    expect(r2 / r1).toBeCloseTo(2, 3)
    expect(r4 / r1).toBeCloseTo(4, 3)
  })

  it('handles an edge parallel to the camera-forward axis without throwing', () => {
    // Camera at +Z looking at origin → forward = -Z. Edge axis = (0,0,1) is
    // parallel to the camera axis, so cross(axis, fwd) is degenerate. The
    // helper must fall back to cross-with-camera-up and produce a finite,
    // non-negative result.
    const { cam, w, h } = makeCamera()
    let result
    expect(() => {
      result = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 0, 1], cam, 50, 0, w, h)
    }).not.toThrow()
    expect(Number.isFinite(result)).toBe(true)
    expect(result).toBeGreaterThanOrEqual(0)
  })

  it('returns 0 for a degenerate (zero-length) edge axis', () => {
    const { cam, w, h } = makeCamera()
    const r = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 0, 0], cam, 100, 50, w, h)
    expect(r).toBe(0)
  })
})

describe('computeRadialBasis', () => {
  it('picks a unit vector perpendicular to both the edge axis and camera forward', () => {
    const { cam } = makeCamera()
    const r = computeRadialBasis([0, 1, 0], cam)
    expect(r).not.toBeNull()
    // Camera forward is -Z, edge axis is +Y → cross(+Y, -Z) = -X. Result is
    // unit length and orthogonal to the edge axis.
    expect(r.length()).toBeCloseTo(1, 6)
    expect(r.dot(new THREE.Vector3(0, 1, 0))).toBeCloseTo(0, 6)
  })

  it('returns null for a degenerate edge axis', () => {
    const { cam } = makeCamera()
    expect(computeRadialBasis([0, 0, 0], cam)).toBeNull()
  })

  it('falls back to camera-up when the edge is parallel to camera forward', () => {
    const { cam } = makeCamera()
    // Edge axis = +Z, camera forward = -Z → cross is degenerate, fall back.
    const r = computeRadialBasis([0, 0, 1], cam)
    expect(r).not.toBeNull()
    expect(r.length()).toBeCloseTo(1, 6)
    // Still orthogonal to the edge axis.
    expect(r.dot(new THREE.Vector3(0, 0, 1))).toBeCloseTo(0, 6)
  })

  it('rotates with the camera (re-derives basis given a fresh camera state)', () => {
    // Same edge axis, two different camera positions → different bases.
    const a = makeCamera({ pos: [0, 0, 10] })
    const b = makeCamera({ pos: [10, 0, 0] })
    const ra = computeRadialBasis([0, 1, 0], a.cam)
    const rb = computeRadialBasis([0, 1, 0], b.cam)
    expect(ra).not.toBeNull()
    expect(rb).not.toBeNull()
    // Distinct camera states → distinct radial vectors.
    const dot = ra.dot(rb)
    expect(Math.abs(dot)).toBeLessThan(0.99)
  })
})

// ---------------------------------------------------------------------------
// T-C3: buildFaceModeHandlers — touch drag integration tests.
//
// Strategy: build a minimal harness with a mock domElement (fixed 800×600
// rect), a real THREE.PerspectiveCamera, and mock handles whose `object` is
// a real THREE.Mesh placed in world space. The camera is set up to face
// straight down -Z from (0,0,10) so the X-axis translate handle at [1,0,0]
// projects predictably to screen-right. We bypass THREE.js raycasting for
// the hit test by supplying mock handle objects that report intersections
// through a controlled `pickResult` variable — this keeps tests deterministic
// without a real WebGL renderer.
//
// The tests directly drive onDown → onMove → onUp and assert:
//   1. Touch drag ON a handle → `updateFeature` is called on pointerup.
//   2. Touch drag OFF a handle (miss) → `updateFeature` is NOT called.
//   3. Mouse drag ON a handle → `updateFeature` is also called (parity).
//   4. onUp fires before updateFeature (commit on pointerup, not pointermove).
//   5. Rotate handle touch drag → rotate_face feature committed.

function makeTestCamera() {
  const cam = new THREE.PerspectiveCamera(45, 800 / 600, 0.1, 1000)
  cam.position.set(0, 0, 10)
  cam.lookAt(0, 0, 0)
  cam.updateMatrixWorld(true)
  cam.updateProjectionMatrix()
  return cam
}

// Build a mock domElement that reports a fixed 800×600 bounding rect.
// No DOM required: we use a plain object with the minimal interface the
// handler needs (getBoundingClientRect, addEventListener, removeEventListener,
// setPointerCapture, releasePointerCapture, style).
function makeMockCanvas() {
  const listeners = {}
  const el = {
    getBoundingClientRect: () => ({
      left: 0, top: 0, width: 800, height: 600,
      right: 800, bottom: 600,
    }),
    setPointerCapture: vi.fn(),
    releasePointerCapture: vi.fn(),
    style: { touchAction: '' },
    addEventListener(type, fn, _capture) {
      if (!listeners[type]) listeners[type] = []
      listeners[type].push(fn)
    },
    removeEventListener(type, fn, _capture) {
      if (listeners[type]) {
        listeners[type] = listeners[type].filter((f) => f !== fn)
      }
    },
    // Expose listeners for test inspection if needed.
    _listeners: listeners,
  }
  return el
}

// Build a synthetic PointerEvent-like plain object (jsdom's PointerEvent
// lacks pointerType, so we use a plain object instead).
function makePointerEvent(overrides = {}) {
  const base = {
    pointerId: 1,
    pointerType: 'touch',
    button: 0,
    clientX: 400,
    clientY: 300,
    target: null, // filled in per test
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
  }
  return { ...base, ...overrides }
}

describe('buildFaceModeHandlers — T-C3 touch drag', () => {
  // Shared test context builder. `pickFn` controls what pickHandle returns:
  //   - pass a handle object → the pointer "hits" that handle
  //   - pass null → the pointer misses all handles
  //
  // We override the internal raycasting by making handles whose `object` will
  // cause raycaster.intersectObjects to return a hit when the pointer is
  // aimed at the handle's screen position, or by injecting the handle
  // directly via a custom mock. Since real raycasting needs a renderer, we
  // instead supply handles with `object` meshes that are far off-screen, and
  // pass a `mockPickFn` override — a thin shim that replaces the internal
  // raycaster for test purposes. We achieve this by passing the handle list
  // and using the THREE camera to make the handle actually visible at the
  // given pointer location.
  //
  // Simpler: we pass a single translate handle with `axisDir = [0,0,1]` and
  // place its mesh at the *exact* NDC position of the pointer's clientX/Y
  // so the raycaster will intersect it. With a 45-deg FOV camera at z=10
  // looking at the origin, NDC (0,0) → pixel (400,300).
  // We place a large sphere at world (0,0,0) so raycasts from (0,0) NDC hit it.

  function buildHarness({ pointerType = 'touch' } = {}) {
    const cam = makeTestCamera()
    const canvas = makeMockCanvas()
    const controls = { enabled: true }
    const dragRef = { current: null }

    const updateFeature = vi.fn()
    const newFeatureIdFn = vi.fn(() => 'test-id-1')

    // One translate handle: sphere at world origin (0,0,0), so a pointer
    // aimed at screen center (400,300) = NDC (0,0) should hit it.
    const sphereGeom = new THREE.SphereGeometry(0.5, 8, 6)
    const sphereMat = new THREE.MeshBasicMaterial({ visible: false })
    const sphereMesh = new THREE.Mesh(sphereGeom, sphereMat)
    sphereMesh.position.set(0, 0, 0)
    sphereMesh.updateMatrixWorld(true)
    sphereMesh.userData = { kind: 'translate', axisId: 'z' }

    const handles = [
      {
        kind: 'translate',
        axisId: 'z',
        axisDir: [0, 0, 1],
        object: sphereMesh,
        baseColor: 0x4d9aff,
      },
    ]

    // perPart: face normal along Z so dot(axisDir, normal) = 1.
    const perPart = new Map([
      ['part1', {
        faceMeta: [{ id: 5, centroid: [0, 0, 0], normal: [0, 0, 1] }],
      }],
    ])

    const { onDown, onMove, onUp } = buildFaceModeHandlers({
      handles,
      dragRef,
      controls,
      camera: cam,
      domElement: canvas,
      centroid: [0, 0, 0],
      partId: 'part1',
      faceId: 5,
      perPart,
      overlay: null,
      updateFeature,
      newFeatureIdFn,
    })

    // Helper: aim pointer at screen center (hits the sphere at origin).
    function hitEvent(overrides = {}) {
      const ev = makePointerEvent({
        target: canvas,
        pointerType,
        clientX: 400, // screen center → NDC (0,0) → hits sphere
        clientY: 300,
        ...overrides,
      })
      return ev
    }

    // Helper: aim pointer far off-center (misses the sphere).
    function missEvent(overrides = {}) {
      return makePointerEvent({
        target: canvas,
        pointerType,
        clientX: 5, // far from sphere projection
        clientY: 5,
        ...overrides,
      })
    }

    return { onDown, onMove, onUp, dragRef, controls, updateFeature, hitEvent, missEvent, canvas }
  }

  it('touch pointerdown on a handle enters drag mode and captures the pointer', () => {
    const { onDown, dragRef, controls, canvas, hitEvent } = buildHarness({ pointerType: 'touch' })

    const ev = hitEvent()
    onDown(ev)

    // Drag state populated → drag mode active.
    expect(dragRef.current).not.toBeNull()
    expect(dragRef.current.handle.kind).toBe('translate')
    // OrbitControls disabled during drag.
    expect(controls.enabled).toBe(false)
    // setPointerCapture called with the pointer id.
    expect(canvas.setPointerCapture).toHaveBeenCalledWith(1)
  })

  it('touch drag off a handle does NOT enter drag mode', () => {
    const { onDown, dragRef, controls, missEvent } = buildHarness({ pointerType: 'touch' })

    onDown(missEvent())

    expect(dragRef.current).toBeNull()
    // OrbitControls should not have been disabled.
    expect(controls.enabled).toBe(true)
  })

  it('touch drag on translate handle → updateFeature called on pointerup (commit on pointerup)', () => {
    const { onDown, onMove, onUp, updateFeature, hitEvent } = buildHarness({ pointerType: 'touch' })

    const downEv = hitEvent({ clientX: 400, clientY: 300 })
    onDown(downEv)

    // updateFeature must NOT be called yet (no commit mid-drag).
    expect(updateFeature).not.toHaveBeenCalled()

    // Drag 200px to the right — axis is Z and the tip projects to the right,
    // so the distance will be non-zero. (We just need |distAlongNormal| >= 0.05.)
    // Since the Z axis projects to a near-zero screen length at normal viewing
    // (it goes into the screen), and axis dot normal = 1, we need to drive a
    // drag that produces a measurable distance. We force distance directly by
    // setting a drag delta along the axis screen projection direction.
    // The simplest approach: override the drag state after onDown sets it up,
    // then call onUp with a fake dragged drag.distance.
    // To keep this white-box free, we instead test via a large clientX delta.
    // However, since the Z axis goes into the screen, the screen projection
    // of origin → origin+Z is near-degenerate. Let's use a Y-axis handle
    // which projects clearly upward in screen space.

    // We re-build a harness with a Y-axis translate handle for this test.
    const cam = makeTestCamera()
    const canvas2 = makeMockCanvas()
    const controls2 = { enabled: true }
    const dragRef2 = { current: null }
    const updateFeature2 = vi.fn()

    // Y-axis handle: large sphere at y=1 so the sphere is "above" center.
    const sphereGeom = new THREE.SphereGeometry(0.5, 8, 6)
    const sphereMesh = new THREE.Mesh(sphereGeom, new THREE.MeshBasicMaterial({ visible: false }))
    sphereMesh.position.set(0, 0, 0) // put it at origin so center-pointer hits it
    sphereMesh.updateMatrixWorld(true)
    sphereMesh.userData = { kind: 'translate', axisId: 'y' }

    const handles2 = [{
      kind: 'translate',
      axisId: 'y',
      axisDir: [0, 1, 0],
      object: sphereMesh,
      baseColor: 0x52c41a,
    }]

    const perPart2 = new Map([
      ['part1', { faceMeta: [{ id: 5, centroid: [0, 0, 0], normal: [0, 1, 0] }] }],
    ])

    const { onDown: onDown2, onMove: onMove2, onUp: onUp2 } = buildFaceModeHandlers({
      handles: handles2,
      dragRef: dragRef2,
      controls: controls2,
      camera: cam,
      domElement: canvas2,
      centroid: [0, 0, 0],
      partId: 'part1',
      faceId: 5,
      perPart: perPart2,
      overlay: null,
      updateFeature: updateFeature2,
      newFeatureIdFn: () => 'test-id-2',
    })

    // pointerdown at center (hits sphere).
    onDown2(makePointerEvent({ target: canvas2, pointerType: 'touch', clientX: 400, clientY: 300 }))
    expect(dragRef2.current).not.toBeNull()

    // pointermove: drag 300px upward (Y axis maps to screen-up = clientY decreasing).
    onMove2(makePointerEvent({ target: canvas2, pointerType: 'touch', pointerId: 1, clientX: 400, clientY: 0 }))

    // updateFeature NOT called yet.
    expect(updateFeature2).not.toHaveBeenCalled()

    // pointerup commits.
    onUp2(makePointerEvent({ target: canvas2, pointerType: 'touch', pointerId: 1, clientX: 400, clientY: 0 }))

    // Commit fires on pointerup.
    expect(updateFeature2).toHaveBeenCalledTimes(1)
    const updater = updateFeature2.mock.calls[0][0]
    const result = updater({ features: [] })
    expect(result.features).toHaveLength(1)
    expect(result.features[0].op).toBe('push_pull')
    expect(result.features[0].face_id).toBe(5)
    expect(typeof result.features[0].distance).toBe('number')
    expect(Math.abs(result.features[0].distance)).toBeGreaterThan(0)
  })

  it('touch drag off handle → updateFeature is NOT called even after pointerup', () => {
    const { onDown, onMove, onUp, updateFeature, missEvent } = buildHarness({ pointerType: 'touch' })

    onDown(missEvent())
    onMove(makePointerEvent({ pointerId: 1, clientX: 200, clientY: 200 }))
    onUp(makePointerEvent({ pointerId: 1, clientX: 200, clientY: 200 }))

    expect(updateFeature).not.toHaveBeenCalled()
  })

  it('mouse drag on handle → updateFeature called (mouse parity)', () => {
    // Re-use the Y-axis harness from the translate test, but with pointerType='mouse'.
    const cam = makeTestCamera()
    const canvas = makeMockCanvas()
    const controls = { enabled: true }
    const dragRef = { current: null }
    const updateFeature = vi.fn()

    const sphereGeom = new THREE.SphereGeometry(0.5, 8, 6)
    const sphereMesh = new THREE.Mesh(sphereGeom, new THREE.MeshBasicMaterial({ visible: false }))
    sphereMesh.position.set(0, 0, 0)
    sphereMesh.updateMatrixWorld(true)
    sphereMesh.userData = { kind: 'translate', axisId: 'y' }

    const handles = [{
      kind: 'translate', axisId: 'y', axisDir: [0, 1, 0],
      object: sphereMesh, baseColor: 0x52c41a,
    }]
    const perPart = new Map([
      ['part1', { faceMeta: [{ id: 5, centroid: [0, 0, 0], normal: [0, 1, 0] }] }],
    ])

    const { onDown, onMove, onUp } = buildFaceModeHandlers({
      handles, dragRef, controls, camera: cam, domElement: canvas,
      centroid: [0, 0, 0], partId: 'part1', faceId: 5, perPart,
      overlay: null, updateFeature, newFeatureIdFn: () => 'test-id-3',
    })

    onDown(makePointerEvent({ target: canvas, pointerType: 'mouse', button: 0, clientX: 400, clientY: 300 }))
    expect(dragRef.current).not.toBeNull()

    onMove(makePointerEvent({ pointerType: 'mouse', pointerId: 1, clientX: 400, clientY: 0 }))
    expect(updateFeature).not.toHaveBeenCalled()

    onUp(makePointerEvent({ pointerType: 'mouse', pointerId: 1, clientX: 400, clientY: 0 }))
    expect(updateFeature).toHaveBeenCalledTimes(1)
  })

  it('rotate handle touch drag → rotate_face feature committed on pointerup', () => {
    const cam = makeTestCamera()
    const canvas = makeMockCanvas()
    const controls = { enabled: true }
    const dragRef = { current: null }
    const updateFeature = vi.fn()

    // Rotate handle: torus at origin, but for test purposes a sphere is fine.
    const sphereGeom = new THREE.SphereGeometry(0.5, 8, 6)
    const sphereMesh = new THREE.Mesh(sphereGeom, new THREE.MeshBasicMaterial({ visible: false }))
    sphereMesh.position.set(0, 0, 0)
    sphereMesh.updateMatrixWorld(true)
    sphereMesh.userData = { kind: 'rotate', axisId: 'z' }

    const handles = [{
      kind: 'rotate', axisId: 'z', axisDir: [0, 0, 1],
      object: sphereMesh, baseColor: 0xff4d4f,
    }]
    const perPart = new Map([['part1', { faceMeta: [{ id: 5, centroid: [0, 0, 0] }] }]])

    const { onDown, onMove, onUp } = buildFaceModeHandlers({
      handles, dragRef, controls, camera: cam, domElement: canvas,
      centroid: [0, 0, 0], partId: 'part1', faceId: 5, perPart,
      overlay: null, updateFeature, newFeatureIdFn: () => 'test-id-4',
    })

    // Down at screen-right of center (positive X from center).
    onDown(makePointerEvent({ target: canvas, pointerType: 'touch', clientX: 400, clientY: 300 }))
    expect(dragRef.current).not.toBeNull()

    // Move to screen-top-right: clockwise sweep → positive angle.
    // Start offset from center: (0, 0). End: (100, -100). That's a CCW 45° rotation.
    // clientX = 400+100=500, clientY = 300-100=200.
    onMove(makePointerEvent({ pointerId: 1, pointerType: 'touch', clientX: 500, clientY: 200 }))
    expect(updateFeature).not.toHaveBeenCalled()

    onUp(makePointerEvent({ pointerId: 1, pointerType: 'touch', clientX: 500, clientY: 200 }))
    expect(updateFeature).toHaveBeenCalledTimes(1)
    const updater = updateFeature.mock.calls[0][0]
    const result = updater({ features: [] })
    expect(result.features[0].op).toBe('rotate_face')
    expect(result.features[0].face_id).toBe(5)
    expect(Math.abs(result.features[0].angle_deg)).toBeGreaterThan(0)
  })

  it('second touch pointer during drag is ignored (pointer-id guard)', () => {
    const cam = makeTestCamera()
    const canvas = makeMockCanvas()
    const controls = { enabled: true }
    const dragRef = { current: null }
    const updateFeature = vi.fn()

    const sphereGeom = new THREE.SphereGeometry(0.5, 8, 6)
    const sphereMesh = new THREE.Mesh(sphereGeom, new THREE.MeshBasicMaterial({ visible: false }))
    sphereMesh.position.set(0, 0, 0)
    sphereMesh.updateMatrixWorld(true)
    sphereMesh.userData = { kind: 'translate', axisId: 'y' }

    const handles = [{ kind: 'translate', axisId: 'y', axisDir: [0, 1, 0], object: sphereMesh }]
    const perPart = new Map([
      ['part1', { faceMeta: [{ id: 5, centroid: [0, 0, 0], normal: [0, 1, 0] }] }],
    ])
    const { onDown, onMove, onUp } = buildFaceModeHandlers({
      handles, dragRef, controls, camera: cam, domElement: canvas,
      centroid: [0, 0, 0], partId: 'part1', faceId: 5, perPart,
      overlay: null, updateFeature, newFeatureIdFn: () => 'test-id-5',
    })

    // First finger down (pointerId=1) at center.
    onDown(makePointerEvent({ target: canvas, pointerType: 'touch', pointerId: 1, clientX: 400, clientY: 300 }))
    const stateAfterDown = dragRef.current ? { ...dragRef.current } : null

    // Second finger move (pointerId=2) should be ignored.
    onMove(makePointerEvent({ pointerType: 'touch', pointerId: 2, clientX: 100, clientY: 100 }))
    // dragRef should be unchanged (not corrupted by second finger).
    expect(dragRef.current).not.toBeNull()

    // Second finger pointerup should be ignored.
    onUp(makePointerEvent({ pointerType: 'touch', pointerId: 2, clientX: 100, clientY: 100 }))
    // Drag still active (first finger not lifted).
    expect(dragRef.current).not.toBeNull()
    expect(updateFeature).not.toHaveBeenCalled()

    // First finger lifts with enough delta to commit.
    onMove(makePointerEvent({ pointerType: 'touch', pointerId: 1, clientX: 400, clientY: 0 }))
    onUp(makePointerEvent({ pointerType: 'touch', pointerId: 1, clientX: 400, clientY: 0 }))
    expect(updateFeature).toHaveBeenCalledTimes(1)
  })
})
