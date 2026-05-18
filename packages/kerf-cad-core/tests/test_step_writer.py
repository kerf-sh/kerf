"""Pytest suite for kerf_cad_core.io.step_writer (T-157).

Oracle tests
------------
1. A 1×1×1 cube serialised to text parses as a valid ISO 10303-21
   (Part 21) file, containing:
   - ISO-10303-21 header / ENDSEC / END-ISO-10303-21 delimiters
   - FILE_SCHEMA referencing AUTOMOTIVE_DESIGN
   - exactly 6 ADVANCED_FACE lines

2. Calling write() twice on the same Body yields byte-identical output
   (deterministic entity IDs).

3. write(body, path=...) writes the same bytes to disk.

4. A cylinder body (3 faces) serialises with exactly 3 ADVANCED_FACE
   entries.

Integration test (gated on T-156 step_reader)
---------------------------------------------
If kerf_cad_core.io.step_reader is available, a round-trip test
(write → parse back) is attempted.
"""

import os
import re
import tempfile

import pytest

from kerf_cad_core.geom.brep import make_box, make_cylinder
from kerf_cad_core.io.step_writer import write


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_part21(text: str) -> dict:
    """Very lightweight Part 21 parser — returns structural metadata."""
    result = {
        "has_header": text.strip().startswith("ISO-10303-21;"),
        "has_footer": text.strip().endswith("END-ISO-10303-21;"),
        "has_data_section": "DATA;" in text and "ENDSEC;" in text,
        "file_schema": re.search(r"FILE_SCHEMA\s*\((.+?)\)\s*;", text, re.DOTALL),
        "advanced_face_count": len(re.findall(r"=\s*ADVANCED_FACE\s*\(", text)),
        "manifold_solid_brep_count": len(re.findall(r"=\s*MANIFOLD_SOLID_BREP\s*\(", text)),
    }
    if result["file_schema"]:
        result["file_schema_text"] = result["file_schema"].group(1)
    return result


# ---------------------------------------------------------------------------
# Test: basic structure of a cube export
# ---------------------------------------------------------------------------

def test_cube_is_valid_part21():
    body = make_box(size=(1.0, 1.0, 1.0))
    text = write(body)

    info = _parse_part21(text)
    assert info["has_header"], "Missing ISO-10303-21 opening"
    assert info["has_footer"], "Missing END-ISO-10303-21 closing"
    assert info["has_data_section"], "Missing DATA / ENDSEC section"


def test_cube_has_automotive_design_schema():
    body = make_box(size=(1.0, 1.0, 1.0))
    text = write(body)

    info = _parse_part21(text)
    schema_text = info.get("file_schema_text", "")
    assert "AUTOMOTIVE_DESIGN" in schema_text, (
        f"Expected AUTOMOTIVE_DESIGN in FILE_SCHEMA, got: {schema_text!r}"
    )


def test_cube_has_exactly_6_advanced_faces():
    body = make_box(size=(1.0, 1.0, 1.0))
    text = write(body)

    info = _parse_part21(text)
    assert info["advanced_face_count"] == 6, (
        f"Expected 6 ADVANCED_FACE entries for a cube, got {info['advanced_face_count']}"
    )


def test_cube_has_manifold_solid_brep():
    body = make_box(size=(1.0, 1.0, 1.0))
    text = write(body)

    info = _parse_part21(text)
    assert info["manifold_solid_brep_count"] >= 1, (
        "Expected at least one MANIFOLD_SOLID_BREP entry"
    )


# ---------------------------------------------------------------------------
# Test: deterministic output
# ---------------------------------------------------------------------------

def test_write_is_deterministic():
    """Two calls on the same body must produce byte-identical output."""
    body = make_box(origin=(0.0, 0.0, 0.0), size=(2.0, 3.0, 4.0))
    text1 = write(body)
    text2 = write(body)
    assert text1 == text2, "write() is not deterministic: outputs differ"


def test_write_deterministic_different_sizes():
    """Determinism must hold for non-unit cubes as well."""
    body = make_box(size=(5.0, 10.0, 0.5))
    assert write(body) == write(body)


# ---------------------------------------------------------------------------
# Test: path argument writes correct content
# ---------------------------------------------------------------------------

def test_write_to_file():
    body = make_box(size=(1.0, 1.0, 1.0))
    text = write(body)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".step", delete=False) as fh:
        tmp_path = fh.name
    try:
        write(body, path=tmp_path)
        with open(tmp_path, "r", encoding="utf-8") as fh:
            disk_text = fh.read()
        assert disk_text == text, "Content written to disk differs from returned string"
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Test: cylinder (3 faces: 1 lateral + 2 caps)
# ---------------------------------------------------------------------------

def test_cylinder_has_3_advanced_faces():
    body = make_cylinder(radius=1.0, height=2.0)
    text = write(body)
    info = _parse_part21(text)
    assert info["advanced_face_count"] == 3, (
        f"Expected 3 ADVANCED_FACE entries for a cylinder, got {info['advanced_face_count']}"
    )


def test_cylinder_has_cylindrical_surface():
    body = make_cylinder(radius=1.0, height=2.0)
    text = write(body)
    assert "CYLINDRICAL_SURFACE" in text, (
        "Expected CYLINDRICAL_SURFACE entity in cylinder export"
    )


def test_cylinder_has_plane_surfaces():
    body = make_cylinder(radius=1.0, height=2.0)
    text = write(body)
    assert "=PLANE(" in text or "= PLANE(" in text, (
        "Expected PLANE entity for cylinder caps"
    )


# ---------------------------------------------------------------------------
# Test: entity IDs are ascending integers
# ---------------------------------------------------------------------------

def test_entity_ids_are_positive_integers():
    body = make_box(size=(1.0, 1.0, 1.0))
    text = write(body)
    # Extract all #N= lines from DATA section
    data_section = text.split("DATA;", 1)[-1].split("ENDSEC;", 1)[0]
    ids = [int(m.group(1)) for m in re.finditer(r"^#(\d+)\s*=", data_section, re.MULTILINE)]
    assert ids, "No entity IDs found in DATA section"
    assert ids == sorted(ids), "Entity IDs are not in ascending order"
    assert min(ids) >= 1, "Entity IDs must be >= 1"


# ---------------------------------------------------------------------------
# Test: entity line termination
# ---------------------------------------------------------------------------

def test_every_entity_line_ends_with_semicolon():
    body = make_box(size=(1.0, 1.0, 1.0))
    text = write(body)
    data_section = text.split("DATA;", 1)[-1].split("ENDSEC;", 1)[0]
    for line in data_section.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        assert line.endswith(";"), f"Entity line missing trailing semicolon: {line!r}"


# ---------------------------------------------------------------------------
# Integration test: round-trip via step_reader (T-156 gate)
# ---------------------------------------------------------------------------

try:
    from kerf_cad_core.io import step_reader as _step_reader  # noqa: F401
    _READER_AVAILABLE = True
except ImportError:
    _READER_AVAILABLE = False


@pytest.mark.skipif(
    not _READER_AVAILABLE,
    reason="step_reader (T-156) not yet integrated",
)
def test_roundtrip_cube():
    """Write a cube and read it back — face count must survive."""
    body = make_box(size=(1.0, 1.0, 1.0))
    text = write(body)
    recovered = _step_reader.read_string(text)  # type: ignore[attr-defined]
    assert len(recovered.all_faces()) == 6, (
        "Round-trip face count mismatch"
    )
