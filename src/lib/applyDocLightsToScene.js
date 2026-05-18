/**
 * applyDocLightsToScene.js
 *
 * Pure helper that maps a `doc.lights[]` array (from render.js) into live
 * Three.js light objects inside a scene.
 *
 * Usage:
 *   import { applyDocLightsToScene } from './applyDocLightsToScene.js'
 *
 *   // On each doc.lights change:
 *   prevHandlesRef.current = applyDocLightsToScene(
 *     scene, doc.lights,
 *     { target: [cx, cy, cz], prevHandles: prevHandlesRef.current }
 *   )
 *
 * Coordinates: all positions/directions in doc.lights are in mm, matching
 * the rest of the scene coordinate space.
 */

import * as THREE from 'three'
import { RectAreaLightUniformsLib } from 'three/examples/jsm/lights/RectAreaLightUniformsLib.js'

// Initialise RectAreaLightUniformsLib once at module load.  Subsequent calls
// are no-ops so this is safe to call multiple times.
RectAreaLightUniformsLib.init()

/**
 * Dispose and remove previously-spawned lights, then add new lights derived
 * from `docLights`.
 *
 * @param {THREE.Scene} scene         - The live Three.js scene.
 * @param {object[]}    docLights     - Array of light descriptors from doc.lights.
 * @param {object}      opts
 * @param {number[]}    opts.target   - Scene centre [x, y, z] that directional /
 *                                      spot lights should aim at.
 * @param {THREE.Light[]} opts.prevHandles - Lights spawned on the previous call
 *                                           (will be disposed + removed).
 * @returns {THREE.Light[]} New handles array to pass on the next call.
 */
export function applyDocLightsToScene(scene, docLights, { target = [0, 0, 0], prevHandles = [] } = {}) {
  // 1. Dispose + remove every light from the previous call.
  for (const light of prevHandles) {
    scene.remove(light)
    light.dispose?.()
  }

  if (!Array.isArray(docLights) || docLights.length === 0) {
    return []
  }

  const [tx, ty, tz] = target
  const handles = []

  for (const entry of docLights) {
    const color = entry.color ?? '#ffffff'
    const intensity = entry.intensity ?? 1

    switch (entry.kind) {
      case 'sun': {
        const light = new THREE.DirectionalLight(color, intensity)
        // Direction vector → position offset scaled to 10 000 mm so the light
        // is effectively at infinity for any scene size we deal with.
        const [dx, dy, dz] = entry.direction ?? [0, -1, 0]
        const len = Math.hypot(dx, dy, dz) || 1
        light.position.set(
          tx - (dx / len) * 10000,
          ty - (dy / len) * 10000,
          tz - (dz / len) * 10000,
        )
        light.castShadow = true
        light.shadow.mapSize.width = 1024
        light.shadow.mapSize.height = 1024
        scene.add(light)
        handles.push(light)
        break
      }

      case 'area': {
        const size = entry.size_mm ?? 1000
        const light = new THREE.RectAreaLight(color, intensity, size, size)
        const [px, py, pz] = entry.position ?? [tx, ty + size, tz]
        light.position.set(px, py, pz)
        light.lookAt(tx, ty, tz)
        scene.add(light)
        handles.push(light)
        break
      }

      case 'point': {
        const [px, py, pz] = entry.position ?? [tx, ty, tz]
        const distance = entry.distance ?? 0
        const light = new THREE.PointLight(color, intensity, distance)
        light.position.set(px, py, pz)
        scene.add(light)
        handles.push(light)
        break
      }

      case 'spot': {
        const [px, py, pz] = entry.position ?? [tx, ty + 5000, tz]
        const angle = entry.angle ?? Math.PI / 4
        const light = new THREE.SpotLight(color, intensity)
        light.angle = angle
        light.position.set(px, py, pz)
        light.target.position.set(tx, ty, tz)
        scene.add(light)
        scene.add(light.target)
        handles.push(light)
        handles.push(light.target) // track target so it gets removed too
        break
      }

      default:
        // Unknown kind — skip silently.
        break
    }
  }

  return handles
}
