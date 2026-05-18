"""
kerf_plc.plcopen.reader — Parse PLCopen XML into the AST.

Supports PLCopen XML schema version 2.01 (IEC TR 61131-10).
Uses stdlib xml.etree.ElementTree only.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

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

# PLCopen XML namespaces — schema version 2.01 is the most common.
# The reader accepts both namespace-qualified and unqualified names.
_NS = {
    "pp": "http://www.plcopen.org/xml/tc6_0201",
}

# Some files omit the namespace; we try bare names as a fallback.
_BARE = ""


def _tag(element: ET.Element, local: str) -> bool:
    """Return True if element's local tag name matches *local*."""
    return element.tag.split("}")[-1] == local if "}" in element.tag else element.tag == local


def _find(parent: ET.Element, local: str) -> Optional[ET.Element]:
    """Find first direct child whose local tag name matches *local*."""
    for child in parent:
        if _tag(child, local):
            return child
    return None


def _findall(parent: ET.Element, local: str) -> list[ET.Element]:
    """Find all direct children whose local tag name matches *local*."""
    return [child for child in parent if _tag(child, local)]


def _attr_int(el: ET.Element, name: str, default: int = 0) -> int:
    v = el.get(name)
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _parse_position(el: ET.Element) -> Optional[Position]:
    pos_el = _find(el, "position")
    if pos_el is None:
        return None
    return Position(
        x=_attr_int(pos_el, "x"),
        y=_attr_int(pos_el, "y"),
    )


def _parse_variable(el: ET.Element) -> Variable:
    name = el.get("name", "")
    type_el = _find(el, "type")
    type_name = ""
    if type_el is not None:
        # <type><BOOL/></type>  or  <type><derived name="TON"/></type>
        for child in type_el:
            local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if local == "derived":
                type_name = child.get("name", local)
            else:
                type_name = local
            break
    initial_value: Optional[str] = None
    iv_el = _find(el, "initialValue")
    if iv_el is not None:
        sv = _find(iv_el, "simpleValue")
        if sv is not None:
            initial_value = sv.get("value")
    return Variable(name=name, type_name=type_name, initial_value=initial_value)


def _parse_var_block(el: ET.Element) -> VarBlock:
    local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
    kind_map = {
        "localVars": "local",
        "inputVars": "input",
        "outputVars": "output",
        "inOutVars": "inOut",
        "externalVars": "external",
        "globalVars": "global",
    }
    kind = kind_map.get(local, "local")
    variables: list[Variable] = []
    for var_el in _findall(el, "variable"):
        variables.append(_parse_variable(var_el))
    return VarBlock(kind=kind, variables=variables)


def _parse_contact(el: ET.Element) -> Contact:
    local_id = _attr_int(el, "localId")
    neg_str = el.get("negated", "false").lower()
    negated = neg_str in ("true", "1", "yes")
    variable = ""
    exp_el = _find(el, "expression")
    if exp_el is not None and exp_el.text:
        variable = exp_el.text.strip()
    pos = _parse_position(el)
    return Contact(local_id=local_id, variable=variable, negated=negated, position=pos)


def _parse_coil(el: ET.Element) -> Coil:
    local_id = _attr_int(el, "localId")
    neg_str = el.get("negated", "false").lower()
    negated = neg_str in ("true", "1", "yes")
    variable = ""
    exp_el = _find(el, "expression")
    if exp_el is not None and exp_el.text:
        variable = exp_el.text.strip()
    pos = _parse_position(el)
    return Coil(local_id=local_id, variable=variable, negated=negated, position=pos)


def _parse_fb_instance(el: ET.Element) -> FBInstance:
    local_id = _attr_int(el, "localId")
    type_name = el.get("typeName", "")
    instance_name = el.get("instanceName", "")
    pos = _parse_position(el)
    return FBInstance(
        local_id=local_id,
        type_name=type_name,
        instance_name=instance_name,
        position=pos,
    )


def _parse_rung(el: ET.Element) -> Rung:
    left = None
    right = None
    contacts: list[Contact] = []
    coils: list[Coil] = []
    fb_instances: list[FBInstance] = []

    for child in el:
        local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if local == "leftPowerRail":
            left = LeftPowerRail(
                local_id=_attr_int(child, "localId"),
                position=_parse_position(child),
            )
        elif local == "rightPowerRail":
            right = RightPowerRail(
                local_id=_attr_int(child, "localId"),
                position=_parse_position(child),
            )
        elif local == "contact":
            contacts.append(_parse_contact(child))
        elif local == "coil":
            coils.append(_parse_coil(child))
        elif local == "block":
            fb_instances.append(_parse_fb_instance(child))

    return Rung(
        left_power_rail=left,
        right_power_rail=right,
        contacts=contacts,
        coils=coils,
        fb_instances=fb_instances,
    )


def _parse_body(el: ET.Element) -> Body:
    # Body contains exactly one language element
    for child in el:
        local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if local == "LD":
            rungs = [_parse_rung(r) for r in _findall(child, "rung")]
            return LDBody(rungs=rungs)
        elif local == "ST":
            xhtmlEl = _find(child, "xhtml")
            text = (xhtmlEl.text or "").strip() if xhtmlEl is not None else ""
            if not text:
                # Some implementations put ST text directly
                text = (child.text or "").strip()
            return STBody(text=text)
        elif local == "FBD":
            return FBDBody(raw_xml=ET.tostring(child, encoding="unicode"))
        elif local == "IL":
            xhtmlEl = _find(child, "xhtml")
            text = (xhtmlEl.text or "").strip() if xhtmlEl is not None else ""
            return ILBody(text=text)
    return STBody(text="")


def _parse_pou(el: ET.Element) -> POU:
    name = el.get("name", "")
    pou_type_raw = el.get("pouType", "program")
    valid_pou_types = {"function", "functionBlock", "program"}
    if pou_type_raw not in valid_pou_types:
        raise PlcopenParseError(
            f"Invalid pouType '{pou_type_raw}'; expected one of {sorted(valid_pou_types)}"
        )

    var_kinds = {
        "localVars", "inputVars", "outputVars",
        "inOutVars", "externalVars", "globalVars",
    }
    var_blocks: list[VarBlock] = []
    body: Optional[Body] = None

    interface_el = _find(el, "interface")
    if interface_el is not None:
        for child in interface_el:
            local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if local in var_kinds:
                var_blocks.append(_parse_var_block(child))

    body_el = _find(el, "body")
    if body_el is not None:
        body = _parse_body(body_el)

    return POU(name=name, pou_type=pou_type_raw, var_blocks=var_blocks, body=body)


def _parse_types(el: ET.Element) -> Types:
    pous: list[POU] = []
    pous_el = _find(el, "pous")
    if pous_el is not None:
        for pou_el in _findall(pous_el, "pou"):
            pous.append(_parse_pou(pou_el))
    return Types(pous=pous)


def _parse_task(el: ET.Element) -> TaskConfig:
    return TaskConfig(
        name=el.get("name", ""),
        interval=el.get("interval"),
        priority=_attr_int(el, "priority"),
    )


def _parse_program_instance(el: ET.Element) -> ProgramInstance:
    return ProgramInstance(
        name=el.get("name", ""),
        type_name=el.get("typeName", ""),
        task_name=el.get("taskName"),
    )


def _parse_resource(el: ET.Element) -> Resource:
    tasks = [_parse_task(t) for t in _findall(el, "task")]
    prog_instances = [_parse_program_instance(p) for p in _findall(el, "programConfiguration")]
    return Resource(
        name=el.get("name", ""),
        type_name=el.get("typeName", "PLC"),
        tasks=tasks,
        program_instances=prog_instances,
    )


def _parse_configuration(el: ET.Element) -> Configuration:
    resources = [_parse_resource(r) for r in _findall(el, "resource")]
    return Configuration(name=el.get("name", ""), resources=resources)


def _parse_instances(el: ET.Element) -> Instances:
    # PLCopen XML wraps configurations in a <configurations> element.
    # Fall back to direct <configuration> children for schema variants.
    configs: list[Configuration] = []
    configs_el = _find(el, "configurations")
    if configs_el is not None:
        configs = [_parse_configuration(c) for c in _findall(configs_el, "configuration")]
    else:
        configs = [_parse_configuration(c) for c in _findall(el, "configuration")]
    return Instances(configurations=configs)


def _parse_content_header(el: ET.Element) -> ContentHeader:
    def _text(tag: str) -> str:
        child = _find(el, tag)
        return (child.text or "").strip() if child is not None else ""

    coord_ver = _find(el, "coordinateInfo")  # optional, ignore for now
    product_info = _find(el, "productInfo")

    product_name = ""
    product_version = ""
    product_release = ""
    if product_info is not None:
        product_name = product_info.get("productName", "")
        product_version = product_info.get("productVersion", "")
        product_release = product_info.get("productRelease", "")

    return ContentHeader(
        name=el.get("name", ""),
        version=el.get("version", "1.0"),
        product_name=product_name,
        product_version=product_version,
        product_release=product_release,
        creation_date_time=el.get("creationDateTime", ""),
        modification_date_time=el.get("modificationDateTime", ""),
        author=_text("author"),
        organization=_text("organization"),
        language=_text("language"),
        description=_text("description"),
    )


def loads(xml_text: str) -> Project:
    """Parse a PLCopen XML string and return a :class:`Project`.

    Raises :class:`PlcopenParseError` on parse failures.
    """
    if not xml_text or not xml_text.strip():
        raise PlcopenParseError("Empty or blank XML input.")

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise PlcopenParseError(f"XML parse error: {exc}") from exc

    # Accept both namespace-qualified and bare root element
    root_local = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if root_local != "project":
        raise PlcopenParseError(
            f"Root element must be <project>, got <{root_local}>."
        )

    header_el = _find(root, "contentHeader")
    content_header = _parse_content_header(header_el) if header_el is not None else ContentHeader()

    types_el = _find(root, "types")
    types = _parse_types(types_el) if types_el is not None else Types()

    instances_el = _find(root, "instances")
    instances = _parse_instances(instances_el) if instances_el is not None else Instances()

    return Project(
        content_header=content_header,
        types=types,
        instances=instances,
    )


def load(file_path: str) -> Project:
    """Read a PLCopen XML file and return a :class:`Project`."""
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            return loads(fh.read())
    except OSError as exc:
        raise PlcopenParseError(f"Cannot open file '{file_path}': {exc}") from exc
