# Shove Router Algorithm

## Overview

The shove router implements KiCad-style push-pull routing. When a new trace being routed would overlap an existing trace on the same layer with a different net, the existing trace is pushed perpendicular by `clearance_mm` to resolve the conflict.

## Algorithm

### Core Loop
1. Walk each segment of the new trace being routed
2. For each new segment, find all intersecting existing same-layer traces with different nets
3. For each conflict, compute the perpendicular shove vector (90° to the existing trace direction)
4. Apply the shove to the conflicting trace by moving its vertices perpendicular by `clearance_mm`
5. If shoving causes secondary conflicts, recurse (capped at 3 levels)
6. Unresolvable conflicts are added to `conflicts_unresolved`

### Key Helpers

- `segmentMinDistance(seg1, seg2)` — Returns minimum distance between two line segments in mm
- `shoveSegment(seg, perpendicular_vector, amount_mm)` — Returns new segment moved perpendicular by amount

### Conflict Resolution Rules
- Same-net intersections are legal T-junctions and are NOT shoved
- Different-layer traces never conflict
- Shoving preserves net_id and endpoints
- Recursion depth capped at 3 levels to prevent infinite loops

## Examples

### Single Push
```
Existing:  Trace t1 (net1) on 'top' from (0,5) to (10,5)
New:      Route from (5,0) to (5,10) on 'top'
Clearance: 0.25mm

Result: t1 is shoved upward by 0.25mm to (0,5.25)-(10,5.25)
shoved_traces: ['t1']
conflicts_resolved: 1
```

### Cascading 3-Trace Shove
```
Layer: 'top'
Clearance: 0.25mm

Initial state:
  t1 (net1): (0,5) → (10,5)
  t2 (net2): (0,6) → (10,6)
  t3 (net3): (0,7) → (10,7)

New trace: (5,5.5) → (5,5.5) [zero-length point, conflicts with all three]

Resolution:
  Level 0: New trace conflicts with t1 → shove t1 up by 0.25mm
  Level 1: t1 shoved → now conflicts with t2 → shove t2 up by 0.25mm
  Level 2: t2 shoved → now conflicts with t3 → shove t3 up by 0.25mm
  Level 3: Max depth reached, recursion stops

Final state:
  t1: (0,5.25) → (10,5.25)
  t2: (0,6.25) → (10,6.25)
  t3: (0,7.25) → (10,7.25)

shoved_traces: ['t1', 't2', 't3']
conflicts_resolved: 3
```

## Usage

```javascript
import { routeWithShove } from './shoveRouter.js'

const result = routeWithShove(
  circuit_json,       // CircuitJSON board object
  'top',              // layer name
  [[x1,y1], [x2,y2]], // new trace points
  0.25                // clearance in mm
)
// Returns: { circuit_json, shoved_traces:[], conflicts_resolved:N, conflicts_unresolved:N }
```

## Python API

```python
from tools.shove_router import route_with_shove

result = route_with_shove(
    circuit_json={'pcb_board': {...}},  # CircuitJSON
    layer='top',
    points=[[x1,y1], [x2,y2]],
    clearance_mm=0.25
)
```
