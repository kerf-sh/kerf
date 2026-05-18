"""
kerf_plc.plcopen.ast — PLCopen XML (IEC TR 61131-10) in-memory AST.

All types are plain dataclasses; no external dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PlcopenParseError(Exception):
    """Raised when PLCopen XML is structurally invalid or semantically wrong."""


# ---------------------------------------------------------------------------
# LD body elements
# ---------------------------------------------------------------------------

@dataclass
class LocalId:
    """A numeric local-id used for wire connections inside an LD body."""
    value: int


@dataclass
class Position:
    x: int
    y: int


@dataclass
class LeftPowerRail:
    local_id: int
    position: Optional[Position] = None


@dataclass
class RightPowerRail:
    local_id: int
    position: Optional[Position] = None


@dataclass
class Contact:
    local_id: int
    variable: str
    negated: bool = False
    position: Optional[Position] = None


@dataclass
class Coil:
    local_id: int
    variable: str
    negated: bool = False
    position: Optional[Position] = None


@dataclass
class FBInstance:
    """A function-block instance inside an LD rung."""
    local_id: int
    type_name: str
    instance_name: str
    position: Optional[Position] = None


@dataclass
class Rung:
    """One rung of a Ladder Diagram body."""
    left_power_rail: Optional[LeftPowerRail] = None
    right_power_rail: Optional[RightPowerRail] = None
    contacts: list[Contact] = field(default_factory=list)
    coils: list[Coil] = field(default_factory=list)
    fb_instances: list[FBInstance] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Body variants
# ---------------------------------------------------------------------------

@dataclass
class LDBody:
    rungs: list[Rung] = field(default_factory=list)


@dataclass
class STBody:
    text: str = ""


@dataclass
class FBDBody:
    """Placeholder — full FBD AST is out of scope for T-220."""
    raw_xml: str = ""


@dataclass
class ILBody:
    text: str = ""


Body = LDBody | STBody | FBDBody | ILBody


# ---------------------------------------------------------------------------
# Variable declarations
# ---------------------------------------------------------------------------

@dataclass
class Variable:
    name: str
    type_name: str
    initial_value: Optional[str] = None


@dataclass
class VarBlock:
    """One VAR / VAR_INPUT / VAR_OUTPUT / VAR_IN_OUT block."""
    kind: Literal["local", "input", "output", "inOut", "external", "global"] = "local"
    variables: list[Variable] = field(default_factory=list)


# ---------------------------------------------------------------------------
# POU
# ---------------------------------------------------------------------------

PouType = Literal["function", "functionBlock", "program"]


@dataclass
class POU:
    name: str
    pou_type: PouType
    var_blocks: list[VarBlock] = field(default_factory=list)
    body: Optional[Body] = None


# ---------------------------------------------------------------------------
# Types section
# ---------------------------------------------------------------------------

@dataclass
class Types:
    pous: list[POU] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Instances section (resources / tasks)
# ---------------------------------------------------------------------------

@dataclass
class TaskConfig:
    name: str
    interval: Optional[str] = None
    priority: int = 0


@dataclass
class ProgramInstance:
    name: str
    type_name: str
    task_name: Optional[str] = None


@dataclass
class Resource:
    name: str
    type_name: str = "PLC"
    tasks: list[TaskConfig] = field(default_factory=list)
    program_instances: list[ProgramInstance] = field(default_factory=list)


@dataclass
class Configuration:
    name: str
    resources: list[Resource] = field(default_factory=list)


@dataclass
class Instances:
    configurations: list[Configuration] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Content header
# ---------------------------------------------------------------------------

@dataclass
class ContentHeader:
    name: str = ""
    version: str = "1.0"
    product_name: str = "Kerf"
    product_version: str = "1.0"
    product_release: str = "1.0"
    creation_date_time: str = ""
    modification_date_time: str = ""
    author: str = ""
    organization: str = ""
    language: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# Root project
# ---------------------------------------------------------------------------

@dataclass
class Project:
    content_header: ContentHeader = field(default_factory=ContentHeader)
    types: Types = field(default_factory=Types)
    instances: Instances = field(default_factory=Instances)
