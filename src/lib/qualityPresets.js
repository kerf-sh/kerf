/**
 * qualityPresets.js — Render quality preset bundles.
 *
 * Each preset is a named bundle of render settings that trades off
 * speed against quality. Four presets are defined:
 *
 *   draft       — fastest; useful for layout/composition checks.
 *   preview     — balanced; real-time look-dev.
 *   final       — production quality; suitable for client deliverables.
 *   path_traced — ground-truth ray tracing; slowest.
 *
 * No DOM/browser dependencies — safe to import in workers or tests.
 */

// ── Preset definitions ─────────────────────────────────────────────────────────

export const QUALITY_PRESETS = ['draft', 'preview', 'final', 'path_traced'];

/**
 * @typedef {object} QualitySettings
 * @property {number}   samples           - Path samples per pixel.
 * @property {number}   max_bounces       - Maximum ray bounce depth.
 * @property {number}   shadow_map_size   - Shadow map resolution (px × px).
 * @property {string}   aa_mode           - Anti-aliasing mode: 'none'|'fxaa'|'taa'.
 * @property {string[]} post_fx_enabled   - Enabled post-processing effects.
 */

/** @type {Record<string, QualitySettings>} */
const PRESETS = {
  draft: {
    samples: 1,
    max_bounces: 1,
    shadow_map_size: 256,
    aa_mode: 'none',
    post_fx_enabled: [],
  },
  preview: {
    samples: 4,
    max_bounces: 2,
    shadow_map_size: 1024,
    aa_mode: 'fxaa',
    post_fx_enabled: ['bloom'],
  },
  final: {
    samples: 64,
    max_bounces: 4,
    shadow_map_size: 2048,
    aa_mode: 'taa',
    post_fx_enabled: ['bloom', 'ao', 'color_grading'],
  },
  path_traced: {
    samples: 512,
    max_bounces: 8,
    shadow_map_size: 4096,
    aa_mode: 'taa',
    post_fx_enabled: ['bloom', 'ao', 'color_grading', 'lens_flare'],
  },
};

// ── getPreset ──────────────────────────────────────────────────────────────────

/**
 * Return an immutable copy of the named preset's settings.
 *
 * @param {string} name - One of QUALITY_PRESETS.
 * @returns {QualitySettings}
 * @throws {Error} when `name` is not a known preset.
 */
export function getPreset(name) {
  const preset = PRESETS[name];
  if (!preset) {
    throw new Error(
      `Unknown quality preset: "${name}". Valid presets: ${QUALITY_PRESETS.join(', ')}`
    );
  }
  return { ...preset, post_fx_enabled: [...preset.post_fx_enabled] };
}

// ── applyPreset ────────────────────────────────────────────────────────────────

/**
 * Merge a named preset into `currentSettings`, returning a new object.
 * Keys not touched by the preset are preserved unchanged.
 *
 * @param {string} name            - One of QUALITY_PRESETS.
 * @param {object} currentSettings - Existing render settings to merge into.
 * @returns {object} New settings object with preset values applied.
 */
export function applyPreset(name, currentSettings) {
  const preset = getPreset(name);
  return { ...currentSettings, ...preset };
}
