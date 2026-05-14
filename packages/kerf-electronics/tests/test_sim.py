"""
Tests for kerf_electronics/tools/sim.py — SPICE simulation tools.

sim.py handlers require a live DB pool (ctx.pool.fetchrow), so we only
test spec shape, arg validation paths, and tool registration here.  The
actual DB round-trip is an integration concern.
"""
import json
import unittest

# Import the module to trigger @register decorators and populate Registry.
import kerf_electronics.tools.sim  # noqa: F401

from tools.registry import Registry


async def call_tool(name, payload, ctx=None):
    tool = next(t for t in Registry if t.spec.name == name)
    return json.loads(await tool.run(ctx, json.dumps(payload).encode()))


class TestSimToolsRegistered(unittest.IsolatedAsyncioTestCase):

    async def test_run_simulation_registered(self):
        names = {t.spec.name for t in Registry}
        self.assertIn("run_simulation", names)

    async def test_sim_job_status_registered(self):
        names = {t.spec.name for t in Registry}
        self.assertIn("sim_job_status", names)

    async def test_run_simulation_spec_has_required_fields(self):
        tool = next(t for t in Registry if t.spec.name == "run_simulation")
        required = tool.spec.input_schema.get("required", [])
        self.assertIn("circuit_file_id", required)
        self.assertIn("analysis", required)

    async def test_sim_job_status_spec_has_file_id(self):
        tool = next(t for t in Registry if t.spec.name == "sim_job_status")
        required = tool.spec.input_schema.get("required", [])
        self.assertIn("file_id", required)


class TestSimArgValidation(unittest.IsolatedAsyncioTestCase):
    """
    Validate that bad args return error payloads without touching the DB.
    We pass None as ctx — handlers fail before any DB call when args are bad.
    """

    async def test_missing_circuit_file_id_is_error(self):
        result = await call_tool("run_simulation", {
            "circuit_file_id": "",
            "analysis": {"type": "tran"},
        })
        self.assertIn("error", result)

    async def test_missing_analysis_type_is_error(self):
        result = await call_tool("run_simulation", {
            "circuit_file_id": "file-abc",
            "analysis": {},
        })
        self.assertIn("error", result)

    async def test_missing_file_id_for_status_is_error(self):
        result = await call_tool("sim_job_status", {"file_id": ""})
        self.assertIn("error", result)

    async def test_invalid_json_is_error(self):
        tool = next(t for t in Registry if t.spec.name == "run_simulation")
        result = json.loads(await tool.run(None, b"not-json"))
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
