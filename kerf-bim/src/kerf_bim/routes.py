"""
IFC4 compilation via IfcOpenShell.

POST /compile-ifc   (also /compile-bim for backend/tools/bim.py compatibility)
Body: { "bim_content": string }

Returns: { "ifc_base64": string, "warnings": [], "errors": [] }
"""

from fastapi import APIRouter
import base64
import json
import math
import re
import tempfile
from pathlib import Path

router = APIRouter()


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@router.post("/compile-ifc")
async def compile_ifc(req: dict):
    bim_content = req.get("bim_content", "")
    if not bim_content:
        return {"ifc_base64": "", "warnings": [], "errors": ["bim_content required"]}
    warnings: list = []
    errors: list = []
    try:
        ifc_bytes = _compile(bim_content, warnings)
    except Exception as exc:
        errors.append(str(exc))
        return {"ifc_base64": "", "warnings": warnings, "errors": errors}
    return {
        "ifc_base64": base64.b64encode(ifc_bytes).decode(),
        "warnings": warnings,
        "errors": [],
    }


@router.post("/compile-bim")
async def compile_bim(req: dict):
    """Alias kept for backend/tools/bim.py compatibility."""
    return await compile_ifc(req)


# ---------------------------------------------------------------------------
# DSL parser — line-oriented text -> dict
# ---------------------------------------------------------------------------

def _parse_dsl(text: str) -> dict:
    """Parse the .bim line-oriented DSL into the same dict shape as JSON .bim."""
    doc: dict = {
        "version": 1,
        "levels": [],
        "walls": [],
        "slabs": [],
        "spaces": [],
        "openings": [],
    }

    def _vec2(s: str) -> list:
        m = re.match(r'\(\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\s*\)', s.strip())
        if m:
            return [float(m.group(1)), float(m.group(2))]
        raise ValueError(f"expected (x,y) got {s!r}")

    def _boundary(s: str) -> list:
        pts = re.findall(r'\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)', s)
        return [_vec2(p) for p in pts]

    def _kv(s: str) -> dict:
        out = {}
        for m in re.finditer(r'(\w+)=([^\s,]+)', s):
            k, v = m.group(1), m.group(2)
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v.strip('"')
        return out

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or line.startswith('//'):
            continue

        # level "L1" elevation=0
        m = re.match(r'^level\s+"([^"]+)"\s*(.*)', line)
        if m:
            kv = _kv(m.group(2))
            doc["levels"].append({"name": m.group(1), "elevation": kv.get("elevation", 0)})
            continue

        # site { name: "...", lat: ..., lon: ..., elevation: ... }
        m = re.match(r'^site\s*\{(.*)\}', line, re.DOTALL)
        if m:
            inner = m.group(1)
            site: dict = {}
            for pair in re.finditer(r'(\w+)\s*:\s*"?([^,"}\s]+)"?', inner):
                k, v = pair.group(1), pair.group(2).strip()
                try:
                    site[k] = float(v)
                except ValueError:
                    site[k] = v
            doc["site"] = {
                "name": site.get("name", ""),
                "latitude": site.get("lat", 0.0),
                "longitude": site.get("lon", 0.0),
                "elevation": site.get("elevation", 0.0),
            }
            continue

        # wall on="L1" from=(0,0) to=(5000,0) height=3000 thickness=200
        m = re.match(r'^wall\s+(.*)', line)
        if m:
            rest = m.group(1)
            on_m = re.search(r'on="([^"]+)"', rest)
            from_m = re.search(r'from=(\([^)]+\))', rest)
            to_m = re.search(r'to=(\([^)]+\))', rest)
            kv = _kv(rest)
            wall: dict = {
                "level": on_m.group(1) if on_m else "",
                "from": _vec2(from_m.group(1)) if from_m else [0, 0],
                "to": _vec2(to_m.group(1)) if to_m else [0, 0],
                "height": kv.get("height", 3000),
                "thickness": kv.get("thickness", 200),
            }
            doc["walls"].append(wall)
            continue

        # slab on="L1" boundary=[(0,0),...] thickness=200
        m = re.match(r'^slab\s+(.*)', line)
        if m:
            rest = m.group(1)
            on_m = re.search(r'on="([^"]+)"', rest)
            bnd_m = re.search(r'boundary=\[([^\]]+)\]', rest)
            kv = _kv(rest)
            slab: dict = {
                "level": on_m.group(1) if on_m else "",
                "boundary": _boundary(bnd_m.group(1)) if bnd_m else [],
                "thickness": kv.get("thickness", 200),
            }
            doc["slabs"].append(slab)
            continue

        # space on="L1" boundary=[...] name="Living Room"
        m = re.match(r'^space\s+(.*)', line)
        if m:
            rest = m.group(1)
            on_m = re.search(r'on="([^"]+)"', rest)
            bnd_m = re.search(r'boundary=\[([^\]]+)\]', rest)
            name_m = re.search(r'name="([^"]+)"', rest)
            space: dict = {
                "level": on_m.group(1) if on_m else "",
                "boundary": _boundary(bnd_m.group(1)) if bnd_m else [],
                "name": name_m.group(1) if name_m else "",
            }
            doc["spaces"].append(space)
            continue

        # opening in="wall_0" position=(1000,0) width=900 height=2100
        m = re.match(r'^opening\s+(.*)', line)
        if m:
            rest = m.group(1)
            in_m = re.search(r'in="([^"]+)"', rest)
            pos_m = re.search(r'position=(\([^)]+\))', rest)
            kv = _kv(rest)
            opening: dict = {
                "wall": in_m.group(1) if in_m else "",
                "position": _vec2(pos_m.group(1)) if pos_m else [0, 0],
                "width": kv.get("width", 900),
                "height": kv.get("height", 2100),
            }
            doc["openings"].append(opening)

    return doc


def _parse_input(bim_content: str) -> dict:
    """Try JSON first; fall back to line DSL."""
    stripped = bim_content.strip()
    if stripped.startswith('{'):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    return _parse_dsl(bim_content)


# ---------------------------------------------------------------------------
# IFC4 compiler — requires ifcopenshell (imported lazily)
# ---------------------------------------------------------------------------

def _compile(bim_content: str, warnings: list) -> bytes:
    try:
        import ifcopenshell
        import ifcopenshell.guid
    except ImportError as exc:
        raise RuntimeError(f"ifcopenshell not available: {exc}") from exc

    doc = _parse_input(bim_content)
    model = ifcopenshell.file(schema="IFC4")

    # -- project --
    project_name = doc.get("name", "Kerf Building")
    units = model.createIfcUnitAssignment(Units=[
        model.createIfcSIUnit(UnitType="LENGTHUNIT", Name="MILLIMETRE"),
        model.createIfcSIUnit(UnitType="AREAUNIT", Name="SQUARE_METRE"),
        model.createIfcSIUnit(UnitType="VOLUMEUNIT", Name="CUBIC_METRE"),
    ])
    ctx = model.createIfcGeometricRepresentationContext(
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-5,
        WorldCoordinateSystem=model.createIfcAxis2Placement3D(
            Location=model.createIfcCartesianPoint((0.0, 0.0, 0.0))
        ),
    )
    project = model.createIfcProject(
        GlobalId=ifcopenshell.guid.new(),
        Name=project_name,
        UnitsInContext=units,
        RepresentationContexts=[ctx],
    )

    # -- site --
    site_data = doc.get("site", {})
    site = model.createIfcSite(
        GlobalId=ifcopenshell.guid.new(),
        Name=site_data.get("name", "Site"),
        RefLatitude=_dms(site_data.get("latitude", 0.0)),
        RefLongitude=_dms(site_data.get("longitude", 0.0)),
        RefElevation=float(site_data.get("elevation", 0.0)),
        CompositionType="ELEMENT",
    )
    building = model.createIfcBuilding(
        GlobalId=ifcopenshell.guid.new(),
        Name=doc.get("name", "Building"),
        CompositionType="ELEMENT",
    )
    _rel_aggregates(model, ifcopenshell.guid, project, [site])
    _rel_aggregates(model, ifcopenshell.guid, site, [building])

    # -- levels → storeys --
    levels = doc.get("levels", [])
    if not levels:
        levels = [{"name": "L1", "elevation": 0}]
        warnings.append("no levels defined; using default L1 at 0")
    level_map: dict = {}
    storeys = []
    for lv in levels:
        storey = model.createIfcBuildingStorey(
            GlobalId=ifcopenshell.guid.new(),
            Name=lv["name"],
            Elevation=float(lv.get("elevation", 0)),
            CompositionType="ELEMENT",
        )
        level_map[lv["name"]] = storey
        storeys.append(storey)
    _rel_aggregates(model, ifcopenshell.guid, building, storeys)

    # -- walls --
    for i, w in enumerate(doc.get("walls", [])):
        storey = level_map.get(w.get("level", ""))
        if storey is None and level_map:
            storey = next(iter(level_map.values()))
            warnings.append(f"wall {i}: level not found, using first storey")
        elev = _storey_elevation(storey)
        wall = _make_wall(model, ifcopenshell.guid, ctx, w, elev, i)
        if storey:
            _rel_contained(model, ifcopenshell.guid, storey, [wall])

    # -- slabs --
    for i, s in enumerate(doc.get("slabs", [])):
        storey = level_map.get(s.get("level", ""))
        elev = _storey_elevation(storey)
        slab = _make_slab(model, ifcopenshell.guid, ctx, s, elev, i)
        if storey:
            _rel_contained(model, ifcopenshell.guid, storey, [slab])

    # -- spaces --
    for i, sp in enumerate(doc.get("spaces", [])):
        storey = level_map.get(sp.get("level", ""))
        elev = _storey_elevation(storey)
        space = _make_space(model, ifcopenshell.guid, ctx, sp, elev, i)
        if storey:
            _rel_aggregates(model, ifcopenshell.guid, storey, [space])

    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
        tmp_path = tmp.name
    model.write(tmp_path)
    data = Path(tmp_path).read_bytes()
    Path(tmp_path).unlink(missing_ok=True)
    return data


# ---------------------------------------------------------------------------
# IFC geometry helpers
# ---------------------------------------------------------------------------

def _dms(deg: float) -> tuple:
    """Convert decimal degrees to (degrees, minutes, seconds, millionths)."""
    d = int(deg)
    rem = abs(deg - d) * 60
    m = int(rem)
    s = int((rem - m) * 60)
    ms = int(((rem - m) * 60 - s) * 1_000_000)
    return (d, m, s, ms)


def _storey_elevation(storey) -> float:
    if storey is None:
        return 0.0
    try:
        return float(storey.Elevation or 0.0)
    except Exception:
        return 0.0


def _axis2p3d(model, origin=(0.0, 0.0, 0.0), z=None, x=None):
    loc = model.createIfcCartesianPoint(origin)
    kwargs: dict = {"Location": loc}
    if z:
        kwargs["Axis"] = model.createIfcDirection(z)
    if x:
        kwargs["RefDirection"] = model.createIfcDirection(x)
    return model.createIfcAxis2Placement3D(**kwargs)


def _extrude(model, ctx, profile, depth: float, place):
    return model.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=place,
        ExtrudedDirection=model.createIfcDirection((0.0, 0.0, 1.0)),
        Depth=depth,
    )


def _shape_rep(model, ctx, items):
    return model.createIfcShapeRepresentation(
        ContextOfItems=ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=items,
    )


def _rel_aggregates(model, guid_mod, relating, parts):
    model.createIfcRelAggregates(
        GlobalId=guid_mod.new(),
        RelatingObject=relating,
        RelatedObjects=parts,
    )


def _rel_contained(model, guid_mod, storey, elements):
    model.createIfcRelContainedInSpatialStructure(
        GlobalId=guid_mod.new(),
        RelatingStructure=storey,
        RelatedElements=elements,
    )


def _make_wall(model, guid_mod, ctx, w: dict, base_elev: float, idx: int):
    frm = w.get("from", [0, 0])
    to = w.get("to", [1000, 0])
    height = float(w.get("height", 3000))
    thickness = float(w.get("thickness", 200))
    dx = float(to[0]) - float(frm[0])
    dy = float(to[1]) - float(frm[1])
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-6:
        length = 1.0

    x_dir = (dx / length, dy / length, 0.0)
    profile = model.createIfcRectangleProfileDef(
        ProfileType="AREA",
        XDim=length,
        YDim=thickness,
    )
    place = _axis2p3d(
        model,
        origin=(float(frm[0]) + dx / 2, float(frm[1]) + dy / 2, base_elev),
        x=x_dir,
    )
    solid = _extrude(model, ctx, profile, height, place)
    rep = _shape_rep(model, ctx, [solid])
    prod_def = model.createIfcProductDefinitionShape(Representations=[rep])
    return model.createIfcWallStandardCase(
        GlobalId=guid_mod.new(),
        Name=f"Wall_{idx}",
        ObjectPlacement=model.createIfcLocalPlacement(
            RelativePlacement=_axis2p3d(model, (0.0, 0.0, 0.0))
        ),
        Representation=prod_def,
    )


def _make_slab(model, guid_mod, ctx, s: dict, base_elev: float, idx: int):
    boundary = s.get("boundary", [])
    thickness = float(s.get("thickness", 200))
    if len(boundary) < 3:
        boundary = [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]

    pts = [model.createIfcCartesianPoint((float(p[0]), float(p[1]))) for p in boundary]
    polyline = model.createIfcPolyline(Points=pts + [pts[0]])
    profile = model.createIfcArbitraryClosedProfileDef(
        ProfileType="AREA",
        OuterCurve=polyline,
    )
    place = _axis2p3d(model, origin=(0.0, 0.0, base_elev))
    solid = _extrude(model, ctx, profile, thickness, place)
    rep = _shape_rep(model, ctx, [solid])
    prod_def = model.createIfcProductDefinitionShape(Representations=[rep])
    return model.createIfcSlab(
        GlobalId=guid_mod.new(),
        Name=f"Slab_{idx}",
        ObjectPlacement=model.createIfcLocalPlacement(
            RelativePlacement=_axis2p3d(model, (0.0, 0.0, 0.0))
        ),
        Representation=prod_def,
        PredefinedType="FLOOR",
    )


def _make_space(model, guid_mod, ctx, sp: dict, base_elev: float, idx: int):
    boundary = sp.get("boundary", [])
    name = sp.get("name", f"Space_{idx}")
    height = float(sp.get("height", 3000))
    if len(boundary) < 3:
        boundary = [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]

    pts = [model.createIfcCartesianPoint((float(p[0]), float(p[1]))) for p in boundary]
    polyline = model.createIfcPolyline(Points=pts + [pts[0]])
    profile = model.createIfcArbitraryClosedProfileDef(
        ProfileType="AREA",
        OuterCurve=polyline,
    )
    place = _axis2p3d(model, origin=(0.0, 0.0, base_elev))
    solid = _extrude(model, ctx, profile, height, place)
    rep = _shape_rep(model, ctx, [solid])
    prod_def = model.createIfcProductDefinitionShape(Representations=[rep])
    return model.createIfcSpace(
        GlobalId=guid_mod.new(),
        Name=name,
        ObjectPlacement=model.createIfcLocalPlacement(
            RelativePlacement=_axis2p3d(model, (0.0, 0.0, 0.0))
        ),
        Representation=prod_def,
        PredefinedType="INTERNAL",
    )
