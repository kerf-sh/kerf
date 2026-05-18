import { describe, it, expect } from 'vitest';
import {
  SHADOW_TYPES,
  SHADOW_MAP_SIZES,
  BIAS_MIN,
  BIAS_MAX,
  getThreeShadowType,
  clampBias,
  defaultShadowSettings,
  validateShadowSettings,
  serialise,
  deserialise,
} from './shadowSettings.js';

// ── SHADOW_TYPES ───────────────────────────────────────────────────────────────

describe('SHADOW_TYPES', () => {
  it('contains exactly the four expected keys', () => {
    expect(SHADOW_TYPES).toEqual(['basic', 'pcf', 'pcf_soft', 'vsm']);
  });
});

// ── SHADOW_MAP_SIZES ───────────────────────────────────────────────────────────

describe('SHADOW_MAP_SIZES', () => {
  it('contains 512, 1024, 2048, 4096', () => {
    expect(SHADOW_MAP_SIZES).toEqual([512, 1024, 2048, 4096]);
  });
});

// ── getThreeShadowType — enum mapping ──────────────────────────────────────────

describe('getThreeShadowType — enum mapping', () => {
  it('maps basic → THREE.BasicShadowMap (0)', () => {
    expect(getThreeShadowType('basic')).toBe(0);
  });

  it('maps pcf → THREE.PCFShadowMap (1)', () => {
    expect(getThreeShadowType('pcf')).toBe(1);
  });

  it('maps pcf_soft → THREE.PCFSoftShadowMap (2)', () => {
    expect(getThreeShadowType('pcf_soft')).toBe(2);
  });

  it('maps vsm → THREE.VSMShadowMap (3)', () => {
    expect(getThreeShadowType('vsm')).toBe(3);
  });

  it('throws RangeError for an unknown type', () => {
    expect(() => getThreeShadowType('laser')).toThrow(RangeError);
  });

  it('throws for empty string', () => {
    expect(() => getThreeShadowType('')).toThrow(RangeError);
  });

  it('all SHADOW_TYPES map to distinct non-negative integers', () => {
    const values = SHADOW_TYPES.map((t) => getThreeShadowType(t));
    const unique = new Set(values);
    expect(unique.size).toBe(SHADOW_TYPES.length);
    values.forEach((v) => expect(v).toBeGreaterThanOrEqual(0));
  });
});

// ── clampBias ──────────────────────────────────────────────────────────────────

describe('clampBias', () => {
  it('returns value unchanged when within range', () => {
    expect(clampBias(0)).toBe(0);
    expect(clampBias(0.005)).toBe(0.005);
    expect(clampBias(-0.005)).toBe(-0.005);
  });

  it('clamps values above BIAS_MAX', () => {
    expect(clampBias(0.02)).toBe(BIAS_MAX);
    expect(clampBias(1)).toBe(BIAS_MAX);
  });

  it('clamps values below BIAS_MIN', () => {
    expect(clampBias(-0.02)).toBe(BIAS_MIN);
    expect(clampBias(-1)).toBe(BIAS_MIN);
  });

  it('returns BIAS_MAX when given exactly BIAS_MAX', () => {
    expect(clampBias(BIAS_MAX)).toBe(BIAS_MAX);
  });

  it('returns BIAS_MIN when given exactly BIAS_MIN', () => {
    expect(clampBias(BIAS_MIN)).toBe(BIAS_MIN);
  });
});

// ── defaultShadowSettings ──────────────────────────────────────────────────────

describe('defaultShadowSettings', () => {
  it('returns version 1', () => {
    expect(defaultShadowSettings().version).toBe(1);
  });

  it('defaults type to pcf', () => {
    expect(defaultShadowSettings().type).toBe('pcf');
  });

  it('defaults map_size to 1024', () => {
    expect(defaultShadowSettings().map_size).toBe(1024);
  });

  it('defaults lights to an empty array', () => {
    expect(defaultShadowSettings().lights).toEqual([]);
  });

  it('is valid according to validateShadowSettings', () => {
    const { ok, errors } = validateShadowSettings(defaultShadowSettings());
    expect(ok).toBe(true);
    expect(errors).toHaveLength(0);
  });
});

// ── validateShadowSettings ─────────────────────────────────────────────────────

describe('validateShadowSettings — valid document', () => {
  it('accepts the default settings', () => {
    const { ok } = validateShadowSettings(defaultShadowSettings());
    expect(ok).toBe(true);
  });

  it('accepts all valid types', () => {
    SHADOW_TYPES.forEach((type) => {
      const { ok } = validateShadowSettings({ ...defaultShadowSettings(), type });
      expect(ok).toBe(true);
    });
  });

  it('accepts all valid map_sizes', () => {
    SHADOW_MAP_SIZES.forEach((map_size) => {
      const { ok } = validateShadowSettings({ ...defaultShadowSettings(), map_size });
      expect(ok).toBe(true);
    });
  });

  it('accepts a document with per-light entries', () => {
    const settings = {
      ...defaultShadowSettings(),
      lights: [
        { id: 'sun-1', cast_shadow: true, bias: 0.0 },
        { id: 'fill', cast_shadow: false, bias: -0.005 },
      ],
    };
    const { ok } = validateShadowSettings(settings);
    expect(ok).toBe(true);
  });
});

describe('validateShadowSettings — invalid cases', () => {
  it('rejects null', () => {
    const { ok, errors } = validateShadowSettings(null);
    expect(ok).toBe(false);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('rejects an array', () => {
    const { ok } = validateShadowSettings([]);
    expect(ok).toBe(false);
  });

  it('rejects unsupported version', () => {
    const { ok, errors } = validateShadowSettings({
      ...defaultShadowSettings(),
      version: 99,
    });
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes('version'))).toBe(true);
  });

  it('rejects unknown shadow type', () => {
    const { ok, errors } = validateShadowSettings({
      ...defaultShadowSettings(),
      type: 'raytraced',
    });
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes('type'))).toBe(true);
  });

  it('rejects invalid map_size', () => {
    const { ok, errors } = validateShadowSettings({
      ...defaultShadowSettings(),
      map_size: 768,
    });
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes('map_size'))).toBe(true);
  });

  it('rejects lights that is not an array', () => {
    const { ok, errors } = validateShadowSettings({
      ...defaultShadowSettings(),
      lights: null,
    });
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes('lights'))).toBe(true);
  });

  it('rejects a light entry missing cast_shadow', () => {
    const { ok, errors } = validateShadowSettings({
      ...defaultShadowSettings(),
      lights: [{ id: 'sun', bias: 0.0 }],
    });
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes('cast_shadow'))).toBe(true);
  });

  it('rejects a light entry with bias out of range', () => {
    const { ok, errors } = validateShadowSettings({
      ...defaultShadowSettings(),
      lights: [{ id: 'sun', cast_shadow: true, bias: 0.5 }],
    });
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes('bias'))).toBe(true);
  });

  it('rejects a light entry with non-string id', () => {
    const { ok, errors } = validateShadowSettings({
      ...defaultShadowSettings(),
      lights: [{ id: 42, cast_shadow: true, bias: 0.0 }],
    });
    expect(ok).toBe(false);
    expect(errors.some((e) => e.includes('id'))).toBe(true);
  });
});

// ── serialise / deserialise — round-trip ───────────────────────────────────────

describe('serialise / deserialise round-trip', () => {
  it('round-trips the default settings', () => {
    const original = defaultShadowSettings();
    const json = serialise(original);
    expect(typeof json).toBe('string');
    const restored = deserialise(json);
    expect(restored).toEqual(original);
  });

  it('round-trips a document with per-light entries', () => {
    const settings = {
      ...defaultShadowSettings(),
      type: 'vsm',
      map_size: 2048,
      lights: [
        { id: 'key', cast_shadow: true, bias: 0.001 },
        { id: 'fill', cast_shadow: false, bias: -0.002 },
      ],
    };
    const restored = deserialise(serialise(settings));
    expect(restored).toEqual(settings);
  });

  it('serialise produces valid JSON', () => {
    const json = serialise(defaultShadowSettings());
    expect(() => JSON.parse(json)).not.toThrow();
  });

  it('deserialise throws SyntaxError on bad JSON', () => {
    expect(() => deserialise('not json')).toThrow(SyntaxError);
  });

  it('deserialise throws TypeError on invalid settings', () => {
    const bad = JSON.stringify({ version: 1, type: 'laser', map_size: 1024, lights: [] });
    expect(() => deserialise(bad)).toThrow(TypeError);
  });

  it('deserialised object is structurally equal to original', () => {
    const original = defaultShadowSettings();
    const restored = deserialise(serialise(original));
    expect(Object.keys(restored)).toEqual(Object.keys(original));
  });
});
