/**
 * hdriPresets.js — Static registry of HDRI sky presets.
 *
 * Each entry describes one sky environment. The actual .hdr files are NOT
 * bundled in this repository (they are large binaries). A cloud operator or
 * local-install user must place the corresponding files under `public/hdri/`
 * as described in `public/hdri/PLACEHOLDER.md`.
 *
 * Shape:
 *   {
 *     slug         — URL-safe identifier, e.g. "clear-noon"
 *     name         — Human-readable label shown in the UI
 *     file_url     — Runtime URL served from /hdri/<slug>.hdr
 *     license      — SPDX license ID or short string
 *     source       — Attribution / download URL for the original file
 *     intensity    — Default exposure multiplier (1.0 = neutral)
 *     description  — One-sentence description for tooltips / docs
 *     thumbnail_url — Preview image URL (small JPEG/PNG, can be a data-URI
 *                     or a CDN URL; null if not available)
 *   }
 */

/** @type {Array<{
 *   slug: string,
 *   name: string,
 *   file_url: string,
 *   license: string,
 *   source: string,
 *   intensity: number,
 *   description: string,
 *   thumbnail_url: string | null
 * }>} */
export const HDRI_PRESETS = [
  {
    slug: 'clear-noon',
    name: 'Clear Noon',
    file_url: '/hdri/clear-noon.hdr',
    license: 'CC0-1.0',
    source: 'https://polyhaven.com/a/clear_2k',
    intensity: 1.0,
    description: 'Bright midday sun with a clear blue sky and sharp shadows.',
    thumbnail_url: '/hdri/clear-noon.thumb.jpg',
  },
  {
    slug: 'overcast',
    name: 'Overcast',
    file_url: '/hdri/overcast.hdr',
    license: 'CC0-1.0',
    source: 'https://polyhaven.com/a/kloppenheim_06_puresky',
    intensity: 1.2,
    description: 'Soft, diffuse lighting from a fully overcast sky with no directional shadows.',
    thumbnail_url: '/hdri/overcast.thumb.jpg',
  },
  {
    slug: 'sunset',
    name: 'Sunset',
    file_url: '/hdri/sunset.hdr',
    license: 'CC0-1.0',
    source: 'https://polyhaven.com/a/sunset_jhbcentral',
    intensity: 0.9,
    description: 'Warm golden-hour light with long shadows and an orange horizon glow.',
    thumbnail_url: '/hdri/sunset.thumb.jpg',
  },
  {
    slug: 'studio-soft',
    name: 'Studio Soft',
    file_url: '/hdri/studio-soft.hdr',
    license: 'CC0-1.0',
    source: 'https://polyhaven.com/a/studio_small_08',
    intensity: 1.5,
    description: 'Neutral studio environment with soft, even illumination ideal for product shots.',
    thumbnail_url: '/hdri/studio-soft.thumb.jpg',
  },
  {
    slug: 'night-stars',
    name: 'Night Stars',
    file_url: '/hdri/night-stars.hdr',
    license: 'CC0-1.0',
    source: 'https://polyhaven.com/a/starry_night',
    intensity: 0.3,
    description: 'Dark night sky with visible stars and subtle ambient moonlight.',
    thumbnail_url: '/hdri/night-stars.thumb.jpg',
  },
]

/**
 * Look up a single preset by its slug.
 * @param {string} slug
 * @returns {{ slug: string, name: string, file_url: string, license: string,
 *             source: string, intensity: number, description: string,
 *             thumbnail_url: string | null } | undefined}
 */
export function getPresetBySlug(slug) {
  return HDRI_PRESETS.find((p) => p.slug === slug)
}
