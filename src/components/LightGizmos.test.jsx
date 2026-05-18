/**
 * LightGizmos.test.jsx — Vitest assertions for the LightGizmos component
 * and its hitTestGizmoGroup utility.
 *
 * Pure logic tests — no React DOM rendering required. The component itself
 * delegates all geometry work to lightGizmoBuilders.js (covered separately).
 * Here we test:
 *   1. hitTestGizmoGroup — raycasting dispatch and onSelect callback.
 *   2. The gizmo group population logic (simulated via direct builder calls).
 *   3. Edge-cases: empty lights array, unknown kinds, missing groupRef.
 */

import { describe, it, expect, vi } from 'vitest';
import * as THREE from 'three';
import { hitTestGizmoGroup } from './LightGizmos.jsx';
import { dispatchGizmo, buildSunGizmo, buildPointGizmo } from '../lib/lightGizmoBuilders.js';

// ── fixture helpers ───────────────────────────────────────────────────────────

function sunLight(id = 'sun-1') {
  return { id, kind: 'sun', direction: [0, 0, -1], intensity: 5, color: '#ffffff' };
}

function pointLight(id = 'pt-1') {
  return { id, kind: 'point', position: [0, 0, 0], intensity: 3, color: '#ffcc00' };
}

function makeGroupWithGizmos(lights) {
  const group = new THREE.Group();
  for (const light of lights) {
    group.add(dispatchGizmo(light));
  }
  return group;
}

// ── hitTestGizmoGroup — no-hit cases ─────────────────────────────────────────

describe('hitTestGizmoGroup — no hit', () => {
  it('returns false when raycaster is null', () => {
    const group = makeGroupWithGizmos([sunLight()]);
    const onSelect = vi.fn();
    const result = hitTestGizmoGroup(null, group, onSelect);
    expect(result).toBe(false);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('returns false when group is null', () => {
    const raycaster = new THREE.Raycaster();
    const onSelect = vi.fn();
    const result = hitTestGizmoGroup(raycaster, null, onSelect);
    expect(result).toBe(false);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('returns false when the group is empty', () => {
    const raycaster = new THREE.Raycaster();
    const group = new THREE.Group();
    const onSelect = vi.fn();
    const result = hitTestGizmoGroup(raycaster, group, onSelect);
    expect(result).toBe(false);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('does not throw when onSelect is undefined', () => {
    const raycaster = new THREE.Raycaster();
    const group = new THREE.Group();
    expect(() => hitTestGizmoGroup(raycaster, group, undefined)).not.toThrow();
  });
});

// ── hitTestGizmoGroup — hit simulation ───────────────────────────────────────

describe('hitTestGizmoGroup — simulated hit', () => {
  it('calls onSelect with lightId when a gizmo child is intersected', () => {
    const light = pointLight('my-point');
    const group = new THREE.Group();
    const gizmo = buildPointGizmo(light);
    group.add(gizmo);

    // Simulate a raycaster that intersects the sphere mesh inside the gizmo
    const sphereMesh = gizmo.children[0]; // wireframe sphere
    const fakeRaycaster = {
      intersectObjects: (_children, _recursive) => [
        { object: sphereMesh, distance: 10 },
      ],
    };

    const onSelect = vi.fn();
    const result = hitTestGizmoGroup(fakeRaycaster, group, onSelect);
    expect(result).toBe(true);
    expect(onSelect).toHaveBeenCalledWith('my-point');
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('calls onSelect with lightId when the gizmo root itself is intersected', () => {
    const light = sunLight('my-sun');
    const group = new THREE.Group();
    const gizmo = buildSunGizmo(light);
    group.add(gizmo);

    // Intersect a deep descendant of the ArrowHelper
    const arrowHelper = gizmo.children.find(c => c instanceof THREE.ArrowHelper);
    const deepChild = arrowHelper?.children?.[0] ?? gizmo.children[0];

    const fakeRaycaster = {
      intersectObjects: () => [{ object: deepChild, distance: 5 }],
    };

    const onSelect = vi.fn();
    const result = hitTestGizmoGroup(fakeRaycaster, group, onSelect);
    expect(result).toBe(true);
    expect(onSelect).toHaveBeenCalledWith('my-sun');
  });

  it('does not call onSelect when no intersection occurs', () => {
    const group = makeGroupWithGizmos([pointLight()]);
    const fakeRaycaster = { intersectObjects: () => [] };
    const onSelect = vi.fn();
    hitTestGizmoGroup(fakeRaycaster, group, onSelect);
    expect(onSelect).not.toHaveBeenCalled();
  });
});

// ── group population logic ────────────────────────────────────────────────────

describe('gizmo group population', () => {
  it('adds one gizmo per light to the group', () => {
    const lights = [sunLight('s'), pointLight('p')];
    const group = makeGroupWithGizmos(lights);
    expect(group.children).toHaveLength(2);
  });

  it('gizmo userData.lightId matches the light id', () => {
    const lights = [sunLight('sun-id'), pointLight('pt-id')];
    const group = makeGroupWithGizmos(lights);
    const ids = group.children.map(c => c.userData.lightId);
    expect(ids).toContain('sun-id');
    expect(ids).toContain('pt-id');
  });

  it('empty lights array produces an empty group', () => {
    const group = makeGroupWithGizmos([]);
    expect(group.children).toHaveLength(0);
  });

  it('each gizmo child is a THREE.Group', () => {
    const lights = [
      { id: 'a', kind: 'sun', direction: [1, 0, 0] },
      { id: 'b', kind: 'area', position: [0, 0, 0], size_mm: 500 },
      { id: 'c', kind: 'point', position: [0, 0, 0] },
      { id: 'd', kind: 'spot', position: [0, 0, 0], angle: 0.5 },
    ];
    const group = makeGroupWithGizmos(lights);
    for (const child of group.children) {
      expect(child).toBeInstanceOf(THREE.Group);
    }
  });
});
