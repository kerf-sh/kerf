/**
 * iesLoader.test.js — Vitest suite for the IES LM-63 parser and sampler.
 *
 * No DOM or fetch is required: parseIES, iesPolarSample, and polarPlot2D are
 * all pure functions. loadIES (fetch-based) is tested with a vi.stubGlobal
 * fetch stub.
 */

import { describe, it, expect, vi, afterEach } from 'vitest'
import { parseIES, iesPolarSample, polarPlot2D, loadIES } from './iesLoader.js'
import { IES_PRESETS } from './iesPresets.js'
import { existsSync } from 'fs'
import { join } from 'path'

// ── Synthetic IES fixture strings ─────────────────────────────────────────────

// Minimal symmetric downlight — mirrors public/ies/downlight-a.ies
const DOWNLIGHT_A_IES = `IESNA:LM-63-1991
[TEST] Synthetic fixture - downlight type A
[MANUFAC] Kerf Synthetic
[LUMCAT] DOWNLIGHT-A
[LUMINAIRE] Recessed downlight, symmetric, 1000lm
[LAMP] 1 generic LED
TILT=NONE
1 1000.0 1.0 13 1 1 1 0.15 0.15 0.0
1.0
0.0 10.0 20.0 30.0 40.0 50.0 60.0 70.0 80.0 90.0 100.0 110.0 120.0
0.0
850.0 830.0 790.0 720.0 620.0 490.0 340.0 200.0 80.0 10.0 0.0 0.0 0.0
`

// Asymmetric wall-wash with 3 horizontal planes
const WALLWASH_A_IES = `IESNA:LM-63-1991
[TEST] Synthetic fixture - wall wash type A
[MANUFAC] Kerf Synthetic
[LUMCAT] WALLWASH-A
[LUMINAIRE] Wall wash fixture, asymmetric, 600lm
[LAMP] 1 generic LED
TILT=NONE
1 600.0 1.0 10 3 1 1 0.10 0.20 0.0
1.0
0.0 15.0 30.0 45.0 60.0 75.0 90.0 105.0 120.0 135.0
0.0 90.0 180.0
550.0 520.0 460.0 370.0 260.0 150.0 60.0 20.0 5.0 0.0
300.0 280.0 240.0 190.0 130.0 70.0 30.0 10.0 2.0 0.0
80.0 70.0 60.0 45.0 30.0 15.0 5.0 2.0 0.0 0.0
`

// Batwing fixture — peak is off-axis
const BATWING_IES = `IESNA:LM-63-1991
[TEST] Synthetic fixture - batwing flood
[MANUFAC] Kerf Synthetic
[LUMCAT] FLOOD-BATWING
[LUMINAIRE] Batwing distribution, 2000lm
[LAMP] 1 generic LED
TILT=NONE
1 2000.0 1.0 13 1 1 1 0.30 0.30 0.0
1.0
0.0 10.0 20.0 30.0 40.0 50.0 60.0 70.0 80.0 90.0 100.0 110.0 120.0
0.0
400.0 500.0 700.0 950.0 1200.0 1400.0 1500.0 1400.0 1100.0 700.0 300.0 80.0 10.0
`

// ── parseIES ──────────────────────────────────────────────────────────────────

describe('parseIES', () => {
  it('returns required top-level keys', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    expect(profile).toHaveProperty('vertical_angles')
    expect(profile).toHaveProperty('horizontal_angles')
    expect(profile).toHaveProperty('candela_grid')
    expect(profile).toHaveProperty('lumens')
    expect(profile).toHaveProperty('width')
    expect(profile).toHaveProperty('length')
    expect(profile).toHaveProperty('height')
  })

  it('parses the correct number of vertical angles', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    expect(profile.vertical_angles).toHaveLength(13)
  })

  it('parses vertical angles correctly', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    expect(profile.vertical_angles[0]).toBe(0)
    expect(profile.vertical_angles[12]).toBe(120)
  })

  it('parses the correct number of horizontal angles for a symmetric profile', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    expect(profile.horizontal_angles).toHaveLength(1)
    expect(profile.horizontal_angles[0]).toBe(0)
  })

  it('parses 3 horizontal planes for an asymmetric wall-wash', () => {
    const profile = parseIES(WALLWASH_A_IES)
    expect(profile.horizontal_angles).toHaveLength(3)
    expect(profile.horizontal_angles).toEqual([0, 90, 180])
  })

  it('candela_grid has the correct shape (numHoriz × numVert)', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    expect(profile.candela_grid).toHaveLength(1)
    expect(profile.candela_grid[0]).toHaveLength(13)
  })

  it('reads on-axis candela value at theta=0', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    // downlight-a: first candela value is 850.0, multiplier=1.0
    expect(profile.candela_grid[0][0]).toBe(850.0)
  })

  it('reads lumens from the lamp descriptor line', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    expect(profile.lumens).toBe(1000.0)
  })

  it('reads luminaire dimensions from the lamp descriptor line', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    expect(profile.width).toBeCloseTo(0.15)
    expect(profile.length).toBeCloseTo(0.15)
    expect(profile.height).toBeCloseTo(0.0)
  })

  it('applies the candela multiplier', () => {
    // Construct a fixture with multiplier=2.0
    const ies = DOWNLIGHT_A_IES.replace(
      '1 1000.0 1.0 13 1 1 1 0.15 0.15 0.0',
      '1 1000.0 2.0 13 1 1 1 0.15 0.15 0.0'
    )
    const profile = parseIES(ies)
    expect(profile.candela_grid[0][0]).toBe(1700.0) // 850 * 2
  })

  it('throws for empty string', () => {
    expect(() => parseIES('')).toThrow()
  })

  it('throws for non-string input', () => {
    expect(() => parseIES(null)).toThrow()
    expect(() => parseIES(42)).toThrow()
  })

  it('throws when TILT line is missing', () => {
    const noTilt = DOWNLIGHT_A_IES.replace(/^TILT=NONE\n/m, '')
    expect(() => parseIES(noTilt)).toThrow(/TILT/)
  })

  it('parses the batwing fixture correctly', () => {
    const profile = parseIES(BATWING_IES)
    expect(profile.vertical_angles).toHaveLength(13)
    expect(profile.candela_grid[0][0]).toBe(400.0)
  })

  it('parses the asymmetric wall-wash candela_grid correctly', () => {
    const profile = parseIES(WALLWASH_A_IES)
    expect(profile.candela_grid[0][0]).toBe(550.0) // phi=0, theta=0
    expect(profile.candela_grid[1][0]).toBe(300.0) // phi=90, theta=0
    expect(profile.candela_grid[2][0]).toBe(80.0)  // phi=180, theta=0
  })
})

// ── iesPolarSample ────────────────────────────────────────────────────────────

describe('iesPolarSample', () => {
  it('returns on-axis candela at (0, 0) for a symmetric downlight', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    // On-axis at theta=0, phi=0 → first candela value: 850.0
    expect(iesPolarSample(profile, 0, 0)).toBeCloseTo(850.0)
  })

  it('returns on-axis candela at phi=180 for symmetric profile (single horizontal plane)', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    // Symmetric: phi doesn't matter
    expect(iesPolarSample(profile, 0, 180)).toBeCloseTo(850.0)
  })

  it('interpolates correctly between two defined vertical angles', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    // theta=5 is halfway between 0 (850) and 10 (830)
    const expected = (850.0 + 830.0) / 2
    expect(iesPolarSample(profile, 5, 0)).toBeCloseTo(expected)
  })

  it('clamps to last value beyond the defined vertical range', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    // Last defined angle is 120 with value 0.0
    expect(iesPolarSample(profile, 150, 0)).toBeCloseTo(0.0)
  })

  it('clamps to first value below zero degrees', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    expect(iesPolarSample(profile, -5, 0)).toBeCloseTo(850.0)
  })

  it('handles asymmetric wall-wash at phi=0', () => {
    const profile = parseIES(WALLWASH_A_IES)
    expect(iesPolarSample(profile, 0, 0)).toBeCloseTo(550.0)
  })

  it('handles asymmetric wall-wash at phi=90', () => {
    const profile = parseIES(WALLWASH_A_IES)
    expect(iesPolarSample(profile, 0, 90)).toBeCloseTo(300.0)
  })

  it('handles asymmetric wall-wash at phi=180', () => {
    const profile = parseIES(WALLWASH_A_IES)
    expect(iesPolarSample(profile, 0, 180)).toBeCloseTo(80.0)
  })

  it('interpolates phi correctly between defined planes', () => {
    const profile = parseIES(WALLWASH_A_IES)
    // phi=45 is halfway between phi=0 (550) and phi=90 (300) at theta=0
    const expected = (550.0 + 300.0) / 2
    expect(iesPolarSample(profile, 0, 45)).toBeCloseTo(expected)
  })

  it('applies phi folding for half-symmetry (phi > 180 maps to 360-phi)', () => {
    const profile = parseIES(WALLWASH_A_IES)
    // phi=270 should fold to phi=90 for half-plane symmetric data
    expect(iesPolarSample(profile, 0, 270)).toBeCloseTo(iesPolarSample(profile, 0, 90))
  })

  it('throws for invalid profile', () => {
    expect(() => iesPolarSample(null, 0, 0)).toThrow()
    expect(() => iesPolarSample({}, 0, 0)).toThrow()
  })

  it('batwing: off-axis value at 60° is higher than on-axis value at 0°', () => {
    const profile = parseIES(BATWING_IES)
    const onAxis = iesPolarSample(profile, 0, 0)
    const offAxis = iesPolarSample(profile, 60, 0)
    expect(offAxis).toBeGreaterThan(onAxis)
  })
})

// ── polarPlot2D ───────────────────────────────────────────────────────────────

describe('polarPlot2D', () => {
  it('returns an array of objects with theta_deg and candela', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    const plot = polarPlot2D(profile)
    expect(Array.isArray(plot)).toBe(true)
    expect(plot.length).toBeGreaterThan(0)
    for (const pt of plot) {
      expect(pt).toHaveProperty('theta_deg')
      expect(pt).toHaveProperty('candela')
    }
  })

  it('first point at theta_deg=0 matches on-axis candela', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    const plot = polarPlot2D(profile)
    expect(plot[0].theta_deg).toBe(0)
    expect(plot[0].candela).toBeCloseTo(850.0)
  })

  it('default angleStep=5 produces the right number of points', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    // maxTheta = 120; points at 0, 5, 10, ..., 120 → 25 points
    const plot = polarPlot2D(profile)
    expect(plot).toHaveLength(25)
  })

  it('respects a custom angleStep', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    const plot = polarPlot2D(profile, 10)
    // 0, 10, 20, ..., 120 → 13 points
    expect(plot).toHaveLength(13)
  })

  it('all theta_deg values are within the defined range', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    const plot = polarPlot2D(profile)
    for (const pt of plot) {
      expect(pt.theta_deg).toBeGreaterThanOrEqual(0)
      expect(pt.theta_deg).toBeLessThanOrEqual(120)
    }
  })

  it('all candela values are non-negative numbers', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    const plot = polarPlot2D(profile)
    for (const pt of plot) {
      expect(typeof pt.candela).toBe('number')
      expect(pt.candela).toBeGreaterThanOrEqual(0)
    }
  })

  it('batwing: peak candela is not at theta=0', () => {
    const profile = parseIES(BATWING_IES)
    const plot = polarPlot2D(profile, 5)
    const maxPt = plot.reduce((best, pt) => (pt.candela > best.candela ? pt : best), plot[0])
    expect(maxPt.theta_deg).toBeGreaterThan(0)
  })

  it('throws for invalid profile', () => {
    expect(() => polarPlot2D(null)).toThrow()
    expect(() => polarPlot2D({})).toThrow()
  })

  it('throws for non-positive angleStep', () => {
    const profile = parseIES(DOWNLIGHT_A_IES)
    expect(() => polarPlot2D(profile, 0)).toThrow()
    expect(() => polarPlot2D(profile, -1)).toThrow()
  })
})

// ── IES_PRESETS ───────────────────────────────────────────────────────────────

describe('IES_PRESETS', () => {
  it('exports exactly 12 presets', () => {
    expect(IES_PRESETS).toHaveLength(12)
  })

  it('each preset has required fields', () => {
    for (const preset of IES_PRESETS) {
      expect(preset).toHaveProperty('slug')
      expect(preset).toHaveProperty('name')
      expect(preset).toHaveProperty('category')
      expect(preset).toHaveProperty('file_path')
      expect(preset).toHaveProperty('description')
    }
  })

  it('all slugs are unique', () => {
    const slugs = IES_PRESETS.map((p) => p.slug)
    expect(new Set(slugs).size).toBe(12)
  })

  it('all file_paths are unique', () => {
    const paths = IES_PRESETS.map((p) => p.file_path)
    expect(new Set(paths).size).toBe(12)
  })

  it('has exactly 3 downlight presets', () => {
    const dl = IES_PRESETS.filter((p) => p.category === 'downlight')
    expect(dl).toHaveLength(3)
  })

  it('has exactly 2 wall-wash presets', () => {
    const ww = IES_PRESETS.filter((p) => p.category === 'wall-wash')
    expect(ww).toHaveLength(2)
  })

  it('has exactly 2 spot presets', () => {
    const sp = IES_PRESETS.filter((p) => p.category === 'spot')
    expect(sp).toHaveLength(2)
  })

  it('has exactly 2 flood presets', () => {
    const fl = IES_PRESETS.filter((p) => p.category === 'flood')
    expect(fl).toHaveLength(2)
  })

  it('has exactly 3 specialty presets', () => {
    const sp = IES_PRESETS.filter((p) => p.category === 'specialty')
    expect(sp).toHaveLength(3)
  })

  it('all file_path strings start with /ies/', () => {
    for (const preset of IES_PRESETS) {
      expect(preset.file_path).toMatch(/^\/ies\//)
    }
  })

  it('all file_path strings end with .ies', () => {
    for (const preset of IES_PRESETS) {
      expect(preset.file_path).toMatch(/\.ies$/)
    }
  })

  it('all referenced .ies files exist in public/ies/', () => {
    // Resolve public/ relative to this file: src/lib/ → ../../public/
    for (const preset of IES_PRESETS) {
      // file_path is "/ies/xxx.ies" → public/ies/xxx.ies
      const relativePath = preset.file_path.replace(/^\//, '')
      const absolutePath = join(process.cwd(), 'public', relativePath.replace(/^ies\//, 'ies/'))
      expect(
        existsSync(absolutePath),
        `Missing fixture file for preset "${preset.slug}": ${absolutePath}`
      ).toBe(true)
    }
  })

  it('all fields are non-empty strings', () => {
    for (const preset of IES_PRESETS) {
      expect(typeof preset.slug).toBe('string')
      expect(preset.slug.length).toBeGreaterThan(0)
      expect(typeof preset.name).toBe('string')
      expect(preset.name.length).toBeGreaterThan(0)
      expect(typeof preset.category).toBe('string')
      expect(preset.category.length).toBeGreaterThan(0)
      expect(typeof preset.file_path).toBe('string')
      expect(preset.file_path.length).toBeGreaterThan(0)
      expect(typeof preset.description).toBe('string')
      expect(preset.description.length).toBeGreaterThan(0)
    }
  })
})

// ── loadIES ───────────────────────────────────────────────────────────────────

describe('loadIES', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches a URL and returns a parsed profile', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: async () => DOWNLIGHT_A_IES,
    }))
    const profile = await loadIES('/ies/downlight-a.ies')
    expect(profile).toHaveProperty('vertical_angles')
    expect(profile.lumens).toBe(1000.0)
  })

  it('passes the path to fetch', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => DOWNLIGHT_A_IES,
    })
    vi.stubGlobal('fetch', mockFetch)
    await loadIES('/ies/downlight-a.ies')
    expect(mockFetch).toHaveBeenCalledWith('/ies/downlight-a.ies')
  })

  it('throws when fetch returns a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: async () => 'Not found',
    }))
    await expect(loadIES('/ies/missing.ies')).rejects.toThrow('404')
  })

  it('throws for empty path', async () => {
    await expect(loadIES('')).rejects.toThrow()
  })

  it('throws for non-string path', async () => {
    await expect(loadIES(null)).rejects.toThrow()
  })
})
