---
title: "Building firmware in Kerf"
group: reference
order: 51
---

# Building firmware in Kerf

The `kerf-firmware` package wires embedded-software workflows into Kerf projects alongside your schematics and PCB files. Write C/C++ firmware, build it, flash it to your board, and monitor the serial output — all from the same project where your circuit lives.

---

## What is kerf-firmware?

`kerf-firmware` is an open-core plugin that adds:

- **Firmware source files** (`.fw.c`, `.fw.cpp`, `.fw.h`) — tracked in the project tree with full revision history
- **Build configuration** (`.fw.config`) — target board, toolchain, build flags, flash settings
- **Build system bridge** — invokes Arduino CLI or PlatformIO in a subprocess; streams build output back as structured log lines
- **Flash tool** — runs `avrdude`, `esptool`, or the platform-native uploader
- **Serial monitor** — streams UART output from the connected device

---

## File types

| Extension | Kind constant | Editor |
|-----------|---------------|--------|
| `.fw.c` | `firmware_c` | Monaco with C syntax |
| `.fw.cpp` | `firmware_cpp` | Monaco with C++ syntax |
| `.fw.h` | `firmware_h` | Monaco with C syntax |
| `.fw.config` | `firmware_config` | Monaco (JSON) |
| `.fw.build` | `firmware_build` | Read-only — streamed build log |
| `.ino` | `arduino_sketch` | Monaco with C++ syntax |
| `.platformio` | `platformio_ini` | Monaco (INI) |

All firmware files are first-class project files: they appear in the file tree, create revision history on every save, and can be attached to LLM chat threads.

---

## Arduino vs PlatformIO

Kerf supports both toolchains. Choose based on your target and preference:

| Criterion | Arduino CLI | PlatformIO |
|-----------|-------------|------------|
| Setup | `arduino-cli` binary on `$PATH` | PlatformIO Core installed |
| Board config | FQBN string in `.fw.config` | `platformio.ini` in project root |
| Library management | Arduino Library Manager | PlatformIO Library Registry |
| Multi-target | One FQBN per config | Multiple environments in one ini |
| Best for | Quick Arduino sketches, Uno / Mega / Nano | Advanced projects, ESP32, STM32, complex build flags |

Kerf detects which toolchain to use based on the `.fw.config` `toolchain` field:

```json
{
  "version": 1,
  "toolchain": "arduino",
  "fqbn": "arduino:avr:uno",
  "source_files": ["/firmware/main.fw.c"],
  "flash_port": "/dev/ttyUSB0",
  "flash_baud": 115200
}
```

For PlatformIO, set `"toolchain": "platformio"` and point to your `platformio.ini`.

---

## Supported boards

The firmware plugin ships a catalogue of 50+ pre-validated board profiles. Common ones:

| Board | FQBN / PlatformIO env | Notes |
|-------|----------------------|-------|
| Arduino Uno (ATmega328P) | `arduino:avr:uno` | Classic 8-bit, 16 MHz |
| Arduino Mega 2560 | `arduino:avr:mega` | 54 digital I/O |
| Arduino Nano | `arduino:avr:nano` | Breadboard-friendly |
| Arduino Nano 33 BLE | `arduino:mbed_nano:nano33ble` | BLE 5, IMU |
| Arduino MKR WiFi 1010 | `arduino:samd:mkrwifi1010` | SAMD21 + WiFi |
| ESP32-DevKitC | `esp32:esp32:esp32` | Dual-core 240 MHz, WiFi + BT |
| ESP32-S3 | `esp32:esp32:esp32s3` | USB-OTG, AI accelerator |
| ESP8266 NodeMCU | `esp8266:esp8266:nodemcuv2` | WiFi, cheap |
| Raspberry Pi Pico (RP2040) | `rp2040:rp2040:rpipico` | Dual Cortex-M0+, PIO |
| STM32 Nucleo-F401RE | via PlatformIO `nucleo_f401re` | ARM Cortex-M4 |
| STM32 Nucleo-G071RB | via PlatformIO `nucleo_g071rb` | Budget Cortex-M0+ |
| Teensy 4.1 | via PlatformIO `teensy41` | 600 MHz Cortex-M7 |
| Adafruit Feather M0 | `adafruit:samd:adafruit_feather_m0` | SAMD21, LoRa optional |
| SparkFun Pro Micro | `SparkFun:avr:promicro` | Leonardo clone, USB HID |

Ask the LLM: *"What boards are available for ESP32?"* — `firmware_list_boards` returns the full catalogue filtered by chip family.

---

## Workflow

### 1. Create a firmware project

```
New file → Firmware Config
```

Or ask the LLM:

> "Create a blink sketch for the Arduino Uno and add a build config."

`firmware_scaffold` creates a `.fw.config` and a starter `.fw.c` with a `setup()` / `loop()` skeleton.

### 2. Edit firmware

Edit the `.fw.c` / `.fw.cpp` files directly in Monaco, or describe what you want in chat:

> "Add a non-blocking LED blink using millis() instead of delay()."

The assistant edits the file directly. Every save creates a revision — press Ctrl+Z or use the History drawer to step back through previous versions.

### 3. Build

Run the build:

```
"Build the firmware and show me any errors."
```

`firmware_build` invokes Arduino CLI or PlatformIO, streams structured log output, and writes a `.fw.build` result file. Build output is parsed into structured diagnostics:

```json
{
  "status": "success",
  "diagnostics": [
    { "severity": "warning", "file": "/firmware/main.fw.c", "line": 42,
      "message": "comparison between signed and unsigned integer expressions" }
  ],
  "binary_size_bytes": 4820,
  "binary_path": "/tmp/kerf-build/main.hex"
}
```

### 4. Flash

Flash the built binary to the board:

```
"Flash the firmware to /dev/ttyUSB0."
```

`firmware_flash` invokes the platform-appropriate programmer (`avrdude` for AVR, `esptool` for ESP, `picotool` for RP2040). The flash port auto-detected from the `.fw.config` if not specified.

> **USB detection**: Kerf calls `list_serial_ports` to enumerate connected serial devices. Run `firmware_list_ports` to see what's attached before flashing.

### 5. Serial monitor

Monitor UART output live:

```
"Open the serial monitor on /dev/ttyUSB0 at 9600 baud."
```

`firmware_monitor_start` opens the serial port and streams lines back. The LLM can inspect the output in real time:

> "The sensor is reading 0 — can you diagnose what's wrong with the I2C init code?"

---

## LLM tool summary

| Tool | Read / Write | What it does |
|------|-------------|--------------|
| `firmware_scaffold` | write | Create a starter `.fw.c` + `.fw.config` for a named board |
| `firmware_build` | write | Compile firmware; return diagnostics + binary size |
| `firmware_flash` | write | Flash compiled binary to a connected board |
| `firmware_monitor_start` | write | Open serial monitor; stream UART lines to the thread |
| `firmware_monitor_stop` | write | Close the serial monitor |
| `firmware_list_boards` | read | List all supported boards, optionally filtered by chip |
| `firmware_list_ports` | read | Enumerate connected serial / USB-serial devices |
| `firmware_read_config` | read | Parse a `.fw.config` and return its fields |
| `firmware_set_config` | write | Update build flags, FQBN, or flash settings |
| `firmware_add_library` | write | Add a library dependency to the build config |

---

## Linking firmware to a circuit

You can associate a `.fw.config` with a `.circuit.tsx` file — Kerf will show the firmware and PCB side by side in a split-pane view, and cross-link GPIO pin numbers in the schematic with `#define` constants in the firmware.

```json
{
  "version": 1,
  "toolchain": "arduino",
  "fqbn": "arduino:avr:uno",
  "linked_circuit": "/circuits/motor-driver.circuit.tsx",
  "source_files": ["/firmware/main.fw.c"]
}
```

Ask the LLM: *"Check that every GPIO used in the firmware matches the pins on the schematic."*

---

## Capability tags

| Tag | What it enables |
|-----|----------------|
| `firmware.arduino` | Arduino CLI toolchain (needs `arduino-cli` on `$PATH`) |
| `firmware.platformio` | PlatformIO toolchain (needs `platformio` on `$PATH`) |
| `firmware.serial` | Serial monitor (`pyserial` required) |

If neither `arduino-cli` nor `platformio` is installed, the plugin loads in dormant mode — file editing and revision history still work, but build/flash/monitor are unavailable.

---

## Example prompts

```
"Scaffold an ESP32 blink project and build it."
"Add DHT22 sensor reading to the firmware every 5 seconds."
"List the serial ports currently attached to this machine."
"Build for ESP32 and show me the binary size."
"Flash the binary and then tail the serial output for 10 seconds."
```

---

## See also

- [electronics-authoring.md](./electronics-authoring.md) — circuit schematic and PCB workflows
- [llm-tools-catalogue.md](./llm-tools-catalogue.md) — complete tool index including 10 firmware tools
- [file-types.md](./file-types.md) — full extension registry
