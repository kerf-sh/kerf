import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { Sun, SlidersHorizontal, Check, ChevronDown } from 'lucide-react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { Line2 } from 'three/examples/jsm/lines/Line2.js'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'
// Post-FX + HDRI imports.  All come from `three/examples/jsm/` and ship with
// the three package already pinned in package.json (^0.160.0) — no new
// dependency is added.
//   - EffectComposer / RenderPass / UnrealBloomPass: bloom for gemstone
//     highlights, gated behind a quality flag so we can disable when the
//     browser reports `prefers-reduced-motion` or low-power hints.
//   - RGBELoader: loads .hdr equirectangular maps when a real HDRI asset
//     is provided by the caller via `setEnvironmentHdr(url)`.  In the
//     default offline path we synthesise a tiny DataTexture studio gradient
//     and route it through PMREMGenerator → scene.environment.
//   - RoomEnvironment: a self-contained synthetic studio used as the
//     zero-asset fallback; same approach as FeatureRenderer.jsx already does.
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { RGBELoader } from 'three/examples/jsm/loaders/RGBELoader.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { geom3ToBufferGeometry, combinedBoundingBox } from '../lib/geom3.js'
import { getTopologyLazy } from '../lib/topology.js'
import { distance, formatDistance } from '../lib/measure.js'
import { cullByFrustum, setUserVisible, frustumCullEnabled } from '../lib/frustumCull.js'
import { planInstances, instancingEnabled } from '../lib/instancingPlan.js'
import { createZebraMaterial } from '../lib/zebraMaterial.js'
import { recordTurntable as _recordTurntable } from '../lib/turntableRender.js'
import { attachDfmOverlay, detachDfmOverlay, refreshDfm } from '../lib/dfmOverlay.js'
import { renderHeroSet as _renderHeroSet } from '../lib/heroRender.js'
import { captureHeroShot as _captureHeroShot } from '../lib/heroShot.js'
import HeroRenderPanel from './HeroRenderPanel.jsx'

const PALETTE = [0xc9a96b, 0x6b9bc9, 0xc96b89, 0x89c96b, 0xc9b86b, 0x9b6bc9]
const HIGHLIGHT_EMISSIVE = 0x4d3c00 // kerf yellow tint
const BG_COLOR = 0x0f1115 // ink-900
const BG_COLOR_TOP = 0x1a1d24 // soft studio gradient top (slightly warmer)
const KERF_YELLOW = 0xffd633
const INK_300 = 0x8a93a6

// ── Hero / PBR constants ──────────────────────────────────────────────────────
//
// Bloom is tuned for *gemstone highlights*, not the over-bloomed beam glow
// that ruins jewelry photography.  These three numbers are documented in the
// commit message so future tweakers don't have to reverse-engineer them:
//
//   threshold = 0.85 — only the top ~15% of luminance triggers bloom.  Below
//                       this, regular highlights remain crisp.
//   radius    = 0.45 — moderate kernel; gives a halo without smearing detail.
//   strength  = 0.55 — low overall mix; gem facets sparkle but the metal
//                       body stays sharp.  Crank to ~1.2 for studio diamond
//                       hero shots; we expose this via setBloomStrength().
const BLOOM_THRESHOLD = 0.85
const BLOOM_RADIUS = 0.45
const BLOOM_STRENGTH = 0.55

// Default tone-mapping exposure.  ACES filmic with exposure=1.0 gives a
// neutral starting point for jewellery (gold midtones don't blow out, dark
// rhodium retains shape).  The UI slider exposes this 0.2 … 2.0.
const DEFAULT_EXPOSURE = 1.0

// Default hero-shot resolution + supersampling.  Matches heroShot.js defaults
// but redeclared here so the Renderer UI button doesn't have to import the
// internal `_internals` table.
const HERO_DEFAULT_W = 2048
const HERO_DEFAULT_H = 2048
const HERO_DEFAULT_SAMPLES = 4

/**
 * Detect a reduced-motion or low-power preference.  Browsers expose this via
 * `matchMedia('(prefers-reduced-motion: reduce)')`; we treat it as a hint to
 * skip bloom by default.  Wrapped in try/catch so it works in jsdom (which
 * provides matchMedia but may not honour all media queries).
 */
function prefersReducedMotion() {
  try {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches === true
  } catch {
    return false
  }
}

// NURBS surface tessellation note:
//
// NURBS surfaces authored via feature_sweep2 / feature_network_srf /
// feature_blend_srf (and the sweep1 starter) are evaluated by the OCCT worker
// (occtWorker.js) using OpenCascade.js operations:
//   sweep2      → BRepOffsetAPI_MakePipeShell
//   network_srf → GeomFill_BSplineCurves / BRepOffsetAPI_ThruSections
//   blend_srf   → BRepFill_Filling
//
// The resulting B-rep shape is tessellated by OCCT into a triangle mesh
// (BRepMesh_IncrementalMesh) and returned as a BufferGeometry, which is then
// resolved here. The Python NurbsSurface objects in backend/geom/ are the
// LLM-accessible manipulation layer; they do not drive rendering directly.
//
// Phase 4 scope: surface creation + display. NURBS trimming and boolean ops
// on NURBS require a deeper OCCT NURBS kernel integration and are out of scope.

// Resolve any of:
//   - Three.js BufferGeometry (already tessellated, e.g. from STEP or OCCT worker)
//   - JSCAD Geom3 (polygon list, runJscad output)
// → BufferGeometry. We never mutate the input — JSCAD path always creates new.
function resolveGeometry(geom) {
  if (!geom) return null
  if (geom.isBufferGeometry) {
    // Cache a clone on the geometry so repeated mounts share buffers but don't
    // step on each other on dispose. We clone here, return the clone — the
    // mesh group fully owns it and will dispose on unmount.
    return geom.clone()
  }
  return geom3ToBufferGeometry(geom)
}

// Build a BufferGeometry from a face's flat triangle list. Computes flat
// normals so the overlay doesn't z-fight visibly with the underlying mesh.
function geometryFromFaceTriangles(triangles) {
  const positions = new Float32Array(triangles.length * 9)
  const normals = new Float32Array(triangles.length * 9)
  for (let i = 0; i < triangles.length; i++) {
    const [a, b, c] = triangles[i]
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2]
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2]
    let nx = uy * vz - uz * vy
    let ny = uz * vx - ux * vz
    let nz = ux * vy - uy * vx
    const l = Math.hypot(nx, ny, nz) || 1
    nx /= l; ny /= l; nz /= l
    const o = i * 9
    positions[o] = a[0]; positions[o + 1] = a[1]; positions[o + 2] = a[2]
    positions[o + 3] = b[0]; positions[o + 4] = b[1]; positions[o + 5] = b[2]
    positions[o + 6] = c[0]; positions[o + 7] = c[1]; positions[o + 8] = c[2]
    for (let k = 0; k < 9; k += 3) {
      normals[o + k] = nx; normals[o + k + 1] = ny; normals[o + k + 2] = nz
    }
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  g.setAttribute('normal', new THREE.BufferAttribute(normals, 3))
  return g
}

function Renderer({
  parts,
  selectedId,
  hiddenIds,
  onPick,
  className = '',
  // Measure-tool extension:
  mode = 'object',
  selectedFeatures = [],
  onPickFeature,
  // Modifier hint: when true, click ADDs to selectedFeatures (up to 2)
  // instead of replacing the first slot.
  // (We track shift internally on click; this is just a hook for tests.)
  // Assembly extension: highlight all parts whose `componentId` matches.
  selectedComponentId = null,
  // S2 instancing: optional array of raw assembly Component rows
  // (from parseAssembly), containing file_id + config_id so the instancing
  // planner can group identical parts into InstancedMesh objects.
  // Only used when KERF_INSTANCING is on. Non-assembly callers omit this.
  assemblyComponents = null,
  // Hero Render: project ID forwarded to HeroRenderPanel for the gallery tab
  // and render job submission.
  projectId = null,
}, ref) {
  const mountRef = useRef(null)
  const stateRef = useRef(null) // holds three.js objects across renders
  const [hudId, setHudId] = useState(null)
  const [leaderHtml, setLeaderHtml] = useState(null) // {x, y, text} screen coords
  const [zebraOn, setZebraOn] = useState(false)
  // Exposure slider state — wired into the tone-mapping exposure of the
  // WebGLRenderer.  Lives in a state hook (not a ref) so the slider thumb
  // updates as the user drags; the live render loop reads renderer state
  // directly on each frame so there's no re-render thrash.
  const [exposure, setExposure] = useState(DEFAULT_EXPOSURE)
  // Bloom is gated by both an auto detection (prefers-reduced-motion) and a
  // user override.  Default ON unless the OS hints otherwise.
  const [bloomOn, setBloomOn] = useState(() => !prefersReducedMotion())
  // Background mode toggle for hero-shot framing.  'studio' = dark gradient
  // (default), 'hdri' = the loaded environment map shown as background too
  // (so reflections and background are consistent).  We never apply the HDRI
  // to the background by default — full HDRI bg can look noisy for everyday
  // viewport editing.
  const [hdriBackground, setHdriBackground] = useState(false)
  // "Daylight": one strong directional sun + minimal fill/ambient, vs
  // the default balanced studio 3-point rig.
  const [daylight, setDaylight] = useState(false)
  // The render-controls dropdown (Daylight / Zebra / Bloom / HDRI bg)
  // replaces the old scattered floating toggle buttons.
  const [renderMenuOpen, setRenderMenuOpen] = useState(false)
  // Hero Render panel — opened from the Render dropdown.
  const [showHeroPanel, setShowHeroPanel] = useState(false)
  // Hero-shot capture in-flight flag so we can dim the chrome while the
  // upscale + blob encode is running.  Pure UX cue, no rendering effect.
  // Hero-shot capture in-flight flag. Set by doCaptureHeroShot; the
  // capture entry point now lives in the top-bar Export dropdown
  // (invoked via the imperative captureHeroShot() ref) rather than a
  // floating viewport button.
  const [, setHeroBusy] = useState(false)
  const modeRef = useRef(mode)
  const selectedFeaturesRef = useRef(selectedFeatures)
  const onPickFeatureRef = useRef(onPickFeature)

  useEffect(() => { modeRef.current = mode }, [mode])
  useEffect(() => { selectedFeaturesRef.current = selectedFeatures }, [selectedFeatures])
  useEffect(() => { onPickFeatureRef.current = onPickFeature }, [onPickFeature])

  // Build per-part topology lazily — `getTopologyLazy` returns a Map-shaped
  // object that defers `getTopology()` until the first `.get(partId)` call.
  // In object mode (no edge/vertex aux to build, no FeatureInspector open)
  // nothing gets computed.
  const topologies = useMemo(() => getTopologyLazy(parts), [parts])

  // ----- Mount: create scene/camera/renderer/controls once -----
  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return

    // preserveDrawingBuffer lets us read pixels via toBlob() even if a
    // browser repaint sneaks in between renderer.render() and the encode.
    // Tiny perf cost, big reliability win for thumbnail capture.
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true })
    renderer.setPixelRatio(window.devicePixelRatio || 1)
    renderer.setClearColor(BG_COLOR, 1)

    // ── PBR upgrade ──────────────────────────────────────────────────────
    // ACES filmic tonemap + sRGB output is the de-facto "looks like KeyShot"
    // pipeline for PBR jewellery / product viz.  `useLegacyLights = false`
    // tells Three.js to use the new physically-correct lighting model
    // (intensities in candela / lumens / lux), `physicallyCorrectLights` is
    // the older alias kept for back-compat with three pre-r155.  We set both
    // so future three-version bumps don't silently regress.
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = DEFAULT_EXPOSURE
    if ('outputColorSpace' in renderer) {
      renderer.outputColorSpace = THREE.SRGBColorSpace
    }
    if ('physicallyCorrectLights' in renderer) {
      renderer.physicallyCorrectLights = true
    }
    if ('useLegacyLights' in renderer) {
      renderer.useLegacyLights = false
    }
    // Shadow map for the contact-shadow plane and the casting sun light.
    // PCFSoft gives the softest 5×5 PCF kernel without going to VSM.
    renderer.shadowMap.enabled = true
    renderer.shadowMap.type = THREE.PCFSoftShadowMap

    mount.appendChild(renderer.domElement)
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'

    const scene = new THREE.Scene()
    // Soft studio gradient via Canvas2D → CanvasTexture.  This is the default
    // "studio" background; the HDRI is only applied to scene.background when
    // the user explicitly flips the "HDRI bg" toggle for a hero shot.
    const gradientBg = _makeStudioGradientTexture(BG_COLOR, BG_COLOR_TOP)
    if (gradientBg) {
      scene.background = gradientBg
    } else {
      scene.background = new THREE.Color(BG_COLOR)
    }

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000)
    camera.position.set(80, 80, 80)
    camera.lookAt(0, 0, 0)

    // ── PBR environment ──────────────────────────────────────────────────
    // Synthetic neutral studio HDR built from RoomEnvironment (ships with
    // three/examples).  Zero external assets — works offline, no CORS, and
    // it's been the standard "tiny PBR test rig" in three since r131.  This
    // is the *default*; callers can call ref.setEnvironmentHdr(url) to swap
    // in a real .hdr asset later (e.g. for a heavy jewellery hero render).
    const pmrem = new THREE.PMREMGenerator(renderer)
    pmrem.compileEquirectangularShader()
    let envTexture = null
    try {
      envTexture = pmrem.fromScene(new RoomEnvironment(0.5), 0.04).texture
      scene.environment = envTexture
    } catch (e) {
      // Some headless GL contexts can't run the PMREM shader; PBR materials
      // still work without env, they just don't get reflections.  Skip
      // silently — the contact shadows + bloom still elevate the look.
    }

    // Three-point lighting tuned for physical units.  In the new lighting
    // model intensities are roughly lumens for points / spots and lux for
    // directionals, so values that worked at 0.9 on the old pipeline need
    // a generous bump for the same perceived brightness.  These are tuned
    // alongside the env-map ambient (RoomEnvironment) to land at neutral.
    const ambient = new THREE.AmbientLight(0xffffff, 0.25)
    const key = new THREE.DirectionalLight(0xffffff, 2.2)
    key.position.set(60, 90, 40)
    // Cast shadows from the key only — adding shadows on every light triples
    // the GPU cost for no visible win.
    key.castShadow = true
    key.shadow.mapSize.width = 1024
    key.shadow.mapSize.height = 1024
    // Tune the shadow camera to a sensible default cube; the parts-rebuild
    // path widens it to match the bounding box of the actual model so the
    // shadow map stays high-resolution at any scale.
    key.shadow.camera.near = 1
    key.shadow.camera.far = 1000
    key.shadow.camera.left = -200
    key.shadow.camera.right = 200
    key.shadow.camera.top = 200
    key.shadow.camera.bottom = -200
    key.shadow.bias = -0.0005
    key.shadow.normalBias = 0.02
    const fill = new THREE.DirectionalLight(0x99ccff, 0.8)
    fill.position.set(-50, 30, -60)
    scene.add(ambient, key, fill)

    // ── Contact shadow plane ────────────────────────────────────────────
    // A large transparent ShadowMaterial plane that only catches shadows.
    // The plane sits a hair below the auto-framed model and is repositioned
    // in the parts-rebuild effect (so it follows the actual model bottom).
    const contactShadowMat = new THREE.ShadowMaterial({ opacity: 0.42 })
    const contactShadowPlane = new THREE.Mesh(
      new THREE.PlaneGeometry(400, 400),
      contactShadowMat,
    )
    contactShadowPlane.rotation.x = -Math.PI / 2
    contactShadowPlane.position.y = -0.001
    contactShadowPlane.receiveShadow = true
    contactShadowPlane.userData._heroChrome = false // not hidden during hero
    scene.add(contactShadowPlane)

    // Subtle ground grid.
    const grid = new THREE.GridHelper(400, 40, 0x232730, 0x14171c)
    grid.rotation.x = Math.PI / 2 // JSCAD is Z-up; spin grid into XY plane.
    grid.userData._heroChrome = true // hide for hero shots
    scene.add(grid)

    const axes = new THREE.AxesHelper(20)
    axes.userData._heroChrome = true // hide for hero shots
    scene.add(axes)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    // T-C1: dampingFactor=0.08 chosen to feel responsive without overshoot
    // on both mouse-drag orbit and pinch-zoom inertia.  Lower → smoother but
    // laggy on small finger gestures; higher → snappier but jitter on pinch.
    controls.dampingFactor = 0.08
    // T-C1: explicit touch mapping so we don't depend on OrbitControls'
    // implicit defaults — one finger orbits, two fingers pinch-zoom AND pan
    // simultaneously (DOLLY_PAN).  Desktop mouse mapping (LEFT=ROTATE,
    // RIGHT=PAN, MIDDLE=DOLLY, wheel=zoom) is left untouched: we do NOT
    // assign `controls.mouseButtons`, so OrbitControls' defaults stand.
    controls.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN }
    controls.enableZoom = true
    controls.enablePan = true
    // screenSpacePanning=true makes two-finger pan move parallel to the
    // screen plane — the intuitive expectation on touch.  Mouse right-drag
    // pan inherits the same setting; users still get correct WYSIWYG
    // panning relative to the view plane.
    controls.screenSpacePanning = true
    // Suppress browser pinch-zoom / scroll gestures on the canvas so they
    // route through OrbitControls / our pointer handlers instead.  Also
    // prevents synthetic mouse events from being dispatched after a tap.
    renderer.domElement.style.touchAction = 'none'

    // Layered groups so each mode can show/hide its aux geometry independently.
    const meshGroup = new THREE.Group()
    const edgeGroup = new THREE.Group()
    const vertexGroup = new THREE.Group()
    const overlayGroup = new THREE.Group()  // hover face highlight + selection
    const leaderGroup = new THREE.Group()   // distance leader-line between picks
    scene.add(meshGroup, edgeGroup, vertexGroup, overlayGroup, leaderGroup)

    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    raycaster.params.Line2 = { threshold: 8 }

    // ── Post-FX composer ─────────────────────────────────────────────────
    // RenderPass draws the scene; UnrealBloomPass adds the gem-highlight
    // halo on top.  We keep a reference to the bloom pass so the user-facing
    // toggle can enable/disable just that pass (cheap: re-renders without
    // post-FX) without tearing down the composer.
    //
    // The composer's render-target size is wired into applySize() below so
    // it tracks the canvas pixel size on container resizes.
    const composer = new EffectComposer(renderer)
    composer.setPixelRatio(window.devicePixelRatio || 1)
    const renderPass = new RenderPass(scene, camera)
    composer.addPass(renderPass)
    const bloomPass = new UnrealBloomPass(
      new THREE.Vector2(1, 1),  // resized in applySize
      BLOOM_STRENGTH,
      BLOOM_RADIUS,
      BLOOM_THRESHOLD,
    )
    bloomPass.enabled = !prefersReducedMotion()
    composer.addPass(bloomPass)

    let running = true
    function loop() {
      if (!running) return
      controls.update()

      // S1: frustum cull — toggle mesh.visible per frame so Three.js skips
      // off-screen geometry in both the render call AND picking.  We only cull
      // the meshGroup children; aux groups (edges, vertices, overlays) are
      // small enough that their built-in frustumCulled path is sufficient.
      const s = stateRef.current
      if (s) {
        const enabled = frustumCullEnabled()
        cullByFrustum(s.meshGroup.children, camera, { enabled })
        // InstancedMesh entries live directly in meshGroup too — Three.js
        // already handles per-instance culling for InstancedMesh via its own
        // frustumCulled flag, so we just let them pass through (cullByFrustum
        // skips objects without geometry.boundingBox in a safe way).
      }

      // Drive the post-FX composer when bloom is on; fall back to the bare
      // renderer.render() path when bloom is off so the second framebuffer
      // copy of EffectComposer doesn't eat fillrate on low-end devices.
      if (bloomPass.enabled) {
        composer.render()
      } else {
        renderer.render(scene, camera)
      }
      // Update leader-line HUD (project the midpoint to screen).
      const pos = stateRef.current?.leaderMidpoint
      if (pos) {
        const v = pos.clone().project(camera)
        const rect = renderer.domElement.getBoundingClientRect()
        const x = (v.x * 0.5 + 0.5) * rect.width
        const y = (-v.y * 0.5 + 0.5) * rect.height
        // Hide if behind camera.
        if (v.z < 1 && v.z > -1) {
          stateRef.current?.setLeaderScreen?.({ x, y, text: stateRef.current.leaderText })
        } else {
          stateRef.current?.setLeaderScreen?.(null)
        }
      } else {
        stateRef.current?.setLeaderScreen?.(null)
      }
      requestAnimationFrame(loop)
    }
    loop()

    // Resize via ResizeObserver on the container.
    function applySize() {
      const w = mount.clientWidth || 1
      const h = mount.clientHeight || 1
      renderer.setSize(w, h, false)
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      // Keep post-FX composer + bloom pass in sync with the canvas size.
      // EffectComposer.setSize() resizes its internal render targets; the
      // bloom pass's `resolution` Vector2 drives the blur kernel and must
      // match the canvas to avoid soft / pixelated halos.
      composer.setSize(w, h)
      bloomPass.resolution.set(w, h)
      // Update LineMaterial.resolution on every fat-line we own.
      const s = stateRef.current
      if (s) {
        for (const m of s.fatLineMaterials) m.resolution.set(w, h)
      }
    }
    applySize()
    const ro = new ResizeObserver(applySize)
    ro.observe(mount)

    // T-C2: tap-vs-drag threshold (px) measured in CSS pixels.  Movement
    // beyond this between pointerdown and pointerup is treated as a drag
    // (orbit / pan / pinch) and suppresses the pick.  6 px chosen to
    // tolerate finger jitter on touch / shaky-hand mouse drift but stay
    // well under the smallest UI target (~24 px CSS).
    const TAP_DRAG_PX = 6
    // T-C2: long-press duration (ms) for touch-equivalent "shift-add".
    // 500 ms is the de-facto mobile long-press threshold (matches Android
    // text-selection, iOS context menu).  Movement >TAP_DRAG_PX or a
    // second pointer cancels the timer.
    const LONG_PRESS_MS = 500

    // Active pointer state.  We only pick on the primary pointer; secondary
    // pointers (multi-touch pinch/pan) are intentionally ignored by the
    // pick path — they belong to OrbitControls.
    let primaryPointerId = null
    let downX = 0
    let downY = 0
    let downShift = false
    let movedBeyondThreshold = false
    let longPressTimer = null
    let longPressFired = false
    let activePointerCount = 0

    function cancelLongPress() {
      if (longPressTimer !== null) {
        clearTimeout(longPressTimer)
        longPressTimer = null
      }
    }

    function setPointerFromEvent(ev) {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1
      pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1
    }

    // Run hover only for mouse / pen — there's no hover state on touch.
    function onPointerMove(ev) {
      // Track movement on the primary pointer (used for tap-vs-drag decision).
      if (ev.pointerId === primaryPointerId) {
        const dx = ev.clientX - downX
        const dy = ev.clientY - downY
        if (Math.hypot(dx, dy) > TAP_DRAG_PX) {
          movedBeyondThreshold = true
          cancelLongPress()
        }
      }

      // Skip hover for touch — touch has no concept of hover, and running
      // raycasts during a drag is wasted work that fights OrbitControls.
      if (ev.pointerType === 'touch') return

      const m = modeRef.current
      if (m === 'object') {
        clearHoverOverlay(stateRef.current)
        return
      }
      setPointerFromEvent(ev)
      raycaster.setFromCamera(pointer, camera)
      pickFeature(stateRef.current, raycaster, m, /*hover*/ true)
    }

    // Dispatch a pick at the current pointer position.  `shiftAdd` is true
    // when the user signalled add-to-selection (mouse shift held, or touch
    // long-press fired).
    function dispatchPick(ev, shiftAdd) {
      const m = modeRef.current
      setPointerFromEvent(ev)
      raycaster.setFromCamera(pointer, camera)

      if (m === 'object') {
        const visible = meshGroup.children.filter((mm) => mm.visible)
        const hits = raycaster.intersectObjects(visible, false)
        if (hits.length > 0) {
          const hitObj = hits[0].object
          let id = hitObj.userData.id
          // S2: InstancedMesh hit — map instanceId back to the Component.id
          // so the rest of the picking pipeline (gumball, selection highlight,
          // assembly editor) sees the same component-level id it expects.
          if (!id && hitObj.isInstancedMesh && hitObj.userData.componentIds) {
            const instanceId = hits[0].instanceId
            id = hitObj.userData.componentIds[instanceId] ?? null
          }
          setHudId(id)
          stateRef.current?.onPickRef?.(id)
        } else {
          setHudId(null)
          stateRef.current?.onPickRef?.(null)
        }
        return
      }
      // Feature mode → call onPickFeature with whatever's under the cursor.
      const hit = pickFeature(stateRef.current, raycaster, m, /*hover*/ false)
      if (hit && onPickFeatureRef.current) {
        onPickFeatureRef.current(hit.partId, hit.kind, hit.featureId, shiftAdd)
      } else if (!hit && onPickFeatureRef.current) {
        // Click in empty space + non-shift → clear selection.
        if (!shiftAdd) onPickFeatureRef.current(null, null, null, false)
      }
    }

    function onPointerDown(ev) {
      activePointerCount += 1
      // Multi-touch: a second pointer means pinch/pan — cancel any pending
      // pick + long-press.  Note: OrbitControls handles its own multi-touch
      // gesture state via the DOM element directly.
      if (activePointerCount > 1) {
        primaryPointerId = null
        cancelLongPress()
        movedBeyondThreshold = true // also kills any latent tap dispatch
        return
      }
      // Only the primary mouse button starts a pick.  Right / middle drag
      // is OrbitControls pan/dolly territory; pen barrel buttons fall
      // through too (we only pick on the contact tip).
      if (ev.pointerType === 'mouse' && ev.button !== 0) return

      primaryPointerId = ev.pointerId
      downX = ev.clientX
      downY = ev.clientY
      downShift = !!ev.shiftKey
      movedBeyondThreshold = false
      longPressFired = false
      cancelLongPress()

      // Long-press only makes sense for touch.  Mouse has shift-click already.
      if (ev.pointerType === 'touch') {
        longPressTimer = setTimeout(() => {
          longPressTimer = null
          if (!movedBeyondThreshold && primaryPointerId === ev.pointerId) {
            longPressFired = true
            // Fire pick immediately on long-press so the user gets feedback
            // without having to lift their finger.  We DO NOT clear the
            // primaryPointerId here: pointerup still runs but is a no-op
            // for the pick path (longPressFired short-circuits it).
            dispatchPick(ev, /*shiftAdd*/ true)
          }
        }, LONG_PRESS_MS)
      }
    }

    function onPointerUp(ev) {
      activePointerCount = Math.max(0, activePointerCount - 1)
      cancelLongPress()
      if (ev.pointerId !== primaryPointerId) return
      primaryPointerId = null

      // Long-press already fired the pick on the down-stroke — don't fire again.
      if (longPressFired) {
        longPressFired = false
        return
      }
      // Drag beyond threshold → OrbitControls handled it; no pick.
      if (movedBeyondThreshold) return
      // Multi-touch session that resolved (activePointerCount went >1 then
      // back to 0): movedBeyondThreshold was set on the second down, so we
      // never reach here in that case.

      // Mouse: preserve byte-for-byte the prior `click` handler semantics
      // (used `ev.shiftKey` at the click event).  Pointerup's shiftKey is
      // the equivalent.  Touch: downShift is always false (no shift key);
      // long-press is the touch path for add-to-selection.
      const shiftAdd = ev.pointerType === 'mouse' ? !!ev.shiftKey : downShift
      dispatchPick(ev, shiftAdd)
    }

    function onPointerCancel(ev) {
      activePointerCount = Math.max(0, activePointerCount - 1)
      if (ev.pointerId === primaryPointerId) {
        primaryPointerId = null
        cancelLongPress()
      }
    }

    renderer.domElement.addEventListener('pointermove', onPointerMove)
    renderer.domElement.addEventListener('pointerdown', onPointerDown)
    renderer.domElement.addEventListener('pointerup', onPointerUp)
    renderer.domElement.addEventListener('pointercancel', onPointerCancel)

    stateRef.current = {
      renderer, scene, camera, controls,
      meshGroup, edgeGroup, vertexGroup, overlayGroup, leaderGroup,
      raycaster, pointer,
      onPickRef: null, lastPartsKey: null,
      // Per-part aux geometry:
      perPart: new Map(), // partId → { faceMeshes, edgeLines: Line2[], vertexInstanced }
      fatLineMaterials: new Set(),
      // Hover state:
      hoverOverlay: null,
      // Selection overlays:
      selectionOverlays: [],
      // Leader-line state:
      leaderLine: null,
      leaderMidpoint: null,
      leaderText: '',
      setLeaderScreen: setLeaderHtml,
      // PBR / post-FX:
      composer,
      renderPass,
      bloomPass,
      pmrem,
      envTexture,
      gradientBg,
      // Lights + helpers — held so we can re-tune the shadow camera in the
      // parts-rebuild effect and dispose cleanly on unmount.
      key,
      ambient,
      fill,
      contactShadowPlane,
      grid,
      axes,
    }

    return () => {
      running = false
      ro.disconnect()
      cancelLongPress()
      renderer.domElement.removeEventListener('pointermove', onPointerMove)
      renderer.domElement.removeEventListener('pointerdown', onPointerDown)
      renderer.domElement.removeEventListener('pointerup', onPointerUp)
      renderer.domElement.removeEventListener('pointercancel', onPointerCancel)
      disposeAll(stateRef.current)
      try { composer.dispose?.() } catch { /* older three lacks dispose */ }
      try { bloomPass.dispose?.() } catch {}
      try { renderPass.dispose?.() } catch {}
      try { pmrem.dispose?.() } catch {}
      try { envTexture?.dispose?.() } catch {}
      try { gradientBg?.dispose?.() } catch {}
      try { contactShadowMat.dispose?.() } catch {}
      try { contactShadowPlane.geometry?.dispose?.() } catch {}
      controls.dispose()
      renderer.dispose()
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement)
      stateRef.current = null
    }
  }, [])

  // Keep onPick in a ref so the click handler always uses the latest.
  useEffect(() => {
    if (stateRef.current) stateRef.current.onPickRef = onPick
  }, [onPick])

  // ----- Rebuild meshes when parts change -----
  // Only mesh + bbox are built up-front. Edge/vertex aux is deferred to
  // `ensurePartAux` below — it's expensive (forces topology derivation per
  // part) and useless until the user enters a feature-pick mode or the
  // FeatureInspector opens.
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    const { meshGroup, edgeGroup, vertexGroup, camera, controls } = s

    // Dispose old meshes + aux.
    disposePartsAux(s)
    while (meshGroup.children.length) {
      const m = meshGroup.children[0]
      meshGroup.remove(m)
      m.geometry?.dispose()
      if (Array.isArray(m.material)) m.material.forEach((mat) => mat.dispose())
      else m.material?.dispose()
    }
    while (edgeGroup.children.length) edgeGroup.remove(edgeGroup.children[0])
    while (vertexGroup.children.length) vertexGroup.remove(vertexGroup.children[0])

    const entries = []

    // S2: Build instancing plan when assemblyComponents is provided and the
    // KERF_INSTANCING flag is on.  When instancing is active, identical parts
    // are batched into a single InstancedMesh (one draw call for N copies).
    // Singletons fall through to the regular per-Mesh path below.
    //
    // The plan uses assemblyComponents (raw parsed rows with file_id /
    // config_id) for grouping.  Geometries come from the matching `parts`
    // entries (keyed by componentId which is set by resolveAssemblyParts).
    const useInstancing = instancingEnabled() && Array.isArray(assemblyComponents) && assemblyComponents.length > 0

    // componentId → resolved {part, geometry, color, paletteIndex} for fast lookup.
    const partByComponentId = new Map()
    if (useInstancing) {
      ;(parts || []).forEach((part, i) => {
        if (!part?.geom || !part.componentId) return
        const geometry = resolveGeometry(part.geom)
        if (!geometry) return
        const color = part.color != null ? part.color : PALETTE[i % PALETTE.length]
        if (!partByComponentId.has(part.componentId)) {
          partByComponentId.set(part.componentId, { part, geometry, color, idx: i })
        }
      })
    }

    // Set of componentIds handled by InstancedMesh (won't create individual Mesh for these).
    const instancedComponentIds = new Set()

    if (useInstancing) {
      const { groups } = planInstances(assemblyComponents)
      for (const group of groups) {
        // Find the first componentId in this group that has a resolved geometry.
        let templateEntry = null
        for (const cid of group.componentIds) {
          if (partByComponentId.has(cid)) { templateEntry = partByComponentId.get(cid); break }
        }
        if (!templateEntry) continue  // no geometry available for this group yet — skip

        const { geometry, color } = templateEntry
        const material = new THREE.MeshStandardMaterial({
          color,
          metalness: 0.15,
          roughness: 0.55,
          flatShading: true,
          emissive: 0x000000,
        })

        const count = group.componentIds.length
        const instMesh = new THREE.InstancedMesh(geometry, material, count)
        instMesh.userData.kind = 'part-instanced'
        // Parallel list: instanceId → Component.id so pick handlers can look up
        // the right component.
        instMesh.userData.componentIds = group.componentIds
        // Shadow casting on for the InstancedMesh — the contact-shadow plane
        // collects these to give the model a grounded look.
        instMesh.castShadow = true
        instMesh.receiveShadow = true

        group.transforms.forEach((m4, idx) => {
          instMesh.setMatrixAt(idx, m4)
        })
        instMesh.instanceMatrix.needsUpdate = true

        // Compute a bounding box for the whole instanced set (union of all instances).
        instMesh.computeBoundingBox()

        meshGroup.add(instMesh)
        entries.push({ id: group.key, geometry })

        // Mark all these componentIds as handled.
        for (const cid of group.componentIds) instancedComponentIds.add(cid)
      }
    }

    // Per-Mesh path: handles singletons (instancing mode) OR all parts (non-instancing).
    ;(parts || []).forEach((part, i) => {
      if (!part?.geom) return
      // Skip parts whose componentId was already batched into an InstancedMesh.
      if (useInstancing && part.componentId && instancedComponentIds.has(part.componentId)) return

      const geometry = resolveGeometry(part.geom)
      if (!geometry) return
      const color = part.color != null ? part.color : PALETTE[i % PALETTE.length]
      const material = new THREE.MeshStandardMaterial({
        color,
        metalness: 0.15,
        roughness: 0.55,
        flatShading: true,
        emissive: 0x000000,
      })
      const mesh = new THREE.Mesh(geometry, material)
      mesh.userData.id = part.id
      mesh.userData.kind = 'part'
      mesh.userData.componentId = part.componentId || null
      // Shadow flags — the contact-shadow plane grounds the model and parts
      // sharing the scene cast onto each other (intended for assemblies).
      mesh.castShadow = true
      mesh.receiveShadow = true
      meshGroup.add(mesh)
      entries.push({ id: part.id, geometry })

      // Bounding box for vertex sphere sizing — cheap, no topology.
      const bb = new THREE.Box3().setFromBufferAttribute(geometry.getAttribute('position'))
      // Lazy aux slot: edges/vertices populated on first feature-mode entry.
      // `topology` stays null until ensurePartAux fills it in.
      const partAux = {
        edgeLines: [], vertexInstanced: null, edgeMaterials: [],
        bbox: bb, topology: null, auxBuilt: false,
      }
      s.perPart.set(part.id, partAux)
    })

    // Initial visibility on aux groups based on mode. If we're already in a
    // non-object mode (rare on first mount, common on parts-change while a
    // measure mode is active) we need to build the aux now.
    applyModeVisibility(s, modeRef.current)
    if (modeRef.current !== 'object') ensureAllAux(s, parts, topologies)

    // Auto-frame on a *fresh* parts swap (different ids than last time).
    const key = (parts || []).map((p) => p.id).join('|')
    if (key && key !== s.lastPartsKey) {
      const box = combinedBoundingBox(entries)
      if (box) {
        const center = new THREE.Vector3()
        box.getCenter(center)
        const size = new THREE.Vector3()
        box.getSize(size)
        const radius = Math.max(size.x, size.y, size.z) || 50
        const dist = radius * 2.2 + 30
        camera.position.set(center.x + dist, center.y + dist, center.z + dist * 0.8)
        camera.near = Math.max(0.1, radius / 100)
        camera.far = Math.max(2000, radius * 50)
        camera.updateProjectionMatrix()
        controls.target.copy(center)
        controls.update()

        // Re-tune the key-light shadow camera to fit the model.  An oversized
        // shadow camera spreads the 1024² shadow map over too much area and
        // looks pixelated; a tight one clips.  We use 1.4× the largest axis
        // as the half-extent so there's a small margin for OrbitControls
        // panning before clipping shows up.
        if (s.key && s.key.shadow && s.key.shadow.camera) {
          const half = radius * 1.4
          s.key.shadow.camera.left = -half
          s.key.shadow.camera.right = half
          s.key.shadow.camera.top = half
          s.key.shadow.camera.bottom = -half
          s.key.shadow.camera.near = Math.max(0.1, radius / 50)
          s.key.shadow.camera.far = radius * 8 + 100
          s.key.shadow.camera.updateProjectionMatrix()
        }
        // Drop the contact-shadow plane just under the model bottom.  We
        // subtract a tiny epsilon so the plane never z-fights with parts
        // that rest exactly on Y=0.
        if (s.contactShadowPlane) {
          s.contactShadowPlane.position.y = box.min.y - radius * 0.0005
          // Scale the plane to comfortably contain the model + soft halo.
          const scale = Math.max(1, radius * 0.04)
          s.contactShadowPlane.scale.setScalar(scale)
        }
      }
      s.lastPartsKey = key
    }
  }, [parts, topologies, assemblyComponents])

  // ----- Visibility toggling -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    const hidden = hiddenIds || new Set()
    s.meshGroup.children.forEach((m) => {
      // Use setUserVisible so cullByFrustum can distinguish "hidden by user"
      // from "hidden by frustum" and never accidentally un-hides user-hidden
      // meshes on the next frame.
      //
      // S2 InstancedMesh: Three.js doesn't support per-instance visibility
      // via a simple flag.  Our policy: if ALL instances in this batch are
      // hidden, hide the whole InstancedMesh; if ANY are visible, keep it
      // visible (individual hidden instances remain visible within the batch —
      // acceptable trade-off, rare in practice because users hide whole groups).
      if (m.isInstancedMesh) {
        const cids = m.userData.componentIds || []
        const allHidden = cids.length > 0 && cids.every((cid) => hidden.has(cid))
        setUserVisible(m, !allHidden)
        return
      }
      const id = m.userData.id ?? m.userData.componentId
      const userVisible = id ? !hidden.has(id) : true
      setUserVisible(m, userVisible)
    })
    // Hide aux for hidden parts too.
    for (const [partId, aux] of s.perPart.entries()) {
      const visible = !hidden.has(partId)
      for (const l of aux.edgeLines) l.visible = visible
      if (aux.vertexInstanced) aux.vertexInstanced.visible = visible
    }
  }, [hiddenIds, parts])

  // ----- Highlight selected (object mode) -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    s.meshGroup.children.forEach((m) => {
      if (m.isInstancedMesh) {
        // S2: For InstancedMesh we use per-instance color to highlight.
        // We reset all instances to white (multiplicative identity) then
        // tint the selected one with the emissive-equivalent color.
        const cids = m.userData.componentIds
        if (!cids) return
        // Ensure instanceColor buffer exists.
        if (!m.instanceColor) {
          const colors = new Float32Array(m.count * 3)
          colors.fill(1) // white = no tint
          m.instanceColor = new THREE.InstancedBufferAttribute(colors, 3)
          m.material.vertexColors = false // keep base color; instance color multiplies
        }
        for (let i = 0; i < m.count; i++) {
          const cid = cids[i]
          const isSel = cid === selectedId
            || (selectedComponentId && cid === selectedComponentId)
          // Tint: emissive highlight → shift toward warm yellow
          if (isSel) {
            const h = HIGHLIGHT_EMISSIVE
            m.instanceColor.setXYZ(i,
              1 + ((h >> 16) & 0xff) / 255,
              1 + ((h >> 8) & 0xff) / 255,
              1 + ((h) & 0xff) / 255,
            )
          } else {
            m.instanceColor.setXYZ(i, 1, 1, 1)
          }
        }
        m.instanceColor.needsUpdate = true
        return
      }
      const isSel = m.userData.id === selectedId
        || (selectedComponentId && m.userData.componentId === selectedComponentId)
      if (m.material && 'emissive' in m.material) {
        m.material.emissive.setHex(isSel ? HIGHLIGHT_EMISSIVE : 0x000000)
      }
    })
  }, [selectedId, selectedComponentId, parts])

  // ----- Mode switch: show/hide aux groups + clear hover -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    if (mode !== 'object') ensureAllAux(s, parts, topologies)
    applyModeVisibility(s, mode)
    clearHoverOverlay(s)
  }, [mode, parts, topologies])

  // ----- Tone-mapping exposure -----
  // Pushes the slider value straight into the WebGLRenderer; the render loop
  // picks it up on the next frame without a React re-render.
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    s.renderer.toneMappingExposure = exposure
  }, [exposure])

  // ----- Bloom toggle -----
  // We re-route the loop to skip composer when bloom is off (handled in the
  // render loop above by inspecting bloomPass.enabled).  This effect just
  // flips the flag.
  useEffect(() => {
    const s = stateRef.current
    if (!s || !s.bloomPass) return
    s.bloomPass.enabled = bloomOn
  }, [bloomOn])

  // ----- HDRI-as-background toggle -----
  // When the user wants the env-map to also be the background (typical for
  // hero shots), we swap scene.background to the env texture.  Off → restore
  // the studio gradient.
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    if (hdriBackground && s.envTexture) {
      s.scene.background = s.envTexture
    } else if (s.gradientBg) {
      s.scene.background = s.gradientBg
    } else {
      s.scene.background = new THREE.Color(BG_COLOR)
    }
  }, [hdriBackground])

  // ----- Daylight lighting mode -----
  // Default rig: balanced 3-point (ambient 0.25, white key 2.2, cool
  // fill 0.8). Daylight: a single dominant warm sun with crisp shadows
  // and the fill/ambient pulled right down — a hard, outdoor look.
  useEffect(() => {
    const s = stateRef.current
    if (!s || !s.key) return
    if (daylight) {
      s.key.color.setHex(0xfff2dd)
      s.key.intensity = 4.4
      if (s.ambient) s.ambient.intensity = 0.08
      if (s.fill) s.fill.intensity = 0.12
    } else {
      s.key.color.setHex(0xffffff)
      s.key.intensity = 2.2
      if (s.ambient) s.ambient.intensity = 0.25
      if (s.fill) s.fill.intensity = 0.8
    }
  }, [daylight])

  // ----- Selection overlays + leader line -----
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    // Clear previous selection overlays.
    for (const o of s.selectionOverlays) {
      s.overlayGroup.remove(o)
      o.geometry?.dispose?.()
      if (Array.isArray(o.material)) o.material.forEach((mm) => mm.dispose())
      else o.material?.dispose?.()
    }
    s.selectionOverlays = []
    // Clear leader.
    if (s.leaderLine) {
      s.leaderGroup.remove(s.leaderLine)
      s.leaderLine.geometry?.dispose?.()
      s.leaderLine.material?.dispose?.()
      s.leaderLine = null
      s.leaderMidpoint = null
      s.leaderText = ''
    }

    // Build new overlays. We need aux populated so face/edge/vertex overlays
    // and the per-part bbox are available even if the user clicked into a
    // mode without entering it via the toolbar (e.g. selection persisted
    // across parts changes).
    if (selectedFeatures.length > 0) ensureAllAux(s, parts, topologies)
    for (const sel of selectedFeatures) {
      const part = (parts || []).find((p) => p.id === sel.partId)
      const topology = topologies.get(sel.partId)
      if (!part || !topology) continue
      const overlay = buildSelectionOverlay(sel, topology, s)
      if (overlay) {
        s.overlayGroup.add(overlay)
        s.selectionOverlays.push(overlay)
      }
    }

    // Build leader line + distance text if 2 selections.
    if (selectedFeatures.length === 2) {
      const [a, b] = selectedFeatures
      const da = lookupFeature(a, topologies)
      const db = lookupFeature(b, topologies)
      if (da && db) {
        const r = distance(
          { kind: a.kind, data: da, partId: a.partId },
          { kind: b.kind, data: db, partId: b.partId },
        )
        const lg = new LineGeometry()
        lg.setPositions([
          r.points[0][0], r.points[0][1], r.points[0][2],
          r.points[1][0], r.points[1][1], r.points[1][2],
        ])
        const mat = new LineMaterial({
          color: KERF_YELLOW,
          linewidth: 2,
          transparent: true,
          opacity: 0.95,
          dashed: true,
          dashScale: 1,
          dashSize: 1.5,
          gapSize: 1,
          depthTest: false,
        })
        const w = s.renderer.domElement.clientWidth || 1
        const h = s.renderer.domElement.clientHeight || 1
        mat.resolution.set(w, h)
        s.fatLineMaterials.add(mat)
        const line = new Line2(lg, mat)
        line.computeLineDistances()
        line.renderOrder = 999
        s.leaderGroup.add(line)
        s.leaderLine = line
        s.leaderMidpoint = new THREE.Vector3(
          (r.points[0][0] + r.points[1][0]) / 2,
          (r.points[0][1] + r.points[1][1]) / 2,
          (r.points[0][2] + r.points[1][2]) / 2,
        )
        s.leaderText = formatDistance(r.value)
      }
    }
  }, [selectedFeatures, parts, topologies])

  // ----- Zebra / reflection-line overlay -----
  // When zebraOn is true we swap every mesh in meshGroup to a ZebraMaterial
  // and store the original material so we can restore it on toggle-off.
  // We do NOT touch edge/vertex aux, overlays, or leader lines — those are
  // unaffected by the surface analysis overlay.
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    for (const mesh of s.meshGroup.children) {
      if (zebraOn) {
        if (!mesh.userData._origMaterial) {
          mesh.userData._origMaterial = mesh.material
        }
        // Create a fresh ZebraMaterial per mesh so each can be disposed
        // independently on parts rebuild.
        const zm = createZebraMaterial()
        mesh.material = zm
      } else {
        if (mesh.userData._origMaterial) {
          mesh.material.dispose()
          mesh.material = mesh.userData._origMaterial
          mesh.userData._origMaterial = null
        }
      }
    }
  }, [zebraOn, parts])

  // ----- Hero-shot capture (shared between UI button + imperative API) -----
  // Defined here as a closure so the UI button and the ref both invoke the
  // same path.  Hides UI chrome by walking the live state graph rather than
  // mutating React state — avoids a re-render mid-capture.
  async function doCaptureHeroShot(opts = {}) {
    const s = stateRef.current
    if (!s) return null
    // Build the chrome-hide list: aux groups + grid + axes + leader line +
    // hover overlay + any DFM markers + any current selection overlays.
    // The contact-shadow plane is NOT hidden (it grounds the model).
    const hideTargets = []
    if (s.grid) hideTargets.push(s.grid)
    if (s.axes) hideTargets.push(s.axes)
    if (s.leaderGroup) hideTargets.push(s.leaderGroup)
    if (s.overlayGroup) hideTargets.push(s.overlayGroup)
    if (s.edgeGroup) hideTargets.push(s.edgeGroup)
    if (s.vertexGroup) hideTargets.push(s.vertexGroup)
    setHeroBusy(true)
    try {
      // Suppress the leader HTML overlay too — it's outside the canvas.
      const prevSetLeader = s.setLeaderScreen
      s.setLeaderScreen = () => {}
      try {
        return await _captureHeroShot({
          renderer: s.renderer,
          scene: s.scene,
          camera: s.camera,
          composer: s.bloomPass && s.bloomPass.enabled ? s.composer : null,
          width: opts.width ?? HERO_DEFAULT_W,
          height: opts.height ?? HERO_DEFAULT_H,
          samples: opts.samples ?? HERO_DEFAULT_SAMPLES,
          transparent: !!opts.transparent,
          background: opts.background,
          hideTargets,
        })
      } finally {
        s.setLeaderScreen = prevSetLeader
      }
    } finally {
      setHeroBusy(false)
    }
  }

  // ----- Imperative handle: expose canvas snapshot for thumbnails -----
  // The Editor calls this after a successful save (debounced) to grab a
  // small JPEG of the current scene. We render once more synchronously
  // (so post-save geometry is on-screen) and crop to a square through an
  // offscreen canvas before encoding.
  /**
   * Imperative API surface exposed to the parent via ref:
   *
   *   snapshot({ size, quality }) → Promise<Blob | null>
   *     Existing thumbnail capture (small JPEG, center-cropped to square).
   *     Unchanged from prior behaviour.
   *
   *   recordTurntable(opts) → Promise<string[]>
   *     Existing 360° orbit capture; delegates to turntableRender.js.
   *
   *   renderHeroSet(opts) → Promise<{ stills, turntable }>
   *     Existing 4-still + N-frame turntable capture; delegates to
   *     heroRender.js.
   *
   *   captureHeroShot({ width, height, samples, transparent, background })
   *     → Promise<Blob | null>
   *     NEW.  One-click marketing-quality single-image capture.  Defaults to
   *     2048×2048 / 4 supersample passes.  UI chrome (grid, axes, hover
   *     overlays, leader line, DFM markers) is hidden for the duration of
   *     the capture and restored afterwards (even on error).  Returns a
   *     PNG Blob; the caller is responsible for download / upload.
   *
   *   setEnvironmentHdr(url, [opts]) → Promise<void>
   *     NEW.  Swap the synthetic RoomEnvironment for a real .hdr asset
   *     loaded via RGBELoader.  Passing null reverts to the synthetic env.
   *
   *   setBloomEnabled(on) → void
   *   setBloomStrength(strength) → void
   *   setExposure(value) → void
   *     NEW.  Programmatic counterparts to the UI toggles for tests /
   *     keybindings / other components that want to drive PBR knobs.
   *
   *   setDfmIssues(issues) → void
   *     Existing DFM overlay attach/detach.
   */
  useImperativeHandle(ref, () => ({
    /**
     * Capture the rendered scene as a JPEG Blob.
     * @param {{ size?: number, quality?: number }} [opts]
     * @returns {Promise<Blob|null>}
     */
    snapshot: ({ size = 512, quality = 0.7 } = {}) =>
      new Promise((resolve) => {
        const s = stateRef.current
        if (!s) return resolve(null)
        // Wait one frame so any pending layout/render is on the canvas
        // before we read pixels (preserveDrawingBuffer is false, so the
        // back-buffer would otherwise be cleared between paints).
        requestAnimationFrame(() => {
          try {
            // Force a render *now* so the buffer has fresh pixels we can
            // read in the same frame as toBlob().
            s.renderer.render(s.scene, s.camera)
            const src = s.renderer.domElement
            const sw = src.width
            const sh = src.height
            if (!sw || !sh) return resolve(null)

            // Center-crop to the largest square that fits, then resize to `size`.
            const off = document.createElement('canvas')
            off.width = size
            off.height = size
            const ctx = off.getContext('2d')
            if (!ctx) return resolve(null)
            const side = Math.min(sw, sh)
            const sx = (sw - side) / 2
            const sy = (sh - side) / 2
            ctx.drawImage(src, sx, sy, side, side, 0, 0, size, size)
            off.toBlob((blob) => resolve(blob), 'image/jpeg', quality)
          } catch {
            resolve(null)
          }
        })
      }),

    /**
     * Orbit the camera 360° and capture each frame as a PNG data-URL.
     * Delegates to turntableRender.recordTurntable() using the live scene/camera/renderer.
     * @param {object} [opts]  See turntableRender.recordTurntable opts.
     * @returns {Promise<string[]>}
     */
    recordTurntable: (opts = {}) => {
      const s = stateRef.current
      if (!s) return Promise.resolve([])
      return _recordTurntable(s.scene, s.camera, s.renderer, opts)
    },
    renderHeroSet: (opts = {}) => { const s = stateRef.current; if (!s) return Promise.resolve({ stills: [], turntable: [] }); return _renderHeroSet(s.scene, s.camera, s.renderer, opts) },

    /**
     * captureHeroShot — marketing-quality single image.
     *
     * @param {object} [opts]
     * @param {number}  [opts.width=2048]   Output width (px).
     * @param {number}  [opts.height=2048]  Output height (px).
     * @param {number}  [opts.samples=4]    Supersampling passes.
     * @param {boolean} [opts.transparent=false]  Transparent PNG background.
     * @param {number}  [opts.background]   Hex color override for background.
     * @returns {Promise<Blob|null>}
     */
    captureHeroShot: (opts = {}) => doCaptureHeroShot(opts),

    /**
     * setEnvironmentHdr — swap scene.environment to a real .hdr loaded via
     * RGBELoader.  Pass null to revert to the synthetic RoomEnvironment.
     *
     * @param {string|null} url
     * @returns {Promise<void>}
     */
    setEnvironmentHdr: (url) => new Promise((resolve, reject) => {
      const s = stateRef.current
      if (!s) return resolve()
      if (!url) {
        // Revert: rebuild from RoomEnvironment if we previously swapped out.
        try {
          const tex = s.pmrem.fromScene(new RoomEnvironment(0.5), 0.04).texture
          // Dispose the old environment to release the GPU texture.
          s.envTexture?.dispose?.()
          s.envTexture = tex
          s.scene.environment = tex
          if (hdriBackground) s.scene.background = tex
        } catch (e) {
          return reject(e)
        }
        return resolve()
      }
      const loader = new RGBELoader()
      loader.load(url, (hdrTex) => {
        try {
          const pmremTex = s.pmrem.fromEquirectangular(hdrTex).texture
          hdrTex.dispose()
          s.envTexture?.dispose?.()
          s.envTexture = pmremTex
          s.scene.environment = pmremTex
          if (hdriBackground) s.scene.background = pmremTex
          resolve()
        } catch (e) {
          reject(e)
        }
      }, undefined, (err) => reject(err))
    }),

    /** Toggle bloom on/off programmatically. */
    setBloomEnabled: (on) => { setBloomOn(!!on) },

    /** Override bloom strength (default 0.55). */
    setBloomStrength: (strength) => {
      const s = stateRef.current
      if (!s || !s.bloomPass) return
      s.bloomPass.strength = Number(strength) || 0
    },

    /** Override tone-mapping exposure (0.2 .. 2.0 typical). */
    setExposure: (value) => { setExposure(Number(value) || DEFAULT_EXPOSURE) },

    /** Toggle the HDRI-as-background mode. */
    setHdriBackground: (on) => { setHdriBackground(!!on) },

    /** Paint DFM issue markers in the viewport. Pass null/[] to clear. */
    setDfmIssues: (issues) => { const s = stateRef.current; if (!s) return; issues?.length ? attachDfmOverlay(s.scene, s.camera, s.renderer, issues) : detachDfmOverlay() },
  }), [hdriBackground])

  // HUD shows the prop-driven selection if present, else the last clicked id.
  const displayedId = selectedId ?? hudId

  return (
    <div className={`relative ${className}`}>
      <div ref={mountRef} className="absolute inset-0 overflow-hidden" />
      {leaderHtml && (
        <div
          className="absolute pointer-events-none px-1.5 py-0.5 rounded bg-kerf-300 text-ink-950 text-[10px] font-mono font-semibold shadow-md"
          style={{ left: leaderHtml.x, top: leaderHtml.y, transform: 'translate(-50%, -50%)' }}
        >
          {leaderHtml.text}
        </div>
      )}
      {mode === 'object' && (displayedId ? (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-ink-900/80 border border-ink-700 text-xs font-mono text-kerf-300 backdrop-blur">
          {displayedId}
        </div>
      ) : (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-ink-900/60 border border-ink-800 text-xs font-mono text-ink-400 backdrop-blur">
          click a part to reference it
        </div>
      ))}
      {mode !== 'object' && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-ink-900/80 border border-ink-700 text-[11px] font-mono text-kerf-300 backdrop-blur">
          {mode} mode · click to pick · shift+click to add
        </div>
      )}
      {/* Standalone exposure control — top-right, on its own, with a sun
          icon. (Was a cramped "EV" pill stacked among toggle buttons.) */}
      <div className="absolute top-3 right-3 z-10 flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-ink-900/85 border border-ink-700 backdrop-blur shadow-lg shadow-black/30">
        <Sun size={13} className="text-kerf-300/90" />
        <label
          className="text-[10px] uppercase tracking-wider font-mono text-ink-400"
          htmlFor="kerf-exposure-slider"
        >
          Exposure
        </label>
        <input
          id="kerf-exposure-slider"
          type="range"
          min="0.2"
          max="2.0"
          step="0.05"
          value={exposure}
          onChange={(e) => setExposure(parseFloat(e.target.value) || DEFAULT_EXPOSURE)}
          title="Tone-mapping exposure (ACES filmic)"
          className="w-24 accent-kerf-300"
        />
        <span className="text-[10px] font-mono text-ink-300 w-8 text-right tabular-nums">
          {exposure.toFixed(2)}
        </span>
      </div>

      {/* Render-types dropdown — one tidy menu replacing the old
          scattered floating Zebra / Bloom / HDRI toggle buttons. */}
      <div className="absolute top-14 right-3 z-10">
        <button
          type="button"
          onClick={() => setRenderMenuOpen((v) => !v)}
          title="Render options"
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-ink-900/85 border border-ink-700 text-[11px] font-mono text-ink-300 hover:text-kerf-300 hover:border-kerf-300/50 backdrop-blur shadow-lg shadow-black/30"
        >
          <SlidersHorizontal size={13} />
          Render
          <ChevronDown
            size={12}
            className={`text-ink-500 transition-transform ${renderMenuOpen ? 'rotate-180' : ''}`}
          />
        </button>
        {renderMenuOpen && (
          <>
            <div
              className="fixed inset-0 z-0"
              onClick={() => setRenderMenuOpen(false)}
              aria-hidden
            />
            <div className="absolute right-0 mt-1.5 z-10 w-52 rounded-lg border border-ink-700 bg-ink-900 shadow-2xl shadow-black/50 overflow-hidden">
              <div className="px-3 py-1.5 border-b border-ink-800 text-[10px] uppercase tracking-wider text-ink-500 font-semibold">
                Render mode
              </div>
              {[
                { on: daylight, set: () => setDaylight((v) => !v), label: 'Daylight', hint: 'Single strong sun' },
                { on: zebraOn, set: () => setZebraOn((v) => !v), label: 'Zebra', hint: 'Class-A surface lines' },
                { on: bloomOn, set: () => setBloomOn((v) => !v), label: 'Bloom', hint: 'Gem / edge glow' },
                { on: hdriBackground, set: () => setHdriBackground((v) => !v), label: 'HDRI background', hint: 'Env map as backdrop' },
              ].map((it) => (
                <button
                  key={it.label}
                  type="button"
                  onClick={it.set}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-ink-800"
                >
                  <span
                    className={`grid place-items-center w-4 h-4 rounded border flex-shrink-0 ${
                      it.on
                        ? 'bg-kerf-300 border-kerf-300 text-ink-950'
                        : 'border-ink-600 text-transparent'
                    }`}
                  >
                    <Check size={11} strokeWidth={3} />
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-[12px] text-ink-100">{it.label}</span>
                    <span className="block text-[10px] text-ink-500">{it.hint}</span>
                  </span>
                </button>
              ))}
              <div className="border-t border-ink-800 my-1" />
              <button
                type="button"
                onClick={() => { setRenderMenuOpen(false); setShowHeroPanel(true) }}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-ink-800"
              >
                <span className="grid place-items-center w-4 h-4 rounded border border-kerf-300/60 flex-shrink-0 text-kerf-300">
                  ✦
                </span>
                <span className="flex-1 min-w-0">
                  <span className="block text-[12px] text-kerf-300 font-semibold">Hero Render…</span>
                  <span className="block text-[10px] text-ink-500">High-fidelity PNG + EXR export</span>
                </span>
              </button>
            </div>
          </>
        )}
      </div>
      {showHeroPanel && (
        <HeroRenderPanel
          onClose={() => setShowHeroPanel(false)}
          projectId={projectId}
          rendererRef={stateRef}
        />
      )}
    </div>
  )
}

export default forwardRef(Renderer)

// ---------------------------------------------------------------------------
// Helpers using the renderer's ref state object.

/**
 * Build a vertical gradient texture used as the default studio background.
 * Top → bg_top (a hair warmer/lighter), bottom → bg_bottom.  Built with a
 * Canvas2D context (already required elsewhere for thumbnails) so we don't
 * need a shader background or an external image.  Returns null if the host
 * environment can't create a canvas — caller falls back to a solid color.
 *
 * The resulting CanvasTexture is wrapped in repeat-mode + sRGB color space
 * so PBR materials see a colorimetrically-correct background colour.
 */
function _makeStudioGradientTexture(bottomHex, topHex) {
  if (typeof document === 'undefined' || typeof document.createElement !== 'function') {
    return null
  }
  try {
    const canvas = document.createElement('canvas')
    canvas.width = 2
    canvas.height = 256
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    const grad = ctx.createLinearGradient(0, 0, 0, 256)
    grad.addColorStop(0, '#' + topHex.toString(16).padStart(6, '0'))
    grad.addColorStop(1, '#' + bottomHex.toString(16).padStart(6, '0'))
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, 2, 256)
    const tex = new THREE.CanvasTexture(canvas)
    if ('colorSpace' in tex) tex.colorSpace = THREE.SRGBColorSpace
    tex.needsUpdate = true
    return tex
  } catch {
    return null
  }
}

function applyModeVisibility(s, mode) {
  if (!s) return
  s.edgeGroup.visible = mode === 'edge'
  s.vertexGroup.visible = mode === 'vertex'
  // Face overlay & leader line are always rendered when present.
  s.overlayGroup.visible = true
  s.leaderGroup.visible = true
}

// Build edge-line + vertex-instance aux for one part on demand. Idempotent:
// repeated calls after the first do nothing. `topologies` is the lazy Map
// from getTopologyLazy — calling `.get(partId)` here is the trigger that
// derives topology for the part.
function ensurePartAux(s, part, topologies) {
  if (!s || !part) return
  const aux = s.perPart.get(part.id)
  if (!aux || aux.auxBuilt) return
  const topology = topologies.get(part.id) || { faces: [], edges: [], vertices: [] }
  aux.topology = topology
  aux.auxBuilt = true

  const w = s.renderer.domElement.clientWidth || 1
  const h = s.renderer.domElement.clientHeight || 1
  const bb = aux.bbox
  const size = bb ? new THREE.Vector3() : null
  if (bb) bb.getSize(size)
  const diag = size ? Math.hypot(size.x, size.y, size.z) || 50 : 50
  const sphereR = Math.min(2.0, Math.max(0.3, diag * 0.005))

  for (const e of topology.edges) {
    const lg = new LineGeometry()
    lg.setPositions([e.a[0], e.a[1], e.a[2], e.b[0], e.b[1], e.b[2]])
    const mat = new LineMaterial({
      color: INK_300,
      linewidth: 3,
      transparent: true,
      opacity: 0.95,
      depthTest: true,
    })
    mat.resolution.set(w, h)
    s.fatLineMaterials.add(mat)
    const line = new Line2(lg, mat)
    line.computeLineDistances()
    line.userData = { partId: part.id, kind: 'edge', featureId: e.id }
    aux.edgeLines.push(line)
    aux.edgeMaterials.push(mat)
    s.edgeGroup.add(line)
  }

  if (topology.vertices.length > 0) {
    const sg = new THREE.SphereGeometry(sphereR, 12, 8)
    const sm = new THREE.MeshBasicMaterial({ color: INK_300 })
    const inst = new THREE.InstancedMesh(sg, sm, topology.vertices.length)
    const dummy = new THREE.Object3D()
    topology.vertices.forEach((v, k) => {
      dummy.position.set(v.position[0], v.position[1], v.position[2])
      dummy.updateMatrix()
      inst.setMatrixAt(k, dummy.matrix)
    })
    inst.instanceMatrix.needsUpdate = true
    inst.userData = {
      partId: part.id,
      kind: 'vertex',
      vertexIds: topology.vertices.map((v) => v.id),
    }
    aux.vertexInstanced = inst
    s.vertexGroup.add(inst)
  }
}

function ensureAllAux(s, parts, topologies) {
  if (!s) return
  for (const part of parts || []) ensurePartAux(s, part, topologies)
}

function clearHoverOverlay(s) {
  if (!s) return
  if (s.hoverOverlay) {
    if (s.hoverOverlay.parent) s.hoverOverlay.parent.remove(s.hoverOverlay)
    s.hoverOverlay.geometry?.dispose?.()
    if (Array.isArray(s.hoverOverlay.material)) s.hoverOverlay.material.forEach((m) => m.dispose())
    else s.hoverOverlay.material?.dispose?.()
    s.hoverOverlay = null
  }
}

// pickFeature: raycast against whichever aux geometry is appropriate for the
// current mode and either install a hover highlight (hover=true) OR return
// the hit info for click handling.
function pickFeature(s, raycaster, mode, hover) {
  if (!s) return null
  if (mode === 'face') {
    // Raycast against meshes; convert hit triangle → owning face id by
    // walking the part's topology and finding the face whose triangles
    // contain the hit point. Cheap centroid match.
    const visibleMeshes = s.meshGroup.children.filter((m) => m.visible)
    const hits = raycaster.intersectObjects(visibleMeshes, false)
    if (hits.length === 0) {
      if (hover) clearHoverOverlay(s)
      return null
    }
    const hit = hits[0]
    const partId = hit.object.userData.id
    // Find the face whose triangle has the closest centroid to the hit point.
    // (Simplest robust mapping; we don't need the exact triangle, just the
    // face cluster.)
    const topology = getCachedTopologyForPart(s, partId)
    if (!topology || topology.faces.length === 0) return null
    const p = hit.point
    let best = null
    let bestDist = Infinity
    for (const f of topology.faces) {
      // Quick centroid heuristic + plane test: face whose plane the point
      // lies closest to and whose centroid is nearest.
      const dx = f.centroid[0] - p.x
      const dy = f.centroid[1] - p.y
      const dz = f.centroid[2] - p.z
      const d = dx * dx + dy * dy + dz * dz
      if (d < bestDist) { bestDist = d; best = f }
    }
    if (!best) return null
    if (hover) {
      installFaceHover(s, best)
      return null
    }
    return { partId, kind: 'face', featureId: best.id }
  }
  if (mode === 'edge') {
    const visible = s.edgeGroup.children.filter((m) => m.visible)
    const hits = raycaster.intersectObjects(visible, false)
    if (hits.length === 0) {
      if (hover) clearLineHover(s)
      return null
    }
    const hit = hits[0]
    const ud = hit.object.userData
    if (hover) {
      hoverLine(s, hit.object)
      return null
    }
    return { partId: ud.partId, kind: 'edge', featureId: ud.featureId }
  }
  if (mode === 'vertex') {
    const visible = s.vertexGroup.children.filter((m) => m.visible)
    const hits = raycaster.intersectObjects(visible, false)
    if (hits.length === 0) {
      if (hover) clearVertexHover(s)
      return null
    }
    const hit = hits[0]
    const inst = hit.object
    const id = inst.userData.vertexIds[hit.instanceId]
    if (hover) {
      hoverInstance(s, inst, hit.instanceId)
      return null
    }
    return { partId: inst.userData.partId, kind: 'vertex', featureId: id }
  }
  return null
}

function installFaceHover(s, face) {
  clearHoverOverlay(s)
  const g = geometryFromFaceTriangles(face.triangles)
  const m = new THREE.MeshBasicMaterial({
    color: KERF_YELLOW,
    transparent: true,
    opacity: 0.4,
    depthTest: false,
    side: THREE.DoubleSide,
  })
  const mesh = new THREE.Mesh(g, m)
  mesh.renderOrder = 998
  s.overlayGroup.add(mesh)
  s.hoverOverlay = mesh
}

// Track currently-hovered line so we can revert its color on next move.
function hoverLine(s, line) {
  if (s._hoveredLine === line) return
  if (s._hoveredLine) {
    const mat = s._hoveredLine.material
    if (mat && mat.color) mat.color.setHex(INK_300)
  }
  s._hoveredLine = line
  if (line.material && line.material.color) line.material.color.setHex(KERF_YELLOW)
}
function clearLineHover(s) {
  if (s._hoveredLine) {
    const mat = s._hoveredLine.material
    if (mat && mat.color) mat.color.setHex(INK_300)
    s._hoveredLine = null
  }
}

// For instanced spheres, change just the hovered instance's color via
// instanceColor. Cheap and avoids material churn.
function hoverInstance(s, inst, instanceId) {
  if (!inst.instanceColor) {
    const colors = new Float32Array(inst.count * 3)
    for (let i = 0; i < inst.count; i++) {
      colors[i * 3] = ((INK_300 >> 16) & 0xff) / 255
      colors[i * 3 + 1] = ((INK_300 >> 8) & 0xff) / 255
      colors[i * 3 + 2] = (INK_300 & 0xff) / 255
    }
    inst.instanceColor = new THREE.InstancedBufferAttribute(colors, 3)
    inst.material.vertexColors = true
    inst.material.needsUpdate = true
  }
  if (s._hoveredInstance && (s._hoveredInstance.inst !== inst || s._hoveredInstance.id !== instanceId)) {
    const { inst: oldInst, id: oldId } = s._hoveredInstance
    if (oldInst.instanceColor) {
      oldInst.instanceColor.setXYZ(
        oldId,
        ((INK_300 >> 16) & 0xff) / 255,
        ((INK_300 >> 8) & 0xff) / 255,
        (INK_300 & 0xff) / 255,
      )
      oldInst.instanceColor.needsUpdate = true
    }
  }
  inst.instanceColor.setXYZ(
    instanceId,
    ((KERF_YELLOW >> 16) & 0xff) / 255,
    ((KERF_YELLOW >> 8) & 0xff) / 255,
    (KERF_YELLOW & 0xff) / 255,
  )
  inst.instanceColor.needsUpdate = true
  s._hoveredInstance = { inst, id: instanceId }
}
function clearVertexHover(s) {
  if (s._hoveredInstance) {
    const { inst, id } = s._hoveredInstance
    if (inst.instanceColor) {
      inst.instanceColor.setXYZ(
        id,
        ((INK_300 >> 16) & 0xff) / 255,
        ((INK_300 >> 8) & 0xff) / 255,
        (INK_300 & 0xff) / 255,
      )
      inst.instanceColor.needsUpdate = true
    }
    s._hoveredInstance = null
  }
}

function buildSelectionOverlay(sel, topology, s) {
  if (sel.kind === 'face') {
    const f = topology.faces.find((x) => x.id === sel.featureId)
    if (!f) return null
    const g = geometryFromFaceTriangles(f.triangles)
    const m = new THREE.MeshBasicMaterial({
      color: KERF_YELLOW,
      transparent: true,
      opacity: 0.55,
      depthTest: false,
      side: THREE.DoubleSide,
    })
    const mesh = new THREE.Mesh(g, m)
    mesh.renderOrder = 997
    return mesh
  }
  if (sel.kind === 'edge') {
    const e = topology.edges.find((x) => x.id === sel.featureId)
    if (!e) return null
    const lg = new LineGeometry()
    lg.setPositions([e.a[0], e.a[1], e.a[2], e.b[0], e.b[1], e.b[2]])
    const w = s.renderer.domElement.clientWidth || 1
    const h = s.renderer.domElement.clientHeight || 1
    const mat = new LineMaterial({
      color: KERF_YELLOW,
      linewidth: 5,
      transparent: true,
      opacity: 1,
      depthTest: false,
    })
    mat.resolution.set(w, h)
    s.fatLineMaterials.add(mat)
    const line = new Line2(lg, mat)
    line.computeLineDistances()
    line.renderOrder = 997
    return line
  }
  if (sel.kind === 'vertex') {
    const v = topology.vertices.find((x) => x.id === sel.featureId)
    if (!v) return null
    // Larger sphere overlay.
    const aux = s.perPart.get(sel.partId)
    let r = 1.0
    if (aux?.bbox) {
      const size = new THREE.Vector3(); aux.bbox.getSize(size)
      const diag = Math.hypot(size.x, size.y, size.z) || 50
      r = Math.min(3.0, Math.max(0.5, diag * 0.008))
    }
    const sg = new THREE.SphereGeometry(r, 16, 12)
    const sm = new THREE.MeshBasicMaterial({ color: KERF_YELLOW, depthTest: false })
    const mesh = new THREE.Mesh(sg, sm)
    mesh.position.set(v.position[0], v.position[1], v.position[2])
    mesh.renderOrder = 997
    return mesh
  }
  return null
}

function lookupFeature(sel, topologies) {
  const t = topologies.get(sel.partId)
  if (!t) return null
  if (sel.kind === 'face') return t.faces.find((f) => f.id === sel.featureId) || null
  if (sel.kind === 'edge') return t.edges.find((f) => f.id === sel.featureId) || null
  if (sel.kind === 'vertex') return t.vertices.find((f) => f.id === sel.featureId) || null
  return null
}

// Topology lookup for a partId by walking the perPart map's parent topologies.
// We don't store the topology directly on the renderer state — pull it from
// the cache (which is keyed by geom WeakMap inside topology.js).
function getCachedTopologyForPart(s, partId) {
  // We need access to the parts array; but we kept aux per-part already. The
  // cleanest way is to recompute via perPart edge/vertex contents — but here
  // we just store the topology when we build aux. (Patch perPart to include it.)
  const aux = s.perPart.get(partId)
  return aux?.topology || null
}

// (perPart aux now also holds `topology`; we set it in the rebuild loop.)
function disposePartsAux(s) {
  if (!s) return
  for (const aux of s.perPart.values()) {
    for (const l of aux.edgeLines) {
      l.geometry?.dispose?.()
      // Materials shared via fatLineMaterials.
    }
    for (const m of aux.edgeMaterials) {
      m.dispose()
      s.fatLineMaterials.delete(m)
    }
    if (aux.vertexInstanced) {
      aux.vertexInstanced.geometry?.dispose?.()
      aux.vertexInstanced.material?.dispose?.()
    }
  }
  s.perPart.clear()
  // Also clear hover/selection overlays.
  clearHoverOverlay(s)
  for (const o of s.selectionOverlays) {
    if (o.parent) o.parent.remove(o)
    o.geometry?.dispose?.()
    if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose())
    else o.material?.dispose?.()
  }
  s.selectionOverlays = []
  if (s.leaderLine) {
    if (s.leaderLine.parent) s.leaderLine.parent.remove(s.leaderLine)
    s.leaderLine.geometry?.dispose?.()
    s.leaderLine.material?.dispose?.()
    s.leaderLine = null
  }
  s._hoveredLine = null
  s._hoveredInstance = null
}

function disposeAll(s) {
  if (!s) return
  s.meshGroup.children.forEach((m) => {
    m.geometry?.dispose()
    if (Array.isArray(m.material)) m.material.forEach((mat) => mat.dispose())
    else m.material?.dispose()
  })
  disposePartsAux(s)
  for (const m of s.fatLineMaterials) m.dispose()
  s.fatLineMaterials.clear()
}

