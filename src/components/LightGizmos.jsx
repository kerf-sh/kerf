// TODO(parent): mount <LightGizmos lights={doc.lights} onSelect={...} /> in Renderer.jsx

/**
 * LightGizmos.jsx — Declarative wrapper that mounts per-light Three.js gizmos
 * into a parent-supplied THREE.Group via a ref-callback.
 *
 * Usage:
 *   const gizmoGroupRef = useRef(new THREE.Group());
 *   scene.add(gizmoGroupRef.current);
 *   <LightGizmos
 *     lights={doc.lights}
 *     groupRef={gizmoGroupRef}
 *     onSelect={(id) => setSelectedLight(id)}
 *   />
 *
 * The component renders no DOM; it is purely a side-effect manager that keeps
 * the THREE.Group in sync with the `lights` array.
 */

import { useEffect } from 'react';
import * as THREE from 'three';
import { dispatchGizmo } from '../lib/lightGizmoBuilders.js';

/**
 * @param {object}   props
 * @param {object[]} props.lights    - Array of light objects from doc.lights.
 * @param {object}   props.groupRef  - React ref holding the THREE.Group to populate.
 * @param {Function} props.onSelect  - Callback (id: string) => void fired on click.
 */
export function LightGizmos({ lights = [], groupRef, onSelect }) {
  useEffect(() => {
    const group = groupRef?.current;
    if (!group) return;

    // Remove stale gizmos
    while (group.children.length > 0) {
      const child = group.children[0];
      group.remove(child);
    }

    if (!Array.isArray(lights) || lights.length === 0) return;

    for (const light of lights) {
      let gizmo;
      try {
        gizmo = dispatchGizmo(light);
      } catch {
        // Skip unrecognised light kinds silently
        continue;
      }
      group.add(gizmo);
    }
  }, [lights, groupRef]);

  // Pointer-down on gizmo meshes/lines fires onSelect with the light id.
  // Raycasting is handled by the parent renderer's pointer-event loop.
  // We expose a helper so the parent can forward hits to this component.
  return null;
}

/**
 * hitTestGizmoGroup — utility for the parent renderer's pointer handler.
 *
 * Raycasts against all gizmo objects in `group`, finds the closest hit,
 * and calls `onSelect(lightId)`.
 *
 * @param {THREE.Raycaster} raycaster
 * @param {THREE.Group}     group       - The group passed to LightGizmos.
 * @param {Function}        onSelect    - Callback (id: string) => void.
 * @returns {boolean} True if a gizmo was hit.
 */
export function hitTestGizmoGroup(raycaster, group, onSelect) {
  if (!raycaster || !group) return false;

  const intersects = raycaster.intersectObjects(group.children, /* recursive */ true);
  if (intersects.length === 0) return false;

  // Walk up to find the gizmo root (which holds userData.lightId)
  let obj = intersects[0].object;
  while (obj && !obj.userData?.lightId && obj.parent !== group) {
    obj = obj.parent;
  }
  // Also check the parent group level
  if (!obj?.userData?.lightId && obj?.parent?.userData?.lightId) {
    obj = obj.parent;
  }

  const lightId = obj?.userData?.lightId;
  if (lightId && typeof onSelect === 'function') {
    onSelect(lightId);
    return true;
  }
  return false;
}
