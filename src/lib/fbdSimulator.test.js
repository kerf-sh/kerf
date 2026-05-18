import { describe, it, expect, beforeEach } from 'vitest'
import { simulateFbdTick, runFbdFor, topoSort } from './fbdSimulator.js'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Minimal valid network with no blocks or signals.
 */
function emptyNetwork() {
  return { blocks: [], signals: [] }
}

/**
 * Build a simple network: INPUT → gate → OUTPUT
 * Returns { network, inputId, gateId, outputId }
 */
function makeGateNetwork(gateType, extraParams = {}) {
  // INPUT A
  const inputA = {
    id: 'inputA',
    type: 'INPUT',
    params: { name: 'A' },
    inputs: [],
    outputs: [{ name: 'OUT', signal_id: null }],
  }
  // INPUT B (for two-input gates)
  const inputB = {
    id: 'inputB',
    type: 'INPUT',
    params: { name: 'B' },
    inputs: [],
    outputs: [{ name: 'OUT', signal_id: null }],
  }
  // Gate block
  const isTwoInput = ['AND', 'OR'].includes(gateType)
  const gateInputs = isTwoInput
    ? [{ name: 'IN1', signal_id: 'sig_a' }, { name: 'IN2', signal_id: 'sig_b' }]
    : [{ name: 'IN', signal_id: 'sig_a' }]
  const gate = {
    id: 'gate',
    type: gateType,
    params: { ...extraParams },
    inputs: gateInputs,
    outputs: [{ name: 'OUT', signal_id: null }],
  }
  // OUTPUT
  const output = {
    id: 'outputY',
    type: 'OUTPUT',
    params: { name: 'Y' },
    inputs: [{ name: 'IN', signal_id: 'sig_out' }],
    outputs: [],
  }

  const signals = isTwoInput
    ? [
        { id: 'sig_a', source_block_id: 'inputA', source_pin: 'OUT', dest_block_id: 'gate', dest_pin: 'IN1' },
        { id: 'sig_b', source_block_id: 'inputB', source_pin: 'OUT', dest_block_id: 'gate', dest_pin: 'IN2' },
        { id: 'sig_out', source_block_id: 'gate', source_pin: 'OUT', dest_block_id: 'outputY', dest_pin: 'IN' },
      ]
    : [
        { id: 'sig_a', source_block_id: 'inputA', source_pin: 'OUT', dest_block_id: 'gate', dest_pin: 'IN' },
        { id: 'sig_out', source_block_id: 'gate', source_pin: 'OUT', dest_block_id: 'outputY', dest_pin: 'IN' },
      ]

  const blocks = isTwoInput
    ? [inputA, inputB, gate, output]
    : [inputA, gate, output]

  return { network: { blocks, signals } }
}

// ── topoSort ──────────────────────────────────────────────────────────────────

describe('topoSort', () => {
  it('returns [] for empty network', () => {
    expect(topoSort(emptyNetwork())).toEqual([])
  })

  it('orders a 3-block chain INPUT → AND → OUTPUT', () => {
    const { network } = makeGateNetwork('AND')
    const order = topoSort(network)
    // inputA and inputB must appear before gate; gate before outputY
    expect(order.indexOf('inputA')).toBeLessThan(order.indexOf('gate'))
    expect(order.indexOf('inputB')).toBeLessThan(order.indexOf('gate'))
    expect(order.indexOf('gate')).toBeLessThan(order.indexOf('outputY'))
  })

  it('raises a structured error with code=CYCLE on self-feedback', () => {
    // Block that feeds back to itself: blocked by addSignal but we test the
    // topo-sort's cycle detection independently with a hand-crafted network.
    const network = {
      blocks: [
        { id: 'a', type: 'AND', params: {}, inputs: [{ name: 'IN1', signal_id: 's1' }, { name: 'IN2', signal_id: null }], outputs: [{ name: 'OUT', signal_id: 's1' }] },
        { id: 'b', type: 'AND', params: {}, inputs: [{ name: 'IN1', signal_id: 's2' }, { name: 'IN2', signal_id: null }], outputs: [{ name: 'OUT', signal_id: 's2' }] },
      ],
      signals: [
        // a → b → a  (cycle of length 2)
        { id: 's1', source_block_id: 'a', source_pin: 'OUT', dest_block_id: 'b', dest_pin: 'IN1' },
        { id: 's2', source_block_id: 'b', source_pin: 'OUT', dest_block_id: 'a', dest_pin: 'IN1' },
      ],
    }
    let thrown
    try {
      topoSort(network)
    } catch (e) {
      thrown = e
    }
    expect(thrown).toBeDefined()
    expect(thrown.code).toBe('CYCLE')
    expect(Array.isArray(thrown.blocks)).toBe(true)
    expect(thrown.blocks.length).toBeGreaterThan(0)
  })
})

// ── AND gate ──────────────────────────────────────────────────────────────────

describe('AND gate', () => {
  it('true AND true → true', () => {
    const { network } = makeGateNetwork('AND')
    const { outputs } = simulateFbdTick(network, { A: true, B: true }, {})
    expect(outputs.Y).toBe(true)
  })

  it('true AND false → false', () => {
    const { network } = makeGateNetwork('AND')
    const { outputs } = simulateFbdTick(network, { A: true, B: false }, {})
    expect(outputs.Y).toBe(false)
  })

  it('false AND false → false', () => {
    const { network } = makeGateNetwork('AND')
    const { outputs } = simulateFbdTick(network, { A: false, B: false }, {})
    expect(outputs.Y).toBe(false)
  })

  it('false AND true → false', () => {
    const { network } = makeGateNetwork('AND')
    const { outputs } = simulateFbdTick(network, { A: false, B: true }, {})
    expect(outputs.Y).toBe(false)
  })
})

// ── OR gate ───────────────────────────────────────────────────────────────────

describe('OR gate', () => {
  it('false OR false → false', () => {
    const { network } = makeGateNetwork('OR')
    const { outputs } = simulateFbdTick(network, { A: false, B: false }, {})
    expect(outputs.Y).toBe(false)
  })

  it('true OR false → true', () => {
    const { network } = makeGateNetwork('OR')
    const { outputs } = simulateFbdTick(network, { A: true, B: false }, {})
    expect(outputs.Y).toBe(true)
  })

  it('false OR true → true', () => {
    const { network } = makeGateNetwork('OR')
    const { outputs } = simulateFbdTick(network, { A: false, B: true }, {})
    expect(outputs.Y).toBe(true)
  })

  it('true OR true → true', () => {
    const { network } = makeGateNetwork('OR')
    const { outputs } = simulateFbdTick(network, { A: true, B: true }, {})
    expect(outputs.Y).toBe(true)
  })
})

// ── NOT gate ──────────────────────────────────────────────────────────────────

describe('NOT gate', () => {
  it('NOT true → false', () => {
    const { network } = makeGateNetwork('NOT')
    const { outputs } = simulateFbdTick(network, { A: true }, {})
    expect(outputs.Y).toBe(false)
  })

  it('NOT false → true', () => {
    const { network } = makeGateNetwork('NOT')
    const { outputs } = simulateFbdTick(network, { A: false }, {})
    expect(outputs.Y).toBe(true)
  })
})

// ── TON (on-delay timer) ──────────────────────────────────────────────────────

describe('TON timer', () => {
  /**
   * Build INPUT → TON → OUTPUT network for the TON tests.
   * TON.PT is baked into block params (500 ms).
   */
  function makeTONNetwork(pt_ms = 500) {
    const inputBlock = {
      id: 'inp',
      type: 'INPUT',
      params: { name: 'IN_SIG' },
      inputs: [],
      outputs: [{ name: 'OUT', signal_id: 's1' }],
    }
    const tonBlock = {
      id: 'ton',
      type: 'TON',
      params: { PT: pt_ms },
      inputs: [{ name: 'IN', signal_id: 's1' }],
      outputs: [{ name: 'Q', signal_id: 's2' }, { name: 'ET', signal_id: null }],
    }
    const outputBlock = {
      id: 'out',
      type: 'OUTPUT',
      params: { name: 'Q_OUT' },
      inputs: [{ name: 'IN', signal_id: 's2' }],
      outputs: [],
    }
    const network = {
      blocks: [inputBlock, tonBlock, outputBlock],
      signals: [
        { id: 's1', source_block_id: 'inp', source_pin: 'OUT', dest_block_id: 'ton', dest_pin: 'IN' },
        { id: 's2', source_block_id: 'ton', source_pin: 'Q', dest_block_id: 'out', dest_pin: 'IN' },
      ],
    }
    return network
  }

  it('Q is false before PT elapses', () => {
    const network = makeTONNetwork(500)
    let state = {}
    // Run 499 ticks with IN=true — Q should still be false
    for (let t = 0; t < 499; t++) {
      const result = simulateFbdTick(network, { IN_SIG: true }, state)
      state = result.newState
      expect(result.outputs.Q_OUT).toBe(false)
    }
  })

  it('Q rises after exactly PT ticks (500 ms with tick_ms=1)', () => {
    const network = makeTONNetwork(500)
    let state = {}
    let outputs = {}
    for (let t = 0; t < 500; t++) {
      ;({ outputs, newState: state } = simulateFbdTick(network, { IN_SIG: true }, state, 1))
    }
    expect(outputs.Q_OUT).toBe(true)
  })

  it('Q resets when IN drops back to false', () => {
    const network = makeTONNetwork(500)
    let state = {}
    // Bring Q high
    for (let t = 0; t < 500; t++) {
      ;({ newState: state } = simulateFbdTick(network, { IN_SIG: true }, state, 1))
    }
    // Drop IN — Q should immediately go false
    const { outputs } = simulateFbdTick(network, { IN_SIG: false }, state)
    expect(outputs.Q_OUT).toBe(false)
  })
})

// ── TOF (off-delay timer) ─────────────────────────────────────────────────────

describe('TOF timer', () => {
  function makeTOFNetwork(pt_ms = 100) {
    const inputBlock = {
      id: 'inp',
      type: 'INPUT',
      params: { name: 'IN_SIG' },
      inputs: [],
      outputs: [{ name: 'OUT', signal_id: 's1' }],
    }
    const tofBlock = {
      id: 'tof',
      type: 'TOF',
      params: { PT: pt_ms },
      inputs: [{ name: 'IN', signal_id: 's1' }],
      outputs: [{ name: 'Q', signal_id: 's2' }, { name: 'ET', signal_id: null }],
    }
    const outputBlock = {
      id: 'out',
      type: 'OUTPUT',
      params: { name: 'Q_OUT' },
      inputs: [{ name: 'IN', signal_id: 's2' }],
      outputs: [],
    }
    return {
      blocks: [inputBlock, tofBlock, outputBlock],
      signals: [
        { id: 's1', source_block_id: 'inp', source_pin: 'OUT', dest_block_id: 'tof', dest_pin: 'IN' },
        { id: 's2', source_block_id: 'tof', source_pin: 'Q', dest_block_id: 'out', dest_pin: 'IN' },
      ],
    }
  }

  it('Q is true while IN is true', () => {
    const network = makeTOFNetwork(100)
    const { outputs } = simulateFbdTick(network, { IN_SIG: true }, {})
    expect(outputs.Q_OUT).toBe(true)
  })

  it('Q stays true for PT ms after IN falls', () => {
    const network = makeTOFNetwork(100)
    let state = {}
    // Assert IN for a few ticks
    for (let t = 0; t < 5; t++) {
      ;({ newState: state } = simulateFbdTick(network, { IN_SIG: true }, state))
    }
    // Drop IN — Q should still be true during off-delay
    let outputs
    for (let t = 0; t < 99; t++) {
      ;({ outputs, newState: state } = simulateFbdTick(network, { IN_SIG: false }, state))
      expect(outputs.Q_OUT).toBe(true)
    }
  })

  it('Q drops after PT ms of IN=false', () => {
    const network = makeTOFNetwork(100)
    let state = {}
    for (let t = 0; t < 5; t++) {
      ;({ newState: state } = simulateFbdTick(network, { IN_SIG: true }, state))
    }
    // Tick exactly PT=100 ticks with IN=false
    let outputs
    for (let t = 0; t < 100; t++) {
      ;({ outputs, newState: state } = simulateFbdTick(network, { IN_SIG: false }, state))
    }
    expect(outputs.Q_OUT).toBe(false)
  })
})

// ── CTU (up-counter) ──────────────────────────────────────────────────────────

describe('CTU counter', () => {
  function makeCTUNetwork(pv = 3) {
    const cuInput = {
      id: 'cu',
      type: 'INPUT',
      params: { name: 'CU_SIG' },
      inputs: [],
      outputs: [{ name: 'OUT', signal_id: 's1' }],
    }
    const ctuBlock = {
      id: 'ctu',
      type: 'CTU',
      params: { PV: pv },
      inputs: [{ name: 'CU', signal_id: 's1' }],
      outputs: [{ name: 'Q', signal_id: 's2' }, { name: 'CV', signal_id: null }],
    }
    const outputBlock = {
      id: 'out',
      type: 'OUTPUT',
      params: { name: 'Q_OUT' },
      inputs: [{ name: 'IN', signal_id: 's2' }],
      outputs: [],
    }
    return {
      blocks: [cuInput, ctuBlock, outputBlock],
      signals: [
        { id: 's1', source_block_id: 'cu', source_pin: 'OUT', dest_block_id: 'ctu', dest_pin: 'CU' },
        { id: 's2', source_block_id: 'ctu', source_pin: 'Q', dest_block_id: 'out', dest_pin: 'IN' },
      ],
    }
  }

  it('Q is false before PV rising edges', () => {
    const network = makeCTUNetwork(3)
    let state = {}
    for (let i = 0; i < 2; i++) {
      // Rising edge: false → true
      ;({ newState: state } = simulateFbdTick(network, { CU_SIG: false }, state))
      const { outputs } = simulateFbdTick(network, { CU_SIG: true }, state)
      ;({ newState: state } = simulateFbdTick(network, { CU_SIG: true }, state))
      expect(outputs.Q_OUT).toBe(false)
    }
  })

  it('Q rises after PV rising edges', () => {
    const network = makeCTUNetwork(3)
    let state = {}
    let outputs
    for (let i = 0; i < 3; i++) {
      // Rising edge
      ;({ newState: state } = simulateFbdTick(network, { CU_SIG: false }, state))
      ;({ outputs, newState: state } = simulateFbdTick(network, { CU_SIG: true }, state))
    }
    expect(outputs.Q_OUT).toBe(true)
  })
})

// ── CONSTANT block ────────────────────────────────────────────────────────────

describe('CONSTANT block', () => {
  it('emits fixed boolean value', () => {
    const network = {
      blocks: [
        { id: 'c', type: 'CONSTANT', params: { value: true }, inputs: [], outputs: [{ name: 'OUT', signal_id: 's1' }] },
        { id: 'o', type: 'OUTPUT', params: { name: 'R' }, inputs: [{ name: 'IN', signal_id: 's1' }], outputs: [] },
      ],
      signals: [{ id: 's1', source_block_id: 'c', source_pin: 'OUT', dest_block_id: 'o', dest_pin: 'IN' }],
    }
    const { outputs } = simulateFbdTick(network, {}, {})
    expect(outputs.R).toBe(true)
  })

  it('emits fixed numeric value', () => {
    const network = {
      blocks: [
        { id: 'c', type: 'CONSTANT', params: { value: 42 }, inputs: [], outputs: [{ name: 'OUT', signal_id: 's1' }] },
        { id: 'o', type: 'OUTPUT', params: { name: 'R' }, inputs: [{ name: 'IN', signal_id: 's1' }], outputs: [] },
      ],
      signals: [{ id: 's1', source_block_id: 'c', source_pin: 'OUT', dest_block_id: 'o', dest_pin: 'IN' }],
    }
    const { outputs } = simulateFbdTick(network, {}, {})
    expect(outputs.R).toBe(42)
  })
})

// ── runFbdFor ─────────────────────────────────────────────────────────────────

describe('runFbdFor', () => {
  it('returns one entry per tick', () => {
    const { network } = makeGateNetwork('AND')
    const trace = runFbdFor(network, { A: true, B: true }, 5, 1)
    expect(trace).toHaveLength(5)
    expect(trace[0].tick).toBe(0)
    expect(trace[4].tick).toBe(4)
  })

  it('accepts a function inputProvider', () => {
    const { network } = makeGateNetwork('NOT')
    const trace = runFbdFor(
      network,
      (tick) => ({ A: tick < 3 }),
      6,
      1,
    )
    // Ticks 0–2: A=true → NOT → Y=false
    // Ticks 3–5: A=false → NOT → Y=true
    expect(trace[0].outputs.Y).toBe(false)
    expect(trace[2].outputs.Y).toBe(false)
    expect(trace[3].outputs.Y).toBe(true)
    expect(trace[5].outputs.Y).toBe(true)
  })

  it('accumulates elapsed_ms correctly', () => {
    const { network } = makeGateNetwork('OR')
    const trace = runFbdFor(network, { A: false, B: false }, 10, 2)
    expect(trace).toHaveLength(5)
    expect(trace[0].elapsed_ms).toBe(0)
    expect(trace[1].elapsed_ms).toBe(2)
    expect(trace[4].elapsed_ms).toBe(8)
  })

  it('simulates TON rising after 500 ticks via runFbdFor', () => {
    const inputBlock = {
      id: 'inp', type: 'INPUT', params: { name: 'IN_SIG' },
      inputs: [], outputs: [{ name: 'OUT', signal_id: 's1' }],
    }
    const tonBlock = {
      id: 'ton', type: 'TON', params: { PT: 500 },
      inputs: [{ name: 'IN', signal_id: 's1' }],
      outputs: [{ name: 'Q', signal_id: 's2' }, { name: 'ET', signal_id: null }],
    }
    const outBlock = {
      id: 'out', type: 'OUTPUT', params: { name: 'Q_OUT' },
      inputs: [{ name: 'IN', signal_id: 's2' }], outputs: [],
    }
    const network = {
      blocks: [inputBlock, tonBlock, outBlock],
      signals: [
        { id: 's1', source_block_id: 'inp', source_pin: 'OUT', dest_block_id: 'ton', dest_pin: 'IN' },
        { id: 's2', source_block_id: 'ton', source_pin: 'Q', dest_block_id: 'out', dest_pin: 'IN' },
      ],
    }
    const trace = runFbdFor(network, { IN_SIG: true }, 501, 1)
    // ET accumulates 1 ms per tick; at tick 498 ET=499, at tick 499 ET reaches 500 → Q rises.
    // At tick 498 (elapsed=498 ms, ET=499) Q is still false
    expect(trace[498].outputs.Q_OUT).toBe(false)
    // At tick 499 (elapsed=499 ms, ET=500) Q is true
    expect(trace[499].outputs.Q_OUT).toBe(true)
  })
})

// ── Cycle detection (simulateFbdTick surface) ─────────────────────────────────

describe('cycle detection — simulateFbdTick', () => {
  it('raises a structured CYCLE error', () => {
    const network = {
      blocks: [
        { id: 'a', type: 'AND', params: {},
          inputs: [{ name: 'IN1', signal_id: 's2' }, { name: 'IN2', signal_id: null }],
          outputs: [{ name: 'OUT', signal_id: 's1' }] },
        { id: 'b', type: 'AND', params: {},
          inputs: [{ name: 'IN1', signal_id: 's1' }, { name: 'IN2', signal_id: null }],
          outputs: [{ name: 'OUT', signal_id: 's2' }] },
      ],
      signals: [
        { id: 's1', source_block_id: 'a', source_pin: 'OUT', dest_block_id: 'b', dest_pin: 'IN1' },
        { id: 's2', source_block_id: 'b', source_pin: 'OUT', dest_block_id: 'a', dest_pin: 'IN1' },
      ],
    }
    expect(() => simulateFbdTick(network, {}, {})).toThrowError(/cycle/i)
    try {
      simulateFbdTick(network, {}, {})
    } catch (e) {
      expect(e.code).toBe('CYCLE')
      expect(Array.isArray(e.blocks)).toBe(true)
    }
  })
})
