# kerf-piping · P&ID / plant design

P&ID (Piping and Instrumentation Diagram) data model, isometric routing, and
DXF/SVG export for process plant design per ISA 5.1.

## Data model (`pid.py`)

### Equipment classes

| Class           | Tag pattern  | Key attributes                         |
|-----------------|--------------|----------------------------------------|
| `Vessel`        | V-101        | vessel_type, diameter_m, length_m      |
| `Pump`          | P-101        | pump_type, flow_m3h, head_m, motor_kw  |
| `HeatExchanger` | E-101        | hx_type, duty_kw, area_m2              |
| `Valve`         | XV-101       | valve_type (ValveType), diameter_mm    |
| `Instrument`    | FT-101       | variable, function, loop_number        |

Each equipment item has named `Nozzle` objects (connection points with 3D position).

### `PIDDiagram`

Container for components and pipes.

```python
from kerf_piping.pid import PIDDiagram, Pump, Vessel, HeatExchanger, Pipe

diag = PIDDiagram("P&ID-001")
pump  = diag.add_component(Pump("P-101"))
tank  = diag.add_component(Vessel("V-101"))
hx    = diag.add_component(HeatExchanger("E-101"))

diag.add_pipe(Pipe(
    tag="2\"-PR-001",
    from_equipment="P-101", from_nozzle="discharge",
    to_equipment="V-101",   to_nozzle="inlet",
    diameter_mm=50.0, fluid="water",
))
print(diag.summary())
```

## Isometric routing (`isometric.py`)

Routes pipe between two 3D nozzle positions using orthogonal (axis-aligned)
segments with standard long-radius (1.5D) ASME B16.9 elbows.

```python
from kerf_piping.pid import Point3
from kerf_piping.isometric import route_orthogonal, count_fittings, pipe_length

segments = route_orthogonal(
    Point3(0, 0, 1),    # pump discharge
    Point3(5, 0, 4),    # vessel inlet
    prefer_axis="Z",    # rise first, then run
)
fc = count_fittings(segments)
print(f"Elbows: {fc.elbows_90}, Pipe length: {pipe_length(segments):.2f} m")
```

### `route_loop(waypoints, ...)` — multi-leg routing

```python
from kerf_piping.isometric import route_loop, summarise_route

waypoints = [
    Point3(0, 0, 1),   # pump discharge
    Point3(5, 0, 4),   # vessel inlet → outlet
    Point3(10, 0, 2),  # HX shell inlet
]
legs = route_loop(waypoints)
summary = summarise_route(legs)
print(summary.as_dict())
```

## P&ID text import (`tools.py` / `piping_import_pid`)

Parse a compact text specification:

```
VESSEL V-101 type=drum d=1.2 L=3.0
PUMP   P-101 type=centrifugal flow=15.0 head=40.0
HX     E-101 type=shell_tube duty=750.0
PIPE   L-001 P-101.discharge V-101.inlet   dn=50 sched=40 fluid=water
PIPE   L-002 V-101.outlet    E-101.shell_inlet dn=50 fluid=water
```

## SVG / DXF export (`symbols.py`)

```python
from kerf_piping.symbols import pid_diagram_svg, pid_diagram_dxf

# SVG (no deps)
svg = pid_diagram_svg(diag, width=1200, height=400)
with open("pid.svg", "w") as f:
    f.write(svg)

# DXF (requires ezdxf: pip install kerf-piping[dxf])
doc = pid_diagram_dxf(diag)
doc.saveas("pid.dxf")
```

## LLM tools

| Tool                      | Description                                          |
|---------------------------|------------------------------------------------------|
| `piping_route_isometric`  | Route a pipe and return elbow/tee counts + segments  |
| `piping_import_pid`       | Parse text P&ID spec into the data model             |
| `piping_export_svg`       | Parse spec + return SVG string                       |

## ISA 5.1 tag convention

- First letter: measured variable (F=Flow, L=Level, P=Pressure, T=Temperature, …)
- Second letter(s): function (T=Transmitter, I=Indicator, C=Controller, …)
- Loop number: three-digit integer

Example: `FIC-101` = Flow Indicating Controller, loop 101.
