// architectureDomainPage.test.jsx — coverage for the exported pure-data constants
// and the JSON-LD builder in the Architecture domain page and its meta module.
//
// DOM rendering is out of scope for this suite (no jsdom environment). We test:
//   - ARCH_META shape and SEO constraints (title ≤60 chars, description ≤155 chars)
//   - buildArchJsonLd() produces valid JSON-LD with expected @type values
//   - TODAY_CAPABILITIES list shape, uniqueness, and no-oversell rules
//   - ARCH_ROADMAP items are distinct from TODAY_CAPABILITIES
//   - COMPARISON_ROWS shape: kerf column always present, required features present
//   - CHAT_TURNS: alternating user/assistant roles, uses real module names

import { describe, it, expect } from 'vitest'
import { ARCH_META, buildArchJsonLd } from '../routes/domains/architecture.meta.js'
import {
  TODAY_CAPABILITIES,
  ARCH_ROADMAP,
  COMPARISON_ROWS,
  CHAT_TURNS,
} from '../routes/domains/Architecture.jsx'

/* -------------------------------------------------------------------------- */
/* ARCH_META — SEO constraints                                                 */
/* -------------------------------------------------------------------------- */

describe('ARCH_META', () => {
  it('has a title of 60 characters or fewer', () => {
    expect(ARCH_META.title.length).toBeLessThanOrEqual(60)
  })

  it('has a description of 155 characters or fewer', () => {
    expect(ARCH_META.description.length).toBeLessThanOrEqual(155)
  })

  it('canonical URL points to /domains/architecture', () => {
    expect(ARCH_META.canonicalUrl).toContain('/domains/architecture')
  })

  it('OG image URL points to kerf.sh/og/architecture.png', () => {
    expect(ARCH_META.ogImage).toBe('https://kerf.sh/og/architecture.png')
  })

  it('updatedDate matches expected format YYYY-MM-DD', () => {
    expect(ARCH_META.updatedDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

/* -------------------------------------------------------------------------- */
/* buildArchJsonLd — JSON-LD validity                                          */
/* -------------------------------------------------------------------------- */

describe('buildArchJsonLd', () => {
  it('returns valid JSON', () => {
    expect(() => JSON.parse(buildArchJsonLd())).not.toThrow()
  })

  it('contains a WebPage node', () => {
    const ld = JSON.parse(buildArchJsonLd())
    const graph = ld['@graph']
    expect(Array.isArray(graph)).toBe(true)
    const page = graph.find((n) => n['@type'] === 'WebPage')
    expect(page).toBeDefined()
    expect(page.url).toContain('/domains/architecture')
  })

  it('contains an ItemList node with at least 5 items', () => {
    const ld = JSON.parse(buildArchJsonLd())
    const list = ld['@graph'].find((n) => n['@type'] === 'ItemList')
    expect(list).toBeDefined()
    expect(list.itemListElement.length).toBeGreaterThanOrEqual(5)
  })

  it('ItemList positions are sequential starting at 1', () => {
    const ld = JSON.parse(buildArchJsonLd())
    const list = ld['@graph'].find((n) => n['@type'] === 'ItemList')
    list.itemListElement.forEach((item, i) => {
      expect(item.position).toBe(i + 1)
    })
  })

  it('ItemList items each have name and description', () => {
    const ld = JSON.parse(buildArchJsonLd())
    const list = ld['@graph'].find((n) => n['@type'] === 'ItemList')
    list.itemListElement.forEach((item) => {
      expect(typeof item.name).toBe('string')
      expect(item.name.length).toBeGreaterThan(0)
      expect(typeof item.description).toBe('string')
      expect(item.description.length).toBeGreaterThan(0)
    })
  })
})

/* -------------------------------------------------------------------------- */
/* TODAY_CAPABILITIES — what's shipped today                                   */
/* -------------------------------------------------------------------------- */

describe('TODAY_CAPABILITIES', () => {
  it('is a non-empty array', () => {
    expect(Array.isArray(TODAY_CAPABILITIES)).toBe(true)
    expect(TODAY_CAPABILITIES.length).toBeGreaterThan(0)
  })

  it('each capability has id, icon, title, and subtitle', () => {
    TODAY_CAPABILITIES.forEach((cap) => {
      expect(typeof cap.id).toBe('string')
      expect(cap.id.length).toBeGreaterThan(0)
      expect(typeof cap.title).toBe('string')
      expect(cap.title.length).toBeGreaterThan(0)
      expect(typeof cap.subtitle).toBe('string')
      expect(cap.subtitle.length).toBeGreaterThan(0)
      // icon must be defined (React component — Lucide icons may be objects or functions)
      expect(cap.icon).toBeDefined()
      expect(cap.icon).not.toBeNull()
    })
  })

  it('ids are unique', () => {
    const ids = TODAY_CAPABILITIES.map((c) => c.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('includes IFC import capability', () => {
    const ifc = TODAY_CAPABILITIES.find((c) => c.id === 'ifc-import')
    expect(ifc).toBeDefined()
    expect(ifc.title).toContain('IFC')
  })

  it('includes DXF capability', () => {
    const dxf = TODAY_CAPABILITIES.find((c) => c.id === 'dxf')
    expect(dxf).toBeDefined()
  })

  it('includes stairs builder capability', () => {
    const stairs = TODAY_CAPABILITIES.find((c) => c.id === 'stairs')
    expect(stairs).toBeDefined()
    // Should mention StairView (the real module name)
    expect(stairs.subtitle).toContain('StairView')
  })

  it('includes BOM capability', () => {
    const bom = TODAY_CAPABILITIES.find((c) => c.id === 'bom')
    expect(bom).toBeDefined()
  })

  it('includes file-revision history capability', () => {
    const revisions = TODAY_CAPABILITIES.find((c) => c.id === 'revisions')
    expect(revisions).toBeDefined()
  })

  it('does NOT include parametric walls/doors (not yet shipped)', () => {
    // Parametric BIM elements are roadmap items. Ensure they don't appear
    // as shipped capabilities.
    const parametricBim = TODAY_CAPABILITIES.find(
      (c) =>
        c.title.toLowerCase().includes('parametric wall') ||
        c.title.toLowerCase().includes('parametric door') ||
        c.id === 'parametric-bim'
    )
    expect(parametricBim).toBeUndefined()
  })

  it('does NOT include IFC export (not yet shipped)', () => {
    const ifcExport = TODAY_CAPABILITIES.find(
      (c) =>
        c.id === 'ifc-export' ||
        (c.title.toLowerCase().includes('ifc') && c.title.toLowerCase().includes('export'))
    )
    expect(ifcExport).toBeUndefined()
  })
})

/* -------------------------------------------------------------------------- */
/* ARCH_ROADMAP — upcoming items                                               */
/* -------------------------------------------------------------------------- */

describe('ARCH_ROADMAP', () => {
  it('is a non-empty array', () => {
    expect(Array.isArray(ARCH_ROADMAP)).toBe(true)
    expect(ARCH_ROADMAP.length).toBeGreaterThan(0)
  })

  it('each item has id, title, and body', () => {
    ARCH_ROADMAP.forEach((item) => {
      expect(typeof item.id).toBe('string')
      expect(item.id.length).toBeGreaterThan(0)
      expect(typeof item.title).toBe('string')
      expect(item.title.length).toBeGreaterThan(0)
      expect(typeof item.body).toBe('string')
      expect(item.body.length).toBeGreaterThan(0)
    })
  })

  it('ids are unique', () => {
    const ids = ARCH_ROADMAP.map((r) => r.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('includes BIM Tier 2/3 as a roadmap item', () => {
    const bim = ARCH_ROADMAP.find((r) => r.id === 'bim-tier2')
    expect(bim).toBeDefined()
  })

  it('includes IFC export as a roadmap item', () => {
    const ifcExport = ARCH_ROADMAP.find((r) => r.id === 'ifc-export')
    expect(ifcExport).toBeDefined()
  })

  it('no roadmap id overlaps with TODAY_CAPABILITIES ids', () => {
    const todayIds = new Set(TODAY_CAPABILITIES.map((c) => c.id))
    ARCH_ROADMAP.forEach((r) => {
      expect(todayIds.has(r.id)).toBe(false)
    })
  })
})

/* -------------------------------------------------------------------------- */
/* COMPARISON_ROWS — fair comparison table                                     */
/* -------------------------------------------------------------------------- */

describe('COMPARISON_ROWS', () => {
  it('is a non-empty array', () => {
    expect(Array.isArray(COMPARISON_ROWS)).toBe(true)
    expect(COMPARISON_ROWS.length).toBeGreaterThan(0)
  })

  it('each row has feature and kerf columns', () => {
    COMPARISON_ROWS.forEach((row) => {
      expect(typeof row.feature).toBe('string')
      expect(row.feature.length).toBeGreaterThan(0)
      expect(row.kerf).toBeDefined()
    })
  })

  it('each row has all five competitor columns', () => {
    COMPARISON_ROWS.forEach((row) => {
      expect(row.revit).toBeDefined()
      expect(row.archicad).toBeDefined()
      expect(row.autocad).toBeDefined()
      expect(row.freecadArch).toBeDefined()
      expect(row.bricsadBim).toBeDefined()
    })
  })

  it('includes a "Parametric BIM depth" row', () => {
    const row = COMPARISON_ROWS.find((r) => r.feature === 'Parametric BIM depth')
    expect(row).toBeDefined()
  })

  it('Revit has full (true) parametric BIM depth — credit given', () => {
    const row = COMPARISON_ROWS.find((r) => r.feature === 'Parametric BIM depth')
    expect(row.revit).toBe(true)
  })

  it('Kerf does NOT claim full parametric BIM depth', () => {
    const row = COMPARISON_ROWS.find((r) => r.feature === 'Parametric BIM depth')
    // Must be 'partial' or false — never true
    expect(row.kerf).not.toBe(true)
  })

  it('IFC import row exists and Kerf has it', () => {
    const row = COMPARISON_ROWS.find((r) => r.feature === 'IFC import')
    expect(row).toBeDefined()
    expect(row.kerf).toBe(true)
  })

  it('IFC export row exists and Kerf does NOT claim it as shipped', () => {
    const row = COMPARISON_ROWS.find((r) => r.feature === 'IFC export')
    expect(row).toBeDefined()
    // Kerf IFC export is not shipped — must be false or 'partial'
    expect(row.kerf).not.toBe(true)
  })

  it('Chat-driven authoring is true only for Kerf', () => {
    const row = COMPARISON_ROWS.find((r) => r.feature === 'Chat-driven authoring')
    expect(row).toBeDefined()
    expect(row.kerf).toBe(true)
    expect(row.revit).toBe(false)
    expect(row.archicad).toBe(false)
    expect(row.autocad).toBe(false)
    expect(row.freecadArch).toBe(false)
    expect(row.bricsadBim).toBe(false)
  })

  it('Open source row: Kerf is true, Revit/ArchiCAD/AutoCAD are false', () => {
    const row = COMPARISON_ROWS.find((r) => r.feature === 'Open source')
    expect(row).toBeDefined()
    expect(row.kerf).toBe(true)
    expect(row.revit).toBe(false)
    expect(row.archicad).toBe(false)
    expect(row.autocad).toBe(false)
  })

  it('Price row exists and all tools have a price value', () => {
    const row = COMPARISON_ROWS.find((r) => r.feature === 'Price')
    expect(row).toBeDefined()
    expect(typeof row.kerf).toBe('string')
    expect(row.kerf.length).toBeGreaterThan(0)
    expect(typeof row.revit).toBe('string')
    expect(typeof row.archicad).toBe('string')
    expect(typeof row.autocad).toBe('string')
    expect(typeof row.freecadArch).toBe('string')
    expect(typeof row.bricsadBim).toBe('string')
  })
})

/* -------------------------------------------------------------------------- */
/* CHAT_TURNS — realistic session                                               */
/* -------------------------------------------------------------------------- */

describe('CHAT_TURNS', () => {
  it('has 5 or 6 turns', () => {
    expect(CHAT_TURNS.length).toBeGreaterThanOrEqual(5)
    expect(CHAT_TURNS.length).toBeLessThanOrEqual(6)
  })

  it('each turn has role and text', () => {
    CHAT_TURNS.forEach((turn) => {
      expect(['user', 'assistant']).toContain(turn.role)
      expect(typeof turn.text).toBe('string')
      expect(turn.text.length).toBeGreaterThan(0)
    })
  })

  it('first turn is from the user', () => {
    expect(CHAT_TURNS[0].role).toBe('user')
  })

  it('turns alternate between user and assistant', () => {
    for (let i = 0; i < CHAT_TURNS.length - 1; i++) {
      expect(CHAT_TURNS[i].role).not.toBe(CHAT_TURNS[i + 1].role)
    }
  })

  it('references a real module name (StairView or ifc.import_tier2)', () => {
    const allText = CHAT_TURNS.map((t) => t.text).join(' ')
    const hasRealModule =
      allText.includes('StairView') ||
      allText.includes('import_tier2') ||
      allText.includes('ifc.import_tier2') ||
      allText.includes('kerf_core.ifc')
    expect(hasRealModule).toBe(true)
  })

  it('contains an IFC import turn', () => {
    const ifcTurn = CHAT_TURNS.find(
      (t) => t.text.toLowerCase().includes('ifc') && t.role === 'user'
    )
    expect(ifcTurn).toBeDefined()
  })

  it('contains a stair creation turn', () => {
    const stairTurn = CHAT_TURNS.find(
      (t) =>
        (t.text.toLowerCase().includes('stair') || t.text.toLowerCase().includes('riser')) &&
        t.role === 'user'
    )
    expect(stairTurn).toBeDefined()
  })

  it('contains a BOM export turn', () => {
    const bomTurn = CHAT_TURNS.find(
      (t) => t.text.toLowerCase().includes('bom') && t.role === 'user'
    )
    expect(bomTurn).toBeDefined()
  })
})
