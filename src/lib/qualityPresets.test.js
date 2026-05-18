import { describe, it, expect } from 'vitest';
import { QUALITY_PRESETS, getPreset, applyPreset } from './qualityPresets.js';

// ── QUALITY_PRESETS array ──────────────────────────────────────────────────────

describe('QUALITY_PRESETS', () => {
  it('contains exactly the four expected names', () => {
    expect(QUALITY_PRESETS).toEqual(['draft', 'preview', 'final', 'path_traced']);
  });

  it('has exactly 4 entries', () => {
    expect(QUALITY_PRESETS).toHaveLength(4);
  });
});

// ── getPreset ──────────────────────────────────────────────────────────────────

describe('getPreset — draft', () => {
  it('returns the draft preset with expected values', () => {
    const p = getPreset('draft');
    expect(p.samples).toBe(1);
    expect(p.max_bounces).toBe(1);
    expect(p.shadow_map_size).toBe(256);
    expect(p.aa_mode).toBe('none');
    expect(Array.isArray(p.post_fx_enabled)).toBe(true);
  });
});

describe('getPreset — preview', () => {
  it('returns the preview preset with expected values', () => {
    const p = getPreset('preview');
    expect(p.samples).toBe(4);
    expect(p.max_bounces).toBe(2);
    expect(p.shadow_map_size).toBe(1024);
    expect(p.aa_mode).toBe('fxaa');
  });
});

describe('getPreset — final', () => {
  it('returns the final preset with expected values', () => {
    const p = getPreset('final');
    expect(p.samples).toBe(64);
    expect(p.max_bounces).toBe(4);
    expect(p.shadow_map_size).toBe(2048);
    expect(p.aa_mode).toBe('taa');
  });
});

describe('getPreset — path_traced', () => {
  it('returns the path_traced preset with expected values', () => {
    const p = getPreset('path_traced');
    expect(p.samples).toBe(512);
    expect(p.max_bounces).toBe(8);
    expect(p.shadow_map_size).toBe(4096);
    expect(p.aa_mode).toBe('taa');
  });
});

describe('getPreset — unknown name', () => {
  it('throws for an unknown preset name', () => {
    expect(() => getPreset('ultra')).toThrow(/Unknown quality preset/);
  });

  it('throws and mentions valid preset names', () => {
    expect(() => getPreset('ultra')).toThrow(/draft/);
  });
});

describe('getPreset — immutability', () => {
  it('returns a copy — mutating it does not affect subsequent calls', () => {
    const a = getPreset('draft');
    a.samples = 9999;
    const b = getPreset('draft');
    expect(b.samples).toBe(1);
  });

  it('post_fx_enabled array is a copy', () => {
    const a = getPreset('final');
    a.post_fx_enabled.push('custom');
    const b = getPreset('final');
    expect(b.post_fx_enabled).not.toContain('custom');
  });
});

// ── Monotonic ordering ─────────────────────────────────────────────────────────

describe('monotonic samples ordering', () => {
  it('samples increase from draft → preview → final → path_traced', () => {
    const [d, p, f, pt] = QUALITY_PRESETS.map(getPreset);
    expect(d.samples).toBeLessThan(p.samples);
    expect(p.samples).toBeLessThan(f.samples);
    expect(f.samples).toBeLessThan(pt.samples);
  });
});

describe('monotonic max_bounces ordering', () => {
  it('max_bounces increase from draft → preview → final → path_traced', () => {
    const [d, p, f, pt] = QUALITY_PRESETS.map(getPreset);
    expect(d.max_bounces).toBeLessThan(p.max_bounces);
    expect(p.max_bounces).toBeLessThan(f.max_bounces);
    expect(f.max_bounces).toBeLessThan(pt.max_bounces);
  });
});

describe('monotonic shadow_map_size ordering', () => {
  it('shadow_map_size increases from draft → preview → final → path_traced', () => {
    const [d, p, f, pt] = QUALITY_PRESETS.map(getPreset);
    expect(d.shadow_map_size).toBeLessThan(p.shadow_map_size);
    expect(p.shadow_map_size).toBeLessThan(f.shadow_map_size);
    expect(f.shadow_map_size).toBeLessThan(pt.shadow_map_size);
  });
});

// ── draft is lightest, path_traced is heaviest ────────────────────────────────

describe('draft is the lightest preset', () => {
  it('draft has the lowest samples of all presets', () => {
    const draftSamples = getPreset('draft').samples;
    QUALITY_PRESETS.filter((n) => n !== 'draft').forEach((name) => {
      expect(draftSamples).toBeLessThan(getPreset(name).samples);
    });
  });

  it('draft has the lowest max_bounces of all presets', () => {
    const draftBounces = getPreset('draft').max_bounces;
    QUALITY_PRESETS.filter((n) => n !== 'draft').forEach((name) => {
      expect(draftBounces).toBeLessThan(getPreset(name).max_bounces);
    });
  });

  it('draft has no anti-aliasing (aa_mode = none)', () => {
    expect(getPreset('draft').aa_mode).toBe('none');
  });

  it('draft has an empty post_fx_enabled list', () => {
    expect(getPreset('draft').post_fx_enabled).toHaveLength(0);
  });
});

describe('path_traced is the heaviest preset', () => {
  it('path_traced has the highest samples of all presets', () => {
    const ptSamples = getPreset('path_traced').samples;
    QUALITY_PRESETS.filter((n) => n !== 'path_traced').forEach((name) => {
      expect(ptSamples).toBeGreaterThan(getPreset(name).samples);
    });
  });

  it('path_traced has the highest max_bounces of all presets', () => {
    const ptBounces = getPreset('path_traced').max_bounces;
    QUALITY_PRESETS.filter((n) => n !== 'path_traced').forEach((name) => {
      expect(ptBounces).toBeGreaterThan(getPreset(name).max_bounces);
    });
  });

  it('path_traced has the highest shadow_map_size of all presets', () => {
    const ptSize = getPreset('path_traced').shadow_map_size;
    QUALITY_PRESETS.filter((n) => n !== 'path_traced').forEach((name) => {
      expect(ptSize).toBeGreaterThan(getPreset(name).shadow_map_size);
    });
  });
});

// ── applyPreset ────────────────────────────────────────────────────────────────

describe('applyPreset — merge behaviour', () => {
  it('overwrites preset keys in currentSettings', () => {
    const current = { samples: 999, max_bounces: 99, resolution: [1920, 1080] };
    const merged = applyPreset('draft', current);
    expect(merged.samples).toBe(1);
    expect(merged.max_bounces).toBe(1);
  });

  it('preserves unrelated keys from currentSettings', () => {
    const current = {
      resolution: [3840, 2160],
      output_format: 'png',
      denoise: true,
      samples: 10,
    };
    const merged = applyPreset('preview', current);
    expect(merged.resolution).toEqual([3840, 2160]);
    expect(merged.output_format).toBe('png');
    expect(merged.denoise).toBe(true);
  });

  it('does not mutate currentSettings', () => {
    const current = { samples: 999, custom_key: 'hello' };
    applyPreset('final', current);
    expect(current.samples).toBe(999);
    expect(current.custom_key).toBe('hello');
  });

  it('returns a new object, not the same reference', () => {
    const current = { samples: 10 };
    const merged = applyPreset('draft', current);
    expect(merged).not.toBe(current);
  });

  it('works with all four presets without throwing', () => {
    const base = { resolution: [1920, 1080] };
    QUALITY_PRESETS.forEach((name) => {
      expect(() => applyPreset(name, base)).not.toThrow();
    });
  });
});
