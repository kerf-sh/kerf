// circuitTSX.test.js — coverage for the source-edit helpers used to
// round-trip drag/rotate edits in the Schematic + PCB views.
//
// These functions are pure (string in, string out) so we can exercise
// every branch without a JSX parser or a tscircuit runtime.

import { describe, it, expect } from 'vitest'
import {
  setPositionAttr,
  setRotationAttr,
  appendComponent,
  appendTrace,
  appendProbe,
  parseProbes,
  removeProbe,
  renameProbe,
  nextRefdes,
  snap,
} from '../lib/circuitTSX.js'

const SAMPLE = `import { Circuit } from "tscircuit"

export default () => (
  <board width="20mm" height="20mm">
    <resistor name="R1" resistance="1k" pcb_x={1} pcb_y={2} />
    <capacitor name="C1" capacitance="100nF" />
    <chip name="U1" footprint="dip8" pcb_x={5.25} pcb_y={-3.5} pcb_rotation={90} />
  </board>
)
`

describe('setPositionAttr', () => {
  it('replaces an existing pcb_x value', () => {
    const out = setPositionAttr(SAMPLE, 'R1', 'pcb_x', 4.5)
    expect(out).toContain('name="R1"')
    expect(out).toContain('pcb_x={4.5}')
    expect(out).not.toContain('pcb_x={1}')
    // pcb_y untouched
    expect(out).toContain('pcb_y={2}')
  })

  it('inserts pcb_x when missing', () => {
    const out = setPositionAttr(SAMPLE, 'C1', 'pcb_x', 7)
    expect(out).toMatch(/<capacitor name="C1"[^>]*pcb_x=\{7\}[^>]*\/>/)
  })

  it('inserts pcb_y when missing alongside an existing pcb_x', () => {
    const stage1 = setPositionAttr(SAMPLE, 'C1', 'pcb_x', 7)
    const stage2 = setPositionAttr(stage1, 'C1', 'pcb_y', 3)
    expect(stage2).toMatch(/<capacitor name="C1"[^>]*pcb_x=\{7\}[^>]*pcb_y=\{3\}[^>]*\/>/)
  })

  it('handles negative + decimal values', () => {
    const out = setPositionAttr(SAMPLE, 'U1', 'pcb_x', -12.75)
    expect(out).toContain('pcb_x={-12.75}')
    expect(out).toContain('pcb_y={-3.5}')
  })

  it('writes integers without a decimal point', () => {
    const out = setPositionAttr(SAMPLE, 'R1', 'pcb_y', 5)
    expect(out).toContain('pcb_y={5}')
    expect(out).not.toContain('pcb_y={5.0000}')
  })

  it('returns input unchanged when refdes is missing', () => {
    const out = setPositionAttr(SAMPLE, 'X99', 'pcb_x', 10)
    expect(out).toBe(SAMPLE)
  })

  it('returns input unchanged for an unknown axis', () => {
    const out = setPositionAttr(SAMPLE, 'R1', 'foo_x', 10)
    expect(out).toBe(SAMPLE)
  })

  it('returns input unchanged for non-finite values', () => {
    expect(setPositionAttr(SAMPLE, 'R1', 'pcb_x', NaN)).toBe(SAMPLE)
    expect(setPositionAttr(SAMPLE, 'R1', 'pcb_x', Infinity)).toBe(SAMPLE)
  })

  it('replaces a string-form attribute with the JSX-expression form', () => {
    const src = '<resistor name="R2" pcb_x="3.5" />'
    const out = setPositionAttr(src, 'R2', 'pcb_x', 8)
    expect(out).toContain('pcb_x={8}')
    expect(out).not.toContain('pcb_x="3.5"')
  })

  it('handles schematic_x / schematic_y', () => {
    const src = `<resistor name="R1" schematic_x={0} />`
    const out1 = setPositionAttr(src, 'R1', 'schematic_x', 1.2)
    expect(out1).toContain('schematic_x={1.2}')
    const out2 = setPositionAttr(out1, 'R1', 'schematic_y', -0.5)
    expect(out2).toContain('schematic_y={-0.5}')
  })

  it('does not match a refdes substring (R1 != R10)', () => {
    const src = `<resistor name="R10" pcb_x={1} />\n<resistor name="R1" pcb_x={2} />`
    const out = setPositionAttr(src, 'R1', 'pcb_x', 99)
    expect(out).toContain('name="R10" pcb_x={1}')
    expect(out).toContain('name="R1" pcb_x={99}')
  })
})

describe('setRotationAttr', () => {
  it('replaces an existing pcb_rotation', () => {
    const out = setRotationAttr(SAMPLE, 'U1', 'pcb_rotation', 180)
    expect(out).toContain('pcb_rotation={180}')
    expect(out).not.toContain('pcb_rotation={90}')
  })

  it('inserts schematic_rotation when missing', () => {
    const out = setRotationAttr(SAMPLE, 'R1', 'schematic_rotation', 270)
    expect(out).toContain('schematic_rotation={270}')
  })

  it('rejects unknown axes', () => {
    expect(setRotationAttr(SAMPLE, 'R1', 'pcb_x', 90)).toBe(SAMPLE)
  })
})

describe('appendComponent', () => {
  it('inserts a new element just before </board>', () => {
    const out = appendComponent(SAMPLE, '<chip name="U2" footprint="soic8" pcb_x={0} pcb_y={0} />')
    expect(out).toMatch(/U2[\s\S]*<\/board>/)
    // Ordering preserved — original components still present.
    expect(out).toContain('name="R1"')
    expect(out).toContain('name="U1"')
  })

  it('returns input unchanged when no <board> is present', () => {
    const src = '<resistor name="R1" />'
    expect(appendComponent(src, '<chip name="U2" />')).toBe(src)
  })

  it('returns input unchanged for an empty payload', () => {
    expect(appendComponent(SAMPLE, '')).toBe(SAMPLE)
  })
})

describe('nextRefdes', () => {
  it('returns R3 when R1 + R2 + R5 are present', () => {
    const src = `
      <resistor name="R1" />
      <resistor name="R2" />
      <resistor name="R5" />
    `
    expect(nextRefdes(src, 'R')).toBe('R3')
  })

  it('returns R1 for a source with no resistors', () => {
    expect(nextRefdes('<board></board>', 'R')).toBe('R1')
  })

  it('skips over the existing R1 in SAMPLE and returns R2', () => {
    expect(nextRefdes(SAMPLE, 'R')).toBe('R2')
  })

  it('does not collide across prefixes (C does not see R)', () => {
    const src = `<resistor name="R1" /><resistor name="R2" /><capacitor name="C7" />`
    expect(nextRefdes(src, 'C')).toBe('C1')
    expect(nextRefdes(src, 'U')).toBe('U1')
  })

  it('handles single-quoted name attributes', () => {
    const src = `<resistor name='R1' /><resistor name='R3' />`
    expect(nextRefdes(src, 'R')).toBe('R2')
  })

  it('treats refdes as literal — Q does not match QFN1', () => {
    // Common gotcha: a footprint label looks like a refdes prefix. We
    // guard via the `name="..."` anchor, so matching is unambiguous.
    const src = `<chip name="U1" footprint="QFN16" />`
    expect(nextRefdes(src, 'Q')).toBe('Q1')
  })

  it('returns <prefix>1 when input is empty/non-string', () => {
    expect(nextRefdes('', 'D')).toBe('D1')
    expect(nextRefdes(null, 'D')).toBe('D1')
  })
})

describe('appendTrace', () => {
  it('inserts a <trace> JSX element just before </board>', () => {
    const out = appendTrace(SAMPLE, '.R1 > .pin1', '.U1 > .pin3')
    expect(out).toContain('<trace from=".R1 > .pin1" to=".U1 > .pin3" />')
    // Trace lives inside the board.
    expect(out.indexOf('<trace')).toBeLessThan(out.indexOf('</board>'))
    // Original components untouched.
    expect(out).toContain('name="R1"')
    expect(out).toContain('name="U1"')
  })

  it('preserves indentation matching the </board> closer', () => {
    // </board> in SAMPLE is indented by 2 spaces; the inserted line
    // should be indented at least that deep so it reads naturally.
    const out = appendTrace(SAMPLE, '.R1 > .pin1', '.C1 > .pin2')
    expect(out).toMatch(/\n {6}<trace from="\.R1 > \.pin1" to="\.C1 > \.pin2" \/>\n {2}<\/board>/)
  })

  it('returns original source when no </board> is present (graceful no-op)', () => {
    const src = '<resistor name="R1" />'
    expect(appendTrace(src, '.R1 > .pin1', '.R1 > .pin2')).toBe(src)
  })

  it('returns original source when either selector is empty', () => {
    expect(appendTrace(SAMPLE, '', '.R1 > .pin1')).toBe(SAMPLE)
    expect(appendTrace(SAMPLE, '.R1 > .pin1', '')).toBe(SAMPLE)
  })
})

describe('appendProbe', () => {
  it('inserts the probe comment just before </board>', () => {
    const out = appendProbe(SAMPLE, { name: 'VOUT', kind: 'V', portId: 'src_port_abc123' })
    expect(out).toContain('// @kerf-probe NAME=VOUT KIND=V PORT=src_port_abc123')
    expect(out.indexOf('@kerf-probe')).toBeLessThan(out.indexOf('</board>'))
  })

  it('defaults kind to V when omitted', () => {
    const out = appendProbe(SAMPLE, { name: 'X', portId: 'p1' })
    expect(out).toContain('NAME=X KIND=V PORT=p1')
  })

  it('returns input unchanged when name or portId missing', () => {
    expect(appendProbe(SAMPLE, { name: '', portId: 'p1' })).toBe(SAMPLE)
    expect(appendProbe(SAMPLE, { name: 'X', portId: '' })).toBe(SAMPLE)
  })
})

describe('parseProbes', () => {
  it('round-trips a single appendProbe insertion', () => {
    const stage = appendProbe(SAMPLE, { name: 'VOUT', kind: 'V', portId: 'src_port_abc123' })
    const probes = parseProbes(stage)
    expect(probes).toEqual([{ name: 'VOUT', kind: 'V', portId: 'src_port_abc123' }])
  })

  it('round-trips two probes in stable order', () => {
    let s = appendProbe(SAMPLE, { name: 'V1', kind: 'V', portId: 'p1' })
    s = appendProbe(s, { name: 'I1', kind: 'I', portId: 'simple_q1' })
    const probes = parseProbes(s)
    expect(probes).toHaveLength(2)
    expect(probes[0]).toEqual({ name: 'V1', kind: 'V', portId: 'p1' })
    expect(probes[1]).toEqual({ name: 'I1', kind: 'I', portId: 'simple_q1' })
  })

  it('skips malformed lines without throwing', () => {
    const src = `
      // @kerf-probe NAME=A KIND=V PORT=p1
      // @kerf-probe garbage with no kv pairs at all
      // @kerf-probe NAME=B KIND=Z PORT=p2
      // @kerf-probe NAME=C PORT=p3
      // @kerf-probe NAME=D KIND=I PORT=p4
    `
    const probes = parseProbes(src)
    expect(probes).toHaveLength(2)
    expect(probes[0]).toEqual({ name: 'A', kind: 'V', portId: 'p1' })
    expect(probes[1]).toEqual({ name: 'D', kind: 'I', portId: 'p4' })
  })

  it('extracts NAME / KIND / PORT regardless of attribute order', () => {
    const src = '// @kerf-probe PORT=xyz KIND=I NAME=FOO'
    expect(parseProbes(src)).toEqual([{ name: 'FOO', kind: 'I', portId: 'xyz' }])
  })

  it('returns [] for non-string or empty source', () => {
    expect(parseProbes(null)).toEqual([])
    expect(parseProbes('')).toEqual([])
  })
})

describe('removeProbe', () => {
  it('removes only the named probe and leaves siblings intact', () => {
    let s = appendProbe(SAMPLE, { name: 'V1', kind: 'V', portId: 'p1' })
    s = appendProbe(s, { name: 'V2', kind: 'V', portId: 'p2' })
    const out = removeProbe(s, 'V1')
    expect(out).not.toContain('NAME=V1')
    expect(out).toContain('NAME=V2 KIND=V PORT=p2')
    expect(parseProbes(out)).toEqual([{ name: 'V2', kind: 'V', portId: 'p2' }])
  })

  it('returns input unchanged when no probe matches the name', () => {
    const s = appendProbe(SAMPLE, { name: 'VOUT', kind: 'V', portId: 'p1' })
    expect(removeProbe(s, 'NOPE')).toBe(s)
  })

  it('returns input unchanged for empty / non-string source or empty name', () => {
    expect(removeProbe('', 'X')).toBe('')
    expect(removeProbe(null, 'X')).toBe(null)
    expect(removeProbe(SAMPLE, '')).toBe(SAMPLE)
  })

  it('handles whitespace-tolerant probe lines (extra spaces, mixed indent)', () => {
    const src = `<board>\n  //   @kerf-probe   NAME=FOO  KIND=V   PORT=pX\n</board>`
    const out = removeProbe(src, 'FOO')
    expect(out).not.toContain('@kerf-probe')
    expect(out).toContain('</board>')
  })

  it('removing the only probe leaves </board> intact', () => {
    const s = appendProbe(SAMPLE, { name: 'SOLO', kind: 'I', portId: 'src_q1' })
    const out = removeProbe(s, 'SOLO')
    expect(out).toContain('</board>')
    expect(parseProbes(out)).toEqual([])
  })

  it('matches name as a whole token (V1 does not match V10)', () => {
    let s = appendProbe(SAMPLE, { name: 'V1', kind: 'V', portId: 'p1' })
    s = appendProbe(s, { name: 'V10', kind: 'V', portId: 'p10' })
    const out = removeProbe(s, 'V1')
    expect(out).toContain('NAME=V10')
    expect(parseProbes(out)).toEqual([{ name: 'V10', kind: 'V', portId: 'p10' }])
  })
})

describe('renameProbe', () => {
  it('swaps only the NAME field, preserving KIND/PORT', () => {
    const s = appendProbe(SAMPLE, { name: 'VOUT', kind: 'V', portId: 'src_port_abc123' })
    const out = renameProbe(s, 'VOUT', 'VNEW')
    expect(out).toContain('NAME=VNEW KIND=V PORT=src_port_abc123')
    expect(out).not.toContain('NAME=VOUT')
    expect(parseProbes(out)).toEqual([{ name: 'VNEW', kind: 'V', portId: 'src_port_abc123' }])
  })

  it('returns input unchanged when no probe matches the old name', () => {
    const s = appendProbe(SAMPLE, { name: 'VOUT', kind: 'V', portId: 'p1' })
    expect(renameProbe(s, 'NOPE', 'VNEW')).toBe(s)
  })

  it('returns input unchanged for an empty new name', () => {
    const s = appendProbe(SAMPLE, { name: 'VOUT', kind: 'V', portId: 'p1' })
    expect(renameProbe(s, 'VOUT', '')).toBe(s)
  })

  it('returns input unchanged when new name contains spaces', () => {
    const s = appendProbe(SAMPLE, { name: 'VOUT', kind: 'V', portId: 'p1' })
    expect(renameProbe(s, 'VOUT', 'V NEW')).toBe(s)
  })

  it('returns input unchanged when new name contains =', () => {
    const s = appendProbe(SAMPLE, { name: 'VOUT', kind: 'V', portId: 'p1' })
    expect(renameProbe(s, 'VOUT', 'V=X')).toBe(s)
  })

  it('preserves non-probe content surrounding the line', () => {
    const s = appendProbe(SAMPLE, { name: 'VOUT', kind: 'V', portId: 'p1' })
    const out = renameProbe(s, 'VOUT', 'VNEW')
    expect(out).toContain('name="R1"')
    expect(out).toContain('name="C1"')
    expect(out).toContain('name="U1"')
    expect(out).toContain('</board>')
  })
})

describe('snap', () => {
  it('snaps to the grid', () => {
    expect(snap(1.7, 0.5)).toBeCloseTo(1.5)
    expect(snap(-1.7, 0.5)).toBeCloseTo(-1.5)
    expect(snap(0.04, 0.1)).toBeCloseTo(0)
  })

  it('passes through invalid grid values', () => {
    expect(snap(1.7, 0)).toBe(1.7)
    expect(snap(1.7, NaN)).toBe(1.7)
  })
})
