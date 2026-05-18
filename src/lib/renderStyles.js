// TODO(parent): mount activeStyle's effect chain into Renderer.jsx EffectComposer

/**
 * renderStyles.js — Render-style preset registry for the viewport.
 *
 * Defines the six visual styles that the user can switch between in the
 * RenderStylePicker toolbar. Each style maps to either:
 *   - null  (realistic: use the default Renderer.jsx EffectComposer pipeline), or
 *   - one or more EffectComposer pass descriptor objects returned by getStylePass().
 *
 * Pass descriptors are plain objects; Renderer.jsx is responsible for actually
 * mounting them into its EffectComposer (see TODO above).
 *
 * Styles:
 *   realistic   — default PBR pipeline, no override (returns null).
 *   cel         — quantised Lambert shading snapped to 3 tone bands + Sobel outline.
 *   wireframe   — MeshBasicMaterial({wireframe:true}) override on every mesh.
 *   hidden-line — wireframe + back-facing edges drawn as dashed lines (depth-tested).
 *   sketch      — screen-space cross-hatching via cel_outline + sketch_hatching.
 *   blueprint   — white-on-blue inversion with constant-weight edge detection.
 */

import * as THREE from 'three'
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'

// ── Registry ──────────────────────────────────────────────────────────────────

/**
 * Ordered list of all supported render style names.
 * @type {string[]}
 */
export const RENDER_STYLES = [
  'realistic',
  'cel',
  'wireframe',
  'hidden-line',
  'sketch',
  'blueprint',
]

// ── Internal shader sources ────────────────────────────────────────────────────
// Inlined here so getStylePass() can build ShaderPass objects without async
// file I/O. The .glsl files in src/shaders/ are the canonical source-of-truth
// and are used by the shader-load tests; these strings must stay in sync.

const CEL_OUTLINE_FRAGMENT = /* glsl */`
uniform sampler2D tDiffuse;
uniform sampler2D tDepth;
uniform vec2      texelSize;
uniform float     outlineThreshold;
uniform vec3      outlineColor;
varying vec2 vUv;

float readDepth(vec2 uv) {
  return texture2D(tDepth, uv).r;
}

void main() {
  float d00 = readDepth(vUv + texelSize * vec2(-1.0, -1.0));
  float d10 = readDepth(vUv + texelSize * vec2( 0.0, -1.0));
  float d20 = readDepth(vUv + texelSize * vec2( 1.0, -1.0));
  float d01 = readDepth(vUv + texelSize * vec2(-1.0,  0.0));
  float d21 = readDepth(vUv + texelSize * vec2( 1.0,  0.0));
  float d02 = readDepth(vUv + texelSize * vec2(-1.0,  1.0));
  float d12 = readDepth(vUv + texelSize * vec2( 0.0,  1.0));
  float d22 = readDepth(vUv + texelSize * vec2( 1.0,  1.0));
  float gx = -d00 + d20 - 2.0*d01 + 2.0*d21 - d02 + d22;
  float gy = -d00 - 2.0*d10 - d20 + d02 + 2.0*d12 + d22;
  float edge = sqrt(gx*gx + gy*gy);
  float isEdge = step(outlineThreshold, edge);
  vec4 scene = texture2D(tDiffuse, vUv);
  vec3 col   = mix(scene.rgb, outlineColor, isEdge);
  gl_FragColor = vec4(col, scene.a);
}
`

const SKETCH_HATCHING_FRAGMENT = /* glsl */`
uniform sampler2D tDiffuse;
uniform vec2      texelSize;
uniform float     hatchScale;
uniform float     hatchWeight;
varying vec2 vUv;

float hatchLine(vec2 fragCoord, float angle, float scale) {
  float s = sin(angle);
  float c = cos(angle);
  float proj = fragCoord.x * c + fragCoord.y * s;
  return step(scale - 1.0, mod(proj, scale));
}

void main() {
  vec4  scene     = texture2D(tDiffuse, vUv);
  float luminance = dot(scene.rgb, vec3(0.2126, 0.7152, 0.0722));
  vec2  fragCoord = vUv / texelSize;
  float hatching  = 0.0;
  if (luminance < 0.7)  hatching += hatchLine(fragCoord, radians(45.0),  hatchScale);
  if (luminance < 0.4)  hatching += hatchLine(fragCoord, radians(135.0), hatchScale);
  if (luminance < 0.2)  hatching += hatchLine(fragCoord, radians(0.0),   hatchScale);
  hatching = clamp(hatching, 0.0, 1.0);
  vec3 col = mix(scene.rgb, vec3(0.1), hatching * hatchWeight);
  gl_FragColor = vec4(col, scene.a);
}
`

const BLUEPRINT_FRAGMENT = /* glsl */`
uniform sampler2D tDiffuse;
uniform sampler2D tDepth;
uniform vec2      texelSize;
uniform float     edgeWeight;
varying vec2 vUv;

const vec3  BLUEPRINT_BG   = vec3(0.055, 0.141, 0.420);
const vec3  BLUEPRINT_EDGE = vec3(0.95,  0.97,  1.0);
const float EDGE_THRESHOLD = 0.0008;

float readDepth(vec2 uv) {
  return texture2D(tDepth, uv).r;
}

void main() {
  float d00 = readDepth(vUv + texelSize * vec2(-1.0, -1.0));
  float d10 = readDepth(vUv + texelSize * vec2( 0.0, -1.0));
  float d20 = readDepth(vUv + texelSize * vec2( 1.0, -1.0));
  float d01 = readDepth(vUv + texelSize * vec2(-1.0,  0.0));
  float d21 = readDepth(vUv + texelSize * vec2( 1.0,  0.0));
  float d02 = readDepth(vUv + texelSize * vec2(-1.0,  1.0));
  float d12 = readDepth(vUv + texelSize * vec2( 0.0,  1.0));
  float d22 = readDepth(vUv + texelSize * vec2( 1.0,  1.0));
  float gx = -d00 + d20 - 2.0*d01 + 2.0*d21 - d02 + d22;
  float gy = -d00 - 2.0*d10 - d20 + d02 + 2.0*d12 + d22;
  float edge   = sqrt(gx*gx + gy*gy);
  float isEdge = step(EDGE_THRESHOLD, edge) * edgeWeight;
  float depth  = readDepth(vUv);
  float isBg   = step(0.9999, depth);
  vec3  col    = mix(BLUEPRINT_BG, BLUEPRINT_EDGE, isEdge);
  col          = mix(col, BLUEPRINT_BG, isBg * (1.0 - isEdge));
  gl_FragColor = vec4(col, 1.0);
}
`

// Shared vertex shader for all full-screen ShaderPass passes.
const FULLSCREEN_VERTEX = /* glsl */`
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`

// ── Cel shading ───────────────────────────────────────────────────────────────

/**
 * Build a Three.js ShaderMaterial that quantises Lambert diffuse into 3 bands
 * (dark / mid / highlight) for the Cel / toon look.
 *
 * @returns {THREE.ShaderMaterial}
 */
function buildCelMaterial() {
  return new THREE.ShaderMaterial({
    side: THREE.FrontSide,
    lights: true,
    uniforms: THREE.UniformsUtils.merge([
      THREE.UniformsLib.lights,
      {
        baseColor: { value: new THREE.Color(0x888888) },
        // Band thresholds: below dark → band 0; dark–mid → band 1; above → band 2.
        darkThresh: { value: 0.25 },
        midThresh:  { value: 0.65 },
        // Palette: dark tone, mid tone, highlight tone.
        toneDark:   { value: new THREE.Color(0x1a1a2e) },
        toneMid:    { value: new THREE.Color(0x4a6fa5) },
        toneHigh:   { value: new THREE.Color(0xd4e9ff) },
      },
    ]),
    vertexShader: /* glsl */`
      varying vec3 vNormal;
      varying vec3 vViewDir;

      void main() {
        vec4 mvPos  = modelViewMatrix * vec4(position, 1.0);
        vViewDir    = normalize(-mvPos.xyz);
        vNormal     = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * mvPos;
      }
    `,
    fragmentShader: /* glsl */`
      uniform vec3  baseColor;
      uniform float darkThresh;
      uniform float midThresh;
      uniform vec3  toneDark;
      uniform vec3  toneMid;
      uniform vec3  toneHigh;

      #include <common>
      #include <lights_pars_begin>

      varying vec3 vNormal;
      varying vec3 vViewDir;

      void main() {
        vec3  N = normalize(vNormal);
        // Simple key-light direction (approximation; real lights injected via
        // UniformsLib.lights when mounted into a scene).
        float NdotL = clamp(dot(N, normalize(vec3(1.0, 1.0, 1.0))), 0.0, 1.0);

        // Snap NdotL to 3 discrete bands.
        vec3 tone;
        if      (NdotL < darkThresh) tone = toneDark;
        else if (NdotL < midThresh)  tone = toneMid;
        else                          tone = toneHigh;

        gl_FragColor = vec4(baseColor * tone, 1.0);
      }
    `,
  })
}

// ── Material-replacement pass (wireframe / hidden-line) ──────────────────────

/**
 * A lightweight descriptor for a material-replacement pass.  Renderer.jsx is
 * expected to walk scene.traverse() and swap materials on Mesh objects.
 *
 * @typedef {Object} MaterialReplacePass
 * @property {'material-replace'} type
 * @property {THREE.Material}     material   - Material to apply to every mesh.
 * @property {boolean}            hiddenLine - When true, also render back-faces
 *   with a dashed / lower-opacity material to indicate hidden edges.
 */

/**
 * Build a wireframe material-replacement pass descriptor.
 *
 * @param {{ hiddenLine?: boolean }} opts
 * @returns {MaterialReplacePass}
 */
function buildWireframePass({ hiddenLine = false } = {}) {
  return {
    type: 'material-replace',
    material: new THREE.MeshBasicMaterial({
      color: 0xffffff,
      wireframe: true,
    }),
    // Hidden-line: a second back-face pass with dashed-style material.
    backMaterial: hiddenLine
      ? new THREE.MeshBasicMaterial({
          color: 0x888888,
          wireframe: true,
          transparent: true,
          opacity: 0.35,
          side: THREE.BackSide,
        })
      : null,
    hiddenLine,
  }
}

// ── getStylePass ──────────────────────────────────────────────────────────────

/**
 * Return the EffectComposer pass(es) for the given render style, or `null`
 * for 'realistic' (let the default Renderer.jsx pipeline run unchanged).
 *
 * The returned value is one of:
 *   - null                               for 'realistic'
 *   - MaterialReplacePass                for 'wireframe' / 'hidden-line'
 *   - Array of { type, pass } objects    for shader-based styles (cel/sketch/blueprint)
 *
 * @param {string} style - One of RENDER_STYLES.
 * @param {{ renderer?: THREE.WebGLRenderer, scene?: THREE.Scene, camera?: THREE.Camera }} [ctx]
 * @returns {null|object|object[]}
 */
export function getStylePass(style, ctx = {}) {
  const { renderer, scene, camera } = ctx

  switch (style) {
    case 'realistic':
      return null

    case 'wireframe':
      return buildWireframePass({ hiddenLine: false })

    case 'hidden-line':
      return buildWireframePass({ hiddenLine: true })

    case 'cel': {
      // Phase 1: standard RenderPass with Cel ShaderMaterial applied to meshes.
      // Phase 2: ShaderPass that draws Sobel outline on top.
      const texelW = renderer ? 1 / renderer.domElement.width  : 1 / 1920
      const texelH = renderer ? 1 / renderer.domElement.height : 1 / 1080

      const renderPass = (scene && camera)
        ? new RenderPass(scene, camera)
        : { isRenderPass: true }

      const outlinePass = new ShaderPass({
        uniforms: {
          tDiffuse:         { value: null },
          tDepth:           { value: null },
          texelSize:        { value: new THREE.Vector2(texelW, texelH) },
          outlineThreshold: { value: 0.001 },
          outlineColor:     { value: new THREE.Vector3(0, 0, 0) },
        },
        vertexShader:   FULLSCREEN_VERTEX,
        fragmentShader: CEL_OUTLINE_FRAGMENT,
      })

      return [
        { type: 'render',  pass: renderPass, celMaterial: buildCelMaterial() },
        { type: 'shader',  pass: outlinePass, name: 'cel-outline' },
      ]
    }

    case 'sketch': {
      const texelW = renderer ? 1 / renderer.domElement.width  : 1 / 1920
      const texelH = renderer ? 1 / renderer.domElement.height : 1 / 1080

      const renderPass = (scene && camera)
        ? new RenderPass(scene, camera)
        : { isRenderPass: true }

      const outlinePass = new ShaderPass({
        uniforms: {
          tDiffuse:         { value: null },
          tDepth:           { value: null },
          texelSize:        { value: new THREE.Vector2(texelW, texelH) },
          outlineThreshold: { value: 0.001 },
          outlineColor:     { value: new THREE.Vector3(0.1, 0.1, 0.1) },
        },
        vertexShader:   FULLSCREEN_VERTEX,
        fragmentShader: CEL_OUTLINE_FRAGMENT,
      })

      const hatchPass = new ShaderPass({
        uniforms: {
          tDiffuse:    { value: null },
          texelSize:   { value: new THREE.Vector2(texelW, texelH) },
          hatchScale:  { value: 6.0 },
          hatchWeight: { value: 0.7 },
        },
        vertexShader:   FULLSCREEN_VERTEX,
        fragmentShader: SKETCH_HATCHING_FRAGMENT,
      })

      return [
        { type: 'render', pass: renderPass },
        { type: 'shader', pass: outlinePass, name: 'sketch-outline' },
        { type: 'shader', pass: hatchPass,   name: 'sketch-hatch'   },
      ]
    }

    case 'blueprint': {
      const texelW = renderer ? 1 / renderer.domElement.width  : 1 / 1920
      const texelH = renderer ? 1 / renderer.domElement.height : 1 / 1080

      const renderPass = (scene && camera)
        ? new RenderPass(scene, camera)
        : { isRenderPass: true }

      const blueprintPass = new ShaderPass({
        uniforms: {
          tDiffuse:   { value: null },
          tDepth:     { value: null },
          texelSize:  { value: new THREE.Vector2(texelW, texelH) },
          edgeWeight: { value: 1.0 },
        },
        vertexShader:   FULLSCREEN_VERTEX,
        fragmentShader: BLUEPRINT_FRAGMENT,
      })

      return [
        { type: 'render', pass: renderPass },
        { type: 'shader', pass: blueprintPass, name: 'blueprint' },
      ]
    }

    default:
      throw new Error(`renderStyles: unknown style "${style}". Valid styles: ${RENDER_STYLES.join(', ')}`)
  }
}
