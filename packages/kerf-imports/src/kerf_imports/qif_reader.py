"""
qif_reader.py — QIF 3.0 (Quality Information Framework, ISO 23952) reader.

Parses QIF XML documents (namespace-prefixed or bare) into a Kerf inspection
result model.  Pure Python — stdlib xml.etree only, no third-party deps.

Supported QIF sections
----------------------
  QIFDocument
    └── Product/PartSet               → part name / description
    └── MeasurementResources
          └── MeasuredCharacteristics → characteristics list
    └── Features                      → measured features (point/line/plane/
                                        circle/cylinder/sphere)
    └── DatumDefinitions              → datum labels + references
    └── MeasurementResults
          └── MeasuredCharacteristics → actual values, deviations, pass/fail
    └── Statistics                    → summary (skipped with warning if
                                        present but unsupported schema)

Unsupported elements are silently skipped with a warning in the output.

Output model
------------
  {
    "ok": True,
    "part_name": str,
    "characteristics": [
      {
        "id":        str,
        "name":      str,
        "type":      str,       # "dimension" | "flatness" | ... (GD&T type)
        "nominal":   float | None,
        "upper_tol": float | None,  # +tol above nominal
        "lower_tol": float | None,  # -tol below nominal (stored as negative)
        "actual":    float | None,
        "deviation": float | None,  # actual − nominal
        "status":    str | None,    # "PASS" | "FAIL" | None
      },
      ...
    ],
    "features": [
      {
        "id":   str,
        "name": str,
        "type": str,     # "PointFeature" | "LineFeature" | ...
        "nominal": {...} | None,
        "actual":  {...} | None,
      },
      ...
    ],
    "datums": [
      {"id": str, "label": str, "feature_id": str | None},
      ...
    ],
    "summary": {
        "total":  int,
        "passed": int,
        "failed": int,
    },
    "warnings": [str, ...],
  }

On error:
  {"ok": False, "reason": str}

Never raises.

LLM tool ``import_qif`` registered via @register; gated on "imports.qif".
"""

from __future__ import annotations

import json
import logging
import uuid
import warnings as _warnings_mod
import xml.etree.ElementTree as ET
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Namespace handling
# ---------------------------------------------------------------------------

# QIF 3.0 standard namespace URIs (the document may omit these and use bare
# element names, or it may use any of these prefixed forms).
_QIF_NS_URIS = {
    "qif": "http://qifstandards.org/xsd/qif3",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

# Feature type names we understand
_FEATURE_TYPES = {
    "PointFeature",
    "LineFeature",
    "PlaneFeature",
    "CircleFeature",
    "CylinderFeature",
    "SphereFeature",
}


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def _strip_ns(tag: str) -> str:
    """Return the local name of an element, stripping any namespace URI."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _find(elem: ET.Element, *local_names: str) -> Optional[ET.Element]:
    """Depth-first search for a descendant matching any local name."""
    for child in elem:
        local = _strip_ns(child.tag)
        if local in local_names:
            return child
        found = _find(child, *local_names)
        if found is not None:
            return found
    return None


def _findall(elem: ET.Element, local_name: str) -> list[ET.Element]:
    """Return all immediate children whose local name matches."""
    return [c for c in elem if _strip_ns(c.tag) == local_name]


def _findall_deep(elem: ET.Element, local_name: str) -> list[ET.Element]:
    """Return all descendants (any depth) whose local name matches."""
    out: list[ET.Element] = []
    for child in elem:
        if _strip_ns(child.tag) == local_name:
            out.append(child)
        out.extend(_findall_deep(child, local_name))
    return out


def _text(elem: Optional[ET.Element], default: str = "") -> str:
    if elem is None:
        return default
    return (elem.text or "").strip()


def _float_text(elem: Optional[ET.Element]) -> Optional[float]:
    t = _text(elem)
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _attr_id(elem: ET.Element) -> str:
    """Return the 'id' attribute (ignoring namespace)."""
    for attr, val in elem.attrib.items():
        if _strip_ns(attr) == "id":
            return val
    return elem.get("id", "")


# ---------------------------------------------------------------------------
# Feature parsing
# ---------------------------------------------------------------------------

def _parse_location(loc_elem: Optional[ET.Element]) -> Optional[dict]:
    if loc_elem is None:
        return None
    x_el = _find(loc_elem, "X", "x")
    y_el = _find(loc_elem, "Y", "y")
    z_el = _find(loc_elem, "Z", "z")
    x = _float_text(x_el)
    y = _float_text(y_el)
    z = _float_text(z_el)
    if x is None and y is None and z is None:
        return None
    return {"x": x, "y": y, "z": z}


def _parse_feature_nominal(feat_elem: ET.Element, feat_type: str) -> Optional[dict]:
    nom_el = _find(feat_elem, "Nominal")
    if nom_el is None:
        return None
    loc = _parse_location(_find(nom_el, "Location", "Centre", "Center"))
    result: dict[str, Any] = {}
    if loc:
        result["location"] = loc
    # Radius for circle/sphere/cylinder
    r_el = _find(nom_el, "Radius", "Diameter")
    if r_el is not None:
        result["radius"] = _float_text(r_el)
    return result or None


def _parse_feature_actual(feat_elem: ET.Element, feat_type: str) -> Optional[dict]:
    act_el = _find(feat_elem, "Actual")
    if act_el is None:
        return None
    loc = _parse_location(_find(act_el, "Location", "Centre", "Center"))
    result: dict[str, Any] = {}
    if loc:
        result["location"] = loc
    r_el = _find(act_el, "Radius", "Diameter")
    if r_el is not None:
        result["radius"] = _float_text(r_el)
    return result or None


def _parse_features_section(doc_root: ET.Element) -> list[dict]:
    """
    Parse the Features section.

    QIF layout (simplified):
      <Features>
        <FeatureItems>
          <PointFeature id="1"> ... </PointFeature>
          <CircleFeature id="2"> ... </CircleFeature>
          ...
        </FeatureItems>
      </Features>
    """
    out: list[dict] = []
    features_el = _find(doc_root, "Features")
    if features_el is None:
        return out
    items_el = _find(features_el, "FeatureItems")
    if items_el is None:
        items_el = features_el  # some docs omit the wrapper

    for child in items_el:
        feat_type = _strip_ns(child.tag)
        if feat_type not in _FEATURE_TYPES:
            continue
        fid = _attr_id(child)
        name_el = _find(child, "Name")
        name = _text(name_el) or feat_type
        nominal = _parse_feature_nominal(child, feat_type)
        actual = _parse_feature_actual(child, feat_type)
        out.append({
            "id": fid,
            "name": name,
            "type": feat_type,
            "nominal": nominal,
            "actual": actual,
        })
    return out


# ---------------------------------------------------------------------------
# Datum parsing
# ---------------------------------------------------------------------------

def _parse_datums(doc_root: ET.Element) -> list[dict]:
    """
    Parse DatumDefinitions.

      <DatumDefinitions>
        <DatumDefinition id="d1">
          <DatumLabel>A</DatumLabel>
          <FeatureId>1</FeatureId>
        </DatumDefinition>
        ...
      </DatumDefinitions>
    """
    out: list[dict] = []
    datums_el = _find(doc_root, "DatumDefinitions")
    if datums_el is None:
        return out
    for child in datums_el:
        local = _strip_ns(child.tag)
        if local != "DatumDefinition":
            continue
        did = _attr_id(child)
        label_el = _find(child, "DatumLabel", "Label")
        label = _text(label_el)
        fref_el = _find(child, "FeatureId", "FeatureRef")
        feature_id = _text(fref_el) or None
        out.append({
            "id": did,
            "label": label,
            "feature_id": feature_id,
        })
    return out


# ---------------------------------------------------------------------------
# Characteristic parsing from MeasuredCharacteristics
# ---------------------------------------------------------------------------

def _parse_characteristic_item(char_el: ET.Element) -> Optional[dict]:
    """
    Parse a single CharacteristicItem element:

      <CharacteristicItem id="c1">
        <Name>Diameter 1</Name>
        <CharacteristicDesignator>
          <Designator>diameter</Designator>
        </CharacteristicDesignator>
        <NominalValue>10.0</NominalValue>
        <ToleranceValue>0.05</ToleranceValue>
        <!-- OR -->
        <Tolerance>
          <UpperTolerance>0.05</UpperTolerance>
          <LowerTolerance>-0.05</LowerTolerance>
        </Tolerance>
      </CharacteristicItem>
    """
    cid = _attr_id(char_el)
    name_el = _find(char_el, "Name")
    name = _text(name_el) or cid

    # Characteristic type
    type_el = _find(char_el, "CharacteristicDesignator")
    if type_el is None:
        type_el = _find(char_el, "Type")
    if type_el is not None:
        desig_el = _find(type_el, "Designator", "Type")
        char_type = _text(desig_el) or _strip_ns(char_el.tag)
    else:
        char_type = _strip_ns(char_el.tag)

    # Nominal value
    nom_el = _find(char_el, "NominalValue", "Nominal")
    nominal = _float_text(nom_el)

    # Tolerance — try both forms
    upper_tol: Optional[float] = None
    lower_tol: Optional[float] = None

    tol_single_el = _find(char_el, "ToleranceValue")
    tol_block_el = _find(char_el, "Tolerance", "ToleranceZone")

    if tol_single_el is not None:
        t = _float_text(tol_single_el)
        if t is not None:
            upper_tol = t
            lower_tol = -t

    if tol_block_el is not None:
        up_el = _find(tol_block_el, "UpperTolerance", "PlusTolerance")
        lo_el = _find(tol_block_el, "LowerTolerance", "MinusTolerance")
        if up_el is not None:
            upper_tol = _float_text(up_el)
        if lo_el is not None:
            lower_tol = _float_text(lo_el)

    return {
        "id": cid,
        "name": name,
        "type": char_type,
        "nominal": nominal,
        "upper_tol": upper_tol,
        "lower_tol": lower_tol,
        "actual": None,
        "deviation": None,
        "status": None,
    }


def _parse_characteristics_items(doc_root: ET.Element) -> dict[str, dict]:
    """
    Return {id: characteristic_dict} from the MeasuredCharacteristics /
    CharacteristicItems section (definition phase, no actual values yet).

    QIF nesting can vary:
      <MeasurementResources>
        <MeasuredCharacteristics>
          <CharacteristicItems>
            <CharacteristicItem id="..."> ...
    or directly:
      <CharacteristicItems>
        <CharacteristicItem id="..."> ...
    """
    chars: dict[str, dict] = {}

    # Collect from MeasurementResources/MeasuredCharacteristics
    mc_sections = _findall_deep(doc_root, "MeasuredCharacteristics")
    for mc_el in mc_sections:
        items_wrapper = _find(mc_el, "CharacteristicItems")
        if items_wrapper is None:
            items_wrapper = mc_el
        for child in items_wrapper:
            local = _strip_ns(child.tag)
            if not local.endswith("CharacteristicItem"):
                continue
            item = _parse_characteristic_item(child)
            if item:
                chars[item["id"]] = item

    # Also look at top-level CharacteristicItems
    ci_sections = _findall_deep(doc_root, "CharacteristicItems")
    for ci_el in ci_sections:
        for child in ci_el:
            local = _strip_ns(child.tag)
            if not local.endswith("CharacteristicItem"):
                continue
            item = _parse_characteristic_item(child)
            if item and item["id"] not in chars:
                chars[item["id"]] = item

    return chars


# ---------------------------------------------------------------------------
# MeasurementResults parsing (actual values + pass/fail)
# ---------------------------------------------------------------------------

def _parse_measurement_results(
    doc_root: ET.Element,
    chars: dict[str, dict],
    warns: list[str],
) -> None:
    """
    Mutate *chars* in-place with actual values, deviations, and pass/fail
    status from MeasurementResults.

    Typical QIF layout:
      <MeasurementResults>
        <MeasurementResult id="mr1">
          <MeasuredCharacteristics>
            <MeasuredCharacteristic>
              <CharacteristicItemId>c1</CharacteristicItemId>
              <Value>10.03</Value>
              <Status>
                <PassFail>PASS</PassFail>
              </Status>
            </MeasuredCharacteristic>
            ...
          </MeasuredCharacteristics>
        </MeasurementResult>
      </MeasurementResults>
    """
    mr_sections = (
        _findall_deep(doc_root, "MeasurementResults") +
        _findall_deep(doc_root, "MeasurementResult")
    )

    for mr_el in mr_sections:
        mc_el = _find(mr_el, "MeasuredCharacteristics")
        if mc_el is None:
            mc_el = mr_el
        for mc_item in mc_el:
            if _strip_ns(mc_item.tag) != "MeasuredCharacteristic":
                continue
            cid_el = _find(mc_item, "CharacteristicItemId", "CharacteristicId")
            if cid_el is None:
                continue
            cid = _text(cid_el)

            val_el = _find(mc_item, "Value", "ActualValue")
            actual = _float_text(val_el)

            status_el = _find(mc_item, "Status")
            status: Optional[str] = None
            if status_el is not None:
                pf_el = _find(status_el, "PassFail")
                if pf_el is not None:
                    status = _text(pf_el).upper() or None

            if cid in chars:
                chars[cid]["actual"] = actual
                if actual is not None and chars[cid]["nominal"] is not None:
                    chars[cid]["deviation"] = actual - chars[cid]["nominal"]
                if status:
                    chars[cid]["status"] = status
            else:
                # Actual for a characteristic we haven't seen defined — create stub
                chars[cid] = {
                    "id": cid,
                    "name": cid,
                    "type": "unknown",
                    "nominal": None,
                    "upper_tol": None,
                    "lower_tol": None,
                    "actual": actual,
                    "deviation": None,
                    "status": status,
                }


# ---------------------------------------------------------------------------
# Part / product metadata
# ---------------------------------------------------------------------------

def _parse_part_name(doc_root: ET.Element) -> str:
    for tag in ("PartName", "Name", "ProductName"):
        el = _find(doc_root, tag)
        if el is not None and el.text and el.text.strip():
            return el.text.strip()
    return ""


# ---------------------------------------------------------------------------
# Statistics section — emit warning if present (structure varies widely)
# ---------------------------------------------------------------------------

def _check_statistics(doc_root: ET.Element, warns: list[str]) -> None:
    stats_el = _find(doc_root, "Statistics", "MeasurementStatistics")
    if stats_el is not None:
        warns.append(
            "Statistics section detected but not fully parsed; "
            "per-characteristic pass/fail counts are available in 'summary'."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_qif(data: str | bytes) -> dict:
    """
    Parse a QIF 3.0 XML document from a string or bytes.

    Returns the Kerf inspection result model (see module docstring).
    Never raises — errors surface as {"ok": False, "reason": str}.
    """
    warns: list[str] = []

    try:
        if isinstance(data, bytes):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("latin-1", errors="replace")
        else:
            text = data

        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            return {"ok": False, "reason": f"XML parse error: {exc}"}

        # Locate the QIFDocument root (the parsed root might already be it,
        # or it might be wrapped in a processing-instruction envelope).
        doc_root = root
        if _strip_ns(root.tag) != "QIFDocument":
            candidate = _find(root, "QIFDocument")
            if candidate is not None:
                doc_root = candidate
            # else: try to work with whatever root we have

        part_name = _parse_part_name(doc_root)
        features = _parse_features_section(doc_root)
        datums = _parse_datums(doc_root)
        chars_map = _parse_characteristics_items(doc_root)
        _parse_measurement_results(doc_root, chars_map, warns)
        _check_statistics(doc_root, warns)

        char_list = list(chars_map.values())

        # Compute summary
        total = len(char_list)
        passed = sum(1 for c in char_list if c.get("status") == "PASS")
        failed = sum(1 for c in char_list if c.get("status") == "FAIL")

        return {
            "ok": True,
            "part_name": part_name,
            "characteristics": char_list,
            "features": features,
            "datums": datums,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
            },
            "warnings": warns,
        }

    except Exception as exc:
        return {"ok": False, "reason": f"unexpected error: {exc}"}


# ---------------------------------------------------------------------------
# LLM tool
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx

    _import_qif_spec = ToolSpec(
        name="import_qif",
        description=(
            "Import a QIF 3.0 (Quality Information Framework, ISO 23952) "
            "inspection report into the current project. "
            "Accepts a blob_id or storage_key pointing to the uploaded .qif XML file. "
            "Parses characteristics (dimension/GD&T) with nominal, tolerance, actual "
            "values, and pass/fail status. Returns a structured inspection model with "
            "per-characteristic results and a summary pass/fail count. "
            "Gate: imports.qif capability."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "UUID of the target Kerf project.",
                },
                "file_blob_id_or_storage_key": {
                    "type": "string",
                    "description": "Blob ID or storage key for the .qif XML file.",
                },
                "import_folder": {
                    "type": "string",
                    "description": (
                        "Path in the project tree for the imported file. "
                        "Defaults to /qif_import."
                    ),
                },
            },
            "required": ["project_id", "file_blob_id_or_storage_key"],
        },
    )

    @register(_import_qif_spec, write=True)
    async def run_import_qif(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        project_id = a.get("project_id", "").strip()
        blob_ref = a.get("file_blob_id_or_storage_key", "").strip()
        import_folder = a.get("import_folder", "/qif_import").strip()

        if not project_id:
            return err_payload("project_id is required", "BAD_ARGS")
        if not blob_ref:
            return err_payload("file_blob_id_or_storage_key is required", "BAD_ARGS")

        if ctx.storage is None:
            return err_payload("storage backend not configured", "NO_STORAGE")

        try:
            blob_bytes = await ctx.storage.get(blob_ref)
        except Exception as exc:
            return err_payload(f"failed to fetch blob {blob_ref!r}: {exc}", "STORAGE_ERROR")

        if not blob_bytes:
            return err_payload(f"blob not found: {blob_ref}", "NOT_FOUND")

        model = parse_qif(blob_bytes)
        if not model.get("ok"):
            return err_payload(model.get("reason", "QIF parse failed"), "PARSE_ERROR")

        try:
            _pid = uuid.UUID(project_id)
        except Exception:
            return err_payload("project_id must be a valid UUID", "BAD_ARGS")

        fid = uuid.uuid4()
        content = json.dumps({
            "version": 1,
            "part_name": model["part_name"],
            "characteristics": model["characteristics"],
            "features": model["features"],
            "datums": model["datums"],
            "summary": model["summary"],
        })

        try:
            ctx.pool.execute(
                "insert into files (id, project_id, name, kind, content, "
                "created_at, updated_at) values ($1, $2, $3, $4, $5, now(), now())",
                fid, _pid,
                f"{import_folder}/inspection.qif.json",
                "qif_inspection",
                content,
            )
        except Exception as exc:
            model["warnings"].append(f"failed to persist inspection file: {exc}")

        return ok_payload({
            "ok": True,
            "file_id": str(fid),
            "part_name": model["part_name"],
            "characteristic_count": len(model["characteristics"]),
            "feature_count": len(model["features"]),
            "datum_count": len(model["datums"]),
            "summary": model["summary"],
            "warnings": model["warnings"],
        })

    # Expose TOOLS list for plugin loader (mirrors jt_reader / parasolid_reader
    # pattern — plugin.py iterates mod.TOOLS if present).
    TOOLS = [(_import_qif_spec.name, _import_qif_spec, run_import_qif)]

except ImportError:
    # Standalone / test mode — no Kerf runtime available
    pass
