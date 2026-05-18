/**
 * iesPresets.js — Built-in IES light profile presets.
 *
 * Each entry maps to a synthetic LM-63-1991 fixture file under /ies/.
 * These files ship as static assets in public/ies/ and are served directly
 * by the Vite dev server (and copied to dist/ by the build).
 *
 * Categories:
 *   downlight  (3) — recessed ceiling fixtures, primarily downward emission
 *   wall-wash  (2) — asymmetric, designed to graze vertical surfaces
 *   spot       (2) — narrow-beam accent / track fixtures
 *   flood      (2) — wide-angle area fixtures including batwing
 *   specialty  (3) — candle, pendant, linear strip
 */

export const IES_PRESETS = [
  // ── Downlights ─────────────────────────────────────────────────────────────
  {
    slug: 'downlight-a',
    name: 'Downlight A',
    category: 'downlight',
    file_path: '/ies/downlight-a.ies',
    description: 'Recessed downlight, symmetric distribution, 1000 lm.',
  },
  {
    slug: 'downlight-b',
    name: 'Downlight B',
    category: 'downlight',
    file_path: '/ies/downlight-b.ies',
    description: 'Recessed downlight, wide-angle beam, 800 lm.',
  },
  {
    slug: 'downlight-c',
    name: 'Downlight C',
    category: 'downlight',
    file_path: '/ies/downlight-c.ies',
    description: 'Recessed downlight, narrow beam, 1200 lm.',
  },

  // ── Wall-wash ──────────────────────────────────────────────────────────────
  {
    slug: 'wallwash-a',
    name: 'Wall Wash A',
    category: 'wall-wash',
    file_path: '/ies/wallwash-a.ies',
    description: 'Asymmetric wall-wash fixture, 600 lm.',
  },
  {
    slug: 'wallwash-b',
    name: 'Wall Wash B',
    category: 'wall-wash',
    file_path: '/ies/wallwash-b.ies',
    description: 'Adjustable wall-wash, oval beam, 750 lm.',
  },

  // ── Spot ───────────────────────────────────────────────────────────────────
  {
    slug: 'spot-narrow',
    name: 'Narrow Spot',
    category: 'spot',
    file_path: '/ies/spot-narrow.ies',
    description: 'Narrow spot, 10° beam angle, 500 lm.',
  },
  {
    slug: 'spot-track',
    name: 'Track Spot',
    category: 'spot',
    file_path: '/ies/spot-track.ies',
    description: 'Track-mounted spotlight, 25° beam angle, 900 lm.',
  },

  // ── Flood ──────────────────────────────────────────────────────────────────
  {
    slug: 'flood-wide',
    name: 'Wide Flood',
    category: 'flood',
    file_path: '/ies/flood-wide.ies',
    description: 'Wide flood, 60° beam angle, 1500 lm.',
  },
  {
    slug: 'flood-batwing',
    name: 'Batwing Flood',
    category: 'flood',
    file_path: '/ies/flood-batwing.ies',
    description: 'Batwing distribution, maximum emission at 60°, 2000 lm.',
  },

  // ── Specialty ──────────────────────────────────────────────────────────────
  {
    slug: 'specialty-candle',
    name: 'Candle',
    category: 'specialty',
    file_path: '/ies/specialty-candle.ies',
    description: 'Candle-form omnidirectional lamp, 200 lm.',
  },
  {
    slug: 'specialty-pendant',
    name: 'Pendant Globe',
    category: 'specialty',
    file_path: '/ies/specialty-pendant.ies',
    description: 'Pendant globe, wide symmetric distribution, 450 lm.',
  },
  {
    slug: 'specialty-linear',
    name: 'Linear Strip',
    category: 'specialty',
    file_path: '/ies/specialty-linear.ies',
    description: 'Linear LED strip 1200 mm, lambertian distribution, 3000 lm.',
  },
]
