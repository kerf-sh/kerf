---
title: "LLM tools catalogue"
group: reference
order: 54
---

# LLM tools catalogue

This page indexes every domain-specialist LLM tool added by the `kerf-aero`, `kerf-silicon`, and `kerf-firmware` packages — 34 tools total. The complete set of Kerf LLM tools (including mechanical, BIM, electronics, and analysis) is documented in [llm-tools.md](./llm-tools.md).

Call any tool by describing the operation in the chat panel — the assistant will invoke the right tool automatically. All tool names are also callable from the `kerf-sdk` Python package.

---

## Aerospace — 12 tools

The `kerf-aero` package contributes tools across six sub-disciplines. Each tool is available once the matching subpackage is installed and the capability tag is present in `/health/capabilities`.

| Tool | Sector | Capability | Read/Write | Signature | Example prompt |
|------|--------|-----------|-----------|-----------|----------------|
| `aero_create_airfoil` | airfoils | `aero.airfoils` | write | `(naca: str, chord_m: float = 1.0)` → `.airfoil` path | "Create a NACA 2412 airfoil." |
| `aero_run_polar` | airfoils | `aero.airfoils` | write | `(airfoil_path: str, re: float, alpha_start: float, alpha_end: float, alpha_step: float = 1.0)` → `.polar` path | "Compute polar at Re = 1e6 from -5° to 20°." |
| `aero_compare_polars` | airfoils | `aero.airfoils` | read | `(polar_a: str, polar_b: str, metric: str = "cd")` → comparison JSON | "Compare drag polars of NACA 0012 and NACA 2412." |
| `aero_read_polar` | airfoils | `aero.airfoils` | read | `(polar_path: str)` → polar data JSON | "What is the Cl at alpha = 8°?" |
| `orbital_ingest_tle` | orbital | `aero.orbital` | write | `(tle_string: str, name: str = "")` → `.orbit` path | "Import this ISS TLE and save it." |
| `orbital_propagate` | orbital | `aero.orbital` | write | `(orbit_path: str, duration_s: float, step_s: float = 60.0)` → ground-track JSON | "Propagate the orbit for 24 hours." |
| `orbital_hohmann_transfer` | orbital | `aero.orbital` | write | `(r1_km: float, r2_km: float)` → delta-V JSON + `.trajectory` path | "Hohmann transfer from 400 km to GEO." |
| `orbital_ground_track` | orbital | `aero.orbital` | read | `(orbit_path: str, duration_s: float, observer_lat: float, observer_lon: float)` → pass table JSON | "Pass schedule over Cape Town for 12 hours." |
| `propulsion_size_engine` | propulsion | `aero.propulsion` | write | `(thrust_N: float, isp_s: float, propellant: str)` → `.thruster` path | "Size a 500 N LOX/RP-1 engine at 300 s Isp." |
| `propulsion_delta_v` | propulsion | `aero.propulsion` | read | `(thruster_path: str, propellant_mass_kg: float, dry_mass_kg: float)` → delta-V m/s | "What delta-V with 200 g propellant?" |
| `adcs_design_controller` | adcs | `aero.adcs` | write | `(inertia_tensor: list, actuator_type: str, mode: str)` → `.adcs_config` path | "Design LQR nadir-pointing for a 3U CubeSat." |
| `adcs_simulate` | adcs | `aero.adcs` | write | `(adcs_config_path: str, initial_rate_deg_s: list, duration_s: float)` → attitude time-series JSON | "Simulate detumble from 5 deg/s." |

> Tools in the `thermal` and `flight_dynamics` sub-disciplines (`thermal_build_model`, `thermal_run_steady_state`, `thermal_run_transient`, `flight_sim_run`) are covered in [aerospace-overview.md](./aerospace-overview.md) and are not counted in the 12 because they are in the `kerf-aero[thermal]` and `kerf-aero[flight_dynamics]` optional extras.

---

## Silicon — 12 tools

The `kerf-silicon` package contributes tools for chip schematic capture, synthesis, floorplanning, DRC, and GDS export.

| Tool | Capability | Read/Write | Signature | Example prompt |
|------|-----------|-----------|-----------|----------------|
| `silicon_read_schem` | `silicon.schematic` | read | `(path: str)` → gate/net graph JSON | "What gates are in the ALU schematic?" |
| `silicon_edit_schem` | `silicon.schematic` | write | `(path: str, op: str, payload: dict)` → updated path | "Add a sky130 NAND2 and wire it to U1.Y." |
| `silicon_synth_preview` | `silicon.synth` | write | `(rtl_path: str, target_pdk: str, top_module: str)` → gate histogram + `.sil.schem` | "Synthesise alu.v targeting sky130." |
| `silicon_place_macro` | `silicon.schematic` | write | `(floor_path: str, macro_name: str, x_um: float, y_um: float, orient: str = "N")` → updated floor path | "Place the SRAM at (30, 50) with N orientation." |
| `silicon_add_io_pad` | `silicon.schematic` | write | `(floor_path: str, name: str, side: str, x_um: float, metal: str)` → updated floor path | "Add a VDD pad on the top edge at x = 250." |
| `silicon_set_power_rail` | `silicon.schematic` | write | `(floor_path: str, net: str, metal: str, pitch_um: float, width_um: float)` → updated floor path | "Set VDD rails on met1 with 5 µm pitch." |
| `silicon_run_drc` | `silicon.gds` | write | `(path: str, rule_deck: str = "default")` → DRC report JSON | "Run DRC and group errors by rule name." |
| `silicon_export_gds` | `silicon.gds` | write | `(floor_path: str, layer_map: str = "default")` → `.sil.gds` path | "Export the floorplan to GDS using sky130 layers." |
| `silicon_import_lef` | `silicon.schematic` | write | `(lef_path: str)` → cell reference JSON | "Import the sky130 standard cell LEF." |
| `silicon_query_liberty` | `silicon.sky130` | read | `(lib_path: str, cell: str, arc: str = "")` → timing JSON | "What is the setup time for sky130_fd_sc_hd__nand2_1?" |
| `silicon_extract_spef` | `silicon.gds` | write | `(gds_path: str, corner: str = "tt")` → `.spef` path | "Extract parasitics at the TT corner." |
| `silicon_run_lvs` | `silicon.gds` | write | `(schematic_path: str, gds_path: str)` → LVS report JSON | "Run LVS and list mismatched nets." |

---

## Firmware — 10 tools

The `kerf-firmware` package contributes tools for build, flash, serial monitoring, and board management.

| Tool | Capability | Read/Write | Signature | Example prompt |
|------|-----------|-----------|-----------|----------------|
| `firmware_scaffold` | `firmware.arduino` or `firmware.platformio` | write | `(board: str, name: str = "main")` → `.fw.config` + `.fw.c` paths | "Scaffold a blink project for the Arduino Uno." |
| `firmware_build` | `firmware.arduino` or `firmware.platformio` | write | `(config_path: str)` → build result JSON | "Build the firmware and show errors." |
| `firmware_flash` | `firmware.arduino` or `firmware.platformio` | write | `(config_path: str, port: str = "auto")` → flash result JSON | "Flash to /dev/ttyUSB0." |
| `firmware_monitor_start` | `firmware.serial` | write | `(port: str, baud: int = 9600)` → stream handle | "Open serial monitor at 9600 baud." |
| `firmware_monitor_stop` | `firmware.serial` | write | `(handle: str)` → ok | "Close the serial monitor." |
| `firmware_list_boards` | — | read | `(chip_family: str = "")` → board catalogue JSON | "What ESP32 boards are available?" |
| `firmware_list_ports` | `firmware.serial` | read | `()` → port list JSON | "List connected serial devices." |
| `firmware_read_config` | — | read | `(config_path: str)` → config JSON | "What board is configured?" |
| `firmware_set_config` | — | write | `(config_path: str, key: str, value)` → updated config | "Change the baud rate to 115200." |
| `firmware_add_library` | — | write | `(config_path: str, library: str, version: str = "latest")` → updated config | "Add the DHT sensor library." |

---

## Tool availability matrix

A tool is available at runtime only when its capability tag is present. Check the live set:

```
GET /health/capabilities
```

Or ask in chat: *"Which aerospace tools do I have available?"* — the assistant calls `search_kerf_docs("capabilities")` and cross-references the live capability list.

| Package | Min install | Capability tags |
|---------|-------------|----------------|
| `kerf-aero[airfoils]` | `pip install "kerf-aero[airfoils]"` | `aero.airfoils`, `aero.llm_tools` |
| `kerf-aero[orbital]` | `pip install "kerf-aero[orbital]"` | `aero.orbital`, `aero.llm_tools` |
| `kerf-aero[propulsion]` | `pip install "kerf-aero[propulsion]"` | `aero.propulsion`, `aero.llm_tools` |
| `kerf-aero[adcs]` | `pip install "kerf-aero[adcs]"` | `aero.adcs`, `aero.llm_tools` |
| `kerf-silicon` | `pip install kerf-silicon` | `silicon.schematic` (always), `silicon.synth` (needs Yosys), `silicon.gds` (needs KLayout) |
| `kerf-firmware` | `pip install kerf-firmware` | `firmware.arduino`, `firmware.platformio`, `firmware.serial` |

---

## Using tools from the SDK

All LLM tools are callable programmatically from the `kerf-sdk` Python package:

```python
import kerf

client = kerf.Client(base_url="http://localhost:8080", api_token="your-token")
project = client.project("proj-uuid")

# Run a polar analysis
result = project.run_tool("aero_run_polar", {
    "airfoil_path": "/airfoils/naca2412.airfoil",
    "re": 1e6,
    "alpha_start": -5,
    "alpha_end": 20,
})
print(result["polar_path"])
```

See [sdk.md](./sdk.md) for the full SDK reference.

---

## See also

- [aerospace-overview.md](./aerospace-overview.md) — aero workflow walkthrough
- [silicon-overview.md](./silicon-overview.md) — chip design workflow
- [firmware-overview.md](./firmware-overview.md) — embedded firmware workflow
- [llm-tools.md](./llm-tools.md) — full tool reference including mechanical, BIM, and electronics
