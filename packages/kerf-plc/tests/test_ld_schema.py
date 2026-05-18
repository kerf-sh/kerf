"""
tests/test_ld_schema.py — Ladder Diagram schema / data model tests.

Covers:
  T1  load() / dump() round-trip for a valid program
  T2  validation errors for structural problems
  T3  element type constants
  T4  VariableDecl, Rung, LadderProgram dataclasses
"""
from __future__ import annotations

import json

import pytest

from kerf_plc.ld.schema import (
    ALL_ELEMENT_TYPES,
    CONTACT_TYPES,
    COIL_TYPES,
    Element,
    LadderProgram,
    Rung,
    VariableDecl,
    dump,
    load,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_LD = {
    "program": "StartStopLatch",
    "variables": [
        {"name": "start_pb",  "type": "BOOL", "dir": "input"},
        {"name": "stop_pb",   "type": "BOOL", "dir": "input"},
        {"name": "motor_run", "type": "BOOL", "dir": "output"},
    ],
    "rungs": [
        {
            "label": "Rung 0",
            "comment": "start latch",
            "branches": [
                [
                    {"type": "contact_no", "var": "start_pb"},
                    {"type": "contact_nc", "var": "stop_pb"},
                ]
            ],
            "output": {"type": "coil", "var": "motor_run"},
        }
    ],
}

TIMER_LD = {
    "program": "TimerDemo",
    "variables": [
        {"name": "sensor_A", "type": "BOOL", "dir": "input"},
    ],
    "rungs": [
        {
            "label": "Timer rung",
            "branches": [
                [{"type": "contact_no", "var": "sensor_A"}]
            ],
            "output": {
                "type": "fb_call",
                "fb_type": "TON",
                "fb_instance": "Timer1",
                "fb_inputs": {"PT": "T#5s"},
            },
        }
    ],
}


# ---------------------------------------------------------------------------
# T1 — round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_load_returns_ladder_program(self):
        prog = load(VALID_LD)
        assert isinstance(prog, LadderProgram)

    def test_program_name_preserved(self):
        prog = load(VALID_LD)
        assert prog.program == "StartStopLatch"

    def test_variables_loaded(self):
        prog = load(VALID_LD)
        assert len(prog.variables) == 3
        assert prog.variables[0].name == "start_pb"
        assert prog.variables[0].dir == "input"

    def test_rungs_loaded(self):
        prog = load(VALID_LD)
        assert len(prog.rungs) == 1
        rung = prog.rungs[0]
        assert rung.label == "Rung 0"
        assert rung.comment == "start latch"

    def test_branches_loaded(self):
        prog = load(VALID_LD)
        rung = prog.rungs[0]
        assert len(rung.branches) == 1
        branch = rung.branches[0]
        assert len(branch) == 2
        assert branch[0].type == "contact_no"
        assert branch[0].var == "start_pb"
        assert branch[1].type == "contact_nc"

    def test_output_coil_loaded(self):
        prog = load(VALID_LD)
        out = prog.rungs[0].output
        assert out is not None
        assert out.type == "coil"
        assert out.var == "motor_run"

    def test_dump_produces_dict(self):
        prog = load(VALID_LD)
        d = dump(prog)
        assert isinstance(d, dict)
        assert d["program"] == "StartStopLatch"

    def test_dump_preserves_rungs(self):
        prog = load(VALID_LD)
        d = dump(prog)
        assert len(d["rungs"]) == 1
        assert d["rungs"][0]["label"] == "Rung 0"
        assert d["rungs"][0]["output"]["type"] == "coil"

    def test_dump_is_json_serialisable(self):
        prog = load(VALID_LD)
        d = dump(prog)
        # Must not raise
        json.dumps(d)

    def test_round_trip_preserves_data(self):
        prog = load(VALID_LD)
        d = dump(prog)
        prog2 = load(d)
        assert prog2.program == prog.program
        assert len(prog2.rungs) == len(prog.rungs)
        assert prog2.rungs[0].branches[0][0].var == "start_pb"

    def test_fb_call_round_trip(self):
        prog = load(TIMER_LD)
        out = prog.rungs[0].output
        assert out.type == "fb_call"
        assert out.fb_type == "TON"
        assert out.fb_instance == "Timer1"
        assert out.fb_inputs.get("PT") == "T#5s"
        d = dump(prog)
        assert d["rungs"][0]["output"]["fb_type"] == "TON"

    def test_parallel_branches(self):
        ld = {
            "program": "ParallelTest",
            "variables": [],
            "rungs": [
                {
                    "branches": [
                        [{"type": "contact_no", "var": "A"}],
                        [{"type": "contact_no", "var": "B"}],
                    ],
                    "output": {"type": "coil", "var": "Y"},
                }
            ],
        }
        prog = load(ld)
        assert len(prog.rungs[0].branches) == 2


# ---------------------------------------------------------------------------
# T2 — validation errors
# ---------------------------------------------------------------------------

class TestValidation:
    def test_empty_branches_raises(self):
        bad = {**VALID_LD, "rungs": [{"branches": [], "output": {"type": "coil", "var": "x"}}]}
        with pytest.raises(ValueError, match="no branches"):
            load(bad)

    def test_coil_inside_branch_raises(self):
        bad = {
            "program": "X",
            "variables": [],
            "rungs": [
                {
                    "branches": [
                        [{"type": "coil", "var": "y"}]   # wrong: coil in branch
                    ],
                    "output": {"type": "coil", "var": "z"},
                }
            ],
        }
        with pytest.raises(ValueError, match="coil"):
            load(bad)

    def test_contact_as_output_raises(self):
        bad = {
            "program": "X",
            "variables": [],
            "rungs": [
                {
                    "branches": [[{"type": "contact_no", "var": "a"}]],
                    "output": {"type": "contact_no", "var": "b"},  # wrong
                }
            ],
        }
        with pytest.raises(ValueError, match="contact"):
            load(bad)

    def test_missing_program_name_raises(self):
        bad = {**VALID_LD, "program": ""}
        with pytest.raises(ValueError, match="program name"):
            load(bad)

    def test_fb_call_missing_fb_type_raises(self):
        bad = {
            "program": "X",
            "variables": [],
            "rungs": [
                {
                    "branches": [[{"type": "contact_no", "var": "a"}]],
                    "output": {
                        "type": "fb_call",
                        "fb_type": "",        # missing
                        "fb_instance": "T1",
                    },
                }
            ],
        }
        with pytest.raises(ValueError, match="fb_type"):
            load(bad)

    def test_fb_call_missing_instance_raises(self):
        bad = {
            "program": "X",
            "variables": [],
            "rungs": [
                {
                    "branches": [[{"type": "contact_no", "var": "a"}]],
                    "output": {
                        "type": "fb_call",
                        "fb_type": "TON",
                        "fb_instance": "",    # missing
                    },
                }
            ],
        }
        with pytest.raises(ValueError, match="fb_instance"):
            load(bad)


# ---------------------------------------------------------------------------
# T3 — element type constants
# ---------------------------------------------------------------------------

class TestElementTypes:
    def test_contact_types_set(self):
        assert "contact_no" in CONTACT_TYPES
        assert "contact_nc" in CONTACT_TYPES
        assert "contact_pos" in CONTACT_TYPES
        assert "contact_neg" in CONTACT_TYPES
        assert "coil" not in CONTACT_TYPES

    def test_coil_types_set(self):
        assert "coil" in COIL_TYPES
        assert "coil_set" in COIL_TYPES
        assert "coil_reset" in COIL_TYPES
        assert "contact_no" not in COIL_TYPES

    def test_all_element_types_superset(self):
        assert CONTACT_TYPES.issubset(ALL_ELEMENT_TYPES)
        assert COIL_TYPES.issubset(ALL_ELEMENT_TYPES)
        assert "fb_call" in ALL_ELEMENT_TYPES


# ---------------------------------------------------------------------------
# T4 — dataclass construction
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_element_defaults(self):
        e = Element(type="contact_no")
        assert e.var == ""
        assert e.fb_type == ""
        assert e.fb_inputs == {}

    def test_element_validate_no_var(self):
        e = Element(type="contact_no", var="")
        errs = e.validate()
        assert any("var" in err for err in errs)

    def test_element_validate_unknown_type(self):
        e = Element(type="unknown_type", var="x")
        errs = e.validate()
        assert any("unknown element type" in err for err in errs)

    def test_rung_defaults(self):
        r = Rung()
        assert r.label == ""
        assert r.branches == []
        assert r.output is None

    def test_var_decl_defaults(self):
        v = VariableDecl(name="x")
        assert v.type == "BOOL"
        assert v.dir == "local"
