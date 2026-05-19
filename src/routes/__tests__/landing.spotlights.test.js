/**
 * landing.spotlights.test.js
 *
 * Verifies that:
 *   1. DomainSpotlights exports a default function component.
 *   2. All 18 spotlight cards are present (title in source).
 *   3. Each domain slug is referenced in the SPOTLIGHTS data.
 *   4. SectorIllustration wrapper covers every sector name.
 *   5. Per-sector illustration files export a default function + have aria-label.
 *   6. No raster assets, no cloud-internal terms.
 *   7. Responsive grid classes are present.
 *   8. Landing.jsx no longer contains PerDomain.
 *
 * Intentionally no DOM rendering — tests run on source text for speed.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const SPOTLIGHTS_SRC = readFileSync(
  resolve(__dirname, '../../components/landing/DomainSpotlights.jsx'),
  'utf8',
)

const SECTOR_SRC = readFileSync(
  resolve(__dirname, '../../illustrations/SectorIllustration.jsx'),
  'utf8',
)

/* -------------------------------------------------------------------------- */
/* Module shape                                                                 */
/* -------------------------------------------------------------------------- */

describe('DomainSpotlights module shape', () => {
  it('exports a default function DomainSpotlights', () => {
    expect(SPOTLIGHTS_SRC).toMatch(/export default function DomainSpotlights/)
  })

  it('contains the "Domain spotlights" eyebrow text', () => {
    expect(SPOTLIGHTS_SRC).toMatch(/Domain spotlights/)
  })

  it('contains the "Purpose-built for your craft" heading', () => {
    expect(SPOTLIGHTS_SRC).toMatch(/Purpose-built for your craft/)
  })

  it('imports SectorIllustration', () => {
    expect(SPOTLIGHTS_SRC).toMatch(/SectorIllustration/)
  })

  it('uses template-literal link to /domains/<slug>', () => {
    // The card uses to={`/domains/${slug}`} — check the pattern exists
    expect(SPOTLIGHTS_SRC).toMatch(/\/domains\/\$\{slug\}/)
  })
})

/* -------------------------------------------------------------------------- */
/* Each of the 18 spotlights                                                   */
/* -------------------------------------------------------------------------- */

const EXPECTED = [
  { title: 'Mechanical',       slug: 'mechanical'  },
  { title: 'Electronics',      slug: 'electronics' },
  { title: 'Architecture',     slug: 'architecture'},
  { title: 'Jewelry',          slug: 'jewelry'     },
  { title: 'Automotive',       slug: 'automotive'  },
  { title: 'Aerospace',        slug: 'aerospace'   },
  { title: 'Silicon',          slug: 'silicon'     },
  { title: 'Firmware',         slug: 'firmware'    },
  { title: 'PLC',              slug: 'plc'         },
  { title: 'Composites',       slug: 'composites'  },
  { title: 'Dental',           slug: 'dental'      },
  { title: 'Optics',           slug: 'optics'      },
  { title: 'Horology',         slug: 'horology'    },
  { title: 'Marine',           slug: 'marine'      },
  { title: 'Woodworking',      slug: 'woodworking' },
  { title: 'Textiles',         slug: 'textiles'    },
  { title: 'Civil',            slug: 'civil'       },
  { title: 'Motion',           slug: 'motion'      },
]

describe('DomainSpotlights — 18 spotlight cards present', () => {
  EXPECTED.forEach(({ title, slug }) => {
    it(`card "${title}" title appears in source`, () => {
      // Title may appear as part of a longer string like "PLC / Industrial"
      expect(SPOTLIGHTS_SRC).toMatch(new RegExp(title.replace(/[/\\^$*+?.()|[\]{}]/g, '\\$&')))
    })

    it(`slug "${slug}" is referenced in source data`, () => {
      // slug appears as `slug: 'mechanical'` etc in the SPOTLIGHTS array
      expect(SPOTLIGHTS_SRC).toMatch(new RegExp(`slug:\\s*'${slug}'`))
    })
  })
})

/* -------------------------------------------------------------------------- */
/* SectorIllustration wrapper — all sector names resolve                       */
/* -------------------------------------------------------------------------- */

const SECTORS = [
  'mechanical', 'electronics', 'architecture', 'jewelry', 'automotive',
  'aerospace', 'silicon', 'firmware', 'plc', 'composites', 'dental',
  'optics', 'horology', 'marine', 'woodworking', 'textiles', 'civil',
]

describe('SectorIllustration MAP coverage', () => {
  SECTORS.forEach((sector) => {
    it(`sector "${sector}" key is present in SectorIllustration MAP`, () => {
      // MAP uses unquoted keys: `mechanical:   MechanicalIllustration,`
      expect(SECTOR_SRC).toMatch(new RegExp(`${sector}:`))
    })
  })

  it('SectorIllustration exports a default function', () => {
    expect(SECTOR_SRC).toMatch(/export default function SectorIllustration/)
  })

  it('MAP const is defined', () => {
    expect(SECTOR_SRC).toMatch(/const MAP = \{/)
  })
})

/* -------------------------------------------------------------------------- */
/* Per-sector illustration files exist and export a default function           */
/* -------------------------------------------------------------------------- */

describe('Per-sector illustration files', () => {
  SECTORS.forEach((sector) => {
    it(`src/illustrations/${sector}.jsx exports a default function`, () => {
      const src = readFileSync(
        resolve(__dirname, `../../illustrations/${sector}.jsx`),
        'utf8',
      )
      expect(src).toMatch(/export default function \w+Illustration/)
    })

    it(`src/illustrations/${sector}.jsx has a non-empty aria-label`, () => {
      const src = readFileSync(
        resolve(__dirname, `../../illustrations/${sector}.jsx`),
        'utf8',
      )
      const match = src.match(/aria-label="([^"]+)"/)
      expect(match).not.toBeNull()
      expect(match[1].length).toBeGreaterThan(5)
    })
  })
})

/* -------------------------------------------------------------------------- */
/* Design constraints                                                           */
/* -------------------------------------------------------------------------- */

describe('DomainSpotlights design constraints', () => {
  it('does not reference raster images (.png/.jpg/.webp)', () => {
    expect(SPOTLIGHTS_SRC).not.toMatch(/src=["'][^"']*\.(png|jpg|jpeg|webp)["']/)
  })

  it('does not contain cloud-internal terms (Paystack)', () => {
    expect(SPOTLIGHTS_SRC).not.toMatch(/Paystack/)
  })

  it('does not expose pricing-margin language', () => {
    expect(SPOTLIGHTS_SRC).not.toMatch(/20% markup/)
    expect(SPOTLIGHTS_SRC).not.toMatch(/bunny\.net/)
    expect(SPOTLIGHTS_SRC).not.toMatch(/go-git/)
  })

  it('uses responsive grid — md:grid-cols-2 xl:grid-cols-3', () => {
    expect(SPOTLIGHTS_SRC).toMatch(/md:grid-cols-2/)
    expect(SPOTLIGHTS_SRC).toMatch(/xl:grid-cols-3/)
  })

  it('uses lg: breakpoint prefix for responsive layout', () => {
    expect(SPOTLIGHTS_SRC).toMatch(/lg:/)
  })

  it('uses md: breakpoint prefix for illustration layout', () => {
    expect(SPOTLIGHTS_SRC).toMatch(/md:/)
  })

  it('has hover transition styles', () => {
    expect(SPOTLIGHTS_SRC).toMatch(/hover:/)
  })

  it('does not include raw hex colours in className props', () => {
    const classMatches = SPOTLIGHTS_SRC.match(/className="[^"]*#[0-9a-fA-F]{3,6}[^"]*"/g) || []
    expect(classMatches).toHaveLength(0)
  })
})

/* -------------------------------------------------------------------------- */
/* Landing.jsx — PerDomain removed                                             */
/* -------------------------------------------------------------------------- */

describe('Landing.jsx — PerDomain section removed', () => {
  const landingSrc = readFileSync(
    resolve(__dirname, '../Landing.jsx'),
    'utf8',
  )

  it('no longer contains the PerDomain function', () => {
    expect(landingSrc).not.toMatch(/function PerDomain\(\)/)
  })

  it('no longer contains the DOMAINS constant', () => {
    expect(landingSrc).not.toMatch(/const DOMAINS = \[/)
  })

  it('no longer mounts <PerDomain />', () => {
    expect(landingSrc).not.toMatch(/<PerDomain\s*\/>/)
  })

  it('still mounts <DomainSpotlights />', () => {
    expect(landingSrc).toMatch(/<DomainSpotlights\s*\/>/)
  })
})
