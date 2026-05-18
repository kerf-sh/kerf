"""routes_silicon.py — POST /silicon/gds/parse

Accepts a multipart-uploaded .gds file, parses it with the kerf_silicon
GDS-II reader, and returns a layout-shapes JSON tree compatible with the
frontend LayoutViewer component.

Shape model returned:

    {
      "cells": [
        {
          "name": "TOP",
          "shapes": [
            { "kind": "box",     "layer": 68, "datatype": 20, "x": 0, "y": 0, "w": 1000, "h": 500 },
            { "kind": "polygon", "layer": 66, "datatype": 20, "points": [{"x":0,"y":0}, ...] },
            { "kind": "path",    "layer": 67, "datatype": 20, "points": [...], "width": 200 },
            { "kind": "text",    "layer": 83, "datatype": 0,  "x": 0, "y": 0, "label": "A", "size": 100 },
            { "kind": "ref",     "cell": "CHILD", "x": 0, "y": 0, "rotation": 0, "magnification": 1 }
          ]
        }
      ],
      "layers": [
        { "layer": 68, "datatype": 20 },
        ...
      ],
      "topCell": "TOP",
      "db_unit": 1e-9,
      "user_unit": 1e-6
    }
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, UploadFile, File, status

router = APIRouter()


# ---------------------------------------------------------------------------
# Shape conversion helpers  (GDS shapes → frontend JSON)
# ---------------------------------------------------------------------------

def _convert_shape(shape) -> Dict[str, Any]:
    """Convert a kerf_silicon GDS shape object to the frontend JSON model."""
    # Import here to keep the top-level import light and avoid failing fast
    # when kerf_silicon is not installed.
    from kerf_silicon.gds.shapes import Box, Polygon, Path, Text, Reference

    if isinstance(shape, Box):
        x = min(shape.p1.x, shape.p2.x)
        y = min(shape.p1.y, shape.p2.y)
        w = abs(shape.p2.x - shape.p1.x)
        h = abs(shape.p2.y - shape.p1.y)
        return {
            "kind": "box",
            "layer": shape.layer,
            "datatype": shape.datatype,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
        }

    if isinstance(shape, Polygon):
        return {
            "kind": "polygon",
            "layer": shape.layer,
            "datatype": shape.datatype,
            "points": [{"x": p.x, "y": p.y} for p in shape.points],
        }

    if isinstance(shape, Path):
        return {
            "kind": "path",
            "layer": shape.layer,
            "datatype": shape.datatype,
            "points": [{"x": p.x, "y": p.y} for p in shape.points],
            "width": shape.width,
        }

    if isinstance(shape, Text):
        return {
            "kind": "text",
            "layer": shape.layer,
            "datatype": shape.datatype,
            "x": shape.position.x,
            "y": shape.position.y,
            "label": shape.text,
            "size": 100,  # GDS-II TEXT has no explicit size field in the basic spec
        }

    if isinstance(shape, Reference):
        return {
            "kind": "ref",
            "cell": shape.cell_name,
            "x": shape.position.x,
            "y": shape.position.y,
            "rotation": shape.rotation,
            "magnification": shape.magnification,
        }

    # Unknown shape — return a minimal sentinel
    return {"kind": "unknown"}


def _library_to_json(library) -> Dict[str, Any]:
    """Convert a kerf_silicon Library object to the frontend layout JSON."""
    cells_json: List[Dict[str, Any]] = []
    layer_set: set = set()

    for cell in library.cells:
        shapes_json = []
        for shape in cell.shapes:
            converted = _convert_shape(shape)
            shapes_json.append(converted)
            # Collect (layer, datatype) pairs for the layer legend
            if "layer" in converted and "datatype" in converted:
                layer_set.add((converted["layer"], converted["datatype"]))
        cells_json.append({"name": cell.name, "shapes": shapes_json})

    # topCell heuristic: last cell in GDS file is typically the top-level cell
    top_cell = library.cells[-1].name if library.cells else None

    layers_json = [
        {"layer": lyr, "datatype": dt}
        for lyr, dt in sorted(layer_set)
    ]

    return {
        "cells": cells_json,
        "layers": layers_json,
        "topCell": top_cell,
        "db_unit": library.db_unit,
        "user_unit": library.user_unit,
    }


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post(
    "/silicon/gds/parse",
    summary="Parse a GDS-II file and return layout shapes",
    response_model=None,
)
async def parse_gds(
    file: UploadFile = File(..., description="GDS-II binary file (.gds)"),
) -> Dict[str, Any]:
    """Accept a multipart-uploaded .gds file and return a layout-shapes JSON tree.

    No authentication is required; the endpoint is read-only and operates
    entirely in memory without touching the database.

    Returns:
        {cells, layers, topCell, db_unit, user_unit}
    """
    # Read the uploaded bytes
    gds_bytes: bytes = await file.read()

    if not gds_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )

    # Parse with the kerf_silicon GDS reader
    try:
        from kerf_silicon.gds.reader import read_library
        library = read_library(gds_bytes)
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"kerf_silicon package not available: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse GDS file: {exc}",
        )

    return _library_to_json(library)
