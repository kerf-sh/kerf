/**
 * SEO meta for the Jewelry domain page.
 *
 * title  ≤ 60 chars
 * description ≤ 155 chars
 * JSON-LD WebPage + ItemList
 * OG/Twitter: https://kerf.sh/og/jewelry.png (asset authored separately)
 */

export const JEWELRY_META = {
  title: 'Jewelry CAD with chat-driven design — Kerf',
  description:
    'Parametric rings, settings, gem seats, chains and findings — designed in conversation. 30 cuts, prong/bezel/pavé/halo, casting tables. MIT open-core.',
  ogImage: 'https://kerf.sh/og/jewelry.png',
  canonicalUrl: 'https://kerf.sh/domains/jewelry',
}

/**
 * Feature grid items — sourced from actual Kerf jewelry module names.
 * Used both on the page and in the JSON-LD ItemList.
 */
export const JEWELRY_FEATURES = [
  {
    id: 'gemstones',
    title: 'Gemstone library',
    subtitle: '30 cuts: round, oval, princess, emerald, pear, marquise, cushion, radiant and more.',
    tool: 'jewelry_gemstone',
  },
  {
    id: 'settings',
    title: 'Setting styles',
    subtitle:
      'Prong / head, gallery, bezel, under-bezel, coronet, suspension, V-tip, bombé, patterned bezel, trellis-prong, bar-channel graduated.',
    tool: 'jewelry_prong_head + jewelry_bezel_setting',
  },
  {
    id: 'gem-seat',
    title: 'Gem-seat engine',
    subtitle: 'Pavé field, halo / cluster, gypsy, baguette channel — auto-seats from stone count and pitch.',
    tool: 'jewelry_gem_seat',
  },
  {
    id: 'ring',
    title: 'Ring builder v4',
    subtitle: 'Eternity, signet, stacking, contoured, composite bands — shank sizing, comfort-fit, metal weight.',
    tool: 'jewelry_ring',
  },
  {
    id: 'chain',
    title: 'Chain designer',
    subtitle: '8 link styles (cable, curb, figaro, rope, box, wheat, Singapore, anchor) with gauge and sizing.',
    tool: 'jewelry_chain',
  },
  {
    id: 'findings',
    title: 'Findings',
    subtitle: 'Clasps, jump rings, bails, ear wires, pin stems — parametric from standard gauges.',
    tool: 'jewelry_findings',
  },
  {
    id: 'pieces',
    title: 'Piece types',
    subtitle: 'Pendant, earrings, brooch, cufflink, bangle — top-level assembly containers with mass and stone value roll-up.',
    tool: 'jewelry_piece',
  },
  {
    id: 'decorative',
    title: 'Decorative elements',
    subtitle: 'Milgrain, filigree, engraving paths, gallery lace — applied as parametric surface operations.',
    tool: 'jewelry_decorative',
  },
  {
    id: 'casting',
    title: 'Casting alloy tables',
    subtitle: '14 kt yellow, white, rose gold; sterling/fine silver; platinum 950 — density + price presets, full-quote cost panel.',
    tool: 'jewelry_casting',
  },
]

/**
 * Build a JSON-LD WebPage + ItemList object for <script type="application/ld+json">.
 */
export function buildJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: JEWELRY_META.title,
    description: JEWELRY_META.description,
    url: JEWELRY_META.canonicalUrl,
    mainEntity: {
      '@type': 'ItemList',
      name: 'Kerf jewelry design capabilities',
      itemListElement: JEWELRY_FEATURES.map((f, i) => ({
        '@type': 'ListItem',
        position: i + 1,
        name: f.title,
        description: f.subtitle,
      })),
    },
  }
}
