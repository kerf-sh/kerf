import json
from typing import Any

from kerf_electronics.freerouting.dsn_writer import AutorouteParams, circuit_to_dsn
from kerf_electronics.freerouting.freerouting import FreeRouter
from kerf_electronics.freerouting.ses_reader import ses_to_routes
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register


autoroute_circuit_spec = ToolSpec(
    name="autoroute_circuit",
    description="Autoroute PCB traces for a circuit using FreeRouting. Converts circuit to Specctra DSN, runs FreeRouting JAR, parses SES session, and returns updated circuit with routed traces.",
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {"type": "object"},
            "trace_width_mm": {"type": "number"},
            "via_diameter_mm": {"type": "number"},
            "via_drill_mm": {"type": "number"},
            "clearance_mm": {"type": "number"},
            "routing_layers": {"type": "string"},
            "cost_dihedral": {"type": "number"},
            "cost_via": {"type": "number"},
        },
        "required": ["circuit_json"],
    },
)


@register(autoroute_circuit_spec, write=True)
async def autoroute_circuit(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit = a.get("circuit_json")
    if not circuit:
        return err_payload("circuit_json is required", "BAD_ARGS")

    params = AutorouteParams(
        trace_width_mm=a.get("trace_width_mm", 0.2),
        via_diameter_mm=a.get("via_diameter_mm", 0.6),
        via_drill_mm=a.get("via_drill_mm", 0.3),
        clearance_mm=a.get("clearance_mm", 0.2),
        routing_layers=a.get("routing_layers", "1top,16bot"),
        cost_dihedral=a.get("cost_dihedral", 90.0),
        cost_via=a.get("cost_via", 50.0),
    )

    try:
        dsn_output = circuit_to_dsn(circuit, params)
    except Exception as e:
        return err_payload(f"failed to generate DSN: {e}", "DSN_ERROR")

    try:
        router = FreeRouter()
        ses_output = router.route(
            dsn_output,
            trace_width=params.trace_width_mm,
            via_diameter=params.via_diameter_mm,
            via_drill=params.via_drill_mm,
            clearance=params.clearance_mm,
            layers=params.routing_layers.split(","),
            cost_dihedral=params.cost_dihedral,
            cost_via=params.cost_via,
        )
    except Exception as e:
        return err_payload(f"freerouting failed: {e}", "FREEROUTE_ERROR")

    try:
        routes_result = ses_to_routes(ses_output)
    except Exception as e:
        return err_payload(f"failed to parse SES: {e}", "SES_PARSE_ERROR")

    updated_circuit = _apply_routes_to_circuit(circuit, routes_result)

    return ok_payload({
        "updated_circuit": updated_circuit,
        "segments_routed": routes_result.get("segments_routed", 0),
        "vias_placed": routes_result.get("vias_placed", 0),
        "nets_routed": routes_result.get("nets_routed", 0),
        "nets_unrouted": routes_result.get("nets_unrouted", 0),
        "warnings": [],
    })


def _apply_routes_to_circuit(circuit: dict, routes_result: dict) -> dict:
    updated = dict(circuit)
    updated["routes"] = routes_result.get("routes", [])
    updated["vias"] = routes_result.get("vias", [])
    updated["autorouted"] = True
    return updated
