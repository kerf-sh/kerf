# Via Stitching & Teardrops

Tools for adding KiCad-style via stitching patterns and teardrop fillets to CircuitJSON boards.

## add_via_stitching

Add a pattern of vias around a copper pour or board edge for shielding, impedance control, or thermal relief.

### Input Schema

```json
{
  "circuit_json": "<CircuitJSON board>",
  "pour_id_or_polygon": "<string: pour_id | array: polygon points>",
  "pitch_mm": 5.0,
  "net_id": "GND",
  "strategy": "grid" | "perimeter" | "hex",
  "via_spec": {
    "diameter": 0.8,
    "drill": 0.4
  },
  "edge_offset_mm": 0
}
```

### Output Schema

```json
{
  "circuit_json": "<updated CircuitJSON with via_stitching array>"
}
```

### CircuitJSON Shape

Added to `board.via_stitching`:

```json
{
  "pour_id": "pour1",
  "vias": [{ "x": 1.2, "y": 3.4, "net_id": "GND", "diameter": 0.8, "drill": 0.4 }],
  "strategy": "grid",
  "pitch_mm": 5.0
}
```

---

## apply_teardrops

Apply teardrop fillets to pad/via - trace connections to reduce solder starvation and improve manufacturability.

### Input Schema

```json
{
  "circuit_json": "<CircuitJSON board>",
  "radius_factor": 1.5
}
```

### Output Schema

```json
{
  "circuit_json": "<updated CircuitJSON with teardrops array>"
}
```

### CircuitJSON Shape

Added to `board.teardrops`:

```json
{
  "pad_id_or_via_id": "pad1",
  "trace_id": "trace_a1b2c3d4",
  "radius_factor": 1.5,
  "path": [{ "x": 10.0, "y": 5.0 }, { "x": 11.5, "y": 5.0 }, { "x": 8.5, "y": 5.0 }]
}
```

---

## remove_via_stitching

Remove via stitching from a copper pour by pour_id.

### Input Schema

```json
{
  "circuit_json": "<CircuitJSON board>",
  "pour_id": "pour1"
}
```

---

## Example 1: GND Stitching Around Board Edge

```python
# Add perimeter stitching around entire board at 5mm pitch
circuit = {
    "pcb_board": {
        "width": 100,
        "height": 80,
        "copper_pour": [{
            "pour_id": "board_outline",
            "polygon": [
                {"x": 0, "y": 0},
                {"x": 100, "y": 0},
                {"x": 100, "y": 80},
                {"x": 0, "y": 80}
            ],
            "layer": "top_copper",
            "net_id": "GND"
        }]
    }
}

result = await add_via_stitching(
    circuit_json=circuit,
    pour_id_or_polygon="board_outline",
    pitch_mm=5.0,
    net_id="GND",
    strategy="perimeter",
    via_spec={"diameter": 0.8, "drill": 0.4},
    edge_offset_mm=1.0
)
# result.circuit_json.pcb_board.via_stitching[0].vias
# → [{x: 1.0, y: 0}, {x: 1.0, y: 5.0}, ...]
```

## Example 2: Teardrops on Signal Traces

```python
# Apply teardrops to all GND pad-trace connections
circuit = {
    "pcb_board": {
        "width": 50,
        "height": 50,
        "pcb_trace": [{
            "pcb_trace_id": "trace_1",
            "net_id": "GND",
            "route": [{"x": 10, "y": 10}, {"x": 40, "y": 10}],
            "width": 0.3
        }],
        "pcb_pad": [{
            "pcb_pad_id": "pad_1",
            "net_id": "GND",
            "x": 25,
            "y": 10,
            "width": 1.6,
            "height": 1.6
        }]
    }
}

result = await apply_teardrops(
    circuit_json=circuit,
    radius_factor=1.5
)
# result.circuit_json.pcb_board.teardrops[0].path
# → [{"x": 24.775, "y": 10.15}, {"x": 25, "y": 10}, {"x": 25.225, "y": 9.85}]
```