"""
kerf_plc.ld.export — IEC 61131-3 XML export for Ladder Diagram programs.

Produces an IEC 61131-3 compliant XML document (`.xwl` or `.xml`) that can
be imported by CODESYS, OpenPLC, Beremiz, and other IEC 61131-3 compliant
engineering environments.

The XML format follows the PLCopen XML exchange format (TC6-XML) which is the
most widely-supported IEC 61131-3 interchange format — a superset of the bare
IEC XML and accepted by the broadest tool ecosystem.

Structure:
  <project>
    <fileHeader ... />
    <contentHeader ... />
    <types />
    <instances>
      <configurations>
        <configuration name="Config0">
          <resource name="Resource1">
            <task name="MainTask" interval="T#10ms" priority="0">
              <pouInstance name="Main" typeName="PROGRAM_NAME" />
            </task>
            <pouInstance name="Main" typeName="PROGRAM_NAME" />
          </resource>
        </configuration>
      </configurations>
    </instances>
    <pous>
      <pou name="PROGRAM_NAME" pouType="program">
        <interface>
          <localVars> ... </localVars>
          <inputVars> ... </inputVars>
          <outputVars> ... </outputVars>
        </interface>
        <body>
          <LD>
            <rung localId="...">
              ...
            </rung>
          </LD>
        </body>
      </pou>
    </pous>
  </project>
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString

from kerf_plc.ld.schema import (
    COIL_TYPES,
    CONTACT_TYPES,
    FB_TYPE,
    Element,
    LadderProgram,
    Rung,
    VariableDecl,
)

# PLCopen XML namespace
_NS = "http://www.plcopen.org/xml/tc6_0200"


def _el(tag: str, **attribs) -> ET.Element:
    el = ET.Element(tag)
    for k, v in attribs.items():
        el.set(k, str(v))
    return el


def _sub(parent: ET.Element, tag: str, **attribs) -> ET.Element:
    el = ET.SubElement(parent, tag)
    for k, v in attribs.items():
        el.set(k, str(v))
    return el


# ---------------------------------------------------------------------------
# Variable sections
# ---------------------------------------------------------------------------

def _dir_to_section(dir_key: str) -> str:
    return {
        "input": "inputVars",
        "output": "outputVars",
        "in_out": "inOutVars",
        "global": "externalVars",
        "local": "localVars",
    }.get(dir_key, "localVars")


def _export_interface(interface: ET.Element, variables: list[VariableDecl]) -> None:
    from collections import defaultdict
    groups: dict[str, list[VariableDecl]] = defaultdict(list)
    for v in variables:
        groups[v.dir].append(v)

    for dir_key, var_list in groups.items():
        section = _dir_to_section(dir_key)
        sec_el = _sub(interface, section)
        var_list_el = _sub(sec_el, "varList")
        for v in var_list:
            var_el = _sub(var_list_el, "variable", name=v.name)
            type_el = _sub(var_el, "type")
            # Simple BOOL/INT etc — use <BOOL/>, <INT/>, etc.
            _sub(type_el, v.type)
            if v.initial is not None:
                init_el = _sub(var_el, "initialValue")
                _sub(init_el, "simpleValue", value=str(v.initial))
            if v.comment:
                doc_el = ET.SubElement(var_el, "documentation")
                doc_el.text = v.comment


# ---------------------------------------------------------------------------
# LD body — contact/coil/fb elements
# ---------------------------------------------------------------------------

# Contact typeId values (PLCopen TC6 LD)
_CONTACT_TYPE = {
    "contact_no":  "normallyOpenContact",
    "contact_nc":  "normallyClosedContact",
    "contact_pos": "positiveTransitionContact",
    "contact_neg": "negativeTransitionContact",
}

_COIL_TYPE = {
    "coil":       "coil",
    "coil_set":   "setCoil",
    "coil_reset":  "resetCoil",
    "coil_pos":   "positiveTransitionCoil",
    "coil_neg":   "negativeTransitionCoil",
}

# Layout constants for the XML body (in PLCopen coordinate units)
_ELEM_W = 80
_ELEM_H = 40
_BRANCH_H = 60
_LEFT_RAIL_X = 0
_CONTENT_X0 = 100


def _export_ld_body(body: ET.Element, prog: LadderProgram) -> None:
    ld_el = _sub(body, "LD")
    local_id = [1]  # mutable counter

    def nid() -> str:
        v = str(local_id[0])
        local_id[0] += 1
        return v

    y_cursor = 20

    for ri, rung in enumerate(prog.rungs):
        rung_el = _sub(ld_el, "rung", localId=nid(), height=str(_BRANCH_H * max(len(rung.branches), 1)))
        if rung.comment:
            comment_el = ET.SubElement(rung_el, "comment")
            content_el = ET.SubElement(comment_el, "content")
            content_el.text = rung.comment

        # Left power rail
        lr = _sub(rung_el, "leftPowerRail", localId=nid())
        pos = _sub(lr, "position", x=str(_LEFT_RAIL_X), y=str(y_cursor))

        max_contacts = max((len(b) for b in rung.branches), default=0)

        # Contacts
        for bi, branch in enumerate(rung.branches):
            branch_y = y_cursor + bi * _BRANCH_H
            prev_id = lr.get("localId")
            prev_x = _CONTENT_X0

            for ci, elem in enumerate(branch):
                if elem.type not in CONTACT_TYPES:
                    continue
                c_el = _sub(rung_el, "contact",
                            localId=nid(),
                            negated="true" if elem.type == "contact_nc" else "false",
                            storage=_CONTACT_TYPE.get(elem.type, "normallyOpenContact"))
                _sub(c_el, "position",
                     x=str(prev_x + ci * _ELEM_W),
                     y=str(branch_y))
                var_el = _sub(c_el, "variable")
                var_el.text = elem.var
                conn = _sub(c_el, "connectionPointIn")
                conn_conn = _sub(conn, "connection", refLocalId=prev_id)
                prev_id = c_el.get("localId")

        # Output coil / FB
        output_x = _CONTENT_X0 + max_contacts * _ELEM_W
        rung_y_center = y_cursor + max(len(rung.branches), 1) * _BRANCH_H // 2

        if rung.output is not None:
            out = rung.output
            if out.type in COIL_TYPES:
                coil_el = _sub(rung_el, "coil",
                               localId=nid(),
                               negated="false",
                               storage=_COIL_TYPE.get(out.type, "coil"))
                _sub(coil_el, "position", x=str(output_x), y=str(rung_y_center))
                var_el = _sub(coil_el, "variable")
                var_el.text = out.var
                # Connect from last contact of first branch (simplified wiring)
                conn = _sub(coil_el, "connectionPointIn")
                _sub(conn, "connection", refLocalId=lr.get("localId"))
                # Right power rail connection
                rpr = _sub(rung_el, "rightPowerRail", localId=nid())
                _sub(rpr, "position", x=str(output_x + _ELEM_W), y=str(rung_y_center))

            elif out.type == FB_TYPE:
                fb_el = _sub(rung_el, "block",
                             localId=nid(),
                             typeName=out.fb_type,
                             instanceName=out.fb_instance)
                _sub(fb_el, "position", x=str(output_x), y=str(rung_y_center))
                conn_in = _sub(fb_el, "inputVariables")
                var_in_el = _sub(conn_in, "variable", formalParameter="EN")
                conn = _sub(var_in_el, "connectionPointIn")
                _sub(conn, "connection", refLocalId=lr.get("localId"))

                for pin, var_name in out.fb_inputs.items():
                    var_pin_el = _sub(conn_in, "variable", formalParameter=pin)
                    cpIn = _sub(var_pin_el, "connectionPointIn")
                    expr = ET.SubElement(cpIn, "expression")
                    expr.text = var_name

        y_cursor += max(len(rung.branches), 1) * _BRANCH_H + 20


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_xml(prog: LadderProgram) -> str:
    """
    Export a LadderProgram to a PLCopen TC6 XML string.

    The returned string is a pretty-printed UTF-8 XML document suitable for
    writing to a `.xwl` or `.xml` file for import into CODESYS / OpenPLC /
    Beremiz.
    """
    project = _el("project", xmlns=_NS)

    # fileHeader
    file_hdr = _sub(project, "fileHeader",
                    companyName="Kerf",
                    productName="Kerf IEC 61131-3 LD Editor",
                    productVersion="1.0",
                    creationDateTime="2025-01-01T00:00:00")

    # contentHeader
    content_hdr = _sub(project, "contentHeader", name=prog.program,
                       version="1.0")

    # types (empty)
    _sub(project, "types")

    # instances → configurations → configuration → resource
    instances = _sub(project, "instances")
    configs = _sub(instances, "configurations")
    config = _sub(configs, "configuration", name="Config0")
    resource = _sub(config, "resource", name="Resource1")
    task = _sub(resource, "task", name="MainTask",
                interval="T#10ms", priority="0")
    _sub(task, "pouInstance", name="Main", typeName=prog.program)
    _sub(resource, "pouInstance", name="Main", typeName=prog.program)

    # pous → pou
    pous = _sub(project, "pous")
    pou = _sub(pous, "pou", name=prog.program, pouType="program")

    # interface
    interface = _sub(pou, "interface")
    _export_interface(interface, prog.variables)

    # body → LD
    body = _sub(pou, "body")
    _export_ld_body(body, prog)

    # Pretty-print
    raw = ET.tostring(project, encoding="unicode", xml_declaration=False)
    try:
        dom = parseString(f'<?xml version="1.0" encoding="UTF-8"?>{raw}')
        return dom.toprettyxml(indent="  ", encoding=None)
    except Exception:
        return raw
