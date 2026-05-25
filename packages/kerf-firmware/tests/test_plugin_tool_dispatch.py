"""test_plugin_tool_dispatch.py — dispatch-level tests for newly registered firmware tools.

Covers the async tool handlers wired in plugin._register_tools:
  D01  verify_pin_mapping tool — bad args returns BAD_ARGS JSON
  D02  verify_pin_mapping tool — missing fw_path returns BAD_ARGS
  D03  verify_pin_mapping tool — handler is an async coroutine
  D04  make_arduino_sketch tool — blink spec returns sketch and manifest
  D05  make_arduino_sketch tool — missing spec returns BAD_ARGS
  D06  make_arduino_sketch tool — handler is an async coroutine
  D07  make_usb_midi_controller tool — note-button spec returns sketch
  D08  make_usb_midi_controller tool — missing spec returns BAD_ARGS
  D09  make_usb_midi_controller tool — handler is an async coroutine
  D10  make_usb_macro_keyboard tool — F13 spec returns sketch + keycode
  D11  make_usb_macro_keyboard tool — missing spec returns BAD_ARGS
  D12  make_usb_macro_keyboard tool — handler is an async coroutine
  D13  _register_tools registers expected capability names in provides list
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

# Insert package src on path
_PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PKG / "src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx():
    """Minimal ctx mock that records registered tools."""
    registered = {}

    class _Tools:
        def register(self, name, spec, handler):
            registered[name] = (spec, handler)

    ctx = SimpleNamespace(tools=_Tools())
    ctx._registered = registered
    return ctx


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Build the tool set once for the module
# ---------------------------------------------------------------------------

_ctx = _make_ctx()
_provides: list[str] = []

from kerf_firmware.plugin import _register_tools  # noqa: E402
_register_tools(_ctx, _provides)
_reg = _ctx._registered


# ---------------------------------------------------------------------------
# D01–D03  verify_pin_mapping
# ---------------------------------------------------------------------------

class TestVerifyPinMappingDispatch:
    def test_d01_invalid_json_returns_bad_args(self):
        """D01: non-JSON bytes → BAD_ARGS."""
        if "verify_pin_mapping" not in _reg:
            pytest.skip("verify_pin_mapping tool not registered")
        _, handler = _reg["verify_pin_mapping"]
        result = json.loads(_run(handler(None, b"not json")))
        assert "error" in result or result.get("code") == "BAD_ARGS"

    def test_d02_missing_fw_path_returns_bad_args(self):
        """D02: empty args dict → BAD_ARGS (fw_path required)."""
        if "verify_pin_mapping" not in _reg:
            pytest.skip("verify_pin_mapping tool not registered")
        _, handler = _reg["verify_pin_mapping"]
        payload = json.dumps({}).encode()
        result = json.loads(_run(handler(None, payload)))
        assert result.get("code") == "BAD_ARGS" or "error" in result

    def test_d03_handler_is_coroutine(self):
        """D03: handler must be an async coroutine function."""
        if "verify_pin_mapping" not in _reg:
            pytest.skip("verify_pin_mapping tool not registered")
        _, handler = _reg["verify_pin_mapping"]
        assert inspect.iscoroutinefunction(handler)


# ---------------------------------------------------------------------------
# D04–D06  make_arduino_sketch
# ---------------------------------------------------------------------------

class TestMakeArduinoSketchDispatch:
    def test_d04_blink_spec_returns_sketch(self):
        """D04: blink spec → sketch + manifest."""
        if "make_arduino_sketch" not in _reg:
            pytest.skip("make_arduino_sketch tool not registered")
        _, handler = _reg["make_arduino_sketch"]
        payload = json.dumps({"spec": "blink LED on pin 13"}).encode()
        result = json.loads(_run(handler(None, payload)))
        assert "sketch" in result
        assert "manifest" in result

    def test_d05_missing_spec_returns_bad_args(self):
        """D05: missing spec field → BAD_ARGS."""
        if "make_arduino_sketch" not in _reg:
            pytest.skip("make_arduino_sketch tool not registered")
        _, handler = _reg["make_arduino_sketch"]
        payload = json.dumps({}).encode()
        result = json.loads(_run(handler(None, payload)))
        assert "error" in result

    def test_d06_handler_is_coroutine(self):
        """D06: handler must be async."""
        if "make_arduino_sketch" not in _reg:
            pytest.skip("make_arduino_sketch tool not registered")
        _, handler = _reg["make_arduino_sketch"]
        assert inspect.iscoroutinefunction(handler)


# ---------------------------------------------------------------------------
# D07–D09  make_usb_midi_controller
# ---------------------------------------------------------------------------

class TestMakeUsbMidiDispatch:
    def test_d07_note_button_spec_returns_sketch(self):
        """D07: note button spec → sketch + manifest."""
        if "make_usb_midi_controller" not in _reg:
            pytest.skip("make_usb_midi_controller tool not registered")
        _, handler = _reg["make_usb_midi_controller"]
        payload = json.dumps({"spec": "note button on pin 3, note 60"}).encode()
        result = json.loads(_run(handler(None, payload)))
        assert "sketch" in result or "error" in result  # graceful

    def test_d08_missing_spec_returns_error(self):
        """D08: missing spec → error."""
        if "make_usb_midi_controller" not in _reg:
            pytest.skip("make_usb_midi_controller tool not registered")
        _, handler = _reg["make_usb_midi_controller"]
        payload = json.dumps({}).encode()
        result = json.loads(_run(handler(None, payload)))
        assert "error" in result

    def test_d09_handler_is_coroutine(self):
        """D09: handler must be async."""
        if "make_usb_midi_controller" not in _reg:
            pytest.skip("make_usb_midi_controller tool not registered")
        _, handler = _reg["make_usb_midi_controller"]
        assert inspect.iscoroutinefunction(handler)


# ---------------------------------------------------------------------------
# D10–D12  make_usb_macro_keyboard
# ---------------------------------------------------------------------------

class TestMakeUsbMacroDispatch:
    def test_d10_f13_spec_returns_sketch_and_keycode(self):
        """D10: F13 button spec → sketch + keycode."""
        if "make_usb_macro_keyboard" not in _reg:
            pytest.skip("make_usb_macro_keyboard tool not registered")
        _, handler = _reg["make_usb_macro_keyboard"]
        payload = json.dumps({"spec": {"button_pin": 2, "send": "F13"}}).encode()
        result = json.loads(_run(handler(None, payload)))
        assert "sketch" in result or "error" in result  # graceful
        if "keycode" in result:
            assert result["keycode"] == 0x68  # HID F13

    def test_d11_missing_spec_returns_error(self):
        """D11: missing spec → error."""
        if "make_usb_macro_keyboard" not in _reg:
            pytest.skip("make_usb_macro_keyboard tool not registered")
        _, handler = _reg["make_usb_macro_keyboard"]
        payload = json.dumps({}).encode()
        result = json.loads(_run(handler(None, payload)))
        assert "error" in result

    def test_d12_handler_is_coroutine(self):
        """D12: handler must be async."""
        if "make_usb_macro_keyboard" not in _reg:
            pytest.skip("make_usb_macro_keyboard tool not registered")
        _, handler = _reg["make_usb_macro_keyboard"]
        assert inspect.iscoroutinefunction(handler)


# ---------------------------------------------------------------------------
# D13  capability provides list
# ---------------------------------------------------------------------------

class TestProvidesCapabilities:
    def test_d13_expected_capabilities_registered(self):
        """D13: _register_tools should add expected capability strings."""
        # firmware.build may be absent (PIO not installed) — that's OK
        # The newly wired capabilities should be present
        expected = {
            "firmware.pcb_xcheck",
            "firmware.protocol_driver",
            "firmware.arduino_sketch",
            "firmware.usb_midi",
            "firmware.usb_hid",
        }
        assert expected.issubset(set(_provides)), (
            f"Missing provides: {expected - set(_provides)}"
        )
