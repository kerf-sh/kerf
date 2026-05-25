"""
Dispatch tests for mold_check_moldability, mold_generate_parting_surface,
and mold_draft_angle_per_face — previously only conditionally accessible.
"""

from __future__ import annotations

import asyncio
import json
import pytest

from kerf_mold.tools import (
    _CHECK_SPEC, run_mold_check_moldability,
    _PARTING_SPEC, run_mold_generate_parting_surface,
    _DRAFT_SPEC, run_mold_draft_angle_per_face,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _Ctx:
    pass


CTX = _Ctx()

# ---------------------------------------------------------------------------
# Minimal geometry helpers
# ---------------------------------------------------------------------------

def _square_face(z: float = 0.0, face_id: str = "f0"):
    """Simple planar face with upward normal."""
    return {
        "vertices": [[0, 0, z], [10, 0, z], [10, 10, z], [0, 10, z]],
        "normal": [0, 0, 1],
        "face_id": face_id,
    }


def _square_parting_line():
    return [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]]


# ---------------------------------------------------------------------------
# Spec sanity
# ---------------------------------------------------------------------------

class TestSpecs:
    def test_check_spec_name(self):
        assert _CHECK_SPEC.name == "mold_check_moldability"

    def test_parting_spec_name(self):
        assert _PARTING_SPEC.name == "mold_generate_parting_surface"

    def test_draft_spec_name(self):
        assert _DRAFT_SPEC.name == "mold_draft_angle_per_face"


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

class TestPluginRegistration:
    def test_all_four_tools_registered(self):
        from kerf_mold.plugin import register

        class _MockReg:
            def __init__(self):
                self.registered = {}
            def register(self, name, spec, handler):
                self.registered[name] = (spec, handler)

        class _MockCtx:
            def __init__(self):
                self.tools = _MockReg()

        import asyncio
        from fastapi import FastAPI
        app = FastAPI()
        ctx = _MockCtx()

        async def _go():
            return await register(app, ctx)

        asyncio.get_event_loop().run_until_complete(_go())

        for name in (
            "mold_check_moldability",
            "mold_generate_parting_surface",
            "mold_draft_angle_per_face",
            "mold_cooling_analysis",
        ):
            assert name in ctx.tools.registered, f"Missing: {name}"


# ---------------------------------------------------------------------------
# mold_check_moldability
# ---------------------------------------------------------------------------

class TestMoldCheckMoldability:
    def test_basic_check(self):
        args = json.dumps({
            "core_faces": [_square_face(0.0, "core_0")],
            "cavity_faces": [_square_face(5.0, "cav_0")],
            "parting_line_points": _square_parting_line(),
            "pull_direction": [0, 0, 1],
        }).encode()
        result = json.loads(_run(run_mold_check_moldability(CTX, args)))
        assert "ok" in result

    def test_missing_parting_line_returns_error(self):
        args = json.dumps({
            "core_faces": [],
            "cavity_faces": [],
            "pull_direction": [0, 0, 1],
        }).encode()
        result = json.loads(_run(run_mold_check_moldability(CTX, args)))
        assert result.get("ok") is False or "error" in result

    def test_invalid_json_returns_error(self):
        result = json.loads(_run(run_mold_check_moldability(CTX, b"not json")))
        assert result.get("ok") is False or "error" in result


# ---------------------------------------------------------------------------
# mold_generate_parting_surface
# ---------------------------------------------------------------------------

class TestMoldGeneratePartingSurface:
    def test_flat_style(self):
        args = json.dumps({
            "parting_line_points": _square_parting_line(),
            "style": "flat",
        }).encode()
        result = json.loads(_run(run_mold_generate_parting_surface(CTX, args)))
        assert result.get("ok") is True
        assert "vertices" in result

    def test_ruled_style(self):
        args = json.dumps({
            "parting_line_points": _square_parting_line(),
            "style": "ruled",
            "pull_direction": [0, 0, 1],
            "extrusion_depth_mm": 20.0,
        }).encode()
        result = json.loads(_run(run_mold_generate_parting_surface(CTX, args)))
        assert result.get("ok") is True

    def test_too_few_points_returns_error(self):
        args = json.dumps({
            "parting_line_points": [[0, 0, 0], [1, 0, 0]],  # only 2 points
        }).encode()
        result = json.loads(_run(run_mold_generate_parting_surface(CTX, args)))
        assert result.get("ok") is False or "error" in result


# ---------------------------------------------------------------------------
# mold_draft_angle_per_face
# ---------------------------------------------------------------------------

class TestMoldDraftAnglePerFace:
    def test_upward_facing_face_has_positive_draft(self):
        args = json.dumps({
            "faces": [_square_face(0.0)],
            "pull_direction": [0, 0, 1],
        }).encode()
        result = json.loads(_run(run_mold_draft_angle_per_face(CTX, args)))
        assert result.get("ok") is True
        results = result.get("results", [])
        assert len(results) == 1
        # Face normal = [0,0,1] aligned with pull [0,0,1] → max draft (90°)
        assert results[0]["draft_deg"] > 0

    def test_missing_faces_returns_error(self):
        args = json.dumps({
            "pull_direction": [0, 0, 1],
        }).encode()
        result = json.loads(_run(run_mold_draft_angle_per_face(CTX, args)))
        assert result.get("ok") is False or "error" in result
