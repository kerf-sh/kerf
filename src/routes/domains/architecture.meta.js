/**
 * SEO + JSON-LD metadata for the Architecture & Civil domain page.
 * Imported by Architecture.jsx to render <head> tags via a Helmet-style
 * pattern, and also imported directly by the test suite.
 */

export const ARCH_META = {
  title: 'Architectural CAD with chat-driven design — Kerf',
  description:
    'Open-source chat-driven CAD for architecture. IFC Tier 2 import, DXF, drawings, structural sketcher, stairs, BOM. Honest about BIM depth vs Revit.',
  canonicalUrl: 'https://kerf.sh/domains/architecture',
  ogImage: 'https://kerf.sh/og/architecture.png',
  updatedDate: '2026-05-15',
}

// JSON-LD WebPage + ItemList for the capabilities section
export function buildArchJsonLd() {
  return JSON.stringify({
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'WebPage',
        '@id': ARCH_META.canonicalUrl,
        name: ARCH_META.title,
        description: ARCH_META.description,
        url: ARCH_META.canonicalUrl,
        dateModified: ARCH_META.updatedDate,
        image: ARCH_META.ogImage,
        isPartOf: { '@id': 'https://kerf.sh' },
      },
      {
        '@type': 'ItemList',
        name: 'Architecture & Civil capabilities in Kerf',
        itemListElement: [
          {
            '@type': 'ListItem',
            position: 1,
            name: 'IFC Tier 2 import',
            description: 'Revit-compatible IFC 2x3/4 import via the open-core OCCT kernel.',
          },
          {
            '@type': 'ListItem',
            position: 2,
            name: 'DXF read/write',
            description: 'AutoCAD DXF interchange for drafting workflows.',
          },
          {
            '@type': 'ListItem',
            position: 3,
            name: 'Drawings',
            description: 'Multi-sheet TechDraw drawings with dims and GD&T.',
          },
          {
            '@type': 'ListItem',
            position: 4,
            name: 'Stairs builder',
            description: 'StairView: parametric stair from L1 to L2 with configurable risers.',
          },
          {
            '@type': 'ListItem',
            position: 5,
            name: 'Structural sketcher',
            description: 'Constrained 2D sketcher for structural cross-sections.',
          },
          {
            '@type': 'ListItem',
            position: 6,
            name: 'BOM + distributors',
            description: 'Bill of materials with distributor pricing for procurement workflows.',
          },
          {
            '@type': 'ListItem',
            position: 7,
            name: 'File-revision history',
            description: 'Fine-grained undo / revision history for every project file.',
          },
        ],
      },
    ],
  })
}
