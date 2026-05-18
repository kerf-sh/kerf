/**
 * shadowSettings.js — Pure JS helpers for Three.js shadow configuration.
 *
 * No DOM/browser/Three.js runtime dependency at import time.
 * THREE constants are inlined as named integers so this module is testable
 * without a WebGL context.
 *
 * Public API
 * ──────────
 *   SHADOW_TYPES           — ordered array of valid shadow type keys
 *   SHADOW_MAP_SIZES       — allowed shadow-map texel resolutions
 *   BIAS_MIN / BIAS_MAX    — clamp range for per-light shadow bias
 *   getThreeShadowType(t)  — map a SHADOW_TYPES key → THREE.*ShadowMap integer
 *   defaultShadowSettings()— factory: returns a fresh settings object
 *   validateShadowSettings(s) — { ok, errors }
 *   clampBias(b)           — clamp a bias value to [BIAS_MIN, BIAS_MAX]
 *   serialise(s)           — settings → JSON string
 *   deserialise(json)      — JSON string → validated settings object (throws on error)
 */

// ── Constants ──────────────────────────────────────────────────────────────────

/** Valid shadow-type keys, in display order. */
export const SHADOW_TYPES = ['basic', 'pcf', 'pcf_soft', 'vsm'];

/** Valid shadow-map resolutions (texels per side). Must be powers of two. */
export const SHADOW_MAP_SIZES = [512, 1024, 2048, 4096];

/** Bias slider range — keeps self-shadowing / peter-panning artefacts usable. */
export const BIAS_MIN = -0.01;
export const BIAS_MAX = 0.01;

/**
 * THREE.*ShadowMap integer constants, inlined so this module has no runtime
 * dependency on the Three.js package.
 *
 *   THREE.BasicShadowMap   === 0
 *   THREE.PCFShadowMap     === 1
 *   THREE.PCFSoftShadowMap === 2
 *   THREE.VSMShadowMap     === 3
 */
const THREE_SHADOW_MAP = {
  basic: 0,    // THREE.BasicShadowMap
  pcf: 1,      // THREE.PCFShadowMap
  pcf_soft: 2, // THREE.PCFSoftShadowMap
  vsm: 3,      // THREE.VSMShadowMap
};

// ── getThreeShadowType ─────────────────────────────────────────────────────────

/**
 * Map a shadow-type key to its THREE.*ShadowMap integer constant.
 *
 * @param {string} type - One of SHADOW_TYPES.
 * @returns {number} The corresponding THREE.*ShadowMap integer.
 * @throws {RangeError} If `type` is not a recognised key.
 */
export function getThreeShadowType(type) {
  if (!Object.prototype.hasOwnProperty.call(THREE_SHADOW_MAP, type)) {
    throw new RangeError(
      `Unknown shadow type: "${type}". Must be one of: ${SHADOW_TYPES.join(', ')}.`
    );
  }
  return THREE_SHADOW_MAP[type];
}

// ── clampBias ──────────────────────────────────────────────────────────────────

/**
 * Clamp a shadow-bias value to [BIAS_MIN, BIAS_MAX].
 *
 * @param {number} bias
 * @returns {number}
 */
export function clampBias(bias) {
  return Math.min(BIAS_MAX, Math.max(BIAS_MIN, bias));
}

// ── defaultShadowSettings ──────────────────────────────────────────────────────

/**
 * Create a default shadow-settings document.
 *
 * The document is plain JSON-serialisable: no class instances, no functions.
 *
 * Shape:
 * ```json
 * {
 *   "version": 1,
 *   "type": "pcf",
 *   "map_size": 1024,
 *   "lights": []
 * }
 * ```
 *
 * Per-light entries in `lights` have the shape:
 * ```json
 * { "id": "<string>", "cast_shadow": true, "bias": 0.0 }
 * ```
 *
 * @returns {object}
 */
export function defaultShadowSettings() {
  return {
    version: 1,
    type: 'pcf',
    map_size: 1024,
    lights: [],
  };
}

// ── validateShadowSettings ─────────────────────────────────────────────────────

/**
 * Validate a shadow-settings document.
 *
 * @param {unknown} settings
 * @returns {{ ok: boolean, errors: string[] }}
 */
export function validateShadowSettings(settings) {
  const errors = [];

  if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
    return { ok: false, errors: ['settings must be a plain object'] };
  }

  if (settings.version !== 1) {
    errors.push(`unsupported version: ${settings.version}`);
  }

  if (!SHADOW_TYPES.includes(settings.type)) {
    errors.push(
      `type must be one of [${SHADOW_TYPES.join(', ')}], got: ${settings.type}`
    );
  }

  if (!SHADOW_MAP_SIZES.includes(settings.map_size)) {
    errors.push(
      `map_size must be one of [${SHADOW_MAP_SIZES.join(', ')}], got: ${settings.map_size}`
    );
  }

  if (!Array.isArray(settings.lights)) {
    errors.push('lights must be an array');
  } else {
    settings.lights.forEach((light, i) => {
      if (!light || typeof light !== 'object') {
        errors.push(`lights[${i}] must be an object`);
        return;
      }
      if (!light.id || typeof light.id !== 'string') {
        errors.push(`lights[${i}].id must be a non-empty string`);
      }
      if (typeof light.cast_shadow !== 'boolean') {
        errors.push(`lights[${i}].cast_shadow must be a boolean`);
      }
      if (typeof light.bias !== 'number') {
        errors.push(`lights[${i}].bias must be a number`);
      } else if (light.bias < BIAS_MIN || light.bias > BIAS_MAX) {
        errors.push(
          `lights[${i}].bias must be in [${BIAS_MIN}, ${BIAS_MAX}], got: ${light.bias}`
        );
      }
    });
  }

  return { ok: errors.length === 0, errors };
}

// ── serialise / deserialise ────────────────────────────────────────────────────

/**
 * Serialise a shadow-settings document to a JSON string.
 *
 * @param {object} settings
 * @returns {string}
 */
export function serialise(settings) {
  return JSON.stringify(settings);
}

/**
 * Deserialise a JSON string to a shadow-settings document.
 * Validates the result and throws if it is invalid.
 *
 * @param {string} json
 * @returns {object} Validated settings document.
 * @throws {SyntaxError} If `json` is not valid JSON.
 * @throws {TypeError} If the parsed object fails validation.
 */
export function deserialise(json) {
  const parsed = JSON.parse(json); // throws SyntaxError on bad JSON
  const { ok, errors } = validateShadowSettings(parsed);
  if (!ok) {
    throw new TypeError(
      `Invalid shadow settings: ${errors.join('; ')}`
    );
  }
  return parsed;
}
