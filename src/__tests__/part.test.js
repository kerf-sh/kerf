// Coverage for src/lib/part.js — Part schema parse / serialize / validate.
// All helpers are pure and need no DOM or network.
import { describe, it, expect } from 'vitest'
import {
  parsePart,
  serializePart,
  validatePart,
  defaultPart,
  partLabel,
  partThumbnailURL,
  getActiveConfig,
  normalizeConfiguration,
  PART_VISIBILITY_VALUES,
} from '../lib/part.js'

describe('parsePart', () => {
  it('returns a defaulted blank Part on empty / null / garbage input', () => {
    const blank = parsePart('')
    expect(blank.version).toBe(1)
    expect(blank.name).toBe('')
    expect(blank.distributors).toEqual([])
    expect(blank.visibility).toBe('private')
    expect(blank.photos).toEqual([])
    expect(parsePart(null).name).toBe('')
    expect(parsePart('{ broken json').name).toBe('')
  })

  it('round-trips a fully populated Part through serialize → parse', () => {
    const input = {
      version: 1,
      name: 'M3 socket cap',
      description: 'standard hex socket cap screw',
      category: 'bolt',
      manufacturer: 'McMaster',
      mpn: '91290A115',
      value: 'M3x10',
      datasheet_url: 'https://example.com/m3.pdf',
      distributors: [
        { name: 'mcmaster', url: 'https://www.mcmaster.com/91290A115/', sku: '91290A115', price_usd: 0.42 },
      ],
      visibility: 'public',
      photos: [
        { storage_key: 'parts/x/a.jpg', mime_type: 'image/jpeg', primary: true, width: 800 },
      ],
      default_config: 'M3',
      configurations: [{ id: 'M3', label: 'M3', params: { d: 3 } }],
    }
    const json = serializePart(input)
    const re = parsePart(json)
    expect(re.name).toBe('M3 socket cap')
    expect(re.distributors[0].sku).toBe('91290A115')
    expect(re.distributors[0].price_usd).toBe(0.42)
    expect(re.photos[0].primary).toBe(true)
    expect(re.photos[0].width).toBe(800)
    expect(re.visibility).toBe('public')
    expect(re.default_config).toBe('M3')
    expect(re.configurations[0].params.d).toBe(3)
  })

  it('drops malformed distributors and photos without a storage_key', () => {
    const p = parsePart(JSON.stringify({
      name: 'x',
      distributors: [
        { name: '', url: 'https://x' },          // dropped — no name
        null,                                     // dropped
        { name: 'lcsc', url: 'https://lcsc' },   // kept
      ],
      photos: [
        { mime_type: 'image/jpeg' },             // dropped — no storage_key
        { storage_key: 'k', mime_type: 'image/png' },
      ],
    }))
    expect(p.distributors).toHaveLength(1)
    expect(p.distributors[0].name).toBe('lcsc')
    expect(p.photos).toHaveLength(1)
    expect(p.photos[0].mime_type).toBe('image/png')
  })

  it('rejects unknown visibility values, defaulting to private', () => {
    const p = parsePart(JSON.stringify({ name: 'x', visibility: 'world-readable' }))
    expect(p.visibility).toBe('private')
    for (const v of PART_VISIBILITY_VALUES) {
      const ok = parsePart(JSON.stringify({ name: 'x', visibility: v }))
      expect(ok.visibility).toBe(v)
    }
  })

  it('accepts an object input directly (not just a JSON string)', () => {
    const p = parsePart({ name: 'direct', mpn: 'X1' })
    expect(p.name).toBe('direct')
    expect(p.mpn).toBe('X1')
  })
})

describe('validatePart', () => {
  it('reports missing name', () => {
    const r = validatePart({ name: '' })
    expect(r.ok).toBe(false)
    expect(r.errors.some((e) => /name is required/.test(e))).toBe(true)
  })

  it('rejects non-http datasheet and distributor URLs', () => {
    const r = validatePart({
      name: 'x',
      datasheet_url: 'javascript:alert(1)',
      distributors: [{ name: 'd', url: 'ftp://x' }],
    })
    expect(r.ok).toBe(false)
    expect(r.errors.some((e) => /datasheet_url/.test(e))).toBe(true)
    expect(r.errors.some((e) => /distributors\[0\].url/.test(e))).toBe(true)
  })

  it('rejects more than one primary photo', () => {
    const r = validatePart({
      name: 'x',
      photos: [
        { storage_key: 'a', primary: true },
        { storage_key: 'b', primary: true },
      ],
    })
    expect(r.ok).toBe(false)
    expect(r.errors.some((e) => /at most one photo can be primary/.test(e))).toBe(true)
  })

  it('passes a minimally-valid Part', () => {
    expect(validatePart({ name: 'ok' })).toEqual({ ok: true })
  })
})

describe('configurations + misc helpers', () => {
  it('normalizeConfiguration drops missing id and defaults label/params', () => {
    expect(normalizeConfiguration({ id: '' })).toBeNull()
    expect(normalizeConfiguration(null)).toBeNull()
    const c = normalizeConfiguration({ id: 'M4' })
    expect(c).toEqual({ id: 'M4', label: 'M4', params: {} })
    const c2 = normalizeConfiguration({ id: 'M4', label: 'Metric 4', params: { d: 4 } })
    expect(c2.label).toBe('Metric 4')
    expect(c2.params.d).toBe(4)
  })

  it('getActiveConfig honours configId, falls back to default_config, then first', () => {
    const parsed = {
      default_config: 'M3',
      configurations: [
        { id: 'M3', params: { d: 3 } },
        { id: 'M4', params: { d: 4 } },
      ],
    }
    expect(getActiveConfig(parsed, 'M4').id).toBe('M4')
    expect(getActiveConfig(parsed, 'unknown').id).toBe('M3') // falls back to default
    expect(getActiveConfig(parsed, '').id).toBe('M3')
    expect(getActiveConfig({ configurations: [{ id: 'A' }] }, '').id).toBe('A')
    expect(getActiveConfig({ configurations: [] }, '')).toBeNull()
    expect(getActiveConfig(null, 'M3')).toBeNull()
  })

  it('defaultPart produces a valid blank Part', () => {
    const p = defaultPart('Widget')
    expect(p.name).toBe('Widget')
    expect(p.visibility).toBe('private')
    expect(validatePart(p).ok).toBe(true)
  })

  it('partLabel strips a trailing .part extension (case-insensitive)', () => {
    expect(partLabel({ name: 'm3.part' })).toBe('m3')
    expect(partLabel({ name: 'm3.PART' })).toBe('m3')
    expect(partLabel({ name: 'no-ext' })).toBe('no-ext')
    expect(partLabel(null)).toBe('')
  })

  it('partThumbnailURL returns the blob URL for parts with a model', () => {
    const url = partThumbnailURL({ content: JSON.stringify({ name: 'x', model_storage_key: 'parts/abc/foo.glb' }) })
    expect(url).toBe('/api/blobs/parts/abc/foo.glb')
    expect(partThumbnailURL({ content: JSON.stringify({ name: 'x' }) })).toBeNull()
    expect(partThumbnailURL(null)).toBeNull()
  })
})
