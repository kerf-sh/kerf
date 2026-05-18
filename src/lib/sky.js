// TODO(parent): mount addProceduralSky(scene, settings) into Renderer.jsx

/**
 * sky.js — Procedural sky + sun-position atmospheric scattering helpers.
 *
 * Uses three/examples/jsm/objects/Sky.js (Preetham / Hosek-Wilkie-style shader)
 * to create a sky dome whose sun position is driven by elevation and azimuth
 * angles supplied by the user.
 *
 * Public API:
 *   createProceduralSky(options)  → { sky, sunPosition }
 *   elevationAzimuthToDirection(elevation_deg, azimuth_deg) → THREE.Vector3
 */

import { Sky } from 'three/examples/jsm/objects/Sky.js'
import { Vector3 } from 'three'

// ── Constants ──────────────────────────────────────────────────────────────────

const DEG2RAD = Math.PI / 180

// ── Helpers ────────────────────────────────────────────────────────────────────

/**
 * Convert elevation + azimuth (degrees) to a unit Vector3 pointing toward the sun.
 *
 * Convention (matches Three.js Sky shader sunPosition uniform):
 *   x = cos(elevation) · cos(azimuth)
 *   y = sin(elevation)
 *   z = cos(elevation) · sin(azimuth)
 *
 * @param {number} elevation_deg  Sun elevation above horizon (0 = horizon, 90 = zenith)
 * @param {number} azimuth_deg    Sun azimuth from north, clockwise (0 = north / +x axis)
 * @returns {Vector3}
 */
export function elevationAzimuthToDirection(elevation_deg, azimuth_deg) {
  const el = elevation_deg * DEG2RAD
  const az = azimuth_deg  * DEG2RAD

  const cosEl = Math.cos(el)
  return new Vector3(
    cosEl * Math.cos(az),
    Math.sin(el),
    cosEl * Math.sin(az),
  ).normalize()
}

// ── Main factory ───────────────────────────────────────────────────────────────

/**
 * Create a Three.js Sky mesh pre-configured with atmospheric scattering uniforms.
 *
 * @param {object} [opts]
 * @param {number} [opts.elevation_deg=15]        Sun elevation (0–90°)
 * @param {number} [opts.azimuth_deg=180]         Sun azimuth (0–360°)
 * @param {number} [opts.turbidity=10]            Turbidity (haze), 1–20
 * @param {number} [opts.rayleigh=3]              Rayleigh scattering coefficient
 * @param {number} [opts.mieCoefficient=0.005]    Mie scattering coefficient
 * @param {number} [opts.mieDirectionalG=0.7]     Mie directional g factor
 *
 * @returns {{ sky: Sky, sunPosition: Vector3 }}
 *   sky         — A THREE.Mesh (Sky instance) ready to add to the scene.
 *   sunPosition — Unit Vector3 direction toward the sun (use to aim a DirectionalLight).
 */
export function createProceduralSky({
  elevation_deg    = 15,
  azimuth_deg      = 180,
  turbidity        = 10,
  rayleigh         = 3,
  mieCoefficient   = 0.005,
  mieDirectionalG  = 0.7,
} = {}) {
  const sky = new Sky()

  // Scale to render-unit "infinity" — large enough to always be behind all scene objects.
  sky.scale.setScalar(450_000)

  const uniforms = sky.material.uniforms
  uniforms['turbidity'].value        = turbidity
  uniforms['rayleigh'].value         = rayleigh
  uniforms['mieCoefficient'].value   = mieCoefficient
  uniforms['mieDirectionalG'].value  = mieDirectionalG

  const sunPosition = elevationAzimuthToDirection(elevation_deg, azimuth_deg)
  uniforms['sunPosition'].value.copy(sunPosition)

  return { sky, sunPosition }
}
