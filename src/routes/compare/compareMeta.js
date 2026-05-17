/**
 * compareMeta.js — shared SEO meta + JSON-LD generator for /compare/* pages.
 *
 * Usage:
 *   import { makeCompareMeta } from './compareMeta.js'
 *   const meta = makeCompareMeta('freecad')
 *
 *   <head>
 *     <title>{meta.title}</title>
 *     <meta name="description" content={meta.description} />
 *     <link rel="canonical" href={meta.canonical} />
 *     ...
 *   </head>
 */

const BASE = 'https://kerf.sh'

/** Per-slug SEO data (title ≤60 chars, description ≤155 chars). */
const PAGES = {
  freecad: {
    title: 'Kerf vs FreeCAD — chat-driven CAD compared',
    description:
      'FreeCAD is the gold standard for open-source parametric B-rep CAD. ' +
      "See how Kerf's chat-native workflow and MIT open-core stack compare.",
    slug: 'freecad',
    product: 'FreeCAD',
  },
  kicad: {
    title: 'Kerf vs KiCad — PCB design tools compared',
    description:
      "KiCad is the leading open-source EDA suite. Compare KiCad's mature " +
      "tooling against Kerf's integrated electronics + mechanical workflow.",
    slug: 'kicad',
    product: 'KiCad',
  },
  rhino: {
    title: 'Kerf vs Rhino — NURBS & jewelry CAD compared',
    description:
      'Rhino (with RhinoGold / Matrix) sets the bar for NURBS surfacing and ' +
      "jewelry CAD. See where Kerf's open-core approach stands today.",
    slug: 'rhino',
    product: 'Rhino',
  },
  revit: {
    title: 'Kerf vs Revit — architecture BIM compared',
    description:
      'Revit is the industry-standard BIM platform for architecture. Compare ' +
      "its deep BIM toolset against Kerf's IFC-capable open-core workspace.",
    slug: 'revit',
    product: 'Revit',
  },
  fusion: {
    title: 'Kerf vs Fusion 360 — cloud CAD compared',
    description:
      "Fusion 360 pioneered cloud-connected mechanical CAD. See how Kerf's " +
      'MIT open-core, chat-driven approach compares on features and pricing.',
    slug: 'fusion',
    product: 'Fusion 360',
  },
  solidworks: {
    title: 'Kerf vs SOLIDWORKS — mechanical CAD compared',
    description:
      'SOLIDWORKS is the incumbent professional mechanical CAD. See how ' +
      "Kerf's MIT open-core, chat-driven, multi-discipline workspace compares — honestly.",
    slug: 'solidworks',
    product: 'SOLIDWORKS',
  },
  onshape: {
    title: 'Kerf vs Onshape — cloud CAD compared',
    description:
      "Onshape pioneered real-time collaborative cloud CAD. See how Kerf's " +
      'MIT open-core, chat-driven, multi-discipline stack compares.',
    slug: 'onshape',
    product: 'Onshape',
  },
  altium: {
    title: 'Kerf vs Altium Designer — PCB & ECAD tools compared',
    description:
      'Altium Designer is the industry-standard commercial ECAD platform. ' +
      "See how Kerf's open-core, multi-discipline, chat-driven approach compares.",
    slug: 'altium',
    product: 'Altium Designer',
  },
  matrixgold: {
    title: 'Kerf vs MatrixGold — jewelry CAD compared',
    description:
      'MatrixGold is the professional standard for jewelry CAD. See how ' +
      "Kerf's 40-module jewelry vertical, open-core licence, and workflow " +
      'compare — honestly.',
    slug: 'matrixgold',
    product: 'MatrixGold',
  },
  blender: {
    title: 'Kerf vs Blender — CAD vs DCC compared',
    description:
      'Blender is a world-class mesh/DCC tool, not a B-rep CAD. See where they ' +
      "overlap and where Kerf's parametric engineering workflow is the right fit.",
    slug: 'blender',
    product: 'Blender',
  },
  autocad: {
    title: 'Kerf vs AutoCAD — drafting vs parametric 3D CAD compared',
    description:
      'AutoCAD owns 2D drafting and the .dwg ecosystem. See where Kerf fits — ' +
      'a 3D parametric workspace with chat-driven UX and multi-discipline scope.',
    slug: 'autocad',
    product: 'AutoCAD',
  },
  inventor: {
    title: 'Kerf vs Autodesk Inventor — mechanical CAD compared',
    description:
      'Inventor is a top-tier mechanical CAD. See where Kerf overlaps and where ' +
      'the multi-discipline parametric history workflow differs.',
    slug: 'inventor',
    product: 'Autodesk Inventor',
  },
  civil3d: {
    title: 'Kerf vs Civil 3D — civil infrastructure design compared',
    description:
      'Civil 3D owns corridor modelling and pipe networks. See where Kerf ' +
      "complements with civil-engineering calc modules (hydrology / geotech / pavement / surveying).",
    slug: 'civil3d',
    product: 'Civil 3D',
  },
  max3ds: {
    title: 'Kerf vs 3ds Max — modelling and rendering compared',
    description:
      '3ds Max is the archviz / game-art DCC standard. See where Kerf overlaps ' +
      'for product visualisation and where the engineering CAD workflow differs.',
    slug: 'max3ds',
    product: '3ds Max',
  },
}

/**
 * Returns title, description, canonical URL, OG image URL, and a JSON-LD
 * WebPage schema string for the given slug.
 */
export function makeCompareMeta(slug) {
  const page = PAGES[slug]
  if (!page) throw new Error(`Unknown compare slug: ${slug}`)

  const canonical = `${BASE}/compare/${slug}`
  const ogImage = `${BASE}/og/compare-${slug}.png`

  const jsonLd = JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: page.title,
    description: page.description,
    url: canonical,
    image: ogImage,
    publisher: {
      '@type': 'Organization',
      name: 'Kerf',
      url: BASE,
    },
  })

  return {
    title: page.title,
    description: page.description,
    canonical,
    ogImage,
    jsonLd,
    product: page.product,
    slug,
  }
}

export { PAGES }
