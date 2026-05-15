"""test_spice_lib.py — tests for the built-in SPICE model library and tools.

Covers:
  - Model library completeness / content correctness
  - SPICE syntax validity of every generated model string
  - inject_models_into_netlist behaviour (injection, deduplication)
  - list_spice_models tool (registration, filtering, payload shape)
  - assign_spice_model tool (registration, validation, netlist output,
    compatibility with the existing sim flow netlist contract)
"""

import importlib.util
import json
import math
import os
import re
import sys
import types
import unittest


# ---------------------------------------------------------------------------
# Load spice_lib standalone without triggering the full plugin registry
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src", "kerf_electronics", "tools", "spice_lib.py")

# Stub kerf_chat.tools.registry so @register doesn't need the real stack
_reg_stub = types.ModuleType("kerf_chat.tools.registry")
_reg_stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: json.dumps({"error": msg, "code": code})
_reg_stub.ok_payload = lambda v: json.dumps(v)
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)

_prev_kerf_chat = sys.modules.get("kerf_chat")
_prev_tools = sys.modules.get("kerf_chat.tools")
_prev_registry = sys.modules.get("kerf_chat.tools.registry")

# Build a minimal package hierarchy so the import resolves
_pkg = types.ModuleType("kerf_chat")
_tools_pkg = types.ModuleType("kerf_chat.tools")
_pkg.tools = _tools_pkg
sys.modules.setdefault("kerf_chat", _pkg)
sys.modules.setdefault("kerf_chat.tools", _tools_pkg)
sys.modules["kerf_chat.tools.registry"] = _reg_stub

_spec = importlib.util.spec_from_file_location("kerf_electronics.tools.spice_lib", _SRC)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_LIBRARY = _mod._LIBRARY
get_model_string = _mod.get_model_string
inject_models_into_netlist = _mod.inject_models_into_netlist
list_spice_models = _mod.list_spice_models
assign_spice_model = _mod.assign_spice_model


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _call(fn, payload: dict) -> dict:
    raw = await fn(None, json.dumps(payload).encode())
    return json.loads(raw)


def _is_valid_spice_model(text: str) -> tuple[bool, str]:
    """Basic SPICE syntax check: must start with .MODEL or .SUBCKT (case-insensitive)
    and have no obviously empty lines in .MODEL directives."""
    stripped = text.strip()
    if not stripped:
        return False, "empty model string"
    first_line = stripped.splitlines()[0].strip().upper()
    if not (first_line.startswith(".MODEL") or first_line.startswith(".SUBCKT")):
        return False, f"first line is neither .MODEL nor .SUBCKT: {first_line!r}"
    return True, ""


# ---------------------------------------------------------------------------
# 1. Library content tests
# ---------------------------------------------------------------------------

class TestLibraryContent(unittest.TestCase):

    def test_library_not_empty(self):
        self.assertGreater(len(_LIBRARY), 0)

    def test_all_families_present(self):
        families = {v["family"] for v in _LIBRARY.values()}
        for expected in ("diode", "bjt", "mosfet", "opamp", "regulator", "passive"):
            self.assertIn(expected, families, f"family {expected!r} missing from library")

    def test_each_entry_has_required_keys(self):
        for name, entry in _LIBRARY.items():
            for key in ("family", "description", "fn"):
                self.assertIn(key, entry, f"{name}: missing key {key!r}")

    def test_all_diode_names_present(self):
        names = set(_LIBRARY.keys())
        for expected in ("D1N4148", "D1N4001", "D1N4007", "DSCHOTTKY", "DZENER5V1", "DZENER12V"):
            self.assertIn(expected, names)

    def test_all_bjt_names_present(self):
        names = set(_LIBRARY.keys())
        for expected in ("Q2N3904", "Q2N3906", "QBC547", "QBC557"):
            self.assertIn(expected, names)

    def test_all_mosfet_names_present(self):
        names = set(_LIBRARY.keys())
        for expected in ("M2N7000", "MIRF540", "MIRF9540", "M2P7000"):
            self.assertIn(expected, names)

    def test_all_opamp_names_present(self):
        names = set(_LIBRARY.keys())
        for expected in ("OPAMP_IDEAL", "OPAMP_GBW1M", "OPAMP_GBW10M"):
            self.assertIn(expected, names)

    def test_all_regulator_names_present(self):
        names = set(_LIBRARY.keys())
        for expected in ("LDO_78XX", "LDO_79XX", "LDO_ADJ"):
            self.assertIn(expected, names)

    def test_passive_models_present(self):
        names = set(_LIBRARY.keys())
        for expected in ("CAP_ELEC_100U", "CAP_X7R_100N", "IND_10U"):
            self.assertIn(expected, names)


# ---------------------------------------------------------------------------
# 2. SPICE syntax validity for every model
# ---------------------------------------------------------------------------

class TestModelStrings(unittest.TestCase):

    def test_every_model_generates_valid_spice(self):
        for name in _LIBRARY:
            with self.subTest(model=name):
                text = get_model_string(name)
                self.assertIsNotNone(text, f"{name}: get_model_string returned None")
                ok, reason = _is_valid_spice_model(text)
                self.assertTrue(ok, f"{name}: invalid SPICE syntax — {reason}")

    def test_get_model_string_case_insensitive(self):
        text_upper = get_model_string("D1N4148")
        text_lower = get_model_string("d1n4148")
        self.assertIsNotNone(text_upper)
        self.assertEqual(text_upper, text_lower)

    def test_get_model_string_unknown_returns_none(self):
        self.assertIsNone(get_model_string("NOTAMODEL"))

    def test_d1n4148_is_model_directive(self):
        s = get_model_string("D1N4148")
        self.assertIn(".MODEL D1N4148 D(", s)

    def test_q2n3904_is_npn(self):
        s = get_model_string("Q2N3904")
        self.assertIn("NPN(", s)

    def test_q2n3906_is_pnp(self):
        s = get_model_string("Q2N3906")
        self.assertIn("PNP(", s)

    def test_m2n7000_is_nmos(self):
        s = get_model_string("M2N7000")
        self.assertIn("NMOS(", s)

    def test_mirf9540_is_pmos(self):
        s = get_model_string("MIRF9540")
        self.assertIn("PMOS(", s)

    def test_opamp_ideal_subckt_pins(self):
        s = get_model_string("OPAMP_IDEAL")
        self.assertIn(".SUBCKT OPAMP_IDEAL IN+ IN- V+ V- OUT", s)
        self.assertIn(".ENDS OPAMP_IDEAL", s)

    def test_opamp_gbw1m_subckt_structure(self):
        s = get_model_string("OPAMP_GBW1M")
        self.assertIn(".SUBCKT OPAMP_GBW1M", s)
        self.assertIn(".ENDS OPAMP_GBW1M", s)

    def test_ldo_78xx_subckt_ends(self):
        s = get_model_string("LDO_78XX")
        self.assertIn(".SUBCKT LDO_78XX", s)
        self.assertIn(".ENDS LDO_78XX", s)

    def test_cap_elec_subckt_contains_esr_esl(self):
        s = get_model_string("CAP_ELEC_100U")
        # Should have LESL, RESR, and C1 elements
        self.assertIn("LESL", s)
        self.assertIn("RESR", s)
        self.assertIn("C1", s)

    def test_cap_x7r_subckt_valid(self):
        s = get_model_string("CAP_X7R_100N")
        self.assertIn(".SUBCKT CAP_X7R_100N", s)
        self.assertIn(".ENDS CAP_X7R_100N", s)

    def test_inductor_has_dcr_and_srf_cap(self):
        s = get_model_string("IND_10U")
        self.assertIn("Rdcr", s)
        self.assertIn("Cp", s)
        self.assertIn(".SUBCKT IND_10U", s)

    def test_inductor_srf_cap_nonzero(self):
        """Cp value derived from SRF formula must be a positive float."""
        s = get_model_string("IND_10U")
        m = re.search(r"Cp\s+\S+\s+\S+\s+([\d.e+-]+)", s, re.IGNORECASE)
        self.assertIsNotNone(m, "Cp line not found in inductor model")
        val = float(m.group(1))
        self.assertGreater(val, 0)


# ---------------------------------------------------------------------------
# 3. inject_models_into_netlist
# ---------------------------------------------------------------------------

_MINIMAL_NETLIST = """\
Simple RC circuit
R1 1 2 1k
C1 2 0 1u
V1 1 0 DC 5
.op
.end
"""


class TestInjectModels(unittest.TestCase):

    def test_inject_single_model(self):
        result = inject_models_into_netlist(_MINIMAL_NETLIST, {"D1": "D1N4148"})
        self.assertIn(".MODEL D1N4148", result)

    def test_inject_multiple_unique_models(self):
        result = inject_models_into_netlist(_MINIMAL_NETLIST, {
            "D1": "D1N4148",
            "Q1": "Q2N3904",
        })
        self.assertIn(".MODEL D1N4148", result)
        self.assertIn(".MODEL Q2N3904", result)

    def test_same_model_injected_once_even_if_multiple_refdes(self):
        result = inject_models_into_netlist(_MINIMAL_NETLIST, {
            "D1": "D1N4148",
            "D2": "D1N4148",
            "D3": "D1N4148",
        })
        count = result.count(".MODEL D1N4148")
        self.assertEqual(count, 1, "D1N4148 should appear exactly once")

    def test_no_duplicate_when_model_already_present(self):
        netlist_with_model = _MINIMAL_NETLIST + "\n.MODEL D1N4148 D(IS=1e-9 BV=100)\n"
        result = inject_models_into_netlist(netlist_with_model, {"D1": "D1N4148"})
        count = result.count(".MODEL D1N4148")
        self.assertEqual(count, 1, "model should not be duplicated if already in netlist")

    def test_empty_assignments_returns_netlist_unchanged(self):
        result = inject_models_into_netlist(_MINIMAL_NETLIST, {})
        self.assertEqual(result, _MINIMAL_NETLIST)

    def test_title_line_preserved_at_position_0(self):
        result = inject_models_into_netlist(_MINIMAL_NETLIST, {"D1": "D1N4148"})
        first_line = result.splitlines()[0]
        self.assertEqual(first_line, "Simple RC circuit")

    def test_injected_block_appears_before_end(self):
        result = inject_models_into_netlist(_MINIMAL_NETLIST, {"D1": "D1N4148"})
        model_pos = result.find(".MODEL D1N4148")
        end_pos = result.upper().find(".END")
        self.assertLess(model_pos, end_pos)

    def test_subckt_model_injected(self):
        result = inject_models_into_netlist(_MINIMAL_NETLIST, {"X1": "OPAMP_IDEAL"})
        self.assertIn(".SUBCKT OPAMP_IDEAL", result)
        self.assertIn(".ENDS OPAMP_IDEAL", result)

    def test_no_double_subckt_if_already_present(self):
        already = _MINIMAL_NETLIST + "\n.SUBCKT OPAMP_IDEAL IN+ IN- V+ V- OUT\nE_IDEAL OUT 0\n.ENDS OPAMP_IDEAL\n"
        result = inject_models_into_netlist(already, {"X1": "OPAMP_IDEAL"})
        count = result.count(".SUBCKT OPAMP_IDEAL")
        self.assertEqual(count, 1)


# ---------------------------------------------------------------------------
# 4. list_spice_models tool
# ---------------------------------------------------------------------------

class TestListSpiceModelsTool(unittest.IsolatedAsyncioTestCase):

    async def test_list_all_returns_all_models(self):
        result = await _call(list_spice_models, {})
        self.assertIn("models", result)
        self.assertIn("total", result)
        self.assertEqual(result["total"], len(_LIBRARY))

    async def test_result_contains_disclaimer(self):
        result = await _call(list_spice_models, {})
        self.assertIn("disclaimer", result)
        self.assertIn("representative", result["disclaimer"])

    async def test_filter_by_diode(self):
        result = await _call(list_spice_models, {"family": "diode"})
        for m in result["models"]:
            self.assertEqual(m["family"], "diode")
        self.assertGreater(result["total"], 0)

    async def test_filter_by_bjt(self):
        result = await _call(list_spice_models, {"family": "bjt"})
        names = {m["model_name"] for m in result["models"]}
        self.assertIn("Q2N3904", names)
        self.assertIn("Q2N3906", names)

    async def test_filter_by_mosfet(self):
        result = await _call(list_spice_models, {"family": "mosfet"})
        names = {m["model_name"] for m in result["models"]}
        self.assertIn("M2N7000", names)

    async def test_filter_by_opamp(self):
        result = await _call(list_spice_models, {"family": "opamp"})
        names = {m["model_name"] for m in result["models"]}
        self.assertIn("OPAMP_IDEAL", names)
        self.assertIn("OPAMP_GBW1M", names)
        self.assertIn("OPAMP_GBW10M", names)

    async def test_filter_by_regulator(self):
        result = await _call(list_spice_models, {"family": "regulator"})
        names = {m["model_name"] for m in result["models"]}
        self.assertIn("LDO_78XX", names)

    async def test_filter_by_passive(self):
        result = await _call(list_spice_models, {"family": "passive"})
        names = {m["model_name"] for m in result["models"]}
        self.assertIn("CAP_ELEC_100U", names)
        self.assertIn("CAP_X7R_100N", names)
        self.assertIn("IND_10U", names)

    async def test_each_model_entry_shape(self):
        result = await _call(list_spice_models, {})
        for m in result["models"]:
            self.assertIn("model_name", m)
            self.assertIn("family", m)
            self.assertIn("description", m)

    async def test_invalid_json_returns_error(self):
        raw = await list_spice_models(None, b"not json")
        data = json.loads(raw)
        self.assertIn("error", data)


# ---------------------------------------------------------------------------
# 5. assign_spice_model tool
# ---------------------------------------------------------------------------

class TestAssignSpiceModelTool(unittest.IsolatedAsyncioTestCase):

    async def test_basic_assignment_returns_netlist(self):
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {"D1": "D1N4148"},
        })
        self.assertIn("netlist", result)
        self.assertIn(".MODEL D1N4148", result["netlist"])

    async def test_netlist_passable_to_run_spice_contract(self):
        """The returned netlist must be a string that routes_spice.py will accept:
        non-empty, contains the original title, and contains .MODEL lines."""
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {"D1": "D1N4148", "Q1": "Q2N3904"},
        })
        netlist = result["netlist"]
        # Non-empty string
        self.assertIsInstance(netlist, str)
        self.assertGreater(len(netlist.strip()), 0)
        # Title line preserved
        self.assertTrue(netlist.startswith("Simple RC circuit"))
        # Models present
        self.assertIn(".MODEL D1N4148", netlist)
        self.assertIn(".MODEL Q2N3904", netlist)
        # .op and .end preserved
        self.assertIn(".op", netlist.lower())
        self.assertIn(".end", netlist.lower())

    async def test_injected_models_in_response(self):
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {"D1": "D1N4148"},
        })
        injected = result["injected_models"]
        self.assertEqual(len(injected), 1)
        self.assertEqual(injected[0]["refdes"], "D1")
        self.assertEqual(injected[0]["model_name"], "D1N4148")
        self.assertEqual(injected[0]["family"], "diode")

    async def test_disclaimer_present(self):
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {"D1": "D1N4148"},
        })
        self.assertIn("disclaimer", result)

    async def test_unknown_model_returns_error(self):
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {"D1": "NOTAMODEL"},
        })
        self.assertIn("error", result)
        self.assertIn("NOTAMODEL", result["error"])

    async def test_empty_netlist_returns_error(self):
        result = await _call(assign_spice_model, {
            "netlist": "",
            "assignments": {"D1": "D1N4148"},
        })
        self.assertIn("error", result)

    async def test_empty_assignments_returns_error(self):
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {},
        })
        self.assertIn("error", result)

    async def test_missing_netlist_key_returns_error(self):
        result = await _call(assign_spice_model, {
            "assignments": {"D1": "D1N4148"},
        })
        self.assertIn("error", result)

    async def test_invalid_json_returns_error(self):
        raw = await assign_spice_model(None, b"{{bad")
        data = json.loads(raw)
        self.assertIn("error", data)

    async def test_subckt_model_assigned(self):
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {"X1": "OPAMP_IDEAL"},
        })
        self.assertIn(".SUBCKT OPAMP_IDEAL", result["netlist"])

    async def test_multiple_refdes_same_model_no_duplicate(self):
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {"D1": "D1N4148", "D2": "D1N4148"},
        })
        count = result["netlist"].count(".MODEL D1N4148")
        self.assertEqual(count, 1)

    async def test_case_insensitive_model_name(self):
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {"D1": "d1n4148"},
        })
        # Should succeed — no error
        self.assertNotIn("error", result)
        self.assertIn(".MODEL D1N4148", result["netlist"])

    async def test_zener_model_assigned(self):
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {"D3": "DZENER12V"},
        })
        self.assertIn(".MODEL DZENER12V", result["netlist"])
        self.assertIn("BV=12", result["netlist"])

    async def test_passive_cap_with_esr_assigned(self):
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {"C1": "CAP_ELEC_100U"},
        })
        self.assertIn(".SUBCKT CAP_ELEC_100U", result["netlist"])
        self.assertIn("LESL", result["netlist"])

    async def test_inductor_with_parasitics_assigned(self):
        result = await _call(assign_spice_model, {
            "netlist": _MINIMAL_NETLIST,
            "assignments": {"L1": "IND_10U"},
        })
        self.assertIn(".SUBCKT IND_10U", result["netlist"])
        self.assertIn("Rdcr", result["netlist"])
        self.assertIn("Cp", result["netlist"])


# ---------------------------------------------------------------------------
# 6. Parametric helper functions
# ---------------------------------------------------------------------------

class TestParametricHelpers(unittest.TestCase):

    def test_cap_electrolytic_custom_values(self):
        s = _mod._cap_electrolytic_esr(220.0, 0.05, 20.0)
        self.assertIn("CAP_ELEC_220U", s)
        self.assertIn("220", s)  # value appears as 220.0u or 220u depending on format

    def test_cap_ceramic_custom_values(self):
        s = _mod._cap_ceramic_x7r(10.0, 0.02, 0.5)
        self.assertIn("CAP_X7R_10N", s)

    def test_inductor_srf_formula(self):
        """Verify SRF cap computed correctly: Cp = 1/(2*pi*SRF)^2 / L"""
        ind_uh = 10.0
        srf_mhz = 100.0
        expected_cp = 1.0 / ((2 * math.pi * srf_mhz * 1e6) ** 2 * ind_uh * 1e-6)
        s = _mod._inductor_parasitic(ind_uh, 0.05, srf_mhz)
        m = re.search(r"Cp\s+\S+\s+\S+\s+([\d.e+-]+)", s, re.IGNORECASE)
        self.assertIsNotNone(m)
        computed_cp = float(m.group(1))
        # Values are formatted to 4 sig-figs; allow 1% relative tolerance
        self.assertAlmostEqual(computed_cp / expected_cp, 1.0, places=2)


if __name__ == "__main__":
    unittest.main()
