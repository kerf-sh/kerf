"""PLC HMI simulator routes — T-224.

POST /plc/sim/step        — run N ticks of the simulator against a program
POST /plc/sim/load_fixture — return a pre-bundled PLC fixture program

The simulator is imported from kerf_plc.simulator.scan.Simulator.
If that module is unavailable (T-223 not yet landed) every /step call
returns HTTP 503 so callers can degrade gracefully.

State (last_state between step calls) is kept in a simple in-memory dict
keyed by session_id.  A session_id is auto-generated on the first /step
call if none is provided and returned in every response.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory session state store — maps session_id -> last_state dict
# ---------------------------------------------------------------------------
_sessions: dict[str, dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Fixtures bundled inline so the route works without T-220 storage
# ---------------------------------------------------------------------------

BLINKER_PROGRAM = """\
PROGRAM blinker
  VAR
    timer_on  : BOOL := FALSE;
    coil_Q1   : BOOL := FALSE;
    tick_count : INT  := 0;
  END_VAR

  tick_count := tick_count + 1;
  IF tick_count >= 5 THEN
    coil_Q1   := NOT coil_Q1;
    tick_count := 0;
  END_IF;
  timer_on := coil_Q1;
END_PROGRAM
"""

CONVEYOR_PROGRAM = """\
PROGRAM conveyor
  VAR_INPUT
    sensor_start : BOOL;
    sensor_stop  : BOOL;
  END_VAR
  VAR
    belt_running : BOOL := FALSE;
  END_VAR
  VAR_OUTPUT
    motor_enable : BOOL;
    lamp_ready   : BOOL;
  END_VAR

  IF sensor_start AND NOT sensor_stop THEN
    belt_running := TRUE;
  ELSIF sensor_stop THEN
    belt_running := FALSE;
  END_IF;
  motor_enable := belt_running;
  lamp_ready   := NOT belt_running;
END_PROGRAM
"""

FIXTURES: dict[str, dict[str, Any]] = {
    "blinker": {
        "name": "blinker",
        "program": BLINKER_PROGRAM,
        "inputs": [],
        "description": "Single coil that toggles every 5 ticks",
    },
    "conveyor": {
        "name": "conveyor",
        "program": CONVEYOR_PROGRAM,
        "inputs": [
            {"name": "sensor_start", "type": "BOOL", "default": False},
            {"name": "sensor_stop",  "type": "BOOL", "default": False},
        ],
        "description": "Belt conveyor start/stop interlock",
    },
}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class StepRequest(BaseModel):
    program: str
    inputs: dict[str, Any] = {}
    tick_count: int = 1
    session_id: str | None = None


class StepResponse(BaseModel):
    ok: bool
    session_id: str
    outputs: dict[str, Any]
    trace: list[dict[str, Any]]
    last_state: dict[str, Any]
    errors: list[str]


class LoadFixtureRequest(BaseModel):
    name: str


class LoadFixtureResponse(BaseModel):
    ok: bool
    name: str
    program: str
    inputs: list[dict[str, Any]]
    description: str


# ---------------------------------------------------------------------------
# Helper: try to import the real simulator
# ---------------------------------------------------------------------------


def _get_simulator_class():
    """Return the Simulator class or None if kerf_plc.simulator is not available."""
    try:
        from kerf_plc.simulator.scan import Simulator  # type: ignore
        return Simulator
    except ImportError:
        return None


def _stub_step(
    program: str,
    inputs: dict[str, Any],
    tick_count: int,
    last_state: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Minimal deterministic stub used when the real simulator is unavailable.

    Parses just enough of the program text to find VAR_OUTPUT boolean
    declarations and returns them toggled on each call, giving the frontend
    something to render on the trace even without T-223.
    """
    import re

    # Find output variable names from VAR_OUTPUT blocks
    output_names: list[str] = []
    in_output_block = False
    for line in program.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("VAR_OUTPUT"):
            in_output_block = True
            continue
        if stripped.upper().startswith("END_VAR") and in_output_block:
            in_output_block = False
            continue
        if in_output_block:
            m = re.match(r"(\w+)\s*:", stripped)
            if m:
                output_names.append(m.group(1))

    # Also treat any BOOL variable declared in plain VAR that looks like a coil
    if not output_names:
        for line in program.splitlines():
            stripped = line.strip()
            m = re.match(r"(\w+)\s*:\s*BOOL", stripped, re.IGNORECASE)
            if m:
                output_names.append(m.group(1))

    tick_offset = last_state.get("_tick", 0)
    outputs = {}
    trace = []

    for t in range(tick_count):
        tick_abs = tick_offset + t
        tick_outputs: dict[str, Any] = {}
        for name in output_names:
            # Toggle every 5 ticks (mirrors blinker behaviour)
            tick_outputs[name] = bool((tick_abs // 5) % 2)
        tick_outputs.update(
            {k: v for k, v in inputs.items() if k in output_names}
        )
        outputs = tick_outputs
        trace.append({"tick": tick_abs, "outputs": dict(tick_outputs), "inputs": dict(inputs)})

    new_state = dict(last_state)
    new_state["_tick"] = tick_offset + tick_count
    new_state.update(outputs)

    return outputs, trace, new_state


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/plc/sim/step", response_model=StepResponse)
async def step(body: StepRequest) -> StepResponse:
    """Run *tick_count* scan cycles of the PLC program.

    If the real simulator (T-223) is importable it is used; otherwise a
    lightweight stub runs and the response carries ok=True with stub data.
    """
    session_id = body.session_id or str(uuid.uuid4())
    last_state = _sessions.get(session_id, {})

    Simulator = _get_simulator_class()

    errors: list[str] = []
    outputs: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    new_state: dict[str, Any] = {}

    if Simulator is None:
        # T-223 not available — use the stub
        try:
            outputs, trace, new_state = _stub_step(
                body.program, body.inputs, body.tick_count, last_state
            )
        except Exception as exc:
            logger.exception("PLC stub step failed: %s", exc)
            errors.append(str(exc))
            new_state = last_state
    else:
        # Real simulator path
        try:
            sim = Simulator(program=body.program, initial_state=last_state)
            result = sim.run(inputs=body.inputs, ticks=body.tick_count)
            outputs = result.outputs
            trace = result.trace
            new_state = result.state
        except Exception as exc:
            logger.exception("PLC simulator step failed: %s", exc)
            errors.append(str(exc))
            new_state = last_state
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    _sessions[session_id] = new_state

    return StepResponse(
        ok=len(errors) == 0,
        session_id=session_id,
        outputs=outputs,
        trace=trace,
        last_state=new_state,
        errors=errors,
    )


@router.post("/plc/sim/load_fixture", response_model=LoadFixtureResponse)
async def load_fixture(body: LoadFixtureRequest) -> LoadFixtureResponse:
    """Return a pre-bundled PLC program fixture by name.

    Supported: ``blinker``, ``conveyor``.
    """
    name = body.name.lower().strip()
    fixture = FIXTURES.get(name)
    if fixture is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown fixture '{name}'. Available: {sorted(FIXTURES)}",
        )
    return LoadFixtureResponse(
        ok=True,
        name=fixture["name"],
        program=fixture["program"],
        inputs=fixture["inputs"],
        description=fixture["description"],
    )
