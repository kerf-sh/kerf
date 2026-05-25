"""
kerf-firmware plugin registration.

Wires the firmware build/monitor routes and LLM tools into a Kerf plugin app.
The capability `firmware.build` is only advertised when PlatformIO Core CLI is
available on PATH (probed at startup). The HTTP routes are always mounted —
they return descriptive errors when PlatformIO is absent so the frontend can
show a helpful install prompt.
"""
from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def _pio_available() -> bool:
    """Return True if PlatformIO Core CLI is on PATH."""
    return (
        shutil.which("pio") is not None
        or shutil.which("platformio") is not None
    )


async def register(app: "FastAPI", ctx):
    """Entry point called by the Kerf plugin loader."""
    # ── HTTP routes ──────────────────────────────────────────────────────────
    from kerf_firmware.routes import router as firmware_router
    app.include_router(firmware_router, tags=["firmware"])

    # ── LLM tools ────────────────────────────────────────────────────────────
    provides: list[str] = []
    _register_tools(ctx, provides)

    # Advertise firmware.build only when PlatformIO is actually present.
    if _pio_available():
        if "firmware.build" not in provides:
            provides.append("firmware.build")
        logger.info("kerf-firmware: PlatformIO found — firmware.build available")
    else:
        logger.warning(
            "kerf-firmware: PlatformIO Core CLI not found on PATH — "
            "install it to enable firmware builds. "
            "pip install platformio  |  brew install platformio"
        )

    try:
        from kerf_core.plugin import PluginManifest  # type: ignore
    except ImportError:
        return {
            "name": "firmware",
            "version": "0.1.0",
            "provides": provides,
            "depends": [],
        }

    return PluginManifest(
        name="firmware",
        version="0.1.0",
        provides=provides,
        depends=[],
    )


def _register_tools(ctx, provides: list) -> None:
    """Register all firmware LLM tools into ctx.tools."""
    try:
        from kerf_firmware.tools.build_firmware import (
            build_firmware_tool,
            build_firmware_spec,
        )
        ctx.tools.register("build_firmware", build_firmware_spec, build_firmware_tool)
        provides.append("firmware.build")
    except Exception as exc:
        logger.warning("kerf-firmware: failed to load build_firmware tool: %s", exc)

    # verify_pin_mapping — cross-check firmware pin assignments vs KiCad PCB netlist
    try:
        from kerf_firmware.tools.verify_pin_mapping import _spec as _vpm_spec, verify_pin_mapping as _vpm_fn
        import json as _json

        async def _verify_pin_mapping_tool(ctx, args: bytes) -> str:
            try:
                a = _json.loads(args)
            except Exception as e:
                from kerf_firmware._compat import err_payload
                return err_payload(f"invalid args: {e}", "BAD_ARGS")
            return _vpm_fn(a, ctx)

        ctx.tools.register("verify_pin_mapping", _vpm_spec, _verify_pin_mapping_tool)
        provides.append("firmware.pcb_xcheck")
    except Exception as exc:
        logger.warning("kerf-firmware: failed to load verify_pin_mapping tool: %s", exc)

    # make_protocol_driver — generate C driver source for common I2C/SPI/UART sensors
    try:
        from kerf_firmware.tools.make_protocol_driver import (
            make_protocol_driver_spec,
            run_make_protocol_driver,
        )
        ctx.tools.register(
            "make_protocol_driver",
            make_protocol_driver_spec,
            run_make_protocol_driver,
        )
        provides.append("firmware.protocol_driver")
    except Exception as exc:
        logger.warning("kerf-firmware: failed to load make_protocol_driver tool: %s", exc)

    # make_arduino_sketch — template-based Arduino sketch synthesizer
    try:
        from kerf_firmware.llm_tool import make_arduino_sketch as _make_sketch
        import json as _json

        try:
            from kerf_chat.tools.registry import ToolSpec as _ToolSpec
        except ImportError:
            from kerf_firmware._compat import ToolSpec as _ToolSpec  # type: ignore

        _arduino_spec = _ToolSpec(
            name="make_arduino_sketch",
            description=(
                "Generate a complete Arduino sketch (.ino) from a natural-language description. "
                "Supports blink LED, DHT22 temperature sensor, servo + potentiometer, "
                "MPU6050 accelerometer (serial log), and PWM motor speed control. "
                "Returns {sketch: str, manifest: dict} on success or {error: str, spec: str} "
                "when no pattern matches."
            ),
            input_schema={
                "type": "object",
                "required": ["spec"],
                "properties": {
                    "spec": {
                        "type": "string",
                        "description": (
                            "Natural-language description of the sketch, e.g. "
                            "'blink LED on pin 13', 'read DHT22 on pin 4', "
                            "'control servo with potentiometer on pin 9'."
                        ),
                    },
                },
            },
        )

        async def _make_arduino_sketch_tool(ctx, args: bytes) -> str:
            try:
                a = _json.loads(args)
            except Exception as e:
                return _json.dumps({"error": f"invalid args: {e}", "code": "BAD_ARGS"})
            spec = a.get("spec", "")
            if not spec:
                return _json.dumps({"error": "'spec' is required", "code": "BAD_ARGS"})
            result = _make_sketch(spec)
            return _json.dumps(result)

        ctx.tools.register("make_arduino_sketch", _arduino_spec, _make_arduino_sketch_tool)
        provides.append("firmware.arduino_sketch")
    except Exception as exc:
        logger.warning("kerf-firmware: failed to load make_arduino_sketch tool: %s", exc)

    # make_usb_midi_controller — generate USB-MIDI Arduino sketch
    try:
        from kerf_firmware.tools.make_usb_midi_controller import make_usb_midi_controller as _make_midi
        import json as _json

        try:
            from kerf_chat.tools.registry import ToolSpec as _ToolSpec2
        except ImportError:
            from kerf_firmware._compat import ToolSpec as _ToolSpec2  # type: ignore

        _midi_spec = _ToolSpec2(
            name="make_usb_midi_controller",
            description=(
                "Generate a USB-MIDI controller Arduino sketch (.ino) from a natural-language "
                "spec or parameter dict. Supports note-button, CC-knob, and CC-button patterns. "
                "Board selection: teensy40 → TinyUSB backend; pro-micro → LUFA backend. "
                "Returns {sketch: str, manifest: dict, backend: str} on success."
            ),
            input_schema={
                "type": "object",
                "required": ["spec"],
                "properties": {
                    "spec": {
                        "type": ["string", "object"],
                        "description": (
                            "Natural-language string (e.g. 'note button on pin 3, note 72, teensy 4') "
                            "or parameter dict with keys: button_pin, note, velocity, channel, "
                            "control, pot_pin, board."
                        ),
                    },
                },
            },
        )

        async def _make_usb_midi_tool(ctx, args: bytes) -> str:
            try:
                a = _json.loads(args)
            except Exception as e:
                return _json.dumps({"error": f"invalid args: {e}", "code": "BAD_ARGS"})
            spec = a.get("spec", "")
            if not spec:
                return _json.dumps({"error": "'spec' is required", "code": "BAD_ARGS"})
            result = _make_midi(spec)
            return _json.dumps(result)

        ctx.tools.register("make_usb_midi_controller", _midi_spec, _make_usb_midi_tool)
        provides.append("firmware.usb_midi")
    except Exception as exc:
        logger.warning("kerf-firmware: failed to load make_usb_midi_controller tool: %s", exc)

    # make_usb_macro_keyboard — generate USB-HID macro keyboard Arduino sketch
    try:
        from kerf_firmware.tools.make_usb_macro_keyboard import make_usb_macro_keyboard as _make_macro
        import json as _json

        try:
            from kerf_chat.tools.registry import ToolSpec as _ToolSpec3
        except ImportError:
            from kerf_firmware._compat import ToolSpec as _ToolSpec3  # type: ignore

        _macro_spec = _ToolSpec3(
            name="make_usb_macro_keyboard",
            description=(
                "Generate a USB-HID macro keyboard Arduino sketch (.ino). "
                "The sketch sends a configurable HID keycode (F1–F24, A–Z, digits, Enter, "
                "Space, Escape, or arbitrary 0x00–0xFF hex) when a button is pressed. "
                "Supports Ctrl/Shift/Alt modifiers. Board: teensy40 → TinyUSB; "
                "pro-micro → LUFA. Returns {sketch, manifest, keycode, descriptor_note}."
            ),
            input_schema={
                "type": "object",
                "required": ["spec"],
                "properties": {
                    "spec": {
                        "type": ["string", "object"],
                        "description": (
                            "Natural-language string or dict with keys: "
                            "button_pin (int), send (str, e.g. 'F13'), "
                            "modifier (str, e.g. 'ctrl'), board (str)."
                        ),
                    },
                },
            },
        )

        async def _make_usb_macro_tool(ctx, args: bytes) -> str:
            try:
                a = _json.loads(args)
            except Exception as e:
                return _json.dumps({"error": f"invalid args: {e}", "code": "BAD_ARGS"})
            spec = a.get("spec", "")
            if not spec:
                return _json.dumps({"error": "'spec' is required", "code": "BAD_ARGS"})
            result = _make_macro(spec)
            return _json.dumps(result)

        ctx.tools.register("make_usb_macro_keyboard", _macro_spec, _make_usb_macro_tool)
        provides.append("firmware.usb_hid")
    except Exception as exc:
        logger.warning("kerf-firmware: failed to load make_usb_macro_keyboard tool: %s", exc)
