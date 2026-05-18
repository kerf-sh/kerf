"""
P&ID data model — ISA 5.1 instrument symbols, pipes, valves, vessels, tags.

Key classes
-----------
PIDComponent   Base class for all P&ID components.
Vessel         Storage / process vessel (drum, column, tank, reactor…).
Pump           Centrifugal / positive-displacement pump.
HeatExchanger  Shell-and-tube / plate-and-frame HX.
Valve          Gate / globe / ball / check / control valve.
Instrument     ISA 5.1 field instrument (transmitter, controller, indicator…).
Nozzle         Equipment nozzle — named connection point with a 3D position.
Pipe           Pipe segment connecting two nozzle endpoints.
PIDDiagram     Container: components + pipes + ISA tag registry.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ValveType(str, Enum):
    GATE = "gate"
    GLOBE = "globe"
    BALL = "ball"
    CHECK = "check"
    BUTTERFLY = "butterfly"
    CONTROL = "control"
    RELIEF = "relief"
    NEEDLE = "needle"


class InstrumentFunction(str, Enum):
    """ISA 5.1 second-letter codes (simplified subset)."""
    INDICATOR = "I"
    TRANSMITTER = "T"
    CONTROLLER = "C"
    RECORDER = "R"
    ALARM = "A"
    SWITCH = "S"
    ELEMENT = "E"
    VALVE = "V"


class InstrumentVariable(str, Enum):
    """ISA 5.1 first-letter codes (measured variable)."""
    FLOW = "F"
    LEVEL = "L"
    PRESSURE = "P"
    TEMPERATURE = "T"
    ANALYSIS = "A"
    DENSITY = "D"
    VOLTAGE = "E"
    SPEED = "S"


class PipeSchedule(str, Enum):
    SCH_40 = "40"
    SCH_80 = "80"
    SCH_160 = "160"
    XS = "XS"
    XXS = "XXS"


class FlowDirection(str, Enum):
    FORWARD = "forward"
    REVERSE = "reverse"
    BIDIRECTIONAL = "bidirectional"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Point3:
    x: float
    y: float
    z: float

    def __add__(self, other: "Point3") -> "Point3":
        return Point3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Point3") -> "Point3":
        return Point3(self.x - other.x, self.y - other.y, self.z - other.z)

    def distance_to(self, other: "Point3") -> float:
        import math
        return math.sqrt(
            (self.x - other.x) ** 2
            + (self.y - other.y) ** 2
            + (self.z - other.z) ** 2
        )

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


ORIGIN = Point3(0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Nozzle
# ---------------------------------------------------------------------------

@dataclass
class Nozzle:
    """
    A named connection point on a piece of equipment.

    Attributes
    ----------
    tag         Short identifier within the equipment (e.g. 'N1', 'inlet', 'outlet').
    position    3D position in the plant coordinate system (metres).
    diameter_mm Nominal pipe diameter (mm).
    schedule    Pipe schedule (default SCH_40).
    connected_to  Tag of the Pipe connected here (None if free).
    """

    tag: str
    position: Point3 = field(default_factory=lambda: ORIGIN)
    diameter_mm: float = 50.0
    schedule: PipeSchedule = PipeSchedule.SCH_40
    connected_to: Optional[str] = None  # Pipe.id


# ---------------------------------------------------------------------------
# Base component
# ---------------------------------------------------------------------------

class PIDComponent:
    """Abstract base for all P&ID equipment items."""

    def __init__(
        self,
        tag: str,
        description: str = "",
        position: Point3 = ORIGIN,
    ) -> None:
        self.id: str = str(uuid.uuid4())
        self.tag = tag.upper()
        self.description = description
        self.position = position
        self.nozzles: dict[str, Nozzle] = {}

    def add_nozzle(self, nozzle: Nozzle) -> None:
        self.nozzles[nozzle.tag] = nozzle

    def get_nozzle(self, tag: str) -> Nozzle:
        try:
            return self.nozzles[tag]
        except KeyError:
            raise KeyError(f"Nozzle '{tag}' not found on {self.tag}")

    def nozzle_position(self, tag: str) -> Point3:
        return self.get_nozzle(tag).position

    def __repr__(self) -> str:
        return f"{type(self).__name__}(tag={self.tag!r})"


# ---------------------------------------------------------------------------
# Equipment types
# ---------------------------------------------------------------------------

class Vessel(PIDComponent):
    """
    Pressure vessel: storage drum, column, reactor, tank.

    Parameters
    ----------
    tag             ISA tag (e.g. 'V-101').
    vessel_type     'drum' | 'column' | 'tank' | 'reactor' | 'separator'.
    diameter_m      Shell diameter (m).
    length_m        Shell length (m).
    design_pressure_barg  Design pressure (barg).
    design_temp_c   Design temperature (°C).
    """

    def __init__(
        self,
        tag: str,
        vessel_type: str = "drum",
        diameter_m: float = 1.0,
        length_m: float = 2.0,
        design_pressure_barg: float = 10.0,
        design_temp_c: float = 120.0,
        description: str = "",
        position: Point3 = ORIGIN,
    ) -> None:
        super().__init__(tag, description, position)
        self.vessel_type = vessel_type
        self.diameter_m = diameter_m
        self.length_m = length_m
        self.design_pressure_barg = design_pressure_barg
        self.design_temp_c = design_temp_c

        # Default nozzles: top inlet + bottom outlet
        self._add_default_nozzles()

    def _add_default_nozzles(self) -> None:
        r = self.diameter_m / 2.0
        top = Point3(self.position.x, self.position.y, self.position.z + self.length_m)
        bot = Point3(self.position.x, self.position.y, self.position.z)
        self.add_nozzle(Nozzle("inlet", Point3(top.x, top.y, top.z)))
        self.add_nozzle(Nozzle("outlet", Point3(bot.x, bot.y, bot.z)))


class Pump(PIDComponent):
    """
    Centrifugal or positive-displacement pump.

    Parameters
    ----------
    tag           ISA tag (e.g. 'P-101A').
    pump_type     'centrifugal' | 'pos_disp' | 'gear' | 'diaphragm'.
    flow_m3h      Design flow rate (m³/h).
    head_m        Design head (m).
    motor_kw      Motor power (kW).
    """

    def __init__(
        self,
        tag: str,
        pump_type: str = "centrifugal",
        flow_m3h: float = 10.0,
        head_m: float = 30.0,
        motor_kw: float = 5.0,
        description: str = "",
        position: Point3 = ORIGIN,
    ) -> None:
        super().__init__(tag, description, position)
        self.pump_type = pump_type
        self.flow_m3h = flow_m3h
        self.head_m = head_m
        self.motor_kw = motor_kw

        # suction and discharge nozzles
        self.add_nozzle(Nozzle("suction", Point3(position.x - 0.5, position.y, position.z)))
        self.add_nozzle(Nozzle("discharge", Point3(position.x + 0.5, position.y, position.z)))


class HeatExchanger(PIDComponent):
    """
    Shell-and-tube or plate heat exchanger.

    Parameters
    ----------
    tag           ISA tag (e.g. 'E-101').
    hx_type       'shell_tube' | 'plate' | 'double_pipe' | 'air_cooler'.
    duty_kw       Heat duty (kW).
    area_m2       Heat-transfer area (m²).
    """

    def __init__(
        self,
        tag: str,
        hx_type: str = "shell_tube",
        duty_kw: float = 500.0,
        area_m2: float = 20.0,
        description: str = "",
        position: Point3 = ORIGIN,
    ) -> None:
        super().__init__(tag, description, position)
        self.hx_type = hx_type
        self.duty_kw = duty_kw
        self.area_m2 = area_m2

        # shell side: inlet/outlet; tube side: inlet/outlet
        self.add_nozzle(Nozzle("shell_inlet",  Point3(position.x - 1.0, position.y, position.z + 0.3)))
        self.add_nozzle(Nozzle("shell_outlet", Point3(position.x + 1.0, position.y, position.z + 0.3)))
        self.add_nozzle(Nozzle("tube_inlet",   Point3(position.x - 1.0, position.y, position.z - 0.3)))
        self.add_nozzle(Nozzle("tube_outlet",  Point3(position.x + 1.0, position.y, position.z - 0.3)))


class Valve(PIDComponent):
    """
    Process valve.

    Parameters
    ----------
    tag         ISA tag (e.g. 'XV-101').
    valve_type  ValveType enum.
    diameter_mm Nominal bore (mm).
    cv          Flow coefficient (US gallons/min at 1 psi dP).
    """

    def __init__(
        self,
        tag: str,
        valve_type: ValveType = ValveType.GATE,
        diameter_mm: float = 50.0,
        cv: float = 100.0,
        description: str = "",
        position: Point3 = ORIGIN,
    ) -> None:
        super().__init__(tag, description, position)
        self.valve_type = valve_type
        self.diameter_mm = diameter_mm
        self.cv = cv

        self.add_nozzle(Nozzle("inlet",  Point3(position.x - 0.15, position.y, position.z), diameter_mm))
        self.add_nozzle(Nozzle("outlet", Point3(position.x + 0.15, position.y, position.z), diameter_mm))


class Instrument(PIDComponent):
    """
    ISA 5.1 field instrument.

    The ISA tag has the form  <variable><function>[-<loop>]
    e.g. FT-101 (flow transmitter loop 101), PIC-202 (pressure indicating controller).

    Parameters
    ----------
    tag           Full ISA tag string (e.g. 'FT-101').
    variable      InstrumentVariable (first letter).
    function      InstrumentFunction (second/further letters).
    loop_number   Integer loop number.
    """

    _TAG_RE = re.compile(
        r"^([A-Z])([A-Z]+)-?(\d+)$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        tag: str,
        variable: Optional[InstrumentVariable] = None,
        function: Optional[InstrumentFunction] = None,
        loop_number: Optional[int] = None,
        description: str = "",
        position: Point3 = ORIGIN,
    ) -> None:
        super().__init__(tag, description, position)

        # Parse tag if variable/function not supplied
        m = self._TAG_RE.match(tag.upper().replace("-", ""))
        if m and variable is None:
            try:
                variable = InstrumentVariable(m.group(1).upper())
            except ValueError:
                pass
        if m and function is None:
            try:
                function = InstrumentFunction(m.group(2)[0].upper())
            except ValueError:
                pass
        if loop_number is None and m:
            try:
                loop_number = int(m.group(3))
            except (ValueError, IndexError):
                pass

        self.variable = variable
        self.function = function
        self.loop_number = loop_number


# ---------------------------------------------------------------------------
# Pipe
# ---------------------------------------------------------------------------

@dataclass
class Pipe:
    """
    A pipe segment connecting two nozzle endpoints.

    Attributes
    ----------
    id              UUID string.
    tag             Pipe line number (e.g. '4"-CS-101-A1').
    from_equipment  Equipment tag.
    from_nozzle     Nozzle tag on from_equipment.
    to_equipment    Equipment tag.
    to_nozzle       Nozzle tag on to_equipment.
    diameter_mm     Nominal diameter (mm).
    schedule        Pipe schedule.
    fluid           Fluid service (e.g. 'water', 'steam', 'crude').
    insulated       Whether the pipe is insulated.
    flow_direction  Flow direction along the segment.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tag: str = ""
    from_equipment: str = ""
    from_nozzle: str = ""
    to_equipment: str = ""
    to_nozzle: str = ""
    diameter_mm: float = 50.0
    schedule: PipeSchedule = PipeSchedule.SCH_40
    fluid: str = "process"
    insulated: bool = False
    flow_direction: FlowDirection = FlowDirection.FORWARD

    def line_designation(self) -> str:
        """Return a standard line designation string."""
        dn = f'{int(self.diameter_mm)}'
        sched = self.schedule.value
        return self.tag or f'{dn}"-{self.fluid.upper()[:2]}-{sched}'


# ---------------------------------------------------------------------------
# PIDDiagram
# ---------------------------------------------------------------------------

class PIDDiagram:
    """
    Container for all P&ID components and pipe segments.

    Attributes
    ----------
    name        Drawing title.
    components  Dict of tag → PIDComponent.
    pipes       Dict of id → Pipe.
    """

    def __init__(self, name: str = "P&ID-001") -> None:
        self.name = name
        self.components: dict[str, PIDComponent] = {}
        self.pipes: dict[str, Pipe] = {}

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------

    def add_component(self, comp: PIDComponent) -> PIDComponent:
        if comp.tag in self.components:
            raise ValueError(f"Component tag '{comp.tag}' already exists in diagram")
        self.components[comp.tag] = comp
        return comp

    def add_pipe(self, pipe: Pipe) -> Pipe:
        # Validate endpoints exist
        if pipe.from_equipment not in self.components:
            raise ValueError(
                f"from_equipment '{pipe.from_equipment}' not found in diagram"
            )
        if pipe.to_equipment not in self.components:
            raise ValueError(
                f"to_equipment '{pipe.to_equipment}' not found in diagram"
            )
        # Validate nozzles exist
        self.components[pipe.from_equipment].get_nozzle(pipe.from_nozzle)
        self.components[pipe.to_equipment].get_nozzle(pipe.to_nozzle)

        # Mark nozzles as occupied
        self.components[pipe.from_equipment].nozzles[pipe.from_nozzle].connected_to = pipe.id
        self.components[pipe.to_equipment].nozzles[pipe.to_nozzle].connected_to = pipe.id

        self.pipes[pipe.id] = pipe
        return pipe

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_component(self, tag: str) -> PIDComponent:
        try:
            return self.components[tag.upper()]
        except KeyError:
            raise KeyError(f"Component '{tag}' not found in diagram '{self.name}'")

    def connected_pipes(self, equipment_tag: str) -> list[Pipe]:
        """Return all pipes connected to a given equipment item."""
        tag = equipment_tag.upper()
        return [
            p for p in self.pipes.values()
            if p.from_equipment == tag or p.to_equipment == tag
        ]

    def summary(self) -> dict:
        """Return a summary dictionary suitable for LLM tool responses."""
        return {
            "name": self.name,
            "component_count": len(self.components),
            "pipe_count": len(self.pipes),
            "components": [
                {
                    "tag": c.tag,
                    "type": type(c).__name__,
                    "nozzle_count": len(c.nozzles),
                }
                for c in self.components.values()
            ],
            "pipes": [
                {
                    "tag": p.tag,
                    "from": f"{p.from_equipment}.{p.from_nozzle}",
                    "to": f"{p.to_equipment}.{p.to_nozzle}",
                    "diameter_mm": p.diameter_mm,
                }
                for p in self.pipes.values()
            ],
        }
