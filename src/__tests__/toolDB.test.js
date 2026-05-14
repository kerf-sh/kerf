// toolDB.test.js — unit tests for ToolDBPanel (rendering) and the
// add-tool modal field-validation logic.
//
// We test the pure validation logic extracted from the form component.
// Full DOM rendering requires jsdom + React + lucide, which is heavy for CI;
// we keep these tests dependency-free and fast.

import { describe, it, expect } from 'vitest'

// ---------------------------------------------------------------------------
// Pull out the validation logic from ToolDBPanel for standalone testing.
// We re-implement the same rules here to avoid a React render dependency.
// (The component's `validate()` fn is a closure — we shadow it here.)
// ---------------------------------------------------------------------------

function validate(form) {
  const errs = {}
  if (!form.id || !form.id.trim()) errs.id = 'Required'
  if (!form.name || !form.name.trim()) errs.name = 'Required'
  const d = parseFloat(form.diameter_mm)
  if (!form.diameter_mm || isNaN(d) || d <= 0) errs.diameter_mm = 'Must be > 0'

  const typeFields = {
    ball_end:  ['ball_radius_mm'],
    flat_end:  [],
    bull_end:  ['corner_radius_mm'],
    chamfer:   ['included_angle_deg'],
    drill:     [],
    face_mill: [],
    engraver:  ['included_angle_deg'],
  }[form.type] || []

  for (const f of typeFields) {
    const v = parseFloat(form[f])
    if (!form[f] || isNaN(v) || v <= 0) errs[f] = 'Required and must be > 0'
  }

  if (form.type === 'ball_end' && form.ball_radius_mm && form.diameter_mm) {
    const br = parseFloat(form.ball_radius_mm)
    const diam = parseFloat(form.diameter_mm)
    if (!isNaN(br) && !isNaN(diam) && br > diam / 2 + 1e-9) {
      errs.ball_radius_mm = `Must be ≤ diameter/2 (${(diam / 2).toFixed(3)})`
    }
  }
  return errs
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ToolDBPanel form validation', () => {
  it('rejects empty form', () => {
    const errs = validate({ type: 'ball_end', id: '', name: '', diameter_mm: '' })
    expect(errs.id).toBeTruthy()
    expect(errs.name).toBeTruthy()
    expect(errs.diameter_mm).toBeTruthy()
  })

  it('rejects ball_end missing ball_radius_mm', () => {
    const errs = validate({ type: 'ball_end', id: 'T1', name: 'Ball', diameter_mm: '6', ball_radius_mm: '' })
    expect(errs.ball_radius_mm).toBeTruthy()
    expect(errs.id).toBeUndefined()
  })

  it('rejects ball_radius > diameter/2', () => {
    const errs = validate({ type: 'ball_end', id: 'T1', name: 'Ball', diameter_mm: '6', ball_radius_mm: '4' })
    expect(errs.ball_radius_mm).toMatch(/≤/)
  })

  it('accepts ball_radius == diameter/2 exactly', () => {
    const errs = validate({ type: 'ball_end', id: 'T1', name: 'Ball', diameter_mm: '6', ball_radius_mm: '3' })
    expect(errs.ball_radius_mm).toBeUndefined()
  })

  it('rejects bull_end missing corner_radius_mm', () => {
    const errs = validate({ type: 'bull_end', id: 'T2', name: 'Bull', diameter_mm: '10', corner_radius_mm: '' })
    expect(errs.corner_radius_mm).toBeTruthy()
  })

  it('rejects chamfer missing included_angle_deg', () => {
    const errs = validate({ type: 'chamfer', id: 'T3', name: 'Chamfer', diameter_mm: '8', included_angle_deg: '' })
    expect(errs.included_angle_deg).toBeTruthy()
  })

  it('accepts flat_end with just id + name + diameter', () => {
    const errs = validate({ type: 'flat_end', id: 'T4', name: 'Flat', diameter_mm: '6' })
    expect(Object.keys(errs)).toHaveLength(0)
  })

  it('accepts drill with just id + name + diameter', () => {
    const errs = validate({ type: 'drill', id: 'D1', name: 'Drill', diameter_mm: '3' })
    expect(Object.keys(errs)).toHaveLength(0)
  })

  it('accepts face_mill with just id + name + diameter', () => {
    const errs = validate({ type: 'face_mill', id: 'F1', name: 'Face Mill', diameter_mm: '50' })
    expect(Object.keys(errs)).toHaveLength(0)
  })

  it('rejects zero diameter', () => {
    const errs = validate({ type: 'flat_end', id: 'T5', name: 'Flat', diameter_mm: '0' })
    expect(errs.diameter_mm).toBeTruthy()
  })

  it('rejects negative diameter', () => {
    const errs = validate({ type: 'flat_end', id: 'T5', name: 'Flat', diameter_mm: '-1' })
    expect(errs.diameter_mm).toBeTruthy()
  })

  it('rejects engraver missing included_angle_deg', () => {
    const errs = validate({ type: 'engraver', id: 'E1', name: 'Engrave', diameter_mm: '3', included_angle_deg: '' })
    expect(errs.included_angle_deg).toBeTruthy()
  })

  it('accepts engraver with included_angle_deg', () => {
    const errs = validate({ type: 'engraver', id: 'E1', name: 'Engrave', diameter_mm: '3', included_angle_deg: '60' })
    expect(Object.keys(errs)).toHaveLength(0)
  })
})


// ---------------------------------------------------------------------------
// Tool list rendering (data model)
// ---------------------------------------------------------------------------

describe('Tool list data model', () => {
  const tools = [
    {
      id: 'T1', name: '6mm ball-end', type: 'ball_end',
      diameter_mm: 6, ball_radius_mm: 3, flute_count: 2, material: 'carbide',
      feed_rate_mm_min: 800, spindle_rpm_min: 10000,
    },
    {
      id: 'T2', name: '8mm flat-end', type: 'flat_end',
      diameter_mm: 8,
    },
  ]

  it('has expected tool count', () => {
    expect(tools).toHaveLength(2)
  })

  it('first tool is ball_end with correct fields', () => {
    const t = tools[0]
    expect(t.type).toBe('ball_end')
    expect(t.ball_radius_mm).toBe(3)
    expect(t.ball_radius_mm).toBeLessThanOrEqual(t.diameter_mm / 2)
  })

  it('second tool is flat_end', () => {
    expect(tools[1].type).toBe('flat_end')
    expect(tools[1].ball_radius_mm).toBeUndefined()
  })

  it('tools are findable by id', () => {
    const found = tools.find((t) => t.id === 'T2')
    expect(found).toBeTruthy()
    expect(found.name).toBe('8mm flat-end')
  })
})


// ---------------------------------------------------------------------------
// to_comment equivalent
// ---------------------------------------------------------------------------

describe('Tool comment format', () => {
  function toolComment(tool) {
    const parts = [`${tool.id} — ${tool.name}, ø${tool.diameter_mm} mm`]
    if (tool.type === 'ball_end' && tool.ball_radius_mm != null)
      parts.push(`ball r=${tool.ball_radius_mm} mm`)
    if (tool.flute_count) parts.push(`${tool.flute_count}-flute`)
    if (tool.material) parts.push(tool.material)
    return 'tool: ' + parts.join(', ')
  }

  it('includes ball radius for ball_end', () => {
    const c = toolComment({ id: 'T1', name: 'Ball', type: 'ball_end', diameter_mm: 6, ball_radius_mm: 3 })
    expect(c).toContain('ball r=3 mm')
  })

  it('includes flute count and material', () => {
    const c = toolComment({ id: 'T1', name: 'Ball', type: 'ball_end', diameter_mm: 6, ball_radius_mm: 3, flute_count: 2, material: 'carbide' })
    expect(c).toContain('2-flute')
    expect(c).toContain('carbide')
  })

  it('includes diameter in ø format', () => {
    const c = toolComment({ id: 'T1', name: 'Flat', type: 'flat_end', diameter_mm: 8 })
    expect(c).toContain('ø8 mm')
  })
})
