// occtRunner.test.js — coverage for the pure JSON helpers exported alongside
// the OCCT worker wrapper in src/lib/occtRunner.js. The worker boot path is
// untestable in node (no Worker / WASM); these helpers are not.
//
// Pinned behaviour:
//   * DEFAULT_FEATURE — valid JSON with the expected starter shape so the
//     `.feature` editor (and the LLM `create_feature` tool) agree on the seed.
//   * parseFeature — empty / null / malformed input → safe defaults; valid
//     JSON populates features[]; configurations are normalised (id required;
//     missing label falls back to id; non-object params dropped to {}).
//   * serializeFeature — round-trips a parsed tree; omits empty optional
//     fields (default_config, configurations) so diffs stay clean.
//   * newFeatureId — short, unique-ish, prefix-respecting.

import { describe, it, expect } from 'vitest'
import {
  DEFAULT_FEATURE,
  parseFeature,
  serializeFeature,
  newFeatureId,
} from '../lib/occtRunner.js'

describe('DEFAULT_FEATURE', () => {
  it('is valid JSON with version 1, the starter name, and an empty features list', () => {
    const obj = JSON.parse(DEFAULT_FEATURE)
    expect(obj.version).toBe(1)
    expect(obj.name).toBe('New feature')
    expect(Array.isArray(obj.features)).toBe(true)
    expect(obj.features).toHaveLength(0)
  })
})

describe('parseFeature', () => {
  it('returns the canonical empty shape for empty / whitespace / null input', () => {
    const expected = {
      version: 1,
      name: 'New feature',
      features: [],
      default_config: '',
      configurations: [],
    }
    expect(parseFeature('')).toEqual(expected)
    expect(parseFeature('   \n  ')).toEqual(expected)
    expect(parseFeature(null)).toEqual(expected)
    expect(parseFeature(undefined)).toEqual(expected)
  })

  it('returns the canonical empty shape on malformed JSON', () => {
    const out = parseFeature('{ this is not json')
    expect(out.features).toEqual([])
    expect(out.version).toBe(1)
  })

  it('preserves a valid features list and default_config', () => {
    const json = JSON.stringify({
      version: 1,
      name: 'Bracket',
      features: [{ id: 'f1', op: 'extrude' }, { id: 'f2', op: 'fillet' }],
      default_config: 'big',
    })
    const out = parseFeature(json)
    expect(out.name).toBe('Bracket')
    expect(out.features).toHaveLength(2)
    expect(out.features[0].id).toBe('f1')
    expect(out.default_config).toBe('big')
  })

  it('coerces non-array features and non-string default_config to safe defaults', () => {
    const json = JSON.stringify({
      version: 2,
      features: 'oops',
      default_config: 123,
    })
    const out = parseFeature(json)
    expect(out.features).toEqual([])
    expect(out.default_config).toBe('')
    expect(out.version).toBe(2) // version is preserved when truthy
  })

  it('normalises configurations: drops invalid, defaults label, sanitises params', () => {
    const json = JSON.stringify({
      configurations: [
        null,                                    // dropped
        { label: 'no id' },                      // dropped (no id)
        { id: '   ' },                           // dropped (blank id)
        { id: 'small' },                         // label defaults to id; params={}
        { id: 'big', label: 'Big', params: { len: 100 } },
        { id: 'broken', params: ['arr-not-obj'] },  // params dropped to {}
      ],
    })
    const out = parseFeature(json)
    expect(out.configurations).toHaveLength(3)
    const small = out.configurations.find((c) => c.id === 'small')
    expect(small.label).toBe('small')
    expect(small.params).toEqual({})
    const big = out.configurations.find((c) => c.id === 'big')
    expect(big.label).toBe('Big')
    expect(big.params).toEqual({ len: 100 })
    const broken = out.configurations.find((c) => c.id === 'broken')
    expect(broken.params).toEqual({})
  })
})

describe('serializeFeature', () => {
  it('round-trips a parsed feature tree', () => {
    const original = {
      version: 1,
      name: 'Round',
      features: [{ id: 'a' }],
      default_config: 'one',
      configurations: [{ id: 'one', label: 'One', params: { r: 5 } }],
    }
    const json = serializeFeature(original)
    const reparsed = parseFeature(json)
    expect(reparsed.name).toBe('Round')
    expect(reparsed.features).toEqual([{ id: 'a' }])
    expect(reparsed.default_config).toBe('one')
    expect(reparsed.configurations).toHaveLength(1)
    expect(reparsed.configurations[0]).toEqual({ id: 'one', label: 'One', params: { r: 5 } })
  })

  it('omits empty default_config and configurations from the output for clean diffs', () => {
    const json = serializeFeature({ version: 1, name: 'Clean', features: [] })
    const obj = JSON.parse(json)
    expect(obj.default_config).toBeUndefined()
    expect(obj.configurations).toBeUndefined()
    expect(obj.metadata).toBeUndefined()
  })

  it('includes metadata only when it is an object', () => {
    const withMeta = serializeFeature({
      version: 1,
      name: 'M',
      features: [],
      metadata: { author: 'imran' },
    })
    expect(JSON.parse(withMeta).metadata).toEqual({ author: 'imran' })
    // String metadata is rejected.
    const withStringMeta = serializeFeature({
      version: 1,
      name: 'M',
      features: [],
      metadata: 'nope',
    })
    expect(JSON.parse(withStringMeta).metadata).toBeUndefined()
  })

  it('falls back to safe defaults when fed empty / partial input', () => {
    const empty = JSON.parse(serializeFeature({}))
    expect(empty.version).toBe(1)
    expect(empty.name).toBe('New feature')
    expect(Array.isArray(empty.features)).toBe(true)
    expect(empty.features).toHaveLength(0)
  })
})

describe('newFeatureId', () => {
  it('uses the default "feat" prefix', () => {
    const id = newFeatureId()
    expect(id.startsWith('feat-')).toBe(true)
  })

  it('respects a custom prefix', () => {
    const id = newFeatureId('extr')
    expect(id.startsWith('extr-')).toBe(true)
  })

  it('produces fresh ids on each call (collision-resistant)', () => {
    const seen = new Set()
    for (let i = 0; i < 50; i++) seen.add(newFeatureId('f'))
    // Random base36 6-char suffix → 36^6 ~= 2 billion options; 50 picks should
    // never collide.
    expect(seen.size).toBe(50)
  })
})
