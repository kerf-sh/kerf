// Pure helpers for the Part (Library) JSON document.
//
// A Part is a kind='part' file whose `content` is a JSON document with
// manufacturer / MPN / distributor links and (optionally) a 3D model storage
// key. The schema is:
//
//   {
//     version: 1,
//     name: string,
//     description?: string,
//     category?: string,           // 'resistor' | 'bolt' | 'bearing' | …
//     manufacturer?: string,
//     mpn?: string,
//     value?: string,              // '10kΩ', 'M3x20'
//     datasheet_url?: string,
//     distributors: Array<{
//       name: string,              // 'digikey' | 'mouser' | 'lcsc' | 'mcmaster'
//       sku?: string,
//       url: string,
//       price_usd?: number,
//       stock?: number,
//       fetched_at?: string,
//     }>,
//     visibility?: 'private' | 'unlisted' | 'public',  // default 'private'
//     photos?: Array<{
//       storage_key: string,       // 'parts/<file_id>/photo-<uuid>.jpg'
//       mime_type: string,         // 'image/jpeg' | 'image/png' | 'image/webp'
//       caption?: string,
//       primary?: boolean,         // exactly one photo is primary in a valid Part
//       width?: number,
//       height?: number,
//       bytes?: number,
//     }>,
//     model_storage_key?: string,
//     model_mime_type?: string,    // typically 'model/step' or 'model/gltf-binary'
//     symbol_file_id?: string,     // electronics — Phase 2 (kind='symbol')
//     footprint_file_id?: string,  // electronics — Phase 2 (kind='footprint')
//     metadata?: Record<string, any>,
//   }
//
// The backend mirrors this shape in backend/tools/material.py
// (`PartDoc`); keep the two definitions in sync.

export const PART_VISIBILITY_VALUES = ['private', 'unlisted', 'public']

// Tolerant parse — invalid / missing JSON falls back to a defaulted Part with
// `version=1` and an empty distributors array. Always succeeds.
//
// Configurations / variants
// -------------------------
// A Part may declare per-file parameter overrides (M3 / M4 / M5 sized
// flavors of one fastener; engraved vs blank lid). Shape:
//
//   { ...,
//     "default_config": "M3",
//     "configurations": [
//       { "id": "M3", "label": "M3", "params": { "d": 3, "head_d": 5.5 } },
//       { "id": "M4", "label": "M4", "params": { "d": 4, "head_d": 7   } },
//       ...
//     ]
//   }
//
// At runtime the active config's `params` are merged OVER the equations
// scope (config wins on collision) and passed to the runner. Same shape
// applies to `.feature` and `.jscad` files — `getActiveConfig()` here is
// the canonical lookup.
export function parsePart(content) {
  let raw = null
  if (typeof content === 'string' && content.trim()) {
    try { raw = JSON.parse(content) } catch { raw = null }
  } else if (content && typeof content === 'object') {
    raw = content
  }
  const r = raw && typeof raw === 'object' ? raw : {}
  return {
    version: 1,
    name: typeof r.name === 'string' ? r.name : '',
    description: typeof r.description === 'string' ? r.description : '',
    category: typeof r.category === 'string' ? r.category : '',
    manufacturer: typeof r.manufacturer === 'string' ? r.manufacturer : '',
    mpn: typeof r.mpn === 'string' ? r.mpn : '',
    value: typeof r.value === 'string' ? r.value : '',
    datasheet_url: typeof r.datasheet_url === 'string' ? r.datasheet_url : '',
    distributors: Array.isArray(r.distributors)
      ? r.distributors.map(normalizeDistributor).filter(Boolean)
      : [],
    model_storage_key: typeof r.model_storage_key === 'string' ? r.model_storage_key : '',
    model_mime_type: typeof r.model_mime_type === 'string' ? r.model_mime_type : '',
    symbol_file_id: typeof r.symbol_file_id === 'string' ? r.symbol_file_id : '',
    footprint_file_id: typeof r.footprint_file_id === 'string' ? r.footprint_file_id : '',
    metadata: r.metadata && typeof r.metadata === 'object' && !Array.isArray(r.metadata)
      ? r.metadata
      : undefined,
    visibility: PART_VISIBILITY_VALUES.includes(r.visibility) ? r.visibility : 'private',
    photos: Array.isArray(r.photos)
      ? r.photos.map(normalizePhoto).filter(Boolean)
      : [],
    default_config: typeof r.default_config === 'string' && r.default_config.trim()
      ? r.default_config.trim() : '',
    configurations: Array.isArray(r.configurations)
      ? r.configurations.map(normalizeConfiguration).filter(Boolean)
      : [],
  }
}

// normalizeConfiguration — one row of a `configurations` array. `id` is
// required (string, non-empty); `label` falls back to `id`; `params` is a
// plain object of param-name → number (we don't enforce shape so future
// non-numeric params still round-trip).
export function normalizeConfiguration(raw) {
  if (!raw || typeof raw !== 'object') return null
  const id = typeof raw.id === 'string' ? raw.id.trim() : ''
  if (!id) return null
  const out = { id }
  out.label = typeof raw.label === 'string' && raw.label ? raw.label : id
  if (raw.params && typeof raw.params === 'object' && !Array.isArray(raw.params)) {
    out.params = raw.params
  } else {
    out.params = {}
  }
  return out
}

// getActiveConfig: pick the config matching `configId`; falls back to
// `default_config` if `configId` is empty/missing or unknown. Returns null
// if the parsed file has no configurations or nothing matches.
//
// Works on any parsed object that exposes `configurations` and
// `default_config` — Part, Sketch, Feature. Defensive against missing
// fields.
export function getActiveConfig(parsed, configId) {
  if (!parsed || typeof parsed !== 'object') return null
  const list = Array.isArray(parsed.configurations) ? parsed.configurations : []
  if (list.length === 0) return null
  if (typeof configId === 'string' && configId.trim()) {
    const want = configId.trim()
    const hit = list.find((c) => c && c.id === want)
    if (hit) return hit
  }
  const def = typeof parsed.default_config === 'string' ? parsed.default_config.trim() : ''
  if (def) {
    const hit = list.find((c) => c && c.id === def)
    if (hit) return hit
  }
  return list[0] || null
}

function normalizePhoto(raw) {
  if (!raw || typeof raw !== 'object') return null
  const storage_key = typeof raw.storage_key === 'string' ? raw.storage_key : ''
  if (!storage_key) return null
  const out = {
    storage_key,
    mime_type: typeof raw.mime_type === 'string' ? raw.mime_type : 'image/jpeg',
  }
  if (typeof raw.caption === 'string' && raw.caption) out.caption = raw.caption
  if (raw.primary === true) out.primary = true
  if (Number.isFinite(Number(raw.width))) out.width = Number(raw.width)
  if (Number.isFinite(Number(raw.height))) out.height = Number(raw.height)
  if (Number.isFinite(Number(raw.bytes))) out.bytes = Number(raw.bytes)
  return out
}

function normalizeDistributor(raw) {
  if (!raw || typeof raw !== 'object') return null
  const name = typeof raw.name === 'string' ? raw.name : ''
  if (!name) return null
  const out = { name, url: typeof raw.url === 'string' ? raw.url : '' }
  if (typeof raw.sku === 'string' && raw.sku) out.sku = raw.sku
  if (Number.isFinite(Number(raw.price_usd))) out.price_usd = Number(raw.price_usd)
  if (Number.isFinite(Number(raw.stock))) out.stock = Number(raw.stock)
  if (typeof raw.fetched_at === 'string' && raw.fetched_at) out.fetched_at = raw.fetched_at
  return out
}

// Stable, pretty-printed serialization. Drops empty optional fields so the
// JSON view stays readable.
export function serializePart(part) {
  const p = parsePart(part)
  const out = { version: 1, name: p.name }
  if (p.description) out.description = p.description
  if (p.category) out.category = p.category
  if (p.manufacturer) out.manufacturer = p.manufacturer
  if (p.mpn) out.mpn = p.mpn
  if (p.value) out.value = p.value
  if (p.datasheet_url) out.datasheet_url = p.datasheet_url
  out.distributors = (p.distributors || []).map((d) => {
    const r = { name: d.name, url: d.url || '' }
    if (d.sku) r.sku = d.sku
    if (Number.isFinite(d.price_usd)) r.price_usd = d.price_usd
    if (Number.isFinite(d.stock)) r.stock = d.stock
    if (d.fetched_at) r.fetched_at = d.fetched_at
    return r
  })
  if (p.model_storage_key) out.model_storage_key = p.model_storage_key
  if (p.model_mime_type) out.model_mime_type = p.model_mime_type
  if (p.visibility && p.visibility !== 'private') out.visibility = p.visibility
  if (Array.isArray(p.photos) && p.photos.length > 0) {
    out.photos = p.photos.map((ph) => {
      const r = { storage_key: ph.storage_key, mime_type: ph.mime_type || 'image/jpeg' }
      if (ph.caption) r.caption = ph.caption
      if (ph.primary === true) r.primary = true
      if (Number.isFinite(ph.width)) r.width = ph.width
      if (Number.isFinite(ph.height)) r.height = ph.height
      if (Number.isFinite(ph.bytes)) r.bytes = ph.bytes
      return r
    })
  }
  if (p.symbol_file_id) out.symbol_file_id = p.symbol_file_id
  if (p.footprint_file_id) out.footprint_file_id = p.footprint_file_id
  if (p.metadata && Object.keys(p.metadata).length > 0) out.metadata = p.metadata
  if (p.default_config) out.default_config = p.default_config
  if (Array.isArray(p.configurations) && p.configurations.length > 0) {
    out.configurations = p.configurations.map((c) => ({
      id: c.id,
      label: c.label || c.id,
      params: c.params && typeof c.params === 'object' ? c.params : {},
    }))
  }
  return JSON.stringify(out, null, 2)
}

// Validate: returns {ok:true} or {ok:false, errors:[...]} with human-readable
// messages. Doesn't mutate; safe to call on every render.
export function validatePart(part) {
  const errors = []
  const p = parsePart(part)
  if (p.version !== 1) errors.push('version must be 1')
  if (!p.name || !p.name.trim()) errors.push('name is required')
  if (p.datasheet_url && !isHttpURL(p.datasheet_url)) {
    errors.push('datasheet_url must be a valid http(s) URL')
  }
  for (let i = 0; i < (p.distributors || []).length; i++) {
    const d = p.distributors[i]
    if (!d.name || !d.name.trim()) errors.push(`distributors[${i}].name is required`)
    if (!d.url || !isHttpURL(d.url)) errors.push(`distributors[${i}].url must be a valid http(s) URL`)
  }
  if (p.visibility && !PART_VISIBILITY_VALUES.includes(p.visibility)) {
    errors.push(`visibility must be one of ${PART_VISIBILITY_VALUES.join('|')}`)
  }
  const primaries = (p.photos || []).filter((ph) => ph.primary === true).length
  if (primaries > 1) errors.push('at most one photo can be primary')
  return errors.length === 0 ? { ok: true } : { ok: false, errors }
}

function isHttpURL(s) {
  try {
    const u = new URL(s)
    return u.protocol === 'http:' || u.protocol === 'https:'
  } catch {
    return false
  }
}

// partThumbnailURL: returns the auth-protected blob URL for the Part's 3D
// model, or null if the Part has no model attached. The /api/blobs/* route is
// authed (project membership), so img tags can't use this directly — but
// downloaders / fetch() callers can.
//
// `project` is unused today but reserved so we can move to a project-scoped
// blob route in the future without breaking signatures.
export function partThumbnailURL(file, _project) {
  const p = parsePart(file?.content || '')
  if (!p.model_storage_key) return null
  return `/api/blobs/${encodeURI(p.model_storage_key)}`
}

// defaultPart: a blank, valid Part document with the user-supplied name.
export function defaultPart(name = 'New Part') {
  return {
    version: 1,
    name,
    distributors: [],
    visibility: 'private',
    photos: [],
  }
}

// File-name → display label used in the UI (strips the .part extension).
export function partLabel(file) {
  if (!file) return ''
  const name = file.name || ''
  return name.replace(/\.part$/i, '')
}
