/**
 * lightGizmoBuilders.js — Pure Three.js helpers that build gizmo geometry for
 * each light kind. No DOM or browser dependencies; safe to import in Vitest.
 *
 * All positions/sizes are in millimetres, matching the render-doc schema.
 */

import * as THREE from 'three';

// ── buildSunGizmo ──────────────────────────────────────────────────────────────

/**
 * Build a sun-light gizmo: an arrow along `light.direction` plus a small
 * circle at the world origin (representing the "sun disc" location).
 *
 * @param {object} light  - Light object with `direction: [dx, dy, dz]`.
 * @param {number} [scale=1] - Uniform scale factor applied to the gizmo.
 * @returns {THREE.Group}
 */
export function buildSunGizmo(light, scale = 1) {
  const group = new THREE.Group();
  group.userData = { lightId: light.id, lightKind: 'sun' };

  const [dx, dy, dz] = light.direction ?? [0, 0, -1];
  const dir = new THREE.Vector3(dx, dy, dz).normalize();

  // Arrow shaft
  const arrowLength = 1000 * scale;
  const headLength = 180 * scale;
  const headWidth = 100 * scale;

  const arrowHelper = new THREE.ArrowHelper(dir, new THREE.Vector3(0, 0, 0), arrowLength, 0xffdd00, headLength, headWidth);
  group.add(arrowHelper);

  // Small circle at origin (sun disc visual cue)
  const circleRadius = 120 * scale;
  const circleSegments = 32;
  const circleGeo = new THREE.RingGeometry(circleRadius * 0.6, circleRadius, circleSegments);
  const circleMat = new THREE.MeshBasicMaterial({ color: 0xffdd00, side: THREE.DoubleSide, depthTest: false });
  const circleMesh = new THREE.Mesh(circleGeo, circleMat);
  // Orient circle perpendicular to the direction vector
  circleMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), dir);
  group.add(circleMesh);

  return group;
}

// ── buildAreaGizmo ────────────────────────────────────────────────────────────

/**
 * Build an area-light gizmo: a wireframe rectangle of `light.size_mm` at
 * `light.position`.
 *
 * @param {object} light - Light with `position: [x,y,z]` and `size_mm: number`.
 * @returns {THREE.Group}
 */
export function buildAreaGizmo(light) {
  const group = new THREE.Group();
  group.userData = { lightId: light.id, lightKind: 'area' };

  const [px, py, pz] = light.position ?? [0, 0, 0];
  group.position.set(px, py, pz);

  const s = light.size_mm ?? 500;
  const half = s / 2;

  // Four edges of the rectangle in the XY plane
  const points = [
    new THREE.Vector3(-half, -half, 0),
    new THREE.Vector3( half, -half, 0),
    new THREE.Vector3( half,  half, 0),
    new THREE.Vector3(-half,  half, 0),
    new THREE.Vector3(-half, -half, 0), // close loop
  ];
  const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
  const lineMat = new THREE.LineBasicMaterial({ color: 0x44aaff, depthTest: false });
  const line = new THREE.Line(lineGeo, lineMat);
  group.add(line);

  // Normal indicator (short line extending in +Z)
  const normalPoints = [new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0, half * 0.5)];
  const normalGeo = new THREE.BufferGeometry().setFromPoints(normalPoints);
  const normalLine = new THREE.Line(normalGeo, new THREE.LineBasicMaterial({ color: 0x44aaff, depthTest: false }));
  group.add(normalLine);

  return group;
}

// ── buildPointGizmo ───────────────────────────────────────────────────────────

/**
 * Build a point-light gizmo: a wireframe sphere at `light.position`.
 *
 * @param {object} light - Light with `position: [x,y,z]`.
 * @returns {THREE.Group}
 */
export function buildPointGizmo(light) {
  const group = new THREE.Group();
  group.userData = { lightId: light.id, lightKind: 'point' };

  const [px, py, pz] = light.position ?? [0, 0, 0];
  group.position.set(px, py, pz);

  const radius = 80;
  const sphereGeo = new THREE.SphereGeometry(radius, 12, 8);
  const sphereMat = new THREE.MeshBasicMaterial({ color: 0xff8800, wireframe: true, depthTest: false });
  const sphere = new THREE.Mesh(sphereGeo, sphereMat);
  group.add(sphere);

  return group;
}

// ── buildSpotGizmo ────────────────────────────────────────────────────────────

/**
 * Build a spot-light gizmo: a wireframe cone with apex at `light.position`
 * opening along -Z, with base radius derived from `light.angle` (radians).
 *
 * @param {object} light - Light with `position: [x,y,z]` and `angle: number` (radians).
 * @returns {THREE.Group}
 */
export function buildSpotGizmo(light) {
  const group = new THREE.Group();
  group.userData = { lightId: light.id, lightKind: 'spot' };

  const [px, py, pz] = light.position ?? [0, 0, 0];
  group.position.set(px, py, pz);

  const angle = light.angle ?? Math.PI / 6; // default 30 deg
  const coneLength = 800;
  const baseRadius = Math.tan(angle) * coneLength;

  // THREE.ConeGeometry: height along Y, apex at top
  const coneGeo = new THREE.ConeGeometry(baseRadius, coneLength, 16, 1, true);
  const coneMat = new THREE.MeshBasicMaterial({ color: 0xffaa00, wireframe: true, depthTest: false });
  const cone = new THREE.Mesh(coneGeo, coneMat);
  // Move cone so apex is at origin and base is coneLength below
  cone.position.set(0, -coneLength / 2, 0);
  group.add(cone);

  return group;
}

// ── dispatchGizmo ─────────────────────────────────────────────────────────────

/**
 * Pick and invoke the correct builder for `light.kind`.
 *
 * @param {object} light - Light object with at minimum `{ kind, id }`.
 * @returns {THREE.Group}
 * @throws {Error} if `light.kind` is not recognised.
 */
export function dispatchGizmo(light) {
  switch (light.kind) {
    case 'sun':   return buildSunGizmo(light);
    case 'area':  return buildAreaGizmo(light);
    case 'point': return buildPointGizmo(light);
    case 'spot':  return buildSpotGizmo(light);
    default:
      throw new Error(`lightGizmoBuilders: unknown light kind "${light.kind}"`);
  }
}
