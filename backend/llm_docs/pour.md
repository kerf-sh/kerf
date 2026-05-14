# Copper Pours (Ground Planes / Filled Zones)

A copper pour — also called a filled zone or ground plane — is a solid copper region on a layer connected to a specific net (typically GND or a power net). The pour fills its bounding polygon minus clearance gaps around traces and pads not on that net. Pads belonging to the pour's net receive thermal-relief spokes (spoke connections that reduce heat sinking during soldering).

**When to use copper pours:**
- GND reference plane for signal integrity and EMI shielding.
- Power distribution (wide low-resistance copper for VCC/3V3/5V).
- Heat spreading from power components.
- Filling dead copper to meet PCB fab minimums.

## Data model

Copper pours are stored in the `copper_pours` array of the CircuitJSON board (added alongside the existing `traces` and `pcb_component` entries — backward-compatible).

```jsonc
{
  "type": "copper_pour",
  "polygon": [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 40}, {"x": 0, "y": 40}],
  "layer": "top_copper",
  "net_id": "GND",
  "clearance_mm": 0.25,
  "thermal_relief": {
    "gap": 0.25,
    "spoke_width": 0.5,
    "spoke_count": 4
  },
  "min_thickness_mm": 0.2,
  "priority": 0
}
```

- `polygon`: closed boundary; minimum 3 points.
- `layer`: `top_copper` | `bottom_copper` | `inner_1` | `inner_2`.
- `net_id`: net that the pour is connected to.
- `clearance_mm`: copper-to-copper clearance around obstacles not on the pour net. Default 0.25.
- `thermal_relief`: spoke parameters for same-net pads. `spoke_count` is typically 4.
- `min_thickness_mm`: strips narrower than this are removed from the fill. Default 0.2.
- `priority`: higher-priority pours win at overlaps. Default 0.

## Fill computation

The fill geometry is computed by the pyworker sidecar:

```
POST /compute-pour-fill
Body: {"pour": <pour_object>, "board_state": {"traces": [...], "pads": [...]}}
Returns: {"filled_polygon": {"outer": [[x,y],...], "holes": [...]}, "thermal_spokes": [...]}
```

The fill is rebuilt whenever traces/pads/nets change. The frontend triggers this via a `useEffect` watching the CircuitJSON.

## Tools

### `add_copper_pour`

Add a new copper pour zone to the board.

```json
{
  "file_id": "my-board.circuit.tsx",
  "pour": {
    "polygon": [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 40}, {"x": 0, "y": 40}],
    "layer": "top_copper",
    "net_id": "GND",
    "clearance_mm": 0.25,
    "thermal_relief": {"gap": 0.25, "spoke_width": 0.5, "spoke_count": 4}
  }
}
```

### `delete_copper_pour`

Remove a pour by index or by net + layer.

```json
{"file_id": "my-board.circuit.tsx", "pour_index": 0}
// or
{"file_id": "my-board.circuit.tsx", "net_id": "GND", "layer": "top_copper"}
```

### `set_pour_net`

Reassign a pour to a different net (e.g. change from GND to VCC). Triggers a fill rebuild.

```json
{
  "file_id": "my-board.circuit.tsx",
  "pour_index": 0,
  "net_id": "VCC"
}
```

### `set_pour_clearance`

Update the copper-to-copper clearance of an existing pour. Larger clearance pulls copper further from non-net obstacles; smaller clearance fills more tightly.

```json
{
  "file_id": "my-board.circuit.tsx",
  "pour_index": 0,
  "clearance_mm": 0.4
}
```

- `pour_index`: zero-based index in `copper_pours`.
- `clearance_mm`: non-negative number in mm. Typical range 0.1 – 1.0. Default 0.25.

---

## Worked examples

### Example 1 — Full-board GND pour on top copper

```json
{
  "tool": "add_copper_pour",
  "args": {
    "file_id": "my-board.circuit.tsx",
    "pour": {
      "polygon": [{"x": 0, "y": 0}, {"x": 80, "y": 0}, {"x": 80, "y": 60}, {"x": 0, "y": 60}],
      "layer": "top_copper",
      "net_id": "GND",
      "clearance_mm": 0.25,
      "thermal_relief": {"gap": 0.25, "spoke_width": 0.5, "spoke_count": 4},
      "min_thickness_mm": 0.2,
      "priority": 0
    }
  }
}
```

Then call `POST /compute-pour-fill` with the returned pour + the current `board_state` (traces and pads). The response `filled_polygon` can be rendered directly as an SVG even-odd path.

### Example 2 — Tighten clearance on an existing pour

The board has a GND pour at index 0 but it is leaving too much dead copper around signal traces. Reduce clearance from 0.25 to 0.15 mm:

```json
{
  "tool": "set_pour_clearance",
  "args": {
    "file_id": "my-board.circuit.tsx",
    "pour_index": 0,
    "clearance_mm": 0.15
  }
}
```

After the tool confirms `"updated": true`, trigger `POST /compute-pour-fill` to get updated geometry.

## Frontend PourTool

In `PCBView.jsx`, the `PourTool` lets users click polygon vertices, close the polygon (double-click near first vertex when ≥3 vertices exist), then confirm the net and layer via a dialog. The committed pour is rendered as a semi-transparent filled polygon (red for top copper, blue for bottom copper) with an even-odd SVG path that shows holes.
