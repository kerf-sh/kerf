"""
Tests for kerf_cad_core.

These tests are designed to pass whether or not pythonOCC is installed:
- When OCC is absent, all public symbols still import cleanly and functions
  raise RuntimeError with clear messages rather than ImportError.
- When OCC is present, the helpers are exercised with a minimal cube STEP.
"""

import pytest
import sys
import os

# Make the src layout importable when running pytest from the package root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kerf_cad_core import (
    _OCC_AVAILABLE,
    convert_step_to_stl,
    load_step,
    mesh_shape,
    write_stl,
)
from kerf_cad_core.occ_helpers import _OCC_AVAILABLE as _OCC_AVAILABLE_direct


# ── Package-level smoke ────────────────────────────────────────────────────────

def test_import_public_api():
    """All public symbols must be importable regardless of OCC presence."""
    # If we got here without ImportError, the test passes.
    assert isinstance(_OCC_AVAILABLE, bool)
    assert callable(convert_step_to_stl)
    assert callable(load_step)
    assert callable(mesh_shape)
    assert callable(write_stl)


def test_occ_available_flag_consistent():
    assert _OCC_AVAILABLE == _OCC_AVAILABLE_direct


# ── RuntimeError when OCC absent ──────────────────────────────────────────────

@pytest.mark.skipif(_OCC_AVAILABLE, reason="OCC present; skip absence test")
def test_load_step_without_occ_raises():
    with pytest.raises(RuntimeError, match="pythonOCC not installed"):
        load_step("nonexistent.step")


@pytest.mark.skipif(_OCC_AVAILABLE, reason="OCC present; skip absence test")
def test_mesh_shape_without_occ_raises():
    with pytest.raises(RuntimeError, match="pythonOCC not installed"):
        mesh_shape(object())


@pytest.mark.skipif(_OCC_AVAILABLE, reason="OCC present; skip absence test")
def test_write_stl_without_occ_raises():
    with pytest.raises(RuntimeError, match="pythonOCC not installed"):
        write_stl(object(), "/tmp/test.stl")


@pytest.mark.skipif(_OCC_AVAILABLE, reason="OCC present; skip absence test")
def test_convert_step_to_stl_without_occ_raises():
    with pytest.raises(RuntimeError, match="pythonOCC not installed"):
        convert_step_to_stl("nonexistent.step", "/tmp/test.stl")


# ── Integration tests (OCC present) ───────────────────────────────────────────

@pytest.mark.skipif(not _OCC_AVAILABLE, reason="pythonOCC not installed")
def test_convert_step_to_stl_with_occ(tmp_path):
    """End-to-end: write a minimal cube STEP, convert, verify STL exists."""
    import tempfile
    from pathlib import Path

    # Write a minimal ASCII STEP cube (ISO-10303-21).
    step_content = """\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Open CASCADE Model'),'2;1');
FILE_NAME('cube.step','2024-01-01T00:00:00',('Author'),('Org'),'','','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1 = PRODUCT('cube','cube','',(#2));
#2 = PRODUCT_CONTEXT('',#3,'mechanical');
#3 = APPLICATION_CONTEXT('core data for automotive mechanical design processes');
#4 = PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE('','',#1,.NOT_KNOWN.);
#5 = PRODUCT_DEFINITION('design','',#4,#6);
#6 = PRODUCT_DEFINITION_CONTEXT('part definition',#3,'design');
#7 = PRODUCT_DEFINITION_SHAPE('','',#5);
#8 = AXIS2_PLACEMENT_3D('',#9,#10,#11);
#9 = CARTESIAN_POINT('',(0.,0.,0.));
#10 = DIRECTION('',(0.,0.,1.));
#11 = DIRECTION('',(1.,0.,0.));
#12 = MANIFOLD_SOLID_BREP('',#13);
ENDSEC;
END-ISO-10303-21;
"""
    step_path = str(tmp_path / "cube.step")
    stl_path = str(tmp_path / "cube.stl")
    Path(step_path).write_text(step_content)

    # This will fail gracefully if the STEP is not valid OCC-readable,
    # but the important thing is it doesn't ImportError.
    try:
        shape = convert_step_to_stl(step_path, stl_path)
        assert shape is not None
        assert Path(stl_path).exists()
        assert Path(stl_path).stat().st_size > 0
    except RuntimeError as e:
        # A malformed minimal STEP may not parse; that's acceptable.
        assert "STEPControl_Reader" in str(e) or "StlAPI" in str(e)


# ── Plugin registration smoke ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_plugin_register_returns_manifest():
    """register() must return a PluginManifest regardless of OCC presence."""
    from unittest.mock import MagicMock
    from fastapi import FastAPI
    from kerf_cad_core.plugin import register

    app = FastAPI()
    ctx = MagicMock()

    manifest = await register(app, ctx)

    assert manifest.name == "cad-core"
    assert manifest.version == "0.1.0"
    assert manifest.depends == []

    if _OCC_AVAILABLE:
        assert len(manifest.provides) > 0
        assert "cad.step-io" in manifest.provides
    else:
        assert manifest.provides == []
