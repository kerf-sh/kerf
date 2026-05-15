// jewelryMaterials.js
//
// PBR material presets for jewelry nodes in the viewport.
//
// Metal presets mirror the alloy keys and canonical colours in
// kerf_cad_core/jewelry/metal_cost.py (METAL_DENSITY_G_CM3 / METAL_LABELS).
// Gem presets mirror the RI catalogue in gemstones.py (GEM_CATALOG).
//
// Public API:
//   materialFor(node)
//     → { kind: 'metal', color, metalness, roughness, envMapIntensity }
//     | { kind: 'gem',   color, transmission, ior, dispersion,
//                        thickness, roughness, attenuationColor,
//                        attenuationDistance }
//     | null   (node is not a jewelry node — caller uses default material)
//
// Both result shapes are suitable for constructing THREE.MeshPhysicalMaterial.
// The caller is responsible for instantiating the Three.js material object;
// this module is pure-data / pure-function so the tests need no WebGL.

// ---------------------------------------------------------------------------
// Metal presets
// ---------------------------------------------------------------------------
//
// Base colours derived from JIS / Legor industry colour charts for each alloy.
// Metalness = 1.0 for all precious metals (fully metallic).
// Roughness is set per alloy: polished precious metals are 0.05–0.12.
// envMapIntensity boosts reflections for the dark studio background.
//
// Keys mirror METAL_DENSITY_G_CM3 in metal_cost.py.

const METAL_PRESETS = {
  // --- Yellow gold ---
  // 10k: more copper/silver → paler, slightly greenish yellow
  '10k_yellow': { color: 0xc8a84b, metalness: 1.0, roughness: 0.10, envMapIntensity: 2.0 },
  // 14k: warm gold with moderate copper content
  '14k_yellow': { color: 0xd4a843, metalness: 1.0, roughness: 0.08, envMapIntensity: 2.2 },
  // 18k: rich, saturated yellow gold (most common fine jewelry)
  '18k_yellow': { color: 0xe2a327, metalness: 1.0, roughness: 0.06, envMapIntensity: 2.4 },
  // 22k: deep warm gold, very close to pure
  '22k_yellow': { color: 0xf0b527, metalness: 1.0, roughness: 0.05, envMapIntensity: 2.5 },
  // 24k: pure gold, deep orange-yellow
  '24k_yellow': { color: 0xffd700, metalness: 1.0, roughness: 0.05, envMapIntensity: 2.5 },

  // --- White gold (Pd-white alloys: warmer than platinum) ---
  '10k_white':  { color: 0xc8c0a8, metalness: 1.0, roughness: 0.10, envMapIntensity: 2.0 },
  '14k_white':  { color: 0xd4cdb4, metalness: 1.0, roughness: 0.07, envMapIntensity: 2.2 },
  '18k_white':  { color: 0xe8e3d0, metalness: 1.0, roughness: 0.06, envMapIntensity: 2.4 },
  '22k_white':  { color: 0xeeeae0, metalness: 1.0, roughness: 0.05, envMapIntensity: 2.4 },

  // --- Rose gold (copper-rich → warm pink) ---
  '10k_rose':   { color: 0xc97b5e, metalness: 1.0, roughness: 0.10, envMapIntensity: 2.0 },
  '14k_rose':   { color: 0xd4876a, metalness: 1.0, roughness: 0.07, envMapIntensity: 2.2 },
  '18k_rose':   { color: 0xe8927a, metalness: 1.0, roughness: 0.06, envMapIntensity: 2.4 },
  '22k_rose':   { color: 0xf0a088, metalness: 1.0, roughness: 0.05, envMapIntensity: 2.4 },

  // --- Platinum ---
  // Platinum is cooler/bluer-grey than white gold, very bright
  'platinum_950': { color: 0xe8e8ec, metalness: 1.0, roughness: 0.05, envMapIntensity: 2.8 },
  'platinum_900': { color: 0xe4e4e8, metalness: 1.0, roughness: 0.06, envMapIntensity: 2.6 },

  // --- Palladium ---
  // Lighter than platinum, slightly warmer grey
  'palladium_950': { color: 0xd8d8dc, metalness: 1.0, roughness: 0.07, envMapIntensity: 2.4 },
  'palladium_500': { color: 0xc8c8cc, metalness: 1.0, roughness: 0.10, envMapIntensity: 2.0 },

  // --- Silver ---
  'sterling_925':   { color: 0xd8d8d8, metalness: 1.0, roughness: 0.08, envMapIntensity: 2.2 },
  'fine_silver':    { color: 0xe4e4e4, metalness: 1.0, roughness: 0.06, envMapIntensity: 2.4 },
  'argentium_935':  { color: 0xdcdcdc, metalness: 1.0, roughness: 0.07, envMapIntensity: 2.2 },

  // --- Other jewelry metals ---
  'titanium': { color: 0x888c90, metalness: 0.9, roughness: 0.15, envMapIntensity: 1.6 },
  'brass':    { color: 0xb08040, metalness: 1.0, roughness: 0.12, envMapIntensity: 1.8 },
  'bronze':   { color: 0x9c7040, metalness: 1.0, roughness: 0.14, envMapIntensity: 1.6 },
}

// ---------------------------------------------------------------------------
// Gem presets
// ---------------------------------------------------------------------------
//
// IOR values mirror the "ri" field midpoints from GEM_CATALOG in gemstones.py.
// transmission = 1.0 (fully transmissive faceted stones).
// thickness = 2.0 mm typical; attenuationDistance drives depth-of-colour.
// dispersion = 0.1 for diamond (high fire); 0 for others (coloured stones
//   absorb strongly; chromatic dispersion is masked by body colour).
//
// attenuationColor approximates the stone's absorption / body colour.
// roughness 0.0 = mirror-polished facets.

const GEM_PRESETS = {
  // IOR 2.418 (midpoint of ri range from GEM_CATALOG), high dispersion for fire
  diamond: {
    color: 0xffffff,
    transmission: 1.0,
    ior: 2.418,
    dispersion: 0.1,
    roughness: 0.0,
    thickness: 2.0,
    attenuationColor: 0xffffff,
    attenuationDistance: 50,
  },

  // Corundum: ruby (red) — ri midpoint 1.766
  ruby: {
    color: 0xff1a1a,
    transmission: 0.85,
    ior: 1.766,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0xff2020,
    attenuationDistance: 3.0,
  },

  // Corundum: sapphire (blue) — ri midpoint 1.766
  sapphire: {
    color: 0x1a3aff,
    transmission: 0.85,
    ior: 1.766,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0x2244ff,
    attenuationDistance: 3.5,
  },

  // Beryl: emerald (green) — ri midpoint 1.584
  emerald: {
    color: 0x00b050,
    transmission: 0.80,
    ior: 1.584,
    dispersion: 0.0,
    roughness: 0.02,
    thickness: 2.0,
    attenuationColor: 0x00c060,
    attenuationDistance: 2.5,
  },

  // Quartz: amethyst (purple) — ri midpoint 1.549
  amethyst: {
    color: 0x9b30d0,
    transmission: 0.90,
    ior: 1.549,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0xaa44e0,
    attenuationDistance: 5.0,
  },

  // Quartz: citrine (yellow-orange) — ri midpoint 1.549
  citrine: {
    color: 0xffaa00,
    transmission: 0.90,
    ior: 1.549,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0xffbb20,
    attenuationDistance: 6.0,
  },

  // Beryl: aquamarine (light blue) — ri midpoint 1.579
  aquamarine: {
    color: 0x40c8e0,
    transmission: 0.92,
    ior: 1.579,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0x50d4ec,
    attenuationDistance: 8.0,
  },

  // Beryl: morganite (peach-pink) — ri midpoint 1.586
  morganite: {
    color: 0xffb0a0,
    transmission: 0.90,
    ior: 1.586,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0xffc0b0,
    attenuationDistance: 8.0,
  },

  // Topaz (imperial orange-yellow) — ri midpoint 1.626
  topaz: {
    color: 0xff9040,
    transmission: 0.90,
    ior: 1.626,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0xffa050,
    attenuationDistance: 6.0,
  },

  // Garnet (deep red, pyrope/almandine) — ri midpoint 1.801
  garnet: {
    color: 0xb00020,
    transmission: 0.75,
    ior: 1.801,
    dispersion: 0.0,
    roughness: 0.02,
    thickness: 2.0,
    attenuationColor: 0xc02030,
    attenuationDistance: 2.0,
  },

  // Spinel (red) — ri midpoint 1.737
  spinel: {
    color: 0xff2040,
    transmission: 0.82,
    ior: 1.737,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0xff3050,
    attenuationDistance: 3.0,
  },

  // Tanzanite (violetish-blue) — ri midpoint 1.696
  tanzanite: {
    color: 0x5040d0,
    transmission: 0.85,
    ior: 1.696,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0x6050e0,
    attenuationDistance: 3.5,
  },

  // Peridot (olive green) — ri midpoint 1.677
  peridot: {
    color: 0x90c020,
    transmission: 0.88,
    ior: 1.677,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0xa0d030,
    attenuationDistance: 5.0,
  },

  // Tourmaline (vibrant; use a medium pink-green teal as default)
  tourmaline: {
    color: 0x20b890,
    transmission: 0.85,
    ior: 1.634,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0x30c8a0,
    attenuationDistance: 4.0,
  },

  // Opal (play-of-colour; semi-opaque, no real transmission)
  opal: {
    color: 0xf0f0f8,
    transmission: 0.20,
    ior: 1.450,
    dispersion: 0.0,
    roughness: 0.05,
    thickness: 2.0,
    attenuationColor: 0xf8f8ff,
    attenuationDistance: 20,
  },

  // Moonstone (adularescent white-blue)
  moonstone: {
    color: 0xd8e8f8,
    transmission: 0.50,
    ior: 1.522,
    dispersion: 0.0,
    roughness: 0.04,
    thickness: 2.0,
    attenuationColor: 0xe0eeff,
    attenuationDistance: 15,
  },

  // Alexandrite (green in daylight; use daylight green)
  alexandrite: {
    color: 0x30a040,
    transmission: 0.80,
    ior: 1.751,
    dispersion: 0.0,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0x40b050,
    attenuationDistance: 3.0,
  },

  // Zircon (blue, high RI) — ri midpoint 1.955
  zircon: {
    color: 0x60b0f0,
    transmission: 0.88,
    ior: 1.955,
    dispersion: 0.06,
    roughness: 0.01,
    thickness: 2.0,
    attenuationColor: 0x70c0ff,
    attenuationDistance: 7.0,
  },

  // Pearl (cream white, low transmission)
  pearl: {
    color: 0xf8f0e0,
    transmission: 0.05,
    ior: 1.608,
    dispersion: 0.0,
    roughness: 0.10,
    thickness: 2.0,
    attenuationColor: 0xfff8f0,
    attenuationDistance: 30,
  },

  // Turquoise (opaque, sky blue-green)
  turquoise: {
    color: 0x44b8b0,
    transmission: 0.0,
    ior: 1.630,
    dispersion: 0.0,
    roughness: 0.15,
    thickness: 2.0,
    attenuationColor: 0x50c8c0,
    attenuationDistance: 50,
  },
}

// ---------------------------------------------------------------------------
// Jewelry op set — ops that should receive PBR material overrides.
// ---------------------------------------------------------------------------

const GEM_OPS = new Set([
  'gemstone',
])

const METAL_OPS = new Set([
  'ring_shank',
  'jewelry_prong_head',
  'jewelry_bezel',
  'jewelry_channel',
  'jewelry_pave',
  'gem_seat',
  'channel_seat',
  'bezel_seat',
  'fishtail_seat',
  'gypsy_seat',
  'baguette_channel_seat',
  'multi_stone_seat',
  'pave_field_seat',
  'cluster_halo_seat',
  'eternity_band',
  'signet_ring',
  'stacking_band_set',
  'contoured_band',
  'solitaire_ring',
  'bypass_ring',
  'cocktail_ring',
  'mens_band',
  'wedding_set',
])

// ---------------------------------------------------------------------------
// materialFor — main resolver
// ---------------------------------------------------------------------------
//
// Accepts a feature-tree node (the plain object with `op`, `material`,
// `metal`, `cut` etc. fields from the .feature file).
//
// Returns a params object suitable for THREE.MeshPhysicalMaterial, or null
// when the node is not a jewelry node (caller uses its default material).
//
// The returned object includes a `kind` discriminator ('metal' | 'gem')
// for callers that need to distinguish the two material families.

export function materialFor(node) {
  if (!node || typeof node !== 'object') return null

  const op = typeof node.op === 'string' ? node.op : ''

  // --- Gemstone ---
  if (op === 'gemstone') {
    return gemMaterial(node.material)
  }

  // --- Metal ---
  if (METAL_OPS.has(op)) {
    // `metal` is the preferred field; fall back to node.material for
    // generic pieces that use the material field for alloy selection.
    const key = node.metal || node.material || null
    return metalMaterial(key)
  }

  return null
}

// ---------------------------------------------------------------------------
// metalMaterial(key) — resolve a metal PBR params object by alloy key.
// Returns the preset for the given key, or the 18k_yellow fallback if the
// key is absent / unknown.
// ---------------------------------------------------------------------------

export function metalMaterial(key) {
  const k = typeof key === 'string' ? key.trim().toLowerCase() : null
  const preset = (k && METAL_PRESETS[k]) ? METAL_PRESETS[k] : METAL_PRESETS['18k_yellow']
  return {
    kind: 'metal',
    ...preset,
  }
}

// ---------------------------------------------------------------------------
// gemMaterial(gemName) — resolve a gem PBR params object by material name.
// Returns the preset for the given gem, or the diamond fallback if unknown.
// ---------------------------------------------------------------------------

export function gemMaterial(gemName) {
  const k = typeof gemName === 'string' ? gemName.trim().toLowerCase() : null
  const preset = (k && GEM_PRESETS[k]) ? GEM_PRESETS[k] : GEM_PRESETS['diamond']
  return {
    kind: 'gem',
    ...preset,
  }
}

// ---------------------------------------------------------------------------
// Exports for tests / external consumers
// ---------------------------------------------------------------------------

export { METAL_PRESETS, GEM_PRESETS, METAL_OPS, GEM_OPS }
