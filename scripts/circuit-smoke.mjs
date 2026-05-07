// Smoke test: 3-resistor circuit through @tscircuit/core. Uses JSX intrinsic
// (lowercase) tags rather than the named class exports — tscircuit registers
// `<resistor>`, `<board>`, etc. via React.createElement strings. The class
// exports (Board, Resistor) are reserved for React class JSX, but our worker
// uses sucrase + lowercase tags, mirroring tscircuit's CLI behaviour.
import { Circuit } from '@tscircuit/core'
import * as React from 'react'

const board = React.createElement('board', { width: '20mm', height: '20mm' },
  React.createElement('resistor', { name: 'R1', resistance: '10k', footprint: '0402', pcbX: -5, pcbY: 0, schX: -3 }),
  React.createElement('resistor', { name: 'R2', resistance: '10k', footprint: '0402', pcbX: 0,  pcbY: 0, schX: 0  }),
  React.createElement('resistor', { name: 'R3', resistance: '10k', footprint: '0402', pcbX: 5,  pcbY: 0, schX: 3  }),
  React.createElement('trace', { from: '.R1 > .pin2', to: '.R2 > .pin1' }),
  React.createElement('trace', { from: '.R2 > .pin2', to: '.R3 > .pin1' }),
)

const circuit = new Circuit()
circuit.add(board)
await circuit.renderUntilSettled()
const json = circuit.getCircuitJson()

const counts = {}
const components = []
const sourceTraces = []
for (const el of json) {
  counts[el.type] = (counts[el.type] || 0) + 1
  if (el.type === 'source_component') components.push(el.name)
  if (el.type === 'source_trace') sourceTraces.push(el.source_trace_id)
}
console.log('total elements:', json.length)
console.log('source_components:', components)
console.log('source_traces:', sourceTraces.length)
console.log('schematic_components:', counts.schematic_component || 0)
console.log('pcb_components:', counts.pcb_component || 0)
console.log('cad_components:', counts.cad_component || 0)
console.log('---')
console.log('PASS 3 components:', components.length === 3 ? 'YES' : `NO (${components.length})`)
console.log('PASS >=2 traces:',  sourceTraces.length >= 2 ? 'YES' : `NO (${sourceTraces.length})`)
