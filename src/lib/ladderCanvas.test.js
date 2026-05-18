// ladderCanvas.test.js — Vitest unit tests for the pure-logic ladder canvas lib.

import { describe, it, expect } from 'vitest'
import {
  createRung,
  addContact,
  addCoil,
  deleteElement,
  moveElement,
  validateRung,
  serialiseRung,
} from './ladderCanvas.js'

// ── Fixture helpers ────────────────────────────────────────────────────────────

function makePopulatedRung() {
  let r = createRung('test-rung')
  r = addContact(r, 'no', 0, { name: 'START' })
  r = addContact(r, 'nc', 1, { name: 'STOP' })
  r = addCoil(r, 'output', 5, { name: 'MOTOR' })
  return r
}

// ── createRung ─────────────────────────────────────────────────────────────────

describe('createRung', () => {
  it('returns an object with empty contacts, coils, and wires arrays', () => {
    const r = createRung()
    expect(Array.isArray(r.contacts)).toBe(true)
    expect(Array.isArray(r.coils)).toBe(true)
    expect(Array.isArray(r.wires)).toBe(true)
    expect(r.contacts).toHaveLength(0)
    expect(r.coils).toHaveLength(0)
    expect(r.wires).toHaveLength(0)
  })

  it('uses the provided id', () => {
    const r = createRung('my-rung')
    expect(r.id).toBe('my-rung')
  })

  it('auto-generates an id when none provided', () => {
    const r = createRung()
    expect(typeof r.id).toBe('string')
    expect(r.id.length).toBeGreaterThan(0)
  })
})

// ── addContact ─────────────────────────────────────────────────────────────────

describe('addContact', () => {
  it('adds a NO contact to the rung', () => {
    const r = createRung()
    const r2 = addContact(r, 'no', 0)
    expect(r2.contacts).toHaveLength(1)
    expect(r2.contacts[0].type).toBe('no')
    expect(r2.contacts[0].position).toBe(0)
  })

  it('adds a NC contact with negated=true by default', () => {
    const r = addContact(createRung(), 'nc', 0)
    expect(r.contacts[0].negated).toBe(true)
  })

  it('adds a rising-edge contact', () => {
    const r = addContact(createRung(), 'rising', 2)
    expect(r.contacts[0].type).toBe('rising')
  })

  it('adds a falling-edge contact', () => {
    const r = addContact(createRung(), 'falling', 3)
    expect(r.contacts[0].type).toBe('falling')
  })

  it('accepts a name option', () => {
    const r = addContact(createRung(), 'no', 0, { name: 'SENSOR_1' })
    expect(r.contacts[0].name).toBe('SENSOR_1')
  })

  it('assigns a unique id to each contact', () => {
    let r = createRung()
    r = addContact(r, 'no', 0)
    r = addContact(r, 'no', 1)
    expect(r.contacts[0].id).not.toBe(r.contacts[1].id)
  })

  it('does not mutate the original rung (immutability)', () => {
    const original = createRung()
    addContact(original, 'no', 0)
    expect(original.contacts).toHaveLength(0)
  })

  it('throws for an invalid contact type', () => {
    expect(() => addContact(createRung(), 'bad_type', 0)).toThrow()
  })

  it('throws for a negative position', () => {
    expect(() => addContact(createRung(), 'no', -1)).toThrow()
  })

  it('throws for a non-integer position', () => {
    expect(() => addContact(createRung(), 'no', 1.5)).toThrow()
  })
})

// ── addCoil ────────────────────────────────────────────────────────────────────

describe('addCoil', () => {
  it('adds an output coil', () => {
    const r = addCoil(createRung(), 'output', 5)
    expect(r.coils).toHaveLength(1)
    expect(r.coils[0].type).toBe('output')
    expect(r.coils[0].position).toBe(5)
  })

  it('adds a set coil', () => {
    const r = addCoil(createRung(), 'set', 4)
    expect(r.coils[0].type).toBe('set')
  })

  it('adds a reset coil', () => {
    const r = addCoil(createRung(), 'reset', 4)
    expect(r.coils[0].type).toBe('reset')
  })

  it('adds a pulse coil', () => {
    const r = addCoil(createRung(), 'pulse', 4)
    expect(r.coils[0].type).toBe('pulse')
  })

  it('accepts a name option', () => {
    const r = addCoil(createRung(), 'output', 5, { name: 'VALVE_OUT' })
    expect(r.coils[0].name).toBe('VALVE_OUT')
  })

  it('assigns a unique id to each coil', () => {
    let r = createRung()
    r = addCoil(r, 'output', 5)
    r = addCoil(r, 'set', 6)
    expect(r.coils[0].id).not.toBe(r.coils[1].id)
  })

  it('does not mutate the original rung (immutability)', () => {
    const original = createRung()
    addCoil(original, 'output', 5)
    expect(original.coils).toHaveLength(0)
  })

  it('throws for an invalid coil type', () => {
    expect(() => addCoil(createRung(), 'latch', 5)).toThrow()
  })

  it('throws for a negative position', () => {
    expect(() => addCoil(createRung(), 'output', -1)).toThrow()
  })
})

// ── deleteElement ─────────────────────────────────────────────────────────────

describe('deleteElement', () => {
  it('removes a contact by id', () => {
    let r = createRung()
    r = addContact(r, 'no', 0)
    const id = r.contacts[0].id
    const r2 = deleteElement(r, id)
    expect(r2.contacts).toHaveLength(0)
  })

  it('removes a coil by id', () => {
    let r = createRung()
    r = addCoil(r, 'output', 5)
    const id = r.coils[0].id
    const r2 = deleteElement(r, id)
    expect(r2.coils).toHaveLength(0)
  })

  it('leaves other elements untouched', () => {
    let r = createRung()
    r = addContact(r, 'no', 0)
    r = addContact(r, 'nc', 1)
    const idToRemove = r.contacts[0].id
    const idToKeep = r.contacts[1].id
    const r2 = deleteElement(r, idToRemove)
    expect(r2.contacts).toHaveLength(1)
    expect(r2.contacts[0].id).toBe(idToKeep)
  })

  it('does not mutate the original rung (immutability)', () => {
    let r = createRung()
    r = addContact(r, 'no', 0)
    const id = r.contacts[0].id
    deleteElement(r, id)
    expect(r.contacts).toHaveLength(1)
  })

  it('is a no-op for an unknown id', () => {
    const r = makePopulatedRung()
    const r2 = deleteElement(r, 'nonexistent-id')
    expect(r2.contacts).toHaveLength(r.contacts.length)
    expect(r2.coils).toHaveLength(r.coils.length)
  })
})

// ── moveElement ───────────────────────────────────────────────────────────────

describe('moveElement', () => {
  it('updates the position of a contact', () => {
    let r = addContact(createRung(), 'no', 0)
    const id = r.contacts[0].id
    r = moveElement(r, id, 3)
    expect(r.contacts[0].position).toBe(3)
  })

  it('updates the position of a coil', () => {
    let r = addCoil(createRung(), 'output', 5)
    const id = r.coils[0].id
    r = moveElement(r, id, 8)
    expect(r.coils[0].position).toBe(8)
  })

  it('does not affect other elements', () => {
    let r = createRung()
    r = addContact(r, 'no', 0)
    r = addContact(r, 'nc', 2)
    const id = r.contacts[0].id
    const otherId = r.contacts[1].id
    const r2 = moveElement(r, id, 1)
    // The second contact must be unchanged
    const other = r2.contacts.find((c) => c.id === otherId)
    expect(other.position).toBe(2)
  })

  it('does not mutate the original rung (immutability)', () => {
    let r = addContact(createRung(), 'no', 0)
    const id = r.contacts[0].id
    moveElement(r, id, 3)
    expect(r.contacts[0].position).toBe(0)
  })

  it('throws for a negative newPosition', () => {
    let r = addContact(createRung(), 'no', 0)
    const id = r.contacts[0].id
    expect(() => moveElement(r, id, -1)).toThrow()
  })
})

// ── validateRung ──────────────────────────────────────────────────────────────

describe('validateRung', () => {
  it('returns ok=true for a valid rung with contact(s) left and coil right', () => {
    const r = makePopulatedRung()
    const { ok, errors } = validateRung(r)
    expect(ok).toBe(true)
    expect(errors).toHaveLength(0)
  })

  it('fails when there are no contacts (missing left-rail attachment)', () => {
    let r = createRung()
    r = addCoil(r, 'output', 5)
    const { ok, errors } = validateRung(r)
    expect(ok).toBe(false)
    expect(errors.some((e) => /contact|left rail/i.test(e))).toBe(true)
  })

  it('fails when there are no coils (missing right-rail attachment)', () => {
    let r = createRung()
    r = addContact(r, 'no', 0)
    const { ok, errors } = validateRung(r)
    expect(ok).toBe(false)
    expect(errors.some((e) => /coil|right rail/i.test(e))).toBe(true)
  })

  it('fails when two contacts share the same position (overlap)', () => {
    let r = createRung()
    r = addContact(r, 'no', 2)
    r = addContact(r, 'nc', 2) // same column — overlap
    r = addCoil(r, 'output', 5)
    const { ok, errors } = validateRung(r)
    expect(ok).toBe(false)
    expect(errors.some((e) => /overlap/i.test(e))).toBe(true)
  })

  it('fails when coil position <= max contact position (coil not rightmost)', () => {
    let r = createRung()
    r = addContact(r, 'no', 0)
    r = addContact(r, 'nc', 3)
    r = addCoil(r, 'output', 2) // coil is to the left of one contact
    const { ok, errors } = validateRung(r)
    expect(ok).toBe(false)
    expect(errors.some((e) => /coil.*right|right.*coil|not to the right/i.test(e))).toBe(true)
  })

  it('fails when coil position equals max contact position', () => {
    let r = createRung()
    r = addContact(r, 'no', 4)
    r = addCoil(r, 'output', 4) // same column — not strictly right
    const { ok, errors } = validateRung(r)
    expect(ok).toBe(false)
  })

  it('returns ok=false with an error for null input', () => {
    const { ok, errors } = validateRung(null)
    expect(ok).toBe(false)
    expect(errors.length).toBeGreaterThan(0)
  })

  it('collects multiple errors in one pass', () => {
    // No contacts AND no coils
    const { ok, errors } = validateRung(createRung())
    expect(ok).toBe(false)
    expect(errors.length).toBeGreaterThanOrEqual(2)
  })
})

// ── serialiseRung ─────────────────────────────────────────────────────────────

describe('serialiseRung', () => {
  it('returns an object with id, contacts, coils, and wires', () => {
    const doc = serialiseRung(makePopulatedRung())
    expect(doc).toHaveProperty('id')
    expect(doc).toHaveProperty('contacts')
    expect(doc).toHaveProperty('coils')
    expect(doc).toHaveProperty('wires')
  })

  it('serialises all contacts with required fields', () => {
    const r = makePopulatedRung()
    const doc = serialiseRung(r)
    for (const c of doc.contacts) {
      expect(c).toHaveProperty('id')
      expect(c).toHaveProperty('name')
      expect(c).toHaveProperty('type')
      expect(c).toHaveProperty('position')
      expect(c).toHaveProperty('negated')
    }
  })

  it('serialises all coils with required fields', () => {
    const r = makePopulatedRung()
    const doc = serialiseRung(r)
    for (const c of doc.coils) {
      expect(c).toHaveProperty('id')
      expect(c).toHaveProperty('name')
      expect(c).toHaveProperty('type')
      expect(c).toHaveProperty('position')
    }
  })

  it('produces stable output (sorted by id)', () => {
    const r = makePopulatedRung()
    const doc1 = serialiseRung(r)
    const doc2 = serialiseRung(r)
    expect(JSON.stringify(doc1)).toBe(JSON.stringify(doc2))
  })

  it('does not mutate the original rung', () => {
    const r = makePopulatedRung()
    const contactCountBefore = r.contacts.length
    serialiseRung(r)
    expect(r.contacts.length).toBe(contactCountBefore)
  })
})
