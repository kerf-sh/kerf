// materialPreviewSphere.js
//
// Pure-logic helpers for the MaterialPbrEditor panel.
//
// No Three.js runtime import — this module returns plain dicts shaped for
// THREE.MeshPhysicalMaterial so tests can run without WebGL.
//
// Public API:
//   DEFAULT_PBR_STATE    — baseline PBR values (all knobs)
//   PBR_RANGES           — { prop: [min, max, step] } for each slider
//   pbrStateToSpec(state)     → THREE.MeshPhysicalMaterial-shaped dict
//   parsePbr(material)        → PBR state extracted from a material doc
//   forkMaterial(material, newName) → new material doc (source not mutated)

// ---------------------------------------------------------------------------
// PBR_RANGES — per-property [min, max, step]
// ---------------------------------------------------------------------------
// Values are chosen to match the Three.js MeshPhysicalMaterial clamp limits
// and WebGL convention. anisotropy uses [-1,1] per the Three.js spec.

export const PBR_RANGES = {
  metalness:    [0, 1, 0.01],
  roughness:    [0, 1, 0.01],
  ior:          [1, 3, 0.01],
  transmission: [0, 1, 0.01],
  clearcoat:    [0, 1, 0.01],
  sheen:        [0, 1, 0.01],
  anisotropy:   [-1, 1, 0.01],
  subsurface:   [0, 1, 0.01],
}

// ---------------------------------------------------------------------------
// DEFAULT_PBR_STATE — safe neutral values (non-metallic dielectric)
// ---------------------------------------------------------------------------

export const DEFAULT_PBR_STATE = {
  base_color: [0.8, 0.8, 0.8],   // RGB float [0,1]
  metalness:    0,
  roughness:    0.5,
  ior:          1.5,
  transmission: 0,
  clearcoat:    0,
  sheen:        0,
  anisotropy:   0,
  subsurface:   0,
}

// ---------------------------------------------------------------------------
// clampProp — clamp a value to its PBR_RANGES bounds (or leave as-is for
// base_color which has no scalar range entry).
// ---------------------------------------------------------------------------

function clampProp(key, value) {
  const range = PBR_RANGES[key]
  if (!range) return value
  const [min, max] = range
  if (typeof value !== 'number' || !Number.isFinite(value)) return DEFAULT_PBR_STATE[key]
  return Math.max(min, Math.min(max, value))
}

// clampColor — clamp each RGB channel to [0,1]
function clampColor(rgb) {
  if (!Array.isArray(rgb) || rgb.length < 3) return [...DEFAULT_PBR_STATE.base_color]
  return rgb.slice(0, 3).map((c) => {
    const n = typeof c === 'number' && Number.isFinite(c) ? c : 0.8
    return Math.max(0, Math.min(1, n))
  })
}

// ---------------------------------------------------------------------------
// pbrStateToSpec(state)
//
// Converts a PBR state object (as managed by the editor) into a flat dict
// whose keys mirror THREE.MeshPhysicalMaterial properties. The caller
// passes this to `Object.assign(material, spec)` or spreads it into a
// material constructor.
//
// base_color [r,g,b] → THREE.Color hex (0xRRGGBB) under `color` key so
// callers can do `material.color.set(spec.color)`.
// ---------------------------------------------------------------------------

export function pbrStateToSpec(state) {
  const s = state && typeof state === 'object' ? state : {}

  // base_color → THREE.Color-compatible hex integer
  const rgb = clampColor(s.base_color ?? DEFAULT_PBR_STATE.base_color)
  const r = Math.round(rgb[0] * 255)
  const g = Math.round(rgb[1] * 255)
  const b = Math.round(rgb[2] * 255)
  // eslint-disable-next-line no-bitwise
  const colorHex = (r << 16) | (g << 8) | b

  return {
    color: colorHex,
    metalness:    clampProp('metalness',    s.metalness    ?? DEFAULT_PBR_STATE.metalness),
    roughness:    clampProp('roughness',    s.roughness    ?? DEFAULT_PBR_STATE.roughness),
    ior:          clampProp('ior',          s.ior          ?? DEFAULT_PBR_STATE.ior),
    transmission: clampProp('transmission', s.transmission ?? DEFAULT_PBR_STATE.transmission),
    clearcoat:    clampProp('clearcoat',    s.clearcoat    ?? DEFAULT_PBR_STATE.clearcoat),
    sheen:        clampProp('sheen',        s.sheen        ?? DEFAULT_PBR_STATE.sheen),
    anisotropy:   clampProp('anisotropy',   s.anisotropy   ?? DEFAULT_PBR_STATE.anisotropy),
    subsurface:   clampProp('subsurface',   s.subsurface   ?? DEFAULT_PBR_STATE.subsurface),
  }
}

// ---------------------------------------------------------------------------
// parsePbr(material)
//
// Extracts PBR fields from a material document. Handles two source shapes:
//
//   T-115 BIM shape:
//     material.pbr = { metalness, roughness, ior, transmission, clearcoat,
//                      sheen, anisotropy, subsurface, base_color }
//
//   T-214 general PBR shape (flat top-level):
//     material.metalness, material.roughness, …, material.base_color
//
//   jewelryMaterials shape (flat, `color` as hex int, no base_color):
//     material.color (hex int), material.metalness, material.roughness
//
// Always returns a complete PBR state (missing fields fill from DEFAULT).
// ---------------------------------------------------------------------------

export function parsePbr(material) {
  if (!material || typeof material !== 'object') return { ...DEFAULT_PBR_STATE }

  // Prefer explicit `pbr` sub-object (T-115 BIM)
  const src = (material.pbr && typeof material.pbr === 'object')
    ? material.pbr
    : material

  // Resolve base_color — try pbr.base_color first, then top-level
  // base_color, then color_hex string (#rrggbb), then color hex int.
  let base_color = DEFAULT_PBR_STATE.base_color
  if (Array.isArray(src.base_color) && src.base_color.length >= 3) {
    base_color = clampColor(src.base_color)
  } else if (typeof material.color_hex === 'string' && /^#[0-9a-fA-F]{6}$/.test(material.color_hex)) {
    const hex = parseInt(material.color_hex.slice(1), 16)
    // eslint-disable-next-line no-bitwise
    base_color = [(hex >> 16 & 0xff) / 255, (hex >> 8 & 0xff) / 255, (hex & 0xff) / 255]
  } else if (typeof src.color === 'number' && Number.isFinite(src.color)) {
    const hex = src.color & 0xffffff
    // eslint-disable-next-line no-bitwise
    base_color = [(hex >> 16 & 0xff) / 255, (hex >> 8 & 0xff) / 255, (hex & 0xff) / 255]
  }

  const numOrDefault = (val, key) => {
    if (typeof val === 'number' && Number.isFinite(val)) {
      return clampProp(key, val)
    }
    return DEFAULT_PBR_STATE[key]
  }

  return {
    base_color,
    metalness:    numOrDefault(src.metalness,    'metalness'),
    roughness:    numOrDefault(src.roughness,    'roughness'),
    ior:          numOrDefault(src.ior,          'ior'),
    transmission: numOrDefault(src.transmission, 'transmission'),
    clearcoat:    numOrDefault(src.clearcoat,    'clearcoat'),
    sheen:        numOrDefault(src.sheen,        'sheen'),
    anisotropy:   numOrDefault(src.anisotropy,   'anisotropy'),
    subsurface:   numOrDefault(src.subsurface,   'subsurface'),
  }
}

// ---------------------------------------------------------------------------
// forkMaterial(material, newName)
//
// Returns a new material doc with the PBR layer deep-copied from `material`
// and the `name` replaced with `newName`. The source `material` is NOT
// mutated. The result carries a `pbr` sub-object regardless of whether the
// source stored PBR at the top level or in `pbr`.
// ---------------------------------------------------------------------------

export function forkMaterial(material, newName) {
  const src = material && typeof material === 'object' ? material : {}
  const pbrState = parsePbr(src)

  const fork = {
    ...src,
    name: typeof newName === 'string' ? newName : (src.name ? `${src.name} copy` : 'Untitled'),
    pbr: { ...pbrState },
  }

  return fork
}
