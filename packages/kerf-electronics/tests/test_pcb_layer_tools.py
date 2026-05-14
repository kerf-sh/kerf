"""
Tests for kerf_electronics/tools/pcb_layer_tools.py — PCB layer management tools.
"""
import json
import unittest

from kerf_electronics.tools.pcb_layer_tools import (
    _build_copper_layer_names,
    _default_color_for,
    _parse_layer_stack,
    _inject_layer_stack,
    _layer_stack_with_entry,
    _layer_stack_without_name,
    VALID_COPPER_COUNTS,
)
from kerf_chat.tools.registry import Registry


# ---------------------------------------------------------------------------
# Minimal .circuit.tsx-style content helpers
# ---------------------------------------------------------------------------

def _make_content(layer_stack=None):
    """Produce a minimal board tag with or without a layer_stack attribute."""
    if layer_stack is None:
        return '<board width="100" height="100" />'
    import json as _json
    ls_str = _json.dumps(layer_stack, separators=(',', ':'))
    return f'<board width="100" height="100" layer_stack={ls_str} />'


async def call_tool(name, payload):
    tool = next(t for t in Registry if t.spec.name == name)
    return json.loads(await tool.run(None, json.dumps(payload).encode()))


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------

class TestBuildCopperLayerNames(unittest.TestCase):

    def test_two_layer(self):
        names = _build_copper_layer_names(2)
        self.assertEqual(names, ["top_copper", "bottom_copper"])

    def test_four_layer(self):
        names = _build_copper_layer_names(4)
        self.assertEqual(names, ["top_copper", "inner_1", "inner_2", "bottom_copper"])

    def test_six_layer_has_four_inner(self):
        names = _build_copper_layer_names(6)
        self.assertEqual(names[0], "top_copper")
        self.assertEqual(names[-1], "bottom_copper")
        self.assertEqual(len(names), 6)


class TestDefaultColorFor(unittest.TestCase):

    def test_top_copper(self):
        self.assertEqual(_default_color_for("top_copper"), "#ef4444")

    def test_bottom_copper(self):
        self.assertEqual(_default_color_for("bottom_copper"), "#3b82f6")

    def test_unknown_defaults_to_grey(self):
        self.assertEqual(_default_color_for("unknown_layer"), "#64748b")


class TestParseLayerStack(unittest.TestCase):

    def test_no_layer_stack_returns_none(self):
        content = _make_content()
        self.assertIsNone(_parse_layer_stack(content))

    def test_valid_layer_stack_parsed(self):
        ls = [{"name": "top_copper", "type": "copper", "color": "#ef4444", "visible": True, "sublayer_order": 0}]
        content = _make_content(ls)
        parsed = _parse_layer_stack(content)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed[0]["name"], "top_copper")


class TestLayerStackOps(unittest.TestCase):

    def _base_content(self):
        ls = [
            {"name": "top_copper", "type": "copper", "color": "#ef4444", "visible": True, "sublayer_order": 0},
            {"name": "bottom_copper", "type": "copper", "color": "#3b82f6", "visible": True, "sublayer_order": 1},
        ]
        return _make_content(ls)

    def test_add_entry(self):
        content = self._base_content()
        new_content, err = _layer_stack_with_entry(content, {
            "name": "inner_1", "type": "copper", "color": "#888888", "visible": True,
        })
        self.assertIsNone(err)
        ls = _parse_layer_stack(new_content)
        names = [l["name"] for l in ls]
        self.assertIn("inner_1", names)

    def test_add_duplicate_entry_is_error(self):
        content = self._base_content()
        _, err = _layer_stack_with_entry(content, {
            "name": "top_copper", "type": "copper", "color": "#ef4444", "visible": True,
        })
        self.assertIsNotNone(err)

    def test_remove_entry(self):
        content = self._base_content()
        new_content, err = _layer_stack_without_name(content, "bottom_copper")
        self.assertIsNone(err)
        ls = _parse_layer_stack(new_content)
        names = [l["name"] for l in ls]
        self.assertNotIn("bottom_copper", names)

    def test_remove_nonexistent_entry_is_error(self):
        content = self._base_content()
        _, err = _layer_stack_without_name(content, "nonexistent")
        self.assertIsNotNone(err)


# ---------------------------------------------------------------------------
# Tool: add_pcb_layer
# ---------------------------------------------------------------------------

class TestAddPcbLayer(unittest.IsolatedAsyncioTestCase):

    def _base(self):
        ls = [
            {"name": "top_copper", "type": "copper", "color": "#ef4444", "visible": True, "sublayer_order": 0},
        ]
        return _make_content(ls)

    async def test_adds_layer(self):
        result = await call_tool("add_pcb_layer", {
            "file_content": self._base(),
            "name": "inner_1",
            "type": "copper",
        })
        self.assertTrue(result["success"])
        self.assertIn("inner_1", result["updated_content"])

    async def test_missing_name_is_error(self):
        result = await call_tool("add_pcb_layer", {
            "file_content": self._base(),
            "name": "",
        })
        self.assertIn("error", result)

    async def test_missing_content_is_error(self):
        result = await call_tool("add_pcb_layer", {"file_content": "", "name": "new"})
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Tool: remove_pcb_layer
# ---------------------------------------------------------------------------

class TestRemovePcbLayer(unittest.IsolatedAsyncioTestCase):

    def _base(self):
        ls = [
            {"name": "top_copper", "type": "copper", "color": "#ef4444", "visible": True, "sublayer_order": 0},
            {"name": "bottom_copper", "type": "copper", "color": "#3b82f6", "visible": True, "sublayer_order": 1},
        ]
        return _make_content(ls)

    async def test_removes_layer(self):
        result = await call_tool("remove_pcb_layer", {
            "file_content": self._base(),
            "name": "bottom_copper",
        })
        self.assertTrue(result["success"])
        self.assertNotIn("bottom_copper", result["updated_content"])

    async def test_remove_nonexistent_is_error(self):
        result = await call_tool("remove_pcb_layer", {
            "file_content": self._base(),
            "name": "no_such_layer",
        })
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Tool: set_layer_visibility / set_pcb_layer_visibility
# ---------------------------------------------------------------------------

class TestSetLayerVisibility(unittest.IsolatedAsyncioTestCase):

    def _base(self):
        ls = [
            {"name": "top_silk", "type": "silkscreen", "color": "#f0f0f0", "visible": True, "sublayer_order": 0},
        ]
        return _make_content(ls)

    async def test_set_invisible(self):
        result = await call_tool("set_layer_visibility", {
            "file_content": self._base(),
            "name": "top_silk",
            "visible": False,
        })
        self.assertTrue(result["success"])

    async def test_set_pcb_alias(self):
        result = await call_tool("set_pcb_layer_visibility", {
            "file_content": self._base(),
            "name": "top_silk",
            "visible": True,
        })
        self.assertTrue(result["success"])


# ---------------------------------------------------------------------------
# Tool: set_layer_color / set_pcb_layer_color
# ---------------------------------------------------------------------------

class TestSetLayerColor(unittest.IsolatedAsyncioTestCase):

    def _base(self):
        ls = [{"name": "top_copper", "type": "copper", "color": "#ef4444", "visible": True, "sublayer_order": 0}]
        return _make_content(ls)

    async def test_set_color(self):
        result = await call_tool("set_layer_color", {
            "file_content": self._base(),
            "name": "top_copper",
            "color": "#ff0000",
        })
        self.assertTrue(result["success"])
        self.assertIn("#ff0000", result["updated_content"])


# ---------------------------------------------------------------------------
# Tool: reorder_layers / reorder_pcb_layers
# ---------------------------------------------------------------------------

class TestReorderLayers(unittest.IsolatedAsyncioTestCase):

    def _base(self):
        ls = [
            {"name": "top_copper", "type": "copper", "color": "#ef4444", "visible": True, "sublayer_order": 0},
            {"name": "top_silk", "type": "silkscreen", "color": "#f0f0f0", "visible": True, "sublayer_order": 1},
        ]
        return _make_content(ls)

    async def test_reorder_moves_layer(self):
        result = await call_tool("reorder_layers", {
            "file_content": self._base(),
            "name": "top_silk",
            "new_index": 0,
        })
        self.assertTrue(result["success"])


# ---------------------------------------------------------------------------
# Tool: set_board_layer_count
# ---------------------------------------------------------------------------

class TestSetBoardLayerCount(unittest.IsolatedAsyncioTestCase):

    async def test_set_4_layer_from_existing_2_layer(self):
        # Start with an existing 2-layer stack so the update path runs.
        ls = [
            {"name": "top_copper", "type": "copper", "color": "#ef4444", "visible": True, "sublayer_order": 0},
            {"name": "bottom_copper", "type": "copper", "color": "#3b82f6", "visible": True, "sublayer_order": 1},
        ]
        content = _make_content(ls)
        result = await call_tool("set_board_layer_count", {
            "file_content": content,
            "layer_count": 4,
        })
        self.assertTrue(result["success"])
        self.assertIn("inner_1", result["updated_content"])

    async def test_set_2_layer_from_scratch(self):
        # No existing layer_stack — builds default 2-layer.
        content = _make_content()
        result = await call_tool("set_board_layer_count", {
            "file_content": content,
            "layer_count": 2,
        })
        self.assertTrue(result["success"])
        self.assertIn("top_copper", result["updated_content"])

    async def test_invalid_layer_count_is_error(self):
        content = _make_content()
        result = await call_tool("set_board_layer_count", {
            "file_content": content,
            "layer_count": 3,
        })
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestLayerToolsRegistered(unittest.IsolatedAsyncioTestCase):

    async def test_all_tools_registered(self):
        names = {t.spec.name for t in Registry}
        for tool_name in (
            "add_pcb_layer",
            "remove_pcb_layer",
            "set_layer_visibility",
            "set_layer_color",
            "reorder_layers",
            "assign_to_layer",
            "set_board_layer_count",
            "set_pcb_layer_visibility",
            "set_pcb_layer_color",
            "reorder_pcb_layers",
        ):
            self.assertIn(tool_name, names)


if __name__ == "__main__":
    unittest.main()
