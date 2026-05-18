// TODO(parent): mount makeEffectStack(settings).chain into Renderer.jsx's EffectComposer; pass focalDistance from a viewport-click reticle

/**
 * postEffects.js — Post-effects stack: bloom, DoF, vignette, grain, SSAO, chromatic aberration.
 *
 * Exports:
 *   POST_EFFECTS          — ordered list of effect keys
 *   DEFAULT_SETTINGS      — sensible per-effect defaults
 *   clampSettings(s)      — clamp + NaN-snap each parameter to valid ranges
 *   makeEffectStack(opts) — build an ordered pass array + dispose() from Three.js passes
 *
 * Pass order (inside EffectComposer, after RenderPass):
 *   SSAO → DoF → Bloom → ChromaticAberration → Vignette → Grain
 *
 * The module is deliberately stateless for unit testability (no GPU/DOM required
 * in tests — callers inject stubs).  Real Three.js pass constructors are imported
 * lazily via the opts.three / opts.passes escape hatches so tests can inject fakes.
 */

// ── Effect registry ───────────────────────────────────────────────────────────

/** Canonical ordered list of effect keys. */
export const POST_EFFECTS = ['bloom', 'dof', 'vignette', 'grain', 'ssao', 'chromatic']

// ── Default settings ──────────────────────────────────────────────────────────

/**
 * Sensible defaults for each effect.  Each entry has:
 *   enabled — whether the effect is on by default
 *   + the key parameter(s) used by clampSettings / makeEffectStack
 */
export const DEFAULT_SETTINGS = {
  bloom: {
    enabled: false,
    threshold: 0.85,   // luminance threshold [0, 1]
    strength: 0.4,     // bloom intensity
    radius: 0.5,       // bloom spread
  },
  dof: {
    enabled: false,
    focal_distance: 10.0,  // world-units focus distance (>= 0)
    aperture: 0.025,       // bokeh aperture [0.001, 0.1]
    maxblur: 0.01,         // bokeh max blur radius
  },
  vignette: {
    enabled: true,
    intensity: 0.4,    // darkness amount [0, 1]
    offset: 0.9,       // radial offset (size of clear centre)
  },
  grain: {
    enabled: true,
    intensity: 0.08,   // film-grain intensity [0, 0.5]
  },
  ssao: {
    enabled: false,
    radius: 0.4,       // sample hemisphere radius [0, 2]
    intensity: 1.0,    // occlusion strength [0, 2]
  },
  chromatic: {
    enabled: false,
    amount: 0.003,     // RGB channel shift amount [0, 0.05]
    angle: 0.0,        // shift angle (radians)
  },
}

// ── Clamp helpers ─────────────────────────────────────────────────────────────

function clampNum(value, min, max, fallback) {
  if (typeof value !== 'number' || Number.isNaN(value)) return fallback
  return Math.min(max, Math.max(min, value))
}

/**
 * Return a normalised, fully-populated settings object.
 * Out-of-range values are clamped; NaN snaps to the corresponding DEFAULT_SETTINGS value.
 * The original object is never mutated.
 *
 * @param {object} settings — partial or full settings object (same shape as DEFAULT_SETTINGS)
 * @returns {object} — complete clamped settings
 */
export function clampSettings(settings = {}) {
  const s = settings || {}

  const bloom = { ...(DEFAULT_SETTINGS.bloom), ...(s.bloom || {}) }
  const dof   = { ...(DEFAULT_SETTINGS.dof),   ...(s.dof   || {}) }
  const vig   = { ...(DEFAULT_SETTINGS.vignette), ...(s.vignette || {}) }
  const grain = { ...(DEFAULT_SETTINGS.grain), ...(s.grain || {}) }
  const ssao  = { ...(DEFAULT_SETTINGS.ssao),  ...(s.ssao  || {}) }
  const chrom = { ...(DEFAULT_SETTINGS.chromatic), ...(s.chromatic || {}) }

  return {
    bloom: {
      ...bloom,
      threshold: clampNum(bloom.threshold, 0, 1, DEFAULT_SETTINGS.bloom.threshold),
      strength:  clampNum(bloom.strength,  0, Infinity, DEFAULT_SETTINGS.bloom.strength),
      radius:    clampNum(bloom.radius,    0, Infinity, DEFAULT_SETTINGS.bloom.radius),
    },
    dof: {
      ...dof,
      focal_distance: clampNum(dof.focal_distance, 0, Infinity, DEFAULT_SETTINGS.dof.focal_distance),
      aperture:       clampNum(dof.aperture, 0.001, 0.1, DEFAULT_SETTINGS.dof.aperture),
      maxblur:        clampNum(dof.maxblur, 0, Infinity, DEFAULT_SETTINGS.dof.maxblur),
    },
    vignette: {
      ...vig,
      intensity: clampNum(vig.intensity, 0, 1, DEFAULT_SETTINGS.vignette.intensity),
      offset:    clampNum(vig.offset,    0, Infinity, DEFAULT_SETTINGS.vignette.offset),
    },
    grain: {
      ...grain,
      intensity: clampNum(grain.intensity, 0, 0.5, DEFAULT_SETTINGS.grain.intensity),
    },
    ssao: {
      ...ssao,
      radius:    clampNum(ssao.radius,    0, 2, DEFAULT_SETTINGS.ssao.radius),
      intensity: clampNum(ssao.intensity, 0, 2, DEFAULT_SETTINGS.ssao.intensity),
    },
    chromatic: {
      ...chrom,
      amount: clampNum(chrom.amount, 0, 0.05, DEFAULT_SETTINGS.chromatic.amount),
      angle:  clampNum(chrom.angle,  -Math.PI, Math.PI, DEFAULT_SETTINGS.chromatic.angle),
    },
  }
}

// ── makeEffectStack ───────────────────────────────────────────────────────────

/**
 * Build an ordered chain of Three.js post-processing passes from `settings`.
 *
 * Pass order: SSAO → DoF → Bloom → ChromaticAberration → Vignette → Grain
 *
 * @param {object} opts
 * @param {object}  opts.renderer  — THREE.WebGLRenderer
 * @param {object}  opts.scene     — THREE.Scene
 * @param {object}  opts.camera    — THREE.PerspectiveCamera
 * @param {object}  [opts.settings] — post-effects settings (DEFAULT_SETTINGS used as fallback)
 * @param {object}  [opts._passes]  — optional pass-constructor overrides for testing:
 *                                    { SSAOPass, BokehPass, UnrealBloomPass, ShaderPass,
 *                                      RGBShiftShader, VignetteShader, FilmPass, Vector2 }
 * @returns {{ chain: Pass[], dispose(): void }}
 */
export function makeEffectStack({ renderer, scene, camera, settings = {}, _passes = null }) {
  const clamped = clampSettings({ ...DEFAULT_SETTINGS, ...settings })

  // Resolve constructors — real Three.js imports or test stubs.
  let SSAOPass, BokehPass, UnrealBloomPass, ShaderPass,
      RGBShiftShader, VignetteShader, FilmPass, Vector2

  if (_passes) {
    ;({ SSAOPass, BokehPass, UnrealBloomPass, ShaderPass,
        RGBShiftShader, VignetteShader, FilmPass, Vector2 } = _passes)
  } else {
    // Dynamic imports are not available in a synchronous factory so we use
    // globalThis.THREE_PASSES as the integration-time injection point.
    // Renderer.jsx should populate this before calling makeEffectStack.
    // (Tests always supply _passes, so this branch is only hit in production.)
    const p = globalThis.THREE_PASSES || {}
    SSAOPass         = p.SSAOPass
    BokehPass        = p.BokehPass
    UnrealBloomPass  = p.UnrealBloomPass
    ShaderPass       = p.ShaderPass
    RGBShiftShader   = p.RGBShiftShader
    VignetteShader   = p.VignetteShader
    FilmPass         = p.FilmPass
    Vector2          = p.Vector2
  }

  const chain = []
  const disposables = []

  const size = renderer && renderer.getSize
    ? renderer.getSize(new Vector2())
    : new Vector2(512, 512)
  const w = (size && size.x) || 512
  const h = (size && size.y) || 512

  // 1. SSAO ─────────────────────────────────────────────────────────────────────
  if (clamped.ssao.enabled && SSAOPass) {
    const pass = new SSAOPass(scene, camera, w, h)
    pass.kernelRadius = clamped.ssao.radius
    // SSAOPass stores intensity via the output property (0 = default/occlusion)
    pass.output = 0
    // Store custom intensity for integration use
    pass._kerfIntensity = clamped.ssao.intensity
    chain.push(pass)
    disposables.push(pass)
  }

  // 2. DoF (Bokeh) ──────────────────────────────────────────────────────────────
  if (clamped.dof.enabled && BokehPass) {
    const pass = new BokehPass(scene, camera, {
      focus:    clamped.dof.focal_distance,
      aperture: clamped.dof.aperture,
      maxblur:  clamped.dof.maxblur,
    })
    chain.push(pass)
    disposables.push(pass)
  }

  // 3. Bloom ─────────────────────────────────────────────────────────────────────
  if (clamped.bloom.enabled && UnrealBloomPass) {
    const res = new Vector2(w, h)
    const pass = new UnrealBloomPass(res, clamped.bloom.strength, clamped.bloom.radius, clamped.bloom.threshold)
    chain.push(pass)
    disposables.push(pass)
  }

  // 4. Chromatic Aberration (RGBShift via ShaderPass) ───────────────────────────
  if (clamped.chromatic.enabled && ShaderPass && RGBShiftShader) {
    const pass = new ShaderPass(RGBShiftShader)
    pass.uniforms['amount'].value = clamped.chromatic.amount
    pass.uniforms['angle'].value  = clamped.chromatic.angle
    chain.push(pass)
    disposables.push(pass)
  }

  // 5. Vignette (VignetteShader via ShaderPass) ─────────────────────────────────
  if (clamped.vignette.enabled && ShaderPass && VignetteShader) {
    const pass = new ShaderPass(VignetteShader)
    // VignetteShader uses `darkness` for intensity and `offset` for radius
    pass.uniforms['darkness'].value = clamped.vignette.intensity
    pass.uniforms['offset'].value   = clamped.vignette.offset
    chain.push(pass)
    disposables.push(pass)
  }

  // 6. Grain (FilmPass) ─────────────────────────────────────────────────────────
  if (clamped.grain.enabled && FilmPass) {
    const pass = new FilmPass(clamped.grain.intensity)
    chain.push(pass)
    disposables.push(pass)
  }

  function dispose() {
    for (const p of disposables) {
      if (p && typeof p.dispose === 'function') p.dispose()
    }
    chain.length = 0
  }

  return { chain, dispose }
}
