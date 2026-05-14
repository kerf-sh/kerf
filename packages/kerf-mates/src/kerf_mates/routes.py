"""
Assembly mates solver endpoint.

POST /run-mates
Body: {
    "components": [...],
    "mates": [...],
    "fixed_component_id": str | null
}

Delegates to the solvespace_wrapper pure-Python solver.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Optional

router = APIRouter()


class MatesRequest(BaseModel):
    components: list[dict[str, Any]] = []
    mates: list[dict[str, Any]] = []
    fixed_component_id: Optional[str] = None


@router.post("/run-mates")
async def run_mates(req: MatesRequest):
    """
    Solve geometric constraints for an assembly.

    Returns solved component transforms, tolerance stack-up, and solver
    convergence info. Falls back gracefully if the solver fails.
    """
    try:
        from kerf_mates.solver import solve_assembly
        result = solve_assembly(
            components=req.components,
            mates=req.mates,
            fixed_component_id=req.fixed_component_id,
        )
        return {
            "solved": result["solved"],
            "component_transforms": result["component_transforms"],
            "tolerance_stackup": result["tolerance_stackup"],
            "residuals": result["residuals"],
            "iterations": result["iterations"],
            "error": result.get("error", ""),
        }
    except Exception as exc:
        return {
            "solved": False,
            "component_transforms": {},
            "tolerance_stackup": {},
            "residuals": [],
            "iterations": 0,
            "error": f"Solver error: {exc}",
        }
