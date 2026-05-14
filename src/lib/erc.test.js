import { describe, it, expect } from 'vitest'
import { runERC } from './erc.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _cid = 0, _pid = 0, _tid = 0, _nid = 0

function resetIds() { _cid = _pid = _tid = _nid = 0 }

function makeComponent(name, extra = {}) {
  return { type: 'source_component', source_component_id: `c${++_cid}`, name, ...extra }
}

function makePort(componentId, name, pin_type = 'passive', extra = {}) {
  return { type: 'source_port', source_port_id: `p${++_pid}`, source_component_id: componentId, name, pin_type, ...extra }
}

function makeTrace(...portIds) {
  return { type: 'source_trace', source_trace_id: `t${++_tid}`, connected_source_port_ids: portIds }
}

function makeNet(name, extra = {}) {
  return { type: 'source_net', source_net_id: `n${++_nid}`, name, ...extra }
}

// ---------------------------------------------------------------------------
// Check 1: unconnected_pin
// ---------------------------------------------------------------------------

describe('ERC — unconnected_pin', () => {
  it('flags a port with no trace', () => {
    resetIds()
    const c = makeComponent('R1')
    const p1 = makePort(c.source_component_id, 'pin1')
    const p2 = makePort(c.source_component_id, 'pin2')
    const t = makeTrace(p1.source_port_id)       // p2 not connected
    const { errors } = runERC([c, p1, p2, t])
    expect(errors.some((e) => e.kind === 'unconnected_pin' && e.port_id === p2.source_port_id)).toBe(true)
  })

  it('no error when every port has a trace', () => {
    resetIds()
    const c = makeComponent('R1')
    const p1 = makePort(c.source_component_id, 'pin1')
    const p2 = makePort(c.source_component_id, 'pin2')
    const t = makeTrace(p1.source_port_id, p2.source_port_id)
    const { errors } = runERC([c, p1, p2, t])
    expect(errors.filter((e) => e.kind === 'unconnected_pin')).toHaveLength(0)
  })

  it('returns empty on empty circuit', () => {
    const { errors, warnings } = runERC([])
    expect(errors).toHaveLength(0)
    expect(warnings).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Check 2: duplicate_refdes
// ---------------------------------------------------------------------------

describe('ERC — duplicate_refdes', () => {
  it('flags two components with the same name', () => {
    resetIds()
    const c1 = makeComponent('U1')
    const c2 = makeComponent('U1')
    const { errors } = runERC([c1, c2])
    expect(errors.some((e) => e.kind === 'duplicate_refdes')).toBe(true)
  })

  it('no error when refdes are unique', () => {
    resetIds()
    const c1 = makeComponent('U1')
    const c2 = makeComponent('U2')
    const { errors } = runERC([c1, c2])
    expect(errors.filter((e) => e.kind === 'duplicate_refdes')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Check 3: conflicting_net_label
// ---------------------------------------------------------------------------

describe('ERC — conflicting_net_label', () => {
  it('flags two nets merged by a trace that have different names', () => {
    resetIds()
    const n1 = makeNet('VCC')
    const n2 = makeNet('GND')
    // A trace that connects both net ids — they'd get the same union-find root
    const t = { type: 'source_trace', source_trace_id: 't1',
                connected_source_port_ids: [],
                connected_source_net_ids: [n1.source_net_id, n2.source_net_id] }
    const { errors } = runERC([n1, n2, t])
    expect(errors.some((e) => e.kind === 'conflicting_net_label')).toBe(true)
  })

  it('no error when nets are on separate traces', () => {
    resetIds()
    const n1 = makeNet('VCC')
    const n2 = makeNet('GND')
    // No trace connects them
    const { errors } = runERC([n1, n2])
    expect(errors.filter((e) => e.kind === 'conflicting_net_label')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Check 4: output_to_output
// ---------------------------------------------------------------------------

describe('ERC — output_to_output', () => {
  it('flags two output ports tied together', () => {
    resetIds()
    const c1 = makeComponent('U1')
    const c2 = makeComponent('U2')
    const p1 = makePort(c1.source_component_id, 'OUT', 'output')
    const p2 = makePort(c2.source_component_id, 'OUT', 'output')
    const t  = makeTrace(p1.source_port_id, p2.source_port_id)
    const { errors } = runERC([c1, c2, p1, p2, t])
    expect(errors.some((e) => e.kind === 'output_to_output')).toBe(true)
  })

  it('does not flag open-collector outputs tied together', () => {
    resetIds()
    const c1 = makeComponent('U1')
    const c2 = makeComponent('U2')
    const p1 = makePort(c1.source_component_id, 'OC1', 'output', { electrical_function: 'open_collector' })
    const p2 = makePort(c2.source_component_id, 'OC2', 'output', { electrical_function: 'open_collector' })
    const t  = makeTrace(p1.source_port_id, p2.source_port_id)
    const { errors } = runERC([c1, c2, p1, p2, t])
    expect(errors.filter((e) => e.kind === 'output_to_output')).toHaveLength(0)
  })

  it('does not flag output connected to input', () => {
    resetIds()
    const c1 = makeComponent('U1')
    const c2 = makeComponent('U2')
    const p1 = makePort(c1.source_component_id, 'OUT', 'output')
    const p2 = makePort(c2.source_component_id, 'IN',  'input')
    const t  = makeTrace(p1.source_port_id, p2.source_port_id)
    const { errors } = runERC([c1, c2, p1, p2, t])
    expect(errors.filter((e) => e.kind === 'output_to_output')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Check 5: missing_power
// ---------------------------------------------------------------------------

describe('ERC — missing_power', () => {
  it('flags a power net with no supplying port', () => {
    resetIds()
    const n = makeNet('VCC', { is_power: true })
    const { errors } = runERC([n])
    expect(errors.some((e) => e.kind === 'missing_power')).toBe(true)
  })

  it('no error when a power port sources the net', () => {
    resetIds()
    const n  = makeNet('VCC', { is_power: true })
    const c  = makeComponent('PS1')
    const p  = makePort(c.source_component_id, 'VCC_OUT', 'power', { source_net_id: n.source_net_id })
    const { errors } = runERC([n, c, p])
    expect(errors.filter((e) => e.kind === 'missing_power')).toHaveLength(0)
  })

  it('flags GND by name convention', () => {
    resetIds()
    const n = makeNet('GND')
    const { errors } = runERC([n])
    expect(errors.some((e) => e.kind === 'missing_power')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Check 6: pin_direction_mismatch (warning)
// ---------------------------------------------------------------------------

describe('ERC — pin_direction_mismatch', () => {
  it('warns when two inputs are directly wired with no driver', () => {
    resetIds()
    const c1 = makeComponent('U1')
    const c2 = makeComponent('U2')
    const p1 = makePort(c1.source_component_id, 'IN1', 'input')
    const p2 = makePort(c2.source_component_id, 'IN2', 'input')
    const t  = makeTrace(p1.source_port_id, p2.source_port_id)
    const { warnings } = runERC([c1, c2, p1, p2, t])
    expect(warnings.some((w) => w.kind === 'pin_direction_mismatch')).toBe(true)
  })

  it('no warning when an output also drives the net', () => {
    resetIds()
    const c1 = makeComponent('U1')
    const c2 = makeComponent('U2')
    const c3 = makeComponent('U3')
    const p1 = makePort(c1.source_component_id, 'IN1', 'input')
    const p2 = makePort(c2.source_component_id, 'IN2', 'input')
    const p3 = makePort(c3.source_component_id, 'OUT', 'output')
    const t  = makeTrace(p1.source_port_id, p2.source_port_id, p3.source_port_id)
    const { warnings } = runERC([c1, c2, c3, p1, p2, p3, t])
    expect(warnings.filter((w) => w.kind === 'pin_direction_mismatch')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Check 7: floating_net (warning)
// ---------------------------------------------------------------------------

describe('ERC — floating_net', () => {
  it('warns when a trace connects only one port', () => {
    resetIds()
    const c = makeComponent('R1')
    const p = makePort(c.source_component_id, 'pin1')
    const t = makeTrace(p.source_port_id)
    const { warnings } = runERC([c, p, t])
    expect(warnings.some((w) => w.kind === 'floating_net')).toBe(true)
  })

  it('no warning when a trace connects two or more ports', () => {
    resetIds()
    const c1 = makeComponent('R1')
    const c2 = makeComponent('R2')
    const p1 = makePort(c1.source_component_id, 'pin1')
    const p2 = makePort(c2.source_component_id, 'pin1')
    const t  = makeTrace(p1.source_port_id, p2.source_port_id)
    const { warnings } = runERC([c1, c2, p1, p2, t])
    expect(warnings.filter((w) => w.kind === 'floating_net')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Check 8: bidirectional_promiscuity (warning)
// ---------------------------------------------------------------------------

describe('ERC — bidirectional_promiscuity', () => {
  it('warns when more than 3 bidir ports share a net', () => {
    resetIds()
    const portIds = []
    const elements = []
    for (let i = 1; i <= 4; i++) {
      const c = makeComponent(`U${i}`)
      const p = makePort(c.source_component_id, `SDA${i}`, 'bidirectional')
      elements.push(c, p)
      portIds.push(p.source_port_id)
    }
    const t = makeTrace(...portIds)
    const { warnings } = runERC([...elements, t])
    expect(warnings.some((w) => w.kind === 'bidirectional_promiscuity')).toBe(true)
  })

  it('no warning with 3 or fewer bidir ports on a net', () => {
    resetIds()
    const portIds = []
    const elements = []
    for (let i = 1; i <= 3; i++) {
      const c = makeComponent(`U${i}`)
      const p = makePort(c.source_component_id, `SDA${i}`, 'bidirectional')
      elements.push(c, p)
      portIds.push(p.source_port_id)
    }
    const t = makeTrace(...portIds)
    const { warnings } = runERC([...elements, t])
    expect(warnings.filter((w) => w.kind === 'bidirectional_promiscuity')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// Severity field
// ---------------------------------------------------------------------------

describe('ERC — severity field', () => {
  it('errors carry severity=error', () => {
    resetIds()
    const c = makeComponent('U1')
    const c2 = makeComponent('U1')   // duplicate
    const { errors } = runERC([c, c2])
    expect(errors.every((e) => e.severity === 'error')).toBe(true)
  })

  it('warnings carry severity=warning', () => {
    resetIds()
    const c1 = makeComponent('U1')
    const c2 = makeComponent('U2')
    const p1 = makePort(c1.source_component_id, 'IN1', 'input')
    const p2 = makePort(c2.source_component_id, 'IN2', 'input')
    const t  = makeTrace(p1.source_port_id, p2.source_port_id)
    const { warnings } = runERC([c1, c2, p1, p2, t])
    expect(warnings.every((w) => w.severity === 'warning')).toBe(true)
  })
})
