// sectorCommandIndex.test.js — Vitest suite for sectorCommandIndex.js
//
// Coverage goals:
//   1. Index shape & completeness (25+ entries, required fields)
//   2. fuzzyMatch basic behaviour
//   3. Ranking: "vhdl" hits "New VHDL file" first
//   4. Keyword matching: "arduino" hits firmware entries
//   5. Multi-token queries, partial matches, no-match, empty query
//   6. commandsBySector and sectors() helpers

import { describe, it, expect } from 'vitest'
import {
  SECTOR_COMMANDS,
  fuzzyMatch,
  commandsBySector,
  sectors,
} from './sectorCommandIndex.js'

// ---------------------------------------------------------------------------
// 1. Index shape & completeness
// ---------------------------------------------------------------------------

describe('SECTOR_COMMANDS index', () => {
  it('has at least 25 entries', () => {
    expect(SECTOR_COMMANDS.length).toBeGreaterThanOrEqual(25)
  })

  it('every entry has a unique id', () => {
    const ids = SECTOR_COMMANDS.map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('every entry has required fields: id, label, description, keywords, action_type, target, sector', () => {
    const required = ['id', 'label', 'description', 'keywords', 'action_type', 'target', 'sector']
    for (const entry of SECTOR_COMMANDS) {
      for (const field of required) {
        expect(entry, `entry ${entry.id} missing ${field}`).toHaveProperty(field)
      }
    }
  })

  it('action_type is always one of: route | create_file | open_docs', () => {
    const valid = new Set(['route', 'create_file', 'open_docs'])
    for (const entry of SECTOR_COMMANDS) {
      expect(valid.has(entry.action_type), `${entry.id} has invalid action_type "${entry.action_type}"`).toBe(true)
    }
  })

  it('keywords is a non-empty array on every entry', () => {
    for (const entry of SECTOR_COMMANDS) {
      expect(Array.isArray(entry.keywords), `${entry.id}: keywords not an array`).toBe(true)
      expect(entry.keywords.length, `${entry.id}: keywords is empty`).toBeGreaterThan(0)
    }
  })

  it('covers all five sectors: silicon, firmware, aerospace, plc, atopile', () => {
    const present = new Set(SECTOR_COMMANDS.map((e) => e.sector))
    for (const s of ['silicon', 'firmware', 'aerospace', 'plc', 'atopile']) {
      expect(present.has(s), `missing sector ${s}`).toBe(true)
    }
  })

  it('silicon sector has at least 5 entries', () => {
    expect(commandsBySector('silicon').length).toBeGreaterThanOrEqual(5)
  })

  it('firmware sector has at least 5 entries', () => {
    expect(commandsBySector('firmware').length).toBeGreaterThanOrEqual(5)
  })

  it('aerospace sector has at least 4 entries', () => {
    expect(commandsBySector('aerospace').length).toBeGreaterThanOrEqual(4)
  })

  it('plc sector has at least 4 entries', () => {
    expect(commandsBySector('plc').length).toBeGreaterThanOrEqual(4)
  })

  it('atopile sector has at least 3 entries', () => {
    expect(commandsBySector('atopile').length).toBeGreaterThanOrEqual(3)
  })
})

// ---------------------------------------------------------------------------
// 2. fuzzyMatch — basic behaviour
// ---------------------------------------------------------------------------

describe('fuzzyMatch — basic behaviour', () => {
  it('returns an empty array for an empty query', () => {
    expect(fuzzyMatch('')).toEqual([])
    expect(fuzzyMatch('   ')).toEqual([])
  })

  it('returns an empty array when nothing matches', () => {
    const results = fuzzyMatch('xyzzy_nonexistent_zzz')
    expect(results).toEqual([])
  })

  it('returns entries enriched with a numeric score field', () => {
    const results = fuzzyMatch('vhdl')
    expect(results.length).toBeGreaterThan(0)
    for (const r of results) {
      expect(typeof r.score).toBe('number')
      expect(r.score).toBeGreaterThan(0)
    }
  })

  it('results are sorted descending by score (best first)', () => {
    const results = fuzzyMatch('new')
    expect(results.length).toBeGreaterThan(1)
    for (let i = 0; i < results.length - 1; i++) {
      expect(results[i].score).toBeGreaterThanOrEqual(results[i + 1].score)
    }
  })

  it('does not mutate the original SECTOR_COMMANDS entries', () => {
    const before = SECTOR_COMMANDS.map((e) => ({ ...e }))
    fuzzyMatch('vhdl')
    for (let i = 0; i < SECTOR_COMMANDS.length; i++) {
      expect(SECTOR_COMMANDS[i]).not.toHaveProperty('score')
      expect(SECTOR_COMMANDS[i].id).toBe(before[i].id)
    }
  })
})

// ---------------------------------------------------------------------------
// 3. Ranking: "vhdl" matches "New VHDL file" first
// ---------------------------------------------------------------------------

describe('fuzzyMatch — ranking: vhdl', () => {
  it('"vhdl" returns at least one result', () => {
    const results = fuzzyMatch('vhdl')
    expect(results.length).toBeGreaterThan(0)
  })

  it('"vhdl" returns "New VHDL file" as the top result', () => {
    const results = fuzzyMatch('vhdl')
    expect(results[0].id).toBe('silicon-new-vhdl')
  })

  it('"vhdl" top result has a higher score than any non-VHDL result', () => {
    const results = fuzzyMatch('vhdl')
    const top = results[0]
    const others = results.filter((r) => r.id !== 'silicon-new-vhdl')
    for (const other of others) {
      expect(top.score).toBeGreaterThanOrEqual(other.score)
    }
  })

  it('"VHDL" (uppercase) also returns "New VHDL file" first (case-insensitive)', () => {
    const results = fuzzyMatch('VHDL')
    expect(results[0].id).toBe('silicon-new-vhdl')
  })
})

// ---------------------------------------------------------------------------
// 4. Keyword matching: "arduino" hits firmware entries
// ---------------------------------------------------------------------------

describe('fuzzyMatch — keyword matching: arduino', () => {
  it('"arduino" returns at least one result', () => {
    const results = fuzzyMatch('arduino')
    expect(results.length).toBeGreaterThan(0)
  })

  it('"arduino" top result is the Arduino sketch entry', () => {
    const results = fuzzyMatch('arduino')
    expect(results[0].id).toBe('firmware-new-arduino')
  })

  it('"arduino" results are all from the firmware sector', () => {
    const results = fuzzyMatch('arduino')
    for (const r of results) {
      expect(r.sector).toBe('firmware')
    }
  })

  it('"Arduino" (mixed case) also returns the sketch entry first', () => {
    const results = fuzzyMatch('Arduino')
    expect(results[0].id).toBe('firmware-new-arduino')
  })
})

// ---------------------------------------------------------------------------
// 5. Multi-token queries, partial matches, sector queries
// ---------------------------------------------------------------------------

describe('fuzzyMatch — multi-token queries', () => {
  it('"new vhdl" returns the VHDL file entry first', () => {
    const results = fuzzyMatch('new vhdl')
    expect(results[0].id).toBe('silicon-new-vhdl')
  })

  it('"new verilog" returns the Verilog file entry first', () => {
    const results = fuzzyMatch('new verilog')
    expect(results[0].id).toBe('silicon-new-verilog')
  })

  it('"spice deck" returns the SPICE deck entry', () => {
    const results = fuzzyMatch('spice deck')
    expect(results.length).toBeGreaterThan(0)
    expect(results[0].id).toBe('silicon-new-spice')
  })

  it('"serial monitor" returns the serial monitor firmware entry', () => {
    const results = fuzzyMatch('serial monitor')
    expect(results[0].id).toBe('firmware-serial-monitor')
  })

  it('"orbital transfer" returns the orbital transfer aerospace entry', () => {
    const results = fuzzyMatch('orbital transfer')
    expect(results[0].id).toBe('aerospace-orbital')
  })

  it('"ladder program" returns the ladder PLC entry first', () => {
    const results = fuzzyMatch('ladder program')
    expect(results[0].id).toBe('plc-new-ladder')
  })

  it('"ato file" returns the new .ato atopile entry first', () => {
    const results = fuzzyMatch('ato file')
    expect(results[0].id).toBe('atopile-new-ato')
  })
})

describe('fuzzyMatch — partial / prefix matches', () => {
  it('"sky130" returns the SKY130 PDK layers entry', () => {
    const results = fuzzyMatch('sky130')
    expect(results.length).toBeGreaterThan(0)
    expect(results[0].id).toBe('silicon-sky130-layers')
  })

  it('"flutter" returns the flutter aerospace entry', () => {
    const results = fuzzyMatch('flutter')
    expect(results[0].id).toBe('aerospace-flutter')
  })

  it('"vlm" returns the VLM aerospace entry', () => {
    const results = fuzzyMatch('vlm')
    expect(results[0].id).toBe('aerospace-vlm')
  })

  it('"hmi" returns the HMI tester PLC entry', () => {
    const results = fuzzyMatch('hmi')
    expect(results[0].id).toBe('plc-hmi-tester')
  })

  it('"compile" returns atopile compile entry in results', () => {
    const results = fuzzyMatch('compile')
    const ids = results.map((r) => r.id)
    expect(ids).toContain('atopile-compile')
  })
})

describe('fuzzyMatch — sector-level queries', () => {
  it('"silicon" returns only silicon-sector entries', () => {
    const results = fuzzyMatch('silicon')
    expect(results.length).toBeGreaterThan(0)
    for (const r of results) {
      expect(r.sector).toBe('silicon')
    }
  })

  it('"firmware" returns firmware-sector entries', () => {
    const results = fuzzyMatch('firmware')
    expect(results.length).toBeGreaterThan(0)
    const sects = new Set(results.map((r) => r.sector))
    expect(sects.has('firmware')).toBe(true)
  })

  it('"plc" returns PLC-sector entries', () => {
    const results = fuzzyMatch('plc')
    expect(results.length).toBeGreaterThan(0)
    for (const r of results) {
      expect(r.sector).toBe('plc')
    }
  })
})

// ---------------------------------------------------------------------------
// 6. commandsBySector and sectors() helpers
// ---------------------------------------------------------------------------

describe('commandsBySector', () => {
  it('returns only entries for the given sector', () => {
    for (const s of ['silicon', 'firmware', 'aerospace', 'plc', 'atopile']) {
      const results = commandsBySector(s)
      expect(results.every((e) => e.sector === s)).toBe(true)
    }
  })

  it('returns an empty array for an unknown sector', () => {
    expect(commandsBySector('unknown_sector_xyz')).toEqual([])
  })

  it('respects a custom entries array', () => {
    const custom = [
      { id: 'x', sector: 'custom', label: 'X', description: '', keywords: [], action_type: 'route', target: '/' },
      { id: 'y', sector: 'silicon', label: 'Y', description: '', keywords: [], action_type: 'route', target: '/' },
    ]
    expect(commandsBySector('custom', custom)).toHaveLength(1)
    expect(commandsBySector('custom', custom)[0].id).toBe('x')
  })
})

describe('sectors', () => {
  it('returns all five sector slugs', () => {
    const s = sectors()
    expect(s).toContain('silicon')
    expect(s).toContain('firmware')
    expect(s).toContain('aerospace')
    expect(s).toContain('plc')
    expect(s).toContain('atopile')
  })

  it('returns unique values only', () => {
    const s = sectors()
    expect(new Set(s).size).toBe(s.length)
  })

  it('respects a custom entries array', () => {
    const custom = [
      { id: 'a', sector: 'alpha', label: 'A', description: '', keywords: [], action_type: 'route', target: '/' },
      { id: 'b', sector: 'beta', label: 'B', description: '', keywords: [], action_type: 'route', target: '/' },
      { id: 'c', sector: 'alpha', label: 'C', description: '', keywords: [], action_type: 'route', target: '/' },
    ]
    const s = sectors(custom)
    expect(s).toEqual(['alpha', 'beta'])
  })
})
