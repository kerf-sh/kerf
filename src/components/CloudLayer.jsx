/**
 * CloudLayer.jsx — Declarative billboard cloud layer for the 3-D viewport.
 *
 * Usage:
 *   <CloudLayer
 *     kind="scattered"
 *     density={40}
 *     opacity={0.55}
 *     sceneRef={threeSceneRef}
 *   />
 *
 * Props:
 *   kind      {string}  — one of CLOUD_KINDS; defaults to 'scattered'
 *   density   {number}  — billboard count; falls back to CLOUD_DEFAULTS[kind].density
 *   opacity   {number}  — opacity_max override; falls back to CLOUD_DEFAULTS[kind].opacity_max
 *   sceneRef  {object}  — React ref whose .current is a THREE.Scene; the mesh
 *                         is added to / removed from this scene automatically.
 *
 * The component renders nothing to the DOM.  It mounts the buildCloudMesh
 * result into the THREE scene on mount/update and removes it on unmount.
 */

import { useEffect, useRef } from 'react'
import { buildCloudMesh, CLOUD_DEFAULTS } from '../lib/clouds.js'

/**
 * CloudLayer — pure declarative wrapper around buildCloudMesh.
 *
 * @param {{ kind?: string, density?: number, opacity?: number, sceneRef?: object }} props
 * @returns {null}
 */
export default function CloudLayer({ kind = 'scattered', density, opacity, sceneRef }) {
  // Keep a ref to the currently mounted mesh so we can remove it on cleanup.
  const meshRef = useRef(null)

  useEffect(() => {
    const scene = sceneRef?.current
    if (!scene) return

    // Resolve opacity_max: explicit prop → default for kind → 0.
    const defaults    = CLOUD_DEFAULTS[kind] ?? CLOUD_DEFAULTS.scattered
    const opacity_max = opacity  ?? defaults.opacity_max
    const resolvedDensity = density ?? defaults.density

    // Build the mesh (returns null for kind='none').
    let mesh = null
    try {
      mesh = buildCloudMesh({ kind, density: resolvedDensity, opacity_max })
    } catch (_) {
      // THREE may not be available in SSR / test environments without a stub.
      mesh = null
    }

    if (mesh && typeof scene.add === 'function') {
      scene.add(mesh)
      meshRef.current = mesh
    }

    return () => {
      // Cleanup: remove the mesh from the scene on unmount or prop change.
      if (meshRef.current && typeof scene.remove === 'function') {
        scene.remove(meshRef.current)
      }
      // Dispose geometry + material to avoid GPU leaks.
      if (meshRef.current?.geometry?.dispose) {
        meshRef.current.geometry.dispose()
      }
      if (meshRef.current?.material?.dispose) {
        meshRef.current.material.dispose()
      }
      meshRef.current = null
    }
  }, [kind, density, opacity, sceneRef])

  // This component has no DOM output.
  return null
}
