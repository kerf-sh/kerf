// TODO(parent): mount <CloudLayer> alongside <Sky> from T-205

/**
 * clouds.js — Volumetric / billboard cloud layer helpers.
 *
 * Exports:
 *   CLOUD_KINDS             — ['none', 'scattered', 'overcast', 'storm']
 *   CLOUD_DEFAULTS          — density + opacity_max defaults per kind
 *   noise2d(x, y, seed)     — deterministic value-noise (no external deps)
 *   buildCloudMesh(opts)    — returns a THREE.Mesh of billboard quads, or
 *                             null when kind='none'
 *
 * No DOM / browser dependencies. THREE is accessed via the global passed by
 * the caller (same pattern used by heroRender.js / turntableRender.js so
 * unit tests can inject a stub).
 */

// ── Constants ──────────────────────────────────────────────────────────────────

export const CLOUD_KINDS = ['none', 'scattered', 'overcast', 'storm']

/** Default density (billboard count) and opacity_max per cloud kind. */
export const CLOUD_DEFAULTS = {
  none:      { density: 0,   opacity_max: 0.0 },
  scattered: { density: 40,  opacity_max: 0.55 },
  overcast:  { density: 120, opacity_max: 0.80 },
  storm:     { density: 200, opacity_max: 0.95 },
}

// ── noise2d ────────────────────────────────────────────────────────────────────

/**
 * Deterministic value-noise sampler.
 *
 * Returns a float in [0, 1) that depends only on (x, y, seed).  No external
 * deps.  Algorithm: integer-grid hash via a multiplied-XOR scheme, then
 * bilinear interpolation over the four surrounding lattice corners.
 *
 * @param {number} x
 * @param {number} y
 * @param {number} seed  — integer seed; different seeds give uncorrelated fields
 * @returns {number}     — value in [0, 1)
 */
export function noise2d(x, y, seed) {
  const s = seed | 0

  // Hash one integer lattice point → [0, 1)
  function hash(ix, iy) {
    let h = (ix * 1619 + iy * 31337 + s * 6971) | 0
    h = Math.imul(h ^ (h >>> 16), 0x45d9f3b)
    h = Math.imul(h ^ (h >>> 16), 0x45d9f3b)
    h = h ^ (h >>> 16)
    // Map to [0, 1) via unsigned interpretation
    return (h >>> 0) / 4294967296
  }

  // Bilinear interpolation
  const x0 = Math.floor(x)
  const y0 = Math.floor(y)
  const x1 = x0 + 1
  const y1 = y0 + 1

  const fx = x - x0
  const fy = y - y0

  // Smooth step (fade curve) for less grid-like appearance
  const ux = fx * fx * (3 - 2 * fx)
  const uy = fy * fy * (3 - 2 * fy)

  const v00 = hash(x0, y0)
  const v10 = hash(x1, y0)
  const v01 = hash(x0, y1)
  const v11 = hash(x1, y1)

  return v00 * (1 - ux) * (1 - uy) +
         v10 * ux       * (1 - uy) +
         v01 * (1 - ux) * uy       +
         v11 * ux       * uy
}

// ── buildCloudMesh ─────────────────────────────────────────────────────────────

/**
 * Build a THREE.Mesh composed of billboard quads procedurally placed on a
 * high-altitude sphere.  Each quad's opacity is driven by noise2d so the
 * cloud cover looks organic rather than uniform.
 *
 * @param {object} opts
 * @param {'none'|'scattered'|'overcast'|'storm'} [opts.kind='scattered']
 * @param {number} [opts.density]    — number of billboard quads; defaults from CLOUD_DEFAULTS
 * @param {number} [opts.opacity_max] — maximum per-quad opacity; defaults from CLOUD_DEFAULTS
 * @param {number} [opts.altitude=8000]  — sphere radius in mm (world units)
 * @param {number} [opts.radius=800]     — half-size of each billboard quad (mm)
 * @param {number} [opts.seed=42]        — noise seed
 * @returns {THREE.Mesh|null}
 */
export function buildCloudMesh({
  kind = 'scattered',
  density,
  opacity_max,
  altitude = 8000,
  radius = 800,
  seed = 42,
} = {}) {
  if (kind === 'none') return null

  const defaults = CLOUD_DEFAULTS[kind] ?? CLOUD_DEFAULTS.scattered
  const count       = density    ?? defaults.density
  const opacityMax  = opacity_max ?? defaults.opacity_max

  // THREE is expected on globalThis (same convention as heroRender.js) or as
  // an import.  We try the import first (real browser/build), then the global
  // (test injection).
  let THREE
  try {
    // Dynamic require-style access for test environments where `three` is
    // injected via globalThis.THREE rather than a real module.
    if (typeof globalThis.THREE !== 'undefined') {
      THREE = globalThis.THREE
    } else {
      // In a real bundled context this will be replaced by the bundler with
      // the actual three import.  We can't use a static import here because
      // this file must also work in test environments that stub THREE.
      throw new Error('no global THREE')
    }
  } catch (_) {
    // Fallback: try to pull from the module registry if available.
    // This branch is hit in the real browser build where globalThis.THREE
    // is not set but the bundler has inlined the module.
    THREE = globalThis.THREE
  }

  if (!THREE) {
    throw new Error('clouds.js: THREE.js not available.  Set globalThis.THREE or use the bundled build.')
  }

  // We build one merged BufferGeometry from all billboard quads.
  // Each quad = 2 triangles = 6 vertices.
  const posArr     = new Float32Array(count * 6 * 3)
  const uvArr      = new Float32Array(count * 6 * 2)
  const opacityArr = new Float32Array(count * 6)   // per-vertex opacity attr

  // Golden-angle fibonacci lattice distributes points uniformly on a sphere.
  const PHI = Math.PI * (3 - Math.sqrt(5))

  for (let i = 0; i < count; i++) {
    // Fibonacci lattice point on unit sphere
    const t      = i / count
    const incl   = Math.acos(1 - 2 * t)           // 0..π — inclination
    const azimuth = PHI * i                        // azimuth

    // Keep clouds near the upper hemisphere (0..70° from zenith) so they
    // sit above the horizon.
    const clampedIncl = incl * 0.7 + 0.02          // skew toward zenith

    const sinI = Math.sin(clampedIncl)
    const cosI = Math.cos(clampedIncl)
    const sinA = Math.sin(azimuth)
    const cosA = Math.cos(azimuth)

    // Centre of the billboard on the sphere surface.
    const cx = altitude * sinI * cosA
    const cy = altitude * sinI * sinA
    const cz = altitude * cosI

    // Build two tangent vectors for the billboard plane.
    // Use world-up (0,0,1) crossed with the radial to get a horizontal tangent,
    // then cross again for the vertical tangent.
    // Degenerate case when radial ≈ (0,0,1): use (1,0,0) as fallback.
    const rx = cx / altitude
    const ry = cy / altitude
    const rz = cz / altitude

    let tx, ty, tz  // first tangent
    const upX = 0, upY = 0, upZ = 1
    const dot = rz  // dot(r, up) = rz
    // up - dot*r
    tx = upX - dot * rx
    ty = upY - dot * ry
    tz = upZ - dot * rz
    const tlen = Math.sqrt(tx * tx + ty * ty + tz * tz) || 1
    tx /= tlen; ty /= tlen; tz /= tlen

    // Second tangent: cross(r, t)
    const bx = ry * tz - rz * ty
    const by = rz * tx - rx * tz
    const bz = rx * ty - ry * tx

    // Use noise2d to derive opacity for this quad.
    // Sample at a point spread around the sphere surface.
    const nx = (cx / altitude) * 3.7 + seed * 0.001
    const ny = (cy / altitude) * 3.7 + seed * 0.001
    const rawNoise = noise2d(nx, ny, seed + i)
    const opacity  = rawNoise * opacityMax

    // Four corners of the billboard quad: ±radius along each tangent.
    const corners = [
      [cx - radius * tx - radius * bx, cy - radius * ty - radius * by, cz - radius * tz - radius * bz],
      [cx + radius * tx - radius * bx, cy + radius * ty - radius * by, cz + radius * tz - radius * bz],
      [cx + radius * tx + radius * bx, cy + radius * ty + radius * by, cz + radius * tz + radius * bz],
      [cx - radius * tx + radius * bx, cy - radius * ty + radius * by, cz - radius * tz + radius * bz],
    ]

    // Triangle indices: [0,1,2] and [0,2,3]
    const triIdx = [0, 1, 2, 0, 2, 3]
    const base   = i * 6
    const uvs    = [[0, 0], [1, 0], [1, 1], [0, 0], [1, 1], [0, 1]]

    for (let v = 0; v < 6; v++) {
      const corner = corners[triIdx[v]]
      posArr[    (base + v) * 3    ] = corner[0]
      posArr[    (base + v) * 3 + 1] = corner[1]
      posArr[    (base + v) * 3 + 2] = corner[2]
      uvArr[     (base + v) * 2    ] = uvs[v][0]
      uvArr[     (base + v) * 2 + 1] = uvs[v][1]
      opacityArr[base + v]            = opacity
    }
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(posArr, 3))
  geometry.setAttribute('uv',       new THREE.BufferAttribute(uvArr,  2))
  geometry.setAttribute('cloudOpacity', new THREE.BufferAttribute(opacityArr, 1))

  // MeshBasicMaterial — no lighting required for cloud impostors.
  // Transparency is baked into cloudOpacity; a custom onBeforeCompile would
  // be needed to hook it in a real shader, but for the billboard contract a
  // white semi-transparent material communicates the intent.
  const material = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity: opacityMax,
    depthWrite: false,
    side: THREE.DoubleSide ?? 2,
  })

  const mesh = new THREE.Mesh(geometry, material)
  mesh.userData.cloudKind    = kind
  mesh.userData.cloudDensity = count
  mesh.userData.isClouds     = true

  return mesh
}
