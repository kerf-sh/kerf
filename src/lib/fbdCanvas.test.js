import { describe, it, expect, beforeEach } from 'vitest'
import {
  createNetwork,
  addBlock,
  addSignal,
  removeBlock,
  removeSignal,
  moveBlock,
  validateNetwork,
  BLOCK_TYPES,
  _resetIdCounter,
} from './fbdCanvas.js'

// ── Fixtures ──────────────────────────────────────────────────────────────────

beforeEach(() => {
  _resetIdCounter()
})

// ── createNetwork ─────────────────────────────────────────────────────────────

describe('createNetwork', () => {
  it('returns an empty network', () => {
    const net = createNetwork()
    expect(net.blocks).toEqual([])
    expect(net.signals).toEqual([])
  })

  it('returns a new object each time', () => {
    const a = createNetwork()
    const b = createNetwork()
    expect(a).not.toBe(b)
  })
})

// ── BLOCK_TYPES ───────────────────────────────────────────────────────────────

describe('BLOCK_TYPES', () => {
  it('includes all required IEC 61131-3 types', () => {
    const required = ['AND', 'OR', 'NOT', 'TON', 'TOF', 'CTU', 'INPUT', 'OUTPUT', 'CONSTANT']
    for (const t of required) {
      expect(BLOCK_TYPES).toContain(t)
    }
  })
})

// ── addBlock ──────────────────────────────────────────────────────────────────

describe('addBlock', () => {
  it('adds a block and returns a new network', () => {
    const net = createNetwork()
    const next = addBlock(net, 'AND', { x: 10, y: 20 })
    expect(next.blocks).toHaveLength(1)
    expect(next.blocks[0].type).toBe('AND')
    expect(next.blocks[0].position).toEqual({ x: 10, y: 20 })
  })

  it('is immutable — original network unchanged', () => {
    const net = createNetwork()
    const before = JSON.stringify(net)
    addBlock(net, 'AND', { x: 0, y: 0 })
    expect(JSON.stringify(net)).toBe(before)
  })

  it('assigns unique ids to successive blocks', () => {
    let net = createNetwork()
    net = addBlock(net, 'AND', { x: 0, y: 0 })
    net = addBlock(net, 'OR',  { x: 0, y: 0 })
    const ids = net.blocks.map(b => b.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('populates input/output pins for AND', () => {
    const net  = addBlock(createNetwork(), 'AND', { x: 0, y: 0 })
    const blk  = net.blocks[0]
    expect(blk.inputs.map(p => p.name)).toEqual(['IN1', 'IN2'])
    expect(blk.outputs.map(p => p.name)).toEqual(['OUT'])
  })

  it('populates input/output pins for NOT', () => {
    const net = addBlock(createNetwork(), 'NOT', { x: 0, y: 0 })
    const blk = net.blocks[0]
    expect(blk.inputs.map(p => p.name)).toEqual(['IN'])
    expect(blk.outputs.map(p => p.name)).toEqual(['OUT'])
  })

  it('gives INPUT block no inputs and one OUT', () => {
    const net = addBlock(createNetwork(), 'INPUT', { x: 0, y: 0 })
    const blk = net.blocks[0]
    expect(blk.inputs).toHaveLength(0)
    expect(blk.outputs.map(p => p.name)).toEqual(['OUT'])
  })

  it('gives OUTPUT block one IN and no outputs', () => {
    const net = addBlock(createNetwork(), 'OUTPUT', { x: 0, y: 0 })
    const blk = net.blocks[0]
    expect(blk.inputs.map(p => p.name)).toEqual(['IN'])
    expect(blk.outputs).toHaveLength(0)
  })

  it('throws for unknown block type', () => {
    expect(() => addBlock(createNetwork(), 'NAND', { x: 0, y: 0 })).toThrow()
  })

  it('stores optional params', () => {
    const net = addBlock(createNetwork(), 'CONSTANT', { x: 0, y: 0 }, { value: 42 })
    expect(net.blocks[0].params.value).toBe(42)
  })
})

// ── addSignal ─────────────────────────────────────────────────────────────────

describe('addSignal', () => {
  function twoBlockNet() {
    let net = createNetwork()
    net = addBlock(net, 'INPUT',  { x: 0,   y: 0 })
    net = addBlock(net, 'OUTPUT', { x: 100, y: 0 })
    return net
  }

  it('adds a signal between two blocks', () => {
    const net  = twoBlockNet()
    const srcId = net.blocks[0].id
    const dstId = net.blocks[1].id
    const next = addSignal(net, srcId, 'OUT', dstId, 'IN')
    expect(next.signals).toHaveLength(1)
    const sig = next.signals[0]
    expect(sig.source_block_id).toBe(srcId)
    expect(sig.source_pin).toBe('OUT')
    expect(sig.dest_block_id).toBe(dstId)
    expect(sig.dest_pin).toBe('IN')
  })

  it('is immutable — original network unchanged', () => {
    const net   = twoBlockNet()
    const before = JSON.stringify(net)
    addSignal(net, net.blocks[0].id, 'OUT', net.blocks[1].id, 'IN')
    expect(JSON.stringify(net)).toBe(before)
  })

  it('updates pin signal_id on both ends', () => {
    const net   = twoBlockNet()
    const srcId = net.blocks[0].id
    const dstId = net.blocks[1].id
    const next  = addSignal(net, srcId, 'OUT', dstId, 'IN')
    const sigId = next.signals[0].id
    const src   = next.blocks.find(b => b.id === srcId)
    const dst   = next.blocks.find(b => b.id === dstId)
    expect(src.outputs.find(p => p.name === 'OUT').signal_id).toBe(sigId)
    expect(dst.inputs.find(p => p.name === 'IN').signal_id).toBe(sigId)
  })

  it('rejects duplicate input drives (same dest pin)', () => {
    const net   = twoBlockNet()
    const [inp, out] = net.blocks
    const net2  = addSignal(net, inp.id, 'OUT', out.id, 'IN')
    // Add a second INPUT block and try to drive the same pin
    let net3    = addBlock(net2, 'INPUT', { x: 0, y: 50 })
    const inp2  = net3.blocks[net3.blocks.length - 1]
    expect(() => addSignal(net3, inp2.id, 'OUT', out.id, 'IN')).toThrow()
  })

  it('rejects self-loop (src === dst block)', () => {
    let net = createNetwork()
    net = addBlock(net, 'AND', { x: 0, y: 0 })
    const id = net.blocks[0].id
    expect(() => addSignal(net, id, 'OUT', id, 'IN1')).toThrow()
  })

  it('throws for non-existent source block', () => {
    const net = twoBlockNet()
    expect(() => addSignal(net, 'ghost', 'OUT', net.blocks[1].id, 'IN')).toThrow()
  })

  it('throws for non-existent dest block', () => {
    const net = twoBlockNet()
    expect(() => addSignal(net, net.blocks[0].id, 'OUT', 'ghost', 'IN')).toThrow()
  })

  it('throws for wrong source pin name', () => {
    const net = twoBlockNet()
    const [src, dst] = net.blocks
    expect(() => addSignal(net, src.id, 'NOPE', dst.id, 'IN')).toThrow()
  })

  it('throws for wrong dest pin name', () => {
    const net = twoBlockNet()
    const [src, dst] = net.blocks
    expect(() => addSignal(net, src.id, 'OUT', dst.id, 'NOPE')).toThrow()
  })
})

// ── removeBlock ───────────────────────────────────────────────────────────────

describe('removeBlock', () => {
  it('removes the block', () => {
    let net = createNetwork()
    net = addBlock(net, 'AND', { x: 0, y: 0 })
    const id  = net.blocks[0].id
    const next = removeBlock(net, id)
    expect(next.blocks).toHaveLength(0)
  })

  it('is immutable — original unchanged', () => {
    let net = createNetwork()
    net = addBlock(net, 'AND', { x: 0, y: 0 })
    const before = JSON.stringify(net)
    removeBlock(net, net.blocks[0].id)
    expect(JSON.stringify(net)).toBe(before)
  })

  it('cascades to remove connected signals', () => {
    let net = createNetwork()
    net = addBlock(net, 'INPUT',  { x: 0,   y: 0 })
    net = addBlock(net, 'OUTPUT', { x: 100, y: 0 })
    const [inp, out] = net.blocks
    net = addSignal(net, inp.id, 'OUT', out.id, 'IN')
    expect(net.signals).toHaveLength(1)

    const next = removeBlock(net, inp.id)
    expect(next.blocks).toHaveLength(1)
    expect(next.signals).toHaveLength(0)
  })

  it('clears signal_id on remaining block pins after cascade', () => {
    let net = createNetwork()
    net = addBlock(net, 'INPUT',  { x: 0,   y: 0 })
    net = addBlock(net, 'OUTPUT', { x: 100, y: 0 })
    const [inp, out] = net.blocks
    net = addSignal(net, inp.id, 'OUT', out.id, 'IN')

    const next   = removeBlock(net, inp.id)
    const outBlk = next.blocks.find(b => b.id === out.id)
    expect(outBlk.inputs[0].signal_id).toBeNull()
  })

  it('throws if block not found', () => {
    expect(() => removeBlock(createNetwork(), 'ghost')).toThrow()
  })
})

// ── removeSignal ──────────────────────────────────────────────────────────────

describe('removeSignal', () => {
  function connectedNet() {
    let net = createNetwork()
    net = addBlock(net, 'INPUT',  { x: 0,   y: 0 })
    net = addBlock(net, 'OUTPUT', { x: 100, y: 0 })
    net = addSignal(net, net.blocks[0].id, 'OUT', net.blocks[1].id, 'IN')
    return net
  }

  it('removes the signal', () => {
    const net  = connectedNet()
    const sigId = net.signals[0].id
    const next = removeSignal(net, sigId)
    expect(next.signals).toHaveLength(0)
  })

  it('is immutable', () => {
    const net    = connectedNet()
    const before = JSON.stringify(net)
    removeSignal(net, net.signals[0].id)
    expect(JSON.stringify(net)).toBe(before)
  })

  it('clears pin signal_id references on both blocks', () => {
    const net   = connectedNet()
    const sigId = net.signals[0].id
    const next  = removeSignal(net, sigId)
    const [inp, out] = next.blocks
    expect(inp.outputs[0].signal_id).toBeNull()
    expect(out.inputs[0].signal_id).toBeNull()
  })

  it('throws if signal not found', () => {
    expect(() => removeSignal(createNetwork(), 'ghost')).toThrow()
  })
})

// ── moveBlock ─────────────────────────────────────────────────────────────────

describe('moveBlock', () => {
  it('updates the block position', () => {
    let net = createNetwork()
    net = addBlock(net, 'AND', { x: 0, y: 0 })
    const id   = net.blocks[0].id
    const next = moveBlock(net, id, { x: 50, y: 75 })
    expect(next.blocks[0].position).toEqual({ x: 50, y: 75 })
  })

  it('is immutable', () => {
    let net = createNetwork()
    net = addBlock(net, 'AND', { x: 0, y: 0 })
    const before = JSON.stringify(net)
    moveBlock(net, net.blocks[0].id, { x: 99, y: 99 })
    expect(JSON.stringify(net)).toBe(before)
  })

  it('throws if block not found', () => {
    expect(() => moveBlock(createNetwork(), 'ghost', { x: 0, y: 0 })).toThrow()
  })
})

// ── validateNetwork ───────────────────────────────────────────────────────────

describe('validateNetwork', () => {
  it('passes for an empty network', () => {
    const { ok, errors } = validateNetwork(createNetwork())
    expect(ok).toBe(true)
    expect(errors).toHaveLength(0)
  })

  it('rejects non-object', () => {
    expect(validateNetwork(null).ok).toBe(false)
    expect(validateNetwork(42).ok).toBe(false)
    expect(validateNetwork('x').ok).toBe(false)
  })

  it('passes for INPUT → AND → OUTPUT', () => {
    let net = createNetwork()
    net = addBlock(net, 'INPUT',  { x: 0,   y: 0 })
    net = addBlock(net, 'INPUT',  { x: 0,   y: 50 })
    net = addBlock(net, 'AND',    { x: 100, y: 25 })
    net = addBlock(net, 'OUTPUT', { x: 200, y: 25 })
    const [in1, in2, and, out] = net.blocks
    net = addSignal(net, in1.id, 'OUT', and.id,  'IN1')
    net = addSignal(net, in2.id, 'OUT', and.id,  'IN2')
    net = addSignal(net, and.id, 'OUT', out.id, 'IN')
    const { ok, errors } = validateNetwork(net)
    expect(ok).toBe(true)
    expect(errors).toHaveLength(0)
  })

  it('detects a cycle: A → B → A', () => {
    // Manually construct a network that bypasses addSignal validation
    // so we can test the cycle detector with two blocks that point at each other.
    // We use AND (has both IN1 and IN2 inputs and OUT output) for both sides.
    let net = createNetwork()
    net = addBlock(net, 'AND', { x: 0,   y: 0 })
    net = addBlock(net, 'AND', { x: 100, y: 0 })
    const [a, b] = net.blocks

    // addSignal would reject this because of missing required inputs, but
    // we want to inject the cycle directly to test the cycle detector.
    const cyclic = {
      blocks: net.blocks,
      signals: [
        { id: 'sig_fwd', source_block_id: a.id, source_pin: 'OUT', dest_block_id: b.id, dest_pin: 'IN1' },
        { id: 'sig_back', source_block_id: b.id, source_pin: 'OUT', dest_block_id: a.id, dest_pin: 'IN1' },
      ],
    }

    const { ok, errors } = validateNetwork(cyclic)
    expect(ok).toBe(false)
    expect(errors.some(e => e.toLowerCase().includes('cycle'))).toBe(true)
  })

  it('flags unconnected required inputs', () => {
    let net = createNetwork()
    net = addBlock(net, 'AND', { x: 0, y: 0 })
    // No signals connected
    const { ok, errors } = validateNetwork(net)
    expect(ok).toBe(false)
    expect(errors.some(e => e.includes('IN1'))).toBe(true)
    expect(errors.some(e => e.includes('IN2'))).toBe(true)
  })

  it('flags double-driven input in the validate pass', () => {
    let net = createNetwork()
    net = addBlock(net, 'INPUT',  { x: 0,   y: 0 })
    net = addBlock(net, 'INPUT',  { x: 0,   y: 50 })
    net = addBlock(net, 'OUTPUT', { x: 100, y: 0 })
    const [in1, in2, out] = net.blocks

    // Inject double-drive directly to bypass addSignal guard
    const doubleDriven = {
      blocks: net.blocks,
      signals: [
        { id: 'sig1', source_block_id: in1.id, source_pin: 'OUT', dest_block_id: out.id, dest_pin: 'IN' },
        { id: 'sig2', source_block_id: in2.id, source_pin: 'OUT', dest_block_id: out.id, dest_pin: 'IN' },
      ],
    }

    const { ok, errors } = validateNetwork(doubleDriven)
    expect(ok).toBe(false)
    expect(errors.some(e => e.toLowerCase().includes('double') || e.includes('driven'))).toBe(true)
  })

  it('flags dangling signal with missing source block', () => {
    let net = createNetwork()
    net = addBlock(net, 'OUTPUT', { x: 100, y: 0 })
    const out = net.blocks[0]
    const dangling = {
      blocks: net.blocks,
      signals: [
        { id: 'sig1', source_block_id: 'ghost', source_pin: 'OUT', dest_block_id: out.id, dest_pin: 'IN' },
      ],
    }
    const { ok, errors } = validateNetwork(dangling)
    expect(ok).toBe(false)
    expect(errors.some(e => e.includes('ghost'))).toBe(true)
  })
})
