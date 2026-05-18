"""
kerf_plc.plcopen — PLCopen XML (IEC TR 61131-10) reader/writer.

Quick start::

    from kerf_plc.plcopen import load, dump, loads, dumps, Project

    project = load("my_program.plc")
    xml_text = dumps(project)
"""
from .ast import (
    Body,
    Coil,
    Configuration,
    Contact,
    ContentHeader,
    FBDBody,
    FBInstance,
    ILBody,
    Instances,
    LDBody,
    LeftPowerRail,
    POU,
    PlcopenParseError,
    Position,
    ProgramInstance,
    Project,
    Resource,
    RightPowerRail,
    Rung,
    STBody,
    TaskConfig,
    Types,
    VarBlock,
    Variable,
)
from .reader import load, loads
from .writer import dump, dumps

__all__ = [
    # AST types
    "Body",
    "Coil",
    "Configuration",
    "Contact",
    "ContentHeader",
    "FBDBody",
    "FBInstance",
    "ILBody",
    "Instances",
    "LDBody",
    "LeftPowerRail",
    "POU",
    "PlcopenParseError",
    "Position",
    "ProgramInstance",
    "Project",
    "Resource",
    "RightPowerRail",
    "Rung",
    "STBody",
    "TaskConfig",
    "Types",
    "VarBlock",
    "Variable",
    # IO
    "load",
    "loads",
    "dump",
    "dumps",
]
