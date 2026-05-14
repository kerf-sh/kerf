// Pure helpers for the Material (Library) JSON document.
//
// A Material is a kind='material' file whose `content` is a JSON document
// declaring one engineering material (E / ν / ρ / α / yield / k / cₚ).
// Consumed downstream by FEM, tolerance studies, drawing callouts, and
// Part defaults (a Part may carry a `material_path` pointer).
//
// File shape:
//
//   {
//     version: 1,
//     name: 'AISI 1018 Steel',
//     category: 'metal/steel/carbon',
//     common_names: ['mild steel', 'low-carbon steel'],
//     color_hex: '#7d8088',
//     mechanical: {
//       E_GPa: 205, G_GPa: 80, nu: 0.29,
//       yield_MPa: 370, ultimate_MPa: 440, elongation_pct: 15
//     },
//     thermal: {
//       alpha_per_K: 11.7e-6, k_W_mK: 51.9, cp_J_kgK: 486,
//       T_min_C: -40, T_max_C: 250
//     },
//     physical: { rho_kg_m3: 7870 },
//     callout: 'AISI 1018',
//     notes: 'General-purpose mild steel.'
//   }
//
// Convention: unknown numbers are written as `null` (rather than omitted)
// so the editor and consumers can render them as "—" without guessing.
//
// The backend mirrors this shape in
// backend/tools/material.py (`MaterialDoc`); keep the two
// definitions in sync.

const MECHANICAL_KEYS = [
  'E_GPa', 'G_GPa', 'nu',
  'yield_MPa', 'ultimate_MPa', 'elongation_pct',
]
const THERMAL_KEYS = [
  'alpha_per_K', 'k_W_mK', 'cp_J_kgK', 'T_min_C', 'T_max_C',
]
const PHYSICAL_KEYS = ['rho_kg_m3']

// numericOrNull tolerates strings (from inputs) and trims them. Empty or
// non-numeric values become null so the UI can render "—".
function numericOrNull(v) {
  if (v === null || v === undefined || v === '') return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

function pickGroup(raw, keys) {
  const out = {}
  const src = (raw && typeof raw === 'object') ? raw : {}
  for (const k of keys) out[k] = numericOrNull(src[k])
  return out
}

// parseMaterial — tolerant parse. Bad JSON / missing fields fall back to
// the empty defaultMaterial(); always returns a fully-populated object.
export function parseMaterial(content) {
  let raw = null
  if (typeof content === 'string' && content.trim()) {
    try { raw = JSON.parse(content) } catch { raw = null }
  } else if (content && typeof content === 'object') {
    raw = content
  }
  const r = raw && typeof raw === 'object' ? raw : {}
  const commonNames = Array.isArray(r.common_names)
    ? r.common_names.filter((s) => typeof s === 'string')
    : []
  return {
    version: 1,
    name: typeof r.name === 'string' ? r.name : '',
    category: typeof r.category === 'string' ? r.category : '',
    common_names: commonNames,
    color_hex: typeof r.color_hex === 'string' ? r.color_hex : '',
    mechanical: pickGroup(r.mechanical, MECHANICAL_KEYS),
    thermal: pickGroup(r.thermal, THERMAL_KEYS),
    physical: pickGroup(r.physical, PHYSICAL_KEYS),
    callout: typeof r.callout === 'string' ? r.callout : '',
    notes: typeof r.notes === 'string' ? r.notes : '',
  }
}

// serializeMaterial — emits pretty-printed JSON suitable for storage.
// Always pins `version: 1`. The shape mirrors what parseMaterial reads
// back so a round-trip is lossless.
export function serializeMaterial(material) {
  const m = material && typeof material === 'object' ? material : {}
  const doc = {
    version: 1,
    name: typeof m.name === 'string' ? m.name : '',
    category: typeof m.category === 'string' ? m.category : '',
    common_names: Array.isArray(m.common_names)
      ? m.common_names.filter((s) => typeof s === 'string' && s.trim())
      : [],
    color_hex: typeof m.color_hex === 'string' ? m.color_hex : '',
    mechanical: pickGroup(m.mechanical, MECHANICAL_KEYS),
    thermal: pickGroup(m.thermal, THERMAL_KEYS),
    physical: pickGroup(m.physical, PHYSICAL_KEYS),
    callout: typeof m.callout === 'string' ? m.callout : '',
    notes: typeof m.notes === 'string' ? m.notes : '',
  }
  return JSON.stringify(doc, null, 2)
}

// defaultMaterial — empty seed. Every numeric field is null so the editor
// renders "—" everywhere until the user fills something in.
export function defaultMaterial(name = '') {
  return {
    version: 1,
    name,
    category: '',
    common_names: [],
    color_hex: '',
    mechanical: pickGroup(null, MECHANICAL_KEYS),
    thermal: pickGroup(null, THERMAL_KEYS),
    physical: pickGroup(null, PHYSICAL_KEYS),
    callout: '',
    notes: '',
  }
}

// MATERIAL_FIELD_META describes each numeric field for the editor: the
// display label and the SI unit. The order matches the visual order in
// MaterialEditor.jsx so a single source of truth drives both.
export const MATERIAL_FIELD_META = {
  mechanical: [
    { key: 'E_GPa',          label: 'Young’s modulus (E)', unit: 'GPa' },
    { key: 'G_GPa',          label: 'Shear modulus (G)',         unit: 'GPa' },
    { key: 'nu',             label: 'Poisson’s ratio (ν)', unit: '' },
    { key: 'yield_MPa',      label: 'Yield strength',            unit: 'MPa' },
    { key: 'ultimate_MPa',   label: 'Ultimate tensile strength', unit: 'MPa' },
    { key: 'elongation_pct', label: 'Elongation at break',       unit: '%'   },
  ],
  thermal: [
    { key: 'alpha_per_K', label: 'Thermal expansion (α)', unit: '1/K'  },
    { key: 'k_W_mK',      label: 'Thermal conductivity (k)',   unit: 'W/m·K' },
    { key: 'cp_J_kgK',    label: 'Specific heat (cₚ)',    unit: 'J/kg·K' },
    { key: 'T_min_C',     label: 'Min service temperature',    unit: '°C' },
    { key: 'T_max_C',     label: 'Max service temperature',    unit: '°C' },
  ],
  physical: [
    { key: 'rho_kg_m3', label: 'Density (ρ)', unit: 'kg/m³' },
  ],
}
