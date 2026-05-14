# Widget Bracket

Parametric L-bracket with 4 mounting holes.

## Files

- `main.jscad` — JSCAD model using @jscad/modeling (CSG booleans)
- `bracket.sketch` — L-profile sketch (50×40mm outline, 3mm thickness)
- `bracket.feature` — Pad + 4 holes + fillets (OCCT B-rep)
- `drawing.drawing` — A3 landscape: front, right, iso views
- `params.equations` — Shared parameters: wall_thickness, hole_diameter, mount_spacing

## Parameters

| Name | Default | Description |
|------|---------|-------------|
| wall_thickness | 3 mm | Wall thickness |
| hole_diameter | 4 mm | Mounting hole diameter |
| mount_spacing | 20 mm | Hole spacing along base |
