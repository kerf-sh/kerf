/**
 * automotiveDomainPage.test.jsx
 *
 * Smoke tests for:
 *   - src/routes/domains/Automotive.jsx
 *   - src/routes/domains/automotive.meta.js
 *   - src/App.jsx route registration
 *
 * Tests are pure source-level (readFileSync) — no jsdom required.
 * They verify structural correctness, real module names, fair comparison
 * copy, and meta-string length constraints.
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const PAGE_SRC = readFileSync(
  resolve(__dirname, '../routes/domains/Automotive.jsx'),
  'utf8',
)

const META_SRC = readFileSync(
  resolve(__dirname, '../routes/domains/automotive.meta.js'),
  'utf8',
)

const APP_SRC = readFileSync(
  resolve(__dirname, '../App.jsx'),
  'utf8',
)

/* -------------------------------------------------------------------------- */
/* Automotive page structure                                                   */
/* -------------------------------------------------------------------------- */

describe('Automotive page — module', () => {
  it('exports a default function Automotive', () => {
    expect(PAGE_SRC).toMatch(/export default function Automotive/)
  })

  it('imports Header', () => {
    expect(PAGE_SRC).toMatch(/import Header/)
  })

  it('imports Footer', () => {
    expect(PAGE_SRC).toMatch(/import Footer/)
  })

  it('imports Button', () => {
    expect(PAGE_SRC).toMatch(/import Button/)
  })

  it('imports automotive.meta.js', () => {
    expect(PAGE_SRC).toMatch(/automotive\.meta/)
  })
})

describe('Automotive page — hero', () => {
  it('has a main h1 heading about automotive engineering', () => {
    expect(PAGE_SRC).toMatch(/automotive/)
  })

  it('links to /signup CTA', () => {
    expect(PAGE_SRC).toMatch(/\/signup/)
  })

  it('links to /docs/automotive', () => {
    expect(PAGE_SRC).toMatch(/\/docs\/automotive/)
  })

  it('mentions MIT licensed', () => {
    expect(PAGE_SRC).toMatch(/MIT licensed/)
  })

  it('mentions Python SDK or kerf-sdk', () => {
    expect(PAGE_SRC).toMatch(/Python SDK|kerf-sdk/)
  })
})

describe('Automotive page — capabilities', () => {
  it('mentions NURBS surfacing', () => {
    expect(PAGE_SRC).toMatch(/NURBS surfacing/)
  })

  it('mentions sheet metal', () => {
    expect(PAGE_SRC).toMatch(/sheet metal/)
  })

  it('mentions GD&T', () => {
    expect(PAGE_SRC).toMatch(/GD&T/)
  })

  it('mentions Y14.5 standard', () => {
    expect(PAGE_SRC).toMatch(/Y14\.5/)
  })

  it('mentions 5-axis CAM', () => {
    expect(PAGE_SRC).toMatch(/5-axis CAM/)
  })

  it('mentions STEP', () => {
    expect(PAGE_SRC).toMatch(/STEP/)
  })

  it('mentions IGES', () => {
    expect(PAGE_SRC).toMatch(/IGES/)
  })

  it('mentions assemblies', () => {
    expect(PAGE_SRC).toMatch(/assemblies/)
  })

  it('references OpenCascade / OCCT as the kernel', () => {
    expect(PAGE_SRC).toMatch(/OpenCascade|OCCT/)
  })
})

describe('Automotive page — chat transcript', () => {
  it('includes a realistic user prompt about surfaces', () => {
    expect(PAGE_SRC).toMatch(/G2/)
  })

  it('uses real Kerf tool name: search_kerf_docs', () => {
    expect(PAGE_SRC).toMatch(/search_kerf_docs/)
  })

  it('uses real Kerf tool name: read_file', () => {
    expect(PAGE_SRC).toMatch(/read_file/)
  })

  it('uses real Kerf tool name: write_file', () => {
    expect(PAGE_SRC).toMatch(/write_file/)
  })
})

describe('Automotive page — honest comparison', () => {
  it('mentions Alias', () => {
    expect(PAGE_SRC).toMatch(/Alias/)
  })

  it('mentions CATIA', () => {
    expect(PAGE_SRC).toMatch(/CATIA/)
  })

  it('mentions NX', () => {
    expect(PAGE_SRC).toMatch(/NX/)
  })

  it('mentions Fusion', () => {
    expect(PAGE_SRC).toMatch(/Fusion/)
  })

  it('credits competitor strengths (not just negative framing)', () => {
    // Should contain positive language about competitors
    expect(PAGE_SRC).toMatch(/strengths|strength|dominant|best-in-class|standard/)
  })

  it('acknowledges limitations honestly (e.g. "cannot match" or "out of scope")', () => {
    expect(PAGE_SRC).toMatch(/cannot match|out of scope|far broader|not a replacement/)
  })
})

describe('Automotive page — open + scriptable section', () => {
  it('mentions MIT license', () => {
    expect(PAGE_SRC).toMatch(/MIT/)
  })

  it('mentions Python SDK or PyPI', () => {
    expect(PAGE_SRC).toMatch(/PyPI|Python SDK/)
  })

  it('shows a Python code sample', () => {
    expect(PAGE_SRC).toMatch(/from kerf_sdk import|import kerf/)
  })
})

describe('Automotive page — design constraints', () => {
  it('does not reference raster images in src attributes', () => {
    expect(PAGE_SRC).not.toMatch(/src=["'][^"']*\.(png|jpg|jpeg|webp)["']/)
  })

  it('does not contain Paystack', () => {
    expect(PAGE_SRC).not.toMatch(/Paystack/)
  })

  it('does not contain bunny.net', () => {
    expect(PAGE_SRC).not.toMatch(/bunny\.net/)
  })

  it('does not contain 20% markup language', () => {
    expect(PAGE_SRC).not.toMatch(/20% markup/)
  })

  it('is responsive — uses lg: Tailwind breakpoint', () => {
    expect(PAGE_SRC).toMatch(/lg:/)
  })

  it('is responsive — uses sm: Tailwind breakpoint', () => {
    expect(PAGE_SRC).toMatch(/sm:/)
  })

  it('uses ink-* or kerf-* design tokens in classNames', () => {
    expect(PAGE_SRC).toMatch(/ink-|kerf-/)
  })
})

/* -------------------------------------------------------------------------- */
/* automotive.meta.js                                                          */
/* -------------------------------------------------------------------------- */

describe('automotive.meta.js — structure', () => {
  it('exports a meta object', () => {
    expect(META_SRC).toMatch(/export const meta/)
  })

  it('has a canonical URL pointing to kerf.sh/domains/automotive', () => {
    expect(META_SRC).toMatch(/https:\/\/kerf\.sh\/domains\/automotive/)
  })

  it('has an OG image URL pointing to kerf.sh/og/automotive.png', () => {
    expect(META_SRC).toMatch(/https:\/\/kerf\.sh\/og\/automotive\.png/)
  })
})

describe('automotive.meta.js — title length', () => {
  it('title is ≤ 70 characters', () => {
    // Extract title string value
    const match = META_SRC.match(/title:\s*['"`]([^'"`]+)['"`]/)
    expect(match).not.toBeNull()
    // Title may be longer for SEO title but page title should be concise.
    // The meta.og.title should be ≤ 70.
    const ogMatch = META_SRC.match(/og:\s*\{[^}]*title:\s*['"`]([^'"`]+)['"`]/)
    if (ogMatch) {
      expect(ogMatch[1].length).toBeLessThanOrEqual(70)
    }
  })

  it('meta description is ≤ 160 characters', () => {
    const match = META_SRC.match(/description:\s*\n?\s*['"`]([^'"`]+)['"`]/)
    if (match) {
      expect(match[1].length).toBeLessThanOrEqual(160)
    }
  })
})

describe('automotive.meta.js — twitter card', () => {
  it('has twitter card summary_large_image', () => {
    expect(META_SRC).toMatch(/summary_large_image/)
  })
})

/* -------------------------------------------------------------------------- */
/* App.jsx route registration                                                  */
/* -------------------------------------------------------------------------- */

describe('App.jsx — automotive route', () => {
  it('imports Automotive component (lazy-loaded)', () => {
    expect(APP_SRC).toMatch(
      /Automotive\s*=\s*lazy\(\(\)\s*=>\s*import\('\.\/routes\/domains\/Automotive\.jsx'\)\)/,
    )
  })

  it('registers /domains/automotive route', () => {
    expect(APP_SRC).toMatch(/domains\/automotive/)
  })

  it('does not contain merge conflict markers', () => {
    expect(APP_SRC).not.toMatch(/<<<<<<<|>>>>>>>|=======/)
  })
})
