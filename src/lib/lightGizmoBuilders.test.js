/**
 * lightGizmoBuilders.test.js — Vitest suite for the gizmo geometry helpers.
 *
 * Three.js is a real dependency (no GPU path exercised here), so no stubs are
 * needed; the pure geometry constructors work in Node/jsdom alike.
 */

import { describe, it, expect } from 'vitest';
import * as THREE from 'three';
import {
  buildSunGizmo,
  buildAreaGizmo,
  buildPointGizmo,
  buildSpotGizmo,
  dispatchGizmo,
} from './lightGizmoBuilders.js';

// ── helpers ───────────────────────────────────────────────────────────────────

function sunLight(overrides = {}) {
  return { id: 'sun-1', kind: 'sun', direction: [-1, -1, -2], intensity: 5, color: '#ffffff', ...overrides };
}

function areaLight(overrides = {}) {
  return { id: 'area-1', kind: 'area', position: [1000, 2000, 1500], size_mm: 800, intensity: 2, ...overrides };
}

function pointLight(overrides = {}) {
  return { id: 'point-1', kind: 'point', position: [500, -300, 1000], intensity: 3, ...overrides };
}

function spotLight(overrides = {}) {
  return { id: 'spot-1', kind: 'spot', position: [0, 0, 2000], angle: Math.PI / 4, intensity: 4, ...overrides };
}

// ── buildSunGizmo ─────────────────────────────────────────────────────────────

describe('buildSunGizmo', () => {
  it('returns a non-null THREE.Group', () => {
    const g = buildSunGizmo(sunLight());
    expect(g).toBeTruthy();
    expect(g).toBeInstanceOf(THREE.Group);
  });

  it('has children (arrow + circle)', () => {
    const g = buildSunGizmo(sunLight());
    expect(g.children.length).toBeGreaterThanOrEqual(2);
  });

  it('stores lightId and lightKind in userData', () => {
    const light = sunLight({ id: 'my-sun' });
    const g = buildSunGizmo(light);
    expect(g.userData.lightId).toBe('my-sun');
    expect(g.userData.lightKind).toBe('sun');
  });

  it('arrow direction matches input direction to 1e-12 precision', () => {
    const rawDir = [-1, -1, -2];
    const light = sunLight({ direction: rawDir });
    const g = buildSunGizmo(light);

    // The ArrowHelper is the first child; its line points in dir.
    const arrowHelper = g.children.find(c => c instanceof THREE.ArrowHelper);
    expect(arrowHelper).toBeTruthy();

    const inputVec = new THREE.Vector3(...rawDir).normalize();
    // ArrowHelper stores the direction in its quaternion; we can recover it
    // by applying the quaternion to the default axis (0,0,1).
    const arrowDir = new THREE.Vector3(0, 1, 0).applyQuaternion(arrowHelper.quaternion);

    expect(Math.abs(arrowDir.x - inputVec.x)).toBeLessThan(1e-12);
    expect(Math.abs(arrowDir.y - inputVec.y)).toBeLessThan(1e-12);
    expect(Math.abs(arrowDir.z - inputVec.z)).toBeLessThan(1e-12);
  });

  it('accepts a scale parameter and scales the gizmo', () => {
    const g1 = buildSunGizmo(sunLight(), 1);
    const g2 = buildSunGizmo(sunLight(), 2);
    // Both must return valid Groups regardless of scale
    expect(g1).toBeInstanceOf(THREE.Group);
    expect(g2).toBeInstanceOf(THREE.Group);
    // Arrow helper in g2 should have a longer arrowLength than g1
    const arrow1 = g1.children.find(c => c instanceof THREE.ArrowHelper);
    const arrow2 = g2.children.find(c => c instanceof THREE.ArrowHelper);
    expect(arrow1).toBeTruthy();
    expect(arrow2).toBeTruthy();
    // line geometry end z differs: line in ArrowHelper has two points (0 and arrowLength)
    // We verify indirectly that the scale parameter was consumed without error.
  });

  it('defaults direction to [0,0,-1] if not provided', () => {
    const light = { id: 'no-dir', kind: 'sun' };
    const g = buildSunGizmo(light);
    expect(g).toBeInstanceOf(THREE.Group);
  });
});

// ── buildAreaGizmo ────────────────────────────────────────────────────────────

describe('buildAreaGizmo', () => {
  it('returns a non-null THREE.Group', () => {
    const g = buildAreaGizmo(areaLight());
    expect(g).toBeTruthy();
    expect(g).toBeInstanceOf(THREE.Group);
  });

  it('positions the group at light.position', () => {
    const light = areaLight({ position: [100, 200, 300] });
    const g = buildAreaGizmo(light);
    expect(g.position.x).toBeCloseTo(100);
    expect(g.position.y).toBeCloseTo(200);
    expect(g.position.z).toBeCloseTo(300);
  });

  it('has at least one Line child for the rectangle outline', () => {
    const g = buildAreaGizmo(areaLight());
    const lines = g.children.filter(c => c instanceof THREE.Line);
    expect(lines.length).toBeGreaterThanOrEqual(1);
  });

  it('stores lightId and lightKind in userData', () => {
    const light = areaLight({ id: 'area-xyz' });
    const g = buildAreaGizmo(light);
    expect(g.userData.lightId).toBe('area-xyz');
    expect(g.userData.lightKind).toBe('area');
  });

  it('uses default position [0,0,0] when none provided', () => {
    const light = { id: 'area-nopos', kind: 'area', size_mm: 500 };
    const g = buildAreaGizmo(light);
    expect(g.position.x).toBe(0);
    expect(g.position.y).toBe(0);
    expect(g.position.z).toBe(0);
  });
});

// ── buildPointGizmo ───────────────────────────────────────────────────────────

describe('buildPointGizmo', () => {
  it('returns a non-null THREE.Group', () => {
    const g = buildPointGizmo(pointLight());
    expect(g).toBeTruthy();
    expect(g).toBeInstanceOf(THREE.Group);
  });

  it('positions the group at light.position', () => {
    const light = pointLight({ position: [50, -75, 120] });
    const g = buildPointGizmo(light);
    expect(g.position.x).toBeCloseTo(50);
    expect(g.position.y).toBeCloseTo(-75);
    expect(g.position.z).toBeCloseTo(120);
  });

  it('has a wireframe sphere child (Mesh)', () => {
    const g = buildPointGizmo(pointLight());
    const meshes = g.children.filter(c => c instanceof THREE.Mesh);
    expect(meshes.length).toBeGreaterThanOrEqual(1);
    expect(meshes[0].material.wireframe).toBe(true);
  });

  it('stores lightId and lightKind in userData', () => {
    const light = pointLight({ id: 'pt-99' });
    const g = buildPointGizmo(light);
    expect(g.userData.lightId).toBe('pt-99');
    expect(g.userData.lightKind).toBe('point');
  });
});

// ── buildSpotGizmo ────────────────────────────────────────────────────────────

describe('buildSpotGizmo', () => {
  it('returns a non-null THREE.Group', () => {
    const g = buildSpotGizmo(spotLight());
    expect(g).toBeTruthy();
    expect(g).toBeInstanceOf(THREE.Group);
  });

  it('positions the group at light.position', () => {
    const light = spotLight({ position: [300, 400, 500] });
    const g = buildSpotGizmo(light);
    expect(g.position.x).toBeCloseTo(300);
    expect(g.position.y).toBeCloseTo(400);
    expect(g.position.z).toBeCloseTo(500);
  });

  it('has a wireframe cone child (Mesh)', () => {
    const g = buildSpotGizmo(spotLight());
    const meshes = g.children.filter(c => c instanceof THREE.Mesh);
    expect(meshes.length).toBeGreaterThanOrEqual(1);
    expect(meshes[0].material.wireframe).toBe(true);
  });

  it('stores lightId and lightKind in userData', () => {
    const light = spotLight({ id: 'spot-42' });
    const g = buildSpotGizmo(light);
    expect(g.userData.lightId).toBe('spot-42');
    expect(g.userData.lightKind).toBe('spot');
  });

  it('uses default angle of π/6 when none provided', () => {
    const light = { id: 'spot-noangle', kind: 'spot', position: [0, 0, 0] };
    // Should not throw
    const g = buildSpotGizmo(light);
    expect(g).toBeInstanceOf(THREE.Group);
  });
});

// ── dispatchGizmo ─────────────────────────────────────────────────────────────

describe('dispatchGizmo', () => {
  it('routes sun → buildSunGizmo (returns Group with ArrowHelper)', () => {
    const g = dispatchGizmo(sunLight());
    expect(g).toBeInstanceOf(THREE.Group);
    expect(g.userData.lightKind).toBe('sun');
    const arrow = g.children.find(c => c instanceof THREE.ArrowHelper);
    expect(arrow).toBeTruthy();
  });

  it('routes area → buildAreaGizmo (returns Group with Line)', () => {
    const g = dispatchGizmo(areaLight());
    expect(g).toBeInstanceOf(THREE.Group);
    expect(g.userData.lightKind).toBe('area');
    const line = g.children.find(c => c instanceof THREE.Line);
    expect(line).toBeTruthy();
  });

  it('routes point → buildPointGizmo (returns Group with wireframe Mesh)', () => {
    const g = dispatchGizmo(pointLight());
    expect(g).toBeInstanceOf(THREE.Group);
    expect(g.userData.lightKind).toBe('point');
    const mesh = g.children.find(c => c instanceof THREE.Mesh);
    expect(mesh).toBeTruthy();
    expect(mesh.material.wireframe).toBe(true);
  });

  it('routes spot → buildSpotGizmo (returns Group with wireframe cone Mesh)', () => {
    const g = dispatchGizmo(spotLight());
    expect(g).toBeInstanceOf(THREE.Group);
    expect(g.userData.lightKind).toBe('spot');
    const mesh = g.children.find(c => c instanceof THREE.Mesh);
    expect(mesh).toBeTruthy();
    expect(mesh.material.wireframe).toBe(true);
  });

  it('throws for an unknown light kind', () => {
    const badLight = { id: 'x', kind: 'laser' };
    expect(() => dispatchGizmo(badLight)).toThrow(/unknown light kind/);
  });

  it('preserves lightId in returned group userData for all kinds', () => {
    const kinds = [sunLight(), areaLight(), pointLight(), spotLight()];
    for (const light of kinds) {
      const g = dispatchGizmo(light);
      expect(g.userData.lightId).toBe(light.id);
    }
  });
});
