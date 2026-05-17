"""Hermetic tests for kerf-render cycles_translator + material_mapping.

T-106a: scene translator + material mapping (Kerf Body -> Blender Cycles).

These tests do **not** require Blender / bpy. They cover:

  - glTF binary spec compliance (magic, version, chunk types, length).
  - Per-face mesh accounting (one mesh primitive per Face, correct root
    node + child nodes layout).
  - Generated Blender Python script: compiles cleanly, contains the
    expected glass-BSDF / principled-BSDF wiring, embeds the right
    camera matrix and gem optic data.
  - Material mapping table: every named gem in the catalog has IOR +
    Abbe + Sellmeier coefficients that round-trip; every named metal
    has metallic=1 and a colour appropriate to its alloy family.
  - Graceful failure on bad input.
"""

from __future__ import annotations

import json
import math
import struct

import numpy as np
import pytest

from kerf_cad_core.geom.brep import (
    Body,
    Solid,
    make_box,
    make_cylinder,
    make_sphere,
    make_tetra,
)

from kerf_render.cycles_translator import (
    Camera,
    Light,
    RenderOutput,
    parse_glb_header,
    translate_body_to_gltf_plus_materials,
    vertex_count_for_body,
)
from kerf_render.material_mapping import (
    DEFAULT_MATERIAL,
    GEMSTONE_OPTICS,
    METAL_PBR,
    ORGANIC_OPAQUE,
    PLASTIC_PBR,
    WAVELENGTHS_UM,
    abbe_from_sellmeier,
    canonical_key,
    lookup_material,
    material_kind,
    sellmeier_n,
    supported_materials,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _box_body(size=(2.0, 2.0, 2.0), origin=(0.0, 0.0, 0.0)):
    return make_box(origin=origin, size=size)


def _gem_face_body():
    """Tiny one-face body (a tetrahedron) used as a stand-in for a gemstone."""
    return make_tetra()


# ---------------------------------------------------------------------------
# glTF binary structure
# ---------------------------------------------------------------------------


class TestGltfBinary:
    def test_box_returns_ok_payload(self):
        body = _box_body()
        result = translate_body_to_gltf_plus_materials(body)
        assert result["ok"] is True
        assert result["face_count"] == 6
        assert isinstance(result["gltf_bytes"], (bytes, bytearray))
        assert len(result["gltf_bytes"]) > 100

    def test_gltf_magic_and_version(self):
        body = _box_body()
        glb = translate_body_to_gltf_plus_materials(body)["gltf_bytes"]
        magic, version, length = struct.unpack("<III", glb[:12])
        assert magic == 0x46546C67    # "glTF"
        assert version == 2
        assert length == len(glb)

    def test_gltf_total_length_field_matches_payload_size(self):
        body = _box_body()
        glb = translate_body_to_gltf_plus_materials(body)["gltf_bytes"]
        _, _, length = struct.unpack("<III", glb[:12])
        assert length == len(glb)

    def test_parse_glb_header_round_trips(self):
        body = _box_body()
        glb = translate_body_to_gltf_plus_materials(body)["gltf_bytes"]
        parsed = parse_glb_header(glb)
        assert parsed["magic"] == 0x46546C67
        assert parsed["version"] == 2
        assert parsed["length"] == len(glb)
        assert isinstance(parsed["json"], dict)
        assert parsed["json"]["asset"]["version"] == "2.0"

    def test_box_produces_6_meshes_and_root_node(self):
        body = _box_body()
        glb = translate_body_to_gltf_plus_materials(body)["gltf_bytes"]
        parsed = parse_glb_header(glb)
        gltf = parsed["json"]
        # 6 face meshes
        assert len(gltf["meshes"]) == 6
        # 6 face nodes + 1 root node
        assert len(gltf["nodes"]) == 7
        # one scene with the root node as its sole entry
        assert gltf["scene"] == 0
        assert len(gltf["scenes"]) == 1
        root = gltf["nodes"][-1]
        assert root["name"] == "root"
        assert len(root["children"]) == 6

    def test_each_face_mesh_has_triangle_primitive(self):
        body = _box_body()
        glb = translate_body_to_gltf_plus_materials(body)["gltf_bytes"]
        gltf = parse_glb_header(glb)["json"]
        for mesh in gltf["meshes"]:
            assert len(mesh["primitives"]) == 1
            prim = mesh["primitives"][0]
            assert prim["mode"] == 4        # TRIANGLES
            assert "POSITION" in prim["attributes"]
            assert "NORMAL" in prim["attributes"]
            assert "indices" in prim

    def test_bad_input_none_body_returns_failure(self):
        result = translate_body_to_gltf_plus_materials(None)
        assert result["ok"] is False
        assert "reason" in result and isinstance(result["reason"], str)

    def test_bad_input_empty_body_returns_failure(self):
        result = translate_body_to_gltf_plus_materials(Body())
        assert result["ok"] is False
        assert "zero faces" in result["reason"]

    def test_missing_material_in_strict_mode_returns_failure(self):
        body = _box_body()
        faces = body.all_faces()
        result = translate_body_to_gltf_plus_materials(
            body,
            materials={faces[0].id: "unobtainium_42"},
            strict=True,
        )
        assert result["ok"] is False
        assert "unobtainium_42" in result["reason"]

    def test_missing_material_in_non_strict_mode_falls_back_gracefully(self):
        body = _box_body()
        faces = body.all_faces()
        result = translate_body_to_gltf_plus_materials(
            body, materials={faces[0].id: "totally_not_real"}
        )
        assert result["ok"] is True
        assert "totally_not_real" in result["missing"]

    def test_vertex_count_round_trip_matches_input_body(self):
        body = _box_body()
        expected_total = vertex_count_for_body(body)
        glb = translate_body_to_gltf_plus_materials(body)["gltf_bytes"]
        gltf = parse_glb_header(glb)["json"]
        total = 0
        for mesh in gltf["meshes"]:
            attrs = mesh["primitives"][0]["attributes"]
            pos_acc = gltf["accessors"][attrs["POSITION"]]
            total += pos_acc["count"]
        assert total == expected_total

    def test_planar_box_face_has_four_vertices_and_two_triangles(self):
        body = _box_body()
        glb = translate_body_to_gltf_plus_materials(body)["gltf_bytes"]
        gltf = parse_glb_header(glb)["json"]
        # Each box face is a quad: 4 vertices, 6 indices (2 tris).
        for mesh in gltf["meshes"]:
            attrs = mesh["primitives"][0]["attributes"]
            pos = gltf["accessors"][attrs["POSITION"]]
            idx = gltf["accessors"][mesh["primitives"][0]["indices"]]
            assert pos["count"] == 4
            assert idx["count"] == 6


# ---------------------------------------------------------------------------
# Material mapping table
# ---------------------------------------------------------------------------


class TestMaterialMapping:
    def test_diamond_optics_correct(self):
        mat = lookup_material("diamond")
        assert mat["bsdf"] == "glass"
        assert mat["ior"] == pytest.approx(2.417, abs=1e-3)
        assert mat["abbe"] == pytest.approx(55.3, abs=0.5)
        assert mat["dispersion"] is True

    def test_sapphire_optics_correct(self):
        mat = lookup_material("sapphire")
        assert mat["bsdf"] == "glass"
        assert mat["ior"] == pytest.approx(1.77, abs=1e-2)
        assert mat["abbe"] == pytest.approx(72.2, abs=1.0)

    def test_emerald_and_ruby_optics(self):
        e = lookup_material("emerald")
        r = lookup_material("ruby")
        assert e["bsdf"] == "glass"
        assert e["ior"] == pytest.approx(1.58, abs=2e-2)
        assert r["bsdf"] == "glass"
        assert r["ior"] == pytest.approx(1.77, abs=2e-2)
        assert r["abbe"] == pytest.approx(72.2, abs=1.0)

    def test_all_listed_gems_present(self):
        # The catalogue must cover at least these ten gems.
        must_have = [
            "diamond", "sapphire", "ruby", "emerald", "topaz",
            "amethyst", "citrine", "garnet", "peridot", "tanzanite",
            "tourmaline", "spinel", "morganite", "aquamarine",
            "alexandrite", "moonstone", "zircon",
        ]
        for name in must_have:
            assert name in GEMSTONE_OPTICS, f"missing gem: {name}"
            mat = lookup_material(name)
            assert mat["bsdf"] == "glass"
            assert "sellmeier" in mat
            assert len(mat["sellmeier"]) == 3
            assert mat["transmission"] == 1.0

    def test_at_least_ten_gems_with_principled_or_glass(self):
        gems = supported_materials()["gem"]
        assert len(gems) >= 10
        for name in gems:
            mat = lookup_material(name)
            assert mat["bsdf"] in {"glass", "principled"}

    def test_sellmeier_reproduces_published_nd(self):
        for name, entry in GEMSTONE_OPTICS.items():
            n_d = sellmeier_n(entry["sellmeier"], WAVELENGTHS_UM["D"])
            assert n_d == pytest.approx(entry["ior"], rel=0.05), (
                f"{name}: sellmeier n_D={n_d:.4f} vs target {entry['ior']}"
            )

    def test_sellmeier_reproduces_published_abbe(self):
        for name, entry in GEMSTONE_OPTICS.items():
            abbe_calc = abbe_from_sellmeier(entry["sellmeier"])
            assert abbe_calc == pytest.approx(entry["abbe"], rel=0.05), (
                f"{name}: abbe_calc={abbe_calc:.2f} vs target {entry['abbe']}"
            )

    def test_gold_alloys_are_metals(self):
        for slot in ["10k_yellow", "14k_yellow", "18k_yellow",
                     "22k_yellow", "24k_yellow"]:
            mat = lookup_material(slot)
            assert mat["bsdf"] == "principled"
            assert mat["metallic"] == 1.0
            r, g, b, _ = mat["base_color"]
            # Yellow gold: R > G > B
            assert r > g > b, f"{slot} should have R>G>B (got {r}, {g}, {b})"

    def test_silver_alloys_present(self):
        for slot in ["sterling_925", "fine_silver", "argentium_935"]:
            mat = lookup_material(slot)
            assert mat["metallic"] == 1.0
            r, g, b, _ = mat["base_color"]
            # Silver: roughly neutral, all channels >= 0.9
            assert min(r, g, b) >= 0.85

    def test_platinum_and_palladium_present(self):
        for slot in ["platinum_950", "platinum_900",
                     "palladium_950", "palladium_500"]:
            mat = lookup_material(slot)
            assert mat["bsdf"] == "principled"
            assert mat["metallic"] == 1.0

    def test_rose_gold_has_red_dominance(self):
        for slot in ["10k_rose", "14k_rose", "18k_rose", "22k_rose"]:
            mat = lookup_material(slot)
            r, g, b, _ = mat["base_color"]
            assert r > g and r > b, f"{slot}: rose gold should be R-dominant"

    def test_mech_materials_present(self):
        for slot in ["steel_1018", "steel_4140", "aluminum_6061",
                     "abs", "pla", "pp", "pe", "nylon"]:
            kind = material_kind(slot)
            assert kind in {"metal", "plastic"}, (
                f"{slot} resolved to kind {kind}, expected metal/plastic"
            )

    def test_canonical_alias_resolution(self):
        assert canonical_key("Yellow Gold") == "18k_yellow"
        assert canonical_key("white-gold") == "18k_white"
        assert canonical_key("PLATINUM") == "platinum_950"
        assert canonical_key("Sterling") == "sterling_925"
        assert canonical_key("tsavorite") == "garnet"
        assert canonical_key("rubellite") == "tourmaline"

    def test_organic_gems_use_principled_not_glass(self):
        for name in ["pearl", "turquoise", "lapis_lazuli"]:
            mat = lookup_material(name)
            assert mat["bsdf"] == "principled", (
                f"{name} should be opaque (Principled), not Glass"
            )

    def test_lookup_unknown_material_raises(self):
        with pytest.raises(KeyError):
            lookup_material("definitely_not_a_real_material")

    def test_default_material_is_neutral(self):
        assert DEFAULT_MATERIAL["bsdf"] == "principled"
        r, g, b, _ = DEFAULT_MATERIAL["base_color"]
        # neutral grey ish
        assert abs(r - g) < 0.01 and abs(g - b) < 0.01


# ---------------------------------------------------------------------------
# Materials dict produced by translator
# ---------------------------------------------------------------------------


class TestTranslatorMaterials:
    def test_diamond_face_emits_glass_bsdf(self):
        body = _gem_face_body()
        faces = body.all_faces()
        result = translate_body_to_gltf_plus_materials(
            body, materials={faces[0].id: "diamond"},
        )
        d = result["materials_dict"]["diamond"]
        assert d["bsdf"] == "glass"
        assert d["ior"] == pytest.approx(2.417, abs=1e-3)
        assert d["abbe"] == pytest.approx(55.3, abs=0.5)
        assert d["dispersion"] is True

    def test_gold_face_emits_principled_with_yellow_tint(self):
        body = _box_body()
        faces = body.all_faces()
        result = translate_body_to_gltf_plus_materials(
            body, materials={faces[0].id: "18k_yellow"},
        )
        g = result["materials_dict"]["18k_yellow"]
        assert g["bsdf"] == "principled"
        assert g["metallic"] == 1.0
        r, gg, b, _ = g["base_color"]
        assert r > gg > b

    def test_default_material_appears_for_unspecified_faces(self):
        body = _box_body()
        result = translate_body_to_gltf_plus_materials(body)
        assert "default" in result["materials_dict"]
        d = result["materials_dict"]["default"]
        # falls back to neutral grey
        assert d["bsdf"] == "principled"


# ---------------------------------------------------------------------------
# Blender script generation
# ---------------------------------------------------------------------------


class TestBlenderScript:
    def test_script_is_valid_python(self):
        body = _box_body()
        result = translate_body_to_gltf_plus_materials(body)
        compile(result["blender_script"], "<gen>", "exec")

    def test_script_mentions_principled_and_glass_bsdfs(self):
        body = _box_body()
        faces = body.all_faces()
        result = translate_body_to_gltf_plus_materials(
            body,
            materials={
                faces[0].id: "diamond",       # glass BSDF
                faces[1].id: "18k_yellow",    # principled
            },
        )
        script = result["blender_script"]
        assert "ShaderNodeBsdfPrincipled" in script
        assert "ShaderNodeBsdfGlass" in script
        assert "Dispersion" in script

    def test_script_imports_bpy_and_gltf(self):
        body = _box_body()
        result = translate_body_to_gltf_plus_materials(body)
        script = result["blender_script"]
        assert "import bpy" in script
        assert "bpy.ops.import_scene.gltf" in script

    def test_script_embeds_camera_position(self):
        body = _box_body()
        result = translate_body_to_gltf_plus_materials(
            body, camera=Camera(position=(0.0, 0.0, 5.0)),
        )
        script = result["blender_script"]
        # SCENE_CONFIG = json.loads(r"""...""")
        json_start = script.find('json.loads(r"""') + len('json.loads(r"""')
        json_end = script.find('""")', json_start)
        cfg = json.loads(script[json_start:json_end])
        assert cfg["camera"]["position"] == [0.0, 0.0, 5.0]
        assert cfg["camera"]["target"] == [0.0, 0.0, 0.0]

    def test_script_embeds_camera_look_at_helper(self):
        body = _box_body()
        result = translate_body_to_gltf_plus_materials(
            body, camera=Camera(position=(0.0, 0.0, 5.0),
                                target=(0.0, 0.0, 0.0)),
        )
        script = result["blender_script"]
        # The script must contain a look-at helper that maps the
        # configured (pos, tgt, up) into camera.matrix_world.
        assert "_look_at_matrix" in script
        assert "matrix_world" in script

    def test_script_embeds_lights(self):
        body = _box_body()
        result = translate_body_to_gltf_plus_materials(
            body, lights=[
                Light(type="sun", position=(1, 1, 1), energy=2.0,
                      name="key"),
                Light(type="area", position=(-2, 2, 3), energy=500.0,
                      name="fill", size=2.5),
            ],
        )
        script = result["blender_script"]
        # SUN / AREA wiring uses bpy.data.lights.new(...type=...)
        assert 'SUN' in script
        assert 'AREA' in script
        json_start = script.find('json.loads(r"""') + len('json.loads(r"""')
        json_end = script.find('""")', json_start)
        cfg = json.loads(script[json_start:json_end])
        assert [light["name"] for light in cfg["lights"]] == ["key", "fill"]

    def test_script_embeds_render_output_path(self):
        body = _box_body()
        result = translate_body_to_gltf_plus_materials(
            body, output=RenderOutput(path="/tmp/foo.png",
                                       resolution=(640, 480),
                                       samples=64),
        )
        script = result["blender_script"]
        assert "/tmp/foo.png" in script
        json_start = script.find('json.loads(r"""') + len('json.loads(r"""')
        json_end = script.find('""")', json_start)
        cfg = json.loads(script[json_start:json_end])
        assert cfg["render"]["path"] == "/tmp/foo.png"
        assert cfg["render"]["resolution"] == [640, 480]
        assert cfg["render"]["samples"] == 64

    def test_script_carries_gem_sellmeier(self):
        body = _gem_face_body()
        faces = body.all_faces()
        result = translate_body_to_gltf_plus_materials(
            body, materials={faces[0].id: "diamond"},
        )
        script = result["blender_script"]
        # The script must embed the sellmeier coefficient list inside the
        # JSON config so the Cycles worker can later build a dispersive
        # IOR network if a custom caustic solver is wired in.
        assert "sellmeier" in script

    def test_script_assigns_materials_by_slot(self):
        body = _box_body()
        result = translate_body_to_gltf_plus_materials(body)
        script = result["blender_script"]
        # An assignment helper that walks objects and reads back the
        # material_slot custom property to attach the right material.
        assert "_assign_materials" in script


# ---------------------------------------------------------------------------
# Camera / light wiring
# ---------------------------------------------------------------------------


class TestCameraWiring:
    def test_default_camera_position(self):
        body = _box_body()
        result = translate_body_to_gltf_plus_materials(body)
        script = result["blender_script"]
        json_start = script.find('json.loads(r"""') + len('json.loads(r"""')
        json_end = script.find('""")', json_start)
        cfg = json.loads(script[json_start:json_end])
        assert cfg["camera"]["position"] == [0.0, 0.0, 5.0]

    def test_custom_camera_position_is_propagated(self):
        body = _box_body()
        custom_cam = Camera(position=(3.0, -4.0, 7.5),
                             target=(0.5, 0.5, 0.0),
                             fov_deg=22.0)
        result = translate_body_to_gltf_plus_materials(body, camera=custom_cam)
        script = result["blender_script"]
        json_start = script.find('json.loads(r"""') + len('json.loads(r"""')
        json_end = script.find('""")', json_start)
        cfg = json.loads(script[json_start:json_end])
        assert cfg["camera"]["position"] == [3.0, -4.0, 7.5]
        assert cfg["camera"]["target"] == [0.5, 0.5, 0.0]
        assert cfg["camera"]["fov_rad"] == pytest.approx(
            math.radians(22.0), abs=1e-9)


# ---------------------------------------------------------------------------
# Different Body topologies
# ---------------------------------------------------------------------------


class TestNonPlanarBodies:
    def test_cylinder_body_translates(self):
        body = make_cylinder(radius=1.0, height=2.0)
        result = translate_body_to_gltf_plus_materials(body)
        assert result["ok"] is True
        assert result["face_count"] == 3   # side + 2 caps
        # parse glb back
        gltf = parse_glb_header(result["gltf_bytes"])["json"]
        assert len(gltf["meshes"]) == 3

    def test_sphere_body_translates(self):
        body = make_sphere(radius=1.0)
        result = translate_body_to_gltf_plus_materials(body)
        assert result["ok"] is True
        assert result["face_count"] == 1
        gltf = parse_glb_header(result["gltf_bytes"])["json"]
        # sphere face must produce a non-empty mesh
        mesh = gltf["meshes"][0]
        pos_acc = gltf["accessors"][mesh["primitives"][0]["attributes"]["POSITION"]]
        assert pos_acc["count"] > 0

    def test_tetra_body_translates(self):
        body = make_tetra()
        result = translate_body_to_gltf_plus_materials(body)
        assert result["ok"] is True
        assert result["face_count"] == 4
        gltf = parse_glb_header(result["gltf_bytes"])["json"]
        assert len(gltf["meshes"]) == 4


# ---------------------------------------------------------------------------
# Aabb / position bounds preserved in glTF
# ---------------------------------------------------------------------------


class TestAabbAndBounds:
    def test_position_aabb_present_on_box(self):
        body = _box_body(size=(2.0, 2.0, 2.0))
        result = translate_body_to_gltf_plus_materials(body)
        gltf = parse_glb_header(result["gltf_bytes"])["json"]
        for mesh in gltf["meshes"]:
            pos_acc = gltf["accessors"][mesh["primitives"][0]["attributes"]["POSITION"]]
            assert "min" in pos_acc and "max" in pos_acc
            for mn, mx in zip(pos_acc["min"], pos_acc["max"]):
                assert mn <= mx


# ---------------------------------------------------------------------------
# Material kind dispatch
# ---------------------------------------------------------------------------


class TestMaterialKindDispatch:
    def test_kind_classification(self):
        assert material_kind("diamond") == "gem"
        assert material_kind("18k_yellow") == "metal"
        assert material_kind("abs") == "plastic"
        assert material_kind("pearl") == "organic"
        assert material_kind("definitely_not_real") == "unknown"
