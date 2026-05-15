"""
techdraw.py — FreeCAD TechDraw → Kerf .drawing translator.

FreeCAD TechDraw workbench produces:
- ``TechDraw::DrawPage`` — the top-level sheet (paper size, scale, template).
- ``TechDraw::DrawViewPart`` — a projected view of a PartDesign::Body.
- ``TechDraw::DrawViewSection`` — a section view.
- ``TechDraw::DrawViewDetail`` — a detail (magnified) view.
- ``TechDraw::DrawProjGroup`` — a set of related projected views.
- ``TechDraw::DrawViewDimension`` — a dimension annotation on a view.

We translate a single ``DrawPage`` and its child views into a Kerf
``.drawing`` sheet payload.  The output follows the schema documented in
``packages/kerf-chat/llm_docs/drawing.md``.

**Projection math note:**

FreeCAD stores each ``DrawView`` with an ``X`` and ``Y`` position on the
page (in mm), a ``Scale`` factor, and a ``Direction`` vector that encodes
the projection direction (the view normal in model space).  We map this
directly::

    Kerf view position  = [DrawView.X, DrawView.Y]
    Kerf view scale     = DrawView.Scale
    Kerf projection dir = closest named projection from Direction vector

The direction-to-projection-name mapping is:

+---------------------+-------------+
| Direction vector    | Kerf label  |
+=====================+=============+
| (0, 0, 1)  or close | ``front``   |
| (0, 0, -1)          | ``back``    |
| (0, -1, 0) or close | ``top``     |
| (0, 1, 0)           | ``bottom``  |
| (1, 0, 0)  or close | ``right``   |
| (-1, 0, 0)          | ``left``    |
| others              | ``iso``     |
+---------------------+-------------+

We do NOT recompute projected 2D geometry (that requires the BRep solid
and is deferred to Kerf's native renderer).  The imported ``.drawing``
references source feature files by their FreeCAD source name (stored in
``source_feature_name``); the caller can resolve these to actual file IDs
in the post-import wiring step.
"""
from __future__ import annotations

import math
from typing import Any

from .types import FCStdObject, FCStdDocument


# ---------------------------------------------------------------------------
# Paper size mappings
# ---------------------------------------------------------------------------

_FC_TEMPLATE_TO_SIZE: dict[str, str] = {
    "A0_Landscape": "A0",
    "A0_Portrait": "A0",
    "A1_Landscape": "A1",
    "A1_Portrait": "A1",
    "A2_Landscape": "A2",
    "A2_Portrait": "A2",
    "A3_Landscape": "A3",
    "A3_Portrait": "A3",
    "A4_Landscape": "A4",
    "A4_Portrait": "A4",
    "ANSI_A_Landscape": "ANSI_A",
    "ANSI_A_Portrait": "ANSI_A",
    "ANSI_B_Landscape": "ANSI_B",
    "ANSI_C_Landscape": "ANSI_C",
    "ANSI_D_Landscape": "ANSI_D",
}

_FC_TEMPLATE_TO_ORIENT: dict[str, str] = {
    "A0_Landscape": "landscape", "A1_Landscape": "landscape",
    "A2_Landscape": "landscape", "A3_Landscape": "landscape",
    "A4_Landscape": "landscape",
    "A0_Portrait": "portrait", "A1_Portrait": "portrait",
    "A2_Portrait": "portrait", "A3_Portrait": "portrait",
    "A4_Portrait": "portrait",
    "ANSI_A_Landscape": "landscape", "ANSI_A_Portrait": "portrait",
    "ANSI_B_Landscape": "landscape", "ANSI_C_Landscape": "landscape",
    "ANSI_D_Landscape": "landscape",
}


# ---------------------------------------------------------------------------
# Projection direction → name
# ---------------------------------------------------------------------------

_NAMED_DIRS: list[tuple[tuple[float, float, float], str]] = [
    ((0, 0, 1),   "front"),
    ((0, 0, -1),  "back"),
    ((0, -1, 0),  "top"),
    ((0, 1, 0),   "bottom"),
    ((1, 0, 0),   "right"),
    ((-1, 0, 0),  "left"),
    ((0.577, 0.577, 0.577),  "iso"),
    ((-0.577, 0.577, 0.577), "iso"),
]


def _direction_to_projection(d: dict | None) -> str:
    """Map a FreeCAD Direction vector dict to a Kerf projection name."""
    if not d:
        return "front"
    x = float(d.get("x", 0) or 0)
    y = float(d.get("y", 0) or 0)
    z = float(d.get("z", 0) or 0)

    mag = math.sqrt(x * x + y * y + z * z)
    if mag < 1e-9:
        return "front"
    x, y, z = x / mag, y / mag, z / mag

    best_name = "iso"
    best_dot = -2.0
    for (nx, ny, nz), name in _NAMED_DIRS:
        dot = x * nx + y * ny + z * nz
        if dot > best_dot:
            best_dot = dot
            best_name = name

    return best_name


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def translate_drawpage(
    page_obj: FCStdObject,
    doc: FCStdDocument,
) -> dict[str, Any]:
    """
    Translate a ``TechDraw::DrawPage`` FCStdObject into a Kerf ``.drawing``
    sheet payload.

    Parameters
    ----------
    page_obj :
        The ``TechDraw::DrawPage`` object from the parsed document.
    doc :
        The full :class:`~kerf_imports.freecad.types.FCStdDocument` so
        we can look up child view objects.

    Returns
    -------
    dict
        Kerf ``.drawing`` payload with keys:
        ``sheets``       — single-item list (the translated sheet)
        ``freecad_ref``  — provenance
        ``warnings``     — list of warning strings
    """
    warnings: list[str] = []

    # ── Frame ─────────────────────────────────────────────────────────────────
    template_name: str = page_obj.properties.get("Template", "") or ""
    if isinstance(template_name, bytes):
        template_name = ""
    if isinstance(template_name, str) and "/" in template_name:
        template_name = template_name.rsplit("/", 1)[-1].replace(".svg", "")

    size = _FC_TEMPLATE_TO_SIZE.get(template_name, "A3")
    orientation = _FC_TEMPLATE_TO_ORIENT.get(template_name, "landscape")

    if template_name.endswith("_Landscape") or "landscape" in template_name.lower():
        orientation = "landscape"
    elif template_name.endswith("_Portrait") or "portrait" in template_name.lower():
        orientation = "portrait"

    scale_val = page_obj.properties.get("Scale")
    if isinstance(scale_val, dict):
        scale_val = scale_val.get("value", 1.0)
    page_scale = float(scale_val or 1.0)

    if page_scale < 1:
        scale_label = f"1:{int(round(1 / page_scale))}"
    elif page_scale > 1:
        scale_label = f"{int(round(page_scale))}:1"
    else:
        scale_label = "1:1"

    frame: dict[str, Any] = {
        "size": size,
        "orientation": orientation,
        "title": page_obj.label or page_obj.name,
        "scale_label": scale_label,
        "template": "default",
    }

    # ── Views ─────────────────────────────────────────────────────────────────
    views: list[dict[str, Any]] = []
    view_ids_seen: set[str] = set()

    child_view_refs = page_obj.properties.get("Views") or []
    if not isinstance(child_view_refs, list):
        child_view_refs = []

    view_types = frozenset({
        "TechDraw::DrawViewPart",
        "TechDraw::DrawViewSection",
        "TechDraw::DrawViewDetail",
        "TechDraw::DrawView",
        "TechDraw::DrawProjGroupItem",
    })

    child_names: set[str] = set()
    for ref in child_view_refs:
        from .types import LinkRef
        if isinstance(ref, LinkRef):
            child_names.add(ref.target_name)
        elif isinstance(ref, str):
            child_names.add(ref)

    candidate_views: list[FCStdObject] = []
    for obj in doc.objects:
        if obj.type not in view_types:
            continue
        if child_names:
            if obj.name in child_names:
                candidate_views.append(obj)
        else:
            candidate_views.append(obj)

    for v_obj in candidate_views:
        view_dict, v_warnings = _translate_view(v_obj, page_scale)
        warnings.extend(v_warnings)
        if view_dict is not None:
            vid = view_dict["id"]
            if vid not in view_ids_seen:
                view_ids_seen.add(vid)
                views.append(view_dict)

    sheet: dict[str, Any] = {
        "id": f"sh-{page_obj.name}",
        "frame": frame,
        "views": views,
        "dimensions": [],
        "annotations": [],
        "centerlines": [],
        "breaks": [],
        "symbols": [],
    }

    return {
        "sheets": [sheet],
        "freecad_ref": {
            "name": page_obj.name,
            "label": page_obj.label,
            "type": page_obj.type,
        },
        "warnings": warnings,
    }


def _translate_view(
    v_obj: FCStdObject,
    page_scale: float,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Translate one TechDraw view object into a Kerf view dict."""
    warnings: list[str] = []

    x = v_obj.properties.get("X")
    y = v_obj.properties.get("Y")
    if isinstance(x, dict):
        x = x.get("value", 0)
    if isinstance(y, dict):
        y = y.get("value", 0)
    x = float(x or 0)
    y = float(y or 0)

    scale_val = v_obj.properties.get("Scale")
    if isinstance(scale_val, dict):
        scale_val = scale_val.get("value", page_scale)
    scale = float(scale_val or page_scale)

    direction = v_obj.properties.get("Direction")
    projection = _direction_to_projection(direction)

    is_section = v_obj.type == "TechDraw::DrawViewSection"
    is_detail = v_obj.type == "TechDraw::DrawViewDetail"

    source_refs = v_obj.properties.get("Source") or []
    if not isinstance(source_refs, list):
        source_refs = [source_refs]
    source_feature_name: str | None = None
    from .types import LinkRef
    for ref in source_refs:
        if isinstance(ref, LinkRef):
            source_feature_name = ref.target_name
            break
        elif isinstance(ref, str) and ref:
            source_feature_name = ref
            break

    show_hidden_raw = v_obj.properties.get("ShowHiddenLines")
    if isinstance(show_hidden_raw, str):
        show_hidden = show_hidden_raw.lower() in ("true", "1")
    elif isinstance(show_hidden_raw, bool):
        show_hidden = show_hidden_raw
    else:
        show_hidden = True

    view_id = f"v-{v_obj.name}"
    view: dict[str, Any] = {
        "id": view_id,
        "source_feature_name": source_feature_name,
        "source_file_id": None,
        "part_id": "*",
        "projection": projection,
        "scale": scale,
        "position": [x, y],
        "show_hidden": show_hidden,
        "show_silhouette": True,
        "label": v_obj.label or v_obj.name,
        "freecad_type": v_obj.type,
    }

    if is_section:
        view["is_section"] = True
        view["hatch_spacing"] = 2.5
        view["hatch_angle"] = 45

    if is_detail:
        detail_scale = v_obj.properties.get("ScaleFactor")
        if isinstance(detail_scale, dict):
            detail_scale = detail_scale.get("value")
        if detail_scale is not None:
            view["scale"] = float(detail_scale or scale)
        view["is_detail"] = True

    return view, warnings


# ---------------------------------------------------------------------------
# Convenience: translate all DrawPages in a document
# ---------------------------------------------------------------------------

def translate_all_drawpages(doc: FCStdDocument) -> list[dict[str, Any]]:
    """
    Translate every ``TechDraw::DrawPage`` in *doc* into a list of
    ``.drawing`` payload dicts.  Returns an empty list if the document
    has no TechDraw pages.
    """
    pages = [o for o in doc.objects if o.type == "TechDraw::DrawPage"]
    return [translate_drawpage(p, doc) for p in pages]
