"""
Tessellation via occt-import-js Node sidecar.

POST /run-tess
Body: {
    "step_b64": string (base64-encoded STEP file),
    "input_spec": {
        "resolution": int,
        "export_format": string,
        "scale": float
    }
}

Returns: {
    "glb_b64": string (base64-encoded GLB),
    "warnings": [],
    "errors": []
}
"""

import asyncio
import base64
import json
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class TessInputSpec(BaseModel):
    resolution: int = 50000
    export_format: str = "glb"
    scale: float = 1.0


class TessRequest(BaseModel):
    step_b64: str
    input_spec: TessInputSpec = TessInputSpec()


def _resolve_sidecar_script() -> str:
    candidates = [
        Path(__file__).parent.parent.parent.parent / "scripts" / "step-tessellate.mjs",
        Path(os.getcwd()) / "scripts" / "step-tessellate.mjs",
        Path("scripts/step-tessellate.mjs"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    raise RuntimeError(
        f"step-tessellate.mjs not found (tried {[str(c) for c in candidates]})"
    )


async def _run_sidecar(step_bytes: bytes) -> bytes:
    node_bin = os.getenv("NODE_BIN", "node")
    script = _resolve_sidecar_script()

    req = {"step_b64": base64.b64encode(step_bytes).decode()}
    req_json = json.dumps(req)

    proc = await asyncio.create_subprocess_exec(
        node_bin,
        script,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=req_json.encode())

    if proc.returncode != 0:
        raise RuntimeError(
            f"sidecar exit {proc.returncode}: {stderr.decode()[:500]}"
        )

    lines = stdout.decode().strip().split("\n")
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{"):
            resp = json.loads(line)
            if resp.get("error"):
                raise RuntimeError(f"sidecar error: {resp['error']}")
            if resp.get("glb_b64"):
                return base64.b64decode(resp["glb_b64"])
    raise RuntimeError("sidecar produced no valid JSON response")


@router.post("/run-tess")
async def run_tess(req: TessRequest):
    if not req.step_b64:
        raise HTTPException(status_code=400, detail="step_b64 required")

    try:
        step_bytes = base64.b64decode(req.step_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid step_b64: {e}")

    if not step_bytes:
        return {"glb_b64": "", "warnings": [], "errors": ["empty step bytes"]}

    try:
        glb_bytes = await _run_sidecar(step_bytes)
    except Exception as e:
        logger.error("tessellation failed: %s", e)
        return {"glb_b64": "", "warnings": [], "errors": [str(e)]}

    glb_b64 = base64.b64encode(glb_bytes).decode()
    return {"glb_b64": glb_b64, "warnings": [], "errors": []}