// SectorIllustration.test.jsx — vitest smoke tests for the SVG illustration library.
//
// Uses react-dom/server (already a project dep) to render to static markup and
// assert structural properties without @testing-library/react.

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

import SectorIllustration from './SectorIllustration.jsx'
import {
  MechanicalIllustration,
  ElectronicsIllustration,
  ArchitectureIllustration,
  JewelryIllustration,
  AutomotiveIllustration,
  AerospaceIllustration,
  SiliconIllustration,
  FirmwareIllustration,
  PLCIllustration,
  CompositesIllustration,
  DentalIllustration,
  OpticsIllustration,
  HorologyIllustration,
  MarineIllustration,
  WoodworkingIllustration,
  TextilesIllustration,
  CivilIllustration,
  SECTOR_ILLUSTRATIONS,
} from './index.js'

// ── helpers ───────────────────────────────────────────────────────────────────

function render(element) {
  return renderToStaticMarkup(element)
}

function countMatches(html, pattern) {
  return (html.match(pattern) || []).length
}

// ── 1. SECTOR_ILLUSTRATIONS array ─────────────────────────────────────────────

describe('SECTOR_ILLUSTRATIONS', () => {
  it('exports exactly 17 sector entries', () => {
    expect(SECTOR_ILLUSTRATIONS).toHaveLength(17)
  })

  it('every entry has key, label, and description', () => {
    for (const entry of SECTOR_ILLUSTRATIONS) {
      expect(entry).toHaveProperty('key')
      expect(entry).toHaveProperty('label')
      expect(entry).toHaveProperty('description')
      expect(typeof entry.key).toBe('string')
      expect(typeof entry.label).toBe('string')
      expect(typeof entry.description).toBe('string')
    }
  })

  it('keys are unique', () => {
    const keys = SECTOR_ILLUSTRATIONS.map((e) => e.key)
    expect(new Set(keys).size).toBe(keys.length)
  })
})

// ── 2. SectorIllustration router ──────────────────────────────────────────────

describe('SectorIllustration', () => {
  it('renders an SVG for every known sector key', () => {
    for (const { key } of SECTOR_ILLUSTRATIONS) {
      const html = render(<SectorIllustration sector={key} />)
      expect(html).toMatch(/<svg\b/)
    }
  })

  it('routes mechanical to the gear illustration (contains circle + polygon)', () => {
    const html = render(<SectorIllustration sector="mechanical" />)
    expect(html).toMatch(/<circle\b/)
    expect(html).toMatch(/<polygon\b/)
  })

  it('routes electronics to PCB illustration (contains path + line)', () => {
    const html = render(<SectorIllustration sector="electronics" />)
    expect(html).toMatch(/<path\b/)
    expect(html).toMatch(/<line\b/)
  })

  it('routes architecture to the iso wall illustration (contains path)', () => {
    const html = render(<SectorIllustration sector="architecture" />)
    expect(html).toMatch(/<path\b/)
  })

  it('routes jewelry to the gemstone illustration (contains polygon)', () => {
    const html = render(<SectorIllustration sector="jewelry" />)
    expect(html).toMatch(/<polygon\b/)
  })

  it('routes automotive (contains path)', () => {
    const html = render(<SectorIllustration sector="automotive" />)
    expect(html).toMatch(/<path\b/)
  })

  it('routes aerospace (contains path + line)', () => {
    const html = render(<SectorIllustration sector="aerospace" />)
    expect(html).toMatch(/<path\b/)
    expect(html).toMatch(/<line\b/)
  })

  it('routes silicon (contains rect)', () => {
    const html = render(<SectorIllustration sector="silicon" />)
    expect(html).toMatch(/<rect\b/)
  })

  it('routes firmware (contains rect + circle)', () => {
    const html = render(<SectorIllustration sector="firmware" />)
    expect(html).toMatch(/<rect\b/)
    expect(html).toMatch(/<circle\b/)
  })

  it('routes plc (contains line + circle)', () => {
    const html = render(<SectorIllustration sector="plc" />)
    expect(html).toMatch(/<line\b/)
    expect(html).toMatch(/<circle\b/)
  })

  it('routes composites (contains line)', () => {
    const html = render(<SectorIllustration sector="composites" />)
    expect(html).toMatch(/<line\b/)
  })

  it('routes dental (contains path)', () => {
    const html = render(<SectorIllustration sector="dental" />)
    expect(html).toMatch(/<path\b/)
  })

  it('routes optics (contains path + line)', () => {
    const html = render(<SectorIllustration sector="optics" />)
    expect(html).toMatch(/<path\b/)
    expect(html).toMatch(/<line\b/)
  })

  it('routes horology (contains circle + polygon)', () => {
    const html = render(<SectorIllustration sector="horology" />)
    expect(html).toMatch(/<circle\b/)
    expect(html).toMatch(/<polygon\b/)
  })

  it('routes marine (contains path)', () => {
    const html = render(<SectorIllustration sector="marine" />)
    expect(html).toMatch(/<path\b/)
  })

  it('routes woodworking (contains polygon)', () => {
    const html = render(<SectorIllustration sector="woodworking" />)
    expect(html).toMatch(/<polygon\b/)
  })

  it('routes textiles (contains line)', () => {
    const html = render(<SectorIllustration sector="textiles" />)
    expect(html).toMatch(/<line\b/)
  })

  it('routes civil (contains line + polygon)', () => {
    const html = render(<SectorIllustration sector="civil" />)
    expect(html).toMatch(/<line\b/)
    expect(html).toMatch(/<polygon\b/)
  })

  it('renders a fallback SVG for unknown sector', () => {
    const html = render(<SectorIllustration sector="unknown-sector-xyz" />)
    expect(html).toMatch(/<svg\b/)
    expect(html).toMatch(/data-fallback="true"/)
  })

  it('forwards size prop (default 120)', () => {
    const html = render(<SectorIllustration sector="mechanical" />)
    expect(html).toMatch(/width="120"/)
    expect(html).toMatch(/height="120"/)
  })

  it('forwards custom size prop', () => {
    const html = render(<SectorIllustration sector="mechanical" size={80} />)
    expect(html).toMatch(/width="80"/)
    expect(html).toMatch(/height="80"/)
  })

  it('all illustrations preserve viewBox="0 0 120 120"', () => {
    for (const { key } of SECTOR_ILLUSTRATIONS) {
      const html = render(<SectorIllustration sector={key} />)
      expect(html).toMatch(/viewBox="0 0 120 120"/)
    }
  })
})

// ── 3. Individual illustration smoke tests ────────────────────────────────────

const ALL_ILLUSTRATIONS = [
  ['MechanicalIllustration', MechanicalIllustration],
  ['ElectronicsIllustration', ElectronicsIllustration],
  ['ArchitectureIllustration', ArchitectureIllustration],
  ['JewelryIllustration', JewelryIllustration],
  ['AutomotiveIllustration', AutomotiveIllustration],
  ['AerospaceIllustration', AerospaceIllustration],
  ['SiliconIllustration', SiliconIllustration],
  ['FirmwareIllustration', FirmwareIllustration],
  ['PLCIllustration', PLCIllustration],
  ['CompositesIllustration', CompositesIllustration],
  ['DentalIllustration', DentalIllustration],
  ['OpticsIllustration', OpticsIllustration],
  ['HorologyIllustration', HorologyIllustration],
  ['MarineIllustration', MarineIllustration],
  ['WoodworkingIllustration', WoodworkingIllustration],
  ['TextilesIllustration', TextilesIllustration],
  ['CivilIllustration', CivilIllustration],
]

describe('individual illustrations', () => {
  it('exports exactly 17 named illustration components', () => {
    expect(ALL_ILLUSTRATIONS).toHaveLength(17)
  })

  for (const [name, Component] of ALL_ILLUSTRATIONS) {
    it(`${name} renders without crashing`, () => {
      expect(() => render(<Component />)).not.toThrow()
    })

    it(`${name} produces an SVG element`, () => {
      const html = render(<Component />)
      expect(html).toMatch(/<svg\b/)
    })

    it(`${name} includes fill="none" (stroke-based)`, () => {
      const html = render(<Component />)
      expect(html).toMatch(/fill="none"/)
    })

    it(`${name} has aria-hidden="true"`, () => {
      const html = render(<Component />)
      expect(html).toMatch(/aria-hidden="true"/)
    })

    it(`${name} contains at least one SVG primitive (path|line|rect|circle|polygon|ellipse)`, () => {
      const html = render(<Component />)
      const count = countMatches(html, /<(path|line|rect|circle|polygon|ellipse)\b/g)
      expect(count).toBeGreaterThan(0)
    })

    it(`${name} applies size prop`, () => {
      const html = render(<Component size={64} />)
      expect(html).toMatch(/width="64"/)
      expect(html).toMatch(/height="64"/)
    })

    it(`${name} applies className prop`, () => {
      const html = render(<Component className="test-class" />)
      expect(html).toMatch(/test-class/)
    })
  }
})
