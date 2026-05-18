/**
 * compareSearch.js — fuzzy/substring search over the compare manifest.
 *
 * Each manifest item has the shape:
 *   { slug, competitor, category, hero_tagline }
 *
 * Search matches substring (case-insensitive) on competitor + slug + hero_tagline.
 * Empty query returns all items.
 *
 * Categories align with the new .md schema pill values:
 *   cad-mechanical | cad-electronics | cad-architecture | cad-sim
 *   cad-silicon | cad-firmware | cad-creative
 */

/**
 * The canonical compare manifest — single source of truth for the landing.
 *
 * `category` values map to pill slugs. `hero_tagline` is the one-line
 * description shown on each card.
 *
 * @type {Array<{slug: string, competitor: string, category: string, hero_tagline: string}>}
 */
export const COMPARE_MANIFEST = [
  // ── cad-mechanical ─────────────────────────────────────────────────────────
  {
    slug: 'freecad',
    competitor: 'FreeCAD',
    category: 'cad-mechanical',
    hero_tagline: 'Open-source parametric B-rep modeller',
  },
  {
    slug: 'fusion',
    competitor: 'Fusion 360',
    category: 'cad-mechanical',
    hero_tagline: 'Cloud-connected mechanical CAD',
  },
  {
    slug: 'solidworks',
    competitor: 'SOLIDWORKS',
    category: 'cad-mechanical',
    hero_tagline: 'Industry-standard mechanical CAD',
  },
  {
    slug: 'onshape',
    competitor: 'Onshape',
    category: 'cad-mechanical',
    hero_tagline: 'Browser-native real-time-collab CAD',
  },
  {
    slug: 'inventor',
    competitor: 'Inventor',
    category: 'cad-mechanical',
    hero_tagline: "Autodesk's professional mechanical CAD",
  },
  {
    slug: 'autocad',
    competitor: 'AutoCAD',
    category: 'cad-mechanical',
    hero_tagline: 'Industry-standard 2D drafting + 3D modelling',
  },

  // ── cad-electronics ────────────────────────────────────────────────────────
  {
    slug: 'kicad',
    competitor: 'KiCad',
    category: 'cad-electronics',
    hero_tagline: 'Open-source EDA suite',
  },
  {
    slug: 'altium',
    competitor: 'Altium Designer',
    category: 'cad-electronics',
    hero_tagline: 'Industrial-grade PCB design',
  },

  // ── cad-architecture ───────────────────────────────────────────────────────
  {
    slug: 'revit',
    competitor: 'Revit',
    category: 'cad-architecture',
    hero_tagline: 'Industry-standard BIM platform',
  },
  {
    slug: 'civil3d',
    competitor: 'Civil 3D',
    category: 'cad-architecture',
    hero_tagline: 'Civil infrastructure design',
  },

  // ── cad-creative ───────────────────────────────────────────────────────────
  {
    slug: 'rhino',
    competitor: 'Rhino',
    category: 'cad-creative',
    hero_tagline: 'NURBS & jewelry CAD (MatrixGold / RhinoGold)',
  },
  {
    slug: 'matrixgold',
    competitor: 'MatrixGold',
    category: 'cad-creative',
    hero_tagline: 'Industry-standard jewelry CAD',
  },
  {
    slug: 'blender',
    competitor: 'Blender',
    category: 'cad-creative',
    hero_tagline: 'Mesh / DCC tool (not a B-rep CAD)',
  },
  {
    slug: 'max3ds',
    competitor: '3ds Max',
    category: 'cad-creative',
    hero_tagline: 'Archviz & game-art DCC',
  },
]

/**
 * Category pill metadata — ordered for display in the pill row.
 *
 * @type {Array<{id: string, label: string}>}
 */
export const COMPARE_CATEGORIES = [
  { id: 'cad-mechanical',   label: 'Mechanical CAD' },
  { id: 'cad-electronics',  label: 'Electronics' },
  { id: 'cad-architecture', label: 'Architecture / BIM' },
  { id: 'cad-sim',          label: 'Simulation' },
  { id: 'cad-silicon',      label: 'Silicon / ASIC' },
  { id: 'cad-firmware',     label: 'Firmware' },
  { id: 'cad-creative',     label: 'Creative / DCC' },
]

/**
 * Search the compare manifest.
 *
 * @param {string} query - substring to match (case-insensitive); empty = all items
 * @param {string|null} category - category id to filter by, or null for all
 * @returns {Array<{slug: string, competitor: string, category: string, hero_tagline: string}>}
 */
export function compareSearch(query, category = null) {
  const q = (query ?? '').trim().toLowerCase()

  let items = COMPARE_MANIFEST

  // Filter by category pill first
  if (category) {
    items = items.filter((item) => item.category === category)
  }

  // Filter by substring match across slug + competitor + hero_tagline
  if (q.length > 0) {
    items = items.filter(
      (item) =>
        item.slug.toLowerCase().includes(q) ||
        item.competitor.toLowerCase().includes(q) ||
        item.hero_tagline.toLowerCase().includes(q),
    )
  }

  return items
}

/**
 * Group an array of manifest items by category, preserving COMPARE_CATEGORIES order.
 *
 * @param {Array} items
 * @returns {Array<{category: string, label: string, items: Array}>}
 */
export function groupByCategory(items) {
  const map = new Map()
  for (const cat of COMPARE_CATEGORIES) {
    map.set(cat.id, { category: cat.id, label: cat.label, items: [] })
  }
  // Items not in COMPARE_CATEGORIES get appended at end
  for (const item of items) {
    if (map.has(item.category)) {
      map.get(item.category).items.push(item)
    } else {
      if (!map.has(item.category)) {
        map.set(item.category, { category: item.category, label: item.category, items: [] })
      }
      map.get(item.category).items.push(item)
    }
  }
  return [...map.values()].filter((g) => g.items.length > 0)
}
