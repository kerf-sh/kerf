import asyncio
import base64
import json
import logging
from typing import Optional

import asyncpg

try:
    from workers.base import BaseWorker
except ImportError:
    from kerf_fem._compat import BaseWorker

logger = logging.getLogger(__name__)


class FEMInputSpec:
    def __init__(
        self,
        material_props: Optional[dict] = None,
        boundary_conditions: Optional[list] = None,
        loads: Optional[list] = None,
        mesh_size: float = 0.0,
        solver: str = "fenicsx",
        analysis_type: str = "linear_static",
    ):
        self.material_props = material_props or {}
        self.boundary_conditions = boundary_conditions or []
        self.loads = loads or []
        self.mesh_size = mesh_size
        self.solver = solver
        self.analysis_type = analysis_type

    @classmethod
    def from_dict(cls, d: dict) -> "FEMInputSpec":
        return cls(
            material_props=d.get("material_props", {}),
            boundary_conditions=d.get("boundary_conditions", []),
            loads=d.get("loads", []),
            mesh_size=d.get("mesh_size", 0.0),
            solver=d.get("solver", "fenicsx"),
            analysis_type=d.get("analysis_type", "linear_static"),
        )

    def to_dict(self) -> dict:
        return {
            "material_props": self.material_props,
            "boundary_conditions": self.boundary_conditions,
            "loads": self.loads,
            "mesh_size": self.mesh_size,
            "solver": self.solver,
            "analysis_type": self.analysis_type,
        }


class FEMResult:
    def __init__(
        self,
        max_vonmises_stress: float = 0.0,
        max_displacement: float = 0.0,
        displacement: Optional[dict] = None,
        fos: float = 0.0,
        frequencies: Optional[list] = None,
        mode_shapes: Optional[list] = None,
        temperatures: Optional[list] = None,
        warnings: Optional[list] = None,
        errors: Optional[list] = None,
    ):
        self.max_vonmises_stress = max_vonmises_stress
        self.max_displacement = max_displacement
        self.displacement = displacement or {}
        self.fos = fos
        self.frequencies = frequencies or []
        self.mode_shapes = mode_shapes or []
        self.temperatures = temperatures or []
        self.warnings = warnings or []
        self.errors = errors or []

    def to_dict(self) -> dict:
        return {
            "max_vonmises_stress": self.max_vonmises_stress,
            "max_displacement": self.max_displacement,
            "displacement": self.displacement,
            "fos": self.fos,
            "frequencies": self.frequencies,
            "mode_shapes": self.mode_shapes,
            "temperatures": self.temperatures,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class FEMDriver:
    def __init__(self, pyworker_url: str = "http://localhost:8090", timeout: int = 300):
        self.pyworker_url = pyworker_url
        self.timeout = timeout

    async def run_fem(self, step_bytes: bytes, spec: FEMInputSpec) -> FEMResult:
        import aiohttp

        req = {
            "step_b64": base64.b64encode(step_bytes).decode(),
            "input_spec": spec.to_dict(),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.pyworker_url}/run-fem",
                json=req,
                timeout=aiohttp.ClientTimeout(total=self.timeout + 30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"pyworker status {resp.status}: {body}")

                data = await resp.json()

                if data.get("error"):
                    raise RuntimeError(f"pyworker error: {data['error']}")

                if not data.get("result_b64"):
                    raise RuntimeError("pyworker returned no result")

                result_bytes = base64.b64decode(data["result_b64"])
                result_data = json.loads(result_bytes)

                return FEMResult(
                    max_vonmises_stress=result_data.get("max_vonmises_stress", 0.0),
                    max_displacement=result_data.get("max_displacement", 0.0),
                    displacement=result_data.get("displacement", {}),
                    fos=result_data.get("fos", 0.0),
                    frequencies=result_data.get("frequencies", []),
                    mode_shapes=result_data.get("mode_shapes", []),
                    temperatures=result_data.get("temperatures", []),
                    warnings=result_data.get("warnings", []),
                    errors=result_data.get("errors", []),
                )


class FEMWorker(BaseWorker):
    def __init__(
        self,
        pool: asyncpg.Pool,
        storage_getter,
        pyworker_url: str = "http://localhost:8090",
        poll_interval: float = 5.0,
        timeout: int = 300,
    ):
        super().__init__("fem", pool, poll_interval)
        self.storage_getter = storage_getter
        self.driver = FEMDriver(pyworker_url=pyworker_url, timeout=timeout)
        self.timeout = timeout

    async def run_one(self) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                job = await self.claim_job(conn, "fem_jobs", "files")
                if job is None:
                    return False

                job_id = job["id"]
                file_id = job["file_id"]
                storage_key = job["storage_key"]
                input_spec_raw = job["input_spec"]

                input_spec = FEMInputSpec.from_dict(
                    input_spec_raw if isinstance(input_spec_raw, dict)
                    else json.loads(input_spec_raw) if input_spec_raw else {}
                )

        storage = self.storage_getter()
        try:
            rc = await storage.get(storage_key)
            step_bytes = await rc.read()
            await rc.close()
        except Exception as e:
            logger.error(f"fem: download step failed (job={job_id}): {e}")
            await self.mark_error("fem_jobs", job_id, f"download step: {e}")
            return True

        if not step_bytes:
            await self.mark_error("fem_jobs", job_id, "empty step file")
            return True

        try:
            async with asyncio.timeout(self.timeout):
                result = await self.driver.run_fem(step_bytes, input_spec)
        except asyncio.TimeoutError:
            await self.mark_error("fem_jobs", job_id, "fem computation timeout")
            return True
        except Exception as e:
            logger.error(f"fem: job={job_id} failed: {e}")
            await self.mark_error("fem_jobs", job_id, str(e))
            return True

        await self.mark_done("fem_jobs", job_id, result.to_dict())
        logger.info(f"fem: job={job_id} file={file_id} done")
        return True
