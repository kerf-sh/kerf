"""
PCB Autorouting via FreeRouting JAR.

POST /autoroute
Body: {
    "circuit_json": dict,
    "trace_width_microns": float,
    "via_diameter_microns": float,
    "via_drill_microns": float,
    "route_layers": str,
    "clearance_microns": float,
}
"""

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException

from kerf_electronics.freerouting.dsn_writer import AutorouteParams, circuit_to_dsn
from kerf_electronics.freerouting.freerouting import FreeRouter
from kerf_electronics.freerouting.ses_reader import ses_to_routes

router = APIRouter()


@router.post("/autoroute")
async def autoroute(req: dict):
    circuit = req.get("circuit_json")
    if not circuit:
        raise HTTPException(status_code=400, detail="circuit_json is required")

    trace_width_mm = req.get("trace_width_microns", 200) / 1000.0
    via_diameter_mm = req.get("via_diameter_microns", 600) / 1000.0
    via_drill_mm = req.get("via_drill_microns", 300) / 1000.0
    clearance_mm = req.get("clearance_microns", 200) / 1000.0
    route_layers = req.get("route_layers", "1top,16bot")
    cost_dihedral = req.get("cost_dihedral", 90.0)
    cost_via = req.get("cost_via", 50.0)
    num_passes = req.get("num_passes", 3)
    max_vias = req.get("max_vias", None)

    params = AutorouteParams(
        trace_width_mm=trace_width_mm,
        via_diameter_mm=via_diameter_mm,
        via_drill_mm=via_drill_mm,
        clearance_mm=clearance_mm,
        routing_layers=route_layers,
        cost_dihedral=cost_dihedral,
        cost_via=cost_via,
    )

    try:
        dsn_output = circuit_to_dsn(circuit, params)
    except Exception as e:
        return {
            "updated_circuit": None,
            "warnings": [f"DSN generation failed: {e}"],
            "segments_routed": 0,
            "vias_placed": 0,
            "nets_routed": 0,
            "nets_unrouted": 0,
        }

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
            num_passes=num_passes,
            max_vias=max_vias,
            progress_callback=lambda line: print(f"[freerouter] {line}", flush=True),
        )
    except Exception as e:
        return {
            "updated_circuit": None,
            "warnings": [f"FreeRouting failed: {e}"],
            "segments_routed": 0,
            "vias_placed": 0,
            "nets_routed": 0,
            "nets_unrouted": 0,
        }

    try:
        routes_result = ses_to_routes(ses_output)
    except Exception as e:
        return {
            "updated_circuit": None,
            "warnings": [f"SES parse failed: {e}"],
            "segments_routed": 0,
            "vias_placed": 0,
            "nets_routed": 0,
            "nets_unrouted": 0,
        }

    updated_circuit = _apply_routes_to_circuit(circuit, routes_result)

    return {
        "updated_circuit": updated_circuit,
        "warnings": [],
        "segments_routed": routes_result.get("segments_routed", 0),
        "vias_placed": routes_result.get("vias_placed", 0),
        "nets_routed": routes_result.get("nets_routed", 0),
        "nets_unrouted": routes_result.get("nets_unrouted", 0),
    }


def _apply_routes_to_circuit(circuit: dict, routes_result: dict) -> dict:
    updated = dict(circuit)
    updated["routes"] = routes_result.get("routes", [])
    updated["vias"] = routes_result.get("vias", [])
    updated["autorouted"] = True
    return updated
