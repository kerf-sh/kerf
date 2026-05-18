"""
kerf_plc.plcopen.writer — Serialise a Project AST to PLCopen XML.

Produces namespace-qualified XML using the PLCopen TC6 0201 schema URI.
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

_NS_URI = "http://www.plcopen.org/xml/tc6_0201"
_XSD_URI = "http://www.plcopen.org/xml/tc6_0201 http://www.plcopen.org/xml/tc6_0201/tc6_xml_v201.xsd"


def _qn(local: str) -> str:
    return f"{{{_NS_URI}}}{local}"


def _sub(parent: ET.Element, local: str, **attrib: str) -> ET.Element:
    return ET.SubElement(parent, _qn(local), **attrib)


def _write_position(parent: ET.Element, pos: Optional[Position]) -> None:
    if pos is not None:
        _sub(parent, "position", x=str(pos.x), y=str(pos.y))


def _write_variable(parent: ET.Element, var: Variable) -> None:
    el = _sub(parent, "variable", name=var.name)
    type_el = _sub(el, "type")
    # Simple IEC types → bare element; derived (FB) types → <derived name="...">
    simple_types = {
        "BOOL", "BYTE", "WORD", "DWORD", "LWORD",
        "SINT", "INT", "DINT", "LINT",
        "USINT", "UINT", "UDINT", "ULINT",
        "REAL", "LREAL",
        "TIME", "DATE", "TOD", "DT",
        "STRING", "WSTRING",
    }
    if var.type_name.upper() in simple_types:
        _sub(type_el, var.type_name.upper())
    else:
        _sub(type_el, "derived", name=var.type_name)
    if var.initial_value is not None:
        iv_el = _sub(el, "initialValue")
        _sub(iv_el, "simpleValue", value=var.initial_value)


def _write_var_block(parent: ET.Element, vb: VarBlock) -> None:
    kind_to_tag = {
        "local": "localVars",
        "input": "inputVars",
        "output": "outputVars",
        "inOut": "inOutVars",
        "external": "externalVars",
        "global": "globalVars",
    }
    tag = kind_to_tag.get(vb.kind, "localVars")
    block_el = _sub(parent, tag)
    for var in vb.variables:
        _write_variable(block_el, var)


def _write_contact(parent: ET.Element, contact: Contact) -> None:
    el = _sub(parent, "contact",
               localId=str(contact.local_id),
               negated="true" if contact.negated else "false")
    _write_position(el, contact.position)
    exp_el = _sub(el, "expression")
    exp_el.text = contact.variable


def _write_coil(parent: ET.Element, coil: Coil) -> None:
    el = _sub(parent, "coil",
               localId=str(coil.local_id),
               negated="true" if coil.negated else "false")
    _write_position(el, coil.position)
    exp_el = _sub(el, "expression")
    exp_el.text = coil.variable


def _write_fb_instance(parent: ET.Element, fb: FBInstance) -> None:
    el = _sub(parent, "block",
               localId=str(fb.local_id),
               typeName=fb.type_name,
               instanceName=fb.instance_name)
    _write_position(el, fb.position)


def _write_rung(parent: ET.Element, rung: Rung) -> None:
    rung_el = _sub(parent, "rung")
    if rung.left_power_rail is not None:
        lpr = rung.left_power_rail
        lpr_el = _sub(rung_el, "leftPowerRail", localId=str(lpr.local_id))
        _write_position(lpr_el, lpr.position)
    for contact in rung.contacts:
        _write_contact(rung_el, contact)
    for fb in rung.fb_instances:
        _write_fb_instance(rung_el, fb)
    for coil in rung.coils:
        _write_coil(rung_el, coil)
    if rung.right_power_rail is not None:
        rpr = rung.right_power_rail
        rpr_el = _sub(rung_el, "rightPowerRail", localId=str(rpr.local_id))
        _write_position(rpr_el, rpr.position)


def _write_body(parent: ET.Element, body: Body) -> None:
    body_el = _sub(parent, "body")
    if isinstance(body, LDBody):
        ld_el = _sub(body_el, "LD")
        for rung in body.rungs:
            _write_rung(ld_el, rung)
    elif isinstance(body, STBody):
        st_el = _sub(body_el, "ST")
        xhtml_el = _sub(st_el, "xhtml")
        xhtml_el.text = body.text
    elif isinstance(body, ILBody):
        il_el = _sub(body_el, "IL")
        xhtml_el = _sub(il_el, "xhtml")
        xhtml_el.text = body.text
    elif isinstance(body, FBDBody):
        # Re-insert the raw FBD XML
        fbd_el = ET.fromstring(body.raw_xml) if body.raw_xml else _sub(body_el, "FBD")
        if body.raw_xml:
            body_el.append(fbd_el)


def _write_pou(parent: ET.Element, pou: POU) -> None:
    pou_el = _sub(parent, "pou", name=pou.name, pouType=pou.pou_type)
    if pou.var_blocks:
        iface_el = _sub(pou_el, "interface")
        for vb in pou.var_blocks:
            _write_var_block(iface_el, vb)
    if pou.body is not None:
        _write_body(pou_el, pou.body)


def _write_types(parent: ET.Element, types: Types) -> None:
    types_el = _sub(parent, "types")
    pous_el = _sub(types_el, "pous")
    for pou in types.pous:
        _write_pou(pous_el, pou)


def _write_task(parent: ET.Element, task: TaskConfig) -> None:
    attribs: dict[str, str] = {"name": task.name, "priority": str(task.priority)}
    if task.interval is not None:
        attribs["interval"] = task.interval
    _sub(parent, "task", **attribs)


def _write_program_instance(parent: ET.Element, pi: ProgramInstance) -> None:
    attribs: dict[str, str] = {"name": pi.name, "typeName": pi.type_name}
    if pi.task_name is not None:
        attribs["taskName"] = pi.task_name
    _sub(parent, "programConfiguration", **attribs)


def _write_resource(parent: ET.Element, res: Resource) -> None:
    res_el = _sub(parent, "resource", name=res.name, typeName=res.type_name)
    for task in res.tasks:
        _write_task(res_el, task)
    for pi in res.program_instances:
        _write_program_instance(res_el, pi)


def _write_configuration(parent: ET.Element, cfg: Configuration) -> None:
    cfg_el = _sub(parent, "configuration", name=cfg.name)
    for res in cfg.resources:
        _write_resource(cfg_el, res)


def _write_instances(parent: ET.Element, instances: Instances) -> None:
    inst_el = _sub(parent, "instances")
    configs_el = _sub(inst_el, "configurations")
    for cfg in instances.configurations:
        _write_configuration(configs_el, cfg)


def _write_content_header(parent: ET.Element, ch: ContentHeader) -> None:
    attribs: dict[str, str] = {
        "name": ch.name,
        "version": ch.version,
    }
    if ch.creation_date_time:
        attribs["creationDateTime"] = ch.creation_date_time
    if ch.modification_date_time:
        attribs["modificationDateTime"] = ch.modification_date_time
    header_el = _sub(parent, "contentHeader", **attribs)

    if ch.product_name or ch.product_version or ch.product_release:
        _sub(
            header_el,
            "productInfo",
            productName=ch.product_name,
            productVersion=ch.product_version,
            productRelease=ch.product_release,
        )

    for tag, value in [
        ("author", ch.author),
        ("organization", ch.organization),
        ("language", ch.language),
        ("description", ch.description),
    ]:
        if value:
            el = _sub(header_el, tag)
            el.text = value


def dumps(project: Project) -> str:
    """Serialise *project* to a PLCopen XML string."""
    # Register the default namespace so ElementTree doesn't invent ns0: prefixes.
    # We must NOT also set xmlns= as an explicit attribute — ET already handles
    # xmlns emission via register_namespace, and a duplicate would be invalid XML.
    ET.register_namespace("", _NS_URI)
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")

    root = ET.Element(_qn("project"), attrib={
        "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation": _XSD_URI,
    })

    _write_content_header(root, project.content_header)
    _write_types(root, project.types)
    _write_instances(root, project.instances)

    ET.indent(root, space="  ")
    xml_bytes = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_bytes}\n'


def dump(project: Project, file_path: str) -> None:
    """Write *project* as PLCopen XML to *file_path*."""
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(dumps(project))
